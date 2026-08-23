# 仓库规则（claude-code-github-demo）

本仓库是「Claude Code × GitHub 协作」实验场，学习内容来自 [scrape.center](https://scrape.center/) 的 54 个爬虫练习案例。计划总纲见 issue #16。

---

## 一、核心纪律：任何代码提交必须关联 issue

**约束目标是「双向可达」——从 issue 能找到代码，从代码能找到 issue。** 缺任一方向即视为不合格。

### 1. 先有 issue，后有代码

动手前必须存在对应 issue。没有合适的就先建一个（学习案例挂到对应阶段 issue，工程杂务另开 `chore` issue）。**禁止先写完再补 issue。**

### 2. 分支命名带 issue 线索

| 场景 | 分支名 | 例 |
|---|---|---|
| 案例练习 | `case/sNN-<案例名>` | `case/s01-ssr1` |
| 工程杂务 | `chore/<简述>-<issue号>` | `chore/ci-link-check-17` |
| 文档 | `docs/<简述>-<issue号>` | `docs/plan-16` |

### 3. commit message 必须带 issue 引用

每条 commit 的正文（或标题）必须出现 `refs #<issue号>`；能直接关掉 issue 的用 `Closes #<issue号>`。

```
feat(ssr1): 列表页翻页抓取 + 详情页字段解析

- 分页参数走 ?page=N，共 10 页
- 输出 data/ssr1.json，字段与页面一一对应

refs #4
```

这一条不是形式主义：GitHub 会把带引用的 commit 自动挂到 issue 时间线上，**这是「从 issue 找到代码」的主要通道**。

### 4. 代码走 PR，PR 正文写关联

- 代码变更一律走 Pull Request，不直推 `main`
- PR 正文必须含 `Closes #<issue号>`（完成该 issue）或 `Refs #<issue号>`（部分推进）
- 纯文档小修可直推 `main`，但 commit 仍须带 `refs #<issue号>`

CI（`.github/workflows/issue-link.yml`）会校验 PR 的关联，缺失直接失败。

### 5. 代码位置固定，且自带 issue 出处

- 实现代码一律在 `src/` 下，**不散落在仓库根目录**
- 学习案例：`src/sNN_<阶段名>/<案例名>/`，如 `src/s01_ssr/ssr1/`
- 每个案例目录必须有 `README.md`，**首行写明 issue 与案例出处**：

```markdown
> issue: #4 · 案例: ssr1 · 来源: https://ssr1.scrape.center
```

这是「从代码找到 issue」的通道——任何人打开任一代码目录，第一行就知道它归属哪个 issue。

### 6. 合入后回帖 Permalink

PR 合入后，在对应 issue 下贴一条代码永久链接（GitHub 上按 `y` 得到带 commit sha 的 Permalink），格式：

```
✅ ssr1 完成 → https://github.com/bubiji/claude-code-github-demo/blob/<sha>/src/s01_ssr/ssr1/
说明：分页 10 页共 100 条，落盘 data/ssr1.json
```

分支会被删、`main` 会漂移，**只有带 sha 的 Permalink 是永久有效的**，所以不要贴 `blob/main/...`。

### 7. issue 侧的进度维护

- 案例 checkbox 做完就勾，**不攒到最后一次性勾**
- 验收标准全勾 + 代码 Permalink 已贴 → 才可 close issue

---

## 二、给 Claude Code 的执行要求

在本仓库工作时：

1. **动手写代码前先确认 issue 号**。用户没给就先问、或用 `gh issue list` 找，找不到就建一个再动手——不允许无归属地写代码。
2. **每次 commit 自动补 `refs #<issue号>`**，不要等用户提醒。
3. **建案例目录时同时生成 `README.md` 首行的 issue/来源标注**，不许留空。
4. **PR 创建时正文自动带 `Closes #<issue号>`**。
5. **收尾时主动把 Permalink 贴回 issue**（`gh issue comment`），并勾掉对应 checkbox。
6. 引用 scrape.center 的案例描述时**逐字照抄，不改写不润色**；自己的分析写在原文之外。

## 三、目录结构

```
.
├── CLAUDE.md            # 本规则
├── README.md            # 仓库说明
├── doc/                 # 计划、原件存档
│   ├── 学习计划.md
│   └── scrape-center-cases.raw.json   # 54 个案例原件（逐字保真）
├── src/
│   ├── tools/           # 仓库基建脚本（抓案例、生成 issue、校验关联）
│   └── sNN_*/           # 各阶段案例代码
└── .github/             # PR 模板与关联校验 CI
```

## 四、练习伦理

scrape.center 是案例作者公开提供的**专用练习平台**，本仓库的抓取代码只针对该平台。不要把这些代码指向未获授权的站点；限流类案例（antispider5/6/7）请按其规则控速，不要用于压测。
