#!/usr/bin/env python3
"""antispider8 的 debugger 反调试：四种绕过手段的实测对照（issue #12 / 阶段 9）

站点埋了两处 `debugger`（均逐字引自站点下发的 chunk，未改动）：

  ① 定时循环 debugger —— js/app.40192839.js
     `r.default.config.productionTip=!1,setInterval((function(){debugger;console.log("debugger")}),1e3),`

  ② 接口处 debugger —— js/chunk-51935b2c.7a777070.js（列表页组件）
     `onFetchData:function(){var t=this;debugger;this.loading=!0;var a=(this.page-1)*this.limit,e=Object(s.a)(this.$store.state.url.index);...`
     以及 js/chunk-27855899.741dfe15.js（详情页组件）同一模式。

本脚本用 Playwright + CDP 做**受控实验**，五组，每组只改一个变量：

    E0 对照组·无调试器      不接 CDP Debugger，看页面能不能自己跑起来
    E1 对照组·接调试器      接 CDP Debugger.enable，不做任何对抗 → 应当被反复打断
    E2 中间人改写响应        route 拦截 js，把 debugger 语句剥掉再交给浏览器
    E3 调试器侧忽略断点      CDP Debugger.setSkipAllPauses(true)
    E4 置换 setInterval      addInitScript 在业务代码之前换掉 setInterval（只能治①，治不了②）

判据统一：窗口期内 **Debugger.paused 事件次数** + **页面是否真的渲染出电影卡片**。
「看起来没卡」不算证据，事件计数才算。

    python debugger_bypass.py
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
EV = HERE / "evidence"
BASE = "https://antispider8.scrape.center"
WINDOW = 8.0          # 每组实验的观察窗口（秒）；定时 debugger 是 1s 一次，8s 足够看出规模
CARD = "#index .item"  # 列表页电影卡片


class Probe:
    """一次实验。"""

    def __init__(self, name: str, desc: str):
        self.name = name
        self.desc = desc
        self.paused = 0
        self.cards = 0
        self.api_status: list[int] = []
        self.stripped: dict | None = None
        self.error: str | None = None

    def as_dict(self) -> dict:
        return {
            "实验": self.name,
            "手段": self.desc,
            "Debugger.paused 次数": self.paused,
            "渲染出的电影卡片数": self.cards,
            "/api/movie 响应码": self.api_status,
            "改写统计": self.stripped,
            "异常": self.error,
        }


# `debugger;` / `debugger}` / 换行分隔的 debugger 都要覆盖，但不能误伤
# 字符串里的 "debugger"（app.js 里就有一句 console.log("debugger")）。
DEBUGGER_STMT = re.compile(r"(?<![\w$.\"'])debugger\s*;?")


def strip_debugger(js: str) -> tuple[str, int]:
    """把 `debugger` 语句换成空语句 `;`。

    为什么不是简单 `js.replace("debugger","")`：app.js 里紧跟着一句
    `console.log("debugger")`，字符串里的那个 debugger 不能动 —— 动了就改变了页面行为，
    实验就不干净了。所以用「前面不能是标识符字符或引号」的边界条件卡住。
    """
    n = 0

    def sub(_m):
        nonlocal n
        n += 1
        return ";"

    return DEBUGGER_STMT.sub(sub, js), n


def experiment(
    pw, name: str, desc: str, *,
    attach_debugger: bool,
    rewrite_js: bool = False,
    skip_all_pauses: bool = False,
    kill_setinterval: bool = False,
) -> Probe:
    p = Probe(name, desc)
    browser = pw.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    stats = {"files": 0, "removed": 0, "per_file": {}}

    try:
        if rewrite_js:
            def handler(route):
                resp = route.fetch()
                body = resp.text()
                new, n = strip_debugger(body)
                stats["files"] += 1
                stats["removed"] += n
                # 逐文件记账：总数会因为 prefetch 而重复计同一个文件，
                # 只报总数会让人误以为站点里埋了那么多条。分开记才说得清。
                fname = route.request.url.rsplit("/", 1)[-1]
                e = stats["per_file"].setdefault(fname, {"拦截次数": 0, "每次剥掉": n})
                e["拦截次数"] += 1
                route.fulfill(response=resp, body=new,
                              headers={**resp.headers, "content-length": str(len(new.encode()))})
            ctx.route("**/js/*.js", handler)

        if kill_setinterval:
            # 在页面任何脚本之前执行：把 setInterval 换成「只吞掉带 debugger 的回调」的版本。
            ctx.add_init_script("""
                const _si = window.setInterval;
                window.setInterval = function (fn, ms, ...rest) {
                  const src = typeof fn === 'function' ? Function.prototype.toString.call(fn) : String(fn);
                  if (/\\bdebugger\\b/.test(src.replace(/(["'`]).*?\\1/g, ''))) {
                    window.__killedIntervals = (window.__killedIntervals || 0) + 1;
                    return -1;                       // 假 id，定时器根本没建
                  }
                  return _si.call(this, fn, ms, ...rest);
                };
            """)

        page = ctx.new_page()
        page.on("response", lambda r: p.api_status.append(r.status) if "/api/movie" in r.url else None)

        cdp = None
        pending = []
        if attach_debugger:
            cdp = ctx.new_cdp_session(page)
            cdp.on("Debugger.paused", lambda e: pending.append(e))
            cdp.send("Debugger.enable")
            if skip_all_pauses:
                cdp.send("Debugger.setSkipAllPauses", {"skip": True})

        page.goto(BASE + "/", wait_until="commit", timeout=45000)
        if attach_debugger and skip_all_pauses:
            # 必须在导航**之后**再下一次：Debugger.setSkipAllPauses 是会话状态，
            # 页面一导航就被重置。只在 goto 之前设置的话，实测仍会被 debugger 打断
            # （第一版就是这么写的，E3 记到 8 次 pause，看着像「这招没用」）。
            cdp.send("Debugger.setSkipAllPauses", {"skip": True})

        deadline = time.time() + WINDOW
        while time.time() < deadline:
            page.wait_for_timeout(200)
            while pending:
                pending.pop()
                p.paused += 1
                if cdp:
                    cdp.send("Debugger.resume")      # 不放行页面就永远卡着，实验也就没了下文

        try:
            p.cards = page.locator(CARD).count()
        except Exception as e:                       # noqa: BLE001
            p.error = f"读取卡片数失败: {e}"

        if rewrite_js:
            uniq = sum(v["每次剥掉"] for v in stats["per_file"].values())
            p.stripped = {
                "拦截的 js 请求数": stats["files"],
                "累计剥掉的 debugger 语句数": stats["removed"],
                "去重后站点里实有的 debugger 语句数": uniq,
                "逐文件": stats["per_file"],
            }
        if kill_setinterval:
            try:
                p.stripped = {"被拦截的 setInterval 次数": page.evaluate("window.__killedIntervals || 0")}
            except Exception:                        # noqa: BLE001
                pass
    except Exception as e:                           # noqa: BLE001
        p.error = f"{type(e).__name__}: {e}"
    finally:
        try:
            browser.close()
        except Exception:                            # noqa: BLE001
            pass
    return p


def main() -> int:
    plans = [
        ("E0 对照组·不接调试器", "什么都不做，headless 直接打开",
         dict(attach_debugger=False)),
        ("E1 对照组·接调试器", "CDP Debugger.enable，不做任何对抗",
         dict(attach_debugger=True)),
        ("E2 中间人改写响应", "route 拦截 **/js/*.js，把 debugger 语句替换成空语句",
         dict(attach_debugger=True, rewrite_js=True)),
        ("E3 调试器侧忽略断点", "CDP Debugger.setSkipAllPauses(true)（= DevTools 的「停用断点/Never pause here」）",
         dict(attach_debugger=True, skip_all_pauses=True)),
        ("E4 置换 setInterval", "addInitScript 抢在业务代码前换掉 setInterval，丢弃带 debugger 的回调",
         dict(attach_debugger=True, kill_setinterval=True)),
    ]
    results = []
    with sync_playwright() as pw:
        for name, desc, kw in plans:
            print(f"\n▶ {name} —— {desc}", flush=True)
            r = experiment(pw, name, desc, **kw)
            print("  " + json.dumps(r.as_dict(), ensure_ascii=False), flush=True)
            results.append(r.as_dict())

    out = {
        "site": BASE,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S %z"),
        "观察窗口秒": WINDOW,
        "两处 debugger 出处": {
            "定时循环": "js/app.40192839.js  → setInterval((function(){debugger;console.log(\"debugger\")}),1e3)",
            "接口处": "js/chunk-51935b2c.7a777070.js (列表) / js/chunk-27855899.741dfe15.js (详情) → onFetchData:function(){var t=this;debugger;...}",
        },
        "实验": results,
    }
    EV.mkdir(parents=True, exist_ok=True)
    (EV / "debugger_bypass.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✅ 写出 {EV / 'debugger_bypass.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
