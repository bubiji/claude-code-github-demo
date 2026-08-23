> issue: #12 · 案例: spa13 · 来源: https://spa13.scrape.center

# spa13 —— JavaScript Obfuscator（obfuscator.io）

## 案例原描述（逐字引自 https://scrape.center/）

> NBA 球星数据网站，数据纯前端渲染，Token 经过加密处理，JavaScript 经过 JavaScript Obfuscator 混淆，适合 JavaScript 逆向分析。

---

## 识别：`_0x` 变量满天飞 + 一个大字符串数组

obfuscator.io 默认配置的三件套，看开头 100 个字节就全齐了：

```js
const _0x4afa=['\x31\x39\x39\x33\x2d\x30\x33\x2d\x31\x31','\x37\x39\x2e\x34\x4b\x47',…];
```

判据：正则 `_0x[0-9a-f]{4,}` 密集出现。

## 还原前（`evidence/before.js`，原样）

数组之后紧跟旋转 IIFE 与下标解码器：

```js
];(function(_0x35db0b,_0x4afab2){const _0x343162=function(_0x6f5802){while(--_0x6f5802){_0x35db0b['\x70\x75\x73\x68'](_0x35db0b['\x73\x68\x69\x66\x74']());}};_0x343162(++_0x4afab2);}(_0x4afa,0xed));const _0x3431=function(_0x35db0b,_0x4afab2){_0x35db0b=_0x35db0b-0x0;let _0x343162=_0x4afa[_0x35db0b];return _0x343162;};const _0x5e920f=_0x3431,players=[{'\x6e\x61\x6d\x65':'凯文\x2d杜兰特','\x69\x6d\x61\x67\x65':_0x5e920f('\x30\x78\x33\x30'),…
```

拆开看是四层：

| 层 | 干什么 |
|---|---|
| ① `const _0x4afa=[…]` | 63 个字面量全被抽进一个数组 |
| ② `(function(a,b){while(--b){a.push(a.shift())}}(_0x4afa,0xed))` | 把数组**旋转 0xed = 237 次** |
| ③ `const _0x3431=function(i){…return _0x4afa[i-0x0]}` | 下标解码器 |
| ④ `'\x6e\x61\x6d\x65'` / `_0x5e920f('\x30\x78\x33\x30')` | 剩下的标识符与下标全部十六进制转义 |

## 还原手段：这里那把「钩执行入口」的钥匙失灵了

**spa13 与前面四个案例的根本区别：它没有「最终 payload 字符串」。** obfuscator.io 的产物是直接可运行的代码，不存在「解码 → 交给 Function 执行」这一步，所以 `unwrap.js` 的探针钩不到任何东西。必须换成静态还原三步（实现在 `../tools/strarray.js`）：

1. **把「数组声明 + 旋转 IIFE + 解码器声明」这段前言原样丢进 Node vm 跑一遍。**
   旋转是**运行时行为** —— 静态读那个数组只会拿到错位 237 位的字符串。这一步必须真跑，读不能代替跑。
2. **从沙箱里取出解码器，把源码中每处 `别名('0x2f')` 换成它的真实返回值。**
   坑：解码器在每个函数作用域里会被再起一个局部别名，得递归收集。本例找到 4 个 —— `_0x3431 / _0x5e920f / _0x511d2e / _0x3c8dcd`，共替换 **69 处**。只认第一个名字会漏掉三分之二。
3. **扫字符串字面量去 `\xNN` / `\uNNNN` 转义**，顺手 `obj["prop"]` → `obj.prop`、`{"key":v}` → `{key:v}`，再做极简换行排版。
   用手写扫描器而不是全局正则：只有确定当前在字符串里，才敢动 `\xNN`。

还有一个静态定位的坑记在这里：**「找解码器」不能取第一个 `const _0x…=function(…){…}` 匹配** —— 旋转 IIFE 内部也声明了一个函数（`_0x343162`），它排在前面。真正的判据是**函数体里引用了字符串数组本身**（`_0x4afa`）。第一版按顺序取，取到了 IIFE 内部那个，前言被截断，vm 直接 `SyntaxError: Unexpected end of input`。

```
$ node ../tools/strarray.js evidence/before.js --out evidence/after.js
[strarray] 前言执行完成：数组 _0x4afa（63 项，已旋转），解码器 _0x3431
[strarray] 解码器别名 4 个: _0x3431, _0x5e920f, _0x511d2e, _0x3c8dcd
[strarray] 替换解码器调用 69 处
```

## 还原后（`evidence/after.js`，原样）

```js
const players=[
  {
    name:"凯文-杜兰特",
    image:"durant.png",
    birthday:"1988-09-29",
    height:"208cm",
    weight:"108.9KG"
  },
```

```js
new Vue({
  el:"#app",
  data:function(){
    return{
      players:players,
      key:"JD8wgBMgVjdQbBUVbMarpZMAadLD7yvfzVV"
    };
  },
  methods:{
    "getToken"(_0x6f5802){
      let _0x425481=CryptoJS.enc.Utf8.parse(this.key);
      const {
        name:_0x36356e,
        birthday:_0x3c0e63,
        height:_0x2bc6b2,
        weight:_0x4c82f0
      }=_0x6f5802;
      let _0x88eb16=CryptoJS.enc.Base64.stringify(CryptoJS.enc.Utf8.parse(_0x36356e)),
      _0x2c2072=CryptoJS.DES.encrypt(""+_0x88eb16+_0x3c0e63+_0x2bc6b2+_0x4c82f0,
      _0x425481,
      {
        mode:CryptoJS.mode.ECB,
        padding:CryptoJS.pad.Pkcs7
      });
      return _0x2c2072.toString();
    }
  }
});
```

**还原度的边界要说清楚**：局部变量名（`_0x425481`、`_0x88eb16`…）恢复不了——混淆器把它们**丢弃**了，不是编码了，原名没有存在任何地方。同理模板串 `` `${base64Name}…` `` 被改写成了 `""+a+b+c+d`。所以这一份与 spa8 的明文是**形不同、义同**，而 spa9–spa12 那四份是逐字同义。这是「还原」和「恢复原稿」的区别。

---

## Token 算法

同 spa8，见 `../README.md` 第二节。site key = `JD8wgBMgVjdQbBUVbMarpZMAadLD7yvfzVV`。

## 实测输出

```
$ python spider.py
[spa13] JavaScript Obfuscator（字符串数组 + 数组旋转 + 十六进制转义）
  ① GET https://spa13.scrape.center/ → evidence/index.html (1793 bytes)
  ① 混淆原件 ← https://spa13.scrape.center/js/main.js → evidence/before.js (8394 bytes)
  ② 还原 → evidence/after.js
     [strarray] 前言执行完成：数组 _0x4afa（63 项，已旋转），解码器 _0x3431
     [strarray] 解码器别名 4 个: _0x3431, _0x5e920f, _0x511d2e, _0x3c8dcd
     [strarray] 替换解码器调用 69 处
  ③ 取值：site key = 'JD8wgBMgVjdQbBUVbMarpZMAadLD7yvfzVV'，players = 16 人
  ④ Python DES ←→ 站点 crypto-js 逐字节比对：16/16 一致
  ⑤ 落盘 → data/spa13_players.json
```

## 产物

| 路径 | 内容 |
|---|---|
| `evidence/index.html` | 页面原样落盘 |
| `evidence/before.js` | `js/main.js` 的 obfuscator.io 原文 |
| `evidence/after.js` | 还原后源码（字符串已复原、排版已还原） |
| `evidence/report.json` | 五步流水线机读记录 |
| `data/spa13_players.json` | 16 名球员 + token |
