#!/usr/bin/env python3
"""spa4（新闻网站索引 · Ajax 加载 · 无页码翻页 · 智能页面提取）。

issue: #5 · 案例: spa4 · 来源: https://spa4.scrape.center

spa4 的索引接口只给元数据（标题 / 外站原文 URL / 站点 / 缩略图 / 发布时间），
正文在**外站**。所以本案例分两步：

  ① index  —— /api/news/?limit&offset 抓索引（451370 条，默认只取前 N 条）
  ② fetch  —— 抽样打开外站原文，用 common.extract_main_text() 做**通用正文提取**：
              按「文本密度 + 链接密度」给块级节点打分，不写死任何一家新闻站的
              选择器（代码里没有一个 `#artibody` 之类的常量）。

「接口模式 / 渲染模式复用同一份解析逻辑」在这里体现得最直白：
    NewsItem.from_api(json)  —— 索引接口返回的 JSON
    NewsItem.from_dom(soup)  —— 外站原文页面的 DOM（og:* / h1 / <title> 等通用信号）
两条路都落到同一个 NewsItem.build()，脚本随后把两份记录逐字段比对（字段一致率
写进 data/spa4_articles_sample.json）。

用法：
    python spider.py                      # 索引 200 条 + 抽 25 篇原文做正文提取
    python spider.py --index-items 500 --sample 40
    python spider.py --mode index         # 只抓索引
"""

from __future__ import annotations

import argparse
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bs4 import BeautifulSoup  # noqa: E402

from common import (  # noqa: E402
    NewsItem,
    PoliteSession,
    clean_text,
    extract_main_text,
    offset_pages,
    print_stats,
    save_json,
)

API = "https://spa4.scrape.center/api/news/"
FRONTEND_LIMIT = 10  # 前端源码 data(){ ... limit: 10 ... }


def crawl_index(session: PoliteSession, limit: int, max_items: int) -> list:
    news, count = [], None
    for page in offset_pages(session, API, limit=limit, max_items=max_items):
        count = page.count
        news += [NewsItem.from_api(o, source="spa4-api") for o in page.results]
        print(f"  offset={page.offset:<6} 本次 {len(page.results):>3} 条 "
              f"累计 {len(news):>4}/{count}")
    return news


def crawl_index_spread(session: PoliteSession, limit: int, spread: int) -> list:
    """跨全库均匀取样：在 [0, count) 上等距取 spread 个 offset，各拉一页。

    索引头部清一色是同一家站点，全部按 offset=0 顺着爬，抽出来的样本没有域名多样性，
    通用正文提取就等于只在一家站上验证过。等距取样能覆盖到语料里的其他站点。
    """
    probe = session.get_json(API, params={"limit": 1, "offset": 0})
    count = probe.get("count") or 0
    step = max(1, count // max(1, spread))
    news = []
    for i in range(spread):
        offset = min(count - limit, i * step)
        payload = session.get_json(API, params={"limit": limit, "offset": offset})
        got = payload.get("results") or []
        news += [NewsItem.from_api(o, source="spa4-api") for o in got]
        print(f"  offset={offset:<6} 本次 {len(got):>3} 条 累计 {len(news):>4}/{count}")
    return news


def harvest_articles(session: PoliteSession, news: list, sample: int, seed: int) -> tuple:
    """抽样打开外站原文，做通用正文提取 + 接口/渲染两侧字段比对。"""
    random.seed(seed)
    picked = _stratified_sample(news, sample)
    rows, fails = [], 0
    for i, item in enumerate(picked, 1):
        row = {
            "id": item.id, "url": item.url, "domain": item.domain,
            "api_title": item.title, "api_published_at": item.published_at,
        }
        try:
            html = session.get_text(item.url, allow_redirects=True)
        except Exception as exc:  # 外站失效/超时是常态，记下来不中断整轮
            fails += 1
            row.update({"ok": False, "error": str(exc)[:160]})
            rows.append(row)
            print(f"  [{i}/{len(picked)}] 取回失败 {item.domain}: {str(exc)[:60]}")
            continue

        soup = BeautifulSoup(html, "lxml")
        dom_item = NewsItem.from_dom(soup, url=item.url, source="spa4-dom")
        art = extract_main_text(html)

        title_match = _loose_eq(item.title, dom_item.title)
        row.update({
            "ok": bool(art.get("ok")),
            "html_bytes": len(html.encode("utf-8", "ignore")),
            "dom_title": dom_item.title,
            "dom_title_matches_api": title_match,
            "dom_published_at": dom_item.published_at,
            "extract_container": art.get("stats", {}).get("tag"),
            "extract_stats": art.get("stats"),
            "n_paragraphs": art.get("n_paragraphs"),
            "n_chars": art.get("n_chars"),
            "text_head": (art.get("text") or "")[:300],
        })
        if not art.get("ok"):
            row.update({
                "reason": art.get("reason"),
                "body_chars": art.get("body_chars"),
                "n_p_tags": art.get("n_p_tags"),
            })
        rows.append(row)
        print(f"  [{i}/{len(picked)}] {item.domain:<24} 正文 {art.get('n_chars', 0):>5} 字 "
              f"/ {art.get('n_paragraphs', 0):>3} 段 · 容器 <{art.get('stats', {}).get('tag')}> "
              f"链接密度 {art.get('stats', {}).get('link_ratio')} · 标题一致={title_match}")
    return rows, fails


def _by_domain(rows: list) -> dict:
    """按域名统计提取成功率——通用提取器在哪家站上翻车，一眼可见。"""
    out: dict = {}
    for r in rows:
        d = out.setdefault(r.get("domain") or "?",
                           {"sampled": 0, "ok": 0, "fetch_failed": 0, "avg_chars": 0})
        d["sampled"] += 1
        if r.get("error"):
            d["fetch_failed"] += 1
        elif r.get("ok"):
            d["ok"] += 1
            d["avg_chars"] += r.get("n_chars") or 0
    for d in out.values():
        d["avg_chars"] = round(d["avg_chars"] / d["ok"]) if d["ok"] else None
    return out


def _stratified_sample(news: list, sample: int) -> list:
    """按域名分层轮转取样：先保证每个站都被取到，再按站内随机补齐。

    通用提取器的价值在「换一家站也不用改代码」，样本必须跨站，否则验证不了这一点。
    """
    buckets: dict = {}
    for item in news:
        buckets.setdefault(item.domain or "?", []).append(item)
    for items in buckets.values():
        random.shuffle(items)
    picked, i = [], 0
    while len(picked) < min(sample, len(news)):
        drained = True
        for items in buckets.values():
            if i < len(items):
                picked.append(items[i])
                drained = False
                if len(picked) >= min(sample, len(news)):
                    break
        if drained:
            break
        i += 1
    return picked


def _loose_eq(a: str, b: str) -> bool:
    """外站 <h1>/og:title 常带站点后缀，做宽松包含比较。"""
    a, b = clean_text(a), clean_text(b)
    if not a or not b:
        return False
    return a in b or b in a or a[:12] == b[:12]


def main() -> None:
    ap = argparse.ArgumentParser(description="spa4 新闻索引 + 通用正文提取")
    ap.add_argument("--mode", choices=["all", "index"], default="all")
    ap.add_argument("--limit", type=int, default=FRONTEND_LIMIT,
                    help=f"接口每页条数（前端 {FRONTEND_LIMIT}，接口实测支持 100）")
    ap.add_argument("--index-items", type=int, default=200, help="索引抓多少条（顺序模式）")
    ap.add_argument("--spread", type=int, default=0,
                    help="跨全库等距取样的页数（>0 时替代顺序抓取，用于覆盖多个站点）")
    ap.add_argument("--sample", type=int, default=25, help="抽多少篇原文做正文提取")
    ap.add_argument("--seed", type=int, default=20260823)
    ap.add_argument("--delay", type=float, default=0.5)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "data"))
    args = ap.parse_args()

    started = time.time()
    session = PoliteSession(delay=args.delay)

    print(f"① 索引：GET /api/news/?limit={args.limit}&offset=N"
          + (f"（跨全库等距取样 {args.spread} 页）" if args.spread else ""))
    if args.spread:
        news = crawl_index_spread(session, args.limit, args.spread)
    else:
        news = crawl_index(session, args.limit, args.index_items)
    info = save_json(
        os.path.join(args.out, "spa4_news_index.json"), news,
        meta={"case": "spa4", "issue": 5, "mode": "index", "api": API,
              "limit": args.limit, "requested_items": args.index_items,
              "spread_pages": args.spread, "frontend_limit": FRONTEND_LIMIT},
    )
    print(f"  -> {info}")
    if args.mode == "index":
        print_stats("spa4", started, session, records=len(news))
        return

    print("② 原文：抽样打开外站，通用正文提取（无站点选择器）")
    rows, fails = harvest_articles(session, news, args.sample, args.seed)
    ok_rows = [r for r in rows if r.get("ok")]
    chars = [r["n_chars"] for r in ok_rows if r.get("n_chars")]
    title_hits = sum(1 for r in ok_rows if r.get("dom_title_matches_api"))
    report = {
        "case": "spa4", "issue": 5, "mode": "article",
        "sampled": len(rows),
        "extracted_ok": len(ok_rows),
        "fetch_failed": fails,
        "domains": sorted({r["domain"] for r in rows if r.get("domain")}),
        "chars_min": min(chars) if chars else None,
        "chars_max": max(chars) if chars else None,
        "chars_avg": round(sum(chars) / len(chars)) if chars else None,
        "dom_title_matches_api": f"{title_hits}/{len(ok_rows)}",
        "by_domain": _by_domain(rows),
        "note": "正文容器由文本密度/链接密度打分选出，代码内无任何站点专用选择器",
    }
    info = save_json(os.path.join(args.out, "spa4_articles_sample.json"), rows, meta=report)
    print(f"  -> {info}")
    print("  汇总:", {k: v for k, v in report.items() if k != "domains"})
    print_stats("spa4", started, session, index=len(news), articles=len(ok_rows))


if __name__ == "__main__":
    main()
