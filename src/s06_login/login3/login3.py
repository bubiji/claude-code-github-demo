#!/usr/bin/env python3
"""login3 —— JWT 模拟登录、过期判定与刷新（issue #9）。

来源: https://login3.scrape.center
案例描述（逐字引自 scrape.center）:
    对接 JWT 模拟登录方式，适合用作 JWT 模拟登录练习。

用法:
    python login3.py login                  # 取 token，落盘 data/jwt.json
    python login3.py inspect                # 拆 header/payload/signature，dump exp 等字段
    python login3.py refresh                # 主动换新 token
    python login3.py expiry                 # 过期/失效行为实测（无 token / 篡改 / 错前缀 / refresh 链）
    python login3.py fetch --pages 3        # 带 JWT 抓书目；**按 exp 自动刷新**
    python login3.py fetch --pages 3 --refresh-margin 999999   # 强制走刷新分支（实跑验证）
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE = "https://login3.scrape.center"
HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
TOKEN_FILE = DATA / "jwt.json"                # 真实 token，已被 .gitignore 排除


def rel(p: Path) -> str:
    """打印相对路径——运行日志要进 public 仓库，不外发本机绝对路径。"""
    return str(p.relative_to(HERE))

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
DELAY = 1.0                                   # 礼貌抓取
DEFAULT_MARGIN = 300                          # exp 剩余不足 5 分钟就刷新


def mask(v: str, head: int = 8, tail: int = 6) -> str:
    """public 仓库：token 一律脱敏后才允许打印/落盘。"""
    if not v:
        return v
    if len(v) <= head + tail:
        return v[:2] + "..."
    return f"{v[:head]}...{v[-tail:]}"


def mask_jwt(tok: str) -> str:
    """JWT 按三段分别脱敏，保留结构可读性。"""
    parts = tok.split(".")
    if len(parts) != 3:
        return mask(tok)
    return ".".join(mask(p, 6, 4) for p in parts)


# --------------------------------------------------------------------------
# JWT 拆解
# --------------------------------------------------------------------------
def b64url_decode(seg: str) -> bytes:
    """JWT 用的是 base64url **无补位**，要自己补 '='。"""
    return base64.urlsafe_b64decode(seg + "=" * (-len(seg) % 4))


def decode_jwt(tok: str) -> dict:
    """本地拆 JWT——只解码，不验签（签名密钥在服务端，客户端本来就验不了）。"""
    h, p, s = tok.split(".")
    return {
        "header": json.loads(b64url_decode(h)),
        "payload": json.loads(b64url_decode(p)),
        "signature_b64url": s,
        "signature_bytes": len(b64url_decode(s)),
        "segments_len": [len(h), len(p), len(s)],
    }


def exp_info(payload: dict) -> dict:
    now = int(time.time())
    exp = payload.get("exp")
    orig = payload.get("orig_iat")
    return {
        "now_epoch": now,
        "exp_epoch": exp,
        "exp_utc": datetime.fromtimestamp(exp, timezone.utc).isoformat(timespec="seconds") if exp else None,
        "orig_iat_epoch": orig,
        "orig_iat_utc": datetime.fromtimestamp(orig, timezone.utc).isoformat(timespec="seconds") if orig else None,
        "ttl_seconds": (exp - now) if exp else None,
        "ttl_human": f"{(exp - now) / 3600:.2f} 小时" if exp else None,
        "lifetime_seconds": (exp - orig) if exp and orig else None,
        "expired": bool(exp and exp <= now),
    }


# --------------------------------------------------------------------------
# 持久化
# --------------------------------------------------------------------------
def save_token(tok: str, how: str) -> Path:
    DATA.mkdir(parents=True, exist_ok=True)
    d = decode_jwt(tok)
    TOKEN_FILE.write_text(json.dumps({
        "token": tok,
        "obtained_how": how,
        "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "payload": d["payload"],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return TOKEN_FILE


def load_token() -> dict:
    if not TOKEN_FILE.exists():
        raise SystemExit(f"[error] 没有 token 文件：{rel(TOKEN_FILE)}\n        先跑 `python login3.py login`")
    return json.loads(TOKEN_FILE.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# 端点
# --------------------------------------------------------------------------
def api_login(username: str, password: str) -> str:
    r = requests.post(f"{BASE}/api/login", json={"username": username, "password": password},
                      headers={"User-Agent": UA}, timeout=30)
    r.raise_for_status()
    return r.json()["token"]


def api_refresh(tok: str) -> tuple[int, str | None, str]:
    """djangorestframework-jwt 的 refresh_jwt_token：拿旧 token 换新 token。

    注意它**不是**另发一个 refresh_token，而是拿当前 token 续期；
    续出来的新 token 里 orig_iat 原样不动 —— 这就是刷新窗口的锚点。
    """
    r = requests.post(f"{BASE}/api/refresh", json={"token": tok},
                      headers={"User-Agent": UA}, timeout=30)
    body = r.text
    return r.status_code, (r.json().get("token") if r.ok else None), body[:300]


def api_get(path: str, tok: str | None, prefix: str = "jwt") -> requests.Response:
    h = {"User-Agent": UA}
    if tok:
        h["Authorization"] = f"{prefix} {tok}"
    return requests.get(BASE + path, headers=h, timeout=30)


# --------------------------------------------------------------------------
# 命令
# --------------------------------------------------------------------------
def cmd_login(u: str, p: str) -> int:
    tok = api_login(u, p)
    d = decode_jwt(tok)
    print(f"[login] POST /api/login -> 200")
    print(f"[login] token（脱敏）= {mask_jwt(tok)}")
    print(f"[login] header  = {d['header']}")
    print(f"[login] payload = {d['payload']}")
    e = exp_info(d["payload"])
    print(f"[login] exp={e['exp_utc']}  orig_iat={e['orig_iat_utc']}  "
          f"寿命={e['lifetime_seconds']}s（{e['lifetime_seconds'] / 3600:.0f} 小时）  剩余={e['ttl_human']}")
    print(f"[login] token 已落盘 -> {rel(save_token(tok, 'POST /api/login'))}")
    return 0


def cmd_inspect() -> int:
    blob = load_token()
    tok = blob["token"]
    d = decode_jwt(tok)
    e = exp_info(d["payload"])
    print(f"[inspect] 原始 token（脱敏三段）: {mask_jwt(tok)}")
    print(f"[inspect] 三段长度 header/payload/signature = {d['segments_len']}")
    print(f"[inspect] ① header    : {json.dumps(d['header'], ensure_ascii=False)}")
    print(f"[inspect] ② payload   : {json.dumps(d['payload'], ensure_ascii=False)}")
    print(f"[inspect] ③ signature : {mask(d['signature_b64url'], 8, 6)}  "
          f"（{d['signature_bytes']} 字节，HS256 = HMAC-SHA256，正好 32 字节）")
    print(f"[inspect] exp      = {e['exp_epoch']}  {e['exp_utc']}")
    print(f"[inspect] orig_iat = {e['orig_iat_epoch']}  {e['orig_iat_utc']}")
    print(f"[inspect] 单次寿命 = {e['lifetime_seconds']}s；当前剩余 = {e['ttl_seconds']}s（{e['ttl_human']}）；"
          f"已过期 = {e['expired']}")
    out = DATA / "login3_jwt_dump.json"
    out.write_text(json.dumps({
        "source": BASE,
        "note": "public 仓库：token 与签名均为脱敏样本，仅保留结构与前后几位",
        "token_masked": mask_jwt(tok),
        "header": d["header"],
        "payload": d["payload"],
        "signature_masked": mask(d["signature_b64url"], 8, 6),
        "signature_bytes": d["signature_bytes"],
        "segments_len": d["segments_len"],
        "exp": e,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[inspect] 脱敏 dump -> {rel(out)}")
    return 0


def cmd_refresh() -> int:
    blob = load_token()
    old = blob["token"]
    old_p = decode_jwt(old)["payload"]
    st, new, body = api_refresh(old)
    print(f"[refresh] POST /api/refresh -> {st}")
    if not new:
        print(f"[refresh] 失败: {body}")
        return 1
    new_p = decode_jwt(new)["payload"]
    print(f"[refresh] 旧 token {mask_jwt(old)}  exp={old_p['exp']}")
    print(f"[refresh] 新 token {mask_jwt(new)}  exp={new_p['exp']}")
    print(f"[refresh] token 变了: {new != old}；exp 前移 {new_p['exp'] - old_p['exp']}s；"
          f"orig_iat 保持不变: {new_p['orig_iat'] == old_p['orig_iat']}（刷新窗口锚点）")
    print(f"[refresh] 已落盘 -> {rel(save_token(new, 'POST /api/refresh'))}")
    return 0


def ensure_fresh(tok: str, margin: int) -> tuple[str, bool, dict]:
    """过期刷新的核心：按 payload.exp 判断，剩余不足 margin 秒就调 /api/refresh。

    margin 调得极大（如 999999）就能**在真实服务器上强制走刷新分支**，
    不必等 12 小时才验证这段代码跑不跑得通。
    """
    p = decode_jwt(tok)["payload"]
    ttl = p["exp"] - int(time.time())
    log = {"ttl_before": ttl, "margin": margin, "refreshed": False}
    if ttl > margin:
        print(f"[auth] token 剩余 {ttl}s > 阈值 {margin}s，无需刷新")
        return tok, False, log
    print(f"[auth] token 剩余 {ttl}s <= 阈值 {margin}s → 触发刷新")
    st, new, body = api_refresh(tok)
    if not new:
        print(f"[auth] 刷新失败({st}): {body} → 回退为重新登录")
        log.update(refresh_status=st, refresh_body=body, fallback="re-login")
        new = api_login("admin", "admin")
        log["fallback_done"] = True
    np = decode_jwt(new)["payload"]
    log.update(refreshed=True, refresh_status=st,
               ttl_after=np["exp"] - int(time.time()),
               exp_advanced=np["exp"] - p["exp"],
               orig_iat_unchanged=np.get("orig_iat") == p.get("orig_iat"))
    print(f"[auth] 刷新完成：新 token {mask_jwt(new)}，剩余 {log['ttl_after']}s")
    save_token(new, "auto-refresh in fetch")
    return new, True, log


def cmd_fetch(pages: int, margin: int, limit: int) -> int:
    blob = load_token()
    tok, refreshed, log = ensure_fresh(blob["token"], margin)

    books, pages_meta = [], []
    for i in range(pages):
        offset = i * limit
        r = api_get(f"/api/book/?limit={limit}&offset={offset}", tok)
        if r.status_code == 401:
            print(f"[fetch] offset={offset} -> 401 {r.text[:120]}  ← token 失效，重新刷新")
            tok, _, log2 = ensure_fresh(tok, margin=10 ** 9)
            r = api_get(f"/api/book/?limit={limit}&offset={offset}", tok)
        j = r.json()
        got = j.get("results", [])
        print(f"[fetch] GET /api/book/?limit={limit}&offset={offset} -> {r.status_code}  "
              f"count={j.get('count')} 本页 {len(got)} 条")
        pages_meta.append({"offset": offset, "status": r.status_code, "n": len(got)})
        books.extend(got)
        time.sleep(DELAY)

    DATA.mkdir(parents=True, exist_ok=True)
    slim = [{"id": b.get("id"), "name": b.get("name"), "authors": b.get("authors"),
             "score": b.get("score")} for b in books]
    out = DATA / "login3_books.json"
    payload = {"source": BASE, "auth": "Authorization: jwt <token>",
               "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "refresh_log": log, "pages": pages_meta,
               "count": len(slim), "items": slim}
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[fetch] 共 {len(slim)} 条 -> {rel(out)} ({out.stat().st_size} 字节)")
    if slim:
        print(f"[fetch] 样例: {slim[0]['name']} | {slim[0]['authors']} | {slim[0]['score']}")
    return 0


def cmd_expiry(u: str, p: str) -> int:
    """过期 / 失效行为实测：能在服务端真跑出来的全部跑一遍，跑不了的写清为什么。"""
    rep: dict = {"case": "login3", "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 "source": BASE}
    tok = api_login(u, p)
    d = decode_jwt(tok)
    rep["token_shape"] = {"header": d["header"], "payload": d["payload"],
                          "signature_bytes": d["signature_bytes"],
                          "token_masked": mask_jwt(tok)}
    e = exp_info(d["payload"])
    rep["exp"] = e
    print(f"[expiry] 单次寿命 exp-orig_iat = {e['lifetime_seconds']}s = {e['lifetime_seconds'] / 3600:.0f} 小时")

    cases = []

    def rec(name, resp, note=""):
        cases.append({"case": name, "status": resp.status_code,
                      "body": resp.text[:200], "note": note})
        print(f"[expiry] {name:26s} -> {resp.status_code}  {resp.text[:90]}")
        time.sleep(0.5)

    rec("无 Authorization 头", api_get("/api/book/?limit=1", None))
    rec("正确 'jwt ' 前缀", api_get("/api/book/?limit=1", tok, "jwt"))
    rec("大写 'JWT ' 前缀", api_get("/api/book/?limit=1", tok, "JWT"))
    rec("错误 'Bearer ' 前缀", api_get("/api/book/?limit=1", tok, "Bearer"),
        "DRF-JWT 默认 JWT_AUTH_HEADER_PREFIX='JWT'，Bearer 会被当成未提供凭证")
    # 篡改签名 → 服务端验签失败
    bad_sig = tok[:-4] + ("AAAA" if not tok.endswith("AAAA") else "BBBB")
    rec("签名被篡改", api_get("/api/book/?limit=1", bad_sig, "jwt"))
    # 篡改 payload（把 exp 改到过去）→ 签名对不上，报的仍是解码错误
    h, pl, sg = tok.split(".")
    pay = json.loads(b64url_decode(pl))
    pay["exp"] = int(time.time()) - 3600
    forged_pl = base64.urlsafe_b64encode(
        json.dumps(pay, separators=(",", ":")).encode()).decode().rstrip("=")
    forged = f"{h}.{forged_pl}.{sg}"
    rec("payload 改成已过期", api_get("/api/book/?limit=1", forged, "jwt"),
        "本地把 exp 改到 1 小时前；因为改不动签名，服务端在校验 exp 之前就先挂在验签上——"
        "这说明「过期」和「伪造」在服务端是同一道 401 墙的两侧，客户端只能靠本地解 exp 提前判定")
    rep["auth_cases"] = cases

    # refresh 链：连刷两次，看 exp 前移、orig_iat 不动
    chain = []
    cur = tok
    for i in range(2):
        st, new, body = api_refresh(cur)
        if not new:
            chain.append({"round": i + 1, "status": st, "body": body})
            break
        op, npd = decode_jwt(cur)["payload"], decode_jwt(new)["payload"]
        chain.append({"round": i + 1, "status": st,
                      "old_exp": op["exp"], "new_exp": npd["exp"],
                      "exp_advanced": npd["exp"] - op["exp"],
                      "orig_iat_unchanged": npd["orig_iat"] == op["orig_iat"],
                      "token_changed": new != cur,
                      "new_token_masked": mask_jwt(new)})
        print(f"[expiry] refresh #{i + 1}: {st}  exp {op['exp']} -> {npd['exp']} "
              f"(+{npd['exp'] - op['exp']}s)  orig_iat 不变={npd['orig_iat'] == op['orig_iat']}")
        cur = new
        time.sleep(1.2)
    rep["refresh_chain"] = chain

    # 拿废 token 去 refresh
    st, new, body = api_refresh(bad_sig)
    rep["refresh_with_broken_token"] = {"status": st, "body": body}
    print(f"[expiry] 用篡改 token 去 refresh -> {st} {body[:120]}")

    rep["notes"] = [
        "exp - orig_iat = 43200 秒（12 小时），是 DRF-JWT 的 JWT_EXPIRATION_DELTA。",
        "服务端不给短寿命 token，所以「等到自然过期」需要 12 小时，本次未采用等待法；"
        "改为 (a) 本地伪造过期 token 打服务端、(b) 用 --refresh-margin 强制触发刷新分支，两条都实跑。",
        "orig_iat 在 refresh 后保持不变 —— DRF-JWT 用它算刷新窗口 "
        "(JWT_REFRESH_EXPIRATION_DELTA)，超窗后 refresh 会被拒，届时只能重新登录。",
    ]
    DATA.mkdir(parents=True, exist_ok=True)
    out = DATA / "login3_expiry_probe.json"
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[expiry] 落盘 -> {rel(out)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="login3：JWT 模拟登录 / 过期刷新")
    ap.add_argument("cmd", choices=["login", "inspect", "refresh", "fetch", "expiry"])
    ap.add_argument("-u", "--username", default="admin")
    ap.add_argument("-p", "--password", default="admin")
    ap.add_argument("--pages", type=int, default=3)
    ap.add_argument("--limit", type=int, default=18)
    ap.add_argument("--refresh-margin", type=int, default=DEFAULT_MARGIN,
                    help="exp 剩余不足这么多秒就刷新；调大可强制走刷新分支")
    a = ap.parse_args()
    return {
        "login": lambda: cmd_login(a.username, a.password),
        "inspect": cmd_inspect,
        "refresh": cmd_refresh,
        "fetch": lambda: cmd_fetch(a.pages, a.refresh_margin, a.limit),
        "expiry": lambda: cmd_expiry(a.username, a.password),
    }[a.cmd]()


if __name__ == "__main__":
    sys.exit(main())
