> issue: #8 · 案例: antispider7 · 来源: https://antispider7.scrape.center

# antispider7 · IP 与账号双重频率限制

案例描述（逐字引自 <https://scrape.center/>，未做任何改写）：

> 限制单个 IP 访问频率 5 分钟最多 10 次，同时限制单个账号访问频率 5 分钟最多 10 次，如果过多则会封禁 IP 或账号 10 分钟。

## 一、双重限制意味着什么

antispider5 只限 IP，换账号没用；antispider6 只限账号，换 IP 没用。到了 antispider7，
两条路**同时**堵死：

| 手段 | antispider5 | antispider6 | antispider7 |
|---|---|---|---|
| 换出口 IP（代理池） | 有用 | 无用 | 只解一半 |
| 换账号（注册新号） | 无用 | 有用 | 只解一半 |
| **降低请求数** | 有用 | 有用 | **有用** |

所以这个案例把人逼到唯一那条对两边都成立的路上：**别发那么多请求。**

## 二、接口分析

首页是纯 Vue SPA（1215 字节骨架 + `<div id=app></div>`），数据全走 XHR。
直接请求接口拿到 401：

```
GET /api/book/?limit=18&offset=0
→ HTTP 401
  WWW-Authenticate: JWT realm="api"
  {"detail":"Authentication credentials were not provided."}
```

这个站的 Django 开着 `DEBUG = True`，随便请求一个不存在的路径，404 页面会把整份
URLconf 打印出来——比翻前端 JS 快得多：

```
Using the URLconf defined in core.urls, Django tried these URL patterns, in this order:
    healthz [name='healthz']
    api/login [name='login']
    api/refresh [name='refresh']
    api/register [name='register']
    api/book/
    api/book/<pk>/
    api/comment/
    api/comment/<pk>/
```

注意 `api/login` **没有结尾斜杠**——带斜杠请求 `/api/login/` 会 404。

登录拿 JWT（练习站公开凭据 `admin` / `admin`，已核实可用）：

```
POST /api/login   {"username": "admin", "password": "admin"}
→ 200 {"token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...."}

后续请求带  Authorization: jwt <token>
```

> token 是真实凭据，本仓库是公开仓库，落盘时经 `common.redact()` 脱敏为
> `eyJ0eX…7Ng1SY（已脱敏，原长 211）`。公开的 `admin/admin` 可以写进代码，
> 换来的 token 不行。

## 三、关键发现：接口没有设 max_limit

分页是 DRF 的 `LimitOffsetPagination`，前端源码写死 `limit: 18`。全量 9040 条，
按前端的翻法要 503 个请求：

```
504 个请求（含登录） / 10 次 * 300 秒 = 15120 秒 = 4.2 小时（理论下界）
按 35 秒安全间隔    = 17605 秒 = 4.9 小时
```

**但是配额数的是请求次数，不是字节数。** 实测该接口没有配置 DRF 的 `max_limit`：

```
GET /api/book/?limit=2000&offset=0
→ 200，329039 字节，results 里实打实 2000 条
```

于是全量只要 5 个请求：

| 抓法 | 请求数 | 理论下界 | 35s 间隔预算 | **实测耗时** |
|---|---:|---:|---:|---:|
| 前端 limit=18 | 504 | 252 min | 293 min | 未跑（做不完） |
| **limit=2000** | **6** | **3.0 min** | **2.9 min** | **3.1 min** |

请求数降到 1/100，耗时从 4.9 小时降到 3.1 分钟。这是本阶段最值钱的一条经验：
**在按次计费的地方，先问「最少几次能拿完」，再问「能不能快一点」。**

## 四、实测结果

```
$ .venv/bin/python src/s05_rate_proxy/antispider7/spider.py

[19:30:58] 登录成功，token=eyJ0eX…7Ng1SY（已脱敏，原长 211）
offset=0    +2000 → 2000/9040
offset=2000 +2000 → 4000/9040
offset=4000 +2000 → 6000/9040
offset=6000 +2000 → 8000/9040
offset=8000 +1040 → 9040/9040

完成：9040/9040 条，用时 3.1 分钟，限流命中 0 次
```

| 指标 | 值 |
|---|---|
| 抓取范围 | **全量** 9040 / 9040 本 |
| 请求数 | 6（1 登录 + 5 翻页） |
| 最小间隔 / 窗口容量 | 35 秒 / 9 次每 300 秒 |
| 耗时 | 3.1 分钟 |
| 下行字节 | 1 492 858 |
| 限流命中（429/403/拦截页） | **0** |
| 退避重试 | 0 |
| 被封禁 | **否**（全程未触发） |

窗口占用峰值 6/9——配额只用到声明值 10 次的 60%。

## 五、落盘

`data/antispider7_books.json`。完整 JSON 约 1.5 MB，超过仓库约定的 500 KB 上限，
按 `common.save_json()` 降级为**前 100 条 + 统计摘要**（`_truncated` 字段记录了
降级原因与真实总数 9040）。

`summary` 字段的统计是对**全量 9040 条**算的，不是对截断后那 100 条算的——
降级之后它就是全量数据留在仓库里的唯一证据：

```
n = 9040
score: 有值 8697 条（343 条无评分）；min 4.2 / max 10.0 / mean 8.181 / median 8.3
       分档 4分:11  5分:103  6分:623  7分:2302  8分:4025  9分:1628  10分:5
authors: 去重 6393 位；出现最多的是 鲁迅 200、新经典文化 146、[加拿大]亦舒 120、
         [日]东野圭吾 109、幾米 101 ……
```

> `authors` 原样保留了接口返回值里的换行与缩进（`"\n            鲁迅"`）——那是
> 站点自己的数据，不做清洗，以免把「脏」洗成「看起来干净但已经不是原件」。

字段：`id` / `name` / `authors` / `cover` / `score`。

## 六、跑法

```bash
PY=/Users/deanlee/Documents/Claude/Projects/git_github/.venv/bin/python

$PY spider.py --plan            # 只算预算，不发请求
$PY spider.py                   # 全量 9040（limit=2000，6 个请求，约 3 分钟）
$PY spider.py --limit 18        # 复刻前端翻页，仅供对照（约 4.9 小时，不建议真跑）
```
