# antispider2 User-Agent 实测表

目标：https://antispider2.scrape.center/

| 分组 | 实际发出的 User-Agent | 状态码 | 响应字节 | 结果 |
|---|---|---|---|---|
| HTTP 客户端默认 | `python-requests/2.34.2` | 403 | 135 | ❌ 拒绝 |
| HTTP 客户端默认 | `python-requests/2.34.2` | 403 | 135 | ❌ 拒绝 |
| HTTP 客户端默认 | `python-requests/2.0` | 403 | 135 | ❌ 拒绝 |
| HTTP 客户端默认 | `Python-urllib/3.14` | 403 | 135 | ❌ 拒绝 |
| HTTP 客户端默认 | `urllib3/2.7.0` | 200 | 41654 | ✅ 放行 |
| HTTP 客户端默认 | `curl/8.7.1` | 403 | 135 | ❌ 拒绝 |
| HTTP 客户端默认 | `Wget/1.21.4` | 403 | 135 | ❌ 拒绝 |
| HTTP 客户端默认 | `Scrapy/2.11 (+https://scrapy.org)` | 403 | 135 | ❌ 拒绝 |
| HTTP 客户端默认 | `okhttp/4.9` | 403 | 135 | ❌ 拒绝 |
| HTTP 客户端默认 | `Go-http-client/1.1` | 403 | 135 | ❌ 拒绝 |
| HTTP 客户端默认 | `httpx/0.28.1` | 200 | 41654 | ✅ 放行 |
| HTTP 客户端默认 | `PostmanRuntime/7.36` | 403 | 135 | ❌ 拒绝 |
| HTTP 客户端默认 | `Java/17` | 200 | 41654 | ✅ 放行 |
| HTTP 客户端默认 | `aiohttp/3.9` | 200 | 41654 | ✅ 放行 |
| 裸关键词 | `python` | 200 | 41654 | ✅ 放行 |
| 裸关键词 | `requests` | 200 | 41654 | ✅ 放行 |
| 裸关键词 | `spider` | 200 | 41654 | ✅ 放行 |
| 裸关键词 | `bot` | 200 | 41654 | ✅ 放行 |
| 裸关键词 | `crawler` | 200 | 41654 | ✅ 放行 |
| 搜索引擎 | `Googlebot/2.1 (+http://www.google.com/bot.html)` | 403 | 135 | ❌ 拒绝 |
| 搜索引擎 | `Baiduspider` | 403 | 135 | ❌ 拒绝 |
| 搜索引擎 | `bingbot/2.0` | 403 | 135 | ❌ 拒绝 |
| 无意义串 | `(空)` | 403 | 135 | ❌ 拒绝 |
| 无意义串 | `x` | 200 | 41654 | ✅ 放行 |
| 无意义串 | `-` | 200 | 41654 | ✅ 放行 |
| 无意义串 | `Mozilla/5.0` | 200 | 41654 | ✅ 放行 |
| 浏览器 | `Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, ...` | 200 | 41654 | ✅ 放行 |
| 浏览器 | `Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Head...` | 403 | 135 | ❌ 拒绝 |
| 浏览器 | `Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15...` | 200 | 41654 | ✅ 放行 |
| 混搭 | `Mozilla/5.0 python-requests/2.34.2` | 403 | 135 | ❌ 拒绝 |
| 混搭 | `Chrome/120.0.0.0 spider` | 200 | 41654 | ✅ 放行 |

共 31 个 UA：放行 15，拒绝 16。
