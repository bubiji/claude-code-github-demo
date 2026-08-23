> issue: #11 · 案例: spa2 · 来源: https://spa2.scrape.center

# spa2 · Ajax 接口签名参数（token）逆向

## 案例原文（逐字引自 scrape.center）

> 电影数据网站，无反爬，数据通过 Ajax 加载，数据接口参数加密且有时间限制，适合动态页面渲染爬取或 JavaScript 逆向分析。

本目录走的是**后一条路线：JavaScript 逆向**——不开浏览器，在 Python 侧自己生成 token。

## 结论先说：算法

```
token = base64( sha1( ",".join([*args, t]) ) + "," + t )        t = 当前 Unix 秒（10 位）

列表页 args = ["/api/movie", offset]        → 签名串 "/api/movie,0,1787482635"
详情页 args = ["/api/movie/{key}", 0]       → 签名串 "/api/movie/<key>,0,<t>"
详情 key  = base64("ef34#teuq0btua#(-57w1q5o5--j@98xygimlyfxs*-!i-0-mb" + id)
```

三个容易踩的细节：

1. **时间戳既参与哈希，又明文跟在哈希后面**——服务端从 base64 解出 `<sha1>,<t>`，拿 `t` 重算一遍
   sha1 比对，所以 `t` 不能瞎填，也不需要瞎猜（它就写在 token 里）。
2. **参数顺序和分隔符是签名的一部分**：`,` 连接，时间戳永远追加在最后一位。
3. **列表页多带一个 offset，详情页那位固定是 0**。这个「参数个数」在 spa6 上就变了（见 spa6 案例），
   不是可以想当然照抄的。

sha1 用 `hashlib`、base64 用 `base64`、时间戳用 `time.time()`——**零第三方加密依赖，也没有 Node、没有浏览器**。

## 怎么找到的（含试错）

**第 0 步：确认数据不在 HTML 里。** `curl https://spa2.scrape.center/` 返回 1007 字节的 Vue 空壳，
只有 `<div id=app></div>` 和两个 script。数据必然走 XHR。

**第 1 步：在入口 bundle 里搜 token —— 落空。**

```
$ grep -c token spa2_app.js
0
```

这是第一个坑：`app.e9fbf43f.js` 只有 5.9 KB，是 webpack 入口，页面组件被路由懒加载切成了 chunk。
但坑本身给了线索——首页 HTML 的 `<link rel=prefetch>` 已经把 chunk 名字全列出来了：
`chunk-10192a00`（列表页）、`chunk-7502f973`（详情页）、`chunk-4136500c`（两页共用的公共依赖）。

**第 2 步：把三个 chunk 都拉下来再搜。**

```
$ grep -c token spa2_chunk-10192a00.js spa2_chunk-7502f973.js spa2_chunk-4136500c.js
1  1  0
```

列表页 chunk 命中一次，上下文（原件见 `evidence/spa2_chunk-10192a00_index_call_site.js`）：

```js
onFetchData:function(){var t=this;this.loading=!0;var a=(this.page-1)*this.limit,e=Object(i["a"])(this.$store.state.url.index,a);this.$axios.get(this.$store.state.url.index,{params:{limit:this.limit,offset:a,token:e}})...
```

读出三件事：token 由 `i["a"](url, offset)` 算出；`i` 是 webpack import；同一段开头写着 `i=e("7d92")`，
所以**生成器就是模块 `7d92`**——但 `7d92` 不在这个 chunk 里，它在公共 chunk。

**第 3 步：在公共 chunk 里定位 `7d92` —— 关键字选择上试错了两次。**

- `grep btoa` → **0 命中**。以为会用浏览器原生 base64，猜错了；他们用的是 CryptoJS 的 Base64。
- `grep SHA1` → 命中的第一处是 crypto-js **自己的 PBKDF2 模块**（`o.SHA1` 只是库内部引用），
  是库代码不是业务代码，看半天没用。
- `grep getTime` → **全 chunk 唯一一处命中**，就是 `7d92`。事后总结：这类「参数带时间限制」的签名，
  **时间戳是最有辨识度的锚点**——加密库里到处是 SHA1/Base64，但没人在库里调 `new Date().getTime()`。

原件（`evidence/spa2_chunk-4136500c_module_7d92_token.js`，逐字）：

```js
"7d92":function(t,e,r){"use strict";r("6b54");var n=r("3452");function i(){for(var t=Math.round((new Date).getTime()/1e3).toString(),e=arguments.length,r=new Array(e),i=0;i<e;i++)r[i]=arguments[i];r.push(t);var o=n.SHA1(r.join(",")).toString(n.enc.Hex),c=n.enc.Base64.stringify(n.enc.Utf8.parse([o,t].join(",")));return c}e["a"]=i}
```

读法：`arguments` 全收进数组 → `push(t)` 把时间戳追加到末尾 → `join(",")` → SHA1 取 Hex →
`[hex, t].join(",")` → Base64。这就是上面那行公式。

**第 4 步：接口路径与详情 key。** `app.js` 里的 Vuex store 给出路径（原件 `evidence/spa2_app_store_url.js`）：

```js
{state:{url:{index:"/api/movie",detail:"/api/movie/{key}"}}
```

详情页链接里的 key 是 `transfer(a.id)`，`transfer` 是模块 `3e22`（原件 `evidence/spa2_chunk-4136500c_module_3e22_transfer.js`）：

```js
"3e22":function(t,e,r){"use strict";var n="ef34#teuq0btua#(-57w1q5o5--j@98xygimlyfxs*-!i-0-mb",i=r("3452");function o(t){return i.enc.Base64.stringify(i.enc.Utf8.parse(n+t))}e["a"]=o}
```

## 「有时间限制」到底是多少——实测

不猜，直接把时间戳前后平移，看服务端认不认（`spider.py --window`，结果落 `data/spa2_token_timewindow.json`）：

| Δt | -3600 | -600 | -300 | -200 | -181 | **-180** | -60 | 0 | +60 | +179 | **+180** | +181 | +300 | +600 | +3600 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| HTTP | 401 | 401 | 401 | 401 | 401 | **200** | 200 | 200 | 200 | 200 | **200** | 401 | 401 | 401 | 401 |

**窗口 = 服务端当前时间 ±180 秒**（前后各 3 分钟）。边界上有约 1 秒抖动（本地算时间戳到服务端收到请求之间的往返延迟），
spa6 同一组探测量到的是 `[-181, +179]`，是同一个 180 秒窗口。
另外服务端 `Date` 头显示它和本机时钟只差 **-0.7 秒**，所以这里量到的就是策略窗口本身，不是时钟偏差。

推论：**任何硬编码 token 最多活 3 分钟**，这就是本阶段「必须在 Python 侧现算」的硬理由。

## 跑法

```bash
cd src/s08_js_reverse/spa2
../../../.venv/bin/python spider.py            # 旧 token 重放反证 + 列表全量 + 详情抽样
../../../.venv/bin/python spider.py --window   # 额外做一次时间窗口探测
```

依赖：只用 `requests`（已在仓库根 `requirements.txt`）+ 标准库 `hashlib`/`base64`。**无额外依赖。**

## 实测输出（真跑，非编造）

### 第 1 次运行 · 2026-08-23 19:57:15 +09:00

```
[列表页] /api/movie  token 参数 = ["/api/movie", offset, t]
  offset=0   HTTP 200  +10 条  累计 10/104  token=MjBkNDczN2ZjZWExZmQ3OWZkZmM0...
  ...
  offset=100 HTTP 200  +4 条  累计 104/104  token=Zjg2NGViNWIzN2Q2YjhkZDIzMmE0...
[详情页] /api/movie/{key}  token 参数 = [path, 0, t]（抽样 5 条）
  detail id=1   HTTP 200  霸王别姬  score=9.5
  detail id=2   HTTP 200  这个杀手不太冷  score=9.5
  detail id=3   HTTP 200  肖申克的救赎  score=9.5
  detail id=4   HTTP 200  泰坦尼克号  score=9.5
  detail id=5   HTTP 200  罗马假日  score=9.5
共发出 31 个请求
```

### 第 2 次运行 · 2026-08-23 20:06:09 +09:00（完整输出 `data/spa2_run2.log`）

### 第 3 次运行 · 2026-08-23 20:07:53 +09:00（完整输出 `data/spa2_run3.log`）

`data/spa2_runs.json` 逐次记录（节选自真实文件）：

| 运行 | run_at | unix_ts | 首个列表 token | 结果 |
|---|---|---|---|---|
| 1 | 2026-08-23T19:57:15+09:00 | 1787482635 | `MjBkNDczN2ZjZWExZmQ3OWZkZmM0YTkyYTlkM2UwMWZiN2FkOGVjOSwxNzg3NDgyNjM1` | 104/104 |
| 2 | 2026-08-23T20:06:09+09:00 | 1787483169 | `MDY3Njc0NTg3Mjc3OGI0NmY5M2IyNDU4NTNmZjljNmM1Yzg0MGNiMCwxNzg3NDgzMTcw` | 104/104 |

相隔 **8 分 54 秒**，token 完全不同（时间戳变了 → sha1 变了），**两次都 200 拿满 104 条**。
这就是「换个时间点重跑仍能生成合法参数」的证据。

### 反证：旧 token 重放必失效

第 3 次运行开头会自动重放**第 1 次运行记录下来的那个 token**（`replay_stale_token()`，
结果追加进 `data/spa2_stale_token_replay.json`）：

```
[旧 token 重放] 重放 2026-08-23T19:57:15+09:00 那次的 token（已过 638 秒）-> HTTP 401（超过 180 秒就该是 401）

[列表页] /api/movie  token 参数 = ["/api/movie", offset, t]
  offset=0   HTTP 200  +10 条  累计 10/104  token=NGUzZDdjYmUzYTE2OTE5YjVlZGQx...
```

**同一次运行里，10 分 38 秒前的旧 token 拿到 401，现算的新 token 拿到 200。**
硬编码复用这条路到此被堵死。

## 产出

| 文件 | 内容 |
|---|---|
| `data/spa2_movies.json` | 列表接口全量 104 条（42.8 KB，< 500 KB 无需降级） |
| `data/spa2_details_sample.json` | 详情接口抽样 5 条（证明详情 token 形态） |
| `data/spa2_token_timewindow.json` | 时间窗口探测的 15 个数据点 |
| `data/spa2_runs.json` | 每次运行的时间戳 / 请求数 / 首个 token（多次运行的证据链） |
| `data/spa2_stale_token_replay.json` | 旧 token 重放的结果（age_seconds + HTTP 状态） |
| `data/spa2_run2.log` `data/spa2_run3.log` | 第 2、3 次运行的完整终端输出 |
| `evidence/*.js` | 分析用到的**原始 JS 片段**，每份带来源 URL、字符区间、SHA-256 与重新取件命令 |

## 存证清单（原件，逐字未改）

| 文件 | 来源 |
|---|---|
| `evidence/spa2_chunk-4136500c_module_7d92_token.js` | `chunk-4136500c.f3e9bb54.js` 字符 [27161, 27493) —— token 生成器 |
| `evidence/spa2_chunk-4136500c_module_3e22_transfer.js` | 同上 [21296, 21480) —— 详情 key 的 transfer |
| `evidence/spa2_chunk-10192a00_index_call_site.js` | `chunk-10192a00.243cb8b7.js` [2008, 2652) —— 列表页调用点 |
| `evidence/spa2_chunk-7502f973_detail_call_site.js` | `chunk-7502f973.428355cb.js` [7799, 8416) —— 详情页调用点 |
| `evidence/spa2_app_store_url.js` | `app.e9fbf43f.js` [5029, 5137) —— Vuex 里的接口路径 |

## 练习伦理

请求间隔 0.8 秒、串行、单线程；详情页只抽样 5 条不全量刷；时间窗口探测 15 个请求间隔 0.4 秒。
只针对 scrape.center 这个作者公开提供的练习平台。
