> issue: #7 · 案例: antispider4 · 来源: https://antispider4.scrape.center

# antispider4 · 字体文件反爬

## 案例原文（逐字引自 scrape.center）

> 对接字体文件反爬，显示的内容并不在 HTML 内，而是隐藏在字体文件，设置了文字映射表，适合用作字体反爬练习。

## 反爬是怎么判的（实证）

评分那一格在渲染后的 DOM 里长这样（**没有任何数字**）：

```html
<p class="score m-t-md m-b-n-sm">
  <span><i class="icon icon-789"></i></span>
  <span><i class="icon icon-981"></i></span>
  <span><i class="icon icon-504"></i></span>
</p>
```

实测 100 部电影，`p.score` 的 `innerText` 全为空：**100/100 条 HTML 文本里拿不到评分**。
数字是四层间接之后由浏览器画出来的：

### 第 1 层 · JS 映射表：明文数字 → icon 编号

站点 `/js/chunk-7c105922.6b8c0ae9.js` 模块 `e0eb`，逐字原文：

```js
e0eb:function(t,a,e){"use strict";e.d(a,"a",(function(){return s}));e("6b54");var n={0:272,1:643,2:180,3:437,4:378,5:504,6:203,7:102,8:281,9:789,".":981};function s(t){t=t.toString();for(var a=[],e=0;e<t.length;e++){var s=t.charAt(e).toString();a.push(n[s])}return a}}
```

即 `{0:272, 1:643, 2:180, 3:437, 4:378, 5:504, 6:203, 7:102, 8:281, 9:789, ".":981}`。

### 第 2 层 · 模板：icon 编号 → class 名

```js
t._l(t.getFontCharArray(a.score.toFixed(1)),(function(t,n){return e("span",{key:a.score+n},[e("i",{class:"icon icon-"+t})])}))
```

### 第 3 层 · CSS：class 名 → 一个 ASCII 密文字符

`/css/app.654ba59e.css` 里全部 11 条数字规则，逐字原文：

```css
.icon-981:before{content:"."}
.icon-272:before{content:"0"}
.icon-643:before{content:"1"}
.icon-180:before{content:"2"}
.icon-437:before{content:"3"}
.icon-378:before{content:"4"}
.icon-504:before{content:"5"}
.icon-203:before{content:"6"}
.icon-102:before{content:"7"}
.icon-281:before{content:"8"}
.icon-789:before{content:"9"}
```

### 第 4 层 · 自定义字体：码位 → 字形

```css
.icon{font-family:scrape!important;speak:none;font-style:normal;font-weight:400;font-variant:normal;text-transform:none;line-height:1;-webkit-font-smoothing:antialiased;-moz-osx-font-smoothing:grayscale}
```

```css
@font-face{font-family:scrape;src:url(../fonts/scrape.ef1612d4.eot);src:url(../fonts/scrape.ef1612d4.eot?#iefix) format("embedded-opentype"),url(../fonts/scrape.a5ca50ef.woff2) format("woff2"),url(../fonts/scrape.aab72ee4.woff) format("woff"),url(../fonts/scrape.4f15ef91.ttf) format("truetype"),url(../img/scrape.e62f364e.svg#uxfonteditor) format("svg")}
```

字体已下载存盘：`data/scrape.ttf`（80948 B，489 个码位，来源
`https://antispider4.scrape.center/fonts/scrape.4f15ef91.ttf`）。

## 密文字符 → 明文数字 完整对照表

`font_map.py` 把上面四层拼起来，并用 fontTools 读 cmap、把字形轮廓栅格化成点阵。

| icon class（HTML 里的密文） | CSS `content`（密文字符） | 码位 | 字体 cmap 里的字形名 | 字形实际画出的数字（明文） |
|---|---|---|---|---|
| `icon-272` | `0` | U+0030 | `zero` | **0** |
| `icon-643` | `1` | U+0031 | `one` | **1** |
| `icon-180` | `2` | U+0032 | `two` | **2** |
| `icon-437` | `3` | U+0033 | `three` | **3** |
| `icon-378` | `4` | U+0034 | `four` | **4** |
| `icon-504` | `5` | U+0035 | `five` | **5** |
| `icon-203` | `6` | U+0036 | `six` | **6** |
| `icon-102` | `7` | U+0037 | `seven` | **7** |
| `icon-281` | `8` | U+0038 | `eight` | **8** |
| `icon-789` | `9` | U+0039 | `nine` | **9** |
| `icon-981` | `.` | U+002E | `period` | **.** |

字形点阵存在 `data/font_glyphs.txt`，例如 `icon-281`（CSS content `"8"`，字形 `eight`）：

```
·····████████████·····
···████████████████···
·███████████████████··
██████·········██████·
█████············████·
████·············████·
████·············████·
████·············████·
████·············████·
█████···········█████·
·███████████████████··
··█████████████████···
··██████████████████··
·██████········██████·
█████···········█████·
████·············████·
████·············█████
████·············█████
████·············█████
█████············████·
██████·········██████·
·███████████████████··
···████████████████···
····█████████████·····
```

（点阵按字形自身包围盒等比拉伸，所以 `period` 那个小圆点会被拉成一整块黑，属正常现象。）

### 一句必须说清的实话

这份部署里的 `scrape.ttf` **字形本身没有被打乱**——cmap 把 U+0038 映到字形 `eight`，
而 `eight` 画出来的确实是 8。也就是说「隐藏在字体文件里的文字映射表」在本例中体现为
**「HTML 里只剩 class 名，明文靠 CSS `content` + 自定义字体渲染」**这一层，而不是
「字形与码位错位」那种更狠的玩法。这是把 ttf 拆开逐字形栅格化之后核对出来的结论，
不是想当然——`data/font_glyphs.txt` 里 11 个字形的点阵都可以肉眼复核。

对纯 HTTP 爬虫来说难度不变：不下载 CSS、不认这套 icon 编号，就一个数字也拿不到。

## 校验（`data/antispider4_movies.json`）

三重交叉验证，全部实跑：

1. 用 `getComputedStyle(i, '::before').content` 读**浏览器真正解析出来的** content
   （不是脚本正则猜的），例如 `霸王别姬` → `['"9"', '"."', '"5"']`。
2. 用对照表把 `icon_classes` 解码成明文评分。
3. 打 `/api/movie/?limit=10&offset=N` 拿明文 `score` 当 ground truth。

```
还原 100 条，与 API 明文一致 100 条
HTML 文本里评分为空（即数字确实不在 HTML 内）的条数：100/100
```

## 跑法

```bash
cd src/s04_antispider_basic/antispider4
../../../.venv/bin/python font_map.py   # 建映射表（会下载 ttf）
../../../.venv/bin/python spider.py     # 渲染 + 解码 + 与 API 对账
```

依赖（**都不在仓库根 requirements.txt 里**，装进 venv）：

```bash
../../../.venv/bin/pip install fonttools playwright
../../../.venv/bin/playwright install chromium
```

- `fonttools` 用于读 ttf 的 cmap / glyf 轮廓（本次装的是 4.63.0）。
- `playwright` 用于渲染 SPA 并读 computed style。

## 产出

| 文件 | 内容 |
|---|---|
| `data/scrape.ttf` | 字体原件（80948 B） |
| `data/font_cmap.json` | 489 个码位的 cmap 全表（码位 → 字符 → 字形名）+ glyphOrder |
| `data/font_glyphs.txt` | 11 个数字字形的 ASCII 点阵，肉眼可核对 |
| `data/cipher_map.json` | icon 编号 / 密文字符 / 码位 / 字形名 / 明文数字 + 解码表 |
| `data/antispider4_movies.json` | 10 页共 100 条：密文 class、computed content、解码值、API 明文、是否一致 |

## 练习伦理

每页 1.2 秒间隔，封面图 abort；只抓 10 页 100 条。
