# claude-code-github-demo

演示 **Claude Code 与 GitHub 协作**的实验仓库，学习内容是 [scrape.center](https://scrape.center/) 的 54 个爬虫练习案例。

## 快速进入

- **学习计划总纲** → [issue #16](https://github.com/bubiji/claude-code-github-demo/issues/16)
- **12 个阶段 issue** → [`label:stage`](https://github.com/bubiji/claude-code-github-demo/issues?q=is%3Aissue+label%3Astage)
- **仓库规则（代码必须关联 issue）** → [`CLAUDE.md`](CLAUDE.md)
- **计划详述** → [`doc/学习计划.md`](doc/学习计划.md)
- **案例原件（54 条逐字照录）** → [`doc/原件_scrape-center案例清单.md`](doc/原件_scrape-center案例清单.md)

## 这个仓库在演示什么

一条「issue 驱动」的协作闭环，全程由 Claude Code 在终端里完成：

```
抓取案例清单 → 排出学习计划 → 生成 12 个阶段 issue
      ↓
先有 issue → 分支 case/sNN-<案例名> → commit 带 refs #N
      ↓
PR 写 Closes #N → CI 校验关联 → 合入
      ↓
在 issue 下贴代码 Permalink（从 issue 能找到代码）
```

核心约束是**双向可达**：从 issue 能找到代码，从代码能找到 issue。规则全文见 `CLAUDE.md`，CI 实现见 `.github/workflows/issue-link.yml`。

## 目录结构

```
.
├── CLAUDE.md            # 仓库规则：代码必须关联 issue
├── doc/                 # 计划与案例原件存档
├── src/
│   ├── tools/           # 基建脚本：抓案例 / 生成 issue / 校验关联
│   └── sNN_*/           # 各阶段案例代码（随进度新增）
└── .github/             # PR 模板 + 关联校验 CI
```

## 基建脚本

```bash
python3 src/tools/fetch_cases.py -o doc/scrape-center-cases.raw.json   # 抓取案例原件
python3 src/tools/gen_plan_issues.py                                   # 生成阶段 issue 正文
bash    src/tools/create_plan_issues.sh --apply                        # 提交为 GitHub issue（幂等）
python3 src/tools/check_issue_link.py --commits-only                   # 本地校验 commit 关联
```

## 练习伦理

scrape.center 是案例作者公开提供的专用练习平台，本仓库代码只针对该平台；限流类案例请按其规则控速，不要指向未获授权的站点。
