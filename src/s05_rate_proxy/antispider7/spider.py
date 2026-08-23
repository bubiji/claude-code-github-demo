"""antispider7 —— IP 与账号双重频率限制。

issue: #8 · 案例: antispider7 · 来源: https://antispider7.scrape.center

本案例最重要的一条经验：**配额是按「请求次数」计的，不是按「字节数」计的。**
所以在被限流的站点上，降低请求条数比提高请求速度有效得多。

    前端每页 limit=18   → 9040 条要 503 个请求 → 配额下约 4.9 小时
    实测该接口没有设置 DRF 的 max_limit
    改成 limit=2000     → 9040 条只要 5 个请求 → 配额下约 2.3 分钟

同一份全量数据，请求数降到 1/100，全程一次限流都不会碰到。

用法：
    python spider.py                 # 全量 9040 本（limit=2000，5 个请求）
    python spider.py --limit 18      # 复刻前端翻页（会非常慢，仅供对照）
    python spider.py --plan          # 只算预算不发请求
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common import (  # noqa: E402
    PoliteClient,
    RateLimiter,
    budget,
    redact,
    save_json,
    summarize,
)

BASE = "https://antispider7.scrape.center"
API = BASE + "/api/book/"
LOGIN = BASE + "/api/login"
FRONTEND_LIMIT = 18
HERE = os.path.dirname(os.path.abspath(__file__))

# 练习站公开凭据（scrape.center 案例站，非真实账号）
USERNAME = "admin"
PASSWORD = "admin"


def login(cli: PoliteClient) -> str:
    """POST /api/login -> {"token": "<JWT>"}；后续请求带 Authorization: jwt <token>。

    注意登录本身也走 limiter —— 它同样是一次请求，同样计入配额。
    """
    cli.limiter.acquire(on_wait=lambda w: cli.log(f"控速等待 {w:.1f}s → login"))
    r = cli.session.post(
        LOGIN, json={"username": USERNAME, "password": PASSWORD}, timeout=cli.timeout
    )
    cli.stats.requests += 1
    r.raise_for_status()
    token = r.json()["token"]
    cli.log(f"登录成功，token={redact(token)}")
    return token


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=float, default=35.0)
    ap.add_argument("--capacity", type=int, default=9)
    ap.add_argument("--limit", type=int, default=2000,
                    help="每次请求取多少条（前端是 18；接口未设 max_limit）")
    ap.add_argument("--max-items", type=int, default=0, help="只取前 N 条（0=全量）")
    ap.add_argument("--plan", action="store_true")
    args = ap.parse_args()

    total_known = 9040
    plan = {
        "frontend_limit_18": budget(
            1 + math.ceil(total_known / FRONTEND_LIMIT), min_interval=args.interval
        ),
        f"limit_{args.limit}": budget(
            1 + math.ceil(total_known / args.limit), min_interval=args.interval
        ),
    }
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    if args.plan:
        return 0

    limiter = RateLimiter(capacity=args.capacity, min_interval=args.interval,
                          name="antispider7")
    cli = PoliteClient(limiter=limiter, headers={"Referer": BASE + "/"})

    t0 = time.time()
    token = login(cli)
    cli.session.headers["Authorization"] = f"jwt {token}"

    books: list[dict] = []
    count = None
    offset = 0
    while True:
        payload = cli.get_json(API, params={"limit": args.limit, "offset": offset})
        count = payload.get("count")
        results = payload.get("results") or []
        books.extend(results)
        print(f"offset={offset} +{len(results)} → {len(books)}/{count}")
        if not results:
            break
        offset += args.limit
        if count and len(books) >= count:
            break
        if args.max_items and len(books) >= args.max_items:
            break

    elapsed = time.time() - t0
    payload = {
        "source": BASE,
        "issue": 8,
        "case": "antispider7",
        "limit_declared": (
            "限制单个 IP 访问频率 5 分钟最多 10 次，同时限制单个账号访问频率 "
            "5 分钟最多 10 次，如果过多则会封禁 IP 或账号 10 分钟。"
        ),
        "auth": {
            "endpoint": LOGIN,
            "scheme": "JWT (Authorization: jwt <token>)",
            "username": USERNAME,
            "token": redact(token),
        },
        "run": {
            "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "elapsed_s": round(elapsed, 1),
            "elapsed_min": round(elapsed / 60, 1),
            "page_limit": args.limit,
            "frontend_limit": FRONTEND_LIMIT,
            "min_interval_s": args.interval,
            "site_total": count,
            "fetched": len(books),
            "is_full_dataset": bool(count and len(books) >= count),
        },
        "client": cli.report(),
        "request_timeline": cli.events,
        # 摘要对**全量 9040 条**计算，落盘截断只影响 items，不影响这里
        "summary": summarize(books, numeric=("score",), categorical=("authors",)),
        "items": books,
    }
    info = save_json(os.path.join(HERE, "data", "antispider7_books.json"), payload)
    print(json.dumps({"saved": info, "client": cli.report()}, ensure_ascii=False,
                     indent=2))
    print(f"\n完成：{len(books)}/{count} 条，用时 {elapsed/60:.1f} 分钟，"
          f"限流命中 {cli.stats.rate_limited} 次")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
