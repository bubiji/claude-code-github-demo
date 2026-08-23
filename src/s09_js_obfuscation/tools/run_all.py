#!/usr/bin/env python3
"""阶段 9 全案例「隔一段时间跑两次」实测（issue #12）

跑两轮、中间隔 --gap 秒，对两轮结果做**方向相反的两种判定**：

  * spa8–spa13 —— token 是纯函数（无时间戳、无随机数），
    合格判据是 **两轮 96 个 token 逐字节全等**。变了才是出问题。
  * antispider8 —— token 里嵌了 unix 秒，
    合格判据是 **两轮 token 不同、但两轮都拿到 200 和 104 条数据**。
    不变反倒说明是把浏览器里抄来的固定值写死了。

把这两条混为一谈是这一阶段最容易犯的错，所以判定分开写、分别断言。

    python tools/run_all.py --gap 120
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

STAGE = Path(__file__).resolve().parent.parent
PY = sys.executable
SPA = ["spa8", "spa9", "spa10", "spa11", "spa12", "spa13"]


def run_case(case: str) -> dict:
    d = STAGE / case
    proc = subprocess.run([PY, "spider.py"], cwd=d, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"{case} 失败:\n{proc.stdout}\n{proc.stderr}")
    return {"stdout": proc.stdout.strip()}


def spa_payload(case: str) -> dict:
    f = STAGE / case / "data" / f"{case}_players.json"
    return json.loads(f.read_text(encoding="utf-8"))


def spa_tokens(case: str) -> list[str]:
    return [p["token"] for p in spa_payload(case)["players"]]


def spa_roster(case: str) -> list[list[str]]:
    """球员名册（不含 token）—— 六站同源，这份必须逐字段全等。"""
    return [
        [p["name"], p["image"], p["birthday"], p["height"], p["weight"]]
        for p in spa_payload(case)["players"]
    ]


def cross_site_check() -> dict:
    """六站横向对账。

    这一条是补上来的，起因是真出过事：spa8 的响应头没带 charset，requests 猜成
    ISO-8859-1，抓到的球员名全是乱码；但 Python 与 Node 参照实现拿到的是**同一份乱码**，
    token 对照照样 16/16 绿灯。纵向（同一站两个实现比）查不出输入错，
    横向（六站互比）一比就露馅 —— 六个站的名册本该一字不差。
    """
    rosters = {c: spa_roster(c) for c in SPA}
    keys = {c: spa_payload(c)["site_key"] for c in SPA}
    ref = rosters[SPA[0]]
    bad = [c for c in SPA if rosters[c] != ref]
    tokens_first = {c: spa_tokens(c)[0] for c in SPA}
    return {
        "名册逐字段全等": not bad,
        "不一致的站": bad,
        "名册条数": len(ref),
        "首位球员": ref[0][0] if ref else None,
        "各站 site_key": keys,
        "site_key 互不相同": len(set(keys.values())) == len(SPA),
        "同一球员在各站的 token": tokens_first,
        "token 互不相同（key 不同所致）": len(set(tokens_first.values())) == len(SPA),
    }


def as8_snapshot() -> dict:
    f = STAGE / "antispider8" / "data" / "antispider8_movies.json"
    d = json.loads(f.read_text(encoding="utf-8"))
    return {
        "count": d["count"],
        "fetched": d["fetched"],
        "no_token_status": d["no_token_status"],
        "statuses": sorted({t["status"] for t in d["request_trace"]}),
        "first_token_head": d["request_trace"][0]["token_head"],
        "generated_at": d["generated_at"],
    }


def one_pass(tag: str) -> dict:
    print(f"\n===== {tag} =====", flush=True)
    out: dict = {"spa_tokens": {}, "logs": {}}
    for c in SPA:
        print(f"--- {c}", flush=True)
        out["logs"][c] = run_case(c)["stdout"]
        out["spa_tokens"][c] = spa_tokens(c)
    print("--- antispider8", flush=True)
    out["logs"]["antispider8"] = run_case("antispider8")["stdout"]
    out["antispider8"] = as8_snapshot()
    return out


def main() -> int:
    gap = 120
    if "--gap" in sys.argv:
        gap = int(sys.argv[sys.argv.index("--gap") + 1])

    a = one_pass("第 1 轮")
    print(f"\n⏱ 等待 {gap}s 后复跑…", flush=True)
    time.sleep(gap)
    b = one_pass("第 2 轮")

    spa_verdict = {}
    for c in SPA:
        same = a["spa_tokens"][c] == b["spa_tokens"][c]
        spa_verdict[c] = {
            "token 条数": len(a["spa_tokens"][c]),
            "两轮逐字节全等": same,
            "判定": "PASS（纯函数 token，应当全等）" if same else "FAIL",
        }

    as8_same_token = a["antispider8"]["first_token_head"] == b["antispider8"]["first_token_head"]
    as8_ok = (
        not as8_same_token
        and a["antispider8"]["fetched"] == b["antispider8"]["fetched"] == 104
        and a["antispider8"]["statuses"] == b["antispider8"]["statuses"] == [200]
    )
    as8_verdict = {
        "第 1 轮": a["antispider8"],
        "第 2 轮": b["antispider8"],
        "两轮 token 不同": not as8_same_token,
        "两轮都抓满 104 条且全 200": (
            a["antispider8"]["fetched"] == b["antispider8"]["fetched"] == 104
            and a["antispider8"]["statuses"] == b["antispider8"]["statuses"] == [200]
        ),
        "无 token 时": f"HTTP {a['antispider8']['no_token_status']}",
        "判定": "PASS（token 现算，非硬编码）" if as8_ok else "FAIL",
    }

    cross = cross_site_check()

    result = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S %z"),
        "间隔秒": gap,
        "spa8-13（判据：两轮 token 全等）": spa_verdict,
        "antispider8（判据：两轮 token 不同且都成功）": as8_verdict,
        "六站横向对账（判据：名册全等、key 互异）": cross,
        "全部通过": (
            all(v["两轮逐字节全等"] for v in spa_verdict.values())
            and as8_ok
            and cross["名册逐字段全等"]
            and cross["site_key 互不相同"]
        ),
        "两轮完整日志": {"第1轮": a["logs"], "第2轮": b["logs"]},
    }
    out = STAGE / "evidence" / "run_all_twice.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + json.dumps({k: v for k, v in result.items() if k != "两轮完整日志"},
                            ensure_ascii=False, indent=2))
    print(f"\n✅ 写出 {out}")
    return 0 if result["全部通过"] else 1


if __name__ == "__main__":
    sys.exit(main())
