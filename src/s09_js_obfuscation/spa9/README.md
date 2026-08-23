> issue: #12 · 案例: spa9 · 来源: https://spa9.scrape.center

# spa9 —— eval 混淆（Dean Edwards packer）

## 案例原描述（逐字引自 https://scrape.center/）

> NBA 球星数据网站，数据纯前端渲染，Token 经过加密处理，JavaScript 经过 eval 混淆，适合 JavaScript 逆向分析。

---

## 识别：开头那串 `p,a,c,k,e,r` 是签名

Dean Edwards packer 的产物有一个几乎不会变的外壳：

```
eval(function(p,a,c,k,e,r){ … }('<模板>', <a>, <c>, '<字典>'.split('|'), 0, {}))
```

正则 `function\(p,a,c,k,e,r\)` 一抓一个准。**识别成本几乎为零，这是最容易认的一种混淆。**

## 还原前（`evidence/before.js` 前 340 字节，原样）

```js
eval(function(p,a,c,k,e,r){e=function(c){return(c<62?'':e(parseInt(c/62)))+((c=c%62)>35?String.fromCharCode(c+29):c.toString(36))};if('0'.replace(0,e)==0){while(c--)r[e(c)]=k[c];k=[function(e){return r[e]||e}];e=function(){return'[0-9a-zA-D]'};c=1};while(c--)if(k[c])p=p.replace(new RegExp('\\b'+e(c)+'\\b','g'),k[c]);return p}('g h=[{0:\'凯文-杜兰特\',4:\'durant.5\',1:\'b-09-c\',2:\'i\',3:\'108.j\'},…
```

看得懂它在干什么：模板串里 `0`/`1`/`2`/`g`/`h` 这些短标记，会被字典 `'name|birthday|height|weight|image|png|CryptoJS|…'.split('|')` 里的词逐个替换回去。数据本身（球员中文名）压根没加密，摆在那里。

## 还原手段：钩 `eval`，不解析

packer 最后必然把还原好的源码交给 `eval`。所以不用去实现 base62 解码、不用管字典替换 —— **钩住 `eval`，把它的入参记下来就完事**：

```js
const realEval = eval;
globalThis.eval = function (code) { record('eval', code); return realEval(code); };
```

实现在 `../tools/unwrap.js`（同一个文件也对付 JJEncode / AAEncode / JSFuck，见阶段 README 第一节）。

```
$ node ../tools/unwrap.js evidence/before.js --out evidence/after.js
[unwrap] 捕获 1 段代码，入口顺序: ["eval/2091B"]
```

## 还原后（`evidence/after.js` 开头，原样）

```js
const players=[{name:'凯文-杜兰特',image:'durant.png',birthday:'1988-09-29',height:'208cm',weight:'108.9KG'},{name:'勒布朗-詹姆斯',image:'james.png',birthday:'1984-12-30',height:'206cm',weight:'113.4KG'},…
```

结尾（原样）：

```js
new Vue({el:'#app',data:function(){return{players,key:'NAhwcEVLEnRoJA7acv6eZGvXWjtijppyHXh'}},methods:{getToken(player){let key=CryptoJS.enc.Utf8.parse(this.key);const{name,birthday,height,weight}=player;let base64Name=CryptoJS.enc.Base64.stringify(CryptoJS.enc.Utf8.parse(name));let encrypted=CryptoJS.DES.encrypt(`${base64Name}${birthday}${height}${weight}`,key,{mode:CryptoJS.mode.ECB,padding:CryptoJS.pad.Pkcs7});return encrypted.toString()}}})
```

**与 spa8 的明文逐字同义**，只有 `key` 不同 —— 这是「六站同源」的第一处确认。

---

## Token 算法

同 spa8，见 `../README.md` 第二节与 `../common.py::des_token()`。
site key = `NAhwcEVLEnRoJA7acv6eZGvXWjtijppyHXh`。

Token 是纯函数（无时间戳、无随机数），两次运行输出应当逐字节相同。

## 实测输出

```
$ python spider.py
[spa9] eval 混淆（Dean Edwards packer，p,a,c,k,e,r）
  ① GET https://spa9.scrape.center/ → evidence/index.html (3876 bytes)
  ① 混淆原件 ← https://spa9.scrape.center/  （HTML 内联 <script>） → evidence/before.js
  ② 还原 → evidence/after.js
     [unwrap] 捕获 1 段代码，入口顺序: ["eval/2091B"]
  ③ 取值：site key = 'NAhwcEVLEnRoJA7acv6eZGvXWjtijppyHXh'，players = 16 人
  ④ Python DES ←→ 站点 crypto-js 逐字节比对：16/16 一致
  ⑤ 落盘 → data/spa9_players.json
```

## 产物

| 路径 | 内容 |
|---|---|
| `evidence/index.html` | 页面原样落盘 |
| `evidence/before.js` | packer 混淆原文（页面内联 `<script>`） |
| `evidence/after.js` | 钩 `eval` 捕获到的还原源码 |
| `evidence/report.json` | 五步流水线机读记录 |
| `data/spa9_players.json` | 16 名球员 + token |
