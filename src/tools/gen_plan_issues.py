#!/usr/bin/env python3
"""把 scrape.center 的 54 个案例排成学习计划，生成 GitHub issue 正文。

- 案例文字（标题/描述/URL）逐字取自 doc/scrape-center-cases.raw.json，
  不改写、不润色（rule 第 15 条 原件保真）；阶段划分与验收标准是自撰内容，
  在正文里用引用块/正文区分开。
- 只生成正文文件，不直接调 gh；建 issue 由 create_plan_issues.sh 负责，
  便于先看内容再提交。

用法：
  python3 src/tools/gen_plan_issues.py            # 输出到 build/issues/
  python3 src/tools/gen_plan_issues.py -o <dir>
"""
import argparse
import json
import os

SRC_URL = "https://scrape.center/"
CASES = "doc/scrape-center-cases.raw.json"

# (阶段号, 标题, 代码目录, 目标, 验收标准, [案例 name...])
STAGES = [
    (1, "基础请求与解析（SSR 服务端渲染）", "s01_ssr",
     "把「请求 → 解析 → 落盘」这条最短链路跑通，并处理 HTTPS 证书、HTTP Basic Auth、慢响应三种最常见的连接层问题。",
     ["能从列表页翻页抓全所有电影，字段完整存成 JSON/CSV",
      "ssr2 证书异常能明确关掉校验并说明风险，不是靠忽略警告蒙混",
      "ssr3 用 HTTP Basic Auth 正常取数（用户名密码均为 admin）",
      "ssr4 每响应 5 秒延迟下，用并发/超时控制把总耗时压到可接受范围"],
     ["ssr1", "ssr2", "ssr3", "ssr4"]),
    (2, "Ajax 与动态渲染", "s02_ajax_spa",
     "学会看 XHR/Fetch 接口，优先直连数据接口；接口不可用时再退回浏览器渲染。覆盖翻页、无限下拉、索引页三种加载形态。",
     ["spa1/spa5 通过接口分页参数抓全数据，不依赖浏览器",
      "spa3 无限下拉的加载触发条件讲清楚（偏移/游标各是什么）",
      "spa4 新闻索引页做到通用正文提取，不写死选择器",
      "同一份解析逻辑同时能被「接口模式」和「渲染模式」复用"],
     ["spa1", "spa3", "spa4", "spa5"]),
    (3, "协议专题：HTTP/2 与 WebSocket", "s03_protocol",
     "跳出 requests 的舒适区，处理协议本身的差异：HTTP/2 站点与 WebSocket 长连接。",
     ["spa16 用支持 HTTP/2 的客户端（如 httpx）成功取数，并对比 HTTP/1.1 的差别",
      "websocket1 完成握手、收发消息、正确关闭连接",
      "两个案例都留有抓包证据（HAR 或帧记录）"],
     ["spa16", "websocket1"]),
    (4, "基础反爬：指纹、偏移与字体", "s04_antispider_basic",
     "识别并绕过四类不涉及加密的反爬：WebDriver 特征、User-Agent 校验、文字偏移、字体映射。",
     ["antispider1 隐藏 WebDriver 特征后页面正常渲染",
      "antispider2 用合规 UA 正常响应，并说明服务端是按什么判的",
      "antispider3 还原出「所见顺序」与「源码顺序」的映射关系",
      "antispider4 解析字体文件建立映射表，把隐藏文字还原成明文"],
     ["antispider1", "antispider2", "antispider3", "antispider4"]),
    (5, "频率限制与代理池", "s05_rate_proxy",
     "面对 IP 维度、账号维度、双维度三种限流，做出「不触发封禁」的调度策略，并接入代理池。",
     ["antispider5/6/7 各自跑完全量数据且全程未被封禁",
      "限流策略是主动控速 + 退避重试，不是撞墙后硬重试",
      "tool1 代理池接入成型：取代理 → 校验可用 → 失败剔除"],
     ["antispider5", "antispider6", "antispider7", "tool1"]),
    (6, "模拟登录：加密表单、Session、JWT", "s06_login",
     "掌握三种登录态：表单参数加密、Session + Cookies、JWT，并把登录态复用到后续请求。",
     ["login1 还原用户名密码的加密过程，脱离浏览器完成登录",
      "login2 Session + Cookies 持久化，重启脚本无需重新登录",
      "login3 正确携带 JWT 并处理过期刷新"],
     ["login1", "login2", "login3"]),
    (7, "验证码专题", "s07_captcha",
     "覆盖八类验证码的分析思路。重点是把「怎么判断通过/失败」这套验证闭环写出来，识别手段可以是 OCR、模型或打码平台。",
     ["captcha1 滑动拼图：缺口定位 + 轨迹生成",
      "captcha2/3 点选类：目标定位与点击顺序",
      "captcha4/5/6 推理类：题面解析思路成文（可不追求高通过率）",
      "captcha7 OCR 打通；captcha8 说明为何需要打码平台或深度学习",
      "每个案例记录通过率，而不是只贴一次成功截图"],
     ["captcha1", "captcha2", "captcha3", "captcha4", "captcha5", "captcha6", "captcha7", "captcha8"]),
    (8, "JavaScript 逆向入门", "s08_js_reverse",
     "第一次真正读 JS：定位加密入口、抠出算法、在 Python 侧复现或用 Node 执行。",
     ["spa2 复现接口签名参数与时间限制逻辑",
      "spa6 在源码混淆的前提下仍定位到加密入口",
      "spa7 还原纯前端渲染的 Token 生成过程",
      "三者都能脱离浏览器直接请求接口成功"],
     ["spa2", "spa6", "spa7"]),
    (9, "JS 混淆对抗", "s09_js_obfuscation",
     "逐个拆解常见混淆手法：一行混入 HTML、eval、JJEncode、AAEncode、JSFuck、JavaScript Obfuscator，以及无限 debugger。",
     ["spa8-spa13 六种混淆各留一份「还原前 → 还原后」的对照记录",
      "antispider8 绕过无限 debugger 与定时循环 debugger，说明用的是哪种手段",
      "总结成一份「混淆特征 → 识别方法 → 还原手段」速查表"],
     ["spa8", "spa9", "spa10", "spa11", "spa12", "spa13", "antispider8"]),
    (10, "AST 还原高级混淆", "s10_ast",
     "从「肉眼读代码」升级到「用 AST 批量还原」：处理数组位置移动混淆和控制流扁平化。",
     ["antispider9 写出 AST 插件还原位置移动数组，并绕过格式化保护",
      "antispider10 还原控制流扁平化，恢复出可读的顺序逻辑",
      "AST 脚本可复用到其他同类站点，不是一次性硬编码"],
     ["antispider9", "antispider10"]),
    (11, "WASM 逆向", "s11_wasm",
     "加密逻辑搬进 WebAssembly 后的两种形态：数值型与字符串型。",
     ["spa14 数值型 WASM：调用或复现加密函数产出合法参数",
      "spa15 字符串型 WASM：处理内存读写与字符串传参",
      "两者都能在 Python/Node 侧独立生成参数并成功请求接口"],
     ["spa14", "spa15"]),
    (12, "App 抓包与逆向", "s12_app",
     "从 Web 转向移动端：抓包环境搭建、代理检测与 SSL Pinning 对抗、Native 层算法与 Hook。本阶段需要 Android 设备或模拟器。",
     ["appbasic1/appbasic2 完成 Java 层与 Native 层的 Hook 分析",
      "app1 完成基础抓包与请求模拟",
      "app2/app3 处理不走系统代理与代理检测",
      "app4 完成反 SSL Pinning",
      "app5/6/7 拿到加密参数（抓包实时处理、可视化爬取、逆向任选其一并说明取舍）",
      "app8/app9 完成 so 层算法的模拟调用或逆向"],
     ["appbasic1", "appbasic2", "app1", "app2", "app3", "app4",
      "app5", "app6", "app7", "app8", "app9"]),
]


def case_map(root):
    with open(os.path.join(root, CASES), encoding="utf-8") as f:
        return {c["name"]: c for c in json.load(f)}


def render(stage, cases, total_stages):
    num, title, codedir, goal, criteria, names = stage
    L = []
    L.append(f"## 目标\n\n{goal}\n")
    L.append(f"## 案例清单（{len(names)} 个）\n")
    L.append(f"案例标题、描述与链接**逐字引自** {SRC_URL}（原件保真，未做任何改写）：\n")
    for n in names:
        c = cases[n]
        L.append(f"- [ ] **{c['name']}** · {c['category']} · <{c['url']}>")
        L.append(f"  > {c['description']}")
    L.append("")
    L.append("## 代码位置\n")
    L.append(f"本阶段代码一律放在 `src/{codedir}/`，每个案例一个子目录：\n")
    L.append("```")
    for n in names[:3]:
        L.append(f"src/{codedir}/{n}/")
    if len(names) > 3:
        L.append("...")
    L.append("```")
    L.append("")
    L.append("## 验收标准\n")
    for c in criteria:
        L.append(f"- [ ] {c}")
    L.append("")
    L.append("## 提交纪律\n")
    L.append("本仓库要求**任何代码提交都必须关联 issue**，完整规则见仓库根目录 `CLAUDE.md`：\n")
    L.append(f"- 分支：`case/s{num:02d}-<案例名>`")
    L.append(f"- commit message 结尾带 `refs #<本 issue 号>`")
    L.append(f"- PR 正文写 `Closes #<本 issue 号>`")
    L.append(f"- 代码合入后，在本 issue 下贴出代码永久链接（Permalink），做到「从 issue 能找到代码」")
    L.append("")
    L.append(f"---\n阶段 {num}/{total_stages} · 案例来源：{SRC_URL}")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--outdir", default="build/issues")
    ap.add_argument("--root", default=".")
    a = ap.parse_args()

    cases = case_map(a.root)
    os.makedirs(a.outdir, exist_ok=True)
    total = len(STAGES)
    index = []
    for s in STAGES:
        num, title, codedir = s[0], s[1], s[2]
        body = render(s, cases, total)
        path = os.path.join(a.outdir, f"stage{num:02d}.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(body)
        index.append((num, f"[阶段 {num}] {title}", f"src/{codedir}/", len(s[5]), path))
        print(f"✓ 阶段 {num:2d}  {title}  （{len(s[5])} 案例）→ {path}")

    covered = sum(len(s[5]) for s in STAGES)
    print(f"\n合计 {covered} 个案例 / 案例库共 {len(cases)} 个",
          "✓ 全覆盖" if covered == len(cases) else "⚠ 有遗漏")
    with open(os.path.join(a.outdir, "index.json"), "w", encoding="utf-8") as f:
        json.dump([{"stage": n, "title": t, "codedir": d, "cases": c}
                   for n, t, d, c, _ in index], f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
