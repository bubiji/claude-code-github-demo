"""antispider3：文字偏移反爬——把「源码顺序 → 渲染顺序」的映射还原出来。

issue: #7 · 案例: antispider3 · 来源: https://antispider3.scrape.center

机制（从站点自身 JS 里读出来的原文，见 README）：

    getTextChar: function(t, a) {
        if (!t) return [];
        for (var e = [], n = 0; n < t.length; n++)
            e.push({content: t.charAt(n), offset: a * n});
        return Math.random() < .8 && e.sort((function() { return Math.random() - .5 })), e
    }

每个字先按真实下标算出 offset = 16 * n，然后整个数组被 **随机洗牌**；
模板再把每个字渲染成 `<span class="char" style="left: {offset}px">`，
配合 CSS `.char{display:inline-block;position:absolute}` 绝对定位。
于是「DOM/源码顺序」被打乱，而「所见顺序」由 left 的像素值决定。

还原办法：读每个 span 的 left，除以 16 得到真实下标，按下标重排即可。

本脚本：
    1. 打 /api/book 拿到明文书名（ground truth）
    2. Playwright 渲染同一页，按 DOM 顺序抓出 (char, left)
    3. 按 left 重排还原，与 ground truth 逐字比对，统计准确率

跑法：
    ../../../.venv/bin/python spider.py
产出：
    data/antispider3_offset_map.json   每本书的源码顺序 / 偏移 / 渲染顺序 / 置换
    data/antispider3_books.json        还原出的书名 + API 明文对照
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json  # noqa: E402

from common import BROWSER_UA, data_dir, dump_json, get  # noqa: E402

BASE = "https://antispider3.scrape.center"
CHAR_WIDTH = 16  # 模板里写死的 getTextChar(a.name, 16)
PAGES = 3
LIMIT = 18


def api_books(page: int) -> list[dict]:
    r = get(f"{BASE}/api/book/", ua=BROWSER_UA,
            params={"limit": LIMIT, "offset": (page - 1) * LIMIT})
    r.raise_for_status()
    return r.json()["results"]


def dom_books(page_obj, page: int) -> list[dict]:
    """渲染页面，按 DOM 顺序抓出每本书的 char span。"""
    url = f"{BASE}/" if page == 1 else f"{BASE}/page/{page}"
    page_obj.goto(url, wait_until="domcontentloaded", timeout=60000)
    page_obj.wait_for_selector("h3.name span.char, h3.name.whole", timeout=30000)
    page_obj.wait_for_timeout(1500)  # 等 18 张卡片全部渲染完
    return page_obj.evaluate(
        """() => Array.from(document.querySelectorAll('div.el-card.item')).map(card => {
            const link = card.querySelector('.bottom a');
            const h3 = card.querySelector('h3.name');
            const chars = Array.from(card.querySelectorAll('h3.name span.char')).map(s => {
                // 模板给每个 span 包了换行+缩进；trim 掉之后为空说明这一位本来就是空格
                const c = s.textContent.trim();
                return {content: c === '' ? ' ' : c, left: parseFloat(s.style.left)};
            });
            return {
                id: link ? link.getAttribute('href').split('/').pop() : null,
                whole: h3 ? h3.classList.contains('whole') : false,
                dom_text: h3 ? h3.innerText.replace(/\\s+/g, '') : '',
                chars: chars
            };
        })"""
    )


def restore(chars: list[dict]) -> str:
    """按 left 升序重排 → 所见顺序 = 真实书名。"""
    return "".join(c["content"] for c in sorted(chars, key=lambda c: c["left"]))


def main():
    d = data_dir(__file__)
    from playwright.sync_api import sync_playwright

    records, books = [], []
    total = shuffled = ok = 0

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent=BROWSER_UA)
        # 封面图对本案例没用，直接拦掉：省流量也更礼貌
        ctx.route("**/*.{png,jpg,jpeg,webp,gif}", lambda route: route.abort())
        pg = ctx.new_page()

        for p in range(1, PAGES + 1):
            truth = {b["id"]: b["name"] for b in api_books(p)}
            for item in dom_books(pg, p):
                bid = item["id"]
                plain = truth.get(bid, "")
                if item["whole"] or not item["chars"]:
                    # 名字里含 0-9a-zA-Z 时模板走 h3.name.whole 分支，不做偏移
                    books.append({"id": bid, "restored": item["dom_text"],
                                  "api_name": plain, "offset_applied": False})
                    continue

                total += 1
                src_order = [c["content"] for c in item["chars"]]
                offsets = [c["left"] for c in item["chars"]]
                # 源码里第 i 个 span，其真实下标 = left / 16
                perm = [int(round(o / CHAR_WIDTH)) for o in offsets]
                rendered = restore(item["chars"])
                is_shuffled = perm != sorted(perm)
                shuffled += is_shuffled
                good = rendered == plain
                ok += good

                records.append(
                    {
                        "id": bid,
                        "api_name": plain,
                        "source_order": "".join(src_order),          # 源码/DOM 顺序
                        "offsets_px": offsets,                        # 每个 span 的 left
                        "source_index_to_true_index": perm,           # 源码第 i 位 → 真实第 perm[i] 位
                        "rendered_order": rendered,                   # 所见顺序（按 left 重排）
                        "shuffled": is_shuffled,
                        "match_api": good,
                    }
                )
                books.append({"id": bid, "restored": rendered,
                              "api_name": plain, "offset_applied": True})
            pg.wait_for_timeout(1000)
        browser.close()

    with open(os.path.join(d, "antispider3_offset_map.json"), "w", encoding="utf-8") as f:
        json.dump(
            {
                "char_width_px": CHAR_WIDTH,
                "css": ".item .bottom .name .char{display:inline-block;position:absolute}",
                "rule": "真实下标 = round(left / 16)；所见顺序 = 按 left 升序",
                "stats": {"offset_names": total, "actually_shuffled": shuffled,
                          "restored_match_api": ok},
                "records": records,
            },
            f, ensure_ascii=False, indent=2,
        )
    dump_json(books, os.path.join(d, "antispider3_books.json"))

    print(f"偏移书名 {total} 条，其中源码顺序被打乱 {shuffled} 条")
    print(f"按 left 重排后与 API 明文一致：{ok}/{total}")
    for r in records[:3]:
        print(f"  源码 {r['source_order']}  →  重排 {r['rendered_order']}  "
              f"（API: {r['api_name']}）perm={r['source_index_to_true_index']}")
    print(f"落盘 → {d}")


if __name__ == "__main__":
    main()
