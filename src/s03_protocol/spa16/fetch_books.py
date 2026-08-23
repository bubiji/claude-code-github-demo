"""spa16 —— 用支持 HTTP/2 的客户端抓图书列表。

issue: #6 · 案例: spa16 · 来源: https://spa16.scrape.center

要点：站点支持 h2 ≠ 客户端会用 h2。httpx 默认只跑 HTTP/1.1，
必须 `httpx.Client(http2=True)`（依赖 `httpx[http2]` 带的 h2 包）才会在 TLS
握手时用 ALPN 协商出 h2。所以每条响应都把 `response.http_version` 记下来，
作为「确实走了 h2」的证据，而不是嘴上说说。

用法：
    python fetch_books.py                 # 默认 h2 抓 5 页（90 本）
    python fetch_books.py --pages 10 --http1
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

BASE = "https://spa16.scrape.center"
LIST_API = f"{BASE}/api/book/"
DETAIL_API = f"{BASE}/api/book/{{book_id}}/"
LIMIT = 18

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
EVIDENCE = HERE / "evidence"


def fetch(pages: int, http2: bool, delay: float, detail_for: int) -> dict:
    started = datetime.now(timezone.utc)
    protocols: list[str] = []
    books: list[dict] = []
    total = None

    with httpx.Client(http2=http2, timeout=20.0, headers={"User-Agent": "scrape-center-practice/1.0 (+issue #6)"}) as client:
        t0 = time.perf_counter()
        for page in range(pages):
            offset = page * LIMIT
            r = client.get(LIST_API, params={"limit": LIMIT, "offset": offset})
            r.raise_for_status()
            protocols.append(r.http_version)
            payload = r.json()
            total = payload["count"]
            books.extend(payload["results"])
            print(f"  page {page + 1}/{pages} offset={offset:<4} "
                  f"{len(payload['results'])} 本  [{r.http_version}]")
            time.sleep(delay)  # 礼貌抓取

        details = []
        for book in books[:detail_for]:
            r = client.get(DETAIL_API.format(book_id=book["id"]))
            r.raise_for_status()
            protocols.append(r.http_version)
            d = r.json()
            details.append(
                {
                    "id": d.get("id"),
                    "name": d.get("name"),
                    "authors": d.get("authors"),
                    "isbn": d.get("isbn"),
                    "score": d.get("score"),
                    "published_at": d.get("published_at"),
                    "http_version": r.http_version,
                }
            )
            print(f"  detail {d.get('name')}  [{r.http_version}]")
            time.sleep(delay)
        elapsed = time.perf_counter() - t0

    return {
        "case": "spa16",
        "issue": 6,
        "source": BASE,
        "fetched_at": started.isoformat(),
        "client": f"httpx/{httpx.__version__}",
        "http2_enabled": http2,
        "http_versions_observed": sorted(set(protocols)),
        "requests": len(protocols),
        "elapsed_s": round(elapsed, 2),
        "total_books_on_site": total,
        "books_fetched": len(books),
        "books": books,
        "details_sample": details,
    }


def main() -> None:
    p = argparse.ArgumentParser(description="spa16 图书抓取（HTTP/2）")
    p.add_argument("--pages", type=int, default=5)
    p.add_argument("--delay", type=float, default=0.3)
    p.add_argument("--details", type=int, default=3, help="额外抓几条详情")
    p.add_argument("--http1", action="store_true", help="关掉 h2，走 HTTP/1.1 对照")
    args = p.parse_args()

    http2 = not args.http1
    print(f"[spa16] httpx http2={http2} 抓 {args.pages} 页 …")
    result = fetch(args.pages, http2, args.delay, args.details)

    DATA.mkdir(parents=True, exist_ok=True)
    EVIDENCE.mkdir(parents=True, exist_ok=True)

    suffix = "h2" if http2 else "h1"
    out = DATA / f"spa16_books_{suffix}.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    proto = EVIDENCE / f"httpx-protocol-{suffix}.json"
    proto.write_text(
        json.dumps(
            {k: v for k, v in result.items() if k not in ("books", "details_sample")},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"\n协议：{result['http_versions_observed']}  请求数：{result['requests']}  "
          f"耗时：{result['elapsed_s']}s（含 sleep {args.delay}s×{result['requests']}）")
    print(f"站点共 {result['total_books_on_site']} 本，本次落盘 {result['books_fetched']} 本 -> {out}")
    print(f"协议证据 -> {proto}")


if __name__ == "__main__":
    main()
