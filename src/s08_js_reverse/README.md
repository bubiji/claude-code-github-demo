> issue: #11 · 阶段: 阶段 8 JavaScript 逆向入门 · 来源: https://scrape.center/

# 阶段 8：JavaScript 逆向入门（spa2 / spa6 / spa7）

三个案例的共同要求：**加密参数必须在 Python 侧独立生成**——不开浏览器、不把浏览器里抓到的
token 硬编码复用。spa2/spa6 的参数带 ±180 秒时间限制，硬编码的过三分钟必失效。

```
src/s08_js_reverse/
├── spa2/     Ajax 接口签名 token（sha1+base64+时间戳），未混淆
├── spa6/     同一套算法，源码混淆，且调用参数少一个（照抄 spa2 必 401）
└── spa7/     纯前端渲染 + DES-ECB Token，自写纯 Python DES 还原
```

## 三个案例一张表

| | spa2 | spa6 | spa7 |
|---|---|---|---|
| 加密位置 | 懒加载 chunk 模块 `7d92` | 同名模块 `7d92`（混淆后） | `js/main.js`（未压缩） |
| 算法 | `base64(sha1(args+","+t) + "," + t)` | 同左 | `base64(DES-ECB-PKCS7(...))` |
| 时间限制 | **±180 秒**（实测） | **±180 秒**（实测） | 无（Token 与时间无关） |
| 列表 token 参数 | `["/api/movie", offset, t]` | `["/api/movie", t]` ← **少一个** | — |
| 数据来源 | `/api/movie` JSON 接口 | `/api/movie` JSON 接口 | 静态 `main.js`，**站点没有接口** |
| Python 侧依赖 | 只有 `hashlib`/`base64` | 只有 `hashlib`/`base64` | 自写 `des.py`，零依赖 |
| 走的路线 | 纯 Python 复现算法 | 纯 Python 复现算法 | 纯 Python 复现算法（Node 与浏览器只做交叉验证） |

**三个案例都没有用「Node 执行抠出来的 JS」这条路线**——加密逻辑全部用 Python 重写。
spa7 里的 `verify_with_node.js` 不参与生产 Token，只是拿站点自己的 crypto-js 当对照裁判。

## 定位加密入口的通用方法（这三站真用上的）

1. **先确认数据不在 HTML 里**：`curl` 首页看是不是 Vue 空壳。
2. **入口 bundle 搜不到不代表没有**：Vue 路由懒加载会把页面组件切进 chunk，
   chunk 名字在首页 HTML 的 `<link rel=prefetch>` 里列着，全下下来再搜。
3. **挑对关键字**。`token` 能搜到调用点（它是 HTTP 参数名，混淆器不敢改）；
   要找生成器则搜 **`getTime`**——加密库里 SHA1/Base64/AES 满地都是，
   但没有哪个库会调 `new Date().getTime()`，而「参数带时间限制」的签名一定要取当前时间。
   搜 `SHA1` 会先命中 crypto-js 自己的 PBKDF2 模块，是弯路（spa2/spa6 都踩了）。
4. **既看生成器，也看调用点**。算法对了、实参个数错了照样 401（spa6 就是这样）。
5. **判定一律实测**：时间窗口靠平移时间戳打表打出来，参数个数差异靠 401/200 对照实验钉死。

## 阶段实测汇总（真跑）

| 案例 | 结果 |
|---|---|
| spa2 | 列表 104/104 条、详情抽样 5/5 条全 200；时间窗口实测 `[-180, +180]` 秒 |
| spa6 | 列表 104/104 条、详情抽样 5/5 条全 200；对照实验双向 401；窗口 `[-181, +179]` 秒（同 180 秒策略，±1 秒是往返延迟） |
| spa7 | 16 名球员 Token 全部生成；与站点自带 crypto-js（Node）**16/16 一致**；与真浏览器 tooltip 一致 |

各案例的完整过程、试错、原始 JS 存证与两次运行的时间戳，见各自目录的 `README.md`。

## 练习伦理

全部串行、单线程、请求间隔 0.8 秒；详情页只抽样不全量刷；只针对 scrape.center 这个
案例作者公开提供的练习平台。
