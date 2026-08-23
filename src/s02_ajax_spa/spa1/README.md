> issue: #5 · 案例: spa1 · 来源: https://spa1.scrape.center

# spa1 · 电影数据网站（Ajax 加载 + 页码翻页）

案例描述（逐字引自 <https://scrape.center/>，未做任何改写）：

> 电影数据网站，无反爬，数据通过 Ajax 加载，页面动态渲染，适合 Ajax 分析和动态页面渲染爬取。

## 一、接口分析过程

### 1. 先确认「HTML 里没有数据」

```bash
curl -s https://spa1.scrape.center/ | head -c 600
# -> <div id=app></div> + 三个 js bundle，一条电影数据都没有
```

页面是 Vue SPA，数据在 JS 里二次请求。**先别急着上浏览器**，看它请求了什么。

### 2. 从前端 bundle 里把接口挖出来（比开 DevTools 更可复现）

```bash
curl -s https://spa1.scrape.center/ | grep -o 'js/[a-z0-9.-]*\.js'
# js/app.17b3aaa5.js
# js/chunk-700f70e1.0548e2b4.js   <- 详情页组件
# js/chunk-d1db5eda.b564504d.js   <- 列表页组件
# js/chunk-vendors.683ca77c.js
```

`app.17b3aaa5.js` 里是 Vuex store 中的接口表：

```js
url:{index:"/api/movie",detail:"/api/movie/{id}"}
```

列表页组件（`chunk-d1db5eda.b564504d.js`）里是分页逻辑，一行说明全部问题：

```js
data:function(){return{loading:!1,total:null,page:parseInt(this.$route.params.page||1),limit:10,movies:null}}
// onFetchData:
this.$axios.get(this.$store.state.url.index,{params:{limit:this.limit,offset:(this.page-1)*this.limit}})
```

### 3. 参数含义

| 参数 | 含义 | 前端取值 | 实测 |
|---|---|---|---|
| `limit` | 本次要几条 | 固定 `10` | 可以调大，`limit=100` 一次返回 100 条 |
| `offset` | 跳过前几条 | `(page-1)*limit`，即页码 → 偏移的换算 | 任意整数；`offset >= count` 返回空 `results` |

返回体是标准的 DRF `LimitOffsetPagination`：

```json
{"count": 104, "results": [{"id":1,"name":"霸王别姬","alias":"Farewell My Concubine",
  "cover":"...","categories":["剧情","爱情"],"published_at":"1993-07-26",
  "minute":171,"score":9.5,"regions":["中国内地","中国香港"]}, ...]}
```

**页码这层是前端自己算出来的，服务端只认 offset。** 所以「翻页」对爬虫来说不存在，
只有 `offset += limit` 这一件事——这也是它和 spa3「下拉刷新」在 HTTP 层完全一样的原因。

详情接口 `/api/movie/{id}/` 在列表字段之外多给 `drama`（剧情简介）、`actors`（演员表
含角色与头像）、`directors`、`photos`。

## 二、怎么跑

```bash
PY=/path/to/.venv/bin/python
cd src/s02_ajax_spa/spa1

$PY spider.py                 # 接口模式：列表 + 全部详情（默认）
$PY spider.py --no-detail     # 只要列表
$PY spider.py --limit 100     # 把每页调到 100（2 次请求抓完 104 条）
$PY spider.py --mode render   # 渲染模式：解析 ssr1 的真实 DOM
$PY spider.py --mode compare  # 两种模式各跑一遍，逐字段比对
```

## 三、真实运行结果（2026-08-23）

| 运行 | 结果 |
|---|---|
| 接口模式（含详情） | **104 条**，11 次列表请求（offset 0→100，limit=10）+ 104 次详情请求 = **115 次请求，123.2s，下行 2849KB**，0 次重试 |
| 渲染模式（ssr1 DOM） | **100 条**，10 次请求，**4.1s**，下行 410KB |
| 两模式比对 | 100 条同名条目 **100 条字段完全一致，0 条差异**（比对字段：name/alias/categories/regions/score/published_at/minute） |

产出：

- `data/spa1_movies_api.json` —— 接口模式；完整 104 条含 actors/photos 后超过仓库
  500KB 上限，按纪律降级为「前 100 条 + 统计摘要」，且大字段折成键名摘要（62KB）
- `data/spa1_movies_render.json` —— 渲染模式 100 条（47KB，未截断）
- `data/spa1_mode_compare.json` —— 比对报告

## 四、渲染模式为什么打的是 ssr1

本阶段要求「不依赖浏览器」，所以没有 playwright/selenium 可用；而 spa1 自己的 HTML 是
空壳，没有 JS 就没有 DOM 可解析。ssr1（<https://ssr1.scrape.center>）是**同一份电影数据的
服务端渲染版本**，页面结构与 spa1 的 Vue 组件同源（同样的 `el-card` 卡片、同样的
`/detail/{id}` 链接、同样的 `.score` 节点），因此可以在零浏览器的前提下真实跑通
`Movie.from_dom()` 这条解析路径，并和接口模式对答案。

代码里两条路径的分工：

```python
Movie.from_api(obj)   # 取 JSON 的键
Movie.from_dom(card)  # 取 DOM 的文本：h2 -> "名 - alias"、button -> 分类、
                      # .info 行 -> 地区/片长/上映日、.score -> 评分
       ↓ 两者都调用 ↓
Movie.build(**raw)    # 唯一的清洗实现：空白压缩、"9.5"->9.5、
                      # "1993-07-26 上映"->"1993-07-26"、名称/别名拆分
```

比对 100/100 一致，说明这套复用不是嘴上说说：同一份 `build()` 把两种源头的数据规整成了
一模一样的记录。

## 五、坑

1. **`count=104` 但浏览器里只有 100 条。** 多出来的 4 条是数据库里的测试脏数据
   （`value` / `admin` / `测试` / `中文`，见 spa3 的运行输出，两站同库）。前端页码上限
   把它们挡住了，直连接口反而会抓到——**接口的 count 不等于页面能看到的条数**，
   落库前要按业务字段过滤。
2. **详情接口的 `photos` 字段极占体积。** 104 条详情原始 JSON 约 2.8MB，一条能有几十张
   图。仓库单文件 500KB 上限触发后，`common.save_json()` 会先降到 100 条，再把
   `actors/photos/drama` 折成「键名 + 长度」摘要，最后才落盘。
3. **`limit` 可以调大，但不要一把梭。** 实测 `limit=100` 正常返回；脚本默认仍用前端的
   `limit=10` 保持行为一致，只在需要时用 `--limit` 覆盖。
4. **别用 `page=` 猜参数。** 接口只认 `offset`；`?page=2` 会被忽略，静默返回第一页，
   猜参数比读 bundle 危险得多。
5. **JS bundle 的文件名带构建哈希**（`app.17b3aaa5.js`），站点重新发布后会变；解析时
   不要写死文件名，从首页 HTML 里 grep 出来。同理，DOM 解析不要依赖 `data-v-7f856186`
   这类 scoped 样式哈希。
