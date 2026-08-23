> issue: #5 · 案例: spa4 · 来源: https://spa4.scrape.center

# spa4 · 新闻网站索引（Ajax 加载 + 通用正文提取）

案例描述（逐字引自 <https://scrape.center/>，未做任何改写）：

> 新闻网站索引，无反爬，数据通过 Ajax 加载，无页码翻页，适合 Ajax 分析和动态页面渲染抓取以及智能页面提取分析。

## 一、接口分析过程

### 1. 找接口

```bash
curl -s https://spa4.scrape.center/ | grep -o 'js/[a-z0-9.-]*\.js'
# js/app.a87de5b6.js
# js/chunk-f3b5152a.15f8fa10.js   <- 索引页组件
# js/chunk-vendors.0005a229.js

curl -s "https://spa4.scrape.center/api/news/?limit=10&offset=0"
# {"count":451370,"results":[{"id":35654431,"title":"...","code":"370572026",
#   "url":"https://news.sina.com.cn/c/2020-10-21/doc-iiznctkc6705317.shtml",
#   "source":null,"domain":"news.sina.com.cn","website":"新浪新闻",
#   "thumb":"http://n.sinaimg.cn/...png","published_at":"2020-10-20T17:23:00Z",
#   "updated_at":"2020-10-20T17:30:16.274131Z"}, ...]}
```

参数与 spa1/spa3/spa5 同族：`limit`（每页条数，前端固定 10，实测可到 100）+
`offset`（跳过条数）。**索引接口只给元数据，正文在 `url` 指向的外站**——这就是本案例
「智能页面提取分析」的由来。

### 2. 前端的翻页逻辑，以及它的一个 bug

```js
data:function(){return{loading:!1,count:null,
   page:parseInt(this.$route.params.page||1),limit:10,news:null,
   previous:null,next:null}},
computed:{disabled:function(){return!this.next}},
// onFetchData: params:{limit:this.limit,offset:(this.page-1)*this.limit}
//   .then(s => { var e=s.data, a=e.results, n=e.count, i=e.next, o=e.previous; ... })
```

前端把停止条件挂在响应的 `next` 字段上（DRF 分页默认会给 `next`/`previous` 两个链接），
可这个接口的响应里**根本没有这两个字段**：

```bash
curl -s "https://spa4.scrape.center/api/news/?limit=10&offset=0" \
  | python3 -c "import json,sys;print(list(json.load(sys.stdin).keys()))"
# ['count', 'results']
```

于是 `next` 恒为 `undefined` → `disabled` 恒为 `true` → 无限滚动指令一开始就是禁用状态，
**浏览器里这 45 万条新闻只能看到最前面的 10 条**。爬虫不受影响：我们按 `count` +
`offset` 自己推进就行。

### 3. 索引取样策略

索引头部清一色是同一家站点，顺着 `offset=0` 爬出来的样本没有域名多样性，
「通用提取」就等于只在一家站上验证过。所以脚本提供 `--spread N`：在 `[0, count)`
上等距取 N 个 offset 各拉一页，抽样时再按域名分层轮转，保证每家站都被取到。

## 二、通用正文提取怎么做的（不写死选择器）

实现见 `../common.py::extract_main_text()`。**全文件没有一个 `#artibody` / `.post-body`
之类的站点专用选择器**，只用结构统计：

1. 先物理删掉不可能是正文的标签：`script/style/noscript/iframe/svg/canvas/form/input/
   button/select/nav/header/footer/aside/figure/figcaption`。
2. 对每个块级候选（`article/main/section/div/td/body`）算四个量：

   | 量 | 定义 | 直觉 |
   |---|---|---|
   | `text_len` | 节点内 `<p>` 段落总字数（无 `<p>` 时退回全节点文本） | 正文字多 |
   | `link_len` | 节点内 `<a>` 锚文本字数 | 导航/推荐位几乎全是链接 |
   | `link_ratio` | `link_len / text_len` | > 0.5 直接淘汰 |
   | `density` | `text_len / (后代标签数 + 1)` | 正文是「字多标签少」，列表是「字少标签多」 |

3. `score = text_len × (1 − link_ratio) × (0.5 + min(density, 40) / 40)`，取最高分节点。
4. 按 `<p>` 边界还原段落；没有 `<p>` 就按换行切。
5. 失败时**给出可判定的原因**（`body_chars` / `n_p_tags`），区分「HTML 里压根没正文」
   与「有文本但都是导航」，而不是笼统报个 false。

标题/时间/站点名同样走通用信号：`og:title` → `<h1>` → `<title>`，
`article:published_time` / `publishdate` 等 meta。

## 三、接口模式与渲染模式复用同一份解析逻辑

```python
NewsItem.from_api(obj)          # 索引接口的 JSON
NewsItem.from_dom(soup, url)    # 外站原文页面的真实 DOM（og:* / h1 / <title>）
        ↓ 两条路都调用 ↓
NewsItem.build(**raw)           # 唯一的清洗实现：空白压缩、URL 缺失时从 url 反推 domain …
```

脚本对每篇抽样原文**同时**跑两条路，再比对两侧标题（宽松比较，因为外站 `<title>`
常带站点后缀）。本次运行 **15/17 一致**，不一致的两篇是外站标题被改写过（索引落库时的
标题与页面当前标题不同），属于数据本身的差异，不是解析差异。

## 四、怎么跑

```bash
PY=/path/to/.venv/bin/python
cd src/s02_ajax_spa/spa4

$PY spider.py                          # 索引 200 条 + 抽 25 篇原文提取
$PY spider.py --spread 20 --sample 24  # 跨全库等距取 20 页，按域名分层抽 24 篇
$PY spider.py --mode index --index-items 500   # 只抓索引
```

## 五、真实运行结果（2026-08-23）

```
① 索引：GET /api/news/?limit=10&offset=N（跨全库等距取样 20 页）
   count=451370，取回 200 条 → data/spa4_news_index.json（103KB，未截断）
② 原文：按域名分层抽 24 篇（sina/163/ifeng 各 8），逐篇通用正文提取
```

| 指标 | 数值 |
|---|---|
| 索引总量（接口声明） | **451370** 条 |
| 本次取回索引 | **200** 条 / 21 次请求 |
| 抽样原文 | **24** 篇（3 个域名各 8 篇） |
| 正文提取成功 | **17** 篇 |
| 取回失败（外站链接已失效） | 2 篇（news.163.com，重试 3 次仍 4xx/5xx） |
| HTML 内无正文（正文由 JS 二次加载） | 5 篇（全部是 news.ifeng.com） |
| 正文字数 | 最短 120 / 最长 9350 / 平均 **1981** |
| 标题一致（接口 vs DOM） | **15/17** |
| 整轮 | **49 次请求 · 54.1s · 下行 2045KB · 6 次重试** |

分域名成功率（写在 `data/spa4_articles_sample.json` 的 meta 里）：

| 域名 | 抽样 | 提取成功 | 取回失败 | 平均字数 |
|---|---|---|---|---|
| news.sina.com.cn | 8 | 8 | 0 | 1954 |
| news.163.com | 8 | 6 | 2 | 1908 |
| news.ifeng.com | 8 | 3 | 0 | 2199 |

**同一套打分逻辑、零改动，跨三家新闻站都选中了正确的正文容器**（选出的容器一律是
`<div>`，链接密度 0.0–0.066），这就是「不写死选择器」的价值。

## 六、坑

1. **索引接口的 `next`/`previous` 被后端去掉了，而前端还在用它判断「有没有下一页」**，
   导致页面上永远只有 10 条。看前端逻辑时不能假设它是对的——以接口实际返回为准。
2. **正文不在 HTML 里的站，通用提取救不了。** 5 篇 ifeng 页面 `body_chars=0`、`<p>` 标签
   0 个，正文由 JS 二次拉取。识别方法就是上面的诊断字段；解决方向是「再挖一层接口」
   （ifeng 有自己的内容 API）或上浏览器渲染——本阶段要求不依赖浏览器，故如实记为
   失败并写明原因，不掩盖。
3. **外站链接会腐烂。** 语料是 2020 年的新闻，2 篇 163 链接已经取不回来。所以抓取器必须
   逐条容错（本脚本单条失败只记录不中断），且要把失败率写进产出。
4. **`published_at` 两侧格式不同**：接口给 ISO8601（`2020-10-20T17:23:00Z`），页面 meta
   五花八门。`NewsItem.build()` 只做空白规整不强行解析，避免把不确定的东西编成确定的。
5. **抽样不分层就等于没验证通用性**：不按域名分层，24 篇能全是 sina。
6. **礼貌抓外站**：默认间隔 0.5s + 抖动，串行，失败退避重试 ≤3 次。外站不是练习平台，
   更要克制。
