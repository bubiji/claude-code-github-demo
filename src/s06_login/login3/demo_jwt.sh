#!/usr/bin/env bash
# login3 JWT 全流程演示（issue #9）
#
#   ① login   取 token
#   ② inspect 拆 header / payload / signature，dump exp
#   ③ fetch   正常路径：exp 还早，**不刷新**
#   ④ fetch --refresh-margin 999999
#             强制走刷新分支：真调 /api/refresh 换新 token 再抓
#
# 用法:
#   bash demo_jwt.sh                 # 自动找仓库根的 .venv，没有就 python3
#   bash demo_jwt.sh /path/to/python
set -euo pipefail

cd "$(dirname "$0")"
REPO_ROOT="$(cd ../../.. && pwd)"
if [ $# -ge 1 ]; then
  PY="$1"
elif [ -x "$REPO_ROOT/.venv/bin/python" ]; then
  PY="$REPO_ROOT/.venv/bin/python"
else
  PY="python3"
fi

echo "########## ① login ##########"
"$PY" login3.py login
echo
echo "########## ② inspect ##########"
"$PY" login3.py inspect
echo
echo "########## ③ fetch（正常路径，不该刷新）##########"
"$PY" login3.py fetch --pages 2
echo
echo "########## ④ fetch --refresh-margin 999999（强制走刷新分支）##########"
"$PY" login3.py fetch --pages 2 --refresh-margin 999999
