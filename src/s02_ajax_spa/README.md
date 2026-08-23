> issue: #5 · 阶段: 阶段 2 Ajax 与动态渲染 · 来源: https://scrape.center/

# 阶段 2：Ajax 与动态渲染（spa1 / spa3 / spa4 / spa5）

四个案例全部**不依赖浏览器**（无 playwright / selenium），直连 XHR 接口。

```
src/s02_ajax_spa/
├── common.py          # 三层共用逻辑：传输 / 分页 / 解析
├── spa1/              # 有页码翻页 —— 接口模式 + 渲染模式（ssr1 孪生站 DOM）+ 两模式比对
├── spa3/              # 下拉到底刷新 —— 偏移量推进轨迹 + 前端硬上限截断分析
├── spa4/              # 新闻索引 —— 通用正文提取（无站点选择器）
└── spa5/              # 大批量翻页 —— 9040 条书目全量抓取
```

## 一张图看懂 common.py

```
                        ┌──────────────── 传输层 ────────────────┐
                        │ PoliteSession  串行 + 固定间隔 + 抖动   │
                        │                重试退避 / 请求计数      │
                        └────────────────────┬──────────────────┘
                                             │
                        ┌──────────────── 分页层 ────────────────┐
                        │ offset_pages()  limit/offset 通用分页器 │
                        │ 四个站同一套 DRF LimitOffsetPagination  │
                        └────────────────────┬──────────────────┘
                                             │
   接口模式 (XHR JSON) ──► from_api() ──┐    │    ┌── from_dom() ◄── 渲染模式 (DOM)
                                        ▼    ▼    ▼
                                   Movie/Book/NewsItem.build()
                              （唯一的清洗实现：空白压缩、类型转换、
                                日期规整、名称/别名拆分、去重）
                                             │
                                     统一的 dataclass 记录
                                             │
                                   save_json()（500KB 降级）
```

## 验收标准逐条落点

| 验收标准（issue #5 原文） | 落点 |
|---|---|
| spa1/spa5 通过接口分页参数抓全数据，不依赖浏览器 | `spa1/spider.py --mode api`（104 条 / 11 次列表请求）、`spa5/spider.py`（9040 条 / 91 次请求）；全程 requests，无浏览器 |
| spa3 无限下拉的加载触发条件讲清楚（偏移/游标各是什么） | `spa3/README.md` +（真实运行产出）`spa3/data/spa3_scroll_trace.json`：每一跳的触发来源、offset、返回条数、剩余量 |
| spa4 新闻索引页做到通用正文提取，不写死选择器 | `common.extract_main_text()`：文本密度 + 链接密度打分，全文件无站点专用选择器 |
| 同一份解析逻辑同时能被「接口模式」和「渲染模式」复用 | `Movie/Book/NewsItem` 的 `from_api()` / `from_dom()` 两个适配器 → 同一个 `build()`；spa1 用 ssr1 的真实 DOM 跑通并与接口模式**逐字段比对 100/100 一致** |

## 「同一份解析逻辑两种模式复用」是怎么落地的

**复用的是 `build()`，不是 `from_api()`/`from_dom()`。** 两个适配器只负责「把源数据摊平
成同一组原始字段」，一个从 JSON 键取值，一个从 DOM 节点取文本；之后的空白压缩、
`"9.5"` → `9.5`、`"1993-07-26 上映"` → `1993-07-26`、`"霸王别姬 - Farewell My Concubine"`
拆成 name/alias、分类去重——全部只有 `build()` 一份实现。

因此下游（去重、统计、落盘）拿到的永远是同一个 dataclass，不知道也不关心数据来自哪条路。

三个案例分别验证了这条路的不同段：

- **spa1**：接口模式 104 条 vs 渲染模式（ssr1 服务端渲染孪生站，同一份电影数据、
  同一套 el-card 模板）100 条，逐字段比对 **100/100 完全一致**（`spa1/data/spa1_mode_compare.json`）。
- **spa4**：`NewsItem.from_api()` 吃索引接口 JSON，`NewsItem.from_dom()` 吃**外站新闻原文**
  的真实 DOM（走 og:*/h1/`<title>` 等通用信号），两侧标题一致率写在
  `spa4/data/spa4_articles_sample.json` 的 meta 里。
- **spa5**：`--mode render` 用站点自己的 Vue render 函数把接口记录**本地重放**成 DOM 再
  解析回来做闭环比对；这是重放不是抓取，README 里已明确标注。

## 运行

```bash
PY=/path/to/.venv/bin/python           # 需 requests / beautifulsoup4 / lxml
cd src/s02_ajax_spa/spa1 && $PY spider.py --mode compare
cd ../spa3 && $PY spider.py
cd ../spa4 && $PY spider.py --spread 20 --sample 24
cd ../spa5 && $PY spider.py            # 全量 9040 条
```

## 抓取伦理

scrape.center 是案例作者公开提供的练习平台。所有脚本**串行**请求（并发写死为 1），
默认间隔 0.35–0.5s 并带随机抖动，失败退避重试上限 3 次，绝不压测；spa4 会打开外站
新闻原文，同样按此节奏，只读不提交。
