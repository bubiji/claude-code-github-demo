#!/usr/bin/env bash
# 把 gen_plan_issues.py 生成的阶段正文提交为 GitHub issue。
#
#   bash src/tools/create_plan_issues.sh            # 预演，只打印将建哪些 issue
#   bash src/tools/create_plan_issues.sh --apply    # 真正创建
#
# 幂等：同名标题的 issue 已存在就跳过，不重复建。
set -euo pipefail

REPO="${REPO:-bubiji/claude-code-github-demo}"
DIR="${DIR:-build/issues}"
APPLY="${1:-}"

titles=(
  "[阶段 1] 基础请求与解析（SSR 服务端渲染）"
  "[阶段 2] Ajax 与动态渲染"
  "[阶段 3] 协议专题：HTTP/2 与 WebSocket"
  "[阶段 4] 基础反爬：指纹、偏移与字体"
  "[阶段 5] 频率限制与代理池"
  "[阶段 6] 模拟登录：加密表单、Session、JWT"
  "[阶段 7] 验证码专题"
  "[阶段 8] JavaScript 逆向入门"
  "[阶段 9] JS 混淆对抗"
  "[阶段 10] AST 还原高级混淆"
  "[阶段 11] WASM 逆向"
  "[阶段 12] App 抓包与逆向"
)

existing=$(gh issue list -R "$REPO" --state all --limit 200 --json title --jq '.[].title')

for i in "${!titles[@]}"; do
  n=$((i+1))
  body="$DIR/$(printf 'stage%02d.md' "$n")"
  t="${titles[$i]}"
  if grep -Fxq "$t" <<<"$existing"; then
    echo "跳过（已存在）：$t"
    continue
  fi
  if [ "$APPLY" != "--apply" ]; then
    echo "将创建：$t   ← $body"
    continue
  fi
  url=$(gh issue create -R "$REPO" --title "$t" --body-file "$body" \
        --label stage --label scrape-center)
  echo "✓ $t  →  $url"
done
