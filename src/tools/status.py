#!/usr/bin/env python3
"""一屏看清全部阶段作业的进度（数据一律实时取自 GitHub，不读本地缓存）。

rule：任务状态只认 GitHub。本脚本只是只读视图，不写任何状态。

用法：
  python3 src/tools/status.py            # 总览
  python3 src/tools/status.py -w         # 每 60s 自动刷新
  python3 src/tools/status.py 4          # 只看某个 issue 的细节
"""
import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone, timedelta

REPO = "bubiji/claude-code-github-demo"
MILESTONE = "今晚清盘 2026-08-23"
JST = timezone(timedelta(hours=9))

C = {"g": "\033[32m", "y": "\033[33m", "r": "\033[31m", "b": "\033[34m",
     "d": "\033[2m", "0": "\033[0m", "B": "\033[1m"}


def gh(*args):
    p = subprocess.run(["gh", *args], capture_output=True, text=True)
    if p.returncode != 0:
        print(f"gh 失败：{p.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    return p.stdout


def api(path, **kw):
    return json.loads(gh("api", path, "--paginate", *sum([["-f", f"{k}={v}"] for k, v in kw.items()], [])))


def issues():
    out = gh("issue", "list", "-R", REPO, "--label", "stage", "--state", "all",
             "--limit", "50", "--json", "number,title,state,body")
    return sorted(json.loads(out), key=lambda i: i["number"])


def prs():
    out = gh("pr", "list", "-R", REPO, "--state", "all", "--limit", "100",
             "--json", "number,state,body,headRefName,statusCheckRollup,mergedAt")
    return json.loads(out)


def boxes(body):
    done = len(re.findall(r"^\s*- \[x\]", body or "", re.M | re.I))
    todo = len(re.findall(r"^\s*- \[ \]", body or "", re.M))
    return done, done + todo


def pr_for(num, allprs):
    pat = re.compile(rf"(?i)\b(?:closes|fixes|resolves|refs)\s+#{num}\b")
    for p in allprs:
        if pat.search(p.get("body") or ""):
            return p
    return None


def ci_of(p):
    if not p:
        return "-"
    roll = p.get("statusCheckRollup") or []
    if not roll:
        return f"{C['d']}无{C['0']}"
    bad = [c for c in roll if (c.get("conclusion") or "").upper() not in ("SUCCESS", "NEUTRAL", "")]
    run = [c for c in roll if (c.get("status") or "").upper() in ("IN_PROGRESS", "QUEUED")]
    if run:
        return f"{C['y']}跑着{C['0']}"
    return f"{C['r']}fail{C['0']}" if bad else f"{C['g']}pass{C['0']}"


def permalinks(num):
    cs = api(f"/repos/{REPO}/issues/{num}/comments")
    n = sum(len(re.findall(r"/(?:blob|tree)/[0-9a-f]{40}/", c.get("body") or "")) for c in cs)
    stale = sum(len(re.findall(r"/(?:blob|tree)/main/", c.get("body") or "")) for c in cs)
    return n, stale


def w(s):
    """显示宽度：CJK 算 2 列，ANSI 转义不算。"""
    plain = re.sub(r"\033\[[0-9;]*m", "", s)
    return sum(2 if ord(c) > 0x1100 else 1 for c in plain)


def pad(s, n):
    return s + " " * max(1, n - w(s))


def bar(done, total, width=24):
    f = 0 if not total else round(width * done / total)
    color = C["g"] if done == total else C["y"] if done else C["d"]
    return f"{color}{'█' * f}{C['d']}{'░' * (width - f)}{C['0']}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("issue", nargs="?", type=int)
    ap.add_argument("-w", "--watch", action="store_true")
    a = ap.parse_args()

    while True:
        if a.watch:
            print("\033[2J\033[H", end="")
        render(a.issue)
        if not a.watch:
            break
        import time
        time.sleep(60)


def render(only):
    iss, allprs = issues(), prs()
    now = datetime.now(JST)
    dead = now.replace(hour=23, minute=59, second=59, microsecond=0)
    left = dead - now
    hrs = left.total_seconds() / 3600

    done_i = sum(1 for i in iss if i["state"] == "CLOSED")
    cases_done = sum(boxes(i["body"])[0] for i in iss)
    cases_all = sum(boxes(i["body"])[1] for i in iss)

    print(f"\n{C['B']}🎯 {MILESTONE}{C['0']}   "
          f"{C['d']}现在 {now:%m-%d %H:%M} JST · 距 24:00 还剩 "
          f"{C['0']}{C['y'] if hrs < 3 else C['g']}{int(hrs)}h{int(left.total_seconds() % 3600 // 60)}m{C['0']}")
    print(f"   issue {bar(done_i, len(iss))} {done_i}/{len(iss)} 完成"
          f"    勾选项 {cases_done}/{cases_all}\n")

    hdr = ("  " + pad("#", 5) + pad("阶段", 30) + pad("状态", 12)
           + pad("勾选", 9) + pad("PR", 13) + pad("CI", 8) + "链接")
    print(C["B"] + hdr + C["0"])
    print(C["d"] + "  " + "─" * 84 + C["0"])

    for i in iss:
        if only and i["number"] != only:
            continue
        n = i["number"]
        title = re.sub(r"^\[阶段 \d+\] ", "", i["title"])
        d, t = boxes(i["body"])
        p = pr_for(n, allprs)
        if i["state"] == "CLOSED":
            st = f"{C['g']}✅ 已完成{C['0']}"
        elif p and p["state"] == "OPEN":
            st = f"{C['b']}🔵 待合并{C['0']}"
        elif d:
            st = f"{C['y']}🟡 进行中{C['0']}"
        else:
            st = f"{C['d']}⚪️ 未开始{C['0']}"
        prs_ = "-" if not p else (f"#{p['number']} {'已合' if p['mergedAt'] else p['state'].lower()}")
        pl, stale = permalinks(n) if (d or p) else (0, 0)
        link = "-" if not pl else f"{C['g']}✓{pl}条{C['0']}"
        if stale:
            link += f" {C['r']}⚠{stale}条blob/main{C['0']}"
        print("  " + pad(str(n), 5) + pad(title, 30) + pad(st, 12)
              + pad(f"{d}/{t}", 9) + pad(prs_, 13) + pad(ci_of(p), 8) + link)

    print(f"\n{C['d']}  milestone: https://github.com/{REPO}/milestone/1"
          f"\n  刷新：python3 src/tools/status.py -w{C['0']}\n")


if __name__ == "__main__":
    main()
