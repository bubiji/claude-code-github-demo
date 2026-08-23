> issue: #12 · 阶段: 阶段 9 JS 混淆对抗 · 来源: https://scrape.center/

# 阶段 9：JS 混淆对抗（spa8–spa13 + antispider8）

七个案例，**全程不靠浏览器抓数据**。唯一启动 Chromium 的地方是 `antispider8/debugger_bypass.py` —— 它不抓数据，只做 debugger 绕过手段的对照实验。

```
src/s09_js_obfuscation/
├── README.md            # 本文件：混淆特征 → 识别方法 → 还原手段 速查表
├── common.py            # 传输层 + DES Token 复刻 + Node 工具封装 + 落盘
├── pipeline.py          # spa8–spa13 共用五步流水线（取原件→还原→取值→对照→落盘）
├── tools/
│   ├── unwrap.js        # 通用还原：JJEncode / AAEncode / JSFuck / eval-packer
│   ├── strarray.js      # javascript-obfuscator 字符串数组还原
│   ├── extract.js       # 假 Vue 接住 new Vue(...)，取出 key 与 players
│   ├── reftoken.js      # 用站点自带 crypto-js 算 token，作 Python 的对照基准
│   └── run_all.py       # 七案例跑两轮 + 六站横向对账
├── vendor/crypto-js.min.js   # 站点原件，对照基准依赖
├── spa8/ … spa13/       # 六个混淆变体，各自 spider.py + evidence/ + data/
├── antispider8/         # spider.py（不进浏览器）+ debugger_bypass.py（进浏览器做实验）
└── evidence/run_all_twice.json
```

---

## 一、速查表：混淆特征 → 识别方法 → 还原手段

| # | 混淆 | 肉眼特征（看一眼就能认出） | 机器识别方法 | 还原手段 | 本仓库实现 |
|---|---|---|---|---|---|
| 1 | **无混淆 / 内联** | 正常 JS，只是塞在 HTML 的 `<script>` 里 | `<script>` 无 `src` 属性且含业务标识（如 `getToken`） | 不用还原，直接读；只需从 HTML 里择出内联块 | `pipeline._pick_inline_script()` |
| 2 | **eval / packer**<br>(Dean Edwards) | 开头永远是 `eval(function(p,a,c,k,e,r){…}('…',[],62,'a\|b\|c'.split('\|'),0,{}))` | 正则 `function\(p,a,c,k,e,r\)` | 钩住 `eval` 记下入参 | `tools/unwrap.js`（eval 探针） |
| 3 | **JJEncode** | 满屏 `$` 与下划线：`$=~[];$={___:++$,$$$$:(![]+"")[$],…}` | 前 32 字节匹配 `^\$=~\[\];\$=\{` | 钩住 `Function.prototype.constructor` | `tools/unwrap.js` |
| 4 | **AAEncode** | 日文颜文字：`ﾟωﾟﾉ= /｀ｍ´）ﾉ ~┻━┻ //*´∇｀*/ ['_'];` | 含 `ﾟωﾟﾉ` / `(ﾟДﾟ)` | 同上 | `tools/unwrap.js` |
| 5 | **JSFuck** | 只有 `[ ] ( ) ! +` 六个字符，别的一个没有 | 字符集 ⊆ `[]()!+` 且长度巨大 | 同上 | `tools/unwrap.js` |
| 6 | **JavaScript Obfuscator**<br>(obfuscator.io) | `const _0x4afa=['\x31\x39…']` 大字符串数组 + `_0x3431(0x2f)` 下标调用 + `while(--b){a.push(a.shift())}` 旋转 | 正则 `_0x[0-9a-f]{4,}` 密集出现 | ①跑「数组+旋转+解码器」前言 ②替换解码器调用 ③去转义 | `tools/strarray.js` |
| 7 | **无限 / 定时 debugger** | 源码里出现裸 `debugger;`，或 `setInterval(function(){debugger},1e3)` | grep `debugger` | 见下面第三节四种手段 | `antispider8/debugger_bypass.py` |

### 三、四、五号共用一把钥匙

JJEncode、AAEncode、JSFuck 看着天差地别，**破法完全一样**，因为它们的性质是同一个：

> 它们不隐藏语义，只是把「源码字符串」用符号运算重新拼一遍，最后必须把这个字符串
> 交给一个能吃字符串当代码的入口。JS 里这样的入口只有 `eval` 和 `Function` 构造器两个。

而混淆代码不敢直接写全局标识符 `Function`（太显眼），一律绕原型链去取：

```
JJEncode : (1)["constructor"]["constructor"]      → Number.constructor
JSFuck   : [][ "filter" ]["constructor"]          → Function.prototype.constructor
AAEncode : (ﾟДﾟ)['_']                              → 同样落到 constructor 上
```

三条路的终点是同一个对象 —— **`Function.prototype.constructor`**。把它换成一个「先记账、再放行」的探针，payload 源码就在执行前落到手里：

```js
Object.defineProperty(Function.prototype, 'constructor', { value: FunctionProbe, ... });
```

所以 `tools/unwrap.js` 一个文件同时对付四种混淆（含 packer 的 `eval`），**一个颜文字都不用读懂**。这是本阶段最值钱的一条结论。

### 六号为什么要单独一把钥匙

obfuscator.io 的产物**不存在「最终 payload 字符串」** —— 它没有解码执行的一步，代码是直接可运行的，只是所有字面量被抽走、下标化、并且数组在运行时被旋转过。所以钩执行入口钩不到东西，只能：

1. **把「数组声明 + 旋转 IIFE + 解码器声明」这段前言原样跑一遍。** 旋转是运行时行为 —— 静态读那个数组只会拿到错位的字符串，必须真跑。
2. 从沙箱里取出解码器，把源码中每一处 `别名('0x2f')` 就地换成真实返回值。
   （解码器会被起若干局部别名，`strarray.js` 递归收集，本例找到 4 个：`_0x3431 / _0x5e920f / _0x511d2e / _0x3c8dcd`，共替换 69 处。）
3. 扫字符串字面量去 `\xNN` 转义，顺带 `obj["prop"]` → `obj.prop`。

---

## 二、六站同源：一次逆向，六次确认

**spa8–spa13 是同一套 NBA 数据站的六个混淆变体。** 混淆手法各不相同，剥掉混淆之后的业务代码**逐字一致**，Token 算法同源，只有那把 35 字符的 `key` 每站不同。这不是推测，是逐条核对出来的：

| 站点 | 混淆 | 混淆源码大小 | 还原后大小 | site key | Token 交叉验证 |
|---|---|---|---|---|---|
| spa8 | 无混淆（见该案例 README 的说明） | 3.4 KB | — | `qmqTHChqJqiiTDrsRoLQsyR2soxq6knoDPM` | 16/16 |
| spa9 | eval / packer | 2.4 KB | 2.4 KB | `NAhwcEVLEnRoJA7acv6eZGvXWjtijppyHXh` | 16/16 |
| spa10 | JJEncode | 23 KB | 2.1 KB | `VnzXHU3MQzuTXWuzzHXtxM7ifdYdrZVWqbv` | 16/16 |
| spa11 | AAEncode | 132 KB | 2.1 KB | `nCQ7ywzJVEqGTTxncPFJzXv8juDWwPMrZAr` | 16/16 |
| spa12 | JSFuck | 131 KB | 2.5 KB | `wUeziGfVEsfgHMpA8mVZcwwM8oNgsGHQFNu` | 16/16 |
| spa13 | JavaScript Obfuscator | 8.2 KB | 2.8 KB | `JD8wgBMgVjdQbBUVbMarpZMAadLD7yvfzVV` | 16/16 |

同源的三条实测证据（`tools/run_all.py` 每次运行都重算）：

1. **还原后的 `getToken()` 六站逐字一致**（spa13 因保留了混淆器改过的局部变量名，形不同义同）。
2. **球员名册六站逐字段全等**（16 人 × 5 字段），见 `evidence/run_all_twice.json` 的「六站横向对账」。
3. **同一个球员在六站的 token 互不相同** —— 因为 key 不同。若 key 也相同，同源就该表现为 token 也相同。

所以：**Token 算法只逆了一次（在 spa8/spa9 上），其余五站是「还原混淆 + 确认落到同一份代码」，不是各自独立逆了一遍。** 六个 `spider.py` 共享同一个 `pipeline.py`，本身就是这个结论的代码形态。

### Token 算法（六站共用）

```js
getToken(player) {
  let key = CryptoJS.enc.Utf8.parse(this.key);
  const { name, birthday, height, weight } = player;
  let base64Name = CryptoJS.enc.Base64.stringify(CryptoJS.enc.Utf8.parse(name));
  let encrypted = CryptoJS.DES.encrypt(
    `${base64Name}${birthday}${height}${weight}`, key,
    { mode: CryptoJS.mode.ECB, padding: CryptoJS.pad.Pkcs7 });
  return encrypted.toString();
}
```

Python 复刻见 `common.des_token()`。两处静默行为不照抄就对不上：

- **key 只取前 8 字节。** 站点 key 是 35 字符，DES 密钥是 64 bit；CryptoJS 只读 WordArray 的头两个 word，多余的 27 字节被静默丢弃。直接把 35 字节喂 pycryptodome 会抛 `ValueError` —— 那不是算法不对，是漏抄了这条截断。
- **`encrypted.toString()` 不带 `Salted__` 前缀。** 只有用口令派生密钥时 CryptoJS 才加盐；这里传的是 WordArray 密钥，输出就是密文的裸 Base64。

验收不靠「看起来对」：`tools/reftoken.js` 用**站点自己下发的 `crypto-js.min.js`** 跑一遍还原出来的 `getToken`，与 Python 输出逐字节比对，六站各 16/16。

---

## 三、antispider8：两处 debugger，四种绕法，五组对照实验

两处 `debugger` 的确切出处（逐字引自站点下发的 chunk）：

| 位置 | 文件 | 原文 |
|---|---|---|
| 定时循环 | `js/app.40192839.js` | `setInterval((function(){debugger;console.log("debugger")}),1e3)` |
| 接口处（列表） | `js/chunk-51935b2c.7a777070.js` | `onFetchData:function(){var t=this;debugger;this.loading=!0;…}` |
| 接口处（详情） | `js/chunk-27855899.741dfe15.js` | `onFetchData:function(){var t=this;debugger;this.loading=!0;…}` |

`antispider8/debugger_bypass.py` 跑五组受控实验，每组只改一个变量，判据是 8 秒窗口内的 **CDP `Debugger.paused` 事件次数** + **页面渲染出的电影卡片数**（「看着没卡」不算证据）：

| 实验 | 手段 | paused 次数 | 卡片 | 结论 |
|---|---|---|---|---|
| E0 | 不接调试器，headless 直接打开 | **0** | 10 | `debugger` 只对**已附着调试器**的引擎生效，对自动化浏览器本身是空操作 |
| E1 | 接 CDP `Debugger.enable`，不对抗 | **8** | 10 | 陷阱是真的：8 秒被打断 8 次（1 秒 1 次的定时器 + 接口那次） |
| E2 | route 中间人改写 js 响应，剥掉 debugger | **0** | 10 | 彻底；拦下 7 个 js 请求，去重后站点实有 **3** 条 debugger 语句 |
| E3 | CDP `Debugger.setSkipAllPauses(true)` | **0** | 10 | 彻底；等价于 DevTools 的「停用断点 / Never pause here」 |
| E4 | `addInitScript` 置换 `setInterval` | **1** | 10 | **只治定时那一个**，接口处那个照样打断 —— 部分手段 |

数据出自 `antispider8/evidence/debugger_bypass.json`（每次运行重算）。

三条踩过的坑，写在这里免得后人再踩：

- **`Debugger.setSkipAllPauses` 是会话状态，页面一导航就被重置。** 第一版在 `page.goto` 之前下这条指令，E3 记到 8 次 pause，看着像「这招没用」；改成导航之后再下一次，立刻降到 0。
- **剥 debugger 不能用 `replace("debugger","")`。** `app.js` 里 `debugger` 出现 2 次而语句只有 1 条 —— 多出来那次是 `console.log("debugger")` 里的字符串，动了就改变了页面行为，实验也就不干净了。`strip_debugger()` 用「前面不能是标识符字符或引号」的边界卡住。
- **「累计剥掉数」不等于「站点实有数」。** E2 累计剥掉 4 条，但站点实有 3 条：`chunk-51935b2c` 被请求了两次（`<link rel=prefetch>` 一次 + 路由加载一次），同一条被剥了两遍。所以脚本逐文件记账并同时报去重值 —— 只报累计数就会把「站点埋了 3 处」写成「4 处」。
- **接口处的 `debugger` 杀不掉 `setInterval`，反过来也一样。** 两处是不同机制，E4 证明了这一点：置换 `setInterval` 只干掉 1 个定时器，剩下 1 次 pause 就是 `onFetchData` 里那条。想一招通吃只能选 E2 或 E3。

### 但本阶段实际用的是第五种：根本不进浏览器

`antispider8/spider.py` 全程 `requests`，`debugger` 在它眼里连字符都不是。做法是把 token 算法从 chunk 里读出来搬到 Python：

```python
def make_token(*args):                      # 还原自 chunk-4136500c 的模块 "7d92"
    ts = str(round(time.time()))
    sha1_hex = hashlib.sha1(",".join([*args, ts]).encode()).hexdigest()
    return base64.b64encode(f"{sha1_hex},{ts}".encode()).decode()
```

实测（`python antispider8/spider.py`）：

```
[antispider8] 开抓（不启动浏览器）
  · 不带 token: HTTP 401
  · 列表: 104/104 条，11 次请求全部 200
  · 详情: 取前 5 部，全部 200
```

---

## 四、「跑两次都成功」怎么验

两类站点的合格判据**方向相反**，混为一谈就等于没验：

| 对象 | token 里有没有时间因子 | 合格判据 |
|---|---|---|
| spa8–spa13 | 无（纯函数） | 两轮 96 个 token **逐字节全等**。变了才是出问题 |
| antispider8 | 有（unix 秒） | 两轮 token **不同**、但两轮都拿到 200 与 104 条。不变反倒说明是抄了浏览器里的固定值 |

`python tools/run_all.py --gap 150` 一次跑完两轮并分别断言，结果落 `evidence/run_all_twice.json`。

---

## 五、跑起来

```bash
PY=/Users/deanlee/Documents/Claude/Projects/git_github/.venv/bin/python

# 单个案例
cd src/s09_js_obfuscation/spa12 && $PY spider.py

# antispider8：抓数据（不进浏览器）
cd src/s09_js_obfuscation/antispider8 && $PY spider.py

# antispider8：debugger 绕过五组对照实验（会启动 headless Chromium）
cd src/s09_js_obfuscation/antispider8 && $PY debugger_bypass.py

# 全部七个案例跑两轮 + 六站横向对账
cd src/s09_js_obfuscation && $PY tools/run_all.py --gap 150
```

### 额外依赖

本阶段在 venv 里额外装了一个包，**没有改仓库根目录的 `requirements.txt`**：

```bash
$PY -m pip install pycryptodome     # 3.23.0，用于 DES/ECB/PKCS7
```

`node` 用系统自带（实测 v26.5.0），不需要 npm 装任何东西 —— `tools/reftoken.js` 用的是 `vendor/crypto-js.min.js`，即站点自己下发的那一份原件。

## 六、抓取礼貌

`common.PoliteSession`：串行、每次请求间隔 1.0–1.6 秒（含抖动）、失败指数退避。全阶段最重的一次是 antispider8 的 11 次列表请求 + 5 次详情请求。scrape.center 是练习站，不压测。
