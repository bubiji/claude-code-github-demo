> issue: #9 · 案例: login3 · 来源: https://login3.scrape.center

# login3 —— JWT 模拟登录、过期判定与刷新

## 案例原文（逐字引自 https://scrape.center/）

> 对接 JWT 模拟登录方式，适合用作 JWT 模拟登录练习。

## 接口地图（从前端 bundle 逆出来，再逐个实测）

前端是 Vue SPA，vuex store 里就写着全部端点（取自 `/js/app.11ce1f95.js`，逐字）：

```js
state: {
    url: {index: "/api/book", detail: "/api/book/{id}", proxy: "/proxy/{url}", login: "/api/login"},
    jwt: null,
    user: {username: null}
}
```

请求拦截器给每个请求挂 token（逐字）：

```js
e.headers.common["Authorization"] = "jwt ".concat(t)
```

| 端点 | 方法 | 说明 |
|---|---|---|
| `/api/login` | POST `{"username","password"}` | 返回 `{"token": "<JWT>"}` |
| `/api/refresh` | POST `{"token"}` | 拿旧 token 换新 token（djangorestframework-jwt 的 `refresh_jwt_token`） |
| `/api/book/?limit=&offset=` | GET | 受保护列表，需 `Authorization: jwt <token>` |
| `/api/verify` | — | **不存在**（404），此站没开 verify 端点 |

## JWT 三段结构（实测 dump）

```
[inspect] 三段长度 header/payload/signature = [36, 130, 43]
[inspect] ① header    : {"typ": "JWT", "alg": "HS256"}
[inspect] ② payload   : {"user_id": 1, "username": "admin", "exp": 1787524598, "email": "admin@admin.com", "orig_iat": 1787481398}
[inspect] ③ signature : mVf9ZY-u...FCtXkg  （32 字节，HS256 = HMAC-SHA256，正好 32 字节）
[inspect] exp      = 1787524598  2026-08-23T22:36:38+00:00
[inspect] orig_iat = 1787481398  2026-08-23T10:36:38+00:00
[inspect] 单次寿命 = 43200s；当前剩余 = 43199s（12.00 小时）；已过期 = False
```

要点：

- **`exp − orig_iat = 43200 秒 = 12 小时`**，即 DRF-JWT 的 `JWT_EXPIRATION_DELTA`。
- **`orig_iat` 是刷新窗口的锚点**：refresh 之后它**保持不变**（下方实测），DRF-JWT 用
  `orig_iat + JWT_REFRESH_EXPIRATION_DELTA` 判断这条 token 链还能不能续；超窗只能重新登录。
- JWT 三段用的是 **base64url 且不带 `=` 补位**，解码前必须自己补 `=`（`b64url_decode`）。
- payload 是**明文可读**的 —— JWT 不是加密，任何拿到 token 的人都能看见 `username`/`email`。
  签名只保证「没被改过」，不保证「看不见」。

## 鉴权与失效行为（全部实测，`login3.py expiry`）

```
[expiry] 单次寿命 exp-orig_iat = 43200s = 12 小时
[expiry] 无 Authorization 头          -> 401  {"detail":"Authentication credentials were not provided."}
[expiry] 正确 'jwt ' 前缀               -> 200  {"count":9200,...}
[expiry] 大写 'JWT ' 前缀               -> 200  {"count":9200,...}
[expiry] 错误 'Bearer ' 前缀            -> 401  {"detail":"Authentication credentials were not provided."}
[expiry] 签名被篡改                      -> 401  {"detail":"Error decoding signature."}
[expiry] payload 改成已过期              -> 401  {"detail":"Error decoding signature."}
[expiry] refresh #1: 200  exp 1787524619 -> 1787524624 (+5s)  orig_iat 不变=True
[expiry] refresh #2: 200  exp 1787524624 -> 1787524626 (+2s)  orig_iat 不变=True
[expiry] 用篡改 token 去 refresh -> 400 {"non_field_errors":["Error decoding signature."]}
```

几条容易踩的坑：

- **前缀必须是 `jwt` / `JWT`，不是 `Bearer`**。用 `Bearer` 会得到
  `Authentication credentials were not provided.` —— 报的是「没给凭证」，
  跟真的没带头一模一样，很容易误判成「token 没生效」。
- **refresh 后 `exp` 只前移了 5 秒 / 2 秒**，不是 +43200。因为新 token 的
  `exp = 当前时间 + 43200`，两次调用间隔多久就前移多久；换句话说
  **提前刷新不会累积寿命**，别指望靠刷新把 12 小时刷成 24 小时。
- **`orig_iat` 两次刷新后都不变** → 证实它是链条锚点，不随 refresh 更新。

### 关于「token 过期后的行为」——测到哪一步、为什么

服务端只签 12 小时的 token，**没有更短寿命的入口**，等自然过期要 12 小时。所以本次分两条路取证：

1. **本地伪造一个已过期的 token 去打服务端**（把 payload 的 `exp` 改到 1 小时前，重新 base64url 编码）。
   结果是 `401 {"detail":"Error decoding signature."}`。
   —— 改 payload 必然破坏签名，服务端**在校验 `exp` 之前就先挂在验签上**。
   这条恰好说明一件事：**服务端把「过期」和「伪造」关在同一道 401 墙后面，
   客户端拿不到「你的 token 过期了，去刷新」这样的明确信号**，
   所以刷新时机只能靠**本地解 `exp` 提前判定**，不能等 401 再说。
2. **强制走刷新分支**（`--refresh-margin 999999`，把「剩余不足 N 秒就刷新」的阈值调到大于 12 小时），
   让刷新逻辑在真实服务器上真跑一遍，而不是靠一句注释宣称「过期了会刷新」。

**未取证的部分（如实说明）**：`JWT_REFRESH_EXPIRATION_DELTA`（刷新窗口上限）的具体值没测出来——
测它需要一条 `orig_iat` 已经很老的 token，等待时长同样以天计。代码里对这种情况有回退：
`/api/refresh` 失败时自动退回 `/api/login` 重新登录（`ensure_fresh` 的 `fallback="re-login"` 分支）。

## 刷新逻辑（`ensure_fresh`）

```
本地解 payload.exp → ttl = exp - now
ttl > margin(默认 300s) → 直接用
ttl <= margin          → POST /api/refresh
                         成功 → 换新 token 落盘
                         失败 → 退回 POST /api/login 重新登录
抓取过程中撞到 401     → 立刻强制刷新一次再重试该页
```

真实输出（`data/run.log`，第 ③④ 段对照看）：

```
########## ③ fetch（正常路径，不该刷新）##########
[auth] token 剩余 43199s > 阈值 300s，无需刷新
[fetch] GET /api/book/?limit=18&offset=0 -> 200  count=9200 本页 18 条
[fetch] GET /api/book/?limit=18&offset=18 -> 200  count=9200 本页 18 条
[fetch] 共 36 条 -> data/login3_books.json (7099 字节)

########## ④ fetch --refresh-margin 999999（强制走刷新分支）##########
[auth] token 剩余 43196s <= 阈值 999999s → 触发刷新
[auth] 刷新完成：新 token eyJ0eX...NiJ9.eyJ1c2...k4fQ.k6ZDy9...ul0M，剩余 43200s
[fetch] GET /api/book/?limit=18&offset=0 -> 200  count=9200 本页 18 条
[fetch] GET /api/book/?limit=18&offset=18 -> 200  count=9200 本页 18 条
[fetch] 共 36 条 -> data/login3_books.json (7207 字节)
```

## 运行

```bash
cd src/s06_login/login3
bash demo_jwt.sh                 # ①login ②inspect ③fetch ④强制刷新 fetch，一条龙

PY=../../../.venv/bin/python     # 或直接 python3
$PY login3.py login
$PY login3.py inspect
$PY login3.py refresh
$PY login3.py expiry
$PY login3.py fetch --pages 3
$PY login3.py fetch --pages 3 --refresh-margin 999999
```

凭据：`admin` / `admin`（scrape.center 公开练习站的公开演示账号）。

## 产出

| 文件 | 内容 | 入库 |
|---|---|---|
| `data/jwt.json` | **真实 token**，`login` 生成 | ❌ 已 `.gitignore` |
| `data/jwt.sample.json` | 脱敏样本（三段各留前后几位） | ✅ |
| `data/login3_jwt_dump.json` | header/payload/签名长度/exp 解析（token 与签名已脱敏） | ✅ |
| `data/login3_expiry_probe.json` | 鉴权与失效矩阵、refresh 链、结论说明 | ✅ |
| `data/login3_books.json` | 2 页共 36 条图书 + 刷新日志 | ✅ |
| `data/run.log` / `data/expiry_probe.log` | 真实运行输出 | ✅ |

**脱敏说明**：本仓库是 public。入库文件里的 JWT 一律按三段分别脱敏（每段只留前后几位，中间 `...`），
签名同样脱敏；真实 token 只留在被 `.gitignore` 排除的 `data/jwt.json` 里。
payload 里的 `admin@admin.com` 是练习站演示账号自带的固定值，非真实邮箱。

## 依赖

`requests`（已在仓库根 `requirements.txt` 中）。JWT 拆解用标准库 `base64`/`json`，**未引入 PyJWT**——
本案例的重点就是手工拆三段、看清 base64url 无补位这些细节。

## 练习伦理

只针对案例作者公开提供的练习平台；翻页间隔 1 秒、探测间隔 0.5 秒，不用于压测。
