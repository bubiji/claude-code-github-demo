# antispider2：服务端判定规则实测

每个关键词做 4 组对照：单独发 / 放开头 / 放中间 / 全大写；只看 HTTP 状态码。

| 关键词 | 单独 | 在开头 | 在中间 | 全大写 | 判定 |
|---|---|---|---|---|---|
| `python-requests` | 403 | 403 | 403 | 200 | substring，区分大小写 |
| `Python-urllib` | 403 | 403 | 403 | 200 | substring，区分大小写 |
| `curl` | 403 | 403 | 200 | 200 | prefix，区分大小写 |
| `wget` | 403 | 403 | 403 | 200 | substring，区分大小写 |
| `Wget` | 403 | 403 | 403 | 200 | substring，区分大小写 |
| `Scrapy` | 403 | 403 | 403 | 200 | substring，区分大小写 |
| `okhttp` | 403 | 403 | 403 | 200 | substring，区分大小写 |
| `Go-http-client` | 403 | 403 | 403 | 200 | substring，区分大小写 |
| `PostmanRuntime` | 403 | 403 | 403 | 200 | substring，区分大小写 |
| `Googlebot/` | 403 | 403 | 403 | 200 | substring，区分大小写 |
| `Googlebot` | 200 | 200 | 200 | 200 | allowed |
| `Baiduspider` | 403 | 403 | 403 | 200 | substring，区分大小写 |
| `bingbot` | 403 | 403 | 403 | 200 | substring，区分大小写 |
| `libwww-perl` | 403 | 403 | 403 | 200 | substring，区分大小写 |
| `HeadlessChrome` | 403 | 403 | 403 | 200 | substring，区分大小写 |
| `aiohttp` | 200 | 200 | 200 | 200 | allowed |
| `httpx` | 200 | 200 | 200 | 200 | allowed |
| `spider` | 200 | 200 | 200 | 200 | allowed |
| `bot` | 200 | 200 | 200 | 200 | allowed |

空 UA：403
