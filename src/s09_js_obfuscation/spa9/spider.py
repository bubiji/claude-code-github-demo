#!/usr/bin/env python3
"""spa9 —— eval 混淆（Dean Edwards packer，p,a,c,k,e,r）

issue #12 / 阶段 9。抓取逻辑在 ../pipeline.py（六站同源，只有 site key 与混淆手法不同）。

    python spider.py            # 跑一次
    python spider.py --twice 60 # 隔 60s 跑两次，验证 token 可复现
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import pipeline  # noqa: E402

SPEC = pipeline.SiteSpec(
    site="spa9",
    obf="unwrap",
    source="inline",
    label="eval 混淆（Dean Edwards packer，p,a,c,k,e,r）",
)

if __name__ == "__main__":
    raise SystemExit(pipeline.main(SPEC, HERE))
