"""antispider4：用字体映射表把 HTML 里没有的评分还原成明文，并与 API 对账。

issue: #7 · 案例: antispider4 · 来源: https://antispider4.scrape.center

HTML 里评分那一格长这样（没有任何数字）：

    <p class="score"><span><i class="icon icon-281"></i></span>
                     <span><i class="icon icon-981"></i></span>
                     <span><i class="icon icon-504"></i></span></p>

先跑 font_map.py 建好 data/cipher_map.json，本脚本再：
    1. 渲染页面，按 DOM 顺序取出每部电影 score 里的 icon-NNN 序列
    2. 顺便用 getComputedStyle(::before).content 读浏览器**实际解析出来的** content，
       证明映射不是我正则猜的
    3. 用映射表解码成明文评分
    4. 打 /api/movie 取明文评分做 ground truth，逐条对账

跑法：
    ../../../.venv/bin/python font_map.py   # 先建表
    ../../../.venv/bin/python spider.py
产出：
    data/antispider4_movies.json    还原出的电影 + 评分 + 对账结果
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json  # noqa: E402

from common import BROWSER_UA, data_dir, dump_json, get  # noqa: E402

BASE = "https://antispider4.scrape.center"
PAGES = 10
LIMIT = 10


def load_map(d: str) -> dict[str, str]:
    p = os.path.join(d, "cipher_map.json")
    if not os.path.exists(p):
        raise SystemExit("请先跑 font_map.py 生成 data/cipher_map.json")
    with open(p, encoding="utf-8") as f:
        return json.load(f)["decode_map_icon_to_digit"]


def api_scores(page: int) -> dict[str, str]:
    r = get(f"{BASE}/api/movie/", ua=BROWSER_UA,
            params={"limit": LIMIT, "offset": (page - 1) * LIMIT})
    r.raise_for_status()
    return {str(m["id"]): (m["name"], f"{float(m['score']):.1f}") for m in r.json()["results"]}


def dom_rows(pg, page: int):
    url = f"{BASE}/" if page == 1 else f"{BASE}/page/{page}"
    pg.goto(url, wait_until="domcontentloaded", timeout=60000)
    pg.wait_for_selector("p.score i.icon", timeout=30000)
    pg.wait_for_timeout(1200)
    return pg.evaluate(
        """() => Array.from(document.querySelectorAll('div.el-card.item')).map(card => {
            const a = card.querySelector('a.name');
            const icons = Array.from(card.querySelectorAll('p.score i.icon'));
            return {
                id: a ? a.getAttribute('href').split('/').pop() : null,
                name: a ? a.innerText.trim() : '',
                // HTML 里能拿到的全部信息：只有 class 名
                icon_classes: icons.map(i => Array.from(i.classList)
                                              .find(c => c.startsWith('icon-'))),
                // 浏览器真正解析出来的 ::before content（不是正则猜的）
                computed_before: icons.map(i =>
                    getComputedStyle(i, '::before').content),
                // 证明 HTML 文本里确实没有数字
                score_text: card.querySelector('p.score').innerText
            };
        })"""
    )


def main():
    d = data_dir(__file__)
    icon2digit = load_map(d)
    from playwright.sync_api import sync_playwright

    out, ok, total = [], 0, 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent=BROWSER_UA)
        ctx.route("**/*.{png,jpg,jpeg,webp,gif}", lambda route: route.abort())
        pg = ctx.new_page()
        for p in range(1, PAGES + 1):
            truth = api_scores(p)
            for row in dom_rows(pg, p):
                decoded = "".join(icon2digit.get(c, "?") for c in row["icon_classes"])
                name, real = truth.get(row["id"], ("", ""))
                total += 1
                good = decoded == real
                ok += good
                out.append(
                    {
                        "id": row["id"],
                        "name": row["name"] or name,
                        "icon_classes": row["icon_classes"],       # HTML 里的密文
                        "computed_before": row["computed_before"],  # 浏览器解析出的 content
                        "html_score_text": row["score_text"],       # HTML 文本（应为空）
                        "decoded_score": decoded,                   # 还原出的明文
                        "api_score": real,                          # ground truth
                        "match": good,
                    }
                )
            print(f"page {p:>2}  累计 {total} 条，对上 {ok} 条")
    path = dump_json(out, os.path.join(d, "antispider4_movies.json"))

    print(f"\n还原 {total} 条，与 API 明文一致 {ok} 条")
    empty = sum(1 for r in out if not r["html_score_text"].strip())
    print(f"HTML 文本里评分为空（即数字确实不在 HTML 内）的条数：{empty}/{total}")
    for r in out[:3]:
        print(f"  {r['name']}: {r['icon_classes']} → {r['decoded_score']} "
              f"(API {r['api_score']})  computed={r['computed_before']}")
    print(f"落盘 → {path}")


if __name__ == "__main__":
    main()
