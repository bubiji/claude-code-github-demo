> issue: #7 · 阶段: 基础反爬（指纹、偏移与字体）· 来源: https://scrape.center/

# 阶段 4 · 基础反爬：指纹、偏移与字体

四个案例，四种完全不同的「藏法」，也对应四种完全不同的判定位置：

| 案例 | 站点 | 判定发生在 | 藏的是什么 | 破法 |
|---|---|---|---|---|
| [antispider1](antispider1/) | https://antispider1.scrape.center | **客户端 JS** | 整个页面（检测到 WebDriver 就不挂载 Vue） | 页面脚本执行前改掉 `navigator.webdriver` |
| [antispider2](antispider2/) | https://antispider2.scrape.center | **服务端** | 整个响应（403 + 135B） | 换一个不在黑名单里的 UA |
| [antispider3](antispider3/) | https://antispider3.scrape.center | 不判，**渲染时打乱** | 字符顺序（CSS 绝对定位 `left`） | 按 `left` 升序重排，真实下标 = left/16 |
| [antispider4](antispider4/) | https://antispider4.scrape.center | 不判，**渲染时替换** | 数字本身（icon class + CSS content + 自定义字体） | 建立 icon → 字符 → 码位 → 字形 → 明文 的映射表 |

## 实跑结果一览

| 案例 | 结果 |
|---|---|
| antispider1 | 未处理时 `navigator.webdriver=true`，`#app` = `Webdriver Forbidden.`，卡片 0；隐藏后 `undefined`，卡片 10 → 抓下 10 页 **100 条** |
| antispider2 | 31 个 UA 实测：放行 15 / 拒绝 16；19 个关键词 × 4 组对照定出匹配语义 → 用浏览器 UA 抓下 10 页 **100 条** |
| antispider3 | 36 条偏移书名，29 条源码顺序确实被打乱；按 `left` 重排后与 API 明文 **36/36 一致** |
| antispider4 | HTML 文本里评分为空 **100/100**；解码后与 API 明文 **100/100 一致** |

## 目录

```
src/s04_antispider_basic/
├── README.md            # 本文件
├── common.py            # 共用：浏览器 UA、礼貌间隔、落盘（>500KB 自动降级）
├── antispider1/         # spider.py（三趟对照 + 抓取）
├── antispider2/         # ua_probe.py（拒/放）、ua_rule_probe.py（怎么判）、spider.py
├── antispider3/         # spider.py（渲染 + 还原偏移 + 与 API 对账）
└── antispider4/         # font_map.py（拆字体建表）、spider.py（解码 + 与 API 对账）
```

## 依赖

仓库根 `requirements.txt` 已有的：`requests`、`beautifulsoup4`、`lxml`。

本阶段**额外**需要（未写进根 requirements.txt，按需装进 venv）：

```bash
.venv/bin/pip install playwright fonttools
.venv/bin/playwright install chromium
```

- `playwright`（1.62.0）：antispider1 / 3 / 4 需要真实浏览器执行 JS。
- `fonttools`（4.63.0）：antispider4 读 ttf 的 cmap 与字形轮廓。

## 练习伦理

scrape.center 是案例作者公开提供的专用练习平台。四个案例合计约 300 个页面请求 + 约 110 个
探针请求，全部带间隔（HTTP ≥ 0.8s，浏览器每页 1–1.5s），封面图一律 abort。
不要把这些代码指向未获授权的站点。
