"""antispider2：User-Agent 反爬实测——哪些 UA 被拒、哪些放行。

issue: #7 · 案例: antispider2 · 来源: https://antispider2.scrape.center

跑法：
    ../../../.venv/bin/python ua_probe.py
产出：
    data/ua_matrix.json   逐个 UA 的 status/bytes/首屏片段
    data/ua_matrix.md     人可读实测表
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json  # noqa: E402

import requests  # noqa: E402

from common import POLITE_INTERVAL, data_dir, polite_sleep  # noqa: E402

URL = "https://antispider2.scrape.center/"

# (分组, UA)；None = 不设 UA（requests 会自动补 python-requests/x.y）
CASES = [
    ("HTTP 客户端默认", None),
    ("HTTP 客户端默认", "python-requests/2.34.2"),
    ("HTTP 客户端默认", "python-requests/2.0"),
    ("HTTP 客户端默认", "Python-urllib/3.14"),
    ("HTTP 客户端默认", "urllib3/2.7.0"),
    ("HTTP 客户端默认", "curl/8.7.1"),
    ("HTTP 客户端默认", "Wget/1.21.4"),
    ("HTTP 客户端默认", "Scrapy/2.11 (+https://scrapy.org)"),
    ("HTTP 客户端默认", "okhttp/4.9"),
    ("HTTP 客户端默认", "Go-http-client/1.1"),
    ("HTTP 客户端默认", "httpx/0.28.1"),
    ("HTTP 客户端默认", "PostmanRuntime/7.36"),
    ("HTTP 客户端默认", "Java/17"),
    ("HTTP 客户端默认", "aiohttp/3.9"),
    ("裸关键词", "python"),
    ("裸关键词", "requests"),
    ("裸关键词", "spider"),
    ("裸关键词", "bot"),
    ("裸关键词", "crawler"),
    ("搜索引擎", "Googlebot/2.1 (+http://www.google.com/bot.html)"),
    ("搜索引擎", "Baiduspider"),
    ("搜索引擎", "bingbot/2.0"),
    ("无意义串", ""),
    ("无意义串", "x"),
    ("无意义串", "-"),
    ("无意义串", "Mozilla/5.0"),
    (
        "浏览器",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    ),
    (
        "浏览器",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) HeadlessChrome/120.0.0.0 Safari/537.36",
    ),
    (
        "浏览器",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    ),
    ("混搭", "Mozilla/5.0 python-requests/2.34.2"),
    ("混搭", "Chrome/120.0.0.0 spider"),
]


def probe():
    rows = []
    for group, ua in CASES:
        headers = {} if ua is None else {"User-Agent": ua}
        polite_sleep(POLITE_INTERVAL)
        r = requests.get(URL, headers=headers, timeout=20, allow_redirects=False)
        sent = r.request.headers.get("User-Agent")
        rows.append(
            {
                "group": group,
                "ua": ua,
                "ua_sent": sent,
                "status": r.status_code,
                "bytes": len(r.content),
                "snippet": " ".join(r.text[:120].split()),
                "passed": r.status_code == 200,
            }
        )
        flag = "放行" if r.status_code == 200 else "拒绝"
        print(f"{r.status_code}  {len(r.content):>6}B  {flag}  ua={ua!r}")
    return rows


def to_markdown(rows):
    lines = [
        "# antispider2 User-Agent 实测表",
        "",
        f"目标：{URL}",
        "",
        "| 分组 | 实际发出的 User-Agent | 状态码 | 响应字节 | 结果 |",
        "|---|---|---|---|---|",
    ]
    for r in rows:
        ua = r["ua_sent"] or "(空)"
        ua = ua.replace("|", "\\|")
        if len(ua) > 78:
            ua = ua[:75] + "..."
        lines.append(
            f"| {r['group']} | `{ua}` | {r['status']} | {r['bytes']} | "
            f"{'✅ 放行' if r['passed'] else '❌ 拒绝'} |"
        )
    ok = sum(1 for r in rows if r["passed"])
    lines += ["", f"共 {len(rows)} 个 UA：放行 {ok}，拒绝 {len(rows) - ok}。"]
    return "\n".join(lines) + "\n"


def main():
    d = data_dir(__file__)
    rows = probe()
    with open(os.path.join(d, "ua_matrix.json"), "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    with open(os.path.join(d, "ua_matrix.md"), "w", encoding="utf-8") as f:
        f.write(to_markdown(rows))
    ok = sum(1 for r in rows if r["passed"])
    print(f"\n共 {len(rows)} 个 UA：放行 {ok}，拒绝 {len(rows) - ok}")
    print(f"落盘 → {d}/ua_matrix.json, {d}/ua_matrix.md")


if __name__ == "__main__":
    main()
