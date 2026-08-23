> issue: #5 · 案例: spa5 · 来源: https://spa5.scrape.center

# spa5 · 图书网站（Ajax 加载 + 翻页 + 大批量）

案例描述（逐字引自 <https://scrape.center/>，未做任何改写）：

> 图书网站，无反爬，数据通过 Ajax 加载，有翻页，适合大批量动态页面渲染抓取。

## 一、接口分析过程

### 1. 找接口

```bash
curl -s https://spa5.scrape.center/ | grep -o 'js/[a-z0-9.-]*\.js'
# js/app.b93891e2.js             <- Vuex store
# js/chunk-50522e84.6b3e24aa.js  <- 详情页组件
# js/chunk-f52d396c.f8f41620.js  <- 索引页组件
# js/chunk-vendors.a02ff921.js
```

`app.b93891e2.js`：

```js
url:{index:"/api/book",detail:"/api/book/{id}",proxy:"/proxy/{url}"}
```

索引页组件 `chunk-f52d396c.f8f41620.js`：

```js
data:function(){return{loading:!1,total:null,
   page:parseInt(this.$route.params.page||1),limit:18,books:null,imageHeight:null}}
// onFetchData: params:{limit:this.limit,offset:(this.page-1)*this.limit}
// 分页控件：el-pagination，layout:"total, prev, pager, next"
```

### 2. 参数含义

```bash
curl -s "https://spa5.scrape.center/api/book/?limit=18&offset=0"
# {"count":9040,"results":[{"id":"7952978","name":"Wonder",
#   "authors":["R. J. Palacio"],"cover":"https://cdn.scrape.center/book/s27252687.jpg",
#   "score":"8.8"}, ...]}
```

| 参数 | 含义 | 前端 | 实测 |
|---|---|---|---|
| `limit` | 每页条数 | **18**（三行 × 六列的封面墙） | 可调到 100，一次返回 100 条 |
| `offset` | 跳过条数 | `(page-1)*18` | 与 spa1/spa3/spa4 完全同族 |

- 全库 **9040** 条。按前端的 18/页 是 503 页；把 `limit` 提到 100 只要 **91 次请求**。
- 详情接口 `/api/book/{id}/` 多给：`comments`、`translators`、`publisher`、`tags`、
  `url`（豆瓣原书页）、`isbn`、`page_number`、`price`、`introduction`、`catalog`、
  `published_at`、`updated_at`。
- `/proxy/{url}` 实测只返回 SPA 空壳（history 模式的 404 兜底），**不是可用的代理接口**，
  别在它身上浪费时间。

## 二、怎么跑

```bash
PY=/path/to/.venv/bin/python
cd src/s02_ajax_spa/spa5

$PY spider.py                              # 全量 9040 条（limit=100，91 次请求）
$PY spider.py --limit 18                   # 复刻前端每页 18 条的翻页行为
$PY spider.py --max-items 360              # 只抓前 360 条
$PY spider.py --mode detail --sample 20    # 抽样补抓详情
$PY spider.py --mode render                # 渲染模式回放 + 与接口模式逐字段比对
```

## 三、真实运行结果（2026-08-23）

| 运行 | 结果 |
|---|---|
| 全量列表（`limit=100`） | **9040 条 / 91 次请求 / 63.1s / 下行 1460KB / 0 次重试** |
| 详情抽样（`--mode detail --max-items 500 --sample 20`） | 20 条详情，25 次请求，14.0s |
| 渲染模式比对 | 9040 条重放解析，**8976 条字段完全一致，64 条有差异**（差异原因见下） |

产出：

- `data/spa5_books.json` —— 全量 9040 条超过仓库 500KB 上限，按纪律降级为
  「前 100 条 + 统计摘要」（28KB），meta 里带 `total_records: 9040` 与 top 作者/评分统计
- `data/spa5_book_details_sample.json` —— 20 条详情样本（54KB，未截断）
- `data/spa5_mode_compare.json` —— 渲染模式比对报告

## 四、渲染模式在这里是「本地重放」，不是抓页面

本阶段要求不依赖浏览器（无 playwright/selenium），而 spa5 的 HTML 是空壳、书目也没有
服务端渲染的孪生站（不像 spa1 有 ssr1）。所以 `--mode render` 做的是**本地重放**：

1. 把索引页组件的 render 函数（`chunk-f52d396c.f8f41620.js` 里那段
   `el-card.item > router-link > img.cover` + `h3.name` + `p.authors`）照抄成模板；
2. 用接口拿到的记录渲染出「浏览器里会生成的那份 DOM」；
3. 再用 `Book.from_dom()` 把它解析回记录，与 `Book.from_api()` 的结果逐字段比对。

**这是重放，不是抓取所得的页面**，产出文件的 meta 里也这么标注了。它验证的是
「DOM 适配器与接口适配器落到同一个 `build()`、产出同一种记录」这条闭环。

### 64 条差异全部来自模板本身丢信息

```
api: {'authors': ['钟基、李先银、王身刚译注']}
dom: {'authors': ['钟基', '李先银', '王身刚译注']}

api: {'authors': ['[日] 虚渊玄', 'Fate/Zero']}
dom: {'authors': ['[日] 虚渊玄', 'Fate', 'Zero']}
```

页面模板把作者数组 `join(",")` 成一个字符串，作者名里本来就含 `,`、`、`、`/` 的条目，
在 DOM 里再也分不回原来的边界。这不是解析 bug，是**渲染过程有损**：接口是权威数据源，
页面是它的一个投影。能做的只有如实记录差异（比对报告里逐条列出），并在需要精确
作者字段时以接口为准。占比 64/9040 ≈ **0.7%**。

## 五、坑

1. **`id` 是字符串不是整数**（`"7952978"`）。当成 int 存会丢失前导零之类的信息，
   join 时也容易类型不匹配。
2. **`score` 是字符串**（`"8.8"`），排序前必须转 float——`common.to_float()` 统一干这件事。
3. **`authors` 里带脏空白**：接口返回值形如 `"\n            董桥"`，直接落库会带一大串
   空格和换行。`clean_text()` 统一压缩空白，这也是「解析逻辑只写一份」的直接收益。
4. **9040 条别用前端的 limit=18 去抓**：那是 503 次请求；`limit=100` 只要 91 次，
   对站点更友好，也快得多。
5. **大批量必须限速**：脚本串行 + 0.35s 间隔 + 抖动，91 次请求跑了 63s；这是刻意的，
   不要为了快把间隔调到 0。
6. **别指望 `/proxy/{url}`**：看着像个代理接口，实测只回 SPA 空壳。
7. **落盘要有降级策略**：9040 条完整 JSON 远超仓库 500KB 上限，`common.save_json()`
   自动降级为「前 100 条 + 统计摘要」，并在 meta 里写明总量，不至于让人误以为只抓到 100 条。
