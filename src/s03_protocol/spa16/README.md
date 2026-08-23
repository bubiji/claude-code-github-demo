> issue: #6 · 案例: spa16 · 来源: https://spa16.scrape.center

## 案例描述（逐字引自 scrape.center）

> 图书网站，无反爬，不同于其他，该网站协议采用 HTTP 2，适合用于 HTTP 2 协议分析和测试。

---

## 一、结论速览

| 问题 | 实测答案 |
|---|---|
| spa16 支持 HTTP/2 吗 | 支持，且**只**支持 —— HTTP/1.1 请求被直接 RST |
| httpx 默认会用 h2 吗 | **不会**。必须 `httpx.Client(http2=True)` |
| 头部压缩省多少 | 每请求 **194.3 B → 50.3~50.6 B**，省 **74%** |
| 多路复用省多少连接 | 15 并发请求：h2 用 **1 条** TCP，h1.1 用 **5 条** |
| h2 一定更快吗 | **本例不明显**（9.2s vs 10.0s）——瓶颈在服务端串行处理，不在协议 |

数据来源：`evidence/*.json`，全部为真实网络请求产物，脚本可复跑。

---

## 二、脚本与产物

```
spa16/
├── fetch_books.py          # 用 h2 抓图书列表 + 详情，逐条记录 http_version
├── h2_vs_h11_bench.py      # A 协议协商 / B 定量对比 / C 本站 h2 串行 vs 并发
├── data/
│   └── spa16_books_h2.json # 90 本图书（站点共 9040 本）
└── evidence/
    ├── protocol-negotiation.json  # ALPN / httpx / curl 三方协商实测
    ├── httpx-protocol-h2.json     # 抓取过程的协议摘要
    └── h2-vs-h11-bench.json       # 耗时 / 连接数 / 字节数对比
```

复跑：

```bash
python fetch_books.py                 # 默认 h2 抓 5 页（90 本）+ 3 条详情
python h2_vs_h11_bench.py             # A + B + C 全跑
python h2_vs_h11_bench.py --skip-control   # 只跑 spa16 本站部分
```

---

## 三、「站点支持 h2」≠「客户端启用 h2」

这是本案例最容易踩的坑。httpx **默认只跑 HTTP/1.1**，即使对面是纯 h2 站点也不会自动升级——
`http2=True` 才会在 TLS 握手时把 `h2` 放进 ALPN 列表。所以每条响应都记下
`response.http_version` 作为「确实走了 h2」的证据，而不是嘴上说说：

```
httpx http2=True  -> ok=True  HTTP/2
httpx http2=False -> ok=False httpx.ReadError: [Errno 54] Connection reset by peer
curl --http2      -> http_version=2 http_code=200 time_total=0.535645 (exit 0)
curl --http1.1    -> http_version=0 http_code=000 time_total=0.228579 (exit 56)
```

### 一个反直觉的细节：ALPN 谈成了，HTTP 层还是被拒

单独探 ALPN（`ssl.SSLContext.set_alpn_protocols`）：

| 客户端 offer | 服务端 selected |
|---|---|
| `['h2', 'http/1.1']` | `h2` |
| `['h2']` | `h2` |
| `['http/1.1']` | **`http/1.1`** |

只报 `http/1.1` 时，服务端在 **TLS 层同意**了 http/1.1——ALPN 协商是成功的。
但真发出 HTTP/1.1 请求后，连接立刻被 RST（`Errno 54` / curl exit 56）。

**所以「不支持 HTTP/1.1」发生在 HTTP 层而不是 ALPN 层**：服务端 TLS 终结点接受 ALPN 值，
后端却只挂了 h2 handler。光看 ALPN 结果会误判成「两个协议都支持」，必须实发请求才看得出来。

---

## 四、h2 vs h1.1 定量对比

### 为什么对比要挪到 spa1

spa16 **做不出** h2-vs-h1.1 的同站对比——它根本不给 HTTP/1.1 回响应（见上）。
所以定量那一半挪到同平台的 `spa1.scrape.center`：它两个协议都正常响应，
是干净的对照主机。spa16 本站只做「h2 串行 vs h2 并发」。

### 两条指标，各用各的量法

**头部压缩** —— 同步串行，用 `ssl.SSLSocket.send/sendall/recv` 计数器数「交给 TLS 加密**之前**的字节」。
HTTP/1.1 是明文请求行 + 头部，HTTP/2 是 HPACK 压缩后的 HEADERS 帧，差别直接落在每请求发出字节数上。
（热身请求已扣除，握手成本不计入。）

| 协议 | 15 请求发出总字节 | 每请求 | 收到字节 | p50 |
|---|---|---|---|---|
| h2 | 759 B | **50.6 B** | 31963 B | 500.6 ms |
| http/1.1 | 2914 B | **194.3 B** | 33373 B | 521.7 ms |

**省 143.7 B/请求（-74%）**。HPACK 的静态表把 `:method: GET`、`accept-encoding` 这类固定头
压成 1 字节索引，动态表让第二次之后的重复头只发引用——所以请求越多、头越重复，省得越狠。
spa16 本站 h2 是 **50.3 B/请求**，与对照站一致。

**多路复用** —— 异步并发，`max_connections=5`，数连接池里真实的 TCP 连接数与每条连接扛的请求数：

| 协议 | wall | TCP 连接数 | 每条连接的 Request Count |
|---|---|---|---|
| h2 | 9.202 s | **1** | 16 |
| http/1.1 | 9.998 s | **5** | 4 / 3 / 3 / 3 / 3 |

15 个并发请求（+1 热身），h2 全部跑在**一条** TCP 连接上，h1.1 开满了 5 条。
这就是多路复用：h1.1 一条连接同时只能有一个未完成请求，要并发就得开更多连接
（每条都要付 TCP 握手 + TLS 握手的钱）；h2 把请求拆成带 stream id 的帧交错发，一条连接够用。

### 诚实说：本例耗时差别不大

9.202 s vs 9.998 s，只快了 8%。**不要把这个数字当成「h2 快 8%」的通用结论**——
本例的瓶颈是服务端串行处理（并发跑 15 个请求，p50 高达 5–6 秒，说明请求在服务端排队），
协议省下的那点握手与头部开销被淹没了。

h2 的收益在本例中体现为**资源占用**（1 条连接 vs 5 条、每请求少发 74% 字节）而非墙钟时间。
真要看到 h2 的时间优势，需要高延迟链路 + 大量小资源并发的场景。

---

## 五、抓取纪律

- 每请求间隔 0.3 s（`fetch_books.py`）/ 0.1 s（bench 串行），并发度上限 5，不压测。
- 默认只抓 5 页 90 本（站点共 9040 本），够做协议分析即可。
- User-Agent 标明来意：`scrape-center-practice/1.0 (+issue #6)`。
