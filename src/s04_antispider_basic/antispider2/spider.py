"""antispider2：换个合规 UA 就能正常抓的服务端渲染电影列表。

issue: #7 · 案例: antispider2 · 来源: https://antispider2.scrape.center

跑法：
    ../../../.venv/bin/python spider.py
产出：
    data/antispider2_movies.json   10 页共 100 条
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bs4 import BeautifulSoup  # noqa: E402

from common import BROWSER_UA, data_dir, dump_json, get  # noqa: E402

BASE = "https://antispider2.scrape.center"
PAGES = 10


def parse(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    items = []
    for card in soup.select("div.el-card.item"):
        a = card.select_one("a.name")
        if not a:
            continue
        h2 = a.select_one("h2")
        name = h2.get_text(strip=True) if h2 else ""
        infos = card.select("div.info")
        line1 = [s.get_text(strip=True) for s in infos[0].select("span")] if infos else []
        published = infos[1].get_text(strip=True) if len(infos) > 1 else ""
        score = card.select_one("p.score")
        cover = card.select_one("img.cover")
        items.append(
            {
                "id": int(a["href"].rsplit("/", 1)[-1]),
                "name": name,
                "categories": [b.get_text(strip=True) for b in card.select("button.category span")],
                "regions": line1[0].split("、") if line1 else [],
                "minute": line1[2] if len(line1) > 2 else "",
                "published_at": published,
                "score": score.get_text(strip=True) if score else "",
                "cover": cover["src"] if cover else "",
                "detail_url": BASE + a["href"],
            }
        )
    return items


def main():
    movies = []
    for page in range(1, PAGES + 1):
        url = f"{BASE}/page/{page}"
        r = get(url, ua=BROWSER_UA)
        print(f"page {page:>2}  {r.status_code}  {len(r.content)}B", end="")
        if r.status_code != 200:
            print("  ← 被拒，停止")
            break
        got = parse(r.text)
        movies.extend(got)
        print(f"  解析 {len(got)} 条")

    d = data_dir(__file__)
    path = dump_json(movies, os.path.join(d, "antispider2_movies.json"))
    print(f"\n共 {len(movies)} 条 → {path}")
    if movies:
        print("首条：", movies[0]["name"], movies[0]["score"], movies[0]["published_at"])


if __name__ == "__main__":
    main()
