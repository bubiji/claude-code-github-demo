"""阶段 4（基础反爬）共用工具。

issue: #7 · 阶段: s04_antispider_basic
"""
from __future__ import annotations

import json
import os
import time

import requests

# 一个普通桌面浏览器 UA：阶段 4 里 antispider2 就靠它过关
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# 礼貌抓取：每次请求之间至少间隔这么久（秒）
POLITE_INTERVAL = 1.0

_last_request_at = 0.0


def polite_sleep(interval: float = POLITE_INTERVAL) -> None:
    """保证两次请求之间至少间隔 interval 秒。"""
    global _last_request_at
    gap = time.time() - _last_request_at
    if gap < interval:
        time.sleep(interval - gap)
    _last_request_at = time.time()


def get(url: str, *, ua: str | None = BROWSER_UA, **kwargs):
    """带 UA、带间隔的 GET。"""
    headers = dict(kwargs.pop("headers", {}))
    if ua is not None:
        headers.setdefault("User-Agent", ua)
    kwargs.setdefault("timeout", 20)
    polite_sleep()
    return requests.get(url, headers=headers, **kwargs)


def data_dir(case_file: str) -> str:
    """<案例目录>/data，不存在就建。"""
    d = os.path.join(os.path.dirname(os.path.abspath(case_file)), "data")
    os.makedirs(d, exist_ok=True)
    return d


def dump_json(obj, path: str, *, sample_limit: int = 100) -> str:
    """落盘 JSON；>500KB 时降级为「前 sample_limit 条 + 统计摘要」。

    返回实际写入的文件路径。
    """
    text = json.dumps(obj, ensure_ascii=False, indent=2)
    if len(text.encode("utf-8")) <= 500 * 1024 or not isinstance(obj, list):
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    sample = {
        "_note": f"原始 {len(obj)} 条超过 500KB，降级为前 {sample_limit} 条 + 统计摘要",
        "total": len(obj),
        "sample_size": min(sample_limit, len(obj)),
        "results": obj[:sample_limit],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sample, f, ensure_ascii=False, indent=2)
    return path
