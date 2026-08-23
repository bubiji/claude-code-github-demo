# 原件：scrape.center 案例清单（54 条）

> **出处**：<https://scrape.center/> 首页案例列表（数据取自站点 JS chunk 中的 `items` 数组）
> **抓取日期**：2026-08-23　**抓取脚本**：`src/tools/fetch_cases.py`　**机读副本**：`doc/scrape-center-cases.raw.json`

本文件为**原件**：案例的 `name` / `category` / `url` / `description` 四个字段逐字照录站点内容，
未做改写、润色、精简或翻译。本仓库的分析、阶段划分与验收标准一律写在 `doc/学习计划.md`，不混入本文件。


## SSR 网站

- **ssr1** — <https://ssr1.scrape.center>
  > 电影数据网站，无反爬，数据通过服务端渲染，适合基本爬虫练习。
- **ssr2** — <https://ssr2.scrape.center>
  > 电影数据网站，无反爬，无 HTTPS 证书，适合用作 HTTPS 证书验证。
- **ssr3** — <https://ssr3.scrape.center>
  > 电影数据网站，无反爬，带有 HTTP Basic Authentication，适合用作 HTTP 认证案例，用户名密码均为 admin。
- **ssr4** — <https://ssr4.scrape.center>
  > 电影数据网站，无反爬，每个响应增加了 5 秒延迟，适合测试慢速网站爬取或做爬取速度测试，减少网速干扰。

## SPA 网站

- **spa1** — <https://spa1.scrape.center>
  > 电影数据网站，无反爬，数据通过 Ajax 加载，页面动态渲染，适合 Ajax 分析和动态页面渲染爬取。
- **spa2** — <https://spa2.scrape.center>
  > 电影数据网站，无反爬，数据通过 Ajax 加载，数据接口参数加密且有时间限制，适合动态页面渲染爬取或 JavaScript 逆向分析。
- **spa3** — <https://spa3.scrape.center>
  > 电影数据网站，无反爬，数据通过 Ajax 加载，无页码翻页，下拉至底部刷新，适合 Ajax 分析和动态页面渲染爬取。
- **spa4** — <https://spa4.scrape.center>
  > 新闻网站索引，无反爬，数据通过 Ajax 加载，无页码翻页，适合 Ajax 分析和动态页面渲染抓取以及智能页面提取分析。
- **spa5** — <https://spa5.scrape.center>
  > 图书网站，无反爬，数据通过 Ajax 加载，有翻页，适合大批量动态页面渲染抓取。
- **spa6** — <https://spa6.scrape.center>
  > 电影数据网站，数据通过 Ajax 加载，数据接口参数加密且有时间限制，源码经过混淆，适合 JavaScript 逆向分析。
- **spa7** — <https://spa7.scrape.center>
  > NBA 球星数据网站，数据纯前端渲染，Token 经过加密处理，适合基础 JavaScript 模拟分析。
- **spa8** — <https://spa8.scrape.center>
  > NBA 球星数据网站，数据纯前端渲染，Token 经过加密处理，JavaScript 代码一行混入 HTML 代码，防止直接调试，适合 JavaScript 逆向分析。
- **spa9** — <https://spa9.scrape.center>
  > NBA 球星数据网站，数据纯前端渲染，Token 经过加密处理，JavaScript 经过 eval 混淆，适合 JavaScript 逆向分析。
- **spa10** — <https://spa10.scrape.center>
  > NBA 球星数据网站，数据纯前端渲染，Token 经过加密处理，JavaScript 经过 JJEncode 混淆，适合 JavaScript 逆向分析。
- **spa11** — <https://spa11.scrape.center>
  > NBA 球星数据网站，数据纯前端渲染，Token 经过加密处理，JavaScript 经过 AAEncode 混淆，适合 JavaScript 逆向分析。
- **spa12** — <https://spa12.scrape.center>
  > NBA 球星数据网站，数据纯前端渲染，Token 经过加密处理，JavaScript 经过 JSFuck 混淆，适合 JavaScript 逆向分析。
- **spa13** — <https://spa13.scrape.center>
  > NBA 球星数据网站，数据纯前端渲染，Token 经过加密处理，JavaScript 经过 JavaScript Obfuscator 混淆，适合 JavaScript 逆向分析。
- **spa14** — <https://spa14.scrape.center>
  > 电影数据网站，数据通过 Ajax 加载，数据接口参数加密且有时间限制，加密过程通过数值型 WASM 实现，适合 WASM 逆向分析。
- **spa15** — <https://spa15.scrape.center>
  > 电影数据网站，数据通过 Ajax 加载，数据接口参数加密且有时间限制，加密过程通过字符串型 WASM 实现，适合 WASM 逆向分析。
- **spa16** — <https://spa16.scrape.center>
  > 图书网站，无反爬，不同于其他，该网站协议采用 HTTP 2，适合用于 HTTP 2 协议分析和测试。

## 工具网站

- **tool1** — <https://proxypool.scrape.center/random>
  > 代理池 API 网站，访问即可获取随机可用公开代理，源代码来自 https://github.com/Python3WebSpider/ProxyPool

## 验证码网站

- **captcha1** — <https://captcha1.scrape.center>
  > 对接滑动拼图验证码，适合滑动拼图验证码分析处理。
- **captcha2** — <https://captcha2.scrape.center>
  > 对接图标点选验证码，适合图标点选验证码分析处理。
- **captcha3** — <https://captcha3.scrape.center>
  > 对接图文点选验证码，适合图文点选验证码分析处理。
- **captcha4** — <https://captcha4.scrape.center>
  > 对接语序分析验证码，适合语序分析验证码分析处理。
- **captcha5** — <https://captcha5.scrape.center>
  > 对接空间推理验证码，适合空间推理验证码分析处理。
- **captcha6** — <https://captcha6.scrape.center>
  > 对接九宫格识图验证码，适合九宫格识图验证码分析处理。
- **captcha7** — <https://captcha7.scrape.center>
  > 对接普通图像验证码，干扰较少，适合 OCR 识别。
- **captcha8** — <https://captcha8.scrape.center>
  > 对接普通图像验证码，干扰较多，适合打码平台或深度学习处理。

## 模拟登录网站

- **login1** — <https://login1.scrape.center>
  > 模拟登录网站，登录时用户名和密码经过加密处理，适合 JavaScript 逆向分析。
- **login2** — <https://login2.scrape.center>
  > 对接 Session + Cookies 模拟登录，适合用作 Session + Cookies 模拟登录练习。
- **login3** — <https://login3.scrape.center>
  > 对接 JWT 模拟登录方式，适合用作 JWT 模拟登录练习。

## WebSocket

- **websocket1** — <https://websocket1.scrape.center>
  > WebSocket 单人聊天室，适合做 WebSocket 抓包分析。

## 反爬网站

- **antispider1** — <https://antispider1.scrape.center>
  > 对接 WebDriver 反爬，检测到使用 WebDriver 就不显示页面，适合用作 WebDriver 反爬练习。
- **antispider2** — <https://antispider2.scrape.center>
  > 对接 User-Agent 反爬，检测到常见爬虫 User-Agent 就会拒绝响应，适合用作 User-Agent 反爬练习。
- **antispider3** — <https://antispider3.scrape.center>
  > 对接文字偏移反爬，所见顺序并不一定和源码顺序一致，适合用作文字偏移反爬练习。
- **antispider4** — <https://antispider4.scrape.center>
  > 对接字体文件反爬，显示的内容并不在 HTML 内，而是隐藏在字体文件，设置了文字映射表，适合用作字体反爬练习。
- **antispider5** — <https://antispider5.scrape.center>
  > 限制单个 IP 访问频率 5 分钟最多 10 次，如果过多则会封禁 IP 10 分钟。
- **antispider6** — <https://antispider6.scrape.center>
  > 限制单个账号访问频率 5 分钟最多 10 次，如果过多则会暂停访问 10 分钟。
- **antispider7** — <https://antispider7.scrape.center>
  > 限制单个 IP 访问频率 5 分钟最多 10 次，同时限制单个账号访问频率 5 分钟最多 10 次，如果过多则会封禁 IP 或账号 10 分钟。
- **antispider8** — <https://antispider8.scrape.center>
  > JavaScript 反爬，增加了接口处的无限 debugger 和定时循环 debugger。
- **antispider9** — <https://antispider9.scrape.center>
  > JavaScript 反爬，核心加密逻辑使用位置移动数组混淆，同时设置格式化保护，适合 AST 分析。
- **antispider10** — <https://antispider10.scrape.center>
  > JavaScript 反爬，核心加密逻辑使用控制流扁平化混淆，适合 AST 分析。

## App 极简样例

- **appbasic1** — <https://appbasic1.scrape.center/>
  > 极简 App 案例，只有一个按钮和回调提示框，逻辑在 Java 层实现，适合做 Hook 分析。
- **appbasic2** — <https://appbasic2.scrape.center/>
  > 极简 App 案例，只有一个按钮和回调提示框，逻辑在 Native 层实现，适合做逆向和 Hook 分析。

## App

- **app1** — <https://app1.scrape.center/>
  > 最基本的 App 案例，数据通过接口加载，无反爬，无任何加密参数，适合做抓包分析和请求模拟。
- **app2** — <https://app2.scrape.center/>
  > 设置了接口请求不走系统代理，因此无法直接抓包，适合做抓包特殊处理。
- **app3** — <https://app3.scrape.center/>
  > 对系统代理进行了检测，如果设置了代理则无法正常请求数据，适合做抓包特殊处理。
- **app4** — <https://app4.scrape.center/>
  > 设置了 SSL Pining，如果设置了非法证书则无法正常请求数据，适合做反 SSL Pining 处理。
- **app5** — <https://app5.scrape.center/>
  > 接口增加了加密参数，适合做抓包实时处理或可视化爬取或逆向分析。
- **app6** — <https://app6.scrape.center/>
  > 接口增加了加密参数，同时对源码进行了混淆，适合做抓包实时处理或可视化爬取或逆向分析。
- **app7** — <https://app7.scrape.center/>
  > 接口增加了加密参数，同时对安装包进行了加固处理，适合做抓包实时处理或可视化爬取或逆向分析。
- **app8** — <https://app8.scrape.center/>
  > 核心加密算法在 Native 层实现，适合做 so 模拟调用或者逆向分析。
- **app9** — <https://app9.scrape.center/>
  > 核心加密算法在 Native 层实现，同时添加了 LLVM 混淆，适合做 so 模拟或者逆向分析。
