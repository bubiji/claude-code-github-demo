> issue: #4 · 案例: ssr1 · 来源: https://ssr1.scrape.center

# ssr1 —— 基础 SSR 抓取

案例描述（**逐字引自** https://scrape.center/，未改写）：

> 电影数据网站，无反爬，数据通过服务端渲染，适合基本爬虫练习。

数据全在服务端渲染好的 HTML 里，`requests` 拿文本、`BeautifulSoup` + `lxml` 解析即可，
不需要浏览器、不需要找接口。本目录是阶段 1 的地基，ssr2/ssr3/ssr4 只在连接层各加一道
花样（证书 / 认证 / 慢响应），解析与落盘逻辑全部复用 [`../common.py`](../common.py)。

## 怎么跑

```bash
# 仓库根目录已有 .venv（requirements.txt 装好 requests / beautifulsoup4 / lxml）
cd src/s01_ssr/ssr1
python crawl.py                 # 串行 + 0.3s 礼貌间隔，约 65 秒
python crawl.py --no-detail     # 只抓 10 个列表页，约 12 秒
python crawl.py --workers 4     # 想快一点
```

参数：`--workers`（并发线程数，默认 1）、`--delay`（每请求后的间隔，默认 0.3s）、
`--timeout`（默认 30s）、`--no-detail`（跳过详情页）、`--out`（落盘目录）。

## 抓到什么（2026-08-23 真实运行）

```
[ssr1] 抓取完成
  记录数     : 100（列表页 10 页 / 详情页 100 个）
  请求数     : 111，失败 0
  单请求均值 : 0.25s
  总耗时     : 65.43s（列表 5.98s + 详情 59.45s）
  串行预估   : 27.21s（111 请求 × 均值 0.25s）
  落盘       : ssr1.json 482.8KB / ssr1.csv 365.6KB / ssr1.summary.json
```

- 111 个请求 = 10 个列表页 + 1 个探测第 11 页（确认翻到头）+ 100 个详情页。
- 落盘：
  - `data/ssr1.json` —— 100 条完整记录，一行一条（合法 JSON 数组，可逐行 diff）
  - `data/ssr1.csv` —— 同样 100 条的表格视图（列表字段用 `、` 连接，演员写成 `姓名(角色)`）
  - `data/ssr1.summary.json` —— 字段完整度、评分/时长分布、类别与地区计数、本次运行耗时

字段（14 个）：`id / title / name_cn / name_en / categories / regions / minutes /
published_at / score / directors / actors / drama / cover / detail_url`

字段完整度（100 条中非空条数，取自 summary）：

| 字段 | 非空 | 字段 | 非空 |
|---|---|---|---|
| id / title / name_cn / name_en | 100 | score / cover / detail_url | 100 |
| categories / regions / minutes | 100 | directors / actors / drama | 100 |
| **published_at** | **96** | | |

数据面貌：评分 8.8~9.5（均值 8.97）、时长 45~238 分钟（均值 128.8）、
上映年份 1939~2020、演员条目共 5723 条（平均每片 57 人）；
类别 top5 剧情 68 / 爱情 28 / 奇幻 25 / 冒险 24 / 喜剧 18；
地区 top4 美国 51 / 中国香港 14 / 英国 14 / 日本 12。

## 关键实现要点

1. **翻页靠「解析不出条目」终止，不写死 10 页。** `crawl()` 一页页往后翻，某页 0 条即停，
   所以站方加页也不用改代码。
2. **列表页 + 详情页两跳合并。** 列表页给概览（评分/类别/地区/时长/上映日期/封面），
   详情页补剧情简介、导演、完整演员表；`merge()` 以详情页为准、缺字段回落列表页。
3. **字段按形态识别，不按位置取。** 见下面「坑」第 2 条。
4. **单条详情失败不拖垮整轮。** 详情页抛异常时记进 `stats.failures`，该片回落成列表页字段，
   收尾统一报告失败数并以非 0 退出——不静默吞掉。
5. **礼貌抓取。** 默认串行 + 每请求 0.3s 间隔 + 固定 User-Agent；这是练习站，不做压测。

## 遇到的坑

1. **第 11 页不是空列表，是 HTTP 500。**
   ```
   GET /page/10 → 200，10 条
   GET /page/11 → 500，0 条
   ```
   要是直接 `raise_for_status()`，翻页会以异常收场；要是把 500 当故障重试，就死循环。
   处理成「`/page/` 上的 500 = 没有下一页」，其他 5xx 照常抛。

2. **`div.info` 里的字段不定项，按位置取必串位。** 页面上是这样：
   ```html
   <div class="info"><span>中国内地、中国香港</span><span> / </span><span>171 分钟</span></div>
   <div class="info"><span>1993-07-26 上映</span></div>
   ```
   但 100 部里有 **4 部没有上映日期**（#9 楚门的世界、#30 上帝之城、#43 小鞋子、#68 风之谷），
   拿「第二个 info 的第一个 span」当日期，这 4 部就会把地区读成日期。
   改成按形态判：命中 `\d+ 分钟` 是时长，命中 `\d{4}-\d{2}-\d{2}` 是日期，剩下的是地区。

3. **中英标题不能按 `-` 拆。** 站上标题形如 `霸王别姬 - Farewell My Concubine`，
   但真有片名自带连字符：
   - `无敌破坏王 - Wreck-It Ralph`（英文名里有 `-`）
   - `大话西游之大圣娶亲 - A Chinese Odyssey Part Two - Cinderella`（出现两次 ` - `）

   所以按 **` - `（空格-连字符-空格）的第一次出现** 切一刀，切完不再管后面的连字符。

4. **别把选择器绑在 `data-v-*` 上。** 详情页的类别/信息块上带的是 `data-v-7f856186`
   ——和列表页组件同一个哈希，而外层 `#detail` 是 `data-v-63864230`。这类 scoped CSS 哈希
   随前端构建变化，绑上去下次发版就全断。只用语义类名（`.el-card.item` / `a.name` /
   `p.score` / `div.drama` / `div.actor`）。

5. **`indent=2` 会顶穿 500KB 落盘上限。** 演员表平均 57 人，缩进全花在方括号上：
   同一份 100 条数据 `indent=2` 是 **703KB**，紧凑分隔符是 **494KB**。
   本仓库规定单文件超 500KB 就只留前 100 条，为了不无谓触发截断，`common._dump()`
   改成「一行一条记录」——既是合法 JSON，又保留了逐行可读/可 diff。

6. **抓下来的数据要能被验证。** ssr1~ssr4 是同一套站，四份数据除 `detail_url` 的 host
   外应当完全相同，跑 [`../verify.py`](../verify.py) 对指纹即可；对不上说明某条连接路径
   （并发、认证）悄悄丢了数据。
