#!/usr/bin/env python3
"""spa7 可选校验：真浏览器里悬停第一张卡片，读 element-ui tooltip 实际渲染出的 Token。

issue: #11 · 案例: spa7 · 来源: https://spa7.scrape.center

这是「最终裁判」——不经过任何我们自己的代码路径，直接看用户在页面上看到的字符串。
需要额外依赖 playwright + chromium（不在仓库根 requirements.txt 里）：

    ../../../.venv/bin/pip install playwright
    ../../../.venv/bin/playwright install chromium
    ../../../.venv/bin/python verify_with_browser.py
"""
import json

from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto('https://spa7.scrape.center/', wait_until='networkidle')
    page.hover('#players .player >> nth=0')
    page.wait_for_selector('.el-tooltip__popper', timeout=10000)
    print(json.dumps({
        'name': page.inner_text('#players .player .name >> nth=0'),
        'tooltip_token': page.inner_text('.el-tooltip__popper').strip(),
    }, ensure_ascii=False))
    browser.close()
