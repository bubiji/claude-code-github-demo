"""阶段 2（Ajax 与动态渲染）共用逻辑。

issue: #5 · 来源: https://scrape.center/

三层结构，四个案例（spa1 / spa3 / spa4 / spa5）共用：

    ① 传输层   PoliteSession        —— 限速、重试、统一 UA/Referer、请求计数
    ② 分页层   offset_pages()       —— DRF LimitOffsetPagination 通用偏移分页器
    ③ 解析层   Movie / Book / NewsItem
               ├─ build()      唯一的字段清洗与规整实现（真正被复用的那一份）
               ├─ from_api()   适配器：XHR 返回的 JSON dict  → build()
               └─ from_dom()   适配器：渲染后的 DOM 节点      → build()

「接口模式」与「渲染模式」的区别只在**适配器**这一层：两条路径各自把源数据摊平成
同一组原始字段，然后调用同一个 build() 做清洗、类型转换与校验。下游（去重、排序、
落盘、统计）完全不知道数据是从 JSON 来的还是从 HTML 来的。

另有 extract_main_text()：不写死选择器的通用正文提取（spa4 用），按文本密度 +
链接密度对块级节点打分。
"""

from __future__ import annotations

import json
import os
import random
import re
import time
from dataclasses import dataclass, asdict, field
from typing import Any, Callable, Iterable, Iterator, Optional

import requests
from bs4 import BeautifulSoup

# --------------------------------------------------------------------------
# ① 传输层
# --------------------------------------------------------------------------

DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class PoliteSession:
    """礼貌抓取用的 HTTP 会话：固定间隔 + 抖动 + 指数退避重试。

    scrape.center 是作者公开提供的练习平台，本类刻意把并发写死为 1（串行），
    只靠间隔控速，绝不压测。
    """

    def __init__(
        self,
        delay: float = 0.4,
        jitter: float = 0.2,
        timeout: float = 20.0,
        retries: int = 3,
        headers: Optional[dict] = None,
    ) -> None:
        self.delay = delay
        self.jitter = jitter
        self.timeout = timeout
        self.retries = retries
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": DEFAULT_UA, "Accept": "*/*"})
        if headers:
            self.session.headers.update(headers)
        self.n_requests = 0
        self.n_retries = 0
        self.n_failed = 0
        self.bytes_down = 0
        self._last_at = 0.0

    def _wait(self) -> None:
        gap = time.time() - self._last_at
        need = self.delay + random.uniform(0, self.jitter) - gap
        if need > 0:
            time.sleep(need)
        self._last_at = time.time()

    def get(self, url: str, params: Optional[dict] = None, **kw) -> requests.Response:
        last_exc: Optional[Exception] = None
        for attempt in range(1, self.retries + 1):
            self._wait()
            try:
                resp = self.session.get(
                    url, params=params, timeout=self.timeout, **kw
                )
                self.n_requests += 1
                self.bytes_down += len(resp.content or b"")
                if resp.status_code >= 500:
                    raise requests.HTTPError(f"HTTP {resp.status_code}")
                resp.raise_for_status()
                return resp
            except Exception as exc:  # noqa: BLE001 —— 逐次重试，最后再抛
                last_exc = exc
                self.n_retries += 1
                if attempt < self.retries:
                    time.sleep(min(2 ** attempt, 8) + random.uniform(0, 0.5))
        self.n_failed += 1
        raise RuntimeError(f"GET 失败（重试 {self.retries} 次）: {url} -> {last_exc}")

    def get_json(self, url: str, params: Optional[dict] = None, **kw) -> Any:
        return self.get(url, params=params, **kw).json()

    def get_text(self, url: str, params: Optional[dict] = None, **kw) -> str:
        resp = self.get(url, params=params, **kw)
        if not resp.encoding or resp.encoding.lower() == "iso-8859-1":
            resp.encoding = resp.apparent_encoding or "utf-8"
        return resp.text

    def stats(self) -> dict:
        return {
            "requests": self.n_requests,
            "retries": self.n_retries,
            "failed": self.n_failed,
            "bytes_down": self.bytes_down,
        }


# --------------------------------------------------------------------------
# ② 分页层
# --------------------------------------------------------------------------


@dataclass
class Page:
    offset: int
    limit: int
    count: Optional[int]
    results: list


def offset_pages(
    session: PoliteSession,
    api_url: str,
    limit: int = 10,
    start_offset: int = 0,
    max_items: Optional[int] = None,
    extra_params: Optional[dict] = None,
    on_page: Optional[Callable[[Page], None]] = None,
) -> Iterator[Page]:
    """DRF LimitOffsetPagination 通用偏移分页器。

    spa1 / spa3 / spa4 / spa5 四个站的列表接口是同一套后端分页协议：

        GET <api>?limit=<每页条数>&offset=<已跳过条数>
        -> {"count": <总数>, "results": [...]}

    「有页码翻页」（spa1/spa5）与「下拉到底刷新」（spa3/spa4）在 HTTP 层没有任何
    区别，都是 offset += limit；区别只在前端什么时候发这一次请求。所以这一个
    分页器四个案例通用。

    终止条件（任一满足即停）：
      1. 本页 results 为空                —— 后端明确没有更多
      2. offset + len(results) >= count   —— 已覆盖 count 声明的全量
      3. 已产出条数 >= max_items          —— 调用方自己设的上限
    """
    offset = start_offset
    got = 0
    while True:
        params = {"limit": limit, "offset": offset}
        if extra_params:
            params.update(extra_params)
        payload = session.get_json(api_url, params=params)
        results = payload.get("results") or []
        page = Page(
            offset=offset, limit=limit, count=payload.get("count"), results=results
        )
        if on_page:
            on_page(page)
        if not results:
            return
        yield page
        got += len(results)
        offset += len(results)
        if max_items is not None and got >= max_items:
            return
        if page.count is not None and offset >= page.count:
            return


# --------------------------------------------------------------------------
# ③ 解析层：清洗工具
# --------------------------------------------------------------------------

_WS = re.compile(r"[\s　\xa0]+")


def clean_text(value: Any) -> str:
    """压缩空白、去首尾。spa5 的 authors 里带前导换行 + 大段空格，就靠这个规整。"""
    if value is None:
        return ""
    return _WS.sub(" ", str(value)).strip()


def clean_list(values: Any) -> list:
    if not values:
        return []
    if isinstance(values, str):
        values = re.split(r"[、,，/]", values)
    out = []
    for v in values:
        t = clean_text(v)
        if t and t not in out:
            out.append(t)
    return out


def to_float(value: Any) -> Optional[float]:
    t = clean_text(value)
    if not t:
        return None
    m = re.search(r"-?\d+(?:\.\d+)?", t)
    return float(m.group()) if m else None


def to_int(value: Any) -> Optional[int]:
    f = to_float(value)
    return int(f) if f is not None else None


def norm_date(value: Any) -> Optional[str]:
    """把 '1993-07-26 上映' / '1993-07-26' / '2020-10-20T17:23:00Z' 统一成 ISO 日期串。"""
    t = clean_text(value)
    if not t:
        return None
    m = re.search(r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})", t)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return t or None


def split_name_alias(title: str) -> tuple:
    """'霸王别姬 - Farewell My Concubine' -> ('霸王别姬', 'Farewell My Concubine')"""
    t = clean_text(title)
    if " - " in t:
        head, _, tail = t.partition(" - ")
        return clean_text(head), clean_text(tail)
    return t, ""


# --------------------------------------------------------------------------
# ③ 解析层：实体（build 是唯一实现，from_api / from_dom 只是适配器）
# --------------------------------------------------------------------------


@dataclass
class Movie:
    """spa1 / spa3（以及服务端渲染孪生站 ssr1）的电影条目。"""

    id: Optional[str]
    name: str
    alias: str
    categories: list
    regions: list
    score: Optional[float]
    published_at: Optional[str]
    minute: Optional[int]
    cover: str
    source: str = ""
    extra: dict = field(default_factory=dict)

    # ---- 唯一的清洗实现 --------------------------------------------------
    @classmethod
    def build(cls, **raw) -> "Movie":
        name, alias = raw.get("name", ""), raw.get("alias", "")
        if not alias and " - " in clean_text(name):
            name, alias = split_name_alias(name)
        return cls(
            id=clean_text(raw.get("id")) or None,
            name=clean_text(name),
            alias=clean_text(alias),
            categories=clean_list(raw.get("categories")),
            regions=clean_list(raw.get("regions")),
            score=to_float(raw.get("score")),
            published_at=norm_date(raw.get("published_at")),
            minute=to_int(raw.get("minute")),
            cover=clean_text(raw.get("cover")),
            source=raw.get("source", ""),
            extra={k: v for k, v in (raw.get("extra") or {}).items() if v},
        )

    # ---- 适配器 A：接口模式（XHR JSON） ---------------------------------
    @classmethod
    def from_api(cls, obj: dict, source: str = "api") -> "Movie":
        extra = {}
        for k in ("drama", "actors", "directors", "photos"):
            if obj.get(k):
                extra[k] = obj[k]
        return cls.build(
            id=obj.get("id"),
            name=obj.get("name"),
            alias=obj.get("alias"),
            categories=obj.get("categories"),
            regions=obj.get("regions"),
            score=obj.get("score"),
            published_at=obj.get("published_at"),
            minute=obj.get("minute"),
            cover=obj.get("cover"),
            source=source,
            extra=extra,
        )

    # ---- 适配器 B：渲染模式（渲染后的 DOM 卡片节点） --------------------
    @classmethod
    def from_dom(cls, card, source: str = "dom") -> "Movie":
        """card 为一张电影卡片（Element-UI el-card）的节点。

        只依赖该模板必然存在的结构（标题 h2、按钮里的分类、info 行、score 行），
        不依赖 data-v-xxxx 之类构建期哈希。
        """
        h2 = card.find(["h2", "h3"])
        title = h2.get_text(" ", strip=True) if h2 else ""
        name, alias = split_name_alias(title)

        categories = [
            b.get_text(" ", strip=True)
            for b in card.select("button, .category")
            if b.get_text(strip=True)
        ]

        regions, minute, published = [], None, None
        for line in card.select("div.info, .m-v-sm"):
            text = line.get_text(" ", strip=True)
            if not text:
                continue
            if "分钟" in text and not minute:
                minute = to_int(text.split("分钟")[0].split("/")[-1])
            if "上映" in text and not published:
                published = norm_date(text)
            if not regions and "分钟" in text:
                head = text.split("/")[0]
                regions = clean_list(head)

        score_el = card.select_one(".score")
        img = card.find("img")
        link = card.find("a", href=True)
        mid = None
        if link:
            m = re.search(r"/detail/(\d+)", link["href"])
            mid = m.group(1) if m else None

        return cls.build(
            id=mid,
            name=name,
            alias=alias,
            categories=categories,
            regions=regions,
            score=score_el.get_text(strip=True) if score_el else None,
            published_at=published,
            minute=minute,
            cover=img.get("src") if img else "",
            source=source,
        )


@dataclass
class Book:
    """spa5 的图书条目。"""

    id: Optional[str]
    name: str
    authors: list
    score: Optional[float]
    cover: str
    source: str = ""
    extra: dict = field(default_factory=dict)

    @classmethod
    def build(cls, **raw) -> "Book":
        return cls(
            id=clean_text(raw.get("id")) or None,
            name=clean_text(raw.get("name")),
            authors=clean_list(raw.get("authors")),
            score=to_float(raw.get("score")),
            cover=clean_text(raw.get("cover")),
            source=raw.get("source", ""),
            extra={k: v for k, v in (raw.get("extra") or {}).items() if v},
        )

    @classmethod
    def from_api(cls, obj: dict, source: str = "api") -> "Book":
        extra = {}
        for k in ("tags", "price", "published_at", "publisher", "isbn", "comments"):
            if obj.get(k):
                extra[k] = obj[k]
        return cls.build(
            id=obj.get("id"),
            name=obj.get("name"),
            authors=obj.get("authors"),
            score=obj.get("score"),
            cover=obj.get("cover"),
            source=source,
            extra=extra,
        )

    @classmethod
    def from_dom(cls, card, source: str = "dom") -> "Book":
        title_el = card.find(["h3", "h2"])
        authors_el = card.select_one(".authors")
        score_el = card.select_one(".score")
        img = card.find("img")
        link = card.find("a", href=True)
        bid = None
        if link:
            m = re.search(r"/detail/([\w-]+)", link["href"])
            bid = m.group(1) if m else None
        return cls.build(
            id=bid,
            name=title_el.get_text(" ", strip=True) if title_el else "",
            authors=authors_el.get_text(" ", strip=True) if authors_el else "",
            score=score_el.get_text(strip=True) if score_el else None,
            cover=img.get("src") if img else "",
            source=source,
        )


@dataclass
class NewsItem:
    """spa4 的新闻索引条目（索引页给的是元数据 + 外站原文链接）。"""

    id: Optional[str]
    title: str
    url: str
    website: str
    domain: str
    published_at: Optional[str]
    thumb: str
    source: str = ""
    extra: dict = field(default_factory=dict)

    @classmethod
    def build(cls, **raw) -> "NewsItem":
        url = clean_text(raw.get("url"))
        domain = clean_text(raw.get("domain"))
        if not domain and url:
            m = re.match(r"https?://([^/]+)", url)
            domain = m.group(1) if m else ""
        return cls(
            id=clean_text(raw.get("id")) or None,
            title=clean_text(raw.get("title")),
            url=url,
            website=clean_text(raw.get("website")),
            domain=domain,
            published_at=clean_text(raw.get("published_at")) or None,
            thumb=clean_text(raw.get("thumb")),
            source=raw.get("source", ""),
            extra={k: v for k, v in (raw.get("extra") or {}).items() if v},
        )

    @classmethod
    def from_api(cls, obj: dict, source: str = "api") -> "NewsItem":
        return cls.build(
            id=obj.get("id"),
            title=obj.get("title"),
            url=obj.get("url"),
            website=obj.get("website"),
            domain=obj.get("domain"),
            published_at=obj.get("published_at"),
            thumb=obj.get("thumb"),
            source=source,
            extra={"code": obj.get("code"), "updated_at": obj.get("updated_at")},
        )

    @classmethod
    def from_dom(cls, doc, url: str = "", source: str = "dom") -> "NewsItem":
        """从一篇**外站新闻原文**的 DOM 里还原出同样的字段。

        标题、发布时间、站点名都走通用信号（og:* / article:* / h1 / <title>），
        不写死任何一家新闻站的选择器。
        """
        meta = _meta_map(doc)
        h1 = doc.find("h1")
        title = (
            meta.get("og:title")
            or (h1.get_text(" ", strip=True) if h1 else "")
            or (doc.title.get_text(strip=True) if doc.title else "")
        )
        return cls.build(
            id=None,
            title=title,
            url=meta.get("og:url") or url,
            website=meta.get("og:site_name") or meta.get("application-name") or "",
            domain="",
            published_at=(
                meta.get("article:published_time")
                or meta.get("publishdate")
                or meta.get("weibo: article:create_at")
                or ""
            ),
            thumb=meta.get("og:image", ""),
            source=source,
        )


def _meta_map(doc) -> dict:
    out = {}
    for m in doc.find_all("meta"):
        key = m.get("property") or m.get("name") or m.get("itemprop")
        val = m.get("content")
        if key and val:
            out.setdefault(key.strip().lower(), val.strip())
    return out


def dom_cards(html: str, selector: str = ".el-card") -> list:
    """把渲染后的列表页 HTML 切成一张张卡片节点，交给 *.from_dom()。"""
    soup = BeautifulSoup(html, "lxml")
    cards = soup.select(selector)
    return [c for c in cards if c.find(["h2", "h3"])]


# --------------------------------------------------------------------------
# 通用正文提取（spa4「智能页面提取」用；不写死任何站点选择器）
# --------------------------------------------------------------------------

_DROP_TAGS = (
    "script style noscript iframe svg canvas form input button select "
    "nav header footer aside figure figcaption"
).split()

_BLOCK_TAGS = ["article", "main", "section", "div", "td", "body"]


def extract_main_text(html: str, min_chars: int = 120) -> dict:
    """通用正文提取：按「文本密度 + 链接密度」给块级节点打分，取最高分。

    思路（无站点先验，纯结构统计）：
      1. 先物理删掉不可能是正文的标签（脚本、导航、页脚、表单……）。
      2. 对每个块级节点算四个量：
         text_len   —— 该节点内 <p> 段落的总字数（没有 <p> 时退回全节点文本）
         link_len   —— 节点内 <a> 的锚文本字数
         link_ratio —— link_len / text_len，导航/推荐位会非常高
         density    —— text_len / (后代标签数 + 1)，正文是「字多标签少」
      3. score = text_len * (1 - link_ratio) * (0.5 + min(density, 40) / 40)
         链接密度 > 0.5 的节点直接淘汰。
      4. 取分最高的节点，按 <p>/<br> 边界还原成段落。
    """
    soup = BeautifulSoup(html, "lxml")
    for tag in soup.find_all(_DROP_TAGS):
        tag.decompose()
    for c in soup.find_all(string=lambda s: isinstance(s, str) and s.strip().startswith("<!--")):
        c.extract()

    best, best_score, best_stats = None, 0.0, {}
    for node in soup.find_all(_BLOCK_TAGS):
        paras = node.find_all("p")
        if paras:
            text = "\n".join(p.get_text(" ", strip=True) for p in paras)
        else:
            text = node.get_text(" ", strip=True)
        text_len = len(clean_text(text))
        if text_len < min_chars:
            continue
        link_len = sum(len(clean_text(a.get_text())) for a in node.find_all("a"))
        link_ratio = link_len / text_len if text_len else 1.0
        if link_ratio > 0.5:
            continue
        n_tags = len(node.find_all(True)) + 1
        density = text_len / n_tags
        score = text_len * (1 - link_ratio) * (0.5 + min(density, 40) / 40)
        if score > best_score:
            best, best_score = node, score
            best_stats = {
                "text_len": text_len,
                "link_ratio": round(link_ratio, 3),
                "density": round(density, 2),
                "tag": node.name,
                "n_tags": n_tags,
            }

    if best is None:
        body = soup.body or soup
        body_chars = len(clean_text(body.get_text(" ", strip=True)))
        return {
            "ok": False,
            "title": _doc_title(soup),
            "text": "",
            "stats": {},
            # 区分两种失败：HTML 里压根没正文（前端二次加载） vs 有文本但都是导航
            "reason": (
                "HTML 内无正文文本（疑似正文由 JS 二次加载，需再挖一层接口或渲染）"
                if body_chars < min_chars
                else "有文本但所有候选节点链接密度过高或过短（疑似索引/导航页）"
            ),
            "body_chars": body_chars,
            "n_p_tags": len(soup.find_all("p")),
        }

    paras = [p.get_text(" ", strip=True) for p in best.find_all("p")]
    paras = [clean_text(p) for p in paras if len(clean_text(p)) > 1]
    if not paras:
        raw = best.get_text("\n", strip=True)
        paras = [clean_text(p) for p in raw.split("\n") if len(clean_text(p)) > 1]

    return {
        "ok": True,
        "title": _doc_title(soup),
        "text": "\n".join(paras),
        "n_paragraphs": len(paras),
        "n_chars": len("\n".join(paras)),
        "score": round(best_score, 1),
        "stats": best_stats,
    }


def _doc_title(soup) -> str:
    meta = _meta_map(soup)
    if meta.get("og:title"):
        return clean_text(meta["og:title"])
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        return clean_text(h1.get_text(" ", strip=True))
    return clean_text(soup.title.get_text()) if soup.title else ""


# --------------------------------------------------------------------------
# 落盘
# --------------------------------------------------------------------------

SIZE_CAP = 500 * 1024  # 仓库纪律：单文件超 500KB 只存前 100 条 + 统计摘要
SAMPLE_N = 100


def to_rows(objs: Iterable) -> list:
    rows = []
    for o in objs:
        rows.append(asdict(o) if hasattr(o, "__dataclass_fields__") else o)
    return rows


def _dump(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _size(blob: str) -> int:
    return len(blob.encode("utf-8"))


def _slim(row: dict) -> dict:
    """把体积大头（详情里的 actors/photos/drama/comments 等）折成一行摘要。"""
    out = dict(row)
    extra = out.get("extra")
    if isinstance(extra, dict) and extra:
        out["extra"] = {
            "_omitted_keys": {
                k: (len(v) if isinstance(v, (list, dict, str)) else 1)
                for k, v in extra.items()
            }
        }
    return out


def save_json(path: str, records: Iterable, meta: Optional[dict] = None) -> dict:
    """落盘；整包超过 500KB 时自动降级为「前 100 条 + 统计摘要」。

    降级分三档，逐档收紧直到进 500KB：
      ① 全量           → ② 前 100 条 + 统计摘要
      ③ 前 100 条里再把大字段（actors/photos/drama/comments…）折成键名摘要
      ④ 仍超标就继续减条数
    """
    rows = to_rows(records)
    meta = dict(meta or {})
    meta["total_records"] = len(rows)
    payload = {"meta": meta, "records": rows}
    blob = _dump(payload)
    truncated = False
    if _size(blob) > SIZE_CAP:
        truncated = True
        meta["truncated"] = (
            f"完整数据 {len(rows)} 条超过 500KB 上限，此文件只保留前 {SAMPLE_N} 条 + 统计摘要"
        )
        meta["sample_size"] = min(SAMPLE_N, len(rows))
        meta["summary"] = summarize(rows)
        payload = {"meta": meta, "records": rows[:SAMPLE_N]}
        blob = _dump(payload)
        if _size(blob) > SIZE_CAP:
            meta["slimmed"] = "样本记录的 extra 大字段已折成键名+长度摘要"
            payload["records"] = [_slim(r) for r in payload["records"]]
            blob = _dump(payload)
        n = SAMPLE_N
        while _size(blob) > SIZE_CAP and n > 5:
            n = max(5, n // 2)
            meta["sample_size"] = n
            payload["records"] = payload["records"][:n]
            blob = _dump(payload)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(blob)
    return {
        "path": path,
        "records": len(rows),
        "written": len(payload["records"]),
        "bytes": len(blob.encode("utf-8")),
        "truncated": truncated,
    }


def summarize(rows: list) -> dict:
    """给被截断的数据文件配一份统计摘要，保证「截断了也还能看出全貌」。"""
    if not rows:
        return {}
    out: dict = {"n": len(rows)}
    scores = [r.get("score") for r in rows if isinstance(r.get("score"), (int, float))]
    if scores:
        out["score"] = {
            "n": len(scores),
            "min": min(scores),
            "max": max(scores),
            "avg": round(sum(scores) / len(scores), 3),
        }
    for key in ("categories", "regions", "authors"):
        bag: dict = {}
        for r in rows:
            for v in r.get(key) or []:
                bag[v] = bag.get(v, 0) + 1
        if bag:
            out[f"top_{key}"] = dict(
                sorted(bag.items(), key=lambda kv: -kv[1])[:15]
            )
    for key in ("domain", "website"):
        bag = {}
        for r in rows:
            v = r.get(key)
            if v:
                bag[v] = bag.get(v, 0) + 1
        if bag:
            out[f"top_{key}"] = dict(sorted(bag.items(), key=lambda kv: -kv[1])[:15])
    return out


def print_stats(title: str, started: float, session: PoliteSession, **kw) -> None:
    dur = time.time() - started
    parts = [f"{k}={v}" for k, v in kw.items()]
    s = session.stats()
    print(
        f"[{title}] 耗时 {dur:.1f}s · 请求 {s['requests']} 次 · 重试 {s['retries']} 次 · "
        f"下行 {s['bytes_down']/1024:.0f}KB · " + " · ".join(parts)
    )
