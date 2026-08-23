#!/usr/bin/env python3
"""spa5（图书网站 · Ajax 加载 · 有翻页 · 大批量）。

issue: #5 · 案例: spa5 · 来源: https://spa5.scrape.center

三个模式：
  api      —— 走 /api/book/?limit&offset 抓列表。默认 limit=100（前端是 18），
              9040 条书目 91 个请求抓完，完全不依赖浏览器。
  detail   —— 对抽样书目补抓 /api/book/{id}/（含 tags/price/comments 等）。
  render   —— 「渲染模式」回放：用站点自己的 Vue render 函数（js/chunk-f52d396c.js
              里的 index 组件）把接口记录还原成它在浏览器里会生成的 DOM，再走
              Book.from_dom() 解析，和接口模式的产出逐字段比对。
              注意：这是**本地重放渲染**，不是抓来的页面 HTML——本阶段要求不依赖
              浏览器，此模式用来验证 DOM 适配器与接口适配器落到同一个 build()。

用法：
    python spider.py                          # 全量列表（limit=100）
    python spider.py --limit 18               # 复刻前端每页 18 条的翻页
    python spider.py --max-items 360          # 只抓前 360 条
    python spider.py --mode detail --sample 20
    python spider.py --mode render --max-items 180
"""

from __future__ import annotations

import argparse
import html
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common import (  # noqa: E402
    Book,
    PoliteSession,
    dom_cards,
    offset_pages,
    print_stats,
    save_json,
)

API = "https://spa5.scrape.center/api/book/"
DETAIL = "https://spa5.scrape.center/api/book/{id}/"
FRONTEND_LIMIT = 18  # 前端源码 data(){ ... limit: 18 ... }


def crawl_api(session: PoliteSession, limit: int, max_items=None) -> list:
    books, count = [], None
    for page in offset_pages(session, API, limit=limit, max_items=max_items):
        count = page.count
        books += [Book.from_api(o, source="spa5-api") for o in page.results]
        if page.offset % (limit * 10) == 0 or (count and page.offset + limit >= count):
            print(f"  offset={page.offset:<6} 累计 {len(books):>5}/{count}")
    return books


def fetch_details(session: PoliteSession, books: list, sample: int) -> list:
    picked = random.sample(books, min(sample, len(books)))
    out = []
    for i, b in enumerate(picked, 1):
        obj = session.get_json(DETAIL.format(id=b.id))
        out.append(Book.from_api(obj, source="spa5-api-detail"))
        if i % 5 == 0 or i == len(picked):
            print(f"  详情 {i}/{len(picked)}")
    return out


# --- 渲染模式回放：照抄站点 index 组件的 render 函数结构 --------------------
CARD_TPL = """
<div class="el-col el-col-4">
  <div class="el-card item m-b is-hover-shadow">
    <div class="el-card__body">
      <div class="el-row top"><div class="el-col el-col-24">
        <a href="/detail/{id}"><img src="{cover}" class="cover"></a>
      </div></div>
      <div class="el-row bottom p-t-none"><div class="el-col el-col-24">
        <a href="/detail/{id}"><h3 class="m-t-sm m-b-xs name">{name}</h3></a>
        {authors_html}
      </div></div>
    </div>
  </div>
</div>"""


def replay_render(books: list) -> str:
    """把接口记录喂进站点自己的模板，得到浏览器里那份 DOM 的等价物。"""
    cards = []
    for b in books:
        authors_html = (
            f'<p class="authors">{html.escape(",".join(b.authors))}</p>'
            if b.authors else ""
        )
        cards.append(
            CARD_TPL.format(
                id=html.escape(b.id or ""),
                cover=html.escape(b.cover),
                name=html.escape(b.name),
                authors_html=authors_html,
            )
        )
    return (
        '<div id="index"><div class="el-row"><div class="el-col el-col-18">'
        '<div class="el-row">' + "".join(cards) + "</div></div></div></div>"
    )


def compare(api_books: list, dom_books: list) -> dict:
    by_id = {b.id: b for b in api_books}
    fields = ("id", "name", "authors", "cover")
    same, diff = 0, []
    for d in dom_books:
        a = by_id.get(d.id)
        if not a:
            diff.append({"id": d.id, "reason": "接口侧没有这个 id"})
            continue
        bad = [f for f in fields if getattr(a, f) != getattr(d, f)]
        if bad:
            diff.append({"id": d.id, "fields": bad,
                         "api": {f: getattr(a, f) for f in bad},
                         "dom": {f: getattr(d, f) for f in bad}})
        else:
            same += 1
    return {"api_total": len(api_books), "dom_total": len(dom_books),
            "identical": same, "diff": len(diff), "diff_detail": diff[:10]}


def main() -> None:
    ap = argparse.ArgumentParser(description="spa5 图书大批量抓取")
    ap.add_argument("--mode", choices=["api", "detail", "render"], default="api")
    ap.add_argument("--limit", type=int, default=100,
                    help=f"每页条数（前端 {FRONTEND_LIMIT}，接口实测支持 100）")
    ap.add_argument("--max-items", type=int, default=None)
    ap.add_argument("--sample", type=int, default=20, help="detail 模式抽样条数")
    ap.add_argument("--delay", type=float, default=0.35)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "data"))
    args = ap.parse_args()

    started = time.time()
    session = PoliteSession(delay=args.delay)
    print(f"接口模式：GET /api/book/?limit={args.limit}&offset=N")
    books = crawl_api(session, args.limit, args.max_items)
    info = save_json(
        os.path.join(args.out, "spa5_books.json"), books,
        meta={"case": "spa5", "issue": 5, "mode": "api", "api": API,
              "limit": args.limit, "frontend_limit": FRONTEND_LIMIT,
              "requests": session.stats()["requests"]},
    )
    print(f"  -> {info}")

    if args.mode == "detail":
        details = fetch_details(session, books, args.sample)
        info = save_json(
            os.path.join(args.out, "spa5_book_details_sample.json"), details,
            meta={"case": "spa5", "issue": 5, "mode": "detail",
                  "sampled_from": len(books), "sample": len(details)},
        )
        print(f"  -> {info}")

    if args.mode == "render":
        page_html = replay_render(books)
        cards = dom_cards(page_html)
        dom_books = [Book.from_dom(c, source="spa5-dom-replay") for c in cards]
        rep = compare(books, dom_books)
        save_json(
            os.path.join(args.out, "spa5_mode_compare.json"), [rep],
            meta={"case": "spa5", "issue": 5, "mode": "render",
                  "note": "DOM 由站点自身 render 函数本地重放生成，非抓取所得页面"},
        )
        print("  比对:", {k: v for k, v in rep.items() if k != "diff_detail"})
        for d in rep["diff_detail"]:
            print("   差异:", d)

    print_stats("spa5", started, session, mode=args.mode, records=len(books))


if __name__ == "__main__":
    main()
