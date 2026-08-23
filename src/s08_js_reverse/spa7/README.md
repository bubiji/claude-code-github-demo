> issue: #11 · 案例: spa7 · 来源: https://spa7.scrape.center

# spa7 · 纯前端渲染 + DES Token 还原

## 案例原文（逐字引自 scrape.center）

> NBA 球星数据网站，数据纯前端渲染，Token 经过加密处理，适合基础 JavaScript 模拟分析。

## 结论先说：算法

```
token = base64( DES-ECB-PKCS7( base64(name) + birthday + height + weight,  key[:8] ) )

key = "fipFfVsZsTda94hJNKJfLoaqyqMZFFimwLt"   （35 字节，DES 实际只吃前 8 字节 "fipFfVsZ"）
```

以凯文-杜兰特（生日 1988-09-29，身高 208cm，体重 108.9KG）为例，被 DES 加密的明文串是：

```
5Yev5paHLeadnOWFsOeJuQ==1988-09-29208cm108.9KG
└──── base64("凯文-杜兰特") ────┘└─ birthday ─┘└height┘└weight┘
```

加密后 base64 得到的 Token 是：

```
DG1uMMq1M7OeHhds71HlSMHOoI2tFpWCB4ApP00cVFqptmlFKjFu9RluHo2w3mUw
```

（全部 16 名球员的明文构件与 Token 见 `data/spa7_players_tokens.json`，程序算的，没有手抄。）

三个必须说清的细节：

1. **`base64(name)` 只对 name 做，不是对整串做**——`getToken` 里 `base64Name` 是单独一步。
2. **key 长 35 字节，DES 只用前 8 字节**。CryptoJS 拿到 WordArray 形式的 key 时不做 KDF、
   不报错、也不截断提示，直接按 `keySize: 2`（2 个 32 位字 = 8 字节）取走前两个 word。
   自己实现时如果把 35 字节全喂进去或者报错，就对不上了。
3. **`encrypted.toString()` 返回的是密文的 base64，没有 `Salted__` 前缀**。
   CryptoJS 的 OpenSSL 格式化器只在「用口令派生密钥」时才加盐前缀；这里传的是 WordArray 密钥，
   所以输出就是纯 `base64(ciphertext)`。

## 「数据纯前端渲染」——先证明这一点

`spider.py` 会探几个常见接口路径，全部返回**同一份 2088 字节的 index.html**（SPA 兜底），
说明站点没有任何数据接口：

```
  /api/player   HTTP 200  2088 字节  text/html
  /api/players  HTTP 200  2088 字节  text/html
  /api/nba      HTTP 200  2088 字节  text/html
  /api/token    HTTP 200  2088 字节  text/html
  /api          HTTP 200  2088 字节  text/html
  /api/movie    HTTP 200  2088 字节  text/html
  → 6 个路径返回 1 种响应体大小 {2088}；确认没有数据接口，数据只在 main.js 里
```

**所以本案例「脱离浏览器直接请求接口成功」的准确含义是**：数据源就是静态资源 `js/main.js`，
用 requests 直接拉它、在 Python 里解析出 16 名球员并**自己算出与页面完全一致的 Token**，
全程不启动浏览器。这一点如实写在这里，不含糊过去。

## 怎么找到的（这个案例基本没有障碍，如实说）

`index.html` 里 4 个 script 一眼看到底：`vue.min.js` / `element-ui.js` / **`crypto-js.min.js`** / `main.js`。
`crypto-js.min.js` 出现在这种小站的首页，等于把「这里有对称加密」写在了脸上——直接看 `main.js` 就行，
2770 字节，未压缩、未混淆，`getToken` 完整可读（原件 `evidence/main.js`，逐字）：

```js
  methods: {
    getToken(player) {
      let key = CryptoJS.enc.Utf8.parse(this.key)
      const {name, birthday, height, weight} = player
      let base64Name = CryptoJS.enc.Base64.stringify(CryptoJS.enc.Utf8.parse(name))
      let encrypted = CryptoJS.DES.encrypt(`${base64Name}${birthday}${height}${weight}`, key, {
        mode: CryptoJS.mode.ECB,
        padding: CryptoJS.pad.Pkcs7
      })
      return encrypted.toString()
    }
  }
```

Token 在页面上的用途也直白——`index.html` 里 `<el-tooltip :content="getToken(player)">`，
鼠标悬停在球员卡片上就显示出来（原件 `evidence/index.html`）。

**真正的工作量在「怎么在 Python 侧复现」而不是「怎么找到」**，踩到的三个点：

- **venv 里没有任何加解密库**（只有 requests/httpx/bs4/lxml/fonttools/playwright/websockets）。
  阶段要求「纯 Python 复现算法」优先，于是**手写了一份 DES**（`des.py`，约 200 行表驱动，零依赖）。
  自检用 FIPS 官方测试向量：key 与明文全 0x00 → 密文必须是 `8CA64DE9C1B123A7`：

  ```
  $ ../../../.venv/bin/python des.py
  FIPS vector 0x00*8 -> 8CA64DE9C1B123A7 OK
  ```

- **key 到底取几个字节**：一开始不确定 35 字节的 key 会被 CryptoJS 怎么处理（截断？补齐？报错？）。
  没有靠猜——直接拿站点自己的 `crypto-js.min.js` 在 Node 里跑一遍做对照，
  `key[:8]` 的假设一次对上 16/16。
- **`toString()` 输出格式**：同上，交叉验证一次就钉死了「无 Salted__ 前缀」。

## 三重验证（这是本案例的核心证据）

| 路线 | 用什么 | 结果 |
|---|---|---|
| ① 纯 Python | 自写 `des.py`，零依赖 | 16 个 token |
| ② Node + **站点自己的** crypto-js | `verify_with_node.js` 加载 `evidence/crypto-js.min.js`，逐字复用 `getToken` | 与 ① **16/16 完全一致** |
| ③ 真浏览器 | `verify_with_browser.py`，playwright 打开真站、悬停第一张卡片、读 tooltip 实际文字 | 与 ①② **一致** |

③ 的原始输出：

```
{"name": "凯文-杜兰特", "tooltip_token": "DG1uMMq1M7OeHhds71HlSMHOoI2tFpWCB4ApP00cVFqptmlFKjFu9RluHo2w3mUw"}
```

① 的第一条：

```
纯 Python DES 生成 16 个 Token，首个：凯文-杜兰特 -> DG1uMMq1M7OeHhds71HlSMHOoI2tFpWCB4ApP00cVFqptmlFKjFu9RluHo2w3mUw
```

字符串完全相同——页面上用户看到的那个 Token，就是 Python 算出来的这个。

## 跑法

```bash
cd src/s08_js_reverse/spa7
../../../.venv/bin/python des.py        # DES 自检（FIPS 向量）
../../../.venv/bin/python spider.py     # 主流程：拉 main.js → Python 算 token → Node 交叉验证
```

依赖：`requests`（仓库根 `requirements.txt` 已有）+ 标准库；交叉验证需要 `node`（本机 v26.5.0），
**没有 node 也不影响主流程**，程序会打印 `[warn] 没找到 node，跳过交叉验证` 后继续。

可选的浏览器裁判需要额外依赖（**不写进仓库根 requirements.txt**，只装进 venv）：

```bash
../../../.venv/bin/pip install playwright
../../../.venv/bin/playwright install chromium
../../../.venv/bin/python verify_with_browser.py
```

## 实测输出（真跑，非编造）

### 第 1 次运行 · 2026-08-23 19:56:05 +09:00

```
[2026-08-23T19:56:05+09:00] GET https://spa7.scrape.center/js/main.js
  解析到 16 名球员，DES 密钥 'fipFfVsZsTda94hJNKJfLoaqyqMZFFimwLt'（长度 35，DES 实际只用前 8 字节 'fipFfVsZ'）
  纯 Python DES 生成 16 个 Token，首个：凯文-杜兰特 -> DG1uMMq1M7OeHhds71HlSMHOoI2tFpWCB4ApP00cVFqptmlFKjFu9RluHo2w3mUw
  与站点自带 crypto-js（Node 执行）比对：16/16 完全一致
```

（这次运行早于 `probe_no_api()` 的加入，接口探测输出见第 2 次运行日志。）

### 第 2 次运行 · 2026-08-23 20:07:11 +09:00（完整输出 `data/spa7_run2.log`，上面那段接口探测就出自这次）

```
  纯 Python DES 生成 16 个 Token，首个：凯文-杜兰特 -> DG1uMMq1M7OeHhds71HlSMHOoI2tFpWCB4ApP00cVFqptmlFKjFu9RluHo2w3mUw
  与站点自带 crypto-js（Node 执行）比对：16/16 完全一致
```

**注意 spa7 与 spa2/spa6 的区别：它的 Token 里没有时间戳，是确定性的**，
所以「隔一段时间再跑」得到的是**同一个 token**——这恰恰是正确行为，不是缓存或硬编码。
「换时间点重跑仍成功」的时间敏感性证据由 spa2/spa6 承担；这里两次运行证明的是
「重新拉取 main.js、重新解析、重新计算，结果稳定且与站点一致」。
每次运行都会往 `data/spa7_runs.json` 追加一条记录（时间戳 / 条数 / 交叉验证命中数 / 首个 token）。

## 产出

| 文件 | 内容 |
|---|---|
| `data/spa7_players_tokens.json` | 16 名球员的字段 + Python 算出的 Token + 算法与密钥说明（4.4 KB） |
| `data/spa7_runs.json` | 每次运行的记录 |
| `data/spa7_run2.log` | 第 2 次运行完整终端输出 |

## 代码

| 文件 | 作用 |
|---|---|
| `des.py` | 纯 Python DES（ECB + PKCS7），零依赖，自带 FIPS 测试向量自检 |
| `spider.py` | 拉 main.js → 解析球员与密钥 → 算 Token → Node 交叉验证 → 落盘 |
| `verify_with_node.js` | 用站点自己的 crypto-js 复算，作为对照 |
| `verify_with_browser.py` | 可选：真浏览器读 tooltip，最终裁判 |

## 存证清单（原件，逐字未改）

| 文件 | 来源 |
|---|---|
| `evidence/main.js` | https://spa7.scrape.center/js/main.js 全文（2770 字节）——球员数据、密钥、getToken 都在这 |
| `evidence/index.html` | https://spa7.scrape.center/ 全文（2088 字节）——可见 `:content="getToken(player)"` 与 4 个 script |
| `evidence/crypto-js.min.js` | https://spa7.scrape.center/js/crypto-js.min.js 原样（47992 字节）——站点自己的加密库，交叉验证时被 Node 直接 require |

## 练习伦理

主流程只有 1 个静态资源请求；接口探测 6 个请求、间隔 0.4 秒；浏览器校验是可选步骤。
只针对 scrape.center 练习平台。
