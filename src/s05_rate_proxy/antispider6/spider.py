"""antispider6 —— 限制单个账号访问频率 5 分钟最多 10 次。

issue: #8 · 案例: antispider6 · 来源: https://antispider6.scrape.center

与 antispider5 的差别只有一处：**配额挂在账号上，不挂在 IP 上。**
带来的直接后果是——

    · 换 IP（代理池）对这个站**没有任何用**，配额跟着 sessionid 走；
    · 但换账号有用，而 /register 是开放注册的（见 probe.py）；
    · 登录本身也是一次请求，也计入配额，所以要省着用：
      登录用 allow_redirects=False，只花 1 次请求拿 sessionid，
      不让 requests 自动跟随 302 白白多花一次。

用法：
    python spider.py                 # 登录 + 全量 11 个列表页（104 部电影）
    python spider.py --plan
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
    redact,
    save_json,
    summarize,
    total_from_pagination,
)

BASE = "https://antispider6.scrape.center"
LOGIN = BASE + "/login"
HERE = os.path.dirname(os.path.abspath(__file__))

# 练习站公开凭据（scrape.center 案例站，非真实账号）
USERNAME = "admin"
PASSWORD = "admin"


def login(cli: PoliteClient) -> str:
    """表单登录，返回 sessionid（落盘前会脱敏）。

    这个站的登录表单没有 csrfmiddlewaretoken（实测），直接 POST
    username/password 即可；成功是 302 → `/`，sessionid 在 302 的
    Set-Cookie 里就已经下发，不必跟随重定向。
    """
    cli.limiter.acquire(on_wait=lambda w: cli.log(f"控速等待 {w:.1f}s → login"))
    r = cli.session.post(
        LOGIN,
        data={"username": USERNAME, "password": PASSWORD},
        timeout=cli.timeout,
        allow_redirects=False,
    )
    cli.stats.requests += 1
    sid = cli.session.cookies.get("sessionid")
    cli.log(f"POST /login → {r.status_code} {r.headers.get('Location')} "
            f"sessionid={redact(sid)}")
    if not sid:
        raise RuntimeError(f"登录失败：HTTP {r.status_code}，未拿到 sessionid")
    return sid


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=float, default=35.0)
    ap.add_argument("--capacity", type=int, default=9)
    ap.add_argument("--pages", type=int, default=0)
    ap.add_argument("--plan", action="store_true")
    args = ap.parse_args()

    plan = {"login_plus_11_pages": budget(12, min_interval=args.interval)}
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    if args.plan:
        return 0

    limiter = RateLimiter(capacity=args.capacity, min_interval=args.interval,
                          name="antispider6")
    cli = PoliteClient(limiter=limiter, headers={"Referer": BASE + "/"})

    t0 = time.time()
    sid = login(cli)

    movies: list[dict] = []
    total = None
    page = 1
    while True:
        r = cli.get(f"{BASE}/page/{page}")
        if "登录" in r.text and "el-card item" not in r.text:
            raise RuntimeError("会话失效：拿到的是登录页而不是列表页")
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
        if page >= 60:
            break
        page += 1

    elapsed = time.time() - t0
    payload = {
        "source": BASE,
        "issue": 8,
        "case": "antispider6",
        "limit_declared": "限制单个账号访问频率 5 分钟最多 10 次，如果过多则会暂停访问 10 分钟。",
        "auth": {
            "endpoint": LOGIN,
            "scheme": "Django session cookie",
            "username": USERNAME,
            "sessionid": redact(sid),
        },
        "run": {
            "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "elapsed_s": round(elapsed, 1),
            "elapsed_min": round(elapsed / 60, 1),
            "min_interval_s": args.interval,
            "site_total_declared": total,
            "fetched": len(movies),
            "list_pages_crawled": page,
            "pagination_exhausted": True,
            "is_full_list_pagination": True,
            # antispider5 上观察到同样的 100 vs 104 缺口，缺口成因的探针做在
            # antispider5/spider.py（--gap-probe），此处不重复消耗账号配额
            "gap_vs_declared": (total - len(movies)) if total else None,
        },
        "client": cli.report(),
        "request_timeline": cli.events,
        "summary": summarize(movies, numeric=("score",),
                             categorical=("categories", "regions")),
        "items": movies,
    }
    info = save_json(os.path.join(HERE, "data", "antispider6_movies.json"), payload)
    print(json.dumps({"saved": info, "client": cli.report()}, ensure_ascii=False,
                     indent=2))
    print(f"\n完成：翻页全量 {len(movies)} 条（站点声明 {total} 条），用时 "
          f"{elapsed/60:.1f} 分钟，限流命中 {cli.stats.rate_limited} 次")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
