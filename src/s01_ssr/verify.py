#!/usr/bin/env python3
"""交叉校验：ssr1~ssr4 是同一套电影站，抓下来的数据除了 host 之外应当逐字节相同。

issue: #4 · 案例来源: https://scrape.center/

这是本阶段的「验收自检」——四个案例走的是四条不同的连接路径（明文校验 / 关闭证书
校验 / Basic Auth / 5 秒延迟 + 并发），如果解析或调度哪里出了岔子（比如并发下漏抓、
认证失败被当成空页跳过），四份数据就对不上。对得上才说明连接层的花样没污染数据层。

    python verify.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CASES = ["ssr1", "ssr2", "ssr3", "ssr4"]


def load(case: str) -> list[dict] | None:
    p = HERE / case / "data" / f"{case}.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def fingerprint(records: list[dict]) -> str:
    """去掉 detail_url（唯一按 host 变化的字段）后取指纹。"""
    stripped = [{k: v for k, v in r.items() if k != "detail_url"} for r in records]
    blob = json.dumps(stripped, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()


def main() -> int:
    seen: dict[str, list[str]] = {}
    for case in CASES:
        recs = load(case)
        if recs is None:
            print(f"  {case}: 未落盘（跳过）")
            continue
        fp = fingerprint(recs)
        seen.setdefault(fp, []).append(case)
        print(f"  {case}: {len(recs)} 条，指纹 {fp[:16]}")

    if not seen:
        print("没有任何数据可校验。", file=sys.stderr)
        return 2
    if len(seen) == 1:
        cases = next(iter(seen.values()))
        print(f"\n✓ {'/'.join(cases)} 数据完全一致（已排除 detail_url 的 host 差异）")
        return 0
    print("\n✗ 各案例数据不一致：", file=sys.stderr)
    for fp, cases in seen.items():
        print(f"  {fp[:16]} ← {', '.join(cases)}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
