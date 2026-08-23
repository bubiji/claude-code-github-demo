> issue: #4 · 阶段: s01 SSR 服务端渲染 · 来源: https://scrape.center/

# 阶段 1 —— 基础请求与解析（SSR 服务端渲染）

四个案例是**同一套电影站**（100 部电影、10 页列表、`/detail/<id>` 详情页），
只在连接层各加一道花样。所以「请求 → 解析 → 落盘」这条链路只写一份
（[`common.py`](common.py)），各案例的 `crawl.py` 只提供自己的 `fetch(url) -> str`。

| 案例 | 加的那道花样 | 落脚点 |
|---|---|---|
| [ssr1](ssr1/) | 无 | 翻页 + 两跳解析 + 落盘的地基 |
| [ssr2](ssr2/) | 无 HTTPS 证书 | 显式 `verify=False` + 风险声明，不消警告 |
| [ssr3](ssr3/) | HTTP Basic Auth | 401 挑战 → `Authorization: Basic ...` |
| [ssr4](ssr4/) | 每响应 5 秒延迟 | 线程池并发 + 超时控制（实测服务端串行，见其 README） |

案例描述逐字引自 https://scrape.center/，各案例 README 开头照抄，未改写。

## 目录

```
src/s01_ssr/
├── common.py        # 解析（列表页/详情页）、翻页调度、并发、统计、落盘
├── verify.py        # 交叉校验：四份数据除 host 外应完全一致
├── ssr1/{crawl.py, README.md, data/}
├── ssr2/{crawl.py, README.md, data/}
├── ssr3/{crawl.py, README.md, data/}
└── ssr4/{crawl.py, README.md, data/}
```

## 跑一遍

```bash
python src/s01_ssr/ssr1/crawl.py              # ≈ 70s
python src/s01_ssr/ssr2/crawl.py --insecure   # ≈ 174s
python src/s01_ssr/ssr3/crawl.py              # ≈ 170s
python src/s01_ssr/ssr4/crawl.py              # ≈ 11min（每响应固定慢 5s）
python src/s01_ssr/verify.py                  # 四份数据对指纹
```

## 2026-08-23 真实运行汇总

| 案例 | 记录数 | 请求数 | 失败 | 总耗时 | JSON |
|---|---|---|---|---|---|
| ssr1 | 100 | 111 | 0 | 69.4s | 482.8KB |
| ssr2 | 100 | 111 | 0 | 173.5s | 482.8KB |
| ssr3 | 100 | 111 | 0 | 169.6s | 482.8KB |
| ssr4 | 见 [ssr4/README.md](ssr4/README.md) | | | | |

四份数据交叉校验一致（`verify.py`，排除 `detail_url` 的 host 差异），说明证书开关、
Basic Auth、并发这三条不同的连接路径都没有污染数据层。

## 共用的三个判断

1. **翻页终止靠「解析不出条目」**，不写死 10 页。本站第 11 页返回 **HTTP 500** 而不是空页，
   所以各案例的 `fetch` 把「`/page/` 上的 500」翻译成 `""`（没有下一页），其余 5xx 照常抛。
2. **零结果即故障**：认证失败（401）、超时这类情况绝不能混进「翻页结束」，否则会
   「抓到 0 条还报成功」。ssr3 的 401、ssr4 的 Timeout 都是显式抛出并非 0 退出。
3. **单条详情失败不拖垮整轮**：详情页异常记进 `stats.failures`，该片回落到列表页字段，
   收尾统一汇报并以非 0 退出。
