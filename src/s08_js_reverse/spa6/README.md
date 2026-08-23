> issue: #11 · 案例: spa6 · 来源: https://spa6.scrape.center

# spa6 · 混淆源码下定位加密入口

## 案例原文（逐字引自 scrape.center）

> 电影数据网站，数据通过 Ajax 加载，数据接口参数加密且有时间限制，源码经过混淆，适合 JavaScript 逆向分析。

## 结论先说：算法

```
token = base64( sha1( ",".join([*args, t]) ) + "," + t )        t = 当前 Unix 秒

列表页 args = ["/api/movie"]            → 签名串 "/api/movie,1787482714"     ← 不带 offset！
详情页 args = ["/api/movie/{key}"]      → 签名串 "/api/movie/<key>,<t>"      ← 不带那个 0！
详情 key  = base64("ef34#teuq0btua#(-57w1q5o5--j@98xygimlyfxs*-!i-0-mb" + id)
```

**算法本体和 spa2 一模一样，但调用参数少一个。** 这是 spa6 真正会绊人的地方：混淆看着吓人，
实际改的只是「代码长什么样」；真正的行为差异藏在一个不起眼的实参上——照抄 spa2 的写法会稳定 401。

对照实验（`spider.py` 默认就跑，结果落 `data/spa6_arity_contrast.json`）：

| 实验 | 结果 |
|---|---|
| spa6 接口 + spa2 写法（token 参数带 offset） | **HTTP 401** |
| spa2 接口 + spa6 写法（token 参数不带 offset） | **HTTP 401** |
| spa6 接口 + spa6 写法 | HTTP 200 |

## 怎么找到的——混淆下的定位路径（含试错）

拉下来的四个 bundle 长这样（`_0x` 是混淆器生成的标识符）：

```
$ head -c 120 spa6_app.js
(function(_0x2c4462){function _0x3de9fc(_0x4ebc91){for(var _0x22c5a6,_0x1cffb8,_0x1febda=_0x4ebc91[0x0],...
```

混淆器（obfuscator.io 风格）在这里干了四件事：

1. 标识符全部换成 `_0x` + 随机十六进制，语义信息归零；
2. **所有成员访问从 `a.b` 改写成 `a['b']`**；
3. 数字字面量改成十六进制（`1000` → `0x3e8`，`0` → `0x0`，`true` → `!0x0`）；
4. 单引号统一，方便字符串数组化。

**关键判断：它没有做「字符串数组 + 解密函数」那一层。** 判断依据很直接——

```
$ grep -c 'api/movie' spa6_app.js
2
```

字面量 `'/api/movie'` 明文还在。如果做了字符串加密，这里会是 `_0x1a2b(0x1f)` 这种调用，
那就得先还原字符串表才能搜。既然没加密，**关键字搜索这条路依然可用**，只是关键字要挑对。

于是：

**试错 1：搜 `token` —— 部分落空。** `spa6_app.js` 里 0 命中（和 spa2 一样，页面组件在懒加载 chunk 里）。
换成从首页 HTML 的 `<link rel=prefetch>` 拿 chunk 列表再逐个搜，
`chunk-19c920f8`（列表页）和 `chunk-2f73b8f3`（详情页）各命中 1 次。
`token` 之所以还搜得到，是因为**它是 HTTP query 参数名、不是标识符**，混淆器不敢改（改了接口就废了）。
这条经验可以推广：**混淆改得动变量名，改不动协议里的字段名。**

**试错 2：搜 `SHA1` —— 命中 6 处，全是 crypto-js 库自己的。** 和 spa2 踩的是同一个坑。

**成了：搜 `getTime` —— 全站唯一 1 处命中**，就在 `chunk-4dec7ef0` 的模块 `'7d92'`。
理由和 spa2 一样：加密库里 SHA1/Base64 满地都是，但**没有哪个库会去调 `new Date().getTime()`**，
而「参数带时间限制」的签名一定要取当前时间。混淆再狠，`getTime` 这个**宿主环境 API 名**也不能改。

原件（`evidence/spa6_chunk-4dec7ef0_module_7d92_token.js`，逐字）：

```js
'7d92':function(_0x1e1673,_0x29aaea,_0x34777a){'use strict';_0x34777a('6b54');var _0x189cbb=_0x34777a('3452'),_0x358b1f=_0x34777a('27ae')['Base64'];function _0x456254(){for(var _0x5da681=Math['round'](new Date()['getTime']()/0x3e8)['toString'](),_0x2a83dd=arguments['length'],_0x31a891=new Array(_0x2a83dd),_0x596a02=0x0;_0x596a02<_0x2a83dd;_0x596a02++)_0x31a891[_0x596a02]=arguments[_0x596a02];_0x31a891['push'](_0x5da681);var _0xf7c3c7=_0x189cbb['SHA1'](_0x31a891['join'](','))['toString'](_0x189cbb['enc']['Hex']),_0x3c8435=[_0xf7c3c7,_0x5da681]['join'](','),_0x104b5b=_0x358b1f['encode'](_0x3c8435);return _0x104b5b;}_0x29aaea['a']=_0x456254;},
```

我手写的还原版在 `evidence/spa6_module_7d92_token.deobfuscated.mine.js`，**那份是我的注释、不是原件**，
两份并排放，以原件为准。

**读混淆代码的三条实操**（这次真用上的）：

- **`['xxx']` 全是宝**：混淆器把成员名留成了字符串字面量，`['SHA1']`、`['getTime']`、`['join']`、`['encode']`
  连起来读，一行代码的语义就出来了，`_0x` 叫什么根本不用管。
- **十六进制换算回去**：`0x3e8`=1000（毫秒转秒）、`0x0`=0、`!0x1`=false。`/0x3e8` 一出现，
  基本可以断定这是「取秒级时间戳」。
- **webpack 模块 id 没被混淆**：`'7d92'`、`'3e22'` 这些 id 在 spa2 和 spa6 里**完全相同**，
  因为它们是打包器生成的、不是源码标识符。这直接给了一条捷径：先在未混淆的 spa2 里读懂 `7d92`，
  再回 spa6 逐字节比对同名模块的差异——差异只有 Base64 的实现（spa2 用 `CryptoJS.enc.Base64`，
  spa6 用 `js-base64` 的 `Base64.encode`，输出等价）。

**最后一步也是最容易漏的一步：看调用点，不要只看生成器。**
`evidence/spa6_chunk-19c920f8_index_call_site.js`（原件）：

```js
var _0x422986=(this['page']-0x1)*this['limit'],_0x263439=Object(_0x2fa7bd['a'])(this['$store']['state']['url']['index']);this['$axios']['get'](this['$store']['state']['url']['index'],{'params':{'limit':this['limit'],'offset':_0x422986,'token':_0x263439}})
```

`offset` 变量 `_0x422986` **算出来了、也放进了 params，但没传进 token 生成器**。
spa2 的同一行是 `Object(i["a"])(this.$store.state.url.index,a)`——多一个 `a`。
一个字符的差别，决定 200 还是 401。这也是为什么本目录专门写了那个对照实验：这种结论必须实测钉死。

## 「有时间限制」实测

`spider.py --window`，结果落 `data/spa6_token_timewindow.json`：

| Δt | -3600 | -600 | -300 | -200 | **-181** | -180 | -60 | 0 | +60 | **+179** | +180 | +181 | +300 | +600 | +3600 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| HTTP | 401 | 401 | 401 | 401 | **200** | 200 | 200 | 200 | 200 | **200** | 401 | 401 | 401 | 401 | 401 |

**窗口 = ±180 秒**，与 spa2 同一策略。这一趟量到的可接受区间是 `[-181, +179]`，spa2 那趟是 `[-180, +180]`——
差的那 1 秒是本地生成时间戳到服务端收包之间的往返延迟，不是两站策略不同。
**硬编码 token 最多活 3 分钟**，所以必须在 Python 侧现算。

## 跑法

```bash
cd src/s08_js_reverse/spa6
../../../.venv/bin/python spider.py            # 列表全量 + 详情抽样 + 参数个数对照实验
../../../.venv/bin/python spider.py --window   # 额外做时间窗口探测
```

依赖：只用 `requests` + 标准库 `hashlib`/`base64`。**无额外依赖、无 Node、无浏览器。**

## 实测输出（真跑，非编造）

### 第 1 次运行 · 2026-08-23 19:58:34 +09:00

```
[列表页] /api/movie  token 参数 = ["/api/movie", t]
  offset=0   HTTP 200  +10 条  累计 10/104  token=NWRjNmNkMzgwYzEzOGVlYTA2N2Rk...
  ...
  offset=100 HTTP 200  +4 条  累计 104/104  token=MWZkZjUzMGJhZTVkZDk1Y2NjYzFm...
[详情页] /api/movie/{key}  token 参数 = [path, t]（抽样 5 条）
  detail id=1   HTTP 200  霸王别姬  score=9.5
  detail id=2   HTTP 200  这个杀手不太冷  score=9.5
  detail id=3   HTTP 200  肖申克的救赎  score=9.5
  detail id=4   HTTP 200  泰坦尼克号  score=9.5
  detail id=5   HTTP 200  罗马假日  score=9.5
[参数个数对照实验]
  spa6 接口 + spa2 写法（token 参数带 offset）-> HTTP 401（期望 401）
  spa2 接口 + spa6 写法（token 参数不带 offset）-> HTTP 401（期望 401）
共发出 33 个请求
```

### 第 2 次运行 · 2026-08-23 20:06:38 +09:00（完整输出 `data/spa6_run2.log`）

`data/spa6_runs.json` 逐次记录（节选自真实文件）：

| 运行 | run_at | unix_ts | 首个列表 token | 结果 |
|---|---|---|---|---|
| 1 | 2026-08-23T19:58:34+09:00 | 1787482714 | `NWRjNmNkMzgwYzEzOGVlYTA2N2RkNTlhZTE0Nzk0OWZkNWE0MWZkNywxNzg3NDgyNzE1` | 104/104 |
| 2 | 2026-08-23T20:06:38+09:00 | 1787483198 | `ZWNiOTM1NDVhZTUzZTVkNTIzYzgzMDYyNjhiZGI0OGE3NDhhMWEwNiwxNzg3NDgzMTk5` | 104/104 |

相隔 **8 分 04 秒**，token 完全不同，**两次都 200 拿满 104 条**，对照实验两次都是双向 401。
（更直接的「旧 token 重放 → 401」反证做在 spa2 目录里，两站是同一套时间策略。）

## 产出

| 文件 | 内容 |
|---|---|
| `data/spa6_movies.json` | 列表接口全量 104 条（42.8 KB） |
| `data/spa6_details_sample.json` | 详情接口抽样 5 条 |
| `data/spa6_arity_contrast.json` | 「参数个数」对照实验结果 |
| `data/spa6_token_timewindow.json` | 时间窗口探测 15 个数据点 |
| `data/spa6_runs.json` | 每次运行的时间戳 / 请求数 / 首个 token |
| `data/spa6_run2.log` | 第 2 次运行完整终端输出 |

## 存证清单

**原件（逐字未改，每份带来源 URL、字符区间、SHA-256、重新取件命令）**

| 文件 | 来源 |
|---|---|
| `evidence/spa6_chunk-4dec7ef0_module_7d92_token.js` | `chunk-4dec7ef0.e4c2b130.js` 字符 [64199, 64847) —— token 生成器 |
| `evidence/spa6_chunk-4dec7ef0_module_3e22_transfer.js` | 同上 [48855, 49182) —— 详情 key 的 transfer |
| `evidence/spa6_chunk-19c920f8_index_call_site.js` | `chunk-19c920f8.c3a1129d.js` [3223, 4219) —— 列表页调用点（少一个实参就在这里） |
| `evidence/spa6_chunk-2f73b8f3_detail_call_site.js` | `chunk-2f73b8f3.8f2fc3cd.js` [14441, 15368) —— 详情页调用点 |
| `evidence/spa6_app_store_url.js` | `app.5ef0d454.js` [9577, 9716) —— Vuex 里的接口路径 |

**非原件（我写的）**

| 文件 | 说明 |
|---|---|
| `evidence/spa6_module_7d92_token.deobfuscated.mine.js` | 我手工重命名标识符后的还原版，仅供阅读；有出入以原件为准 |

## 练习伦理

请求间隔 0.8 秒、串行；详情只抽样 5 条；对照实验一共 2 个请求。只针对 scrape.center 练习平台。
