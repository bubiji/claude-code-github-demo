> issue: #12 · 用途: 对照基准依赖 · 来源: https://spa8.scrape.center/js/crypto-js.min.js

# vendor/

`crypto-js.min.js` —— **站点自己下发的那一份**，逐字节原样保存，未做任何改动。

- 抓取命令：`curl -s https://spa8.scrape.center/js/crypto-js.min.js -o crypto-js.min.js`
- 抓取时间：2026-08-23
- 大小：47992 bytes
- spa8 / spa9 / spa10 / spa11 / spa12 / spa13 六站引用的都是同一路径的这份文件

放在这里只有一个用途：`tools/reftoken.js` 用它跑一遍还原出来的 `getToken()`，
输出与 `common.py` 的 Python 复刻逐字节比对。**对照基准必须是站点的原件，
换成 npm 上的 crypto-js 就不算对照了**（版本差异会让「对不上」变成噪声）。
