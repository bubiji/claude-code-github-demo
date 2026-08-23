> issue: #9 · 阶段 6 · 来源: https://scrape.center/

# 阶段 6 —— 模拟登录：加密表单、Session、JWT

三个案例，三种「登录」在爬虫侧的形态。

| 案例 | 来源 | 案例原文（逐字引自 scrape.center） | 本阶段要害 |
|---|---|---|---|
| [`login1`](login1/) | https://login1.scrape.center | 模拟登录网站，登录时用户名和密码经过加密处理，适合 JavaScript 逆向分析。 | 把前端「加密」逆出来并在 Python 侧复现 |
| [`login2`](login2/) | https://login2.scrape.center | 对接 Session + Cookies 模拟登录，适合用作 Session + Cookies 模拟登录练习。 | cookie 落盘持久化，换进程免登录 |
| [`login3`](login3/) | https://login3.scrape.center | 对接 JWT 模拟登录方式，适合用作 JWT 模拟登录练习。 | 拆 JWT 三段、按 `exp` 判过期并刷新 |

## 三句话结论

- **login1**：所谓加密 = `Base64(UTF-8(JSON.stringify({username,password})))`，无密钥无盐；
  Python 侧产出的 token 与浏览器逐字节一致。另有一条实测发现：**该站是 nginx 纯静态托管，
  非 GET/HEAD 一律 405，根本没有接收 token 的后端**，所以练习价值全在 JS 逆向本身。
- **login2**：Django 风格表单登录 → `sessionid`（14 天、HttpOnly、SameSite=Lax）；
  cookie 落盘后**换进程、无用户名密码**即可取受保护页面，
  失效表现是 `302 → /login?next=/` 而非 401，`allow_redirects=False` 才看得见。
- **login3**：DRF-JWT，`Authorization: jwt <token>`（不是 `Bearer`），单次寿命 12 小时，
  `/api/refresh` 用旧 token 换新 token 且 `orig_iat` 不变；
  服务端把「过期」和「伪造」都关在同一句 401 后面，**刷新时机只能靠本地解 `exp` 提前判定**。

## 目录

```
src/s06_login/
├── .gitignore                # 排除真实凭据（cookies.json / jwt.json）
├── README.md                 # 本文件
├── login1/
│   ├── README.md             # 逆向过程、算法、密钥来源、定位方法
│   ├── login1.py             # locate / encrypt / submit / probe
│   └── data/                 # 运行结果与日志
├── login2/
│   ├── README.md
│   ├── login2.py             # login / fetch / whoami / probe / logout
│   ├── demo_restart.sh       # 两段式重启验证（3 个独立进程）
│   └── data/
└── login3/
    ├── README.md
    ├── login3.py             # login / inspect / refresh / fetch / expiry
    ├── demo_jwt.sh           # 全流程演示（含强制刷新分支）
    └── data/
```

## 凭据与脱敏

- 三站凭据都是 `admin` / `admin`，是 scrape.center 公开练习站的**公开演示账号**，写进文档无碍。
- **本仓库是 public**：抓到的真实 `sessionid` / JWT 一律不入库。
  入库文件中的凭据值只保留前后几位、中间以 `...` 省略；真实值写在 `data/cookies.json`、
  `data/jwt.json`，已由 `.gitignore` 排除，另配 `*.sample.json` 展示结构。

## 依赖

`requests`、`beautifulsoup4`、`lxml` —— 均已在仓库根 `requirements.txt` 中，本阶段未新增依赖。

## 练习伦理

只针对案例作者公开提供的练习平台；所有翻页/探测均已限速（1s / 0.5s / 0.4s 间隔），不用于压测。
