> issue: #9 · 案例: login1 · 来源: https://login1.scrape.center

# login1 —— 登录表单加密的 JavaScript 逆向

## 案例原文（逐字引自 https://scrape.center/）

> 模拟登录网站，登录时用户名和密码经过加密处理，适合 JavaScript 逆向分析。

## 一句话结论

所谓「加密」是 **Base64(UTF-8(JSON.stringify({username, password})))**，无密钥、无盐、可逆；
Python 侧已完整复现，产出的 token 与浏览器**逐字节一致**。

```
admin/admin  →  {"username":"admin","password":"admin"}
             →  eyJ1c2VybmFtZSI6ImFkbWluIiwicGFzc3dvcmQiOiJhZG1pbiJ9
POST /  body: {"token":"eyJ1c2VybmFtZSI6ImFkbWluIiwicGFzc3dvcmQiOiJhZG1pbiJ9"}
```

## 逆向过程：我是怎么定位到入口的

`login1.py locate` 每次都**实跑**这条链路，不写死结论：

| 步 | 动作 | 命中 |
|---|---|---|
| 1 | `GET /` 拿 SPA 骨架，提取 `<link rel=prefetch href=/js/chunk-*.js>` | `/js/chunk-cc71364c.d38f911d.js`（路由懒加载 chunk）、`/js/chunk-vendors.f1c69639.js` |
| 2 | 在 chunk 里搜 `onSubmit`（Element UI 登录按钮的 `@click`） | 命中 chunk-cc71364c，5901 字节 |
| 3 | 抠出 `onSubmit` 函数体 | 见下方原文 |
| 4 | 在函数体里定位 `encode(JSON.stringify(...))` | `e=c.encode(JSON.stringify(this.form))` |
| 5 | 回查 `c` 的来源 | `c = o("27ae").Base64` → 同 chunk 内的 webpack 模块 `27ae` |
| 6 | 在模块 `27ae` 里搜 `b64chars` | 标准 Base64 字母表（未魔改），版本字符串 `version="2.5.1"` |
| 7 | 在入口 `app.js` 搜 vuex `state.url.root` | `"/"` → 提交地址就是站点根 |

### 原件：`onSubmit` 函数体（逐字，取自 chunk-cc71364c.d38f911d.js）

```js
onSubmit: function () {
    var e = c.encode(JSON.stringify(this.form));
    this.$http.post(a["a"].state.url.root, {token: e}).then((function (e) {
        console.log("data", e)
    }))
}
```

（压缩产物原文一行：`var e=c.encode(JSON.stringify(this.form));this.$http.post(a["a"].state.url.root,{token:e}).then((function(e){console.log("data",e)}))`，此处仅加了换行缩进以便阅读，字符本身未改。）

### 算法是什么

- **算法**：Base64 编码，**不是加密**。用的是 [dankogai/js-base64](https://github.com/dankogai/js-base64) v2.5.1（bundle 内 `version="2.5.1"`、`b64chars`、`utob`/`btou` 全套特征）。
- **密钥 / 盐**：**没有**。`encode(s) = btoa(utob(s))`，`utob` 只是把字符串按 UTF-8 展开，全过程无任何秘密参数。
- **字母表**：标准表 `A-Za-z0-9+/`，未替换字符（脚本每次实跑校验 `b64chars_is_standard`）。
- **URL-safe 分支**：`encode(e, r)` 的第二参 `r` 为真时才把 `+/` 换成 `-_` 并去掉 `=`；`onSubmit` 只传一个参数，所以走**标准 Base64、保留 `=` 补位**。
- **Python 等价物**：`base64.b64encode(s.encode("utf-8"))`。

### 最容易翻车的一处细节

JS 的 `JSON.stringify` 输出**无空格**，Python 的 `json.dumps` 默认输出 `", "` / `": "`。
不改分隔符就会得到另一个 token，跟浏览器对不上：

```
浏览器一致 : eyJ1c2VybmFtZSI6ImFkbWluIiwicGFzc3dvcmQiOiJhZG1pbiJ9   ← separators=(",", ":")
不一致(反例): eyJ1c2VybmFtZSI6ICJhZG1pbiIsICJwYXNzd29yZCI6ICJhZG1pbiJ9  ← json.dumps 默认
```

脚本每次运行都会把这个反例一起打出来自证。键序同样重要：Vue `data.form` 的插入序是 `username` 先于 `password`。

## 服务端实测：这个站没有登录后端（重要）

**「脱离浏览器完成登录」在 login1 上做到了「加密复现 + 按 axios 原样提交」这一步为止，因为服务端根本不受理 POST。**
这不是脚本的问题——用**浏览器同款请求头**（`Origin`/`Referer`/`Content-Type: application/json;charset=UTF-8`/`Sec-Fetch-*`）重放同一请求，结果一样：

| 请求 | 状态码 |
|---|---|
| `GET  /` | 200（SPA 页面） |
| `POST /`（axios 原样，浏览器同款头） | **405 Not Allowed（nginx/1.21.3）** |
| `OPTIONS /` | 405 |
| `PUT /` | 405 |
| `POST /api/login` | 405 |
| `POST /js/app.d03bfa52.js` | 405 |

连静态 JS 文件 POST 都是 405 —— 说明整站由 nginx 纯静态托管，**任何非 GET/HEAD 方法一律 405**，压根没有接收 token 的后端。
前端 `onSubmit` 里也只有 `console.log("data", e)`，没有任何 `if (res.code === 0)` 之类的成功分支。

所以本案例的练习价值 100% 在 JS 逆向本身（这也正是案例描述说的「适合 JavaScript 逆向分析」），不在于拿到会话。
真正的会话式登录见同阶段的 **login2**（Session + Cookies）与 **login3**（JWT）。

## 运行

```bash
cd src/s06_login/login1
PY=../../../.venv/bin/python            # 仓库根的 venv；也可直接用 python3
$PY login1.py all                       # locate + encrypt + submit + probe（默认）
$PY login1.py locate                    # 只跑 JS 定位
$PY login1.py encrypt -u admin -p admin # 只出 token
```

凭据：`admin` / `admin`（scrape.center 公开练习站的公开演示账号）。

## 产出

| 文件 | 内容 |
|---|---|
| `data/login1_result.json` | locate 链路命中项、token、反例对比、submit 响应、方法探测矩阵 |
| `data/run.log` | 一次完整 `login1.py all` 的真实输出 |

本案例无敏感值需脱敏：token 由公开演示账号 `admin/admin` 明文可逆编码而成，本身不构成凭据泄露。

## 依赖

`requests`（已在仓库根 `requirements.txt` 中）。

## 练习伦理

只针对案例作者公开提供的练习平台；`probe` 的方法探测已限速（每次 0.4s 间隔），不用于压测。
