#!/usr/bin/env python3
"""antispider8 —— 接口 debugger + 定时循环 debugger（issue #12 / 阶段 9）

**本文件全程不启动浏览器。** 这就是对付 `debugger` 的第一手段，也是最彻底的一种：
`debugger` 是给「附着了调试器的 JS 引擎」看的指令，requests 眼里它连字符都不是。
逆向的目标从来不是「在浏览器里把页面点开」，而是「把 token 算法搬到浏览器外面」。

浏览器内的绕过实证在 `debugger_bypass.py`（route 中间人改写 / setInterval 置换 / 对照组）。

    python spider.py               # 抓列表 104 条 + 前 5 部详情
    python spider.py --twice 90    # 隔 90s 跑两次，证明 token 是现算的、不是抄来的
"""

from __future__ import annotations

import base64
import hashlib
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import common  # noqa: E402

BASE = "https://antispider8.scrape.center"

# ---------------------------------------------------------------------------
# 从 js/chunk-4136500c.36dbfdb6.js 模块 "7d92" 还原出来的 token 生成器。
# 混淆后的原文（逐字引自站点下发的 chunk，未改动）：
#
#   "7d92":function(t,e,r){"use strict";r("6b54");var i=r("3452");
#     e.a=function(){for(var t=Math.round((new Date).getTime()/1e3).toString(),
#     e=arguments.length,r=new Array(e),n=0;n<e;n++)r[n]=arguments[n];r.push(t);
#     var o=i.SHA1(r.join(",")).toString(i.enc.Hex),
#     s=i.enc.Base64.stringify(i.enc.Utf8.parse([o,t].join(",")));return s}}
#
# 读法：把「若干参数 + 当前 unix 秒」用逗号连成一串取 SHA1（十六进制），
#       再把 "sha1十六进制,unix秒" 整体做 Base64。
# ---------------------------------------------------------------------------
def make_token(*args: str) -> str:
    ts = str(round(time.time()))
    joined = ",".join([*args, ts])
    sha1_hex = hashlib.sha1(joined.encode("utf-8")).hexdigest()
    return base64.b64encode(f"{sha1_hex},{ts}".encode("utf-8")).decode("ascii")


# ---------------------------------------------------------------------------
# 详情页 key。混淆后的原文（模块 "3e22"，逐字引自站点下发的 chunk）：
#
#   "3e22":function(t,e,r){"use strict";var i=r("3452");
#     e.a=function(t){return console.log("stttt",t),
#     i.enc.Base64.stringify(i.enc.Utf8.parse(
#     "ef34#teuq0btua#(-57w1q5o5--j@98xygimlyfxs*-!i-0-mb"+t))}}
#
# 读法：固定盐 + 电影自增 id，整体 Base64。
# （原作者调试时留下的 console.log("stttt", t) 也照抄进注释，不做美化 —— rule 第 15 条。）
# ---------------------------------------------------------------------------
SALT = "ef34#teuq0btua#(-57w1q5o5--j@98xygimlyfxs*-!i-0-mb"


def detail_key(movie_id: int) -> str:
    return base64.b64encode(f"{SALT}{movie_id}".encode("utf-8")).decode("ascii")


# 前端 store 里的两条 URL 模板（chunk js/app.40192839.js）：
#   state:{url:{index:"/api/movie",detail:"/api/movie/{key}"}}
# 注意 token 的第一个参数是**这条路径模板填好之后的字符串**，不是完整 URL。
INDEX_PATH = "/api/movie"
DETAIL_PATH = "/api/movie/{key}"


def fetch_index(sess: common.PoliteSession, limit: int = 10) -> tuple[list[dict], int, list[dict]]:
    movies: list[dict] = []
    total = None
    trace: list[dict] = []
    offset = 0
    while True:
        token = make_token(INDEX_PATH)
        r = sess.get(
            BASE + INDEX_PATH + "/",
            params={"limit": limit, "offset": offset, "token": token},
        )
        trace.append({
            "offset": offset, "status": r.status_code,
            "token_head": token[:24] + "…", "returned": None,
        })
        if r.status_code != 200:
            raise RuntimeError(f"列表 offset={offset} 返回 {r.status_code}: {r.text[:200]}")
        data = r.json()
        total = data["count"]
        got = data["results"]
        trace[-1]["returned"] = len(got)
        movies.extend(got)
        offset += limit
        if offset >= total or not got:
            break
    return movies, total, trace


def fetch_detail(sess: common.PoliteSession, movie_id: int) -> dict:
    path = DETAIL_PATH.format(key=detail_key(movie_id))
    token = make_token(path)
    r = sess.get(BASE + path, params={"token": token})
    if r.status_code != 200:
        raise RuntimeError(f"详情 id={movie_id} 返回 {r.status_code}: {r.text[:200]}")
    return r.json()


def run(tag: str = "") -> dict:
    sess = common.PoliteSession(interval=1.0, jitter=0.3)
    print(f"[antispider8]{tag} 开抓（不启动浏览器）")

    # 反例先跑：不带 token 会怎样 —— 证明 token 确实是门槛，不是摆设
    bare = sess.s.get(BASE + INDEX_PATH + "/", params={"limit": 1, "offset": 0}, timeout=30)
    print(f"  · 不带 token: HTTP {bare.status_code}")

    movies, total, trace = fetch_index(sess)
    print(f"  · 列表: {len(movies)}/{total} 条，{len(trace)} 次请求全部 200")

    details = [fetch_detail(sess, m["id"]) for m in movies[:5]]
    print(f"  · 详情: 取前 {len(details)} 部，全部 200")

    payload = {
        "site": "antispider8",
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S %z"),
        "browser_used": False,
        "no_token_status": bare.status_code,
        "count": total,
        "fetched": len(movies),
        "request_trace": trace,
        "movies": movies,
        "details_sample": details,
    }
    common.save_json(HERE / "data" / "antispider8_movies.json", payload, sample_key="movies")
    return {
        "no_token_status": bare.status_code,
        "count": total,
        "fetched": len(movies),
        "requests": len(trace),
        "details": len(details),
        "first": movies[0]["name"] if movies else None,
        "sample_token": trace[0]["token_head"],
    }


if __name__ == "__main__":
    if "--twice" in sys.argv:
        i = sys.argv.index("--twice")
        gap = int(sys.argv[i + 1]) if len(sys.argv) > i + 1 and sys.argv[i + 1].isdigit() else 90
        a = run(" 第 1 次")
        print(f"  ⏱ 等待 {gap}s…", flush=True)
        time.sleep(gap)
        b = run(" 第 2 次")
        same_token = a["sample_token"] == b["sample_token"]
        proof = {
            "run_1": a, "run_2": b, "gap_seconds": gap,
            "tokens_identical": same_token,
            "conclusion": (
                "两次 token 不同但都拿到 200 —— token 是每次现算的（含 unix 秒），"
                "不是从浏览器抄来的固定值"
                if not same_token else
                "两次 token 相同：间隔太短落在同一秒内，请加大 --twice 间隔重跑"
            ),
        }
        (HERE / "evidence" / "twice_run.json").write_text(
            json.dumps(proof, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(proof, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(run(), ensure_ascii=False, indent=2))
