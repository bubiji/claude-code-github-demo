#!/usr/bin/env python3
"""ssr3 —— HTTP Basic Authentication：401 挑战 → Authorization 头 → 正常取数。

issue: #4 · 案例: ssr3 · 来源: https://ssr3.scrape.center

案例给的用户名密码均为 admin。本脚本除了正常抓取，还先做一次「无认证」请求，
把 401 与 `WWW-Authenticate` 挑战头打出来，说明 Basic Auth 到底是怎么谈成的：

    1. 客户端裸请求         → 401 + WWW-Authenticate: Basic realm="..."
    2. 客户端带 Authorization: Basic base64("admin:admin") 重试 → 200

requests 的 `auth=("admin","admin")` 就是在替你拼第 2 步那个头（HTTPBasicAuth），
脚本里用 --manual-header 可以切换成手工拼 base64 的等价写法做对照。

    python crawl.py                    # auth=("admin","admin")
    python crawl.py --manual-header    # 手工拼 Authorization 头，验证两者等价
"""
from __future__ import annotations

import argparse
import base64
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import add_common_args, build_summary, crawl, report, save_dataset  # noqa: E402

BASE = "https://ssr3.scrape.center"
NAME = "ssr3"
USERNAME = "admin"          # 案例原文：用户名密码均为 admin
PASSWORD = "admin"
UA = "claude-code-github-demo/1.0 (scrape.center practice; issue #4)"


def show_challenge(timeout: float) -> dict:
    """不带认证请求一次，把服务端的 401 挑战原样打出来。"""
    resp = requests.get(f"{BASE}/page/1", timeout=timeout,
                        headers={"User-Agent": UA})
    challenge = resp.headers.get("WWW-Authenticate")
    print(f"[{NAME}] 无认证访问 → HTTP {resp.status_code}；"
          f"WWW-Authenticate: {challenge!r}")
    return {"status": resp.status_code, "www_authenticate": challenge}


def make_session(manual_header: bool) -> tuple[requests.Session, str]:
    session = requests.Session()
    session.headers["User-Agent"] = UA
    if manual_header:
        token = base64.b64encode(f"{USERNAME}:{PASSWORD}".encode()).decode()
        session.headers["Authorization"] = f"Basic {token}"
        return session, f"手工头 Authorization: Basic {token}"
    session.auth = (USERNAME, PASSWORD)   # requests 的 HTTPBasicAuth
    return session, 'requests auth=("admin", "admin")'


def make_fetch(session: requests.Session, timeout: float):
    def fetch(url: str) -> str:
        resp = session.get(url, timeout=timeout)
        if resp.status_code == 401:
            # 认证失败要立刻炸，不能当成空页静默跳过——否则会「抓到 0 条还说成功」
            raise PermissionError(f"401 未通过 Basic Auth：{url}")
        if resp.status_code == 500 and "/page/" in url:
            return ""  # 第 11 页 500 = 没有下一页
        resp.raise_for_status()
        return resp.text

    return fetch


def main() -> int:
    ap = add_common_args(argparse.ArgumentParser(description=__doc__))
    ap.add_argument("--manual-header", action="store_true",
                    help="手工拼 Authorization: Basic base64(user:pass)，替代 requests 的 auth=")
    args = ap.parse_args()

    challenge = show_challenge(args.timeout)
    session, how = make_session(args.manual_header)
    print(f"[{NAME}] 认证方式：{how}")

    print(f"[{NAME}] {BASE} · workers={args.workers} delay={args.delay}s")
    records, stats = crawl(
        BASE, make_fetch(session, args.timeout),
        workers=args.workers, delay=args.delay, with_detail=not args.no_detail,
    )
    if not records:
        print(f"[{NAME}] 一条都没抓到，判定为认证或站点故障。", file=sys.stderr)
        return 2

    outdir = Path(args.out) if args.out else Path(__file__).resolve().parent / "data"
    summary = build_summary(records, stats, {
        "case": NAME, "issue": 4, "base": BASE,
        "auth": {"scheme": "HTTP Basic", "username": USERNAME,
                 "method": how, "unauthenticated_probe": challenge},
        "note": "案例原文：带有 HTTP Basic Authentication，用户名密码均为 admin",
    })
    # ssr1~ssr4 是同一套站的数据，CSV 只在 ssr1 出一份做演示，这里不再塞第二份同样的表
    saved = save_dataset(outdir, NAME, records, summary, write_csv=False)
    report(NAME, records, stats, saved)
    return 1 if stats.failures else 0


if __name__ == "__main__":
    sys.exit(main())
