> issue: #12 · 案例: spa10 · 来源: https://spa10.scrape.center

# spa10 —— JJEncode

## 案例原描述（逐字引自 https://scrape.center/）

> NBA 球星数据网站，数据纯前端渲染，Token 经过加密处理，JavaScript 经过 JJEncode 混淆，适合 JavaScript 逆向分析。

---

## 识别：满屏 `$` 和下划线，开头永远是 `$=~[];$={`

JJEncode（Yosuke Hasegawa 出品）把整段代码编码成只由 `$ _ + " \ ( ) [ ] { } , : ; ~ ! ^ .` 组成的符号串。前 20 个字节就能认出来：

```
$=~[];$={___:++$,$$$$:(![]+"")[$],__$:++$,…
```

判据：`^\$=~\[\];\$=\{`。从 spa11 起页面不再内联脚本，改成外链 `js/main.js`。

## 还原前（`evidence/before.js` 前 240 字节，原样）

```js
$=~[];$={___:++$,$$$$:(![]+"")[$],__$:++$,$_$_:(![]+"")[$],_$_:++$,$_$$:({}+"")[$],$$_$:($[$]+"")[$],_$$:++$,$$$_:(!""+"")[$],$__:++$,$_$:++$,$$__:({}+"")[$],$$_:++$,$$$:++$,$___:++$,$__$:++$};$.$_=($.$_=$+"")[$.$_$]+($._$=$.$_[$.__$])+($.$
```

结尾（原样）：

```js
…+$.__+$.$$$_+$.$$_$+"."+$.__+$._$+"\\"+$.__$+$._$_+$._$$+$.__+"\\"+$.__$+$.$$_+$._$_+"\\"+$.__$+$.$_$+$.__$+"\\"+$.__$+$.$_$+$.$$_+"\\"+$.__$+$.$__+$.$$$+"()}}})\\"+$.__$+$._$_+"\"")())();
```

## 还原手段：钩 `Function.prototype.constructor`

**不要试图读懂那堆 `$`。** JJEncode 并不隐藏语义，它只是把源码字符串用符号运算重新拼出来，最后必须交给一个代码执行入口。看它的倒数第二段就知道入口在哪：

```js
$.$=($.___)[$.$_][$.$_];      // 展开就是 (1)["constructor"]["constructor"] —— 即 Function
$.$($.$($.$$+"\""+ … +"\"")())();
```

`(1).constructor` 是 `Number`，`Number.constructor` 顺着 `__proto__` 落到 **`Function.prototype.constructor`**。所以把这个属性换成一个「先记账、再放行」的探针，源码就在执行前落到手里：

```js
Object.defineProperty(Function.prototype, 'constructor', { value: FunctionProbe, ... });
```

实现在 `../tools/unwrap.js`。同一把钥匙也开 AAEncode(spa11) 和 JSFuck(spa12) 的锁 —— 详见阶段 README 第一节。

```
$ node ../tools/unwrap.js evidence/before.js --out evidence/after.js
[unwrap] 捕获 2 段代码，入口顺序: ["Function/4253B","Function/1904B"]
[unwrap] payload 执行在 Node 里抛错（预期内，缺 Vue/CryptoJS）: Vue is not defined
```

两点值得记：

- **捕获两次是 JJEncode 的固有结构**：`$.$($.$(<拼出来的串>)())()` —— 内层 `Function("return \"…\"")()` 先把源码字符串生成出来（4253 字节，全是 `\156` 这类八进制转义），外层再 `Function(<源码>)()` 执行它（1904 字节）。所以**要按执行顺序取最后一段，不能按长度取最长的**（第一版按长度挑，挑出来的是带转义的包装层）。
- **报错 `Vue is not defined` 是预期内的刹车**：payload 在 Node 里没有 Vue/CryptoJS，必然抛错；抛错时源码早已被记账。

## 还原后（`evidence/after.js` 结尾，原样）

```js
new Vue({el:'#app',data:function(){return{players,key:'VnzXHU3MQzuTXWuzzHXtxM7ifdYdrZVWqbv'}},methods:{getToken(player){let key=CryptoJS.enc.Utf8.parse(this.key);const{name,birthday,height,weight}=player;let base64Name=CryptoJS.enc.Base64.stringify(CryptoJS.enc.Utf8.parse(name));let encrypted=CryptoJS.DES.encrypt(`${base64Name}${birthday}${height}${weight}`,key,{mode:CryptoJS.mode.ECB,padding:CryptoJS.pad.Pkcs7});return encrypted.toString()}}})
```

体积从 **23324 → 1904 字节**；与 spa8/spa9 逐字同义，只有 key 不同。

---

## Token 算法

同 spa8，见 `../README.md` 第二节。site key = `VnzXHU3MQzuTXWuzzHXtxM7ifdYdrZVWqbv`。

## 实测输出

```
$ python spider.py
[spa10] JJEncode
  ① GET https://spa10.scrape.center/ → evidence/index.html (1793 bytes)
  ① 混淆原件 ← https://spa10.scrape.center/js/main.js → evidence/before.js (23324 bytes)
  ② 还原 → evidence/after.js
     [unwrap] 捕获 2 段代码，入口顺序: ["Function/4253B","Function/1904B"]
     [unwrap] payload 执行在 Node 里抛错（预期内，缺 Vue/CryptoJS）: Vue is not defined
  ③ 取值：site key = 'VnzXHU3MQzuTXWuzzHXtxM7ifdYdrZVWqbv'，players = 16 人
  ④ Python DES ←→ 站点 crypto-js 逐字节比对：16/16 一致
  ⑤ 落盘 → data/spa10_players.json
```

## 产物

| 路径 | 内容 |
|---|---|
| `evidence/index.html` | 页面原样落盘 |
| `evidence/before.js` | `js/main.js` 的 JJEncode 原文 |
| `evidence/after.js` | 还原后源码 |
| `evidence/report.json` | 五步流水线机读记录 |
| `data/spa10_players.json` | 16 名球员 + token |
