#!/usr/bin/env python3
"""spa3（电影数据网站 · Ajax 加载 · 无页码翻页，下拉至底部刷新）。

issue: #5 · 案例: spa3 · 来源: https://spa3.scrape.center

「无限下拉」在 HTTP 层没有任何新东西：还是 limit/offset。本脚本做三件事：
  1. scroll 模式：逐次模拟「下拉到底触发一次加载」，把每一跳的偏移量、返回条数、
     是否还有下一跳记成轨迹文件（data/spa3_scroll_trace.json）。
  2. 复刻前端的停止条件（page === 10 就禁用下拉），量出「浏览器里下拉到死也
     看不到的那几条」。
  3. bulk 模式：同一个分页器换个 limit，一次 100 条把全量抓完。

用法：
    python spider.py                 # scroll 模式（limit=10，模拟下拉）
    python spider.py --mode bulk     # bulk 模式（limit=100）
    python spider.py --emulate-frontend   # 额外报告前端 page<=10 的截断
"""

from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common import Movie, PoliteSession, offset_pages, print_stats, save_json  # noqa: E402

API = "https://spa3.scrape.center/api/movie/"
# 前端源码（js/chunk-d5d475e6.4ddc209f.js）里的两个常量：
FRONTEND_LIMIT = 10          # data(){ ... limit: 10 ... }
FRONTEND_MAX_PAGE = 10       # computed: { disabled(){ return this.page === 10 } }


def crawl(session: PoliteSession, limit: int, max_items=None) -> tuple:
    movies, trace = [], []
    step = 0
    for page in offset_pages(session, API, limit=limit, max_items=max_items):
        step += 1
        movies += [Movie.from_api(o, source="spa3-api") for o in page.results]
        remaining = (page.count - (page.offset + len(page.results))) if page.count else None
        trace.append({
            "step": step,
            "trigger": "首屏 mounted()" if step == 1 else f"第 {step-1} 次下拉到底 → onLoadMore()",
            "frontend_page": step,
            "request": f"GET /api/movie/?limit={limit}&offset={page.offset}",
            "offset_sent": page.offset,
            "got": len(page.results),
            "cumulative": len(movies),
            "count_declared": page.count,
            "remaining_after": remaining,
            "has_more": bool(remaining),
        })
        print(
            f"  step={step:<3} offset={page.offset:<4} 本次 {len(page.results):>3} 条 "
            f"累计 {len(movies):>3}/{page.count} 剩余 {remaining}"
        )
    return movies, trace


def main() -> None:
    ap = argparse.ArgumentParser(description="spa3 无限下拉抓取")
    ap.add_argument("--mode", choices=["scroll", "bulk"], default="scroll")
    ap.add_argument("--limit", type=int, default=None, help="覆盖每页条数")
    ap.add_argument("--delay", type=float, default=0.35)
    ap.add_argument("--max-items", type=int, default=None)
    ap.add_argument("--emulate-frontend", action="store_true",
                    help="报告前端 page<=10 硬上限造成的截断")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "data"))
    args = ap.parse_args()

    limit = args.limit or (FRONTEND_LIMIT if args.mode == "scroll" else 100)
    started = time.time()
    session = PoliteSession(delay=args.delay)

    print(f"{args.mode} 模式：GET /api/movie/?limit={limit}&offset=N（offset 每次 += 返回条数）")
    movies, trace = crawl(session, limit, args.max_items)

    total = trace[-1]["count_declared"] if trace else None
    frontend_reachable = min(FRONTEND_LIMIT * FRONTEND_MAX_PAGE, total or 0)
    report = {
        "case": "spa3", "issue": 5, "mode": args.mode,
        "api": API, "limit": limit,
        "count_declared": total,
        "records_fetched": len(movies),
        "requests": session.stats()["requests"],
        "frontend_limit": FRONTEND_LIMIT,
        "frontend_max_page": FRONTEND_MAX_PAGE,
        "frontend_reachable": frontend_reachable,
        "unreachable_in_browser": (total or 0) - frontend_reachable,
    }
    info = save_json(os.path.join(args.out, "spa3_movies.json"), movies, meta=report)
    save_json(os.path.join(args.out, "spa3_scroll_trace.json"), trace,
              meta={k: report[k] for k in ("case", "issue", "mode", "api", "limit",
                                           "count_declared", "records_fetched")})
    print(f"  -> {info}")

    if args.emulate_frontend or args.mode == "scroll":
        miss = [m.name for m in movies[frontend_reachable:]]
        print(f"  前端 disabled(page==={FRONTEND_MAX_PAGE}) 截断："
              f"浏览器最多下拉出 {frontend_reachable} 条，接口声明 {total} 条，"
              f"够不着的 {len(miss)} 条 → {miss}")

    print_stats("spa3", started, session, mode=args.mode, records=len(movies))


if __name__ == "__main__":
    main()
