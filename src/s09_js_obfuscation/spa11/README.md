> issue: #12 · 案例: spa11 · 来源: https://spa11.scrape.center

# spa11 —— AAEncode

## 案例原描述（逐字引自 https://scrape.center/）

> NBA 球星数据网站，数据纯前端渲染，Token 经过加密处理，JavaScript 经过 AAEncode 混淆，适合 JavaScript 逆向分析。

---

## 识别：日文颜文字，第一行就是 `ﾟωﾟﾉ= /｀ｍ´）ﾉ ~┻━┻`

AAEncode（同为 Yosuke Hasegawa 出品，与 JJEncode 同源）把代码编成一串日文颜文字。开头那句「掀桌」`~┻━┻` 是它的固定签名。

判据：源码含 `ﾟωﾟﾉ` 或 `(ﾟДﾟ)`。

## 还原前（`evidence/before.js` 前 300 字节，原样）

```js
ﾟωﾟﾉ= /｀ｍ´）ﾉ ~┻━┻   //*´∇｀*/ ['_']; o=(ﾟｰﾟ)  =_=3; c=(ﾟΘﾟ) =(ﾟｰﾟ)-(ﾟｰﾟ); (ﾟДﾟ) =(ﾟΘﾟ)= (o^_^o)/ (o^_^o);(ﾟДﾟ)={ﾟΘﾟ: '_' ,ﾟωﾟﾉ : ((ﾟωﾟﾉ==3) +'_') [ﾟΘﾟ] ,ﾟｰﾟﾉ :(ﾟωﾟﾉ+ '_')[o^_^o -(ﾟΘﾟ)] ,ﾟДﾟﾉ:((ﾟｰﾟ==3) +'_')[ﾟｰﾟ] }; (ﾟДﾟ) [ﾟΘﾟ] =((ﾟωﾟﾉ==3) +'_') [c^_^o];(ﾟДﾟ) ['c'] = ((ﾟДﾟ)+'_') [ (ﾟｰﾟ)+(ﾟｰﾟ)-(ﾟΘﾟ) ];
```

结尾（原样）：

```js
… (ﾟДﾟ)[ﾟεﾟ]+((ﾟｰﾟ) + (ﾟΘﾟ))+ (ﾟΘﾟ)+ (ﾟДﾟ)[ﾟεﾟ]+(ﾟΘﾟ)+ ((o^_^o) - (ﾟΘﾟ))+ (ﾟДﾟ)[ﾟoﾟ]) (ﾟΘﾟ)) ('_');
```

## 还原手段：和 JJEncode 一模一样的那把钥匙

AAEncode 与 JJEncode 只是「字符集」不同 —— 一个用 `$_`，一个用颜文字 —— **机制完全相同**：拼出源码字符串，交给 `Function` 构造器执行。所以 `../tools/unwrap.js` 那一处 `Function.prototype.constructor` 探针一字不改就能用：

```
$ node ../tools/unwrap.js evidence/before.js --out evidence/after.js
[unwrap] 捕获 2 段代码，入口顺序: ["Function/7095B","Function/1904B"]
[unwrap] payload 执行在 Node 里抛错（预期内，缺 Vue/CryptoJS）: Vue is not defined
```

**这就是本阶段最值钱的一条结论的实证**：认出是哪种混淆，主要价值在于知道「不用逐字读」；真正干活的判断是「它最终把字符串交给谁执行」。这个问题在 JJEncode / AAEncode / JSFuck 上是同一个答案。

体积从 **134991 → 1904 字节**（压缩比约 71:1，颜文字很占地方）。

## 还原后（`evidence/after.js` 结尾，原样）

```js
new Vue({el:'#app',data:function(){return{players,key:'nCQ7ywzJVEqGTTxncPFJzXv8juDWwPMrZAr'}},methods:{getToken(player){let key=CryptoJS.enc.Utf8.parse(this.key);const{name,birthday,height,weight}=player;let base64Name=CryptoJS.enc.Base64.stringify(CryptoJS.enc.Utf8.parse(name));let encrypted=CryptoJS.DES.encrypt(`${base64Name}${birthday}${height}${weight}`,key,{mode:CryptoJS.mode.ECB,padding:CryptoJS.pad.Pkcs7});return encrypted.toString()}}})
```

与 spa10 还原后的代码**逐字相同**，只有 key 从 `VnzXHU…` 变成 `nCQ7yw…`。

---

## Token 算法

同 spa8，见 `../README.md` 第二节。site key = `nCQ7ywzJVEqGTTxncPFJzXv8juDWwPMrZAr`。

## 实测输出

```
$ python spider.py
[spa11] AAEncode
  ① GET https://spa11.scrape.center/ → evidence/index.html (1793 bytes)
  ① 混淆原件 ← https://spa11.scrape.center/js/main.js → evidence/before.js (134991 bytes)
  ② 还原 → evidence/after.js
     [unwrap] 捕获 2 段代码，入口顺序: ["Function/7095B","Function/1904B"]
     [unwrap] payload 执行在 Node 里抛错（预期内，缺 Vue/CryptoJS）: Vue is not defined
  ③ 取值：site key = 'nCQ7ywzJVEqGTTxncPFJzXv8juDWwPMrZAr'，players = 16 人
  ④ Python DES ←→ 站点 crypto-js 逐字节比对：16/16 一致
  ⑤ 落盘 → data/spa11_players.json
```

## 产物

| 路径 | 内容 |
|---|---|
| `evidence/index.html` | 页面原样落盘 |
| `evidence/before.js` | `js/main.js` 的 AAEncode 原文（132 KB 颜文字） |
| `evidence/after.js` | 还原后源码 |
| `evidence/report.json` | 五步流水线机读记录 |
| `data/spa11_players.json` | 16 名球员 + token |
