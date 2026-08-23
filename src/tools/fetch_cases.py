#!/usr/bin/env python3
"""从 scrape.center 抓取全部练习案例清单（原件保真，逐字不改写）。

scrape.center 首页是 Vue SPA，案例数据不在 HTML 里，而是硬编码在异步 chunk
的 `items:[...]` 数组中。本脚本按这条路径取原始数据并落盘为 JSON：

  首页 HTML → 找 prefetch 的 chunk-*.js → 定位 items:[...] → 补引号转 JSON

用法：
  python3 src/tools/fetch_cases.py            # 打印清单
  python3 src/tools/fetch_cases.py -o out.json
"""
import argparse
import json
import re
import urllib.request

HOME = "https://scrape.center/"
UA = {"User-Agent": "Mozilla/5.0"}


def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def chunk_urls(html):
    """首页里 prefetch/preload 的 js chunk 地址（相对路径补全）。"""
    return ["https://scrape.center" + p for p in re.findall(r'href=(/js/chunk-[\w.-]+\.js)', html)]


def extract_items(js):
    """从 chunk 源码里截出 items:[...] 数组并转成 Python 对象。"""
    start = js.find("items:[")
    if start < 0:
        return None
    i = start + len("items:")
    depth = 0
    for j in range(i, len(js)):
        if js[j] == "[":
            depth += 1
        elif js[j] == "]":
            depth -= 1
            if depth == 0:
                raw = js[i:j + 1]
                break
    else:
        return None
    # 压缩后的对象字面量键名没有引号，补上才能当 JSON 解析
    return json.loads(re.sub(r'([{,])(\w+):', r'\1"\2":', raw))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--output", help="写入 JSON 文件")
    a = ap.parse_args()

    html = get(HOME)
    items = None
    for u in chunk_urls(html):
        items = extract_items(get(u))
        if items:
            break
    if not items:
        raise SystemExit("未能定位案例数组 items:[...]，站点结构可能已变")

    if a.output:
        with open(a.output, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
        print(f"✓ {len(items)} 个案例 → {a.output}")
    else:
        for x in items:
            print(f"{x['name']}\t{x['category']}\t{x['url']}\t{x['description']}")


if __name__ == "__main__":
    main()
