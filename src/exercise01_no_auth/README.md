> issue: #1 · 案例: ssr1 · 来源: https://ssr1.scrape.center

# 练习作业 1 · 不需要验证的网站信息获取

这是一个**给初学者看的最小可用示例**：一个脚本、一条直线，把「不需要验证的网站」这件事从**判定**讲到**取数**。
不是全量抓取工程（那是 issue #4 / #5 的活），这里的目标是**看得懂**。

案例描述（逐字引自 <https://scrape.center/>，未作任何改写）：

> 电影数据网站，无反爬，数据通过服务端渲染，适合基本爬虫练习。

## 一、什么叫「不需要验证」

不用登录、不用 Cookie/Token、不用验证码、不用加密参数 —— **一个匿名的 HTTP GET 就能把数据拿回来**。

但「不需要验证」和「拿得到数据」是两件事：有的站不要验证，可数据压根不在 HTML 里。
所以脚本的第 0 步不是抓，是**体检**：先看要不要验证、数据在不在 HTML 里，再决定怎么抓。

判定只看三个可观察的事实，不靠猜：

| 观察到的现象 | 结论 |
|---|---|
| `401` + 响应头 `WWW-Authenticate` | **需要验证**（HTTP 认证），本作业不碰 |
| `200`，且 HTML 里能解析出条目卡片 | 免验证，数据直接在 HTML 里 → 直接抓 |
| `200`，但 HTML 里没有条目 | 免验证，但数据是 Ajax 二次加载 → 得另找接口 |

## 二、跑起来

```bash
# 解释器：仓库根目录的 .venv（已装 requests / bs4 / lxml）
cd src/exercise01_no_auth

python spider.py --probe                 # 第 0 步：免验证体检，不抓数据
python spider.py                         # 主链路：抓 ssr1 全部 10 页列表
python spider.py --pages 2               # 只抓前 2 页（课堂演示够用）
python spider.py --pages 10 --detail 3   # 列表 + 前 3 条详情页（本仓库里的数据就是这条命令跑出来的）
```

参数就四个：`--probe`（只体检）、`--pages N`（抓前 N 页）、`--detail N`（额外抓前 N 条详情）、`--delay`（请求间隔，默认 1 秒）。

## 三、第 0 步：免验证体检（实测输出）

`python spider.py --probe` —— 2026-08-23 实跑：

```
== 第 0 步：免验证体检（先判断要不要验证，再决定抓不抓）==

[ssr1] https://ssr1.scrape.center/page/1
     HTTP 200  耗时 0.51s  41667 字节
     → 免验证，且 HTML 里直接有 10 条数据 → 可以抓

[ssr4] https://ssr4.scrape.center/page/1
     HTTP 200  耗时 5.89s  41667 字节
     → 免验证，且 HTML 里直接有 10 条数据 → 可以抓

[spa1] https://spa1.scrape.center/
     HTTP 200  耗时 0.25s  952 字节
     → 免验证，但 HTML 里没有数据（Ajax 动态渲染）→ 要去找它的接口

[ssr3] https://ssr3.scrape.center/page/1
     HTTP 401  耗时 0.44s  172 字节
     → 需要验证：Basic realm="Authentication Required"

结论：ssr1 / ssr4 / spa1 都不需要验证；ssr3 需要 HTTP Basic Auth，不在本作业范围内。
      本作业的主链路选 ssr1 —— 免验证，且数据直接躺在 HTML 里，一步到位。

  已落盘 data/probe_report.json  (1.7 KB)
```

四行数字里有三个值得停一下：

- **ssr4 耗时 5.89s vs ssr1 的 0.51s** —— 差的正是案例描述里那「每个响应增加了 5 秒延迟」。慢不等于要验证。
- **spa1 只有 952 字节** —— 一个空壳 `<div id=app>`，解析出 0 条数据。免验证，但这条路走不通，得去找它的 Ajax 接口（那是 issue #5 干的事）。
- **ssr3 返回 401，响应体只有 172 字节** —— 服务端在响应头里明说了要 `Basic` 认证。脚本看到这一行就收手：**不带用户名密码、不做任何绕过**，它只是用来当「需要验证长什么样」的对照组。

对照组的四条案例描述都逐字存进了 `data/probe_report.json` 的 `description_verbatim` 字段。

## 四、主链路：请求 → 解析 → 落盘

脚本里就这三段，各自一个函数，名字直接对应：

| 段 | 函数 | 干什么 |
|---|---|---|
| 请求 | `fetch()` | 一个 `session.get()` + `raise_for_status()`。免验证站点的「请求」就这么朴素 |
| 解析 | `parse_list_page()` / `parse_detail_page()` | 用 BeautifulSoup 按 CSS 选择器把字段抠出来 |
| 落盘 | `save_json()` | `ensure_ascii=False` 写 JSON，中文按原样存 |

### 页面长什么样

ssr1 用 Element UI 渲染，一部电影 = 一张 `.el-card.item` 卡片：

```html
<div class="el-card item ...">
  <a href="/detail/1" class="name"><h2>霸王别姬 - Farewell My Concubine</h2></a>
  <div class="categories"><button><span>剧情</span></button>...</div>
  <div class="m-v-sm info"><span>中国内地、中国香港</span><span> / </span><span>171 分钟</span></div>
  <div class="m-v-sm info"><span>1993-07-26 上映</span></div>
  <p class="score">9.5</p>
</div>
```

**两个初学者最容易踩的坑，代码里都写了注释：**

1. **别用 `:nth-of-type(2)` 取第二行 info。** CSS 的 `nth-of-type` 数的是「同标签的第几个」，
   而卡片里 `.categories` 也是 `div`，会把序号顶偏，取到的是第一行。老老实实
   `card.select(".m-v-sm.info")` 拿到列表再按下标取。
2. **站上真有几部片子没有上映日期**（《楚门的世界》《上帝之城》《小鞋子》《风之谷》，第二行 info 是空的）。
   那是**数据本身缺**，不是解析写错了。这种情况记 `None`，别记成 `""` —— 后者会让下游误以为「抓到了一个空值」。

### 抓到的字段

| 字段 | 例 | 来源 |
|---|---|---|
| `id` | `"1"` | `a.name` 的 href 末段 `/detail/1` |
| `name` / `alias` | `霸王别姬` / `Farewell My Concubine` | h2 文本按 `" - "` 切开 |
| `categories` | `["剧情", "爱情"]` | `.categories button` |
| `regions` / `minutes` | `["中国内地", "中国香港"]` / `"171 分钟"` | 第一行 info |
| `published_at` | `"1993-07-26 上映"` | 第二行 info（可能为 `null`） |
| `score` | `"9.5"` | `p.score` |
| `cover` | 图片 URL | `img.cover` |
| `detail_url` | 详情页链接 | 拼 BASE + href |

加 `--detail N` 时，前 N 条再补三个来自详情页的字段：`drama`（剧情简介）、`directors`、`actors`。

## 五、实测运行结果

`python spider.py --pages 10 --detail 3` —— 2026-08-23 实跑：

```
== 主链路：抓取 https://ssr1.scrape.center 前 10 页 ==

  第  1 页  10 条  累计  10 条  (0.41s)  https://ssr1.scrape.center/page/1
  第  2 页  10 条  累计  20 条  (0.25s)  https://ssr1.scrape.center/page/2
  第  3 页  10 条  累计  30 条  (0.23s)  https://ssr1.scrape.center/page/3
  第  4 页  10 条  累计  40 条  (0.17s)  https://ssr1.scrape.center/page/4
  第  5 页  10 条  累计  50 条  (0.28s)  https://ssr1.scrape.center/page/5
  第  6 页  10 条  累计  60 条  (0.24s)  https://ssr1.scrape.center/page/6
  第  7 页  10 条  累计  70 条  (0.23s)  https://ssr1.scrape.center/page/7
  第  8 页  10 条  累计  80 条  (0.34s)  https://ssr1.scrape.center/page/8
  第  9 页  10 条  累计  90 条  (0.31s)  https://ssr1.scrape.center/page/9
  第 10 页  10 条  累计 100 条  (0.23s)  https://ssr1.scrape.center/page/10

  再抓前 3 条的详情页（剧情简介 / 导演 / 演员）：
    #  1 霸王别姬  导演 陈凯歌  演员 30 位  简介 269 字
    #  2 这个杀手不太冷  导演 吕克·贝松  演员 80 位  简介 230 字
    #  3 肖申克的救赎  导演 弗兰克·德拉邦特  演员 66 位  简介 318 字

  共 100 条，用时 17.4s
  已落盘 data/ssr1_movies.json  (52.2 KB)
```

| 指标 | 实测值 |
|---|---|
| 列表页 | 10 页，每页 10 条，共 **100 条**（100 个唯一 id，无重复） |
| HTTP 请求 | 13 次（10 个列表页 + 3 个详情页） |
| 总耗时 | **17.4 秒**；其中 13 秒是礼貌间隔的 `sleep`，真正花在网络+解析上的约 4.4 秒（10 个列表页合计 2.69 秒） |
| 单页耗时 | 0.17 ~ 0.41 秒 |
| 落盘 | `data/ssr1_movies.json` **52.2 KB**、`data/probe_report.json` 1.7 KB |
| 字段完整度 | name / alias / score / minutes / categories / regions / cover 均 100/100；`published_at` **96/100**（4 条站上本来就没有） |
| 详情字段 | 前 3 条含 `drama` / `directors` / `actors`（演员数分别 30 / 80 / 66，是站上真实列出的张数） |

## 六、目录

```
src/exercise01_no_auth/
├── README.md                # 本文件
├── spider.py                # 全部代码（体检 + 请求/解析/落盘）
└── data/
    ├── probe_report.json    # 第 0 步的免验证体检报告（含四条案例原文）
    └── ssr1_movies.json     # 100 条电影数据，前 3 条含详情页字段
```

## 七、和 issue #4 / #5 的分工

- **#4（阶段 1 · SSR）** 做 ssr1–ssr4 的完整工程；**#5（阶段 2 · Ajax）** 已做完 spa1/spa3/spa4/spa5 的接口分析。
- **本作业（#1）** 是教学 demo：单文件、只依赖 requests + BeautifulSoup、不跨目录 import、几十秒出结果。
  独有的角度是第 0 步那个 **probe**（先判定要不要验证再决定抓不抓），#4/#5 都不做这层。

## 八、抓取伦理

scrape.center 是案例作者公开提供的**专用练习平台**。本脚本：亮明 User-Agent、每次请求之间默认间隔 1 秒、
只读不写、不并发、不压测；对需要验证的 ssr3 只看状态码就停手，不带凭证、不做绕过。
不要把这些代码指向未获授权的站点。
