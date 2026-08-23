#!/usr/bin/env python3
"""spa14 —— 数值型 WASM 逆向（issue #14）

站点：https://spa14.scrape.center
列表接口 /api/movie/ 需要 query 参数 sign，由 /js/Wasm.wasm 的导出函数
encrypt(i32 offset, i32 timestamp) -> i32 生成，且有时间限制。

两条路线都实现，并在每次运行时互相对账：
  A. wasm 路线：wasmtime 直接加载 .wasm，调 encrypt 导出函数（无需任何 import）
  B. 纯 Python 路线：按反汇编出来的 5 条指令复现 sign = offset + trunc(ts/3) + 16358

用法：
  python spa14.py                 # 抓全量列表，落 data/
  python spa14.py --probe         # 只做签名有效期探测
  python spa14.py --twice --gap 200   # 间隔 gap 秒跑两轮，证明参数是现算的
"""
from __future__ import annotations

import argparse
import json
import pathlib
import time
from datetime import datetime, timezone

import requests
from wasmtime import Engine, Instance, Module, Store

BASE = "https://spa14.scrape.center"
API = f"{BASE}/api/movie/"
WASM_URL = f"{BASE}/js/Wasm.wasm"

HERE = pathlib.Path(__file__).resolve().parent
WASM_PATH = HERE / "evidence" / "Wasm.wasm"
DATA_DIR = HERE / "data"

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"
PAUSE = 1.0  # 礼貌抓取：每次请求之间至少歇 1 秒


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


# --------------------------------------------------------------------------
# A. wasm 路线
# --------------------------------------------------------------------------
class WasmSigner:
    """直接加载 spa14 的 Wasm.wasm 并调用导出函数 encrypt。

    spa14 的模块 **没有任何 import**（见 evidence/exports.txt），所以
    Instance(store, module, []) 就能起来，不需要 WASI，也不需要 env 桩。
    encrypt 的两个入参和返回值全是普通 i32 数值 —— 这就是「数值型」：
    完全不碰线性内存，没有指针、没有 stackAlloc、没有编解码。
    """

    def __init__(self, wasm_path: pathlib.Path = WASM_PATH):
        engine = Engine()
        self.store = Store(engine)
        module = Module(engine, wasm_path.read_bytes())
        instance = Instance(self.store, module, [])  # 空 import 列表
        exports = instance.exports(self.store)
        init = exports.get("_initialize")
        if init is not None:
            init(self.store)
        self._encrypt = exports["encrypt"]

    def sign(self, offset: int, ts: int) -> int:
        return self._encrypt(self.store, offset, ts)


# --------------------------------------------------------------------------
# B. 纯 Python 路线（按 wat 复现）
# --------------------------------------------------------------------------
#   (func (;4;) (type 4) (param i32 i32) (result i32)
#     local.get 0        ;; offset
#     local.get 1        ;; ts
#     i32.const 3
#     i32.div_s          ;; 有符号除法，向零截断
#     i32.add
#     i32.const 16358
#     i32.add)
def sign_pure(offset: int, ts: int) -> int:
    q = abs(ts) // 3
    if ts < 0:
        q = -q  # i32.div_s 向零截断，Python // 向下取整，负数要修正
    return offset + q + 16358


# --------------------------------------------------------------------------
def fetch_page(sess: requests.Session, signer: WasmSigner, offset: int, limit: int = 10):
    ts = int(round(time.time()))
    sign_wasm = signer.sign(offset, ts)
    sign_py = sign_pure(offset, ts)
    if sign_wasm != sign_py:
        raise SystemExit(f"对账失败：wasm={sign_wasm} pure={sign_py} (offset={offset}, ts={ts})")
    r = sess.get(API, params={"limit": limit, "offset": offset, "sign": sign_wasm}, timeout=20)
    return ts, sign_wasm, r


def crawl(sess: requests.Session, signer: WasmSigner, limit: int = 10, log: list | None = None):
    movies, offset, total = [], 0, None
    while True:
        ts, sign, r = fetch_page(sess, signer, offset, limit)
        line = f"[{now_iso()}] offset={offset:<4} ts={ts} sign={sign} -> HTTP {r.status_code}"
        print(line)
        if log is not None:
            log.append(line)
        r.raise_for_status()
        body = r.json()
        total = body["count"]
        movies.extend(body["results"])
        offset += limit
        if offset >= total:
            break
        time.sleep(PAUSE)
    return total, movies


def probe_expiry(sess: requests.Session, signer: WasmSigner) -> list[dict]:
    """探测 sign 的有效期：用「过去 / 未来」的时间戳算 sign，看服务端认不认。"""
    out = []
    base = int(round(time.time()))
    for age in (0, 30, 60, 120, 150, 180, 300, 600, 3600, -60, -150, -300):
        ts = base - age
        sign = signer.sign(0, ts)
        r = sess.get(API, params={"limit": 1, "offset": 0, "sign": sign}, timeout=20)
        rec = {"age_seconds": age, "ts": ts, "sign": sign, "http": r.status_code}
        out.append(rec)
        print(f"[{now_iso()}] age={age:>5}s ts={ts} sign={sign} -> HTTP {r.status_code}")
        time.sleep(PAUSE)
    return out


def probe_offset_binding(sess: requests.Session, signer: WasmSigner) -> list[dict]:
    """sign 里含 offset，验证服务端是否真的校验 offset 与 sign 的一致性。

    服务端只能从 sign 反解出 ts ≈ (sign - 16358 - offset) * 3。offset 少算 k，
    反解出的 ts 就偏移 3k 秒 —— 所以「offset 对不对」并不是单独校验的，
    而是被折算成时间偏移后由有效期窗口来兜。小幅错位落在窗口内照样 200，
    大幅错位把 ts 顶出窗口才 401。
    """
    out = []
    ts = int(round(time.time()))
    for real_off, sign_off in ((10, 10), (10, 0), (0, 10), (100, 0), (0, 100)):
        sign = signer.sign(sign_off, ts)
        r = sess.get(API, params={"limit": 10, "offset": real_off, "sign": sign}, timeout=20)
        rec = {"request_offset": real_off, "sign_computed_for_offset": sign_off,
               "ts": ts, "sign": sign, "http": r.status_code}
        out.append(rec)
        print(f"[{now_iso()}] offset={real_off} sign_for_offset={sign_off} -> HTTP {r.status_code}")
        time.sleep(PAUSE)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true", help="只跑有效期 / offset 绑定探测")
    ap.add_argument("--twice", action="store_true", help="间隔 --gap 秒跑两轮抓取")
    ap.add_argument("--gap", type=int, default=200, help="两轮之间的间隔秒数（默认 200，超过实测有效期）")
    ap.add_argument("--limit", type=int, default=10)
    args = ap.parse_args()

    DATA_DIR.mkdir(exist_ok=True)
    sess = requests.Session()
    sess.headers.update({"User-Agent": UA, "Accept": "application/json"})
    signer = WasmSigner()

    if args.probe:
        result = {
            "generated_at": now_iso(),
            "expiry_probe": probe_expiry(sess, signer),
            "offset_binding_probe": probe_offset_binding(sess, signer),
        }
        p = DATA_DIR / "spa14_probe.json"
        p.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n已写入 {p}")
        return

    if args.twice:
        log: list[str] = []
        runs = []
        for i in (1, 2):
            if i == 2:
                stale = runs[0]
                print(f"\n--- 等待 {args.gap}s（超过实测有效期）---")
                time.sleep(args.gap)
                # 对照组：拿第一轮的旧 sign 原样再请求一次，应该 401
                r = sess.get(API, params={"limit": 1, "offset": 0, "sign": stale["first_sign"]}, timeout=20)
                line = (f"[{now_iso()}] 对照组：复用第 1 轮的旧 sign={stale['first_sign']} "
                        f"(ts={stale['first_ts']}) -> HTTP {r.status_code}")
                print(line)
                log.append(line)
                stale["replay_old_sign_http"] = r.status_code
                time.sleep(PAUSE)
            started = now_iso()
            ts0 = int(round(time.time()))
            sign0 = signer.sign(0, ts0)
            total, movies = crawl(sess, signer, args.limit, log)
            runs.append({"run": i, "started_at": started, "first_ts": ts0,
                         "first_sign": sign0, "count": total, "fetched": len(movies)})
            print(f"第 {i} 轮：count={total} 实际取到 {len(movies)} 条")
        out = {"generated_at": now_iso(), "gap_seconds": args.gap, "runs": runs, "log": log}
        p = DATA_DIR / "spa14_twice.json"
        p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n已写入 {p}")
        return

    log: list[str] = []
    total, movies = crawl(sess, signer, args.limit, log)
    payload = {
        "source": API,
        "generated_at": now_iso(),
        "count_reported_by_api": total,
        "count_fetched": len(movies),
        "sign_algorithm": "encrypt(offset, ts) = offset + trunc(ts/3) + 16358  (WASM func 4)",
        "results": movies,
    }
    p = DATA_DIR / "spa14_movies.json"
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (DATA_DIR / "spa14_run.log").write_text("\n".join(log) + "\n", encoding="utf-8")
    print(f"\ncount={total} 实际取到 {len(movies)} 条 -> {p}")


if __name__ == "__main__":
    main()
