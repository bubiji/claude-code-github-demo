"""阶段 9（JS 混淆对抗）共用层 —— issue #12。

三件事：
  1. 礼貌抓取（串行 + 固定间隔 + 抖动 + 重试退避）
  2. spa8–spa13 共用的 DES-ECB Token 算法（六站同源，只有 key 不同）
  3. 调 Node 侧还原工具 + 落盘（>500KB 自动降级）

刻意不依赖浏览器：全阶段唯一用到 Playwright 的地方是 antispider8 的
debugger 绕过**实证脚本**，抓数据本身一律 requests + Node。
"""

from __future__ import annotations

import base64
import hashlib
import json
import random
import re
import subprocess
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterable

import requests
from Crypto.Cipher import DES
from Crypto.Util.Padding import pad

HERE = Path(__file__).resolve().parent
TOOLS = HERE / "tools"

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

MAX_JSON_BYTES = 500 * 1024


# --------------------------------------------------------------------------
# 1. 传输层
# --------------------------------------------------------------------------
class PoliteSession:
    """串行、限速、带退避的会话。scrape.center 是练习站，别压测。"""

    def __init__(self, interval: float = 1.2, jitter: float = 0.4, retries: int = 3):
        self.interval = interval
        self.jitter = jitter
        self.retries = retries
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": UA})
        self._last = 0.0
        self.count = 0

    def _wait(self) -> None:
        gap = time.time() - self._last
        need = self.interval + random.uniform(0, self.jitter) - gap
        if need > 0:
            time.sleep(need)

    def get(self, url: str, **kw) -> requests.Response:
        last_err: Exception | None = None
        for attempt in range(self.retries):
            self._wait()
            try:
                r = self.s.get(url, timeout=kw.pop("timeout", 30), **kw)
                self._last = time.time()
                self.count += 1
                if r.status_code >= 500:
                    raise requests.HTTPError(f"HTTP {r.status_code}")
                self._fix_encoding(r)
                return r
            except Exception as e:          # noqa: BLE001 —— 重试层，什么都得接住
                last_err = e
                self._last = time.time()
                time.sleep(1.5 * (2 ** attempt))
        raise RuntimeError(f"GET {url} 连续 {self.retries} 次失败: {last_err}")

    @staticmethod
    def _fix_encoding(r: requests.Response) -> None:
        """响应头没写 charset 时，别让 requests 按 RFC 猜成 ISO-8859-1。

        这不是洁癖，是这一阶段真踩到的坑：spa8 的响应头是 `Content-Type: text/html`
        **不带 charset**，页面里写的是 `<meta charset="UTF-8">`。requests 遵照
        RFC 2616 把 text/* 默认当 ISO-8859-1，于是 `r.text` 里的「凯文-杜兰特」
        变成「å¯æ-æå°ç¹」。

        而这个坑格外阴险的地方是：**它能骗过 token 对照**。
        Python 用乱码名算 DES，Node 参照实现也拿到同一份乱码名，两边算出来一模一样，
        「16/16 一致」照亮绿灯 —— 一致的是两个都错的结果。
        只有把 data/*.json 打开看一眼中文，才发现 spa8 与 spa10 的同一个球员名字不一样。
        教训：跨实现对照能证明「复刻对了算法」，证明不了「喂进去的输入是对的」。
        """
        if "charset" not in (r.headers.get("Content-Type") or "").lower():
            r.encoding = "utf-8"


# --------------------------------------------------------------------------
# 2. spa8–spa13 的 Token 算法（同源）
# --------------------------------------------------------------------------
@dataclass
class Player:
    name: str
    image: str
    birthday: str
    height: str
    weight: str
    token: str = ""


def des_token(site_key: str, name: str, birthday: str, height: str, weight: str) -> str:
    """复刻 spa8–spa13 前端的 getToken()。

    对应的 JS 原文（六站还原后逐字一致，只有 this.key 不同）：

        getToken(player) {
          let key = CryptoJS.enc.Utf8.parse(this.key);
          const { name, birthday, height, weight } = player;
          let base64Name = CryptoJS.enc.Base64.stringify(CryptoJS.enc.Utf8.parse(name));
          let encrypted = CryptoJS.DES.encrypt(
            `${base64Name}${birthday}${height}${weight}`, key,
            { mode: CryptoJS.mode.ECB, padding: CryptoJS.pad.Pkcs7 });
          return encrypted.toString();
        }

    两处容易踩空的对齐点：

    * **key 只取前 8 字节。** 站点的 key 是 35 个字符，而 DES 的密钥就是 64 bit。
      CryptoJS 的 DES 实现只读 WordArray 的前两个 word，多出来的 27 字节被静默丢弃。
      直接把 35 字节喂给 pycryptodome 会抛 ValueError —— 那不是算法不对，是没照抄这条静默截断。
    * **`encrypted.toString()` 不是 OpenSSL 的 "Salted__" 格式。** 只有用口令派生密钥时
      CryptoJS 才会加盐前缀；这里传的是 WordArray 密钥，没有 salt，输出就是密文的裸 Base64。
    """
    b64_name = base64.b64encode(name.encode("utf-8")).decode("ascii")
    plain = f"{b64_name}{birthday}{height}{weight}".encode("utf-8")
    cipher = DES.new(site_key.encode("utf-8")[:8], DES.MODE_ECB)
    return base64.b64encode(cipher.encrypt(pad(plain, DES.block_size))).decode("ascii")


def build_players(site_key: str, raw: Iterable[dict[str, Any]]) -> list[Player]:
    out = []
    for p in raw:
        out.append(
            Player(
                name=p["name"],
                image=p["image"],
                birthday=p["birthday"],
                height=p["height"],
                weight=p["weight"],
                token=des_token(site_key, p["name"], p["birthday"], p["height"], p["weight"]),
            )
        )
    return out


# --------------------------------------------------------------------------
# 3. Node 侧工具封装
# --------------------------------------------------------------------------
def _node(script: Path, *args: str) -> tuple[str, str]:
    proc = subprocess.run(
        ["node", str(script), *args],
        capture_output=True, text=True, check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"node {script.name} 失败:\n{proc.stderr}")
    return proc.stdout, proc.stderr


def unwrap(src_file: Path, out_file: Path) -> str:
    """JJEncode / AAEncode / JSFuck / eval-packer 通用还原（tools/unwrap.js）。"""
    _, log = _node(TOOLS / "unwrap.js", str(src_file), "--out", str(out_file))
    return log.strip()


def strarray(src_file: Path, out_file: Path) -> str:
    """javascript-obfuscator 字符串数组还原（tools/strarray.js）。"""
    _, log = _node(TOOLS / "strarray.js", str(src_file), "--out", str(out_file))
    return log.strip()


def extract_vue(src_file: Path) -> dict[str, Any]:
    """把还原后的 main.js 丢进 Node，用桩件接住 `new Vue({...})`，取出 key 与 players。

    为什么不用正则去抠：还原后的代码格式各站不一（有的压成一行、有的有转义），
    正则抠字段是「看着像就算」；跑一遍再接住 data() 的返回值，拿到的是**代码自己算出来的值**。
    """
    out, _ = _node(TOOLS / "extract.js", str(src_file))
    return json.loads(out)


def verify_with_cryptojs(site_key: str, player: dict[str, Any]) -> str:
    """用站点自带的 crypto-js.min.js 在 Node 里算一次 token，作为 Python 实现的对照基准。"""
    out, _ = _node(TOOLS / "reftoken.js", site_key, json.dumps(player, ensure_ascii=False))
    return out.strip()


# --------------------------------------------------------------------------
# 4. 落盘
# --------------------------------------------------------------------------
def save_json(path: Path, payload: Any, *, sample_key: str | None = None) -> Path:
    """写 JSON；超过 500KB 时降级为「前 100 条 + 统计摘要」。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if len(text.encode("utf-8")) > MAX_JSON_BYTES and sample_key:
        items = payload[sample_key]
        payload = dict(payload)
        payload[sample_key] = items[:100]
        payload["_truncated"] = {
            "reason": f">{MAX_JSON_BYTES} bytes，按仓库规则降级",
            "total": len(items),
            "kept": min(100, len(items)),
        }
        text = json.dumps(payload, ensure_ascii=False, indent=2)
    path.write_text(text, encoding="utf-8")
    return path


def dump_players(path: Path, site: str, site_key: str, players: list[Player], extra: dict | None = None) -> Path:
    payload: dict[str, Any] = {
        "site": site,
        "site_key": site_key,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S %z"),
        "count": len(players),
        "players": [asdict(p) for p in players],
    }
    if extra:
        payload.update(extra)
    return save_json(path, payload, sample_key="players")


def head(text: str, n: int = 400) -> str:
    """取片段用于 README 里的「还原前」展示。"""
    t = re.sub(r"\s+", " ", text[:n]).strip()
    return t
