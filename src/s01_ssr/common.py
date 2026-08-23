#!/usr/bin/env python3
"""阶段 1（SSR）四个案例的共用逻辑 —— 解析、翻页调度、落盘、统计。

issue: #4 · 案例来源: https://scrape.center/

ssr1/ssr2/ssr3/ssr4 是同一套电影站的四种连接层变体（普通 / 证书 / Basic Auth /
5 秒延迟），页面结构完全一致，所以「解析 + 调度 + 落盘」这层只写一份，各案例
只提供自己的 `fetch(url) -> str`（带证书开关、认证、并发参数），别的都复用。

各案例 crawl.py 用法：

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from common import crawl, save_dataset
"""
from __future__ import annotations

import csv
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

from bs4 import BeautifulSoup

# ---------------------------------------------------------------- 解析

DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
MINUTE_RE = re.compile(r"(\d+)\s*分钟")
DETAIL_ID_RE = re.compile(r"/detail/(\d+)")


def _text(node) -> str:
    return node.get_text(strip=True) if node else ""


def _parse_info_lines(scope) -> dict:
    """两行 `div.info` 里混着地区 / 时长 / 上映日期，按内容形态归类，不靠位置。

    页面上是这样的（ssr1 detail/1）：
        <div class="info"><span>中国内地、中国香港</span><span> / </span><span>171 分钟</span></div>
        <div class="info"><span>1993-07-26 上映</span></div>
    但并非每部电影三样都全（有的没时长、有的没上映日期），所以按正则判形态。
    """
    regions: list[str] = []
    minutes = None
    published_at = None

    for div in scope.select("div.info"):
        for span in div.find_all("span", recursive=False) or div.find_all("span"):
            s = span.get_text(strip=True)
            if not s or s == "/":
                continue
            if m := MINUTE_RE.search(s):
                minutes = int(m.group(1))
            elif m := DATE_RE.search(s):
                published_at = m.group(0)
            else:
                regions.extend(p.strip() for p in s.split("、") if p.strip())

    # 去重保序
    seen, uniq = set(), []
    for r in regions:
        if r not in seen:
            seen.add(r)
            uniq.append(r)
    return {"regions": uniq, "minutes": minutes, "published_at": published_at}


def _split_title(title: str) -> tuple[str, str | None]:
    """站上标题形如「霸王别姬 - Farewell My Concubine」，拆成中英两个字段（原标题另存）。"""
    if " - " in title:
        cn, _, en = title.partition(" - ")
        return cn.strip(), en.strip()
    return title.strip(), None


def parse_list_page(html: str) -> list[dict]:
    """列表页 → 每部电影的概览字段（含详情页 id）。"""
    soup = BeautifulSoup(html, "lxml")
    movies = []
    for card in soup.select("div.el-card.item"):
        link = card.select_one("a.name")
        href = link["href"] if link and link.has_attr("href") else ""
        m = DETAIL_ID_RE.search(href)
        title = _text(card.select_one("a.name h2"))
        name_cn, name_en = _split_title(title)
        cover = card.select_one("img.cover")
        score = _text(card.select_one("p.score"))
        movies.append({
            "id": int(m.group(1)) if m else None,
            "title": title,
            "name_cn": name_cn,
            "name_en": name_en,
            "categories": [_text(b) for b in card.select("button.category span")],
            **_parse_info_lines(card),
            "score": float(score) if score else None,
            "cover": cover["src"] if cover and cover.has_attr("src") else None,
            "detail_path": href or None,
        })
    return movies


def parse_detail_page(html: str) -> dict:
    """详情页 → 概览字段 + 剧情简介 + 导演 + 演员表。"""
    soup = BeautifulSoup(html, "lxml")
    detail = soup.select_one("div#detail") or soup
    title = _text(detail.select_one("h2.m-b-sm"))
    name_cn, name_en = _split_title(title)
    score = _text(detail.select_one("p.score"))
    cover = detail.select_one("img.cover")

    actors = []
    for a in detail.select("div.actor"):
        role = _text(a.select_one("p.role"))
        actors.append({
            "name": _text(a.select_one("p.name")),
            # 原文是「饰：程蝶衣」，只去掉前缀，角色名本身不动
            "role": role.split("：", 1)[1] if "：" in role else (role or None),
        })

    return {
        "title": title,
        "name_cn": name_cn,
        "name_en": name_en,
        "categories": [_text(b) for b in detail.select("button.category span")],
        **_parse_info_lines(detail),
        "score": float(score) if score else None,
        "cover": cover["src"] if cover and cover.has_attr("src") else None,
        "drama": _text(detail.select_one("div.drama p")) or None,
        "directors": [_text(d.select_one("p.name")) for d in detail.select("div.director")],
        "actors": actors,
    }


FIELD_ORDER = [
    "id", "title", "name_cn", "name_en", "categories", "regions", "minutes",
    "published_at", "score", "directors", "actors", "drama", "cover",
    "detail_url",
]


def merge(list_item: dict, detail: dict | None, base: str) -> dict:
    """列表页字段 + 详情页字段 → 一条完整记录（详情页缺字段时回落到列表页）。"""
    rec = dict(list_item)
    if detail:
        for k, v in detail.items():
            if v not in (None, [], ""):
                rec[k] = v
    rec["detail_url"] = f"{base}{rec.pop('detail_path', '') or ''}"
    return {k: rec.get(k) for k in FIELD_ORDER}


# ---------------------------------------------------------------- 调度

@dataclass
class CrawlStats:
    """真实跑出来的数字，README / issue 评论里的耗时都取自这里，不手写。"""
    pages: int = 0
    details: int = 0
    requests: int = 0
    failures: list[str] = field(default_factory=list)
    elapsed_pages: float = 0.0
    elapsed_details: float = 0.0
    request_times: list[float] = field(default_factory=list)

    @property
    def elapsed(self) -> float:
        return self.elapsed_pages + self.elapsed_details

    @property
    def avg_request(self) -> float:
        return sum(self.request_times) / len(self.request_times) if self.request_times else 0.0

    @property
    def serial_estimate(self) -> float:
        """若完全串行、单请求耗时取本次实测均值，总共要多久（用于并发效果对比）。"""
        return self.avg_request * self.requests

    def as_dict(self) -> dict:
        return {
            "pages": self.pages,
            "details": self.details,
            "requests": self.requests,
            "failures": self.failures,
            "elapsed_sec": round(self.elapsed, 2),
            "elapsed_pages_sec": round(self.elapsed_pages, 2),
            "elapsed_details_sec": round(self.elapsed_details, 2),
            "avg_request_sec": round(self.avg_request, 2),
            "serial_estimate_sec": round(self.serial_estimate, 2),
        }


Fetch = Callable[[str], str]
"""fetch(url) -> html；抛异常表示该 url 失败。返回 "" 视为「翻到头了」。"""


def _timed(fetch: Fetch, url: str, stats: CrawlStats) -> str:
    t0 = time.perf_counter()
    try:
        return fetch(url)
    finally:
        dt = time.perf_counter() - t0
        stats.request_times.append(dt)
        stats.requests += 1


def _map(fn: Callable, items: Iterable, workers: int) -> list:
    items = list(items)
    if workers <= 1:
        return [fn(x) for x in items]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(fn, items))


def crawl(
    base: str,
    fetch: Fetch,
    *,
    workers: int = 1,
    delay: float = 0.0,
    max_pages: int = 50,
    with_detail: bool = True,
    log: Callable[[str], None] = print,
) -> tuple[list[dict], CrawlStats]:
    """翻完列表页 → 逐个抓详情页 → 合并成完整记录。

    翻页终止条件：某页解析出 0 条（本站第 11 页直接 HTTP 500，见各 README「坑」一节，
    由各案例的 fetch 把它转成 ""）。workers>1 时按批并发，批内出现空页即停止。
    """
    stats = CrawlStats()
    listed: list[dict] = []

    t0 = time.perf_counter()
    page = 1
    batch = max(1, workers)
    done = False
    while not done and page <= max_pages:
        nums = list(range(page, min(page + batch, max_pages + 1)))
        htmls = _map(lambda n: _timed(fetch, f"{base}/page/{n}", stats), nums, workers)
        for n, html in zip(nums, htmls):
            items = parse_list_page(html) if html else []
            if not items:
                log(f"  page {n}: 0 条 → 翻页结束")
                done = True
                break
            stats.pages += 1
            listed.extend(items)
            log(f"  page {n}: {len(items)} 条")
        page = nums[-1] + 1
        if delay and not done:
            time.sleep(delay)
    stats.elapsed_pages = time.perf_counter() - t0

    if not with_detail:
        return [merge(it, None, base) for it in listed], stats

    t0 = time.perf_counter()

    def one(item: dict) -> dict:
        url = f"{base}{item['detail_path']}"
        try:
            detail = parse_detail_page(_timed(fetch, url, stats))
        except Exception as exc:  # 单条失败不拖垮整轮，记录后回落到列表页字段
            stats.failures.append(f"{url}: {type(exc).__name__}: {exc}")
            detail = None
        else:
            stats.details += 1
        if delay:
            time.sleep(delay)
        return merge(item, detail, base)

    records = _map(one, listed, workers)
    records.sort(key=lambda r: r["id"] or 0)
    stats.elapsed_details = time.perf_counter() - t0
    return records, stats


# ---------------------------------------------------------------- 落盘

MAX_BYTES = 500 * 1024
"""单文件超过 500KB 就只落前 100 条（另有统计摘要兜住全量口径）。"""


def build_summary(records: list[dict], stats: CrawlStats, meta: dict) -> dict:
    scores = [r["score"] for r in records if r.get("score") is not None]
    minutes = [r["minutes"] for r in records if r.get("minutes")]
    cats: dict[str, int] = {}
    regions: dict[str, int] = {}
    for r in records:
        for c in r.get("categories") or []:
            cats[c] = cats.get(c, 0) + 1
        for g in r.get("regions") or []:
            regions[g] = regions.get(g, 0) + 1
    years: dict[str, int] = {}
    for r in records:
        if r.get("published_at"):
            y = r["published_at"][:4]
            years[y] = years.get(y, 0) + 1
    return {
        **meta,
        "count": len(records),
        "fields": FIELD_ORDER,
        "completeness": {
            k: sum(1 for r in records if r.get(k) not in (None, [], ""))
            for k in FIELD_ORDER
        },
        "score": {
            "min": min(scores) if scores else None,
            "max": max(scores) if scores else None,
            "avg": round(sum(scores) / len(scores), 3) if scores else None,
        },
        "minutes": {
            "min": min(minutes) if minutes else None,
            "max": max(minutes) if minutes else None,
            "avg": round(sum(minutes) / len(minutes), 1) if minutes else None,
        },
        "categories": dict(sorted(cats.items(), key=lambda kv: -kv[1])),
        "regions": dict(sorted(regions.items(), key=lambda kv: -kv[1])),
        "years": dict(sorted(years.items())),
        "run": stats.as_dict(),
    }


def _csv_value(v):
    if isinstance(v, list):
        if v and isinstance(v[0], dict):  # actors
            return "; ".join(f"{a.get('name')}({a.get('role')})" for a in v)
        return "、".join(str(x) for x in v)
    return v


def _dump(records: list[dict]) -> str:
    """一行一条记录的 JSON 数组：既是合法 JSON，又能逐行读/逐行 diff。

    换成 indent=2 会把 ssr1 这份 100 条的数据从 494KB 撑到 703KB（演员表平均 57 人，
    缩进全花在方括号上），直接顶穿 500KB 落盘上限，所以这里用紧凑分隔符 + 手工换行。
    """
    body = ",\n  ".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) for r in records)
    return f"[\n  {body}\n]\n" if records else "[]\n"


def save_dataset(outdir: Path, name: str, records: list[dict], summary: dict,
                 *, write_csv: bool = True) -> dict:
    """写 <name>.json（+ 可选 <name>.csv）+ <name>.summary.json，返回实际落盘信息。"""
    outdir.mkdir(parents=True, exist_ok=True)
    blob = _dump(records)
    truncated = len(blob.encode()) > MAX_BYTES
    kept = records[:100] if truncated else records
    if truncated:
        blob = _dump(kept)

    summary = {**summary, "truncated": truncated,
               "total_records": len(records), "saved_records": len(kept)}
    (outdir / f"{name}.json").write_text(blob, encoding="utf-8")
    (outdir / f"{name}.summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    csv_bytes = None
    if write_csv:
        with (outdir / f"{name}.csv").open("w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=FIELD_ORDER)
            w.writeheader()
            for r in kept:
                w.writerow({k: _csv_value(r.get(k)) for k in FIELD_ORDER})
        csv_bytes = (outdir / f"{name}.csv").stat().st_size

    return {
        "json_bytes": (outdir / f"{name}.json").stat().st_size,
        "csv_bytes": csv_bytes,
        "truncated": truncated,
        "saved_records": len(kept),
    }


def report(name: str, records: list[dict], stats: CrawlStats, saved: dict,
           log: Callable[[str], None] = print, workers: int = 1) -> None:
    log("")
    log(f"[{name}] 抓取完成")
    log(f"  记录数     : {len(records)}（列表页 {stats.pages} 页 / 详情页 {stats.details} 个）")
    log(f"  请求数     : {stats.requests}，失败 {len(stats.failures)}")
    log(f"  单请求均值 : {stats.avg_request:.2f}s")
    log(f"  总耗时     : {stats.elapsed:.2f}s"
        f"（列表 {stats.elapsed_pages:.2f}s + 详情 {stats.elapsed_details:.2f}s）")
    if workers <= 1:
        # 并发跑时这个均值里含排队等待，拿它外推串行耗时会离谱地高（ssr4 实测
        # 均值 11.17s 而无排队单请求只要 5.93s），所以只在串行时报这一行；
        # 并发下的串行对照由各案例自己用「无排队基线 × 请求数」给（见 ssr4）。
        log(f"  串行预估   : {stats.serial_estimate:.2f}s"
            f"（{stats.requests} 请求 × 均值 {stats.avg_request:.2f}s）")
    csv_part = (f"{name}.csv {saved['csv_bytes'] / 1024:.1f}KB / "
                if saved.get("csv_bytes") else "")
    log(f"  落盘       : {name}.json {saved['json_bytes'] / 1024:.1f}KB / "
        f"{csv_part}{name}.summary.json"
        + ("（超 500KB，已截断到前 100 条）" if saved["truncated"] else ""))
    for f in stats.failures[:5]:
        log(f"  ! {f}")


def add_common_args(ap):
    ap.add_argument("--workers", type=int, default=1, help="并发线程数（1 = 串行）")
    ap.add_argument("--delay", type=float, default=0.3, help="每个请求后的礼貌间隔（秒）")
    ap.add_argument("--timeout", type=float, default=30.0, help="单请求超时（秒）")
    ap.add_argument("--no-detail", action="store_true", help="只抓列表页，不进详情页")
    ap.add_argument("--out", default=None, help="落盘目录（默认脚本同级 data/）")
    return ap
