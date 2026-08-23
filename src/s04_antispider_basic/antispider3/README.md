> issue: #7 · 案例: antispider3 · 来源: https://antispider3.scrape.center

# antispider3 · 文字偏移反爬

## 案例原文（逐字引自 scrape.center）

> 对接文字偏移反爬，所见顺序并不一定和源码顺序一致，适合用作文字偏移反爬练习。

## 反爬是怎么判的（实证）

不是「判」，是**渲染时故意打乱源码顺序**，靠 CSS 绝对定位把视觉顺序拉回来。
机制在站点自己的 `/js/chunk-cd85151c.539dc1c6.js` 里，逐字原文（压缩代码）：

```js
getTextChar:function(t,a){if(!t)return[];for(var e=[],n=0;n<t.length;n++)e.push({content:t.charAt(n),offset:a*n});return Math.random()<.8&&e.sort((function(){return Math.random()-.5})),e}
```

展开：

```js
getTextChar: function (name, charWidth) {          // 模板里调用的是 getTextChar(a.name, 16)
    if (!name) return [];
    var arr = [];
    for (var n = 0; n < name.length; n++)
        arr.push({content: name.charAt(n), offset: charWidth * n});   // offset 记住真实下标
    if (Math.random() < .8)                                            // 80% 概率洗牌
        arr.sort(function () { return Math.random() - .5 });
    return arr;
}
```

模板把每个字渲染成一个 span，`left` 就是上面那个 `offset`：

```js
e("span",{key:a.id+s,staticClass:"char",style:{left:n.offset+"px"}},[t._v(t._s(n.content))])
```

配套 CSS（`/css/chunk-cd85151c.019ee97e.css`，逐字原文）：

```css
.item .bottom .name[data-v-7f1a77ef]{display:inline-block;position:relative;height:5px;text-overflow:ellipsis;white-space:nowrap}
.item .bottom .name .char[data-v-7f1a77ef]{display:inline-block;position:absolute}
```

- 父元素 `.name` 是 `position:relative`，每个 `.char` 是 `position:absolute`。
- 于是每个字**脱离文档流**，横向位置只由 `left` 决定，跟它在 DOM 里排第几完全无关。
- 所以「所见顺序」= 按 `left` 升序；「源码顺序」= DOM 里 span 的先后。

两个附带细节（都在同一段模板里）：

```js
a.name.search(/[0-9a-zA-Z]/g)>=0 ? e("h3",{staticClass:"name whole"},[t._v(t._s(a.name))]) : e("h3",{staticClass:"m-b-sm name"}, ...)
```

- 书名里只要含 `0-9a-zA-Z`，就走 `h3.name.whole` 分支**原样输出**，不做偏移
  （例如 `Wonder`）。只有纯中文/符号的书名才会被打散。
- 洗牌是 `Math.random() < .8`，所以约 20% 的书名源码顺序**碰巧就是正确顺序**。
  实测 36 条偏移书名里有 29 条真被打乱（另 7 条 perm 恰为恒等）。

## 映射关系（`data/antispider3_offset_map.json`）

**真实下标 = round(left / 16)**，16 就是模板写死的 `getTextChar(a.name, 16)`。
文件里对每本书都存了四样东西：`source_order`（源码顺序串）、`offsets_px`（每个 span 的
left）、`source_index_to_true_index`（置换）、`rendered_order`（按 left 重排后的所见顺序）。

两条实例：

| 源码顺序 | 各 span 的 left(px) | 源码第 i 位 → 真实第几位 | 所见顺序 | API 明文 |
|---|---|---|---|---|
| `风清白家` | 48, 0, 16, 32 | [3, 0, 1, 2] | `清白家风` | 清白家风 |
| `结 下（宠篇上终册）法妃的老` | 112,80,176,144,48,128,160,96,192,208,0,64,32,16 | [7,5,11,9,3,8,10,6,12,13,0,4,2,1] | `法老的宠妃 终结篇（上下册）` | 法老的宠妃 终结篇（上下册） |

一个坑：空格那一位的 span 内容被模板的换行缩进包着，`trim()` 之后是空串。
脚本里判定「trim 后为空 = 这一位本来就是空格」才能把 `法老的宠妃 终结篇` 中间那个空格还原
出来（不处理的话 36 条里会有 3 条对不上）。

## 校验

用 `/api/book/?limit=18&offset=N` 返回的明文 `name` 当 ground truth，逐字比对：

```
偏移书名 36 条，其中源码顺序被打乱 29 条
按 left 重排后与 API 明文一致：36/36
```

## 跑法

```bash
cd src/s04_antispider_basic/antispider3
../../../.venv/bin/python spider.py
```

依赖：`playwright`（**不在仓库根 requirements.txt 里**，装进 venv）

```bash
../../../.venv/bin/pip install playwright
../../../.venv/bin/playwright install chromium
```

必须用浏览器：偏移是客户端 JS 现算的，服务端只给空壳 SPA，纯 HTTP 拿不到 span。

## 产出

| 文件 | 内容 |
|---|---|
| `data/antispider3_offset_map.json` | 3 页 36 条偏移书名的完整映射（源码顺序 / left / 置换 / 所见顺序） |
| `data/antispider3_books.json` | 3 页 54 本书的还原书名 + API 明文对照 |

## 练习伦理

每页 1 秒间隔，封面图请求直接 abort（省对方带宽），只抓 3 页 54 本，不遍历全部 9040 本。
