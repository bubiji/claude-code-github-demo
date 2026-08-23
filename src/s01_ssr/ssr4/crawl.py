#!/usr/bin/env python3
"""ssr4 —— 每个响应固定 5 秒延迟：线程池并发 + 超时控制 + 先测清楚并发到底有没有用。

issue: #4 · 案例: ssr4 · 来源: https://ssr4.scrape.center

这站的 5 秒是服务端**故意注入的等待**，不是带宽瓶颈：瓶颈在「等」不在「算」，
所以线程池就够，不必上 asyncio。但并发能不能真的提速，取决于服务端愿不愿意
并行处理——所以本脚本先跑 `--bench` 实测，再决定开几路：

    python crawl.py --bench            # 只测并发梯度（1/2/4/8 路），不抓数据
    python crawl.py --bench --h2       # 同上，但走 HTTP/2 单连接多路复用做对照
    python crawl.py                    # 默认 4 路并发、60s 超时，抓全量
    python crawl.py --no-detail        # 只抓 10 个列表页（最快的完整字段方案）
    python crawl.py --timeout 3        # 复现「超时小于 5s 注入延迟」的翻车

超时有两层要考虑，只想着 5 秒会被坑：
    单请求耗时 ≈ 5s（服务端延迟） + 排队等待（前面还有几个请求没被处理完）
并发 N 路而服务端串行处理时，队尾那个请求要等 N × 5s，超时得按这个量级给。
"""
from __future__ import annotations

import argparse
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import add_common_args, build_summary, crawl, report, save_dataset  # noqa: E402

BASE = "https://ssr4.scrape.center"
NAME = "ssr4"
UA = "claude-code-github-demo/1.0 (scrape.center practice; issue #4)"

_local = threading.local()


def session_for(workers: int) -> requests.Session:
    """每线程一个 Session：Session 不保证线程安全，共用会在并发下出怪问题。"""
    s = getattr(_local, "session", None)
    if s is None:
        s = requests.Session()
        s.headers["User-Agent"] = UA
        adapter = HTTPAdapter(pool_connections=workers, pool_maxsize=workers)
        s.mount("https://", adapter)
        s.mount("http://", adapter)
        _local.session = s
    return s


def make_fetch(timeout: float, workers: int):
    def fetch(url: str) -> str:
        resp = session_for(workers).get(url, timeout=timeout)
        if resp.status_code == 500 and "/page/" in url:
            return ""  # 第 11 页 500 = 没有下一页
        resp.raise_for_status()
        return resp.text

    return fetch


def serial_baseline(n: int, timeout: float) -> float:
    """串行打 n 个请求，量出「没有排队时」的真实单请求耗时，作为串行对照的基准。

    不能拿并发过程里的均值当基准——那个数被排队等待撑大了（本次实测均值 21s，
    而真实单请求只要 6.5s），拿它算串行预估会把并发效果吹上天。
    也不能拿并发里最快的那个当基准——偶发的快响应（2s 级）又会把基准压得过低。
    """
    times = []
    s = requests.Session()
    s.headers["User-Agent"] = UA
    for i in range(1, n + 1):
        t0 = time.perf_counter()
        try:
            s.get(f"{BASE}/detail/{i}", timeout=timeout)
        except requests.exceptions.Timeout:
            # 基线只是为了给对比找个参照，超时了就明说测不出来，不要在这里崩掉——
            # 真正该报超时的地方是下面的抓取，那里的报错信息才带处置建议
            print(f"[{NAME}] 串行基线第 {i} 个请求超时（timeout={timeout}s），"
                  f"跳过基线测量。", file=sys.stderr)
            return 0.0
        times.append(time.perf_counter() - t0)
    avg = statistics.mean(times)
    print(f"[{NAME}] 串行基线：{n} 个请求，单个 {min(times):.2f}~{max(times):.2f}s，"
          f"均值 {avg:.2f}s")
    return avg


def bench(levels: list[int], timeout: float) -> list[dict]:
    """并发梯度实测：N 路同时打 N 个不同详情页，看墙钟时间是不是随 N 摊薄。

    若服务端并行，wall ≈ 5s 恒定；若服务端串行，wall ≈ N × 5s，并发白开。
    """
    rows = []
    for n in levels:
        urls = [f"{BASE}/detail/{i}" for i in range(1, n + 1)]

        def one(u: str) -> float:
            t = time.perf_counter()
            session_for(n).get(u, timeout=timeout)
            return time.perf_counter() - t

        t0 = time.perf_counter()
        with ThreadPoolExecutor(max_workers=n) as pool:
            per = list(pool.map(one, urls))
        wall = time.perf_counter() - t0
        rows.append({
            "workers": n, "requests": n,
            "wall_sec": round(wall, 2),
            "per_request_sec": [round(x, 2) for x in per],
            "throughput_sec_per_request": round(wall / n, 2),
        })
        print(f"[{NAME}] bench workers={n:>2}: 墙钟 {wall:6.2f}s，"
              f"折合 {wall / n:.2f}s/请求，单请求 "
              f"{min(per):.2f}~{max(per):.2f}s")
    return rows


def bench_h2(levels: list[int], timeout: float) -> list[dict]:
    """HTTP/2 单连接多路复用对照：N 个请求走同一条 TCP 连接的 N 个 stream。

    做这个对照是为了把「客户端连接数不够」这个嫌疑彻底排除掉：如果瓶颈在
    连接层，h2 多路复用会明显快过 N 条 HTTP/1.1 连接；如果两者一样慢，那就
    只剩服务端一次只处理一个请求这一种解释。
    """
    import asyncio

    import httpx

    async def run(n: int) -> tuple[float, list[float], str]:
        async with httpx.AsyncClient(http2=True, timeout=timeout,
                                     headers={"User-Agent": UA}) as client:
            # 先单发一个握手，避免把 TLS + h2 协商的时间算进并发那一轮；
            # 顺便记下实际协商到的协议——服务端不支持 h2 时会静默退回 HTTP/1.1，
            # 那样这组对照的前提就不成立了，必须如实写进结果而不是假装测了 h2。
            warmup = await client.get(f"{BASE}/page/1")
            proto = warmup.http_version

            async def one(u: str) -> float:
                t = time.perf_counter()
                await client.get(u)
                return time.perf_counter() - t

            urls = [f"{BASE}/detail/{i}" for i in range(1, n + 1)]
            t0 = time.perf_counter()
            per = await asyncio.gather(*(one(u) for u in urls))
            return time.perf_counter() - t0, list(per), proto

    rows = []
    for n in levels:
        wall, per, proto = asyncio.run(run(n))
        rows.append({
            "protocol": f"{proto} (single connection, multiplexed)",
            "workers": n, "requests": n,
            "wall_sec": round(wall, 2),
            "per_request_sec": [round(x, 2) for x in per],
            "throughput_sec_per_request": round(wall / n, 2),
        })
        print(f"[{NAME}] bench/{proto} streams={n:>2}: 墙钟 {wall:6.2f}s，"
              f"折合 {wall / n:.2f}s/请求，单请求 {min(per):.2f}~{max(per):.2f}s")
    return rows


def main() -> int:
    ap = add_common_args(argparse.ArgumentParser(description=__doc__))
    ap.set_defaults(workers=4, delay=0.0, timeout=60.0)
    ap.add_argument("--bench", action="store_true", help="只跑并发梯度实测，不抓数据")
    ap.add_argument("--bench-levels", default="1,2,4,8", help="梯度，逗号分隔")
    ap.add_argument("--h2", action="store_true",
                    help="--bench 时额外跑 HTTP/2 单连接多路复用对照")
    ap.add_argument("--baseline", type=int, default=3,
                    help="抓取前串行打 N 个请求测无排队时的单请求耗时（0 = 跳过）")
    args = ap.parse_args()

    levels = [int(x) for x in args.bench_levels.split(",") if x.strip()]

    if args.bench:
        rows = bench(levels, args.timeout)
        h2_rows = bench_h2(levels, args.timeout) if args.h2 else None
        out = Path(args.out) if args.out else Path(__file__).resolve().parent / "data"
        out.mkdir(parents=True, exist_ok=True)
        import json
        payload = {"case": NAME, "issue": 4, "base": BASE,
                   # 落盘时刻（= 本轮最后一个档位跑完的时间），用来区分不同轮次：
                   # 这站的并发行为在两轮之间会变（见 README），不标时间就没法对账
                   "written_at": time.strftime("%Y-%m-%d %H:%M:%S%z"),
                   "levels": rows}
        if h2_rows:
            payload["levels_http2"] = h2_rows
        (out / "bench.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"[{NAME}] 梯度结果写入 {out / 'bench.json'}")
        return 0

    if args.timeout <= 5:
        print(f"[{NAME}] 警告：timeout={args.timeout}s 不大于服务端注入的 5s 延迟，"
              f"请求几乎必然超时。", file=sys.stderr)
    elif args.timeout < args.workers * 6:
        print(f"[{NAME}] 警告：workers={args.workers} 时队尾请求可能要等 "
              f"{args.workers * 5}s 以上，timeout={args.timeout}s 偏紧。", file=sys.stderr)

    base_avg = serial_baseline(args.baseline, args.timeout) if args.baseline else None

    print(f"[{NAME}] {BASE} · workers={args.workers} timeout={args.timeout}s "
          f"delay={args.delay}s detail={'off' if args.no_detail else 'on'}")
    t0 = time.perf_counter()
    try:
        records, stats = crawl(
            BASE, make_fetch(args.timeout, args.workers),
            workers=args.workers, delay=args.delay, with_detail=not args.no_detail,
        )
    except requests.exceptions.Timeout as exc:
        # 列表页超时不当成「翻到头了」——那会静默少抓一半数据还报成功
        print(f"[{NAME}] 列表页请求超时（timeout={args.timeout}s）：{exc}\n"
              f"[{NAME}] 这站每个响应固定慢 5s，超时必须显著大于 5s；"
              f"并发 N 路时还要再算上排队。", file=sys.stderr)
        return 2
    wall = time.perf_counter() - t0

    # 串行基线取抓取前实测的无排队单请求耗时；没测就退回并发均值（会低估并发收益，注明来源）
    per_req = base_avg if base_avg else stats.avg_request
    serial_est = per_req * stats.requests
    speedup = serial_est / wall if wall else 0

    outdir = Path(args.out) if args.out else Path(__file__).resolve().parent / "data"
    summary = build_summary(records, stats, {
        "case": NAME, "issue": 4, "base": BASE,
        "concurrency": {
            "workers": args.workers,
            "timeout_sec": args.timeout,
            "serial_per_request_sec": round(per_req, 2),
            "serial_per_request_source": (
                f"抓取前串行实测 {args.baseline} 个请求的均值" if base_avg
                else "并发过程中各请求耗时均值（含排队，会低估并发收益）"),
            "fastest_request_sec": round(min(stats.request_times), 2) if stats.request_times else None,
            "slowest_request_sec": round(max(stats.request_times), 2) if stats.request_times else None,
            "concurrent_throughput_sec_per_request": round(wall / stats.requests, 2) if stats.requests else None,
            "serial_estimate_sec": round(serial_est, 1),
            "actual_wall_sec": round(wall, 1),
            "speedup": round(speedup, 2),
            "note": "串行预估 = 无排队单请求耗时 × 总请求数",
        },
        "note": "案例原文：每个响应增加了 5 秒延迟；瓶颈是等待，线程池并发即可",
    })
    # ssr1~ssr4 是同一套站的数据，CSV 只在 ssr1 出一份做演示，这里不再塞第二份同样的表
    saved = save_dataset(outdir, NAME, records, summary, write_csv=False)
    report(NAME, records, stats, saved, workers=args.workers)
    print(f"  并发效果   : 串行预计 {serial_est:.0f}s（{stats.requests} 请求 × "
          f"无排队 {per_req:.2f}s） → 实际 {wall:.0f}s，加速 {speedup:.2f}×"
          f"（workers={args.workers}，折合 {wall / stats.requests:.2f}s/请求）")
    return 1 if stats.failures else 0


if __name__ == "__main__":
    sys.exit(main())
