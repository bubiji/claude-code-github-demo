#!/usr/bin/env python3
"""spa7 —— 纯前端渲染 + DES 加密 Token，脱离浏览器还原。

issue: #11 · 案例: spa7 · 来源: https://spa7.scrape.center

做法：
1. 纯 HTTP 拉 https://spa7.scrape.center/js/main.js（不开浏览器）；
2. 从 main.js 里解析出 16 名球员数据与 DES 密钥（不硬编码，密钥变了就跟着变）；
3. 用本目录 des.py（纯 Python，零依赖）复现 getToken：
       DES-ECB/PKCS7( base64(name) + birthday + height + weight, key[:8] ) → base64
4. 用站点自己的 crypto-js.min.js 在 Node 里跑一遍同样的 getToken 做交叉验证，逐条比对。

跑法：
    ../../../.venv/bin/python spider.py
"""
import base64
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone

import requests

from des import des_ecb_encrypt

BASE = 'https://spa7.scrape.center'
MAIN_JS = f'{BASE}/js/main.js'
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, 'data')
UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')


def fetch_main_js() -> str:
    r = requests.get(MAIN_JS, headers={'User-Agent': UA}, timeout=20)
    r.raise_for_status()
    r.encoding = 'utf-8'
    return r.text


def parse_main_js(src: str):
    """从 main.js 抠出球员数组与 DES 密钥。"""
    key_m = re.search(r"key:\s*'([^']+)'", src)
    if not key_m:
        raise RuntimeError('main.js 里找不到 key，站点结构可能变了')
    key = key_m.group(1)

    players = []
    for block in re.findall(r'\{\s*name:.*?\}', src, re.S):
        fields = dict(re.findall(r"(\w+):\s*'([^']*)'", block))
        if {'name', 'birthday', 'height', 'weight'} <= set(fields):
            players.append({k: fields[k] for k in ('name', 'image', 'birthday', 'height', 'weight')})
    if not players:
        raise RuntimeError('main.js 里没解析出球员，站点结构可能变了')
    return key, players


def get_token(player: dict, key: str) -> str:
    """main.js getToken 的 Python 等价实现。"""
    base64_name = base64.b64encode(player['name'].encode('utf-8')).decode()
    plaintext = f"{base64_name}{player['birthday']}{player['height']}{player['weight']}"
    ct = des_ecb_encrypt(plaintext.encode('utf-8'), key.encode('utf-8'))
    return base64.b64encode(ct).decode()


def node_cross_check(key: str, players: list):
    """用站点自己的 crypto-js.min.js 在 Node 里算一遍，返回 {name: token} 或 None。"""
    payload = os.path.join(DATA, '_node_input.json')
    with open(payload, 'w', encoding='utf-8') as f:
        json.dump({'key': key, 'players': players}, f, ensure_ascii=False)
    try:
        out = subprocess.run(['node', os.path.join(HERE, 'verify_with_node.js'), payload],
                             capture_output=True, text=True, timeout=60)
    except FileNotFoundError:
        print('  [warn] 没找到 node，跳过交叉验证')
        return None
    finally:
        pass
    if out.returncode != 0:
        print('  [warn] node 交叉验证失败:', out.stderr.strip()[:300])
        return None
    os.remove(payload)
    return json.loads(out.stdout)


def probe_no_api():
    """证明「数据纯前端渲染」：站点没有任何数据接口，所有路径都被 SPA 兜底成同一份 index.html。"""
    print('\n[有没有接口] 探几个常见路径')
    rows = []
    for p in ('api/player', 'api/players', 'api/nba', 'api/token', 'api', 'api/movie'):
        r = requests.get(f'{BASE}/{p}', headers={'User-Agent': UA}, timeout=15)
        rows.append({'path': '/' + p, 'status': r.status_code,
                     'bytes': len(r.content), 'content_type': r.headers.get('content-type')})
        print(f'  /{p:<12} HTTP {r.status_code}  {len(r.content)} 字节  {r.headers.get("content-type")}')
        time.sleep(0.4)
    sizes = {x['bytes'] for x in rows}
    print(f'  → {len(rows)} 个路径返回 {len(sizes)} 种响应体大小 {sizes}；'
          f'{"确认没有数据接口，数据只在 main.js 里" if len(sizes) == 1 else "有路径返回了不一样的东西，值得跟进"}')
    return rows


def main():
    os.makedirs(DATA, exist_ok=True)
    started = datetime.now(timezone.utc).astimezone()
    print(f'[{started.isoformat(timespec="seconds")}] GET {MAIN_JS}')
    src = fetch_main_js()
    key, players = parse_main_js(src)
    print(f'  解析到 {len(players)} 名球员，DES 密钥 {key!r}（长度 {len(key)}，DES 实际只用前 8 字节 {key[:8]!r}）')

    rows = []
    for p in players:
        rows.append(dict(p, token=get_token(p, key)))
    print(f'  纯 Python DES 生成 {len(rows)} 个 Token，首个：{rows[0]["name"]} -> {rows[0]["token"]}')

    ref = node_cross_check(key, players)
    matched = None
    if ref is not None:
        matched = sum(1 for r in rows if ref.get(r['name']) == r['token'])
        print(f'  与站点自带 crypto-js（Node 执行）比对：{matched}/{len(rows)} 完全一致')
        for r in rows:
            if ref.get(r['name']) != r['token']:
                print('  [MISMATCH]', r['name'], r['token'], ref.get(r['name']))

    api_probe = probe_no_api()

    result = {
        'run_at': started.isoformat(timespec='seconds'),
        'source': MAIN_JS,
        'api_probe': api_probe,
        'algorithm': 'base64( DES-ECB-PKCS7( base64(name)+birthday+height+weight, key[:8] ) )',
        'key': key,
        'key_bytes_used': key[:8],
        'node_cross_check_matched': matched,
        'count': len(rows),
        'players': rows,
    }
    out = os.path.join(DATA, 'spa7_players_tokens.json')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f'  落盘 {out}（{os.path.getsize(out)} 字节）')

    log = os.path.join(DATA, 'spa7_runs.json')
    runs = json.load(open(log, encoding='utf-8')) if os.path.exists(log) else []
    runs.append({'run_at': started.isoformat(timespec='seconds'),
                 'count': len(rows),
                 'node_cross_check_matched': matched,
                 'first_token': rows[0]['token']})
    with open(log, 'w', encoding='utf-8') as f:
        json.dump(runs, f, ensure_ascii=False, indent=2)
    print(f'  本次为第 {len(runs)} 次运行，记录追加到 {log}')
    if matched is not None and matched != len(rows):
        sys.exit(1)


if __name__ == '__main__':
    main()
