> issue: #12 · 案例: spa8 · 来源: https://spa8.scrape.center

# spa8 —— JavaScript 代码一行混入 HTML

## 案例原描述（逐字引自 https://scrape.center/）

> NBA 球星数据网站，数据纯前端渲染，Token 经过加密处理，JavaScript 代码一行混入 HTML 代码，防止直接调试，适合 JavaScript 逆向分析。

---

## ⚠️ 实测与原描述不符，先说清楚

原描述说「JavaScript 代码**一行**混入 HTML 代码」。**2026-08-23 实测，站点当前下发的内联 `<script>` 是格式化好的多行明文，不是压成一行，也没有任何混淆。**

证据（`curl` 原样落盘，见 `evidence/index.html` 与 `evidence/before.js`）：

```
$ curl -s https://spa8.scrape.center/ | wc -c
    5469
$ awk '{print length($0)}' evidence/index.html | sort -rn | head -1
72          # 最长的一行只有 72 字符 —— 不存在「一行塞进去」的长行
```

`evidence/before.js` 开头（原样）：

```js
const players = [
  {
    name: "凯文-杜兰特",
    image: "durant.png",
    birthday: "1988-09-29",
    height: "208cm",
    weight: "108.9KG",
  },
```

所以本案例**没有混淆可还原**，`evidence/after.js` 与 `evidence/before.js` 内容相同，`spider.py` 的还原步声明为 `obf="none"`。这一条如实记录，不假装还原了什么。

同一站群里，真正把逻辑压成一行 + 混淆的是 spa9（eval/packer），描述里「防止直接调试」这层意图在 spa9–spa13 才真正兑现。

**这个案例的教学价值不在混淆，在于它是六站里唯一的「明文对照组」** —— 后面五个站还原出来的代码，正确与否就拿它当标尺。

---

## 逆向结论

数据不走接口，16 名球员**硬编码在页面内联脚本里**；Token 是 tooltip 的显示内容，前端现算：

```js
new Vue({
  el: "#app",
  data: function () {
    return { players, key: "qmqTHChqJqiiTDrsRoLQsyR2soxq6knoDPM" };
  },
  methods: {
    getToken(player) {
      let key = CryptoJS.enc.Utf8.parse(this.key);
      const { name, birthday, height, weight } = player;
      let base64Name = CryptoJS.enc.Base64.stringify(
        CryptoJS.enc.Utf8.parse(name)
      );
      let encrypted = CryptoJS.DES.encrypt(
        `${base64Name}${birthday}${height}${weight}`,
        key,
        { mode: CryptoJS.mode.ECB, padding: CryptoJS.pad.Pkcs7 }
      );
      return encrypted.toString();
    },
  },
});
```

（以上逐字引自 `evidence/before.js`。）

Python 复刻在 `../common.py::des_token()`，两处静默行为见那里的注释（key 只取前 8 字节、输出无 `Salted__` 前缀）。

**Token 不含时间戳、不含随机数，是纯函数** —— 所以「隔一段时间跑两次」的正确预期是两次输出**完全相同**，见 `../evidence/run_all_twice.json`。

---

## 踩坑记录：一个能骗过交叉验证的编码坑

第一次跑完，Python 与 Node 参照实现的 token **16/16 一致**，看着完美。但打开 `data/spa8_players.json` 一看：

```json
"name": "å¯æ-æå°ç¹"
```

原因：spa8 的响应头是 `Content-Type: text/html`，**不带 charset**（页面里写的是 `<meta charset="UTF-8">`）。requests 按 RFC 2616 把 `text/*` 默认当 ISO-8859-1，`r.text` 就成了乱码。

阴险的地方是**它能骗过 token 交叉验证**：Python 拿乱码名算 DES，Node 参照实现也拿到同一份乱码名，两边算出来一模一样，绿灯照亮。

> **跨实现对照能证明「复刻对了算法」，证明不了「喂进去的输入是对的」。**

补了两道：

1. `common.PoliteSession._fix_encoding()` —— 响应头没 charset 就按 utf-8 解。
2. `tools/run_all.py::cross_site_check()` —— **六站横向对账**：六个站托管的是同一份名册，16 人 × 5 字段必须逐字段全等。纵向比查不出输入错，横向一比就露馅。

---

## 实测输出

```
$ python spider.py
[spa8] 无混淆（案例原描述为「JavaScript 代码一行混入 HTML 代码」，实测当前下发为格式化明文，见 README）
  ① GET https://spa8.scrape.center/ → evidence/index.html (5469 bytes)
  ① 混淆原件 ← https://spa8.scrape.center/  （HTML 内联 <script>） → evidence/before.js (3374 bytes)
  ② 还原 → evidence/after.js (3374 bytes)
     （无需还原：站点当前下发的即为未混淆源码，见本案例 README）
  ③ 取值：site key = 'qmqTHChqJqiiTDrsRoLQsyR2soxq6knoDPM'，players = 16 人
  ④ Python DES ←→ 站点 crypto-js 逐字节比对：16/16 一致
  ⑤ 落盘 → data/spa8_players.json (4639 bytes)
```

## 产物

| 路径 | 内容 |
|---|---|
| `evidence/index.html` | `https://spa8.scrape.center/` 原样落盘 |
| `evidence/before.js` | 页面内联 `<script>` 原文（本例即明文） |
| `evidence/after.js` | 还原后代码（本例与 before 相同） |
| `evidence/report.json` | 五步流水线的机读记录 |
| `data/spa8_players.json` | 16 名球员 + token |
