"""spa8–spa13 共用流水线 —— issue #12。

六个站是**同一套 NBA 数据站的六个混淆变体**：页面结构、数据字段、Token 算法
全部相同，唯一的区别是 ① 混淆手法 ② 那把 35 字符的 site key。
所以抓取逻辑只有这一份，各案例的 `spider.py` 只是「填参数 + 调用」。

一条流水线五步，每步都落存证：

    ① 取原件      → evidence/before.<ext>      （站点下发的混淆源码，逐字节原样）
    ② 还原        → evidence/after.js          （tools/unwrap.js 或 tools/strarray.js）
    ③ 取值        → tools/extract.js           （假 Vue 接住 new Vue(...) 的 data()）
    ④ 对照        → tools/reftoken.js vs Python（16/16 逐字节一致才算复刻成功）
    ⑤ 落盘        → data/<site>_players.json

第 ④ 步是整条线的验收关：没有它，「我按还原后的代码写了 Python」只是自我感觉良好。
"""

from __future__ import annotations

import json
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import common


@dataclass
class SiteSpec:
    site: str                    # "spa8"
    obf: str                     # "none" | "unwrap" | "strarray"
    source: str                  # "inline" | "main.js"
    label: str                   # 混淆手法中文名，写进报告
    before_ext: str = "js"

    @property
    def base(self) -> str:
        return f"https://{self.site}.scrape.center"


def _pick_inline_script(html: str) -> str:
    """从 HTML 里挑出「装着业务逻辑的那个 <script>」。

    判据不是「最后一个」也不是「最长的」，而是**内容里出现 getToken 或 eval(function(p,a,c,k,e,r**
    —— 页面里还有 vue.min.js / element-ui.js 这些外链 script，内联的只有一个。
    """
    blocks = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)</script>", html)
    for b in blocks:
        if "getToken" in b or "p,a,c,k,e,r" in b:
            return b.strip()
    if blocks:
        return blocks[-1].strip()
    raise RuntimeError("页面里没有内联 <script>")


def run(spec: SiteSpec, case_dir: Path) -> dict:
    ev = case_dir / "evidence"
    ev.mkdir(parents=True, exist_ok=True)
    data_dir = case_dir / "data"
    sess = common.PoliteSession()
    report: dict = {"site": spec.site, "obfuscation": spec.label, "steps": []}

    def step(msg: str) -> None:
        report["steps"].append(msg)
        print(f"  {msg}", flush=True)

    print(f"[{spec.site}] {spec.label}")

    # ---------- ① 取原件 ----------
    html = sess.get(spec.base + "/").text
    (ev / "index.html").write_text(html, encoding="utf-8")
    step(f"① GET {spec.base}/ → evidence/index.html ({len(html.encode())} bytes)")

    if spec.source == "inline":
        obf_src = _pick_inline_script(html)
        origin = f"{spec.base}/  （HTML 内联 <script>）"
    else:
        obf_src = sess.get(spec.base + "/js/main.js").text
        origin = f"{spec.base}/js/main.js"
    before = ev / f"before.{spec.before_ext}"
    before.write_text(obf_src, encoding="utf-8")
    step(f"① 混淆原件 ← {origin} → evidence/{before.name} ({len(obf_src.encode())} bytes)")
    report["before_bytes"] = len(obf_src.encode())
    report["origin"] = origin

    # ---------- ② 还原 ----------
    after = ev / "after.js"
    if spec.obf == "unwrap":
        log = common.unwrap(before, after)
    elif spec.obf == "strarray":
        log = common.strarray(before, after)
    else:                                   # 站点当前下发的就是可读源码，不需要还原
        after.write_text(obf_src, encoding="utf-8")
        log = "（无需还原：站点当前下发的即为未混淆源码，见本案例 README）"
    step(f"② 还原 → evidence/after.js ({after.stat().st_size} bytes)")
    for line in log.splitlines():
        step(f"   {line}")
    report["after_bytes"] = after.stat().st_size
    report["deobf_log"] = log

    # ---------- ③ 取值 ----------
    got = common.extract_vue(after)
    site_key, raw_players = got["key"], got["players"]
    step(f"③ 取值：site key = {site_key!r}，players = {len(raw_players)} 人")
    report["site_key"] = site_key
    report["player_count"] = len(raw_players)

    # ---------- ④ 对照 ----------
    players = common.build_players(site_key, raw_players)
    mismatch = []
    for p in players:
        ref = common.verify_with_cryptojs(
            site_key,
            {"name": p.name, "birthday": p.birthday, "height": p.height, "weight": p.weight},
        )
        if ref != p.token:
            mismatch.append({"name": p.name, "python": p.token, "cryptojs": ref})
    ok = f"{len(players) - len(mismatch)}/{len(players)}"
    step(f"④ Python DES ←→ 站点 crypto-js 逐字节比对：{ok} 一致")
    if mismatch:
        step(f"   ✗ 不一致 {len(mismatch)} 条：{mismatch[:2]}")
    report["token_crosscheck"] = {"matched": len(players) - len(mismatch), "total": len(players)}
    report["mismatch"] = mismatch

    # ---------- ⑤ 落盘 ----------
    out = common.dump_players(
        data_dir / f"{spec.site}_players.json",
        spec.site, site_key, players,
        extra={
            "obfuscation": spec.label,
            "obfuscated_source": origin,
            "token_algorithm": "DES/ECB/PKCS7(key=site_key[:8]) over base64(name)+birthday+height+weight, output=base64(ciphertext)",
            "token_crosscheck_vs_site_cryptojs": f"{ok} 一致",
            "browser_used": False,
        },
    )
    step(f"⑤ 落盘 → {out.relative_to(case_dir)} ({out.stat().st_size} bytes)")

    (ev / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report


def determinism_probe(spec: SiteSpec, case_dir: Path, gap: int = 0) -> dict:
    """跑两次（可隔 gap 秒），证明 token 不含时间因子、结果可复现。

    spa8–spa13 的 token 是**纯函数**（无时间戳、无随机数），所以「隔一段时间跑两次」
    的预期是**两次输出逐字节相同**；这和 antispider8 那种带 unix 时间戳的 token 恰好相反，
    那边的预期是「两次 token 不同但两次都能拿到 200」。两种情况都要跑，才叫说清楚了。
    """
    first = run(spec, case_dir)
    if gap:
        print(f"  ⏱ 等待 {gap}s 后复跑…", flush=True)
        time.sleep(gap)
    data_file = case_dir / "data" / f"{spec.site}_players.json"
    tokens_1 = [p["token"] for p in json.loads(data_file.read_text(encoding="utf-8"))["players"]]
    second = run(spec, case_dir)
    tokens_2 = [p["token"] for p in json.loads(data_file.read_text(encoding="utf-8"))["players"]]
    same = tokens_1 == tokens_2
    print(f"  🔁 两次运行 token 全等: {same}（{len(tokens_1)} 条）", flush=True)
    return {"first": first, "second": second, "identical": same}


def main(spec: SiteSpec, case_dir: Path) -> int:
    gap = 0
    if "--twice" in sys.argv:
        i = sys.argv.index("--twice")
        gap = int(sys.argv[i + 1]) if len(sys.argv) > i + 1 and sys.argv[i + 1].isdigit() else 30
        determinism_probe(spec, case_dir, gap)
    else:
        rep = run(spec, case_dir)
        if rep["mismatch"]:
            return 1
    return 0
