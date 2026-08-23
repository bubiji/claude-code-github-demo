> issue: #4 · 案例: ssr3 · 来源: https://ssr3.scrape.center

# ssr3 —— HTTP Basic Authentication

案例描述（**逐字引自** https://scrape.center/，未改写）：

> 电影数据网站，无反爬，带有 HTTP Basic Authentication，适合用作 HTTP 认证案例，用户名密码均为 admin。

## Basic Auth 是怎么谈成的（实测）

脚本每次运行都会先裸请求一次，把服务端的 401 挑战原样打出来：

```
[ssr3] 无认证访问 → HTTP 401；WWW-Authenticate: 'Basic realm="Authentication Required"'
[ssr3] 认证方式：requests auth=("admin", "admin")
```

整条握手就两步：

```
1. GET /page/1                                  → 401 Unauthorized
                                                  WWW-Authenticate: Basic realm="Authentication Required"
2. GET /page/1
   Authorization: Basic YWRtaW46YWRtaW4=        → 200 OK
```

`YWRtaW46YWRtaW4=` 就是 `base64("admin:admin")`。`requests` 的 `auth=("admin","admin")`
（即 `HTTPBasicAuth`）做的正是第 2 步那个头，没有别的魔法。脚本用 `--manual-header`
可以切换成手工拼头的等价写法，两种方式抓出来的数据完全相同：

```
[ssr3] 认证方式：手工头 Authorization: Basic YWRtaW46YWRtaW4=
```

> **Basic 不是加密，是编码。** base64 可逆，凭证等于明文在头里裸奔——靠 HTTPS 的传输加密
> 才安全，走 http:// 就是把密码送人。这里之所以能把 `admin/admin` 写进代码，
> 是因为它是案例作者在公开页面上给出的练习凭证（见上方逐字引文），不是任何人的真实密码。
> 真凭证一律走环境变量/密钥管理，不进仓库。

## 怎么跑

```bash
cd src/s01_ssr/ssr3
python crawl.py                    # auth=("admin","admin")，约 150 秒
python crawl.py --manual-header    # 手工拼 Authorization 头，验证与上面等价
python crawl.py --no-detail        # 只抓 10 个列表页，约 14 秒
```

## 抓到什么（2026-08-23 真实运行）

```
[ssr3] 无认证访问 → HTTP 401；WWW-Authenticate: 'Basic realm="Authentication Required"'
[ssr3] 认证方式：requests auth=("admin", "admin")
[ssr3] https://ssr3.scrape.center · workers=1 delay=0.3s

[ssr3] 抓取完成
  记录数     : 100（列表页 10 页 / 详情页 100 个）
  请求数     : 111，失败 0
  单请求均值 : 0.99s
  总耗时     : 148.14s（列表 16.02s + 详情 132.12s）
  串行预估   : 109.47s（111 请求 × 均值 0.99s）
  落盘       : ssr3.json 482.8KB / ssr3.summary.json
```

- `data/ssr3.json` —— 100 条完整记录（字段同 ssr1）
- `data/ssr3.summary.json` —— 除统计外多一个 `auth` 字段，存下认证方式与那次
  401 探测的原始响应（状态码 + `WWW-Authenticate`），证明认证确实生效过
- CSV 只在 [`../ssr1/data/ssr1.csv`](../ssr1/data/ssr1.csv) 留一份（四个案例数据相同）
- 跑 [`../verify.py`](../verify.py) 验证本份数据与 ssr1 逐字段相同

## 关键实现要点

1. **401 必须炸，不能当空页。** `make_fetch()` 里 401 直接抛 `PermissionError`。
   要是把 401 也归进「解析不出条目 → 翻页结束」，脚本会抓到 0 条却报成功——
   这是最难发现的那类失败。
2. **收尾再兜一道。** `records` 为空时非 0 退出并打明「判定为认证或站点故障」。
3. 认证之外的一切（翻页终止、字段解析、落盘、统计）全部复用 [`../common.py`](../common.py)。

## 遇到的坑

1. **`auth=` 是抢先发送的，那个 401 不会自己出现。** `HTTPBasicAuth` 在**第一个**请求上就把
   `Authorization` 头带上了，不会先挨一个 401 再重试。所以脚本里那次 401 是**特意裸请求**
   探出来的（`show_challenge()`），不是抓取过程的副产品——不特意探，你根本看不到服务端的挑战头，
   也就不知道人家要的是 Basic 还是 Digest/Bearer。

2. **跨主机重定向时凭证会被丢掉，两种写法都一样。** 翻 `requests/sessions.py` 确认过：
   `rebuild_auth()` 判断 `should_strip_auth(原 url, 新 url)`（主机名/端口/协议变了就算变）后，
   直接 `del headers["Authorization"]`；而它只会从 netrc 重新取认证，**不会**把 `session.auth`
   重新贴回去。也就是说手工塞的头和 `auth=` 一样会被剥，别指望「跨域跳转后还带着认证」——
   本案例没有跨域跳转，但真实站点上这一条经常表现为「加了 auth 还是 401」。

3. **`realm` 只是个提示串，不参与计算。** `Basic realm="Authentication Required"` 里的 realm
   给人看的（浏览器弹框标题），客户端不需要拿它做任何事，别照着 Digest 认证的习惯去解析它。

4. **同样的 500 翻页终止逻辑。** 第 11 页返回 HTTP 500 而不是空列表，见 ssr1 README 第 1 条。
   注意这条要和 401 分开处理：500 是「没有下一页」，401 是「认证坏了」，混在一起就前功尽弃。
