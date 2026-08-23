"""antispider1：WebDriver 反爬——先复现拦截，再隐藏特征后正常渲染。

issue: #7 · 案例: antispider1 · 来源: https://antispider1.scrape.center

检测点（从站点自身 JS 里读出来的原文，见 README）：

    var E = window.navigator.webdriver;
    E ? document.getElementById("app").innerHTML = "<h2>Webdriver Forbidden.</h2>"
      : new r["default"]({...}).$mount("#app")

所以判定 100% 发生在客户端：服务端照常返回同一份 HTML，是浏览器里的 JS
读到 navigator.webdriver === true 之后把 #app 换成一句 Webdriver Forbidden。
对策就是让 navigator.webdriver 不为真。

本脚本跑三趟做对照：
    A. 纯 HTTP（requests）      —— 证明服务端没做任何区分
    B. Playwright 不打补丁      —— 复现 "Webdriver Forbidden."
    C. Playwright 隐藏特征      —— 页面正常渲染，抓下 10 页电影

跑法：
    ../../../.venv/bin/python spider.py
产出：
    data/webdriver_evidence.json    三趟对照的证据
    data/antispider1_movies.json    C 趟抓下来的电影列表
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json  # noqa: E402

from common import BROWSER_UA, data_dir, dump_json, get  # noqa: E402

BASE = "https://antispider1.scrape.center"
PAGES = 10

# 隐藏 webdriver 特征：在任何页面脚本之前执行，把 navigator.webdriver 改掉
STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
"""


def trial_http() -> dict:
    """A：纯 HTTP 取首页，看服务端有没有区别对待。"""
    r = get(f"{BASE}/", ua=BROWSER_UA)
    html = r.text
    return {
        "trial": "A · 纯 HTTP（requests）",
        "status": r.status_code,
        "bytes": len(r.content),
        "app_div": "<div id=app></div>" in html.replace('"', ""),
        "contains_forbidden": "Webdriver Forbidden" in html,
        "note": "服务端返回的是空壳 SPA，HTML 里既没有电影数据也没有 Forbidden 字样",
    }


def _render(pw, stealth: bool):
    """打开首页，返回 (#app 的文本, 卡片数)。"""
    browser = pw.chromium.launch(headless=True)
    ctx = browser.new_context(user_agent=BROWSER_UA)
    if stealth:
        ctx.add_init_script(STEALTH_JS)
    page = ctx.new_page()
    page.goto(f"{BASE}/", wait_until="networkidle", timeout=60000)
    webdriver_value = page.evaluate("() => String(navigator.webdriver)")
    app_text = page.inner_text("#app").strip()
    cards = page.locator("div.el-card.item").count()
    browser.close()
    return webdriver_value, app_text, cards


def scrape_movies(pw) -> list[dict]:
    """C 趟顺带把 10 页电影抓下来（读渲染后的 DOM，不直接打 API）。"""
    browser = pw.chromium.launch(headless=True)
    ctx = browser.new_context(user_agent=BROWSER_UA)
    ctx.add_init_script(STEALTH_JS)
    page = ctx.new_page()
    movies = []
    for p in range(1, PAGES + 1):
        page.goto(f"{BASE}/page/{p}", wait_until="networkidle", timeout=60000)
        page.wait_for_selector("div.el-card.item", timeout=30000)
        got = page.evaluate(
            """() => Array.from(document.querySelectorAll('div.el-card.item')).map(c => {
                const a = c.querySelector('a.name');
                const infos = c.querySelectorAll('div.info');
                const spans = infos[0] ? Array.from(infos[0].querySelectorAll('span')).map(s => s.innerText.trim()) : [];
                return {
                    id: a ? parseInt(a.getAttribute('href').split('/').pop()) : null,
                    name: a ? a.innerText.trim() : '',
                    categories: Array.from(c.querySelectorAll('button.category')).map(b => b.innerText.trim()),
                    regions: spans[0] ? spans[0].split('、') : [],
                    minute: spans[2] || '',
                    published_at: infos[1] ? infos[1].innerText.trim() : '',
                    score: (c.querySelector('p.score') || {}).innerText ?
                           c.querySelector('p.score').innerText.trim() : '',
                    cover: (c.querySelector('img.cover') || {}).src || ''
                };
            })"""
        )
        movies.extend(got)
        print(f"  page {p:>2}  渲染出 {len(got)} 条")
        page.wait_for_timeout(1000)  # 礼貌间隔
    browser.close()
    return movies


def main():
    d = data_dir(__file__)
    evidence = [trial_http()]
    print(f"A 纯 HTTP：status={evidence[0]['status']} "
          f"contains_forbidden={evidence[0]['contains_forbidden']}")

    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        wd, text, cards = _render(pw, stealth=False)
        evidence.append(
            {
                "trial": "B · Playwright 未处理",
                "navigator.webdriver": wd,
                "app_inner_text": text,
                "movie_cards": cards,
                "blocked": "Webdriver Forbidden" in text,
            }
        )
        print(f"B 未处理：navigator.webdriver={wd}  #app={text!r}  卡片数={cards}")

        wd2, text2, cards2 = _render(pw, stealth=True)
        evidence.append(
            {
                "trial": "C · Playwright 隐藏 webdriver 特征",
                "init_script": STEALTH_JS.strip(),
                "navigator.webdriver": wd2,
                "app_inner_text_head": text2[:80],
                "movie_cards": cards2,
                "blocked": "Webdriver Forbidden" in text2,
            }
        )
        print(f"C 隐藏后：navigator.webdriver={wd2}  卡片数={cards2}  "
              f"首屏={text2[:40]!r}")

        print("\nC 趟抓取 10 页：")
        movies = scrape_movies(pw)

    with open(os.path.join(d, "webdriver_evidence.json"), "w", encoding="utf-8") as f:
        json.dump(evidence, f, ensure_ascii=False, indent=2)
    path = dump_json(movies, os.path.join(d, "antispider1_movies.json"))
    print(f"\n共 {len(movies)} 条 → {path}")
    if movies:
        print("首条：", movies[0]["name"], movies[0]["score"])


if __name__ == "__main__":
    main()
