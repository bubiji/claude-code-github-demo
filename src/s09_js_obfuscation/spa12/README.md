> issue: #12 · 案例: spa12 · 来源: https://spa12.scrape.center

# spa12 —— JSFuck

## 案例原描述（逐字引自 https://scrape.center/）

> NBA 球星数据网站，数据纯前端渲染，Token 经过加密处理，JavaScript 经过 JSFuck 混淆，适合 JavaScript 逆向分析。

---

## 识别：整个文件只有六个字符

JSFuck 只用 `[ ] ( ) ! +` 六个字符表达任意 JS。识别可以做到**零歧义**：

```
$ python -c "s=open('evidence/before.js').read(); print(len(s), sorted(set(s)))"
134129 ['!', '(', ')', '+', '[', ']']
```

字符集恰好等于 `{! ( ) + [ ]}` —— 没有第二种混淆长这样。

## 还原前（`evidence/before.js` 前 220 字节，原样）

```js
[][(![]+[])[+[]]+(![]+[])[!+[]+!+[]]+(![]+[])[+!+[]]+(!![]+[])[+[]]][([][(![]+[])[+[]]+(![]+[])[!+[]+!+[]]+(![]+[])[+!+[]]+(!![]+[])[+[]]]+[])[!+[]+!+[]+!+[]]+(!![]+[][(![]+[])[+[]]+(![]+[])[!+[]+!+[]]+(![]+[])[+!+[]]+(!
```

结尾（原样）：

```js
…[]+!+[]]+(!![]+[][(![]+[])[+[]]+(![]+[])[!+[]+!+[]]+(![]+[])[+!+[]]+(!![]+[])[+[]]])[+!+[]+[+[]]]+(!![]+[])[+!+[]]]()[+!+[]+[!+[]+!+[]]])())
```

开头那一段其实是可以直读的，只要知道 JSFuck 的两条基本套路：

- `![]` → `false`，`!![]` → `true`，`[]+[]` → `""`，`+[]` → `0`，`+!+[]` → `1`
- 所以 `(![]+[])[+[]]` = `"false"[0]` = `"f"`，往后 `"a" "l" "s" "e"` 逐个取出来拼成 `"filter"`

`[]["filter"]["constructor"]` —— 又是 `Function.prototype.constructor`。

## 还原手段：还是同一把钥匙

`../tools/unwrap.js` 一字不改：

```
$ node ../tools/unwrap.js evidence/before.js --out evidence/after.js
[unwrap] 捕获 4 段代码，入口顺序: ["Function/11B","Function/13B","Function/6291B","eval/2297B"]
```

这次捕获了 4 段，说明 JSFuck 的执行链比 JJEncode 多两跳（先用 `Function` 拼出几个短工具串，再拼出 6291 字节的包装层，最后走 `eval` 执行 2297 字节的真源码）。**「取最后一段」这条规则在这里同样成立** —— 4 段里最长的是 6291 那个包装层，取最长就又取错了。

体积从 **134129 → 2297 字节**（压缩比约 58:1）。

## 还原后（`evidence/after.js` 结尾，原样）

```js
… new Vue({   el: '#app', data: function () {     return {players, key: 'wUeziGfVEsfgHMpA8mVZcwwM8oNgsGHQFNu'}   }, methods: {     getToken(player) {       let key = CryptoJS.enc.Utf8.parse(this.key);       const {name, birthday, height, weight} = player;       let base64Name = CryptoJS.enc.Base64.stringify(CryptoJS.enc.Utf8.parse(name));       let encrypted = CryptoJS.DES.encrypt(`${base64Name}${birthday}${height}${weight}`, key, {         mode: CryptoJS.mode.ECB,         padding: CryptoJS.pad.Pkcs7       });       return encrypted.toString()     }   } })
```

注意这里连**原始缩进的空格**都保留下来了（JSFuck 编码的是逐字节的原文，包括空白），所以还原度比 spa9/spa10/spa11 还高一点 —— 那三个还原出来的是被压缩过的版本。

---

## Token 算法

同 spa8，见 `../README.md` 第二节。site key = `wUeziGfVEsfgHMpA8mVZcwwM8oNgsGHQFNu`。

## 实测输出

```
$ python spider.py
[spa12] JSFuck
  ① GET https://spa12.scrape.center/ → evidence/index.html (1793 bytes)
  ① 混淆原件 ← https://spa12.scrape.center/js/main.js → evidence/before.js (134129 bytes)
  ② 还原 → evidence/after.js
     [unwrap] 捕获 4 段代码，入口顺序: ["Function/11B","Function/13B","Function/6291B","eval/2297B"]
  ③ 取值：site key = 'wUeziGfVEsfgHMpA8mVZcwwM8oNgsGHQFNu'，players = 16 人
  ④ Python DES ←→ 站点 crypto-js 逐字节比对：16/16 一致
  ⑤ 落盘 → data/spa12_players.json
```

## 产物

| 路径 | 内容 |
|---|---|
| `evidence/index.html` | 页面原样落盘 |
| `evidence/before.js` | `js/main.js` 的 JSFuck 原文（131 KB，六个字符） |
| `evidence/after.js` | 还原后源码（连缩进都保留） |
| `evidence/report.json` | 五步流水线机读记录 |
| `data/spa12_players.json` | 16 名球员 + token |
