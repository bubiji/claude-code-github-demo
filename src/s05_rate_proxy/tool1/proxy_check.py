"""tool1 —— 代理池 API：取代理 → 校验可用 → 失败剔除。

issue: #8 · 案例: tool1 · 来源: https://proxypool.scrape.center/random

这个脚本的产出不是「一堆能用的代理」，而是**一个诚实的可用率数字**。
公开免费代理的存活率通常极低，先量出来，才知道阶段 5 的另外三个案例能不能
指望它。

三档校验，一档比一档严：
    1. connect  —— 代理能不能连上（探针 http://httpbin.org/ip）
    2. https    —— 能不能走 CONNECT 隧道（很多 HTTP 代理只支持明文）
    3. target   —— 能不能真的把 antispider5 的页面取回来（最终唯一有意义的一档）

用法：
    python proxy_check.py --n 50            # 取 50 个去重候选，跑三档校验
    python proxy_check.py --n 50 --no-target  # 不打目标站，只测通用可用性
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common import DEFAULT_UA, PROXY_POOL_API, ProxyPool, save_json  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = "https://antispider5.scrape.center/page/1"


def probe(proxy: str, url: str, timeout: float, expect: str = "") -> dict:
    proxies = {"http": f"http://{proxy}", "https": f"http://{proxy}"}
    t0 = time.time()
    rec = {"proxy": proxy, "ok": False, "reason": None, "status": None,
           "latency_s": None}
    try:
        r = requests.get(url, proxies=proxies, timeout=timeout,
                         headers={"User-Agent": DEFAULT_UA})
        rec["status"] = r.status_code
        rec["latency_s"] = round(time.time() - t0, 2)
        if r.status_code != 200:
            rec["reason"] = f"HTTP {r.status_code}"
        elif expect and expect not in r.text:
            # 透明代理/劫持页会返回 200 但内容不对，必须做内容断言
            rec["reason"] = "content-mismatch"
        else:
            rec["ok"] = True
    except requests.RequestException as e:
        rec["reason"] = type(e).__name__
        rec["latency_s"] = round(time.time() - t0, 2)
    return rec


def stage(name: str, proxies: list[str], url: str, timeout: float,
          expect: str = "", workers: int = 20) -> tuple[list[str], list[dict]]:
    if not proxies:
        print(f"[{name}] 无候选，跳过")
        return [], []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        recs = list(ex.map(lambda p: probe(p, url, timeout, expect), proxies))
    alive = [r["proxy"] for r in recs if r["ok"]]
    rate = len(alive) / len(recs) * 100
    print(f"[{name}] {len(alive)}/{len(recs)} 存活（{rate:.1f}%）  url={url}")
    from collections import Counter

    reasons = Counter(r["reason"] for r in recs if not r["ok"])
    for reason, n in reasons.most_common():
        print(f"        失败原因 {reason}: {n}")
    return alive, recs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=50, help="取多少个去重候选代理")
    ap.add_argument("--timeout", type=float, default=8.0)
    ap.add_argument("--no-target", action="store_true",
                    help="不对 antispider5 做目标站校验")
    args = ap.parse_args()

    t0 = time.time()
    pool = ProxyPool(timeout=args.timeout)

    # ---- 1. 取 ---------------------------------------------------------
    cands = pool.fetch(args.n)
    api_calls = pool.stat.fetched
    dup_rate = 1 - (len(cands) / api_calls) if api_calls else 0

    # ---- 2. 校验（三档）-------------------------------------------------
    alive_http, rec_http = stage("connect/http", cands, "http://httpbin.org/ip",
                                 args.timeout)
    alive_https, rec_https = stage("https", alive_http, "https://httpbin.org/ip",
                                   args.timeout)
    if args.no_target:
        alive_target, rec_target = [], []
    else:
        alive_target, rec_target = stage(
            "target/antispider5", alive_https, TARGET, args.timeout + 7,
            expect="el-card item",
        )

    # ---- 3. 剔除演示：把 target 档没过的从池里删掉 ------------------------
    pool.alive = list(alive_https)
    pool.stat.alive = len(alive_https)
    pool.stat.checked = len(cands)
    for r in rec_target:
        if not r["ok"]:
            pool.drop(r["proxy"], r["reason"] or "target-failed")

    elapsed = time.time() - t0

    def rate(a, b):
        return round(len(a) / len(b), 4) if b else 0.0

    result = {
        "source": PROXY_POOL_API,
        "issue": 8,
        "case": "tool1",
        "description": (
            "代理池 API 网站，访问即可获取随机可用公开代理，源代码来自 "
            "https://github.com/Python3WebSpider/ProxyPool"
        ),
        "run": {
            "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "elapsed_s": round(elapsed, 1),
            "timeout_s": args.timeout,
            "api_calls": api_calls,
            "unique_candidates": len(cands),
            "duplicate_rate": round(dup_rate, 4),
        },
        "funnel": {
            "fetched_unique": len(cands),
            "alive_http": len(alive_http),
            "alive_https": len(alive_https),
            "alive_target_antispider5": len(alive_target),
            "rate_http": rate(alive_http, cands),
            "rate_https": rate(alive_https, cands),
            "rate_target": rate(alive_target, cands),
        },
        "dropped_after_target_check": pool.stat.dropped,
        "surviving_proxies": alive_target,
        "pool_state": pool.report(),
        "items": rec_http + rec_https + rec_target,
    }
    info = save_json(os.path.join(HERE, "data", "proxy_report.json"), result)
    print("\n" + json.dumps(result["funnel"], ensure_ascii=False, indent=2))
    print(json.dumps({"saved": info}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
