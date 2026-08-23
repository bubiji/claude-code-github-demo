> issue: #7 · 案例: antispider1 · 来源: https://antispider1.scrape.center

# antispider1 · WebDriver 反爬

## 案例原文（逐字引自 scrape.center）

> 对接 WebDriver 反爬，检测到使用 WebDriver 就不显示页面，适合用作 WebDriver 反爬练习。

## 反爬是怎么判的（实证）

判定**完全发生在客户端 JS**，不在服务端。检测点在站点自己的 `/js/app.4dcf2489.js`
里，逐字原文（webpack 打包后的压缩代码）：

```js
r["default"].config.productionTip=!1;var E=window.navigator.webdriver;E?document.getElementById("app").innerHTML="<h2>Webdriver Forbidden.</h2>":new r["default"]({store:j,router:_,render:function(e){return e(w)}}).$mount("#app")
```

展开就是：

```js
var E = window.navigator.webdriver;
E ? document.getElementById("app").innerHTML = "<h2>Webdriver Forbidden.</h2>"
  : new Vue({store, router, render: h => h(App)}).$mount("#app");
```

- 页面本身是 Vue SPA，服务端返回的永远是同一份空壳 HTML（`<div id=app></div>`）。
- 浏览器执行 `app.js` 时读 `navigator.webdriver`：为真就把 `#app` 换成
  `<h2>Webdriver Forbidden.</h2>`，压根不挂载 Vue 应用；为假才正常渲染。
- W3C WebDriver 规范要求受自动化控制的浏览器把 `navigator.webdriver` 置为 `true`，
  Playwright/Selenium 默认就会命中。

### 三趟对照实测（`data/webdriver_evidence.json`，本机真跑）

| 趟 | 做法 | `navigator.webdriver` | `#app` 内容 | 电影卡片数 |
|---|---|---|---|---|
| A | 纯 HTTP（requests，浏览器 UA） | —（不执行 JS） | HTML 里既无数据也无 Forbidden 字样，status 200 / 952B | — |
| B | Playwright chromium，不做处理 | `true` | `Webdriver Forbidden.` | 0 |
| C | Playwright chromium，注入 init script | `undefined` | 正常渲染（首屏 `Scrape / 霸王别姬 - Farewell My Concubine / 剧情爱情`） | 10 |

A 趟证明**服务端没有做任何区分**——同一份 HTML 谁来都给，所以这不是 HTTP 层的反爬。

## 绕过办法

用 `add_init_script` 在页面任何脚本执行**之前**改掉这个属性：

```js
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
```

时机是关键：`app.js` 一执行就读了这个值，晚一步就来不及。

## 跑法

```bash
cd src/s04_antispider_basic/antispider1
../../../.venv/bin/python spider.py
```

依赖：`playwright`（**不在仓库根 requirements.txt 里**，装进 venv）

```bash
../../../.venv/bin/pip install playwright
../../../.venv/bin/playwright install chromium
```

## 产出

| 文件 | 内容 |
|---|---|
| `data/webdriver_evidence.json` | A/B/C 三趟对照的原始证据 |
| `data/antispider1_movies.json` | C 趟从渲染后 DOM 抓下来的 10 页共 100 条电影 |

实跑结果：10 页 × 10 条 = **100 条**，首条 `霸王别姬 - Farewell My Concubine` 评分 `9.5`。

## 练习伦理

每页之间 `wait_for_timeout(1000)` 间隔；只抓 scrape.center 这个作者公开提供的练习平台。
