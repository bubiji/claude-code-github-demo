> issue: #12 · 案例: antispider8 · 来源: https://antispider8.scrape.center

# antispider8 —— 无限 debugger + 定时循环 debugger

## 案例原描述（逐字引自 https://scrape.center/）

> JavaScript 反爬，增加了接口处的无限 debugger 和定时循环 debugger。

---

## 一、debugger 的确切出处：3 条语句，2 种机制

站点是 Vue CLI 打包的 SPA，没做混淆，只是压缩过。grep 一遍 `debugger` 就定位干净 —— **共 3 条语句，分属 2 种机制**（一个定时器 + 两个组件的 `onFetchData`）。下列代码块**逐字引自站点下发的 chunk，未改动**：

**① 定时循环 debugger —— `js/app.40192839.js`**

```js
r.default.config.productionTip=!1,setInterval((function(){debugger;console.log("debugger")}),1e3),new r.default({store:p,router:m,render:function(e){return e(s)}}).$mount("#app")
```

**② 接口处 debugger —— `js/chunk-51935b2c.7a777070.js`（列表页组件）**

```js
onFetchData:function(){var t=this;debugger;this.loading=!0;var a=(this.page-1)*this.limit,e=Object(s.a)(this.$store.state.url.index);this.$axios.get(this.$store.state.url.index,{params:{limit:this.limit,offset:a,token:e}}).then((function(a){var e=a.data,s=e.results,n=e.count;t.loading=!1,t.movies=s,t.total=n}))}
```

**③ 接口处 debugger —— `js/chunk-27855899.741dfe15.js`（详情页组件）**，同一模式：

```js
onFetchData:function(){var t=this;debugger;this.loading=!0;var e=s(this.$store.state.url.detail,{key:this.key}),a=Object(r.a)(e);this.$axios.get(e,{params:{token:a}}).then((function(e){var a=e.data;t.loading=!1,t.movie=a}))}
```

注意描述里的「**无限** debugger」在这个站点上其实是「**每次进 onFetchData 就断一次**」+「**每秒断一次的定时器**」的组合，不是那种 `Function("debugger")()` 递归自调的经典无限 debugger。实测证据见下面 E1：8 秒窗口内断 8 次。

---

## 二、四种绕过手段的实测对照

`debugger_bypass.py` 跑五组受控实验，每组只改一个变量。判据是 8 秒窗口内的 **CDP `Debugger.paused` 事件次数** + **页面实际渲染出的电影卡片数** —— 「看着没卡」不算证据，事件计数才算。

| 实验 | 手段 | `Debugger.paused` | 卡片 | `/api/movie` | 结论 |
|---|---|---|---|---|---|
| **E0** | 不接调试器，headless 直接打开 | **0** | 10 | 200 | `debugger` 只对**已附着调试器**的引擎生效 |
| **E1** | 接 CDP `Debugger.enable`，不做任何对抗 | **8** | 10 | 200 | 陷阱是真的，8 秒被打断 8 次 |
| **E2** | route 中间人改写 js 响应，剥掉 debugger | **0** | 10 | 200 | 彻底。拦下 7 个 js 请求，去重后实有 **3** 条语句 |
| **E3** | CDP `Debugger.setSkipAllPauses(true)` | **0** | 10 | 200 | 彻底。等价于 DevTools 的「停用断点 / Never pause here」 |
| **E4** | `addInitScript` 置换 `setInterval` | **1** | 10 | 200 | **只治定时那一个**，接口处那条照断 |

数据出自 `evidence/debugger_bypass.json`（每次运行重算）。

### E0 是最容易被忽略的一条结论

**`debugger` 语句在没有调试器附着时是空操作。** 所以「无限 debugger」拦不住 Playwright / Puppeteer / Selenium 本身 —— E0 里页面正常渲染 10 张卡片、接口正常 200。它拦的是**人**：你打开 DevTools 想看看接口参数怎么来的，立刻被按在断点上，一秒一次，什么也干不了。

把它当成「反自动化」去设计对策，方向就错了；它是**反人工调试**。

### E2 的实现要点：不能用 `replace("debugger","")`

`app.js` 里紧跟着一句 `console.log("debugger")`，字符串里那个 `debugger` 不能动 —— 动了就改变了页面行为，实验也就不干净了。所以边界条件是「前面不能是标识符字符或引号」：

```python
DEBUGGER_STMT = re.compile(r"(?<![\w$.\"'])debugger\s*;?")
```

这条正则在 `app.js` 上的实测结果就是它存在的理由：该文件里 `debugger` 出现 **2** 次，而语句只有 **1** 条 —— 多出来的那次正是 `console.log("debugger")` 里的字符串。

逐文件记账（`evidence/debugger_bypass.json` 的「改写统计」）：

| js 文件 | 被拦次数 | 每次剥掉的语句 |
|---|---|---|
| `app.40192839.js` | 1 | 1 |
| `chunk-51935b2c.7a777070.js`（列表） | 2 | 1 |
| `chunk-27855899.741dfe15.js`（详情） | 1 | 1 |
| `chunk-4136500c.36dbfdb6.js` | 2 | 0 |
| `chunk-vendors.85236b05.js` | 1 | 0 |

**累计剥掉 4 条，但站点里实有的只有 3 条。** 差的那一条是 `chunk-51935b2c` 被请求了两次（页面 `<link rel=prefetch>` 一次 + 路由真正加载一次），同一条语句被剥了两遍。只报「剥掉 4 条」会让人以为站点埋了 4 处 —— 所以脚本同时报**去重后的 3 条**，README 里的表格也按逐文件给。这类「累计数 ≠ 实有数」的坑，在中间人改写场景里非常容易把结论写歪。

### E3 踩过的坑：`setSkipAllPauses` 是会话状态，导航会重置

第一版在 `page.goto()` **之前**下这条 CDP 指令，E3 记到 8 次 pause，看着像「这招没用」。改成导航之后再下一次，立刻降到 0。这个坑值得单记 —— 一个正确的手段因为下发时机不对被误判成无效，是逆向里很常见的错误结论来源。

### E4 说明了「部分手段」长什么样

置换 `setInterval` 只干掉 1 个定时器（`window.__killedIntervals === 1`），剩下的那 1 次 pause 正是 `onFetchData` 里那条 —— 两处 debugger 是**不同机制**，一招只能治一处。想一招通吃，只能选 E2 或 E3。

---

## 三、但实际抓数据用的是第五种：根本不进浏览器

`spider.py` **全程 `requests`，一行浏览器代码都没有**。`debugger` 是给 JS 引擎的指令，requests 眼里它连字符都不是。这是对付反调试最彻底的一种——**逆向的目标从来不是「在浏览器里把页面点开」，而是把 token 算法搬到浏览器外面**。

### Token 算法（还原自 `js/chunk-4136500c.36dbfdb6.js`）

模块 `"7d92"` 原文（逐字引自站点下发的 chunk）：

```js
"7d92":function(t,e,r){"use strict";r("6b54");var i=r("3452");e.a=function(){for(var t=Math.round((new Date).getTime()/1e3).toString(),e=arguments.length,r=new Array(e),n=0;n<e;n++)r[n]=arguments[n];r.push(t);var o=i.SHA1(r.join(",")).toString(i.enc.Hex),s=i.enc.Base64.stringify(i.enc.Utf8.parse([o,t].join(",")));return s}}
```

读法：把「若干参数 + 当前 unix 秒」用逗号连成一串取 SHA1（十六进制），再把 `"sha1十六进制,unix秒"` 整体做 Base64。Python 复刻：

```python
def make_token(*args):
    ts = str(round(time.time()))
    sha1_hex = hashlib.sha1(",".join([*args, ts]).encode()).hexdigest()
    return base64.b64encode(f"{sha1_hex},{ts}".encode()).decode()
```

调用点传的是**路径模板填好后的字符串**，不是完整 URL（`js/app.40192839.js` 里 `state:{url:{index:"/api/movie",detail:"/api/movie/{key}"}}`）。

### 详情页 key（还原自同一 chunk 的模块 `"3e22"`）

```js
"3e22":function(t,e,r){"use strict";var i=r("3452");e.a=function(t){return console.log("stttt",t),i.enc.Base64.stringify(i.enc.Utf8.parse("ef34#teuq0btua#(-57w1q5o5--j@98xygimlyfxs*-!i-0-mb"+t))}}
```

固定盐 + 电影自增 id，整体 Base64。（原作者调试时留下的 `console.log("stttt", t)` 也照抄，不做美化。）

### 实测输出

```
$ python spider.py
[antispider8] 开抓（不启动浏览器）
  · 不带 token: HTTP 401
  · 列表: 104/104 条，11 次请求全部 200
  · 详情: 取前 5 部，全部 200
{
  "no_token_status": 401,
  "count": 104,
  "fetched": 104,
  "requests": 11,
  "details": 5,
  "first": "霸王别姬"
}
```

`no_token_status: 401` 是反证 —— token 确实是门槛，不是摆设。

---

## 四、「隔一段时间跑两次都成功」

antispider8 的 token **嵌了 unix 秒**，所以合格判据是「两轮 token **不同**、但两轮都成功」；**如果两轮 token 相同，那才说明是把浏览器里抄来的固定值写死了**。

`python ../tools/run_all.py --gap 150` 实测（`../evidence/run_all_twice.json`）：

| | 第 1 轮 | 第 2 轮 |
|---|---|---|
| 时间 | 2026-08-23 20:08:38 +0900 | 2026-08-23 20:11:49 +0900 |
| 抓到 | 104 / 104 | 104 / 104 |
| 响应码 | 全 200 | 全 200 |
| 首个 token | `NWE1MGQ3MDJmYzBhZDdmZDU2…` | `NjM0MDU5NzU1MDRkNWJkMDM3…` |
| 无 token 时 | HTTP 401 | HTTP 401 |

判定：**PASS（token 现算，非硬编码）**。

---

## 五、跑起来

```bash
PY=/Users/deanlee/Documents/Claude/Projects/git_github/.venv/bin/python

$PY spider.py                # 抓数据，不进浏览器
$PY spider.py --twice 90     # 隔 90s 跑两次
$PY debugger_bypass.py       # 五组 debugger 绕过对照实验（启动 headless Chromium）
```

## 产物

| 路径 | 内容 |
|---|---|
| `data/antispider8_movies.json` | 104 部电影 + 前 5 部详情 + 每次请求的 trace |
| `evidence/debugger_bypass.json` | 五组实验的 paused 计数与渲染结果 |
| `evidence/twice_run.json` | `--twice` 模式的两轮对比（若跑过） |

## 抓取礼貌

`common.PoliteSession`：串行、请求间隔 1.0–1.3 秒（含抖动）、失败指数退避。一次完整运行 = 1 次反证请求 + 11 次列表 + 5 次详情 = 17 次请求。不压测。
