#!/usr/bin/env python3
"""spa15 —— 字符串型 WASM 逆向（issue #14）

站点：https://spa15.scrape.center
列表接口 /api/movie/ 需要 query 参数 token，由 /js/Wasm.wasm 的导出函数
encrypt(i32, i32) -> i32 生成，且有时间限制。

注意：encrypt 的签名跟 spa14 一字不差（(i32,i32)->i32），但这里三个 i32 全是
**线性内存里的指针**。浏览器侧走的是 Emscripten 的 ccall：

    this.$wasm.ccall("encrypt","string",["string","string"],
                     [this.$store.state.url.index,
                      Math.round((new Date).getTime()/1e3).toString()])

所以 Python 侧必须自己把 ccall 那一套内存管理做出来：
    stackSave -> stackAlloc + 写 UTF-8 字节 -> 传指针 -> 读回 NUL 结尾字符串 -> stackRestore

两条路线都实现，并在每次运行时互相对账：
  A. wasm 路线：wasmtime 加载 .wasm，自己管线性内存调 encrypt
  B. 纯 Python 路线：token = base64(sha1_hex(f"{url},{ts}") + "," + ts)

用法：
  python spa15.py                     # 抓全量列表，落 data/
  python spa15.py --probe             # 只做 token 有效期 / 绑定探测
  python spa15.py --twice --gap 200   # 间隔 gap 秒跑两轮，证明参数是现算的
  python spa15.py --memdump           # 打印一次内存读写全过程（教学用）
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import pathlib
import time
from datetime import datetime, timezone

import requests
from wasmtime import Engine, Func, FuncType, Instance, Module, Store, ValType

BASE = "https://spa15.scrape.center"
API_PATH = "/api/movie"          # 就是 $store.state.url.index，签名用的正是这个裸路径
API = f"{BASE}{API_PATH}/"
WASM_URL = f"{BASE}/js/Wasm.wasm"

HERE = pathlib.Path(__file__).resolve().parent
WASM_PATH = HERE / "evidence" / "Wasm.wasm"
DATA_DIR = HERE / "data"

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"
PAUSE = 1.0


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


# --------------------------------------------------------------------------
# A. wasm 路线：自己实现 Emscripten ccall 的内存管理
# --------------------------------------------------------------------------
class WasmStringSigner:
    """加载 spa15 的 Wasm.wasm，按 ccall 的语义传字符串、读字符串。

    与 spa14 的三点差别（这就是「字符串型」的全部成本）：

    1. 有 import：wasi_snapshot_preview1.proc_exit。wasmtime 按位置顺序传 import，
       必须给一个签名匹配的桩函数，否则 Instance() 直接报错。
    2. 模块没有导出 malloc/free，只有 stackSave / stackAlloc / stackRestore。
       所以字符串只能放在 wasm 的**影子栈**上，用完靠 stackRestore 整体回卷。
    3. 入参和返回值都是 i32 指针，指向 memory 这块线性内存。写进去要自己做
       UTF-8 编码并补 \\0，读回来要自己扫到第一个 \\0 再 decode。
    """

    def __init__(self, wasm_path: pathlib.Path = WASM_PATH, verbose: bool = False):
        engine = Engine()
        self.store = Store(engine)
        module = Module(engine, wasm_path.read_bytes())
        self.verbose = verbose

        # ---- 1. 补上 WASI import（只要签名对，实现可以是空的）----
        proc_exit = Func(self.store, FuncType([ValType.i32()], []), lambda code: None)
        # wasmtime 的 import 是按 module.imports 的顺序位置传入的
        instance = Instance(self.store, module, [proc_exit])

        exp = instance.exports(self.store)
        self.memory = exp["memory"]
        init = exp.get("_initialize")
        if init is not None:
            init(self.store)
        self._encrypt = exp["encrypt"]
        self._stack_save = exp["stackSave"]
        self._stack_alloc = exp["stackAlloc"]
        self._stack_restore = exp["stackRestore"]

    # ---- 2. 往线性内存里写一个 NUL 结尾的 UTF-8 字符串，返回指针 ----
    def _write_cstring(self, s: str) -> int:
        raw = s.encode("utf-8") + b"\x00"
        ptr = self._stack_alloc(self.store, len(raw))
        self.memory.write(self.store, raw, ptr)
        if self.verbose:
            print(f"    stackAlloc({len(raw):>3}) -> ptr={ptr}   写入 {raw!r}")
        return ptr

    # ---- 3. 从线性内存里读一个 NUL 结尾的 UTF-8 字符串 ----
    def _read_cstring(self, ptr: int, chunk: int = 256) -> str:
        buf = bytearray()
        cur = ptr
        size = self.memory.data_len(self.store)
        while True:
            end = min(cur + chunk, size)
            piece = self.memory.read(self.store, cur, end)
            nul = piece.find(b"\x00")
            if nul >= 0:
                buf += piece[:nul]
                break
            buf += piece
            cur = end
            if cur >= size:
                raise RuntimeError("读到内存末尾也没遇到 NUL，指针或长度不对")
        if self.verbose:
            print(f"    UTF8ToString(ptr={ptr}) 扫到 NUL，长度 {len(buf)} 字节")
        return buf.decode("utf-8")

    # ---- 4. 完整的一次 ccall("encrypt","string",["string","string"], [...]) ----
    def token(self, url: str, ts: str) -> str:
        sp = self._stack_save(self.store)          # 记下栈指针
        if self.verbose:
            print(f"  stackSave() -> {sp}")
        try:
            p_url = self._write_cstring(url)
            p_ts = self._write_cstring(ts)
            p_ret = self._encrypt(self.store, p_url, p_ts)
            if self.verbose:
                print(f"    encrypt({p_url}, {p_ts}) -> ptr={p_ret}")
            return self._read_cstring(p_ret)
        finally:
            self._stack_restore(self.store, sp)    # 整体回卷，等价于释放
            if self.verbose:
                print(f"  stackRestore({sp})")


# --------------------------------------------------------------------------
# B. 纯 Python 路线（由实测反推并逐点验证）
# --------------------------------------------------------------------------
def token_pure(url: str, ts: str) -> str:
    digest = hashlib.sha1(f"{url},{ts}".encode()).hexdigest()
    return base64.b64encode(f"{digest},{ts}".encode()).decode()


# --------------------------------------------------------------------------
def make_token(signer: WasmStringSigner, ts: int | None = None) -> tuple[int, str]:
    ts = int(round(time.time())) if ts is None else ts
    tok_wasm = signer.token(API_PATH, str(ts))
    tok_py = token_pure(API_PATH, str(ts))
    if tok_wasm != tok_py:
        raise SystemExit(f"对账失败：\n  wasm={tok_wasm}\n  pure={tok_py}")
    return ts, tok_wasm


def crawl(sess: requests.Session, signer: WasmStringSigner, limit: int = 10, log: list | None = None):
    movies, offset, total = [], 0, None
    while True:
        ts, token = make_token(signer)
        r = sess.get(API, params={"limit": limit, "offset": offset, "token": token}, timeout=20)
        line = f"[{now_iso()}] offset={offset:<4} ts={ts} token={token} -> HTTP {r.status_code}"
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


def probe(sess: requests.Session, signer: WasmStringSigner) -> dict:
    base_ts = int(round(time.time()))
    expiry = []
    for age in (0, 30, 60, 120, 150, 180, 300, 600, 3600, -60, -150, -300):
        ts, token = make_token(signer, base_ts - age)
        r = sess.get(API, params={"limit": 1, "offset": 0, "token": token}, timeout=20)
        expiry.append({"age_seconds": age, "ts": ts, "token": token, "http": r.status_code})
        print(f"[{now_iso()}] age={age:>5}s ts={ts} -> HTTP {r.status_code}")
        time.sleep(PAUSE)

    # token 里不含 offset，验证同一个 token 能否用于任意 offset
    ts, token = make_token(signer)
    offsets = []
    for off in (0, 30, 90):
        r = sess.get(API, params={"limit": 10, "offset": off, "token": token}, timeout=20)
        offsets.append({"offset": off, "http": r.status_code})
        print(f"[{now_iso()}] 同一 token 用于 offset={off} -> HTTP {r.status_code}")
        time.sleep(PAUSE)

    # 签名串里的 url 是否真的参与校验
    wrong = signer.token("/api/movie/", str(int(round(time.time()))))
    r = sess.get(API, params={"limit": 1, "offset": 0, "token": wrong}, timeout=20)
    print(f"[{now_iso()}] 故意用 '/api/movie/'（多一个斜杠）签名 -> HTTP {r.status_code}")
    url_check = {"signed_url": "/api/movie/", "http": r.status_code}

    return {"generated_at": now_iso(), "expiry_probe": expiry,
            "offset_independence": offsets, "wrong_url_probe": url_check}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--twice", action="store_true")
    ap.add_argument("--gap", type=int, default=200)
    ap.add_argument("--memdump", action="store_true", help="打印一次完整的内存读写过程")
    ap.add_argument("--limit", type=int, default=10)
    args = ap.parse_args()

    DATA_DIR.mkdir(exist_ok=True)
    sess = requests.Session()
    sess.headers.update({"User-Agent": UA, "Accept": "application/json"})

    if args.memdump:
        signer = WasmStringSigner(verbose=True)
        ts = int(round(time.time()))
        print(f"ccall(\"encrypt\",\"string\",[\"string\",\"string\"],[{API_PATH!r}, {str(ts)!r}])")
        tok = signer.token(API_PATH, str(ts))
        print(f"  => token = {tok}")
        print(f"  base64 解开 = {base64.b64decode(tok).decode()}")
        print(f"  纯 Python 复现 = {token_pure(API_PATH, str(ts))}")
        print(f"  一致：{tok == token_pure(API_PATH, str(ts))}")
        return

    signer = WasmStringSigner()

    if args.probe:
        result = probe(sess, signer)
        p = DATA_DIR / "spa15_probe.json"
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
                r = sess.get(API, params={"limit": 1, "offset": 0, "token": stale["first_token"]}, timeout=20)
                line = (f"[{now_iso()}] 对照组：复用第 1 轮的旧 token（ts={stale['first_ts']}）"
                        f" -> HTTP {r.status_code}")
                print(line)
                log.append(line)
                stale["replay_old_token_http"] = r.status_code
                time.sleep(PAUSE)
            started = now_iso()
            ts0, tok0 = make_token(signer)
            total, movies = crawl(sess, signer, args.limit, log)
            runs.append({"run": i, "started_at": started, "first_ts": ts0,
                         "first_token": tok0, "count": total, "fetched": len(movies)})
            print(f"第 {i} 轮：count={total} 实际取到 {len(movies)} 条")
        out = {"generated_at": now_iso(), "gap_seconds": args.gap, "runs": runs, "log": log}
        p = DATA_DIR / "spa15_twice.json"
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
        "token_algorithm": 'base64(sha1_hex("/api/movie,<ts>") + "," + <ts>)  (WASM func 24)',
        "results": movies,
    }
    p = DATA_DIR / "spa15_movies.json"
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (DATA_DIR / "spa15_run.log").write_text("\n".join(log) + "\n", encoding="utf-8")
    print(f"\ncount={total} 实际取到 {len(movies)} 条 -> {p}")


if __name__ == "__main__":
    main()
