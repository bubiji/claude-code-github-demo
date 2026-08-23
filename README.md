# claude-code-github-demo

演示 **Claude Code 与 GitHub 协作**的实验仓库。

## 这个仓库用来做什么

作为一次现场实验的试验场，验证 Claude Code 在真实 GitHub 工作流里能做到哪一步：

- 建仓、初始化、首次提交与推送
- issue 的创建、拆解与状态流转
- 分支 / PR / 代码评审
- GitHub Actions（CI）
- 仓库配置（label、branch protection 等）

## 目录结构

```
.
├── README.md      # 本说明
├── .gitignore     # 忽略本地环境文件
├── src/           # 实现代码（脚本 / 程序）
└── doc/           # 过程记录与说明文档
```

## 约定

- 实现代码统一放 `src/`，不散落在仓库根目录
- 文档放 `doc/`
- 本地环境文件（`.claude/settings.local.json`、`.DS_Store` 等）不入库
