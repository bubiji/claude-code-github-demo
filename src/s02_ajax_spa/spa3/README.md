> issue: #5 · 案例: spa3 · 来源: https://spa3.scrape.center

# spa3 · 电影数据网站（Ajax 加载 + 下拉到底刷新）

案例描述（逐字引自 <https://scrape.center/>，未做任何改写）：

> 电影数据网站，无反爬，数据通过 Ajax 加载，无页码翻页，下拉至底部刷新，适合 Ajax 分析和动态页面渲染爬取。

## 一、接口分析过程

### 1. 找接口

```bash
curl -s https://spa3.scrape.center/ | grep -o 'js/[a-z0-9.-]*\.js'
# js/app.49205faa.js            <- Vuex store：接口表
# js/chunk-d5d475e6.4ddc209f.js <- 列表页组件：下拉加载逻辑
# js/chunk-vendors.77daf991.js
```

`app.49205faa.js`：

```js
url:{index:"/api/movie",detail:"/api/movie/{id}"}
```

抓一把看看：

```bash
curl -s "https://spa3.scrape.center/api/movie/?limit=10&offset=0"
# {"count":104,"results":[{"id":1,"name":"霸王别姬",...,"actors":[...],"drama":"..."}]}
```

**注意**：spa3 的列表接口直接把详情字段（`actors` / `drama` / `directors` / `photos`）
一并返回了，不像 spa1 需要再打详情接口——104 条列表就有 2.8MB。

### 2. 「下拉到底刷新」的加载触发条件（本案例的重点）

前端源码 `chunk-d5d475e6.4ddc209f.js`（逐字摘录）：

```js
// 模板：整个 #index 挂了 element-ui 的无限滚动指令
a("div",{directives:[{name:"infinite-scroll",rawName:"v-infinite-scroll",
   value:t.onLoadMore,expression:"onLoadMore"}],
   attrs:{id:"index","infinite-scroll-disabled":"disabled"}}, ...)

// 状态
data:function(){return{loading:!1,total:null,
   page:parseInt(this.$route.params.page||1),limit:10,movies:null}}

// 停止条件
computed:{disabled:function(){return 10===this.page}}

// 首屏
mounted:function(){this.onFetchData()}

// 每次触发
methods:{onLoadMore:function(){this.page+=1,this.onFetchData()},
 onFetchData:function(){ ... this.$axios.get(this.$store.state.url.index,
   {params:{limit:this.limit,offset:(this.page-1)*this.limit}})
   .then(function(s){ ... t.movies=t.movies?t.movies.concat(e):e, t.total=i })}}
```

逐条拆开：

| 问题 | 答案 |
|---|---|
| **触发条件是什么** | element-ui 的 `v-infinite-scroll` 指令：容器滚动到「距底部 < 阈值」时调用 `onLoadMore()`。首屏那次不是滚动触发，是 `mounted()` 直接发的。 |
| **游标是什么** | 没有游标（没有 `next` / `cursor` / `since_id`）。前端维护一个整数 `page`，每次 `page += 1`。 |
| **偏移量怎么算** | `offset = (page - 1) * limit`，`limit` 恒为 10。所以请求序列是 `offset=0,10,20,…`——和 spa1 的「点页码」在 HTTP 层**一模一样**，区别只是谁来触发这次请求。 |
| **数据怎么拼** | `movies = movies.concat(results)`，追加而非替换，所以页面越拉越长。 |
| **怎么判断到底了** | 前端的判断是 `disabled: page === 10`（写死的硬上限）——拉到第 10 页就禁用指令，不再加载。**接口自己的信号是 `count`**：当 `offset + len(results) >= count` 就是真的到底了；再往后请求会返回 `results: []`。 |

爬虫应当用**接口信号**而不是前端的硬上限：

```python
# common.offset_pages() 的终止条件（三选一命中即停）
1. results 为空                     -> 后端明确没有更多
2. offset + len(results) >= count   -> 已覆盖 count 声明的全量
3. 已产出条数 >= max_items          -> 调用方自设上限
```

## 二、怎么跑

```bash
PY=/path/to/.venv/bin/python
cd src/s02_ajax_spa/spa3

$PY spider.py                 # scroll 模式：limit=10，逐跳模拟下拉，记录轨迹
$PY spider.py --mode bulk     # bulk 模式：limit=100，2 次请求抓完
$PY spider.py --max-items 30  # 只要前 30 条
```

## 三、真实运行结果（2026-08-23）

scroll 模式（默认，`limit=10`）：

```
step=1   offset=0    本次  10 条 累计  10/104 剩余 94     <- mounted() 首屏
step=2   offset=10   本次  10 条 累计  20/104 剩余 84     <- 第 1 次下拉到底
...
step=10  offset=90   本次  10 条 累计 100/104 剩余  4
step=11  offset=100  本次   4 条 累计 104/104 剩余  0     <- 浏览器永远走不到这一跳
```

- **104 条 / 11 次请求 / 16.9s / 下行 2821KB / 0 次重试**
- 产出 `data/spa3_movies.json`（原始 104 条含 photos 超过仓库 500KB 上限，按纪律降级为
  前 100 条 + 统计摘要，62KB）
- 产出 `data/spa3_scroll_trace.json`：每一跳的**触发来源、发出的 offset、返回条数、
  累计、剩余量、是否还有下一跳**，即「无限下拉」的完整推进轨迹

## 四、坑

1. **前端写死 `page === 10` 停止，比接口的 `count` 早停。** 实测：浏览器里下拉到死也
   只能出 100 条，接口 `count=104`。够不着的 4 条是数据库里的测试脏数据：
   `value`、`admin`、`测试`、`中文`。
   → 教训一：**别拿页面上数出来的条数当全量**；教训二：直连接口反而会拿到页面上不存在的
   脏数据，落库前要按业务字段过滤。
2. **`offset` 要按「实际返回条数」推进，不是按 `limit` 推进。** 最后一页只回 4 条，如果
   还按 `offset += limit` 走就会跳过数据。`common.offset_pages()` 用的是
   `offset += len(results)`。
3. **无限下拉 ≠ 需要浏览器。** 滚动只是触发器；HTTP 层还是 limit/offset。真正需要浏览器的
   是那种游标签在 DOM 里、或请求签名由 JS 现算的站（本阶段 spa4 的外站原文里就有这种）。
4. **列表接口已经含详情字段**，别再去打一遍 `/api/movie/{id}/`——那是 104 次无谓请求。
   先看清楚一个响应里到底给了什么再动手。
5. **`limit` 调大是最省事的提速手段**：`--mode bulk`（limit=100）2 次请求就抓完同样的
   104 条。但脚本默认保持 `limit=10`，为的是让轨迹文件如实反映浏览器行为。
