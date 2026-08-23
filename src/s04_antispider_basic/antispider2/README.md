> issue: #7 · 案例: antispider2 · 来源: https://antispider2.scrape.center

# antispider2 · User-Agent 反爬

## 案例原文（逐字引自 scrape.center）

> 对接 User-Agent 反爬，检测到常见爬虫 User-Agent 就会拒绝响应，适合用作 User-Agent 反爬练习。

## 反爬是怎么判的（实证）

判定在**服务端**：不合格的 UA 直接返回 `403` + 135 字节；放行的返回 `200` + 约 41 KB 的
完整服务端渲染 HTML。**只看 `User-Agent` 这一个请求头**，与 Cookie、Referer、TLS 指纹无关
（同一个 requests 会话只换 UA 就能在 200/403 之间来回切换）。

### 一、哪些 UA 被拒、哪些放行（31 个 UA 实测，`data/ua_matrix.json` / `.md`）

放行 15，拒绝 16。摘要：

| 结果 | User-Agent |
|---|---|
| ❌ 403 | 不设 UA（requests 默认发 `python-requests/2.34.2`）、`python-requests/2.34.2`、`python-requests/2.0`、`Python-urllib/3.14`、`curl/8.7.1`、`Wget/1.21.4`、`Scrapy/2.11 (+https://scrapy.org)`、`okhttp/4.9`、`Go-http-client/1.1`、`PostmanRuntime/7.36`、`Googlebot/2.1 (+http://www.google.com/bot.html)`、`Baiduspider`、`bingbot/2.0`、空字符串、`Mozilla/5.0 (X11; Linux x86_64) … HeadlessChrome/120.0.0.0 …`、`Mozilla/5.0 python-requests/2.34.2` |
| ✅ 200 | `urllib3/2.7.0`、`httpx/0.28.1`、`Java/17`、`aiohttp/3.9`、`python`、`requests`、`spider`、`bot`、`crawler`、`x`、`-`、`Mozilla/5.0`、Chrome 120 桌面 UA、iPhone Safari UA、`Chrome/120.0.0.0 spider` |

第一眼就看得出：**它不是「看起来像爬虫就拒」**——裸的 `spider`、`bot`、`crawler`、
`python`、`requests` 全部放行，连 `x`、`-` 这种垃圾串也放行；被拒的是一批**具体的库名**。

### 二、匹配语义（`ua_rule_probe.py` → `data/ua_rule.md`）

对每个关键词做 4 组对照：单独发 / 放开头 / 放中间 / 全大写。

| 关键词 | 单独 | 在开头 | 在中间 | 全大写 | 判定 |
|---|---|---|---|---|---|
| `python-requests` | 403 | 403 | 403 | 200 | 子串，区分大小写 |
| `Python-urllib` | 403 | 403 | 403 | 200 | 子串，区分大小写 |
| `curl` | 403 | 403 | **200** | 200 | **只在开头才算**，区分大小写 |
| `wget` | 403 | 403 | 403 | 200 | 子串，区分大小写 |
| `Wget` | 403 | 403 | 403 | 200 | 子串，区分大小写 |
| `Scrapy` | 403 | 403 | 403 | 200 | 子串，区分大小写 |
| `okhttp` | 403 | 403 | 403 | 200 | 子串，区分大小写 |
| `Go-http-client` | 403 | 403 | 403 | 200 | 子串，区分大小写 |
| `PostmanRuntime` | 403 | 403 | 403 | 200 | 子串，区分大小写 |
| `Googlebot/` | 403 | 403 | 403 | 200 | 子串，区分大小写 |
| `Googlebot`（不带斜杠） | 200 | 200 | 200 | 200 | 放行 |
| `Baiduspider` | 403 | 403 | 403 | 200 | 子串，区分大小写 |
| `bingbot` | 403 | 403 | 403 | 200 | 子串，区分大小写 |
| `libwww-perl` | 403 | 403 | 403 | 200 | 子串，区分大小写 |
| `HeadlessChrome` | 403 | 403 | 403 | 200 | 子串，区分大小写 |
| `aiohttp` / `httpx` / `spider` / `bot`（对照组） | 200 | 200 | 200 | 200 | 放行 |

空 UA（`User-Agent:` 值为空串）也是 **403**。

**结论：服务端拿一张固定的字面量黑名单去匹配 UA，区分大小写。**

1. 绝大多数条目是**子串匹配**——出现在 UA 的任何位置都拒。所以
   `Mozilla/5.0 python-requests/2.34.2` 这种「披着浏览器皮」的写法照样 403。
2. `curl` 是个例外，**只有以它开头才拒**：`curl junk` → 403，`x curl` → 200，
   `ccurl` → 200，而 `curly/8.7.1` → 403（仍是前缀）。说明这一条在实现上带了行首锚定。
3. 大小写敏感：`PYTHON-REQUESTS/2.0`、`Python-Requests/2.0`、`WGET`、`scrapy`（小写）
   全部 200。
4. 条目是**带版本分隔符的完整标识**，不是宽泛的词：`Googlebot/` 拒但 `Googlebot` 放行；
   `Python-urllib` 拒但 `urllib`、`urllib3/2.7.0`、`python-urllib`（小写 p）都放行；
   `pythonrequests/2.0`（去掉连字符）也放行。
5. 空 UA 单独判拒。

> 说明：以上是**黑盒实测归纳**，不是读到了服务端源码。名单可能还有本文没试到的条目。

## 绕过办法

拿一个真实浏览器 UA 即可，不需要浏览器内核：

```python
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
requests.get(url, headers={"User-Agent": UA})
```

注意别用 `HeadlessChrome` 那个默认 UA——它在黑名单里。

## 跑法

```bash
cd src/s04_antispider_basic/antispider2
../../../.venv/bin/python ua_probe.py       # 哪些被拒（31 个 UA）
../../../.venv/bin/python ua_rule_probe.py  # 怎么判的（19 个关键词 × 4 组对照）
../../../.venv/bin/python spider.py         # 用合规 UA 抓 10 页
```

依赖：`requests`、`beautifulsoup4`、`lxml`（已在仓库根 requirements.txt 中）。

## 产出

| 文件 | 内容 |
|---|---|
| `data/ua_matrix.json` / `data/ua_matrix.md` | 31 个 UA 的状态码 / 响应字节 / 首屏片段 |
| `data/ua_rule.json` / `data/ua_rule.md` | 19 个关键词 × 4 组对照，判定子串/前缀/大小写 |
| `data/antispider2_movies.json` | 10 页共 100 条电影 |

实跑结果：10 页每页 `200`、40–43 KB，各解析 10 条，共 **100 条**；
首条 `霸王别姬 - Farewell My Concubine`，评分 `9.5`，`1993-07-26 上映`。

## 练习伦理

每次请求间隔 ≥ 0.8 秒（`common.polite_sleep`）；探针共约 110 个请求，不是压测。
