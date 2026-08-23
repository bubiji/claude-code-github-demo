#!/usr/bin/env python3
"""ssr1 —— 最基础的 SSR 抓取：requests + BeautifulSoup，列表页翻页 + 详情页解析。

issue: #4 · 案例: ssr1 · 来源: https://ssr1.scrape.center

本案例只做「请求 → 解析 → 落盘」这条最短链路，不涉及证书 / 认证 / 慢响应，
那三件事分别在 ssr2 / ssr3 / ssr4。解析与落盘逻辑在 ../common.py。

    python crawl.py                 # 默认串行 + 0.3s 礼貌间隔
    python crawl.py --workers 4     # 想快一点
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import add_common_args, build_summary, crawl, report, save_dataset  # noqa: E402

BASE = "https://ssr1.scrape.center"
NAME = "ssr1"
UA = "claude-code-github-demo/1.0 (scrape.center practice; issue #4)"


def make_fetch(session: requests.Session, timeout: float):
    def fetch(url: str) -> str:
        resp = session.get(url, timeout=timeout)
        # 翻到第 11 页时本站直接 500（不是空列表页），把它当成「没有下一页」而非故障。
        if resp.status_code == 500 and "/page/" in url:
            return ""
        resp.raise_for_status()
        return resp.text

    return fetch


def main() -> int:
    ap = add_common_args(argparse.ArgumentParser(description=__doc__))
    args = ap.parse_args()

    session = requests.Session()
    session.headers["User-Agent"] = UA

    print(f"[{NAME}] {BASE} · workers={args.workers} delay={args.delay}s")
    records, stats = crawl(
        BASE, make_fetch(session, args.timeout),
        workers=args.workers, delay=args.delay, with_detail=not args.no_detail,
    )

    outdir = Path(args.out) if args.out else Path(__file__).resolve().parent / "data"
    summary = build_summary(records, stats, {
        "case": NAME, "issue": 4, "base": BASE,
        "note": "无反爬，服务端渲染，直接 requests + BeautifulSoup 即可",
    })
    saved = save_dataset(outdir, NAME, records, summary)
    report(NAME, records, stats, saved)
    return 1 if stats.failures else 0


if __name__ == "__main__":
    sys.exit(main())
