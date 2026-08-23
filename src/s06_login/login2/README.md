> issue: #9 · 案例: login2 · 来源: https://login2.scrape.center

# login2 —— Session + Cookies 模拟登录与持久化

## 案例原文（逐字引自 https://scrape.center/）

> 对接 Session + Cookies 模拟登录，适合用作 Session + Cookies 模拟登录练习。

## 登录链路（实测）

| 步 | 请求 | 结果 |
|---|---|---|
| 0 | `GET /`（无 cookie） | `302 → /login?next=/` |
| 1 | `GET /login?next=/` | `200`，返回登录表单；**页面里没有 `csrfmiddlewaretoken`**，POST 不需要带 CSRF |
| 2 | `POST /login?next=/`，form-urlencoded：`username=admin&password=admin` | `302 → /`，`Set-Cookie: sessionid=...` |
| 3 | 带 `sessionid` 请求 `/`、`/page/N`、`/detail/N` | `200` |
| — | 密码错误时 | `200`（表单原样回吐，**不发 Set-Cookie**）—— 所以「成功」的判据是 **302 而不是 200** |

表单是纯服务端渲染（Django 风格：`vary: Cookie`、`x-frame-options: SAMEORIGIN`），
`requests.Session` 直接 POST 即可，不需要浏览器。

### session cookie 属性（实测）

```
sessionid=****  长度 32
expires=Sun, 06 Sep 2026 10:36:08 GMT
Max-Age=1209600      → 14 天
HttpOnly; Path=/; SameSite=Lax
```

## 验收要点：两段式重启验证

**「重启脚本无需重新登录」是分两个进程真跑出来的**，一键复现：

```bash
cd src/s06_login/login2
bash demo_restart.sh                 # 自动找仓库根 .venv；也可 bash demo_restart.sh /path/to/python
```

真实输出（完整原文见 `data/two_stage_demo.log`）：

```
########## 第 1 段：登录并落盘 cookie（进程 A）##########
=== login2.py login  pid=76273  2026-08-23T10:34:58+00:00 ===
[login] GET /login?next=/ -> 200；页面含 csrfmiddlewaretoken: False
[login] POST /login?next=/ -> 302  Location=/
[login] Set-Cookie（脱敏）: sessionid=ftbu...5v0h; expires=Sun, 06 Sep 2026 10:35:08 GMT; HttpOnly; Max-Age=1209600; Path=/; SameSite=Lax
[login] cookie 已落盘 -> data/cookies.json

[demo] 进程 A 已退出（exit code 0）；磁盘上的 cookie 文件：
[demo]   data/cookies.json  293 字节

########## 第 2 段：全新进程，只读 cookie（进程 B）##########
=== login2.py fetch  pid=76305  2026-08-23T10:35:08+00:00 ===
[fetch] 本进程**不做登录**，只加载磁盘上的 cookie：
[cookie]   sessionid=ftbu...5v0h  domain=login2.scrape.center path=/ expires=2026-09-06T10:35:08+00:00 剩余=14.00 天
[fetch] GET / -> 200  解析出 10 条
[fetch] GET /page/2 -> 200  解析出 10 条
[fetch] GET /page/3 -> 200  解析出 10 条
[fetch] 共 30 条 -> data/login2_movies.json (9218 字节)
[fetch] 本进程发出的全部 HTTP 请求：
[fetch]   GET https://login2.scrape.center/ -> 200
[fetch]   GET https://login2.scrape.center/page/2 -> 200
[fetch]   GET https://login2.scrape.center/page/3 -> 200
[fetch] 其中 path 以 /login 开头的请求数 = 0  → OK：全程未登录，纯 cookie 复用

########## 第 3 段：再起一个进程确认登录态（进程 C）##########
=== login2.py whoami  pid=76317  2026-08-23T10:35:16+00:00 ===
[whoami] 已登录 —— GET / -> 200，页面顶栏显示: admin
```

三处硬证据，缺一不可：

1. **PID 不同**（76273 / 76305 / 76317）→ 确实换了进程，不是同一个 Session 对象留在内存里；
2. **fetch 打印了本进程发出的全部 HTTP 请求**（`requests` 的 response hook 记录，不是脚本自述），
   清单里 **path 以 `/login` 开头的请求数 = 0**；
3. **页面顶栏渲染出 `admin`** → 服务端确实认这个 session，不是拿到一个匿名 200。

## cookie 有效期 / 失效表现（实测，`login2.py probe`）

```
[probe] 无 cookie      GET / -> 302 /login?next=/
[probe] 伪造 sessionid GET / -> 302 /login?next=/
[probe] 密码错误      POST /login -> 200（成功应为 302）  Set-Cookie: False
[probe] sessionid=4lzt...i8ei 长度=32 有效期=14.0 天 属性=['expires=Sun, 06 Sep 2026 10:36:08 GMT', 'HttpOnly', 'Max-Age=1209600', 'Path=/', 'SameSite=Lax']
[probe] GET /logout -> 302 /login
[probe] 登出后复用旧 sessionid GET / -> 302 /login?next=/  ← 服务端已销毁 session
```

结论：

- **有效期 14 天**（`Max-Age=1209600`），期间可反复重启脚本复用；
- **失效表现统一是 `302 → /login?next=/`**，不是 401/403 —— 所以爬虫必须
  `allow_redirects=False` 才看得见失效，否则会拿到一张 200 的登录页当成"抓到了"；
- **服务端可单方面作废**：`GET /logout` 之后，同一个 sessionid 立刻失效（Django 侧 session 记录被删），
  说明「cookie 没过期」≠「还能用」，代码里对 302 必须有重新登录的回退分支（`do_fetch` 返回码 2）。

## 运行

```bash
cd src/s06_login/login2
PY=../../../.venv/bin/python     # 或直接 python3

$PY login2.py login              # 第 1 段：登录并落盘 cookie
$PY login2.py fetch --pages 3    # 第 2 段：全新进程，只读 cookie
$PY login2.py whoami             # 只读 cookie 判断登录态
$PY login2.py probe              # cookie 有效期 / 失效表现实测
$PY login2.py logout             # 服务端登出
```

凭据：`admin` / `admin`（scrape.center 公开练习站的公开演示账号）。

## 产出

| 文件 | 内容 | 入库 |
|---|---|---|
| `data/cookies.json` | **真实 sessionid**，`login` 生成 | ❌ 已 `.gitignore` |
| `data/cookies.sample.json` | 脱敏样本，只保留结构与前后 4 位 | ✅ |
| `data/login2_movies.json` | 3 页共 30 条电影（片名/类别/信息/评分/详情链接）+ 本进程 HTTP 请求清单 | ✅ |
| `data/login2_cookie_probe.json` | cookie 属性与失效矩阵（值已脱敏） | ✅ |
| `data/two_stage_demo.log` | 两段式重启验证的真实输出 | ✅ |
| `data/cookie_probe.log` | probe 的真实输出 | ✅ |

**脱敏说明**：本仓库是 public。所有入库文件里的 `sessionid` 一律只保留前 4 位与后 4 位、中间以 `...` 省略
（`login2.py` 的 `mask()`），真实值只留在被 `.gitignore` 排除的 `data/cookies.json` 里。

## 依赖

`requests`、`beautifulsoup4`、`lxml`（均已在仓库根 `requirements.txt` 中）。

## 练习伦理

只针对案例作者公开提供的练习平台；翻页间隔 1 秒（`DELAY`），不用于压测。
