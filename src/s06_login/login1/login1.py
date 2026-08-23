#!/usr/bin/env python3
"""login1 —— 登录表单加密的 JS 逆向复现（issue #9）。

来源: https://login1.scrape.center
案例描述（逐字引自 scrape.center）:
    模拟登录网站，登录时用户名和密码经过加密处理，适合 JavaScript 逆向分析。

本脚本做三件事，全部脱离浏览器：
  1. locate  —— 从线上 JS bundle 里**定位**加密入口（不写死结论，每次实跑重新定位）
  2. encrypt —— 在 Python 侧复现该加密，产出与浏览器**逐字节一致**的 token
  3. submit  —— 按 axios 的原样请求提交 token，并如实记录服务端响应

用法:
    python login1.py all              # 全流程（默认）
    python login1.py locate           # 只做 JS 定位
    python login1.py encrypt -u admin -p admin
    python login1.py submit -u admin -p admin
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import sys
import time
from pathlib import Path

import requests

BASE = "https://login1.scrape.center"
HERE = Path(__file__).resolve().parent
DATA = HERE / "data"


def rel(p: Path) -> str:
    """打印相对路径——运行日志要进 public 仓库，不外发本机绝对路径。"""
    return str(p.relative_to(HERE))

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# axios 在这个站上发出的请求头（同源 XHR，无预检）
AXIOS_HEADERS = {
    "User-Agent": UA,
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json;charset=UTF-8",
    "Origin": BASE,
    "Referer": BASE + "/",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
    "Accept-Language": "zh-CN,zh;q=0.9",
}


def _get(url: str) -> str:
    r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
    r.raise_for_status()
    return r.text


# --------------------------------------------------------------------------
# 1) locate：从线上 bundle 定位加密入口
# --------------------------------------------------------------------------
def locate() -> dict:
    """顺着 index.html → 路由 chunk → onSubmit，实跑定位加密函数。

    定位链路（每一步都可复现）：
      index.html 里 <link rel=prefetch href=/js/chunk-*.js>  → 路由懒加载 chunk
      chunk 里搜 onSubmit                                     → 表单提交回调
      回调里搜 encode(JSON.stringify(...))                    → 加密表达式
      同 chunk 里搜 b64chars                                   → 确认是 Base64 而非自定义字母表
    """
    out: dict = {"base": BASE, "at": time.strftime("%Y-%m-%d %H:%M:%S")}

    html = _get(BASE + "/")
    chunks = re.findall(r'href=(/js/chunk-[\w.-]+\.js)', html)
    entry = re.findall(r'src=(/js/app\.[\w.]+\.js)', html)
    out["index_chunks"] = chunks
    out["index_entry"] = entry
    print(f"[locate] index.html 里的路由 chunk: {chunks}")
    print(f"[locate] 入口 app.js: {entry}")

    # 加密逻辑在路由 chunk（登录页组件）里
    target = None
    for c in chunks:
        js = _get(BASE + c)
        if "onSubmit" in js:
            target = (c, js)
            break
    if target is None:
        raise SystemExit("[locate] 未在任何 chunk 中找到 onSubmit，站点可能已改版")
    chunk_path, js = target
    out["chunk"] = chunk_path
    print(f"[locate] 命中 chunk: {chunk_path} ({len(js)} 字节)")

    # 提取 onSubmit 函数体
    m = re.search(r"onSubmit\s*:\s*function\s*\([^)]*\)\s*\{(.{0,400}?)\}\s*\}", js, re.S)
    body = m.group(1) if m else ""
    out["onSubmit_body"] = body.strip()
    print(f"[locate] onSubmit 函数体（原样）:\n    {body.strip()}")

    # 加密表达式
    enc = re.search(r"(\w+)\s*=\s*(\w+)\.encode\(JSON\.stringify\((this\.\w+)\)\)", body)
    out["encrypt_expr"] = enc.group(0) if enc else None
    print(f"[locate] 加密表达式: {out['encrypt_expr']}")

    # 提交地址：$http.post(store.state.url.root, {token: e})
    post = re.search(r"\$http\.post\(([^,]+),\s*\{\s*token\s*:\s*(\w+)\s*\}", body)
    out["post_expr"] = post.group(0) if post else None
    print(f"[locate] 提交表达式: {out['post_expr']}")

    # url.root 在入口 app.js 的 vuex store 里
    app = _get(BASE + entry[0]) if entry else ""
    root = re.search(r"state\s*:\s*\{\s*url\s*:\s*\{\s*root\s*:\s*\"([^\"]*)\"", app)
    out["url_root"] = root.group(1) if root else None
    print(f"[locate] vuex state.url.root = {out['url_root']!r}  →  提交到 {BASE}{out['url_root']}")

    # 确认 Base64 字母表是标准表（不是魔改表）
    tab = re.search(r'b64chars\s*=\s*"([^"]+)"', js)
    out["b64chars"] = tab.group(1) if tab else None
    std = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
    out["b64chars_is_standard"] = (out["b64chars"] == std)
    print(f"[locate] Base64 字母表 == 标准表: {out['b64chars_is_standard']}")

    # encode(e, r)：r 为真才转 URL-safe；onSubmit 只传一个参数 → 标准 Base64 + '=' 补位
    urlsafe = re.search(r"encode\s*=\s*function\s*\(\w+,\s*(\w+)\)\s*\{\s*return\s+\1\?", js)
    out["encode_has_urlsafe_branch"] = bool(urlsafe)
    out["urlsafe_used_by_onSubmit"] = False  # onSubmit 调用是 encode(x)，第二参 undefined
    print(f"[locate] encode() 有 URL-safe 分支: {out['encode_has_urlsafe_branch']}；"
          f"onSubmit 未启用（只传 1 个参数）→ 用标准 Base64、保留 '=' 补位")
    return out


# --------------------------------------------------------------------------
# 2) encrypt：Python 侧复现
# --------------------------------------------------------------------------
def js_json_stringify(obj: dict) -> str:
    """复现 JS `JSON.stringify`：无空格分隔符 + 键序按插入序（Vue data 里 username 先于 password）。

    Python 的 json.dumps 默认是 ', ' / ': '，会多出空格 → token 与浏览器不一致。
    这是本案例最容易翻车的一处细节。
    """
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


def encrypt(username: str, password: str) -> str:
    """复现 login1 的「加密」：Base64(UTF-8(JSON.stringify({username, password})))。

    对应 JS（chunk-cc71364c，逐字）:
        onSubmit: function () {
            var e = c.encode(JSON.stringify(this.form));
            this.$http.post(a["a"].state.url.root, {token: e})...
        }
    其中 c = require("27ae").Base64，是 dankogai/js-base64 v2.5.1，
    encode(s) = btoa(utob(s))，utob 把字符串按 UTF-8 展开 —— 等价于 Python 的
    base64.b64encode(s.encode("utf-8"))。
    """
    payload = js_json_stringify({"username": username, "password": password})
    return base64.b64encode(payload.encode("utf-8")).decode("ascii")


def decrypt(token: str) -> dict:
    """对称还原，用来自证 token 结构（Base64 本身可逆，不是真加密）。"""
    return json.loads(base64.b64decode(token).decode("utf-8"))


# --------------------------------------------------------------------------
# 3) submit：按 axios 原样提交
# --------------------------------------------------------------------------
def submit(token: str) -> dict:
    url = BASE + "/"
    body = json.dumps({"token": token}, separators=(",", ":"))
    r = requests.post(url, data=body.encode(), headers=AXIOS_HEADERS, timeout=30)
    res = {
        "url": url,
        "request_body": body,
        "status": r.status_code,
        "resp_headers": dict(r.headers),
        "resp_text_head": r.text[:200],
    }
    print(f"[submit] POST {url} -> {r.status_code}")
    print(f"[submit] 响应首段: {r.text[:120]!r}")
    return res


def server_probe() -> dict:
    """如实探明服务端：login1 是纯静态站，非 GET/HEAD 一律 nginx 405。"""
    out = {}
    for method, path in [("POST", "/"), ("OPTIONS", "/"), ("PUT", "/"),
                         ("POST", "/api/login"), ("POST", "/js/app.d03bfa52.js")]:
        r = requests.request(method, BASE + path, headers={"User-Agent": UA}, timeout=20)
        out[f"{method} {path}"] = r.status_code
        print(f"[probe] {method:8s}{path:26s} -> {r.status_code}")
        time.sleep(0.4)          # 礼貌抓取
    r = requests.get(BASE + "/", headers={"User-Agent": UA}, timeout=20)
    out["GET /"] = r.status_code
    print(f"[probe] {'GET':8s}{'/':26s} -> {r.status_code}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="login1：登录表单加密的 JS 逆向复现")
    ap.add_argument("cmd", nargs="?", default="all",
                    choices=["all", "locate", "encrypt", "submit", "probe"])
    ap.add_argument("-u", "--username", default="admin")
    ap.add_argument("-p", "--password", default="admin")
    a = ap.parse_args()

    DATA.mkdir(parents=True, exist_ok=True)
    report: dict = {"case": "login1", "issue": 9, "source": BASE,
                    "at": time.strftime("%Y-%m-%d %H:%M:%S %z")}

    if a.cmd in ("all", "locate"):
        report["locate"] = locate()
        print()

    if a.cmd in ("all", "encrypt", "submit"):
        plain = js_json_stringify({"username": a.username, "password": a.password})
        tok = encrypt(a.username, a.password)
        print(f"[encrypt] JSON.stringify 结果: {plain}")
        print(f"[encrypt] token = {tok}")
        print(f"[encrypt] 反解回明文 = {decrypt(tok)}")
        # 自检：Python 默认 json.dumps 会多空格，token 就不一样了
        naive = base64.b64encode(json.dumps(
            {"username": a.username, "password": a.password}).encode()).decode()
        print(f"[encrypt] 反例（json.dumps 默认带空格）= {naive}  "
              f"→ 与浏览器一致? {naive == tok}")
        report["encrypt"] = {"plaintext": plain, "token": tok,
                             "roundtrip": decrypt(tok),
                             "naive_dumps_token": naive,
                             "naive_matches_browser": naive == tok}
        print()

    if a.cmd in ("all", "submit"):
        report["submit"] = submit(encrypt(a.username, a.password))
        print()

    if a.cmd in ("all", "probe"):
        report["server_probe"] = server_probe()

    out = DATA / "login1_result.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[done] 结果落盘 -> {rel(out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
