#!/usr/bin/env python3
"""ssr2 —— HTTPS 证书校验：先探明证书到底什么状况，再决定要不要显式关掉校验。

issue: #4 · 案例: ssr2 · 来源: https://ssr2.scrape.center

要点是「明确关掉校验并说明风险」，不是靠 `warnings.filterwarnings` 把
InsecureRequestWarning 藏起来蒙混过去。所以本脚本：

1. `probe_tls()` 先用**开启校验**的方式访问一次，把 SSLError 的原文打印出来
   （证书到底哪里不对，是过期、自签名，还是域名不匹配）；
2. 只有在校验确实失败时才回落到 `verify=False`，并在 stderr 打一条醒目的
   风险声明——关闭校验 = 放弃中间人攻击防护；
3. 关闭校验后仍**保留** urllib3 的 InsecureRequestWarning（不 disable），
   让「这次连接不可信」这件事一直可见。

    python crawl.py                # 自动探测：能校验就校验，不能才关
    python crawl.py --insecure     # 强制 verify=False（复现案例设计意图）
    python crawl.py --strict       # 强制 verify=True，证书不过就直接失败
"""
from __future__ import annotations

import argparse
import ssl
import socket
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import add_common_args, build_summary, crawl, report, save_dataset  # noqa: E402

BASE = "https://ssr2.scrape.center"
NAME = "ssr2"
UA = "claude-code-github-demo/1.0 (scrape.center practice; issue #4)"

RISK = """
!! 已关闭 TLS 证书校验（verify=False）。
!! 风险：不校验证书 = 无法确认对端真是 ssr2.scrape.center，任何能插进链路的人
!!       （公共 WiFi、劫持的 DNS、透明代理）都能出示自己的证书冒充服务端，
!!       明文读走并篡改全部往返内容——即中间人攻击（MITM）。HTTPS 的加密还在，
!!       但「加密给谁」这一半保证没了，等价于对一个陌生人加密。
!! 之所以在这里可接受：目标是案例作者公开提供的练习站（issue #4），抓的是公开
!!   电影数据，请求里不带任何凭证或隐私。生产环境的正解是修证书/配私有 CA，
!!   而不是 verify=False。
""".strip()


def cert_info(url: str) -> dict:
    """不做校验地取一次对端证书，把 subject / issuer / 有效期 / SAN 打出来存档。"""
    host = urlparse(url).hostname
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with socket.create_connection((host, 443), timeout=15) as sock:
        with ctx.wrap_socket(sock, server_hostname=host) as tls:
            der = tls.getpeercert(binary_form=True)
            ver = tls.version()
    # CERT_NONE 下 getpeercert() 拿不到解析后的字段，用 DER 再解一次
    parsed = ssl._ssl._test_decode_cert  # noqa: SLF001
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False) as fh:
        fh.write(ssl.DER_cert_to_PEM_cert(der))
        pem_path = fh.name
    try:
        cert = parsed(pem_path)
    finally:
        Path(pem_path).unlink(missing_ok=True)
    return {
        "tls_version": ver,
        "subject": dict(x[0] for x in cert.get("subject", ())),
        "issuer": dict(x[0] for x in cert.get("issuer", ())),
        "notBefore": cert.get("notBefore"),
        "notAfter": cert.get("notAfter"),
        "subjectAltName": [v for k, v in cert.get("subjectAltName", ()) if k == "DNS"],
    }


def probe_tls(session: requests.Session, timeout: float) -> tuple[bool, str | None]:
    """开启校验访问一次：返回 (校验是否通过, 失败原文)。"""
    try:
        session.get(f"{BASE}/page/1", timeout=timeout, verify=True)
        return True, None
    except requests.exceptions.SSLError as exc:
        return False, f"{type(exc).__name__}: {exc}"


def make_fetch(session: requests.Session, timeout: float, verify: bool):
    def fetch(url: str) -> str:
        resp = session.get(url, timeout=timeout, verify=verify)
        if resp.status_code == 500 and "/page/" in url:
            return ""  # 第 11 页 500 = 没有下一页
        resp.raise_for_status()
        return resp.text

    return fetch


def main() -> int:
    ap = add_common_args(argparse.ArgumentParser(description=__doc__))
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--insecure", action="store_true", help="强制关闭证书校验")
    g.add_argument("--strict", action="store_true", help="强制开启校验，证书不过即失败")
    args = ap.parse_args()

    session = requests.Session()
    session.headers["User-Agent"] = UA

    info = cert_info(BASE)
    print(f"[{NAME}] 对端证书：subject={info['subject'].get('commonName')} "
          f"issuer={info['issuer'].get('organizationName')}/{info['issuer'].get('commonName')} "
          f"有效期 {info['notBefore']} → {info['notAfter']} SAN={info['subjectAltName']} "
          f"({info['tls_version']})")

    ok, err = probe_tls(session, args.timeout)
    print(f"[{NAME}] 开启校验试连：{'通过' if ok else '失败'}")
    if err:
        print(f"[{NAME}] 校验失败原文：{err}")

    if args.strict:
        verify = True
        if not ok:
            print(f"[{NAME}] --strict 且证书校验不过，按要求直接失败退出。", file=sys.stderr)
            return 2
    elif args.insecure:
        verify = False
    else:
        verify = ok  # 能校验就校验，不能才关——关闭是有依据的决定，不是默认姿势

    if not verify:
        print(RISK, file=sys.stderr)
        # 故意不调用 urllib3.disable_warnings()：InsecureRequestWarning 要一直看得见

    print(f"[{NAME}] {BASE} · verify={verify} workers={args.workers} delay={args.delay}s")
    records, stats = crawl(
        BASE, make_fetch(session, args.timeout, verify),
        workers=args.workers, delay=args.delay, with_detail=not args.no_detail,
    )

    outdir = Path(args.out) if args.out else Path(__file__).resolve().parent / "data"
    summary = build_summary(records, stats, {
        "case": NAME, "issue": 4, "base": BASE,
        "tls": {"verify_used": verify, "verify_passed": ok, "error": err, "cert": info},
        "note": "案例设计为『无 HTTPS 证书』；实测时证书状况见 tls 字段",
    })
    # ssr1~ssr4 是同一套站的数据，CSV 只在 ssr1 出一份做演示，这里不再塞第二份同样的表
    saved = save_dataset(outdir, NAME, records, summary, write_csv=False)
    report(NAME, records, stats, saved)
    return 1 if stats.failures else 0


if __name__ == "__main__":
    sys.exit(main())
