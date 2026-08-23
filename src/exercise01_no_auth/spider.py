#!/usr/bin/env python3
"""练习作业 1：不需要验证的网站信息获取（教学 demo，单文件、无跨目录依赖）。

issue: #1 · 案例: ssr1 · 来源: https://ssr1.scrape.center

「不需要验证」= 不用登录、不用 Cookie/Token、不用验证码、不用加密参数，
一个匿名的 HTTP GET 就能把数据拿回来。

本脚本干两件事：

  第 0 步  probe   —— 先判断「这个站到底要不要验证」，再决定抓不抓。
  主链路   crawl   —— 对确认免验证的 ssr1 跑一条最短的「请求 → 解析 → 落盘」。

用法：
    python spider.py --probe            # 只做免验证体检，不抓数据
    python spider.py                    # 抓 ssr1 全部 10 页列表 → data/ssr1_movies.json
    python spider.py --pages 2          # 只抓前 2 页（课堂演示够用）
    python spider.py --pages 1 --detail 3   # 再抓前 3 条的详情页（剧情简介/导演/演员）
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# 常量：目标站点
# ---------------------------------------------------------------------------

BASE = "https://ssr1.scrape.center"          # 主案例：无反爬、服务端渲染
LIST_URL = BASE + "/page/{page}"             # 列表页，页码从 1 开始，共 10 页
DETAIL_URL = BASE + "/detail/{movie_id}"     # 详情页，id 来自列表页的链接

# 免验证体检的对照组：三个免验证站 + 一个需要验证的反例。
# 描述逐字引自 https://scrape.center/ ，未作任何改写。
PROBE_TARGETS = [
    ("ssr1", "https://ssr1.scrape.center/page/1",
     "电影数据网站，无反爬，数据通过服务端渲染，适合基本爬虫练习。"),
    ("ssr4", "https://ssr4.scrape.center/page/1",
     "电影数据网站，无反爬，每个响应增加了 5 秒延迟，适合测试慢速网站爬取或做爬取速度测试，减少网速干扰。"),
    ("spa1", "https://spa1.scrape.center/",
     "电影数据网站，无反爬，数据通过 Ajax 加载，页面动态渲染，适合 Ajax 分析和动态页面渲染爬取。"),
    ("ssr3", "https://ssr3.scrape.center/page/1",
     "电影数据网站，无反爬，带有 HTTP Basic Authentication，适合用作 HTTP 认证案例，用户名密码均为 admin。"),
]

# 礼貌抓取：亮明身份 + 请求之间留间隔，不压测（见仓库 CLAUDE.md「练习伦理」）。
HEADERS = {"User-Agent": "claude-code-github-demo/exercise01 (+https://github.com/bubiji/claude-code-github-demo)"}
DATA_DIR = Path(__file__).parent / "data"


# ---------------------------------------------------------------------------
# 第 0 步：免验证体检
# ---------------------------------------------------------------------------

def probe_one(session: requests.Session, url: str) -> dict:
    """匿名发一次 GET，只看三件事：状态码、要不要验证、HTML 里有没有真数据。

    判定规则（都是可观察的事实，不靠猜）：
      * 401 + 响应头带 WWW-Authenticate  → 需要 HTTP 认证，属于「需要验证」
      * 200 且 HTML 里能解析出条目卡片    → 免验证，且数据直接在 HTML 里，可以抓
      * 200 但 HTML 里没有条目            → 免验证，但数据是 Ajax 二次加载的，要另找接口
    """
    started = time.perf_counter()
    # allow_redirects 保持默认（True）：登录墙常表现为 302 跳到登录页，跟到终点才看得出来。
    resp = session.get(url, timeout=30)
    elapsed = round(time.perf_counter() - started, 2)

    # 401 是「需要验证」最直白的信号，服务端会在响应头里说明认证方式。
    auth_scheme = resp.headers.get("WWW-Authenticate")
    cards = len(BeautifulSoup(resp.text, "lxml").select(".el-card.item"))

    if resp.status_code == 401:
        verdict = "需要验证：{}".format(auth_scheme or "未声明认证方式")
    elif resp.status_code != 200:
        verdict = f"异常状态码 {resp.status_code}，本练习不处理"
    elif cards > 0:
        verdict = f"免验证，且 HTML 里直接有 {cards} 条数据 → 可以抓"
    else:
        verdict = "免验证，但 HTML 里没有数据（Ajax 动态渲染）→ 要去找它的接口"

    return {
        "url": url,
        "status": resp.status_code,
        "elapsed_sec": elapsed,
        "html_bytes": len(resp.content),
        "www_authenticate": auth_scheme,
        "cards_in_html": cards,
        "verdict": verdict,
    }


def run_probe(session: requests.Session, delay: float) -> list[dict]:
    print("== 第 0 步：免验证体检（先判断要不要验证，再决定抓不抓）==\n")
    report = []
    for name, url, desc in PROBE_TARGETS:
        row = probe_one(session, url)
        row["name"] = name
        row["description_verbatim"] = desc  # 案例原文，逐字保留
        report.append(row)
        print(f"[{name}] {url}")
        print(f"     HTTP {row['status']}  耗时 {row['elapsed_sec']}s  {row['html_bytes']} 字节")
        print(f"     → {row['verdict']}\n")
        time.sleep(delay)

    # ssr3 只看状态码就收手：确认它「需要验证」即可，不带用户名密码、不做任何绕过。
    print("结论：ssr1 / ssr4 / spa1 都不需要验证；ssr3 需要 HTTP Basic Auth，不在本作业范围内。")
    print("      本作业的主链路选 ssr1 —— 免验证，且数据直接躺在 HTML 里，一步到位。\n")
    return report


# ---------------------------------------------------------------------------
# 主链路第 1 段：请求
# ---------------------------------------------------------------------------

def fetch(session: requests.Session, url: str) -> str:
    """把一个页面的 HTML 取回来。免验证站点的「请求」就这么朴素：一个 GET。"""
    resp = session.get(url, timeout=30)
    resp.raise_for_status()   # 4xx/5xx 直接抛错，不要把错误页当数据往下解析
    return resp.text


# ---------------------------------------------------------------------------
# 主链路第 2 段：解析
# ---------------------------------------------------------------------------

def text_of(node, selector: str) -> str | None:
    """选中就返回去掉首尾空白的文本，选不中返回 None——避免满屏 if 判空。"""
    hit = node.select_one(selector)
    return hit.get_text(strip=True) if hit else None


def parse_list_page(html: str) -> list[dict]:
    """从列表页 HTML 里抠出每部电影的字段。

    页面用 Element UI 渲染，每部电影是一张 `.el-card.item` 卡片，卡片内部：
        a.name h2            "霸王别姬 - Farewell My Concubine"（名称 - 别名）
        .categories button   类别，可能多个
        .info 第 1 个         "中国内地、中国香港" / "171 分钟"
        .info 第 2 个         "1993-07-26 上映"
        p.score              "9.5"
        a.name[href]         "/detail/1"，末段就是详情页 id
    """
    soup = BeautifulSoup(html, "lxml")
    movies = []

    for card in soup.select(".el-card.item"):
        # 名称与别名同挤在一个 h2 里，用 " - " 分隔；没有别名的片子就只有名称。
        title = text_of(card, "a.name h2") or ""
        name, _, alias = title.partition(" - ")

        # 两行灰色小字：infos[0] = 地区 / 时长，infos[1] = 上映日期。
        # 注意别用 CSS 的 :nth-of-type —— 它数的是「同标签的第几个」，
        # 而卡片里 .categories 也是 div，会把序号顶偏；直接按列表下标取最稳。
        infos = card.select(".m-v-sm.info")
        first_line = [s.get_text(strip=True) for s in infos[0].select("span")] if infos else []
        # 第一行形如 ["中国内地、中国香港", "/", "171 分钟"]，把分隔符 "/" 滤掉
        parts = [p for p in first_line if p and p != "/"]
        regions = parts[0].split("、") if parts else []
        minutes = parts[1] if len(parts) > 1 else None
        # 第二行形如 "1993-07-26 上映"。注意：站上确实有几部片子这一行是空的
        # （如《楚门的世界》），那是数据本身就缺，不是解析错——统一记成 None，别记成 ""。
        published_at = (infos[1].get_text(strip=True) or None) if len(infos) > 1 else None

        href = card.select_one("a.name")["href"] if card.select_one("a.name") else ""

        movies.append({
            "id": href.rsplit("/", 1)[-1] or None,     # "/detail/1" → "1"
            "name": name.strip(),
            "alias": alias.strip() or None,
            "categories": [b.get_text(strip=True) for b in card.select(".categories button")],
            "regions": regions,
            "minutes": minutes,
            "published_at": published_at,
            "score": text_of(card, "p.score"),
            "cover": card.select_one("img.cover")["src"] if card.select_one("img.cover") else None,
            "detail_url": BASE + href if href else None,
        })

    return movies


def parse_detail_page(html: str) -> dict:
    """详情页比列表页多三样：剧情简介、导演、演员。"""
    soup = BeautifulSoup(html, "lxml")
    return {
        "drama": text_of(soup, ".drama p"),
        "directors": [p.get_text(strip=True) for p in soup.select(".directors .director .name")],
        "actors": [p.get_text(strip=True) for p in soup.select(".actors .actor .name")],
    }


# ---------------------------------------------------------------------------
# 主链路第 3 段：落盘
# ---------------------------------------------------------------------------

def save_json(payload, filename: str) -> Path:
    DATA_DIR.mkdir(exist_ok=True)
    path = DATA_DIR / filename
    # ensure_ascii=False：中文按原样写进文件，别存成 中文
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  已落盘 {path.relative_to(Path(__file__).parent)}  ({path.stat().st_size / 1024:.1f} KB)")
    return path


# ---------------------------------------------------------------------------
# 串起来
# ---------------------------------------------------------------------------

def crawl(session: requests.Session, pages: int, detail: int, delay: float) -> list[dict]:
    print(f"== 主链路：抓取 {BASE} 前 {pages} 页 ==\n")
    movies: list[dict] = []

    for page in range(1, pages + 1):
        url = LIST_URL.format(page=page)
        started = time.perf_counter()
        got = parse_list_page(fetch(session, url))       # 请求 → 解析
        movies.extend(got)
        print(f"  第 {page:>2} 页  {len(got):>2} 条  累计 {len(movies):>3} 条  "
              f"({time.perf_counter() - started:.2f}s)  {url}")
        time.sleep(delay)                                # 礼貌间隔，不压测

    if detail:
        print(f"\n  再抓前 {detail} 条的详情页（剧情简介 / 导演 / 演员）：")
        for movie in movies[:detail]:
            html = fetch(session, DETAIL_URL.format(movie_id=movie["id"]))
            movie.update(parse_detail_page(html))
            print(f"    #{movie['id']:>3} {movie['name']}  导演 {'、'.join(movie['directors']) or '—'}  "
                  f"演员 {len(movie['actors'])} 位  简介 {len(movie['drama'] or '')} 字")
            time.sleep(delay)

    return movies


def main() -> int:
    ap = argparse.ArgumentParser(description="不需要验证的网站信息获取（issue #1）")
    ap.add_argument("--probe", action="store_true", help="只做免验证体检，不抓数据")
    ap.add_argument("--pages", type=int, default=10, help="抓列表页前 N 页（ssr1 共 10 页，默认 10）")
    ap.add_argument("--detail", type=int, default=0, help="额外抓前 N 条的详情页（默认 0，不抓）")
    ap.add_argument("--delay", type=float, default=1.0, help="每次请求之间的间隔秒数（默认 1.0）")
    args = ap.parse_args()

    # 一个 Session 复用 TCP 连接，比每次 requests.get() 快，也更礼貌。
    with requests.Session() as session:
        session.headers.update(HEADERS)

        if args.probe:
            save_json(run_probe(session, args.delay), "probe_report.json")
            return 0

        started = time.perf_counter()
        movies = crawl(session, args.pages, args.detail, args.delay)
        elapsed = time.perf_counter() - started

        print(f"\n  共 {len(movies)} 条，用时 {elapsed:.1f}s")
        save_json(movies, "ssr1_movies.json")

        # 抽样打印一条，肉眼确认字段没解析歪
        if movies:
            print("\n  抽样第 1 条：")
            print("   ", json.dumps(movies[0], ensure_ascii=False)[:200], "...")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
