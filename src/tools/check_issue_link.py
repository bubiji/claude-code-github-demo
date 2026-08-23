#!/usr/bin/env python3
"""校验「代码提交必须关联 issue」（CLAUDE.md 第一章），供 CI 与本地钩子调用。

两项检查：
  1. PR 正文含 `Closes #N` / `Refs #N`
  2. 本次 PR 的每条 commit message 含 `#N` 引用

环境变量（GitHub Actions 注入）：PR_BODY / BASE_SHA / HEAD_SHA。
本地跑可只校验 commit：
    BASE_SHA=origin/main HEAD_SHA=HEAD python3 src/tools/check_issue_link.py --commits-only
"""
import argparse
import os
import re
import subprocess
import sys

REF = re.compile(r"(?i)\b(?:closes|close|closed|fixes|fix|fixed|resolves|resolve|resolved|refs|ref)\s+#(\d+)")
BARE = re.compile(r"#(\d+)")


def commit_messages(base, head):
    out = subprocess.run(
        ["git", "log", "--format=%H%x1f%B%x1e", f"{base}..{head}"],
        capture_output=True, text=True, check=True).stdout
    for rec in out.split("\x1e"):
        rec = rec.strip()
        if not rec:
            continue
        sha, _, msg = rec.partition("\x1f")
        yield sha[:8], msg.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--commits-only", action="store_true")
    a = ap.parse_args()

    fails = []

    if not a.commits_only:
        body = os.environ.get("PR_BODY") or ""
        if not REF.search(body):
            fails.append("PR 正文缺少 issue 关联：需要 `Closes #N`（完成）或 `Refs #N`（部分推进）")
        else:
            print(f"✓ PR 正文关联 issue #{REF.search(body).group(1)}")

    base, head = os.environ.get("BASE_SHA"), os.environ.get("HEAD_SHA")
    if base and head:
        n = 0
        for sha, msg in commit_messages(base, head):
            n += 1
            if not BARE.search(msg):
                first = msg.splitlines()[0] if msg else "(空)"
                fails.append(f"commit {sha} 缺少 issue 引用（需 `refs #N`）：{first}")
        print(f"✓ 检查了 {n} 条 commit")
    else:
        print("· 未提供 BASE_SHA/HEAD_SHA，跳过 commit 检查")

    if fails:
        print("\n✗ 未通过「代码必须关联 issue」检查（规则见 CLAUDE.md 第一章）：", file=sys.stderr)
        for f in fails:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print("\n✓ 关联检查通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
