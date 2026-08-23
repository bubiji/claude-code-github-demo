"""阶段 5（频率限制与代理池）共用逻辑。

issue: #8 · 来源: https://scrape.center/

本阶段四个案例（antispider5 / antispider6 / antispider7 / tool1）面对的是同一个
约束：**服务端按「单位时间内的请求次数」计费，超了就封 10 分钟。**

所以本文件的核心不是「怎么解析页面」，而是「怎么让请求发得慢到不触发封禁，
并且在真的挨了限流时优雅退避」。三层结构：

    ① 控速层  RateLimiter    —— 滑动窗口 + 最小间隔的双保险令牌桶
    ② 传输层  PoliteClient   —— 限速 + 指数退避重试 + 限流信号识别 + 统计
    ③ 备份层  ProxyPool      —— 取代理 → 校验可用 → 失败剔除（tool1）

设计取向（重要）
----------------
**主动控速优先，代理只是补充。** 免费公开代理的可用率极低（tool1 的实测数字见
该案例 README），把「换 IP」当主要手段等于把成功率押在一个不可靠的外部资源上。
正确顺序是：先把发送速率压到限流阈值以下（这一步就足以让全程零封禁），代理只
用来在意外挨封时不至于干等 10 分钟。

**不撞墙。** RateLimiter 是**前置**的：请求发出前就先等够，而不是发出去挨了
429/403 再退避。退避逻辑（Backoff）存在的意义是兜底，不是主路径。
"""

from __future__ import annotations

import json
import os
import random
import re
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Iterator, Optional

import requests

DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# scrape.center antispider5/6/7 三站声明的配额，逐字引自案例描述：
#   「限制单个 IP 访问频率 5 分钟最多 10 次，如果过多则会封禁 IP 10 分钟。」
SITE_QUOTA = 10       # 次
SITE_WINDOW = 300.0   # 秒（5 分钟）
BAN_SECONDS = 600.0   # 封禁时长（10 分钟）


# --------------------------------------------------------------------------
# ① 控速层
# --------------------------------------------------------------------------


class RateLimiter:
    """滑动窗口令牌桶 + 最小间隔，双保险。

    只用滑动窗口不够：窗口允许「瞬间打满 9 发再干等 300 秒」，而服务端如果是
    **固定 5 分钟桶**（django-ratelimit 的默认实现就是固定桶），跨桶边界的一次
    突发就可能在同一个桶里落进 10 次以上。

    只用最小间隔也不够：间隔算的是「相邻两次」，遇上重试插队、多线程共用同一个
    出口 IP 时，窗口内总数照样会超。

    两个一起用，取满足条件的最晚时刻：

        capacity=9, window=300  →  任意 300 秒滑动窗口内不超过 9 次
        min_interval=35         →  相邻两次至少隔 35 秒

    为什么 capacity 取 9 而不是 10：站点声明的是「最多 10 次」，边界值本身是否
    计入封禁不确定（`>=` 还是 `>`），且我们的时钟和服务端的时钟不同步。留 1 次
    余量的代价是慢 10%，收益是不用赌。同理 min_interval 取 35 秒而不是 30 秒
    （300/10）：35 秒下任一 300 秒窗口最多落进 floor(300/35)+1 = 9 次，即便服务端
    用固定桶也超不了。
    """

    def __init__(
        self,
        capacity: int = SITE_QUOTA - 1,
        window: float = SITE_WINDOW,
        min_interval: float = 35.0,
        jitter: float = 1.5,
        name: str = "",
    ) -> None:
        self.capacity = capacity
        self.window = window
        self.min_interval = min_interval
        self.jitter = jitter
        self.name = name
        self._hits: deque[float] = deque()
        self._last: float = 0.0
        self._lock = threading.Lock()
        self.total_wait = 0.0

    def _earliest(self, now: float) -> float:
        """返回下一次可以发请求的最早时刻。"""
        # 约束 A：最小间隔
        t_interval = self._last + self.min_interval if self._last else 0.0
        # 约束 B：滑动窗口容量
        while self._hits and now - self._hits[0] >= self.window:
            self._hits.popleft()
        t_window = 0.0
        if len(self._hits) >= self.capacity:
            # 等最老的那一次滑出窗口
            t_window = self._hits[0] + self.window
        return max(t_interval, t_window)

    def acquire(self, on_wait: Optional[Callable[[float], None]] = None) -> float:
        """阻塞到可以安全发请求为止，返回实际等待秒数。"""
        with self._lock:
            now = time.time()
            target = self._earliest(now)
            wait = max(0.0, target - now)
            if wait > 0:
                wait += random.uniform(0, self.jitter)
                if on_wait:
                    on_wait(wait)
                time.sleep(wait)
                self.total_wait += wait
            t = time.time()
            self._hits.append(t)
            self._last = t
            return wait

    def penalize(self, seconds: float) -> None:
        """挨了限流：直接把下一次可发时刻推后 seconds 秒。"""
        with self._lock:
            self._last = max(self._last, time.time() + seconds - self.min_interval)

    def state(self) -> dict:
        now = time.time()
        recent = [t for t in self._hits if now - t < self.window]
        return {
            "in_window": len(recent),
            "capacity": self.capacity,
            "window_s": self.window,
            "min_interval_s": self.min_interval,
            "total_wait_s": round(self.total_wait, 1),
        }


# --------------------------------------------------------------------------
# ② 传输层
# --------------------------------------------------------------------------


class RateLimited(Exception):
    """识别出「被限流/被封禁」的信号。"""

    def __init__(self, status: int, hint: str = "", retry_after: Optional[float] = None):
        super().__init__(f"rate limited: HTTP {status} {hint}")
        self.status = status
        self.hint = hint
        self.retry_after = retry_after


# 站点在挨封时可能给出的正文特征（不同案例文案不同，宽松匹配）
BLOCK_PATTERNS = re.compile(
    r"(访问频率|频率过高|请求过于频繁|too many requests|被封禁|暂停访问|forbidden)",
    re.I,
)


@dataclass
class Stats:
    requests: int = 0
    retries: int = 0
    failed: int = 0
    rate_limited: int = 0       # 收到 429/403 等限流信号的次数
    bytes_down: int = 0
    proxy_switches: int = 0
    started_at: float = field(default_factory=time.time)

    def elapsed(self) -> float:
        return time.time() - self.started_at

    def as_dict(self) -> dict:
        return {
            "requests": self.requests,
            "retries": self.retries,
            "failed": self.failed,
            "rate_limited_hits": self.rate_limited,
            "bytes_down": self.bytes_down,
            "proxy_switches": self.proxy_switches,
            "elapsed_s": round(self.elapsed(), 1),
        }


class PoliteClient:
    """带前置限速与指数退避的 HTTP 客户端。

    调用顺序永远是：**先 limiter.acquire() 等够，再发请求**。
    只有在等够了还挨限流时，才走 Backoff 路径（说明我们对配额的估计错了，
    此时唯一正确的动作是退得更久，而不是立刻重试）。
    """

    def __init__(
        self,
        limiter: Optional[RateLimiter] = None,
        timeout: float = 25.0,
        retries: int = 4,
        backoff_base: float = 20.0,
        backoff_cap: float = BAN_SECONDS + 60,
        headers: Optional[dict] = None,
        proxy_pool: Optional["ProxyPool"] = None,
        verbose: bool = True,
    ) -> None:
        self.limiter = limiter or RateLimiter()
        self.timeout = timeout
        self.retries = retries
        self.backoff_base = backoff_base
        self.backoff_cap = backoff_cap
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": DEFAULT_UA, "Accept": "*/*"})
        if headers:
            self.session.headers.update(headers)
        self.proxy_pool = proxy_pool
        self.verbose = verbose
        self.stats = Stats()
        self.events: list[dict] = []   # 时间线：每次请求的 (t, url, status, wait)

    # -- 日志 --------------------------------------------------------------
    def log(self, msg: str) -> None:
        if self.verbose:
            print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

    # -- 限流信号识别 ------------------------------------------------------
    @staticmethod
    def detect_block(resp: requests.Response) -> Optional[RateLimited]:
        ra = resp.headers.get("Retry-After")
        retry_after = None
        if ra:
            try:
                retry_after = float(ra)
            except ValueError:
                retry_after = None
        if resp.status_code in (429, 503):
            return RateLimited(resp.status_code, "status", retry_after)
        if resp.status_code == 403:
            return RateLimited(403, "forbidden", retry_after)
        # 200 但正文是封禁提示（有些站用 200 返回拦截页）
        ctype = resp.headers.get("Content-Type", "")
        if resp.status_code == 200 and "html" in ctype and len(resp.text) < 4000:
            if BLOCK_PATTERNS.search(resp.text):
                return RateLimited(200, "blocked-body", retry_after)
        return None

    # -- 主入口 ------------------------------------------------------------
    def get(self, url: str, params: Optional[dict] = None, **kw) -> requests.Response:
        last_exc: Optional[Exception] = None
        for attempt in range(self.retries + 1):
            waited = self.limiter.acquire(
                on_wait=lambda w: self.log(f"控速等待 {w:.1f}s → {url}")
            )
            proxies = None
            proxy = None
            if self.proxy_pool:
                proxy = self.proxy_pool.get()
                if proxy:
                    proxies = {"http": f"http://{proxy}", "https": f"http://{proxy}"}
            t0 = time.time()
            try:
                resp = self.session.get(
                    url,
                    params=params,
                    timeout=self.timeout,
                    proxies=proxies,
                    **kw,
                )
            except requests.RequestException as e:
                last_exc = e
                self.stats.retries += 1
                if proxy and self.proxy_pool:
                    self.proxy_pool.drop(proxy, f"{type(e).__name__}")
                    self.stats.proxy_switches += 1
                sleep = self._backoff(attempt)
                self.log(f"网络错误 {type(e).__name__}，退避 {sleep:.1f}s（第 {attempt+1} 次）")
                time.sleep(sleep)
                continue

            self.stats.requests += 1
            self.stats.bytes_down += len(resp.content)
            self.events.append(
                {
                    "t": round(t0, 3),
                    "url": resp.url,
                    "status": resp.status_code,
                    "wait_before_s": round(waited, 1),
                    "elapsed_s": round(resp.elapsed.total_seconds(), 3),
                    "bytes": len(resp.content),
                }
            )
            blocked = self.detect_block(resp)
            if blocked is None:
                return resp

            # 走到这里说明「等够了还是挨了限流」——我们对配额的估计偏乐观
            self.stats.rate_limited += 1
            self.log(
                f"!! 触发限流：HTTP {blocked.status} ({blocked.hint}) at {resp.url}"
            )
            if proxy and self.proxy_pool:
                self.proxy_pool.drop(proxy, "rate-limited")
                self.stats.proxy_switches += 1
            sleep = blocked.retry_after or self._backoff(attempt, floor=BAN_SECONDS)
            self.limiter.penalize(sleep)
            self.log(f"退避 {sleep:.0f}s 后重试（第 {attempt+1} 次）")
            self.stats.retries += 1
            time.sleep(sleep)
            last_exc = blocked

        self.stats.failed += 1
        raise last_exc or RuntimeError(f"GET failed: {url}")

    def get_json(self, url: str, params: Optional[dict] = None, **kw) -> Any:
        return self.get(url, params=params, **kw).json()

    def _backoff(self, attempt: int, floor: float = 0.0) -> float:
        """指数退避 + 满抖动（full jitter）。

        base * 2**attempt 作上界随机取值，避免多个客户端同步重试撞在一起。
        floor 用于「明确挨封」的场景：站点说封 10 分钟，退避就不能小于 10 分钟，
        否则就是在封禁期里反复撞墙、把封禁续期。
        """
        hi = min(self.backoff_cap, self.backoff_base * (2 ** attempt))
        return max(floor, random.uniform(hi / 2, hi))

    def report(self) -> dict:
        d = self.stats.as_dict()
        d["limiter"] = self.limiter.state()
        return d


# --------------------------------------------------------------------------
# ③ 备份层：代理池
# --------------------------------------------------------------------------

PROXY_POOL_API = "https://proxypool.scrape.center/random"


@dataclass
class ProxyStat:
    fetched: int = 0
    unique: int = 0
    checked: int = 0
    alive: int = 0
    dropped: int = 0

    def as_dict(self) -> dict:
        d = {
            "fetched": self.fetched,
            "unique": self.unique,
            "checked": self.checked,
            "alive": self.alive,
            "dropped": self.dropped,
        }
        d["alive_rate"] = round(self.alive / self.checked, 4) if self.checked else 0.0
        return d


class ProxyPool:
    """tool1：代理池客户端 —— 取代理 → 校验可用 → 失败剔除。

    三个动作缺一不可：
      · **取**：GET https://proxypool.scrape.center/random，每次返回一条 ip:port。
        接口不保证不重复，所以要按需重复取直到凑够 N 个**去重**后的候选。
      · **校验**：拿候选代理去请求一个已知可用的探针 URL，能在 timeout 内返回
        期望响应才算活。**不校验就直接用等于把失败推迟到正式抓取时发生**，那时
        一次失败要赔上一次配额。
      · **剔除**：正式使用中一旦失败（连不上/超时/被限流），立刻从池里删掉，
        不再回收——公开代理的失败基本是永久性的。

    现实提醒：公开免费代理的可用率非常低，实测数字见 tool1/README.md。
    """

    def __init__(
        self,
        api: str = PROXY_POOL_API,
        probe_url: str = "https://httpbin.org/ip",
        timeout: float = 8.0,
        verbose: bool = True,
    ) -> None:
        self.api = api
        self.probe_url = probe_url
        self.timeout = timeout
        self.verbose = verbose
        self.alive: list[str] = []
        self.dead: dict[str, str] = {}
        self.stat = ProxyStat()
        self._i = 0
        self.checks: list[dict] = []

    def log(self, msg: str) -> None:
        if self.verbose:
            print(f"[{time.strftime('%H:%M:%S')}] [proxy] {msg}", flush=True)

    # -- 取 ---------------------------------------------------------------
    def fetch(self, n: int, max_tries: Optional[int] = None) -> list[str]:
        """向代理池要 n 个**去重**后的候选代理。"""
        max_tries = max_tries or n * 4
        seen: list[str] = []
        s = set()
        for _ in range(max_tries):
            if len(seen) >= n:
                break
            try:
                r = requests.get(self.api, timeout=self.timeout)
                self.stat.fetched += 1
                p = r.text.strip()
            except requests.RequestException as e:
                self.log(f"取代理失败 {type(e).__name__}")
                continue
            if not re.fullmatch(r"[\d.]+:\d+", p):
                continue
            if p in s:
                continue
            s.add(p)
            seen.append(p)
        self.stat.unique = len(seen)
        self.log(f"取到 {len(seen)} 个去重候选（API 调用 {self.stat.fetched} 次）")
        return seen

    # -- 校验 -------------------------------------------------------------
    def check_one(self, proxy: str) -> dict:
        proxies = {"http": f"http://{proxy}", "https": f"http://{proxy}"}
        t0 = time.time()
        rec = {"proxy": proxy, "ok": False, "reason": "", "latency_s": None}
        try:
            r = requests.get(
                self.probe_url,
                proxies=proxies,
                timeout=self.timeout,
                headers={"User-Agent": DEFAULT_UA},
            )
            rec["status"] = r.status_code
            rec["latency_s"] = round(time.time() - t0, 2)
            if r.status_code == 200:
                rec["ok"] = True
            else:
                rec["reason"] = f"HTTP {r.status_code}"
        except requests.RequestException as e:
            rec["reason"] = type(e).__name__
            rec["latency_s"] = round(time.time() - t0, 2)
        return rec

    def validate(self, candidates: Iterable[str], workers: int = 16) -> list[str]:
        """并发校验候选代理，只保留活的。

        校验阶段可以并发——它打的是代理服务器和探针 URL，不是被限流的目标站。
        """
        from concurrent.futures import ThreadPoolExecutor

        cands = list(candidates)
        with ThreadPoolExecutor(max_workers=workers) as ex:
            recs = list(ex.map(self.check_one, cands))
        self.checks.extend(recs)
        self.stat.checked += len(recs)
        alive = [r["proxy"] for r in recs if r["ok"]]
        self.stat.alive += len(alive)
        for r in recs:
            if not r["ok"]:
                self.dead[r["proxy"]] = r["reason"]
        self.alive.extend(alive)
        self.log(
            f"校验 {len(recs)} 个 → 存活 {len(alive)} 个"
            f"（可用率 {len(alive)/len(recs)*100:.1f}%）"
            if recs
            else "无候选可校验"
        )
        return alive

    def refill(self, n: int = 20) -> list[str]:
        return self.validate(self.fetch(n))

    # -- 用 & 剔除 ---------------------------------------------------------
    def get(self) -> Optional[str]:
        """轮询取一个存活代理；池空返回 None（调用方应回退到直连）。"""
        if not self.alive:
            return None
        self._i = (self._i + 1) % len(self.alive)
        return self.alive[self._i]

    def drop(self, proxy: str, reason: str = "") -> None:
        if proxy in self.alive:
            self.alive.remove(proxy)
            self.stat.dropped += 1
            self.dead[proxy] = reason
            self.log(f"剔除 {proxy}（{reason}），剩余 {len(self.alive)}")

    def report(self) -> dict:
        return {
            "api": self.api,
            "probe_url": self.probe_url,
            "timeout_s": self.timeout,
            **self.stat.as_dict(),
            "alive_now": list(self.alive),
        }


# --------------------------------------------------------------------------
# 通用工具
# --------------------------------------------------------------------------


def budget(n_requests: int, quota: int = SITE_QUOTA, window: float = SITE_WINDOW,
           min_interval: float = 35.0) -> dict:
    """预算计算器：n 个请求在给定配额下串行要跑多久。

    理论下界 = n / quota * window（把配额用满）；
    实际值   = (n - 1) * min_interval（我们留了安全余量的固定间隔）。
    """
    ideal = n_requests / quota * window
    actual = max(0, n_requests - 1) * min_interval
    return {
        "n_requests": n_requests,
        "quota": f"{quota}/{int(window)}s",
        "ideal_s": round(ideal),
        "ideal_min": round(ideal / 60, 1),
        "planned_interval_s": min_interval,
        "planned_s": round(actual),
        "planned_min": round(actual / 60, 1),
    }


def summarize(items: list[dict], numeric: Iterable[str] = ("score",),
              categorical: Iterable[str] = ()) -> dict:
    """给 items 生成统计摘要。

    落盘降级（>500KB 只留前 100 条）之后，摘要就是全量数据**唯一**留在仓库里的
    证据，所以它必须是对**全量**算的，不是对截断后那 100 条算的。
    """
    from collections import Counter

    out: dict[str, Any] = {"n": len(items)}
    for key in numeric:
        vals = []
        for it in items:
            v = it.get(key)
            try:
                if v is not None and v != "":
                    vals.append(float(v))
            except (TypeError, ValueError):
                pass
        if vals:
            vals.sort()
            n = len(vals)
            out[key] = {
                "n_with_value": n,
                "min": round(vals[0], 2),
                "max": round(vals[-1], 2),
                "mean": round(sum(vals) / n, 3),
                "median": round(vals[n // 2], 2),
                "buckets": dict(
                    sorted(Counter(int(v) for v in vals).items())
                ),
            }
    for key in categorical:
        c: Counter = Counter()
        for it in items:
            v = it.get(key)
            if isinstance(v, list):
                c.update(str(x) for x in v)
            elif v not in (None, ""):
                c[str(v)] += 1
        if c:
            out[key] = {
                "distinct": len(c),
                "top20": dict(c.most_common(20)),
            }
    return out


def save_json(path: str, payload: Any, max_bytes: int = 500 * 1024,
              head: int = 100) -> dict:
    """落盘 JSON；超过 max_bytes 时降级为「前 head 条 + 统计摘要」。

    返回落盘信息（含是否降级），方便写进 README 与 issue 评论。
    """
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    info = {"path": path, "bytes": len(text.encode()), "truncated": False}
    if len(text.encode()) > max_bytes and isinstance(payload, dict):
        items = payload.get("items")
        if isinstance(items, list) and len(items) > head:
            reduced = dict(payload)
            reduced["items"] = items[:head]
            reduced["_truncated"] = {
                "reason": f"完整文件 {len(text.encode())} 字节 > {max_bytes} 上限",
                "total_items": len(items),
                "kept_items": head,
            }
            text = json.dumps(reduced, ensure_ascii=False, indent=2)
            info["truncated"] = True
            info["total_items"] = len(items)
            info["kept_items"] = head
            info["bytes"] = len(text.encode())
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return info


def parse_movie_cards(html: str) -> list[dict]:
    """解析 antispider5 / antispider6 的电影列表页卡片。

    两站前端是同一套 Vue + Element UI 模板（`.el-card.item`），字段位置一致，
    所以解析器共用一份；区别只在 antispider6 要先登录拿 sessionid。
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    out: list[dict] = []
    for card in soup.select(".el-card.item"):
        a = card.select_one("a.name")
        h2 = card.select_one("a.name h2")
        title = h2.get_text(strip=True) if h2 else ""
        name_cn, _, name_en = title.partition(" - ")
        infos = [
            d.get_text(" ", strip=True) for d in card.select(".m-v-sm.info")
        ]
        regions, duration, published = "", "", ""
        if infos:
            parts = [p.strip() for p in infos[0].split("/")]
            regions = parts[0] if parts else ""
            duration = parts[1] if len(parts) > 1 else ""
        if len(infos) > 1:
            published = infos[1].replace("上映", "").strip()
        score_el = card.select_one("p.score")
        href = a.get("href") if a else ""
        img = card.select_one("img.cover")
        out.append(
            {
                "id": int(re.sub(r"\D", "", href)) if href else None,
                "name": name_cn or title,
                "name_en": name_en,
                "categories": [
                    b.get_text(strip=True) for b in card.select("button.category span")
                ],
                "regions": [r.strip() for r in regions.split("、") if r.strip()],
                "duration": duration,
                "published_at": published,
                "score": float(score_el.get_text(strip=True)) if score_el else None,
                "cover": img.get("src") if img else None,
                "detail_url": href,
            }
        )
    return out


def total_from_pagination(html: str) -> Optional[int]:
    """从 Element UI 分页控件里读「共 N 条」。"""
    m = re.search(r'total">共\s*(\d+)\s*条', html)
    return int(m.group(1)) if m else None


def redact(value: Optional[str], keep: int = 6) -> Optional[str]:
    """凭据脱敏：只留头尾各 keep 个字符。

    练习站的公开账号（admin/admin）本身可以写进仓库，但**登录后拿到的
    sessionid / JWT 是真实凭据**，落盘前必须脱敏（本仓库是公开仓库）。
    """
    if not value:
        return value
    if len(value) <= keep * 2:
        return "*" * len(value)
    return f"{value[:keep]}…{value[-keep:]}（已脱敏，原长 {len(value)}）"
