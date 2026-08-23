#!/usr/bin/env python3
"""spa11 —— AAEncode

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
    site="spa11",
    obf="unwrap",
    source="main.js",
    label="AAEncode",
)

if __name__ == "__main__":
    raise SystemExit(pipeline.main(SPEC, HERE))
