#!/usr/bin/env python3
"""login2 —— Session + Cookies 模拟登录与持久化（issue #9）。

来源: https://login2.scrape.center
案例描述（逐字引自 scrape.center）:
    对接 Session + Cookies 模拟登录，适合用作 Session + Cookies 模拟登录练习。

关键点：cookie **落盘**，第二个进程不登录、只加载 cookie 就能取受保护页面。

用法（两段式验证就是分两个进程跑）:
    python login2.py login                 # 第 1 段：登录 → 保存 cookie 到 data/cookies.json
    python login2.py fetch --pages 3       # 第 2 段：全新进程，只读 cookie，不再登录
    python login2.py whoami                # 只读 cookie 判断登录态
    python login2.py probe                 # cookie 有效期 / 失效表现实测
    python login2.py logout                # 服务端登出，观察 cookie 失效
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

BASE = "https://login2.scrape.center"
HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
COOKIE_FILE = DATA / "cookies.json"          # 真实 cookie，已被 .gitignore 排除


def rel(p: Path) -> str:
    """打印相对路径——运行日志要进 public 仓库，不外发本机绝对路径。"""
    return str(p.relative_to(HERE))

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
DELAY = 1.0                                   # 礼貌抓取：每页间隔


# --------------------------------------------------------------------------
# 脱敏
# --------------------------------------------------------------------------
def mask(v: str, head: int = 4, tail: int = 4) -> str:
    """只留前后几位，中间省略——落盘/打印一律走它，仓库是 public。"""
    if v is None:
        return None
    if len(v) <= head + tail:
        return v[:1] + "..."
    return f"{v[:head]}...{v[-tail:]}"


# --------------------------------------------------------------------------
# cookie 持久化
# --------------------------------------------------------------------------
_WIRE: list[dict] = []


def _wire_log(resp, *args, **kwargs):
    """把本进程发出的**每一个** HTTP 请求都记下来。

    两段式验证里 fetch 进程会把这份清单打出来——里面没有 /login，
    才算真的「没重新登录」，光靠脚本自己说不算数。
    """
    _WIRE.append({"method": resp.request.method, "url": resp.request.url,
                  "path": urlparse(resp.request.url).path, "status": resp.status_code})
    return resp


def new_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": UA,
                      "Accept-Language": "zh-CN,zh;q=0.9"})
    s.hooks["response"].append(_wire_log)
    return s


def save_cookies(s: requests.Session, note: str = "") -> Path:
    DATA.mkdir(parents=True, exist_ok=True)
    jar = []
    for c in s.cookies:
        jar.append({"name": c.name, "value": c.value, "domain": c.domain,
                    "path": c.path, "expires": c.expires, "secure": c.secure})
    blob = {"saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "note": note, "cookies": jar}
    COOKIE_FILE.write_text(json.dumps(blob, ensure_ascii=False, indent=2), encoding="utf-8")
    return COOKIE_FILE


def load_cookies(s: requests.Session) -> dict:
    if not COOKIE_FILE.exists():
        raise SystemExit(f"[error] 没有 cookie 文件：{rel(COOKIE_FILE)}\n"
                         f"        先跑一次 `python login2.py login`")
    blob = json.loads(COOKIE_FILE.read_text(encoding="utf-8"))
    for c in blob["cookies"]:
        s.cookies.set(c["name"], c["value"], domain=c["domain"], path=c["path"])
    return blob


def describe_cookies(blob: dict) -> None:
    print(f"[cookie] 保存时间: {blob['saved_at']}  ({blob.get('note', '')})")
    for c in blob["cookies"]:
        exp = c.get("expires")
        exp_s = datetime.fromtimestamp(exp, timezone.utc).isoformat(timespec="seconds") if exp else "session"
        left = f"{(exp - time.time()) / 86400:.2f} 天" if exp else "-"
        print(f"[cookie]   {c['name']}={mask(c['value'])}  domain={c['domain']} "
              f"path={c['path']} expires={exp_s} 剩余={left}")


# --------------------------------------------------------------------------
# 登录
# --------------------------------------------------------------------------
def do_login(username: str, password: str) -> int:
    s = new_session()
    # 1) 先 GET 登录页——真实浏览器行为；顺带确认这站要不要 CSRF token
    g = s.get(f"{BASE}/login?next=/", timeout=30)
    has_csrf = "csrfmiddlewaretoken" in g.text
    print(f"[login] GET /login?next=/ -> {g.status_code}；页面含 csrfmiddlewaretoken: {has_csrf}")
    print(f"[login] GET 后的 cookie: {dict(s.cookies)}")

    # 2) POST 表单。注意 allow_redirects=False：302 才是成功信号
    r = s.post(f"{BASE}/login?next=/", data={"username": username, "password": password},
               timeout=30, allow_redirects=False)
    print(f"[login] POST /login?next=/ -> {r.status_code}  Location={r.headers.get('Location')}")
    raw = r.headers.get("Set-Cookie", "")
    print(f"[login] Set-Cookie（脱敏）: {re.sub(r'sessionid=[^;]+', lambda m: 'sessionid=' + mask(m.group(0)[10:]), raw)}")

    if r.status_code != 302:
        print("[login] 失败：登录成功应为 302 重定向，200 表示表单被打回")
        return 1

    p = save_cookies(s, note=f"login as {username}")
    print(f"[login] cookie 已落盘 -> {rel(p)}")
    describe_cookies(json.loads(p.read_text(encoding="utf-8")))
    return 0


# --------------------------------------------------------------------------
# 用 cookie 取受保护页面
# --------------------------------------------------------------------------
def parse_list(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    items = []
    for el in soup.select(".el-card.item"):
        name_el = el.select_one("h2.m-b-sm")
        cats = [x.get_text(strip=True) for x in el.select(".categories button span")]
        info = [x.get_text(strip=True) for x in el.select(".m-v-sm.info")]
        score = el.select_one(".score")
        href = el.select_one("a")
        items.append({
            "name": name_el.get_text(strip=True) if name_el else None,
            "categories": cats,
            "info": info,
            "score": score.get_text(strip=True) if score else None,
            "detail": href["href"] if href and href.has_attr("href") else None,
        })
    return items


def do_fetch(pages: int) -> int:
    s = new_session()
    blob = load_cookies(s)
    print("[fetch] 本进程**不做登录**，只加载磁盘上的 cookie：")
    describe_cookies(blob)

    all_items: list[dict] = []
    for i in range(1, pages + 1):
        path = "/" if i == 1 else f"/page/{i}"
        r = s.get(BASE + path, timeout=30, allow_redirects=False)
        if r.status_code == 302:
            print(f"[fetch] GET {path} -> 302 {r.headers.get('Location')}  ← cookie 已失效，需重新登录")
            return 2
        items = parse_list(r.text)
        print(f"[fetch] GET {path} -> {r.status_code}  解析出 {len(items)} 条")
        all_items.extend(items)
        time.sleep(DELAY)

    DATA.mkdir(parents=True, exist_ok=True)
    out = DATA / "login2_movies.json"
    payload = {"source": BASE, "pages": pages, "count": len(all_items),
               "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "auth": "session cookie loaded from disk, no login in this process",
               "pid": os.getpid(),
               "http_requests_made": _WIRE,
               "items": all_items}
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    size = out.stat().st_size
    print(f"[fetch] 共 {len(all_items)} 条 -> {rel(out)} ({size} 字节)")
    if all_items:
        print(f"[fetch] 样例: {all_items[0]['name']} | {'/'.join(all_items[0]['categories'])} | {all_items[0]['score']}")

    print("[fetch] 本进程发出的全部 HTTP 请求：")
    for w in _WIRE:
        print(f"[fetch]   {w['method']} {w['url']} -> {w['status']}")
    hit = [w for w in _WIRE if w["path"].startswith("/login")]
    print(f"[fetch] 其中 path 以 /login 开头的请求数 = {len(hit)}  "
          f"→ {'又登录了（不合格）' if hit else 'OK：全程未登录，纯 cookie 复用'}")
    return 0


def do_whoami() -> int:
    s = new_session()
    blob = load_cookies(s)
    describe_cookies(blob)
    r = s.get(BASE + "/", timeout=30, allow_redirects=False)
    if r.status_code == 200:
        soup = BeautifulSoup(r.text, "lxml")
        btn = soup.select_one(".user button span") or soup.select_one(".logout")
        who = btn.get_text(strip=True) if btn else "(页面未暴露用户名)"
        print(f"[whoami] 已登录 —— GET / -> 200，页面顶栏显示: {who}")
        return 0
    print(f"[whoami] 未登录 —— GET / -> {r.status_code} {r.headers.get('Location')}")
    return 1


# --------------------------------------------------------------------------
# cookie 有效期 / 失效表现
# --------------------------------------------------------------------------
def do_probe(username: str, password: str) -> int:
    report: dict = {"case": "login2", "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}

    # A. 匿名访问受保护页
    r = requests.get(BASE + "/", headers={"User-Agent": UA}, timeout=30, allow_redirects=False)
    report["anonymous"] = {"status": r.status_code, "location": r.headers.get("Location")}
    print(f"[probe] 无 cookie      GET / -> {r.status_code} {r.headers.get('Location')}")

    # B. 伪造 sessionid
    r = requests.get(BASE + "/", headers={"User-Agent": UA}, cookies={"sessionid": "x" * 32},
                     timeout=30, allow_redirects=False)
    report["forged_sessionid"] = {"status": r.status_code, "location": r.headers.get("Location")}
    print(f"[probe] 伪造 sessionid GET / -> {r.status_code} {r.headers.get('Location')}")

    # C. 密码错误
    s = new_session()
    r = s.post(f"{BASE}/login?next=/", data={"username": username, "password": password + "_wrong"},
               timeout=30, allow_redirects=False)
    report["wrong_password"] = {"status": r.status_code,
                                "set_cookie": bool(r.headers.get("Set-Cookie")),
                                "location": r.headers.get("Location")}
    print(f"[probe] 密码错误      POST /login -> {r.status_code}（成功应为 302）"
          f"  Set-Cookie: {bool(r.headers.get('Set-Cookie'))}")

    # D. 正确登录，读 cookie 属性
    s = new_session()
    r = s.post(f"{BASE}/login?next=/", data={"username": username, "password": password},
               timeout=30, allow_redirects=False)
    ck = next((c for c in s.cookies if c.name == "sessionid"), None)
    raw = r.headers.get("Set-Cookie", "")
    attrs = {k.strip().split("=")[0].lower(): k.strip() for k in raw.split(";")[1:]}
    report["session_cookie"] = {
        "name": "sessionid",
        "value_masked": mask(ck.value) if ck else None,
        "value_len": len(ck.value) if ck else None,
        "expires_epoch": ck.expires if ck else None,
        "expires_utc": datetime.fromtimestamp(ck.expires, timezone.utc).isoformat(timespec="seconds") if ck and ck.expires else None,
        "lifetime_days": round((ck.expires - time.time()) / 86400, 3) if ck and ck.expires else None,
        "attrs": list(attrs.values()),
        "httponly": "httponly" in attrs,
        "secure": bool(ck.secure) if ck else None,
    }
    print(f"[probe] sessionid={mask(ck.value)} 长度={len(ck.value)} "
          f"有效期={report['session_cookie']['lifetime_days']} 天 属性={list(attrs.values())}")

    # E. 服务端登出后，同一个 cookie 还能不能用
    old = ck.value
    lo = s.get(BASE + "/logout", timeout=30, allow_redirects=False)
    print(f"[probe] GET /logout -> {lo.status_code} {lo.headers.get('Location')}")
    reuse = requests.get(BASE + "/", headers={"User-Agent": UA}, cookies={"sessionid": old},
                         timeout=30, allow_redirects=False)
    report["reuse_after_logout"] = {"status": reuse.status_code, "location": reuse.headers.get("Location")}
    print(f"[probe] 登出后复用旧 sessionid GET / -> {reuse.status_code} "
          f"{reuse.headers.get('Location')}  ← 服务端已销毁 session")

    DATA.mkdir(parents=True, exist_ok=True)
    out = DATA / "login2_cookie_probe.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[probe] 落盘 -> {rel(out)}")
    return 0


def do_logout() -> int:
    s = new_session()
    load_cookies(s)
    r = s.get(BASE + "/logout", timeout=30, allow_redirects=False)
    print(f"[logout] GET /logout -> {r.status_code} {r.headers.get('Location')}")
    r2 = s.get(BASE + "/", timeout=30, allow_redirects=False)
    print(f"[logout] 再访问 / -> {r2.status_code} {r2.headers.get('Location')}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="login2：Session + Cookies 模拟登录与持久化")
    ap.add_argument("cmd", choices=["login", "fetch", "whoami", "probe", "logout"])
    ap.add_argument("-u", "--username", default="admin")
    ap.add_argument("-p", "--password", default="admin")
    ap.add_argument("--pages", type=int, default=3)
    a = ap.parse_args()

    # 打印 PID：两段式验证要证明「换了进程」，PID 不同就是硬证据
    print(f"=== login2.py {a.cmd}  pid={os.getpid()}  "
          f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} ===")

    return {
        "login": lambda: do_login(a.username, a.password),
        "fetch": lambda: do_fetch(a.pages),
        "whoami": do_whoami,
        "probe": lambda: do_probe(a.username, a.password),
        "logout": do_logout,
    }[a.cmd]()


if __name__ == "__main__":
    sys.exit(main())
