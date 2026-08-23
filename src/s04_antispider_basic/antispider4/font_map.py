"""antispider4：把字体文件拆开，建立「密文字符 → 明文数字」映射表。

issue: #7 · 案例: antispider4 · 来源: https://antispider4.scrape.center

链路（每一环都从站点原件里读出来，不靠猜）：

    评分 8.5
      → 站点 JS 的映射表 {0:272,1:643,...} 把每位数字换成一个编号
      → 模板渲染成 <i class="icon icon-281"></i>
      → CSS `.icon-281:before{content:"8"}` 把编号换成一个 **ASCII 字符**
      → CSS `.icon{font-family:scrape}` 让这个字符用自定义字体 scrape 渲染
      → scrape 字体里 U+0038 这个码位的字形画出来的 **不是 8**

所以 HTML 里没有明文数字，浏览器里看到的数字由字体字形决定。
要还原就必须下载 ttf，读 cmap（码位 → 字形名），再看字形长什么样。

本脚本：
    1. 抓首页 → 找到 css/app.*.css → 解析出 @font-face 的 ttf 地址
    2. 解析 CSS 里全部 `.icon-NNN:before{content:"X"}`
    3. 下载 ttf，用 fontTools dump cmap / glyphOrder / 每个字形的轮廓
    4. 把 0-9 相关字形栅格化成 ASCII 点阵，肉眼即可读出真实数字
    5. 输出完整对照表

依赖：fonttools（不在仓库根 requirements.txt 里，装进 venv 即可）
    ../../../.venv/bin/pip install fonttools

跑法：
    ../../../.venv/bin/python font_map.py
产出：
    data/scrape.ttf              字体原件
    data/font_cmap.json          cmap 全表（码位 → 字形名）+ glyphOrder
    data/font_glyphs.txt         0-9 相关字形的 ASCII 点阵
    data/cipher_map.json         icon 编号 / 密文字符 / 码位 / 字形名 / 明文数字
"""
from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json  # noqa: E402

from fontTools.pens.basePen import BasePen  # noqa: E402
from fontTools.ttLib import TTFont  # noqa: E402

from common import BROWSER_UA, data_dir, get  # noqa: E402

BASE = "https://antispider4.scrape.center"

# 站点 JS 模块 e0eb 里的原文（数字 → icon 编号）
JS_DIGIT_TO_ICON = {
    "0": 272, "1": 643, "2": 180, "3": 437, "4": 378,
    "5": 504, "6": 203, "7": 102, "8": 281, "9": 789, ".": 981,
}


# ---------- 站点原件抓取 ----------

def fetch_css() -> tuple[str, list[str]]:
    """返回 (全部 css 文本, css 地址列表)。"""
    html = get(f"{BASE}/", ua=BROWSER_UA).text
    hrefs = re.findall(r'href=/?(css/[\w.\-]+\.css)', html)
    hrefs = list(dict.fromkeys(hrefs))
    texts, urls = [], []
    for h in hrefs:
        u = f"{BASE}/{h}"
        texts.append(get(u, ua=BROWSER_UA).text)
        urls.append(u)
    return "\n".join(texts), urls


def find_font_url(css: str) -> str:
    """从 @font-face{font-family:scrape;...} 里挑出 ttf 地址。"""
    m = re.search(r'@font-face\s*\{[^}]*font-family:\s*scrape;[^}]*\}', css)
    if not m:
        raise SystemExit("没找到 font-family:scrape 的 @font-face")
    block = m.group(0)
    t = re.search(r'url\(([^)]*\.ttf)\)', block)
    if not t:
        raise SystemExit(f"@font-face 里没有 ttf：{block}")
    path = t.group(1).lstrip("./").lstrip("/")
    if path.startswith("../"):
        path = path[3:]
    return f"{BASE}/{path}"


def parse_icon_rules(css: str) -> dict[str, str]:
    """`.icon-272:before{content:"0"}` → {"272": "0"}；\\XX 转义还原成真字符。"""
    out = {}
    for num, raw in re.findall(r'\.icon-(\d+):before\{content:"((?:[^"\\]|\\.)*)"\}', css):
        if raw.startswith("\\"):
            ch = chr(int(raw[1:].strip(), 16))
        else:
            ch = raw
        out[num] = ch
    return out


# ---------- 字形栅格化（把轮廓画成 ASCII 点阵） ----------

class PolyPen(BasePen):
    """把字形轮廓拍扁成多边形点列。"""

    def __init__(self, glyphSet, steps: int = 10):
        super().__init__(glyphSet)
        self.contours: list[list[tuple[float, float]]] = []
        self._cur: list[tuple[float, float]] = []
        self.steps = steps

    def _moveTo(self, pt):
        if self._cur:
            self.contours.append(self._cur)
        self._cur = [pt]

    def _lineTo(self, pt):
        self._cur.append(pt)

    def _curveToOne(self, p1, p2, p3):
        p0 = self._cur[-1]
        for i in range(1, self.steps + 1):
            t = i / self.steps
            u = 1 - t
            x = u**3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t**3 * p3[0]
            y = u**3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t**3 * p3[1]
            self._cur.append((x, y))

    def _closePath(self):
        if self._cur:
            self.contours.append(self._cur)
            self._cur = []

    def _endPath(self):
        self._closePath()

    def done(self):
        if self._cur:
            self.contours.append(self._cur)
            self._cur = []
        return self.contours


def _inside(contours, x: float, y: float) -> bool:
    """奇偶规则（数字字形的内圈用这个就够）。"""
    hit = False
    for c in contours:
        n = len(c)
        for i in range(n):
            x1, y1 = c[i]
            x2, y2 = c[(i + 1) % n]
            if (y1 > y) != (y2 > y):
                xint = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
                if x < xint:
                    hit = not hit
    return hit


def render_ascii(font: TTFont, glyph_name: str, w: int = 22, h: int = 24) -> str:
    gs = font.getGlyphSet()
    if glyph_name not in gs:
        return "(字形不存在)"
    pen = PolyPen(gs)
    gs[glyph_name].draw(pen)
    contours = pen.done()
    if not contours:
        return "(空字形)"
    xs = [p[0] for c in contours for p in c]
    ys = [p[1] for c in contours for p in c]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    if x1 == x0 or y1 == y0:
        return "(退化字形)"
    lines = []
    for row in range(h):
        y = y1 - (row + 0.5) * (y1 - y0) / h
        line = "".join(
            "█" if _inside(contours, x0 + (col + 0.5) * (x1 - x0) / w, y) else "·"
            for col in range(w)
        )
        lines.append(line)
    return "\n".join(lines)


# ---------- 主流程 ----------

def main():
    d = data_dir(__file__)

    css, css_urls = fetch_css()
    font_url = find_font_url(css)
    icon_rules = parse_icon_rules(css)
    print(f"CSS: {css_urls}")
    print(f"字体: {font_url}")

    ttf_path = os.path.join(d, "scrape.ttf")
    r = get(font_url, ua=BROWSER_UA)
    r.raise_for_status()
    with open(ttf_path, "wb") as f:
        f.write(r.content)
    print(f"字体已存 → {ttf_path}（{len(r.content)}B）")

    font = TTFont(ttf_path)
    cmap = font.getBestCmap()  # {codepoint: glyphName}
    cmap_dump = {f"U+{cp:04X}": {"char": chr(cp), "glyph": gn} for cp, gn in sorted(cmap.items())}
    with open(os.path.join(d, "font_cmap.json"), "w", encoding="utf-8") as f:
        json.dump(
            {
                "font_url": font_url,
                "num_glyphs": font["maxp"].numGlyphs,
                "glyph_order_head": font.getGlyphOrder()[:40],
                "cmap": cmap_dump,
            },
            f, ensure_ascii=False, indent=2,
        )
    print(f"cmap 共 {len(cmap)} 个码位")

    # 逐个 icon 编号：编号 → 密文字符 → 码位 → 字形名 → 点阵
    art_lines = [
        "antispider4 · scrape 字体字形点阵",
        f"字体：{font_url}",
        "",
        "读法：左边是 CSS `content` 里那个 ASCII 密文字符，右边点阵是这个码位在 scrape",
        "字体里实际画出来的形状——两者对不上，正是这个案例的全部秘密。",
        "",
    ]
    rows = []
    for digit, icon in JS_DIGIT_TO_ICON.items():
        cipher = icon_rules.get(str(icon))
        if cipher is None:
            rows.append({"plain_digit": digit, "icon_class": f"icon-{icon}", "error": "CSS 里没有该规则"})
            continue
        cp = ord(cipher)
        gname = cmap.get(cp)
        art = render_ascii(font, gname) if gname else "(cmap 无此码位)"
        rows.append(
            {
                "plain_digit": digit,          # JS 表给出的明文
                "icon_class": f"icon-{icon}",  # HTML 里出现的 class
                "cipher_char": cipher,         # CSS content 里的密文字符
                "codepoint": f"U+{cp:04X}",
                "glyph_name": gname,
                "ascii_art": art,
            }
        )
        art_lines += [
            f"--- icon-{icon} | CSS content = {cipher!r} (U+{cp:04X}) | 字形名 {gname} "
            f"| JS 表声称的明文 = {digit} ---",
            art,
            "",
        ]

    with open(os.path.join(d, "font_glyphs.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(art_lines))

    with open(os.path.join(d, "cipher_map.json"), "w", encoding="utf-8") as f:
        json.dump(
            {
                "font_url": font_url,
                "css_urls": css_urls,
                "js_digit_to_icon": JS_DIGIT_TO_ICON,
                "icon_to_cipher_char": {k: v for k, v in sorted(icon_rules.items())
                                        if int(k) in JS_DIGIT_TO_ICON.values()},
                "table": [{k: v for k, v in r.items() if k != "ascii_art"} for r in rows],
                "decode_map_icon_to_digit": {
                    r["icon_class"]: r["plain_digit"] for r in rows if "cipher_char" in r
                },
            },
            f, ensure_ascii=False, indent=2,
        )

    print("\nicon 编号 → 密文字符 → 码位 → 字形名 → 明文数字")
    for r in rows:
        if "cipher_char" not in r:
            print(f"  {r['icon_class']}  {r.get('error')}")
            continue
        print(f"  {r['icon_class']:<10} {r['cipher_char']!r:<5} {r['codepoint']:<8} "
              f"{str(r['glyph_name']):<12} → {r['plain_digit']}")
    print(f"\n落盘 → {d}/font_cmap.json, {d}/font_glyphs.txt, {d}/cipher_map.json")
    print("点阵见 font_glyphs.txt，肉眼即可核对字形画的到底是哪个数字。")


if __name__ == "__main__":
    main()
