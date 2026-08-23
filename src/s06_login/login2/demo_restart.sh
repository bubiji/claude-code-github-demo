#!/usr/bin/env bash
# login2 两段式重启验证（issue #9）
#
# 证明「Session + Cookies 持久化，重启脚本无需重新登录」：
#   第 1 段：一个进程登录并把 cookie 写到 data/cookies.json，然后**退出**
#   第 2 段：另一个进程（PID 不同）只读 cookie，不再调用任何登录接口，直接取受保护页面
#
# 用法:
#   bash demo_restart.sh                 # 用仓库根的 .venv（自动定位），没有就退回 python3
#   bash demo_restart.sh /path/to/python # 显式指定解释器
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

echo "########## 第 1 段：登录并落盘 cookie（进程 A）##########"
"$PY" login2.py login
echo
echo "[demo] 进程 A 已退出（exit code $?）；磁盘上的 cookie 文件："
echo "[demo]   data/cookies.json  $(wc -c < data/cookies.json | tr -d ' ') 字节"
echo

echo "########## 第 2 段：全新进程，只读 cookie（进程 B）##########"
echo "[demo] 注意：下面这条命令里没有任何用户名/密码，login2.py fetch 也不会碰 /login"
"$PY" login2.py fetch --pages 3
echo

echo "########## 第 3 段：再起一个进程确认登录态（进程 C）##########"
"$PY" login2.py whoami
echo
echo "[demo] 三段 PID 各不相同 ⇒ cookie 确实跨进程复用，未重新登录。"
