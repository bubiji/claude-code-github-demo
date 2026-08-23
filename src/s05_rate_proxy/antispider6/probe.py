"""antispider6 —— 受控限流探测：用一次性账号量出真实阈值与恢复时长。

issue: #8 · 案例: antispider6 · 来源: https://antispider6.scrape.center

为什么这个探测**不算「把自己撞封」**
------------------------------------
antispider6 的配额挂在**账号**上（案例原文：「限制单个账号访问频率 5 分钟最多
10 次，如果过多则会暂停访问 10 分钟。」）。该站 `/register` 是开放注册的，于是：

    · 探测全程使用一个**一次性注册的账号**，正式抓取用的 admin 账号不参与；
    · 被暂停的是那个一次性账号，10 分钟后它自己恢复，我们也不再用它；
    · 探测在 spider.py 的全量抓取**跑完之后**才执行，不占正式抓取的配额。

也就是说，代价被限定在一个用完即弃的账号上，而不是我们赖以工作的身份。
这就是「受控」的含义：**先设计好谁来承担代价，再去触发它。**

探测同时留了两道闸：
    · `--max` 上限（默认 14 次）——即使一直不被拦也会停，不无限打；
    · 一旦拿到第一个非 200 立刻停手，不在封禁期里反复撞（撞了会续期）。

用法：
    python probe.py                  # 完整探测（含恢复计时，最长等 15 分钟）
    python probe.py --no-recovery    # 只测阈值，不等恢复
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import string
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common import DEFAULT_UA, redact, save_json  # noqa: E402

BASE = "https://antispider6.scrape.center"
HERE = os.path.dirname(os.path.abspath(__file__))


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def new_account() -> tuple[str, str]:
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return f"probe_{suffix}", "Probe" + "".join(random.choices(string.digits, k=6))


def classify(r: requests.Response) -> str:
    if r.status_code != 200:
        return f"HTTP {r.status_code}"
    if "el-card item" in r.text:
        return "ok"
    if re.search(r"(频率|暂停|封禁|forbidden|限制)", r.text, re.I):
        return "blocked-body"
    if "登录" in r.text or "/login" in r.url:
        return "logged-out"
    return "unknown-body"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gap", type=float, default=3.0,
                    help="探测请求间隔（秒）；小间隔是为了在一个 5 分钟窗口里打满")
    ap.add_argument("--max", type=int, default=14,
                    help="最多发多少次（安全闸，即使不被拦也停）")
    ap.add_argument("--no-recovery", action="store_true")
    ap.add_argument("--recovery-poll", type=float, default=30.0)
    ap.add_argument("--recovery-max", type=float, default=900.0)
    args = ap.parse_args()

    user, pwd = new_account()
    s = requests.Session()
    s.headers.update({"User-Agent": DEFAULT_UA, "Referer": BASE + "/"})

    log(f"一次性账号：{user}")
    r = s.get(BASE + "/register", timeout=25)
    log(f"GET /register → {r.status_code}")
    fields = re.findall(r'name="([^"]+)"', r.text)
    log(f"表单字段：{fields}")

    # 按表单**实际存在的**字段填，不照自己的想象填。
    # 实测该表单是 Django 自带的 UserCreationForm：
    #   ['viewport', 'username', 'email', 'password1', 'password2']
    # （viewport 是 <meta name="viewport">，不是表单域，跳过）
    data = {}
    for f in fields:
        if f == "viewport":
            continue
        if f.startswith("password"):
            data[f] = pwd
        elif f == "username":
            data[f] = user
        elif f == "email":
            data[f] = f"{user}@example.com"
        elif f == "csrfmiddlewaretoken":
            data[f] = s.cookies.get("csrftoken", "")
    log(f"提交注册字段：{sorted(data)}")
    r = s.post(BASE + "/register", data=data, timeout=25, allow_redirects=False)
    log(f"POST /register → {r.status_code} {r.headers.get('Location')}")
    if r.status_code >= 500:
        log(f"注册接口服务端错误（{r.status_code}），响应前 200 字节：{r.text[:200]!r}")

    s2 = requests.Session()
    s2.headers.update({"User-Agent": DEFAULT_UA, "Referer": BASE + "/"})
    r = s2.post(BASE + "/login", data={"username": user, "password": pwd},
                timeout=25, allow_redirects=False)
    sid = s2.cookies.get("sessionid")
    log(f"POST /login → {r.status_code} sessionid={redact(sid)}")
    if not sid:
        log("一次性账号登录失败，放弃探测（不改用 admin 账号——那会牺牲正式身份）")
        return 2

    # ---- 阶梯探测 -------------------------------------------------------
    timeline = []
    blocked_at = None
    t_start = time.time()
    for i in range(1, args.max + 1):
        t0 = time.time()
        r = s2.get(f"{BASE}/page/1", timeout=25)
        verdict = classify(r)
        rec = {
            "n": i,
            "t_since_start_s": round(t0 - t_start, 1),
            "status": r.status_code,
            "verdict": verdict,
            "bytes": len(r.content),
            "elapsed_s": round(r.elapsed.total_seconds(), 3),
            "retry_after": r.headers.get("Retry-After"),
        }
        timeline.append(rec)
        log(f"#{i:>2} t+{rec['t_since_start_s']:>5.1f}s  HTTP {r.status_code}  "
            f"{verdict}  {len(r.content)}B")
        if verdict != "ok":
            blocked_at = i
            log(f"→ 第 {i} 次被拦，立即停手（不在封禁期内反复撞）")
            break
        time.sleep(args.gap)

    # ---- 恢复计时 -------------------------------------------------------
    recovery = None
    if blocked_at and not args.no_recovery:
        t_blocked = time.time()
        log(f"开始恢复计时，每 {args.recovery_poll:.0f}s 探一次，最长 "
            f"{args.recovery_max/60:.0f} 分钟")
        while time.time() - t_blocked < args.recovery_max:
            time.sleep(args.recovery_poll)
            r = s2.get(f"{BASE}/page/1", timeout=25)
            v = classify(r)
            waited = round(time.time() - t_blocked, 1)
            log(f"  恢复探针 t+{waited:.0f}s → HTTP {r.status_code} {v}")
            if v == "ok":
                recovery = waited
                break
        log(f"恢复用时：{recovery}s" if recovery else "超时仍未恢复")

    payload = {
        "source": BASE,
        "issue": 8,
        "case": "antispider6",
        "probe": "受控限流探测（一次性账号，正式 admin 账号不参与）",
        "limit_declared": "限制单个账号访问频率 5 分钟最多 10 次，如果过多则会暂停访问 10 分钟。",
        "account": {"username": user, "disposable": True},
        "params": {"gap_s": args.gap, "max_requests": args.max},
        "measured": {
            "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "blocked_at_request": blocked_at,
            "requests_before_block": (blocked_at - 1) if blocked_at else None,
            "window_span_s": timeline[-1]["t_since_start_s"] if timeline else None,
            "recovery_s": recovery,
            "recovery_min": round(recovery / 60, 1) if recovery else None,
        },
        "items": timeline,
    }
    info = save_json(os.path.join(HERE, "data", "rate_limit_probe.json"), payload)
    print(json.dumps(payload["measured"], ensure_ascii=False, indent=2))
    print(json.dumps({"saved": info}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
