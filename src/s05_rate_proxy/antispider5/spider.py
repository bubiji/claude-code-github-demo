"""antispider5 —— 限制单个 IP 访问频率 5 分钟最多 10 次。

issue: #8 · 案例: antispider5 · 来源: https://antispider5.scrape.center

用法：
    python spider.py                 # 全量 11 个列表页（104 部电影）
    python spider.py --details 6     # 额外抓 6 个详情页样本
    python spider.py --plan          # 只算预算不发请求
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common import (  # noqa: E402
    PoliteClient,
    RateLimiter,
    budget,
    parse_movie_cards,
    save_json,
    summarize,
    total_from_pagination,
)

BASE = "https://antispider5.scrape.center"
PER_PAGE = 10
HERE = os.path.dirname(os.path.abspath(__file__))


def probe_gap(cli, movies: list[dict], total: int, limit: int = 6) -> list[dict]:
    """列表页只翻出 100 条，站点却声明 104 条——差的 4 条去哪了？

    翻页在 /page/11 返回 0 张卡片就停了，但 `共 104 条` 是后端渲染的真实计数。
    直接按 id 探 /detail/<id>，看那 4 条记录是否存在：
      · 200 且解析出标题 → 记录存在，只是**列表接口不返回**（前端翻页有上限）
      · 404             → 声明的 104 里包含已删除/不可见的记录

    每探一个 id 花 1 次配额，所以设 limit 上限，不做无边界枚举。
    """
    seen = {m["id"] for m in movies if m["id"]}
    missing = [i for i in range(1, total + 1) if i not in seen][:limit]
    out = []
    for mid in missing:
        r = cli.get(f"{BASE}/detail/{mid}", allow_redirects=False)
        d = {"id": mid, "status": r.status_code}
        if r.status_code == 200:
            d.update(parse_detail(r.text))
        out.append(d)
        print(f"gap probe /detail/{mid} → {r.status_code} {d.get('title')}")
    return out


def parse_detail(html: str) -> dict:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")

    def txt(sel):
        el = soup.select_one(sel)
        return el.get_text(" ", strip=True) if el else None

    return {
        "title": txt("h2.m-b-sm"),
        "drama": txt(".drama p"),
        "score": txt("p.score"),
        "categories": [b.get_text(strip=True) for b in soup.select("button.category span")],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=float, default=35.0,
                    help="最小请求间隔（秒），默认 35（配额 10/300s 的安全值）")
    ap.add_argument("--capacity", type=int, default=9,
                    help="滑动窗口内允许的最大请求数，默认 9（配额 10 留 1 余量）")
    ap.add_argument("--pages", type=int, default=0, help="只跑前 N 页（0=全量）")
    ap.add_argument("--details", type=int, default=0, help="额外抓 N 个详情页样本")
    ap.add_argument("--gap-probe", type=int, default=4,
                    help="翻页数 < 声明总数时，按 id 探查缺口记录的上限个数")
    ap.add_argument("--plan", action="store_true", help="只打印预算，不发请求")
    args = ap.parse_args()

    # ---- 先算账（README 里的预算表就是这么来的）-------------------------
    n_pages_full = 11  # 104 条 / 每页 10 条，向上取整
    plan = {
        "list_only": budget(n_pages_full, min_interval=args.interval),
        "list_plus_all_details": budget(n_pages_full + 104, min_interval=args.interval),
    }
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    if args.plan:
        return 0

    limiter = RateLimiter(capacity=args.capacity, min_interval=args.interval,
                          name="antispider5")
    cli = PoliteClient(limiter=limiter, headers={"Referer": BASE + "/"})

    movies: list[dict] = []
    total = None
    page = 1
    t0 = time.time()
    while True:
        url = f"{BASE}/page/{page}"
        r = cli.get(url)
        if total is None:
            total = total_from_pagination(r.text)
            print(f"站点声明总数：{total}")
        cards = parse_movie_cards(r.text)
        movies.extend(cards)
        print(f"page {page}: +{len(cards)} → {len(movies)}"
              f"{'/' + str(total) if total else ''}")
        if not cards:
            break
        if total and len(movies) >= total:
            break
        if args.pages and page >= args.pages:
            break
        if page >= 60:  # 兜底，防止分页协议变化导致死循环
            break
        page += 1

    gap = []
    if total and len(movies) < total and args.gap_probe:
        gap = probe_gap(cli, movies, total, limit=args.gap_probe)

    details = []
    if args.details:
        for m in movies[: args.details]:
            r = cli.get(BASE + m["detail_url"])
            d = parse_detail(r.text)
            d["id"] = m["id"]
            details.append(d)
            print(f"detail {m['id']}: {d['title']}")

    elapsed = time.time() - t0
    payload = {
        "source": BASE,
        "issue": 8,
        "case": "antispider5",
        "limit_declared": "限制单个 IP 访问频率 5 分钟最多 10 次，如果过多则会封禁 IP 10 分钟。",
        "run": {
            "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "elapsed_s": round(elapsed, 1),
            "elapsed_min": round(elapsed / 60, 1),
            "min_interval_s": args.interval,
            "window_capacity": args.capacity,
            "site_total_declared": total,
            "fetched_list_items": len(movies),
            "list_pages_crawled": page,
            "pagination_exhausted": True,
            "is_full_list_pagination": True,
            "gap_vs_declared": (total - len(movies)) if total else None,
            "detail_samples": len(details),
            "detail_is_sample_only": True,
            "detail_full_would_cost": budget(len(movies), min_interval=args.interval),
        },
        "gap_probe": {
            "why": "列表翻页到 /page/11 返回 0 条即止，站点分页控件却声明「共 104 条」",
            "results": gap,
        },
        "client": cli.report(),
        "request_timeline": cli.events,
        "summary": summarize(movies, numeric=("score",),
                             categorical=("categories", "regions")),
        "detail_samples": details,
        "items": movies,
    }
    info = save_json(os.path.join(HERE, "data", "antispider5_movies.json"), payload)
    print(json.dumps({"saved": info, "client": cli.report()}, ensure_ascii=False,
                     indent=2))
    print(f"\n完成：翻页全量 {len(movies)} 条（站点声明 {total} 条），详情样本 "
          f"{len(details)} 条，缺口探针 {len(gap)} 条；用时 {elapsed/60:.1f} 分钟，"
          f"限流命中 {cli.stats.rate_limited} 次")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
