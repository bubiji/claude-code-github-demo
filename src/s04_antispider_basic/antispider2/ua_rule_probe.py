"""antispider2：把「服务端到底按什么判」测出来。

issue: #7 · 案例: antispider2 · 来源: https://antispider2.scrape.center

ua_probe.py 只回答「哪些 UA 被拒」；本脚本回答「怎么判的」：
对每个候选关键词做 4 组对照，判定它是「整串子串匹配」还是「只在开头才算」，
以及是否区分大小写。

    T            关键词单独发
    "T tail"     关键词在开头
    "head T"     关键词在中间
    T.upper()    大写变体

判定：
    中间也拒 → substring（出现在任何位置都算）
    只有开头拒 → prefix（必须以它开头）
    大写放行 → 区分大小写

跑法：
    ../../../.venv/bin/python ua_rule_probe.py
产出：
    data/ua_rule.json / data/ua_rule.md
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json  # noqa: E402

import requests  # noqa: E402

from common import POLITE_INTERVAL, data_dir, polite_sleep  # noqa: E402

URL = "https://antispider2.scrape.center/"

TOKENS = [
    "python-requests",
    "Python-urllib",
    "curl",
    "wget",
    "Wget",
    "Scrapy",
    "okhttp",
    "Go-http-client",
    "PostmanRuntime",
    "Googlebot/",  # 注意带斜杠；不带斜杠的 "Googlebot" 实测放行
    "Googlebot",
    "Baiduspider",
    "bingbot",
    "libwww-perl",
    "HeadlessChrome",
    # 对照组：实测放行，用来证明「不是只要像爬虫就拒」
    "aiohttp",
    "httpx",
    "spider",
    "bot",
]


def status(ua: str) -> int:
    polite_sleep(POLITE_INTERVAL * 0.8)
    r = requests.get(URL, headers={"User-Agent": ua}, timeout=20, allow_redirects=False)
    return r.status_code


def classify(token: str) -> dict:
    alone = status(token)
    at_head = status(f"{token} tail-junk")
    in_middle = status(f"head-junk {token} tail-junk")
    upper = status(token.upper())

    if in_middle == 403:
        kind = "substring"  # 出现在任何位置都被拒
    elif alone == 403 and at_head == 403:
        kind = "prefix"  # 必须以它开头
    elif alone == 403:
        kind = "exact"
    else:
        kind = "allowed"  # 不在黑名单

    return {
        "token": token,
        "alone": alone,
        "at_head": at_head,
        "in_middle": in_middle,
        "upper": upper,
        "match": kind,
        "case_sensitive": (kind != "allowed" and upper == 200),
    }


def main():
    d = data_dir(__file__)
    rows = [classify(t) for t in TOKENS]
    for r in rows:
        print(
            f"{r['token']:<18} alone={r['alone']} head={r['at_head']} "
            f"mid={r['in_middle']} UPPER={r['upper']} → {r['match']}"
            + ("（区分大小写）" if r["case_sensitive"] else "")
        )

    empty_ua = status("")
    print(f"\n空 UA（User-Agent: ）→ {empty_ua}")

    result = {"url": URL, "empty_ua_status": empty_ua, "tokens": rows}
    with open(os.path.join(d, "ua_rule.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    lines = [
        "# antispider2：服务端判定规则实测",
        "",
        "每个关键词做 4 组对照：单独发 / 放开头 / 放中间 / 全大写；只看 HTTP 状态码。",
        "",
        "| 关键词 | 单独 | 在开头 | 在中间 | 全大写 | 判定 |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| `{r['token']}` | {r['alone']} | {r['at_head']} | {r['in_middle']} | "
            f"{r['upper']} | {r['match']}"
            + ("，区分大小写" if r["case_sensitive"] else "")
            + " |"
        )
    lines += ["", f"空 UA：{empty_ua}"]
    with open(os.path.join(d, "ua_rule.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"落盘 → {d}/ua_rule.json, {d}/ua_rule.md")


if __name__ == "__main__":
    main()
