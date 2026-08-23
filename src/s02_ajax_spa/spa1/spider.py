#!/usr/bin/env python3
"""spa1（电影数据网站 · Ajax 加载 · 有页码翻页）—— 接口模式 + 渲染模式。

issue: #5 · 案例: spa1 · 来源: https://spa1.scrape.center

用法：
    python spider.py                      # 接口模式，抓全量列表（默认带详情）
    python spider.py --no-detail          # 只抓列表
    python spider.py --mode render        # 渲染模式：解析服务端渲染孪生站的 DOM
    python spider.py --mode compare       # 两种模式各跑一遍并逐字段比对
"""

from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common import (  # noqa: E402
    Movie,
    PoliteSession,
    dom_cards,
    offset_pages,
    print_stats,
    save_json,
    to_rows,
)

API = "https://spa1.scrape.center/api/movie/"
DETAIL = "https://spa1.scrape.center/api/movie/{id}/"
# 渲染模式的 DOM 来源：ssr1 是同一份电影数据的服务端渲染版本，
# 页面模板与 spa1 的 Vue 组件同源（同样的 el-card 卡片结构），
# 因此可以在「不启动浏览器」的前提下真实地跑通 Movie.from_dom() 这条路径。
SSR_PAGE = "https://ssr1.scrape.center/page/{page}"


def crawl_api(session: PoliteSession, limit: int, with_detail: bool) -> list:
    movies, count = [], None
    for page in offset_pages(session, API, limit=limit):
        count = page.count
        for obj in page.results:
            movies.append(Movie.from_api(obj, source="spa1-api"))
        print(
            f"  offset={page.offset:<4} limit={limit:<3} 本页 {len(page.results):>3} 条 "
            f"累计 {len(movies):>3}/{count}"
        )
    if with_detail:
        for i, m in enumerate(movies, 1):
            obj = session.get_json(DETAIL.format(id=m.id))
            full = Movie.from_api(obj, source="spa1-api-detail")
            full.extra.setdefault("drama", obj.get("drama"))
            movies[i - 1] = full
            if i % 20 == 0 or i == len(movies):
                print(f"  详情 {i}/{len(movies)}")
    return movies


def crawl_render(session: PoliteSession, pages: int = 10) -> list:
    movies = []
    for p in range(1, pages + 1):
        html = session.get_text(SSR_PAGE.format(page=p))
        cards = dom_cards(html)
        movies += [Movie.from_dom(c, source="ssr1-dom") for c in cards]
        print(f"  page={p:<3} 卡片 {len(cards):>3} 条 累计 {len(movies):>3}")
    return movies


def compare(api_movies: list, dom_movies: list) -> dict:
    """逐字段比对两种模式的产出，证明「同一份 build() 清洗出来的东西是一致的」。"""
    by_name = {m.name: m for m in api_movies}
    fields = ("name", "alias", "categories", "regions", "score", "published_at", "minute")
    same, diff, missing = 0, [], []
    for d in dom_movies:
        a = by_name.get(d.name)
        if not a:
            missing.append(d.name)
            continue
        bad = [f for f in fields if getattr(a, f) != getattr(d, f)]
        if bad:
            diff.append({"name": d.name, "fields": bad,
                         "api": {f: getattr(a, f) for f in bad},
                         "dom": {f: getattr(d, f) for f in bad}})
        else:
            same += 1
    return {
        "api_total": len(api_movies),
        "dom_total": len(dom_movies),
        "matched_identical": same,
        "matched_with_diff": len(diff),
        "dom_only": missing,
        "diff_detail": diff[:10],
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="spa1 电影数据抓取")
    ap.add_argument("--mode", choices=["api", "render", "compare"], default="api")
    ap.add_argument("--limit", type=int, default=10, help="接口分页每页条数（前端用 10）")
    ap.add_argument("--delay", type=float, default=0.35, help="请求间隔秒")
    ap.add_argument("--no-detail", action="store_true", help="接口模式跳过详情页")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "data"))
    args = ap.parse_args()

    started = time.time()
    session = PoliteSession(delay=args.delay)
    out = args.out

    if args.mode in ("api", "compare"):
        print("接口模式：GET /api/movie/?limit&offset")
        api_movies = crawl_api(session, args.limit, not args.no_detail)
        info = save_json(
            os.path.join(out, "spa1_movies_api.json"),
            api_movies,
            meta={"case": "spa1", "issue": 5, "mode": "api", "api": API,
                  "limit": args.limit, "with_detail": not args.no_detail},
        )
        print(f"  -> {info}")

    if args.mode in ("render", "compare"):
        print("渲染模式：解析 ssr1（同数据源的服务端渲染孪生站）DOM")
        dom_movies = crawl_render(session)
        info = save_json(
            os.path.join(out, "spa1_movies_render.json"),
            dom_movies,
            meta={"case": "spa1", "issue": 5, "mode": "render", "dom_source": SSR_PAGE},
        )
        print(f"  -> {info}")

    if args.mode == "compare":
        rep = compare(api_movies, dom_movies)
        save_json(
            os.path.join(out, "spa1_mode_compare.json"),
            [rep],
            meta={"case": "spa1", "issue": 5, "mode": "compare"},
        )
        print("  比对:", {k: v for k, v in rep.items() if k != "diff_detail"})
        for d in rep["diff_detail"]:
            print("   差异:", d)

    print_stats("spa1", started, session, mode=args.mode)


if __name__ == "__main__":
    main()
