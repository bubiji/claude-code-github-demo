"""spa16 —— HTTP/2 与 HTTP/1.1 的实测对比。

issue: #6 · 案例: spa16 · 来源: https://spa16.scrape.center

分三部分，各自落一份可复查的证据文件：

A. **协议协商实测**（对 spa16 本站）
   - TLS ALPN 分别只报 h2 / 只报 http/1.1 / 两个都报，看服务端选什么；
   - httpx 开 h2 与关 h2 各打一次请求，记录 `response.http_version` 或异常原文；
   - curl `--http2` 与 `--http1.1` 各打一次，记录 `%{http_version}` 与退出码。
   → evidence/protocol-negotiation.json

B. **同一批请求的定量对比**（对照站 spa1.scrape.center，h2 与 h1.1 都开）
   spa16 本站做不出 h2-vs-h1.1 的耗时对比——它根本不给 HTTP/1.1 回响应（见 A），
   所以定量那一半挪到同平台的 spa1 上做。两条指标各用各的量法：
   - **头部压缩**：同步客户端串行跑，用 `ssl.SSLSocket.send/sendall/recv` 计数器
     数「交给 TLS 去加密的字节」——HTTP/1.1 是明文头，HTTP/2 是 HPACK 压缩后的
     HEADERS 帧，差别直接落在「每请求发出字节数」上。
   - **多路复用**：异步客户端并发跑，用连接池对象数 TCP 连接数与每条连接的请求数。
   → evidence/h2-vs-h11-bench.json

C. **spa16 本站的 h2 表现**：串行 vs 并发，看是不是真的一条 TCP 连接扛下全部请求。

用法：
    python h2_vs_h11_bench.py                 # A + B + C 全跑
    python h2_vs_h11_bench.py --requests 12
    python h2_vs_h11_bench.py --skip-control  # 只跑 A + C
"""

from __future__ import annotations

import argparse
import asyncio
import json
import socket
import ssl
import statistics
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

SPA16_HOST = "spa16.scrape.center"
SPA16_API = f"https://{SPA16_HOST}/api/book/"
SPA16_LIMIT = 18

CONTROL_HOST = "spa1.scrape.center"
CONTROL_API = f"https://{CONTROL_HOST}/api/movie/"
CONTROL_LIMIT = 10

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE / "evidence"
UA = {"User-Agent": "scrape-center-practice/1.0 (+issue #6)"}


# --------------------------------------------------------------------------
# 套接字计数器：统计 TLS 明文层真正发出/收到的字节数与 TCP 连接数
# --------------------------------------------------------------------------
class SocketMeter:
    """给 ssl.SSLSocket 的 send/sendall/recv 挂计数器（只用于同步客户端）。

    计的是「交给 TLS 去加密之前的字节」，也就是 HTTP 报文本身的大小：
    HTTP/1.1 是明文请求行 + 头部，HTTP/2 是 HPACK 压缩后的 HEADERS 帧。
    异步客户端走 SSLObject + MemoryBIO，这个钩子挂不上，所以字节这项只在串行测。
    """

    def __init__(self) -> None:
        self.sent = 0
        self.recv = 0
        self.sockets: set[int] = set()
        self._lock = threading.Lock()
        self._orig: dict = {}

    def __enter__(self) -> "SocketMeter":
        meter = self
        self._orig = {
            "sendall": ssl.SSLSocket.sendall,
            "send": ssl.SSLSocket.send,
            "recv": ssl.SSLSocket.recv,
        }

        def sendall(sock, data, *a, **kw):
            with meter._lock:
                meter.sent += len(data)
                meter.sockets.add(id(sock))
            return meter._orig["sendall"](sock, data, *a, **kw)

        def send(sock, data, *a, **kw):
            n = meter._orig["send"](sock, data, *a, **kw)
            with meter._lock:
                meter.sent += n
                meter.sockets.add(id(sock))
            return n

        def recv(sock, *a, **kw):
            buf = meter._orig["recv"](sock, *a, **kw)
            with meter._lock:
                meter.recv += len(buf)
                meter.sockets.add(id(sock))
            return buf

        ssl.SSLSocket.sendall = sendall
        ssl.SSLSocket.send = send
        ssl.SSLSocket.recv = recv
        return self

    def __exit__(self, *exc) -> None:
        ssl.SSLSocket.sendall = self._orig["sendall"]
        ssl.SSLSocket.send = self._orig["send"]
        ssl.SSLSocket.recv = self._orig["recv"]


# --------------------------------------------------------------------------
# A. 协议协商实测
# --------------------------------------------------------------------------
def alpn_probe(host: str, offer: list[str]) -> dict:
    ctx = ssl.create_default_context()
    ctx.set_alpn_protocols(offer)
    with socket.create_connection((host, 443), timeout=10) as raw:
        with ctx.wrap_socket(raw, server_hostname=host) as tls:
            return {
                "offered": offer,
                "selected": tls.selected_alpn_protocol(),
                "tls_version": tls.version(),
                "cipher": tls.cipher()[0],
            }


def httpx_probe(url: str, http2: bool) -> dict:
    out: dict = {"http2_enabled": http2}
    t0 = time.perf_counter()
    try:
        with httpx.Client(http2=http2, timeout=15.0, headers=UA) as c:
            r = c.get(url, params={"limit": 1, "offset": 0})
            out.update(
                ok=True,
                status_code=r.status_code,
                http_version=r.http_version,
                elapsed_ms=round((time.perf_counter() - t0) * 1000, 1),
                response_headers=dict(r.headers),
            )
    except Exception as exc:  # noqa: BLE001 —— 失败本身就是证据，原样记下来
        out.update(
            ok=False,
            error_type=f"{type(exc).__module__}.{type(exc).__name__}",
            error=str(exc),
            elapsed_ms=round((time.perf_counter() - t0) * 1000, 1),
        )
    return out


def curl_probe(url: str, flag: str) -> dict:
    cmd = ["curl", "-s", "-o", "/dev/null", flag,
           "-w", "http_version=%{http_version} http_code=%{http_code} time_total=%{time_total}",
           url]
    p = subprocess.run(cmd, capture_output=True, text=True)
    return {
        "cmd": " ".join(cmd),
        "exit_code": p.returncode,
        "stdout": p.stdout.strip(),
        "note": "curl 退出码 56 = Recv failure（连接被对端重置）；0 = 正常",
    }


def part_a() -> dict:
    print("== A. spa16 协议协商实测 ==")
    result = {
        "target": SPA16_API,
        "alpn": {
            "offer_h2_and_http11": alpn_probe(SPA16_HOST, ["h2", "http/1.1"]),
            "offer_http11_only": alpn_probe(SPA16_HOST, ["http/1.1"]),
            "offer_h2_only": alpn_probe(SPA16_HOST, ["h2"]),
        },
        "httpx": {
            "http2_on": httpx_probe(SPA16_API, http2=True),
            "http2_off": httpx_probe(SPA16_API, http2=False),
        },
        "curl": {
            "http2": curl_probe(f"{SPA16_API}?limit=1&offset=0", "--http2"),
            "http1_1": curl_probe(f"{SPA16_API}?limit=1&offset=0", "--http1.1"),
        },
    }
    for name, v in result["alpn"].items():
        print(f"  ALPN {name:<22} offered={v['offered']} -> selected={v['selected']!r}")
    h2, h1 = result["httpx"]["http2_on"], result["httpx"]["http2_off"]
    print(f"  httpx http2=True  -> ok={h2['ok']} {h2.get('http_version') or ''}")
    print(f"  httpx http2=False -> ok={h1['ok']} {h1.get('error_type', '')}: {h1.get('error', '')}")
    print(f"  curl --http2      -> {result['curl']['http2']['stdout']} (exit {result['curl']['http2']['exit_code']})")
    print(f"  curl --http1.1    -> {result['curl']['http1_1']['stdout']} (exit {result['curl']['http1_1']['exit_code']})")
    return result


# --------------------------------------------------------------------------
# B/C. 定量对比
# --------------------------------------------------------------------------
def run_sequential(base: str, offsets: list[int], limit: int, http2: bool, delay: float) -> dict:
    """同步串行 + 字节计数。measure 的是头部开销，不是并发能力。"""
    per_request: list[float] = []
    versions: set[str] = set()
    with SocketMeter() as meter:
        with httpx.Client(http2=http2, timeout=30.0, headers=UA) as client:
            client.get(base, params={"limit": limit, "offset": 0})  # 热身：握手成本不计入
            base_sent, base_recv = meter.sent, meter.recv
            for off in offsets:
                t = time.perf_counter()
                r = client.get(base, params={"limit": limit, "offset": off})
                r.raise_for_status()
                per_request.append((time.perf_counter() - t) * 1000)
                versions.add(r.http_version)
                time.sleep(delay)  # 礼貌间隔，不计入 active_s
            sent, recv = meter.sent - base_sent, meter.recv - base_recv
        conns = len(meter.sockets)
    return {
        "protocol": "h2" if http2 else "http/1.1",
        "mode": "sequential",
        "requests": len(offsets),
        "http_versions": sorted(versions),
        "active_s": round(sum(per_request) / 1000, 3),
        "tcp_connections": conns,
        "sent_bytes": sent,
        "sent_bytes_per_request": round(sent / len(offsets), 1),
        "recv_bytes": recv,
        "per_request_ms": {
            "min": round(min(per_request), 1),
            "median": round(statistics.median(per_request), 1),
            "max": round(max(per_request), 1),
        },
        "note": "sent/recv = 交给 TLS 加密前的 HTTP 报文字节；已扣除热身请求",
    }


async def _run_concurrent(base: str, offsets: list[int], limit: int,
                          http2: bool, workers: int) -> dict:
    limits = httpx.Limits(max_connections=workers, max_keepalive_connections=workers)
    per_request: list[float] = []
    versions: set[str] = set()
    async with httpx.AsyncClient(http2=http2, timeout=30.0, headers=UA, limits=limits) as client:
        await client.get(base, params={"limit": limit, "offset": 0})  # 热身

        async def one(off: int) -> None:
            t = time.perf_counter()
            r = await client.get(base, params={"limit": limit, "offset": off})
            r.raise_for_status()
            per_request.append((time.perf_counter() - t) * 1000)
            versions.add(r.http_version)

        t0 = time.perf_counter()
        await asyncio.gather(*(one(o) for o in offsets))
        wall = time.perf_counter() - t0
        pool = client._transport._pool  # noqa: SLF001 —— 只为数连接，不改行为
        conns = [str(c) for c in pool.connections]

    return {
        "protocol": "h2" if http2 else "http/1.1",
        "mode": f"concurrent(max_connections={workers})",
        "requests": len(offsets),
        "http_versions": sorted(versions),
        "wall_s": round(wall, 3),
        "tcp_connections": len(conns),
        "connection_repr": conns,
        "per_request_ms": {
            "min": round(min(per_request), 1),
            "median": round(statistics.median(per_request), 1),
            "max": round(max(per_request), 1),
        },
        "note": "connection_repr 里的 Request Count 就是该条 TCP 连接扛了多少个请求；含 1 次热身",
    }


def run_concurrent(*a, **kw) -> dict:
    return asyncio.run(_run_concurrent(*a, **kw))


def show(r: dict) -> None:
    t = r.get("wall_s", r.get("active_s"))
    extra = (f"sent={r['sent_bytes']}B ({r['sent_bytes_per_request']}B/req)  "
             if "sent_bytes" in r else "")
    print(f"  {r['protocol']:<9}{r['mode']:<34} t={t:>6.3f}s  conns={r['tcp_connections']}  "
          f"{extra}p50={r['per_request_ms']['median']}ms  {r['http_versions']}")


def part_b(n: int, workers: int, delay: float) -> dict:
    print(f"\n== B. 定量对比（对照站 {CONTROL_HOST}，每种配置 {n} 个请求）==")
    offsets = [i * CONTROL_LIMIT for i in range(n)]
    runs = []
    for http2 in (True, False):
        r = run_sequential(CONTROL_API, offsets, CONTROL_LIMIT, http2, delay)
        runs.append(r); show(r); time.sleep(1.0)
    for http2 in (True, False):
        r = run_concurrent(CONTROL_API, offsets, CONTROL_LIMIT, http2, workers)
        runs.append(r); show(r); time.sleep(1.0)
    return {"control_host": CONTROL_HOST, "endpoint": CONTROL_API, "runs": runs}


def part_c(n: int, workers: int, delay: float) -> dict:
    print(f"\n== C. spa16 本站：h2 串行 vs h2 并发（h1.1 不可用，见 A）==")
    offsets = [i * SPA16_LIMIT for i in range(n)]
    runs = []
    r = run_sequential(SPA16_API, offsets, SPA16_LIMIT, True, delay)
    runs.append(r); show(r); time.sleep(1.0)
    r = run_concurrent(SPA16_API, offsets, SPA16_LIMIT, True, workers)
    runs.append(r); show(r)
    return {"host": SPA16_HOST, "endpoint": SPA16_API, "runs": runs}


def main() -> None:
    p = argparse.ArgumentParser(description="spa16：HTTP/2 vs HTTP/1.1 实测")
    p.add_argument("--requests", type=int, default=15, help="每种配置打多少个请求")
    p.add_argument("--workers", type=int, default=5, help="并发配置的最大连接数/并发度")
    p.add_argument("--delay", type=float, default=0.1, help="串行模式每请求间隔（礼貌抓取，不计入耗时）")
    p.add_argument("--skip-control", action="store_true", help="跳过对照站定量对比")
    args = p.parse_args()

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).isoformat()
    env = {"captured_at": stamp, "client": f"httpx/{httpx.__version__}",
           "requests_per_config": args.requests, "workers": args.workers}

    a = part_a()
    (EVIDENCE / "protocol-negotiation.json").write_text(
        json.dumps({**env, **a}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    bench: dict = dict(env)
    bench["spa16_h2_only"] = part_c(args.requests, args.workers, args.delay)
    if not args.skip_control:
        bench["control"] = part_b(args.requests, args.workers, args.delay)
    (EVIDENCE / "h2-vs-h11-bench.json").write_text(
        json.dumps(bench, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"\n协议协商证据 -> {EVIDENCE / 'protocol-negotiation.json'}")
    print(f"对比数据     -> {EVIDENCE / 'h2-vs-h11-bench.json'}")


if __name__ == "__main__":
    main()
