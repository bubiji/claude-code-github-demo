#!/usr/bin/env python3
"""spa2 —— Ajax 接口签名参数（token）逆向，脱离浏览器直连接口。

issue: #11 · 案例: spa2 · 来源: https://spa2.scrape.center

算法（逆向自 chunk-4136500c 模块 "7d92"，原文见 evidence/）：

    token = base64( sha1( ",".join([*args, t]) ) + "," + t )        t = 当前 Unix 秒

    列表页 args = ["/api/movie", offset]
    详情页 args = ["/api/movie/{key}", 0]       key = base64(salt + id)

零第三方加密依赖：sha1 用 hashlib，base64 用 base64，t 用 time.time()——
所以**每次运行都是现算**，不存在硬编码 token 过期的问题。

跑法：
    ../../../.venv/bin/python spider.py            # 全量列表 + 详情抽样 + 落盘
    ../../../.venv/bin/python spider.py --window   # 额外实测 token 的时间窗口（约 15 个请求）
"""
import base64
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone

import requests

BASE = 'https://spa2.scrape.center'
INDEX_PATH = '/api/movie'
DETAIL_PATH = '/api/movie/{key}'
# 详情页 key 的盐，逐字取自 chunk-4136500c 模块 "3e22"（见 evidence/spa2_module_3e22_transfer.js）
SALT = 'ef34#teuq0btua#(-57w1q5o5--j@98xygimlyfxs*-!i-0-mb'
LIMIT = 10
INTERVAL = 0.8          # 礼貌间隔（秒）
DETAIL_SAMPLE = 5       # 详情页抽样条数，够证明详情 token 的参数形态即可，不压测
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, 'data')
UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')


def make_token(*args, t: int = None) -> str:
    """spa2 的 token 生成器。args 为参与签名的业务参数，时间戳自动追加在最后。"""
    ts = str(int(round(time.time())) if t is None else int(t))
    parts = [str(a) for a in args] + [ts]
    sha1_hex = hashlib.sha1(','.join(parts).encode('utf-8')).hexdigest()
    return base64.b64encode(f'{sha1_hex},{ts}'.encode('utf-8')).decode()


def detail_key(movie_id) -> str:
    """列表里的 id → 详情路由 key（chunk 模块 "3e22" 的 transfer）。"""
    return base64.b64encode(f'{SALT}{movie_id}'.encode('utf-8')).decode()


class Client:
    def __init__(self):
        self.s = requests.Session()
        self.s.headers.update({'User-Agent': UA, 'Accept': 'application/json'})
        self.n = 0

    def get(self, path, params=None, token_args=(), t=None):
        params = dict(params or {})
        params['token'] = make_token(*token_args, t=t)
        if self.n:
            time.sleep(INTERVAL)
        self.n += 1
        return self.s.get(BASE + path, params=params, timeout=20)


def crawl(client: Client):
    movies, total, first_token = [], None, None
    offset = 0
    while True:
        tok = make_token(INDEX_PATH, offset)
        first_token = first_token or tok
        r = client.s.get(BASE + INDEX_PATH,
                         params={'limit': LIMIT, 'offset': offset, 'token': tok}, timeout=20)
        client.n += 1
        r.raise_for_status()
        payload = r.json()
        total = payload['count']
        movies.extend(payload['results'])
        print(f'  offset={offset:<3} HTTP {r.status_code}  +{len(payload["results"])} 条  '
              f'累计 {len(movies)}/{total}  token={tok[:28]}...')
        offset += LIMIT
        if offset >= total or not payload['results']:
            break
        time.sleep(INTERVAL)
    return movies, total, first_token


def crawl_details(client: Client, movies):
    out = []
    for m in movies[:DETAIL_SAMPLE]:
        key = detail_key(m['id'])
        path = DETAIL_PATH.format(key=key)
        r = client.get(path, token_args=(path, 0))
        r.raise_for_status()
        d = r.json()
        out.append({'id': m['id'], 'key': key, 'name': d['name'],
                    'score': d.get('score'), 'published_at': d.get('published_at'),
                    'directors': [x['name'] for x in d.get('directors') or []]})
        print(f'  detail id={m["id"]:<3} HTTP {r.status_code}  {d["name"]}  score={d.get("score")}')
    return out


def probe_window(client: Client):
    """实测 token 的时间限制：把时间戳前后平移若干秒，看服务端还认不认。"""
    print('\n[时间窗口实测] 平移时间戳，观察服务端接受/拒绝')
    rows = []
    for d in (-3600, -600, -300, -200, -181, -180, -60, 0, 60, 179, 180, 181, 300, 600, 3600):
        now = int(round(time.time()))
        r = client.s.get(BASE + INDEX_PATH,
                         params={'limit': 1, 'offset': 0,
                                 'token': make_token(INDEX_PATH, 0, t=now + d)}, timeout=20)
        client.n += 1
        rows.append({'delta_seconds': d, 'status': r.status_code})
        print(f'  t{d:+6d}s -> HTTP {r.status_code}')
        time.sleep(0.4)
    ok = [x['delta_seconds'] for x in rows if x['status'] == 200]
    print(f'  被接受的偏移区间：[{min(ok)}, {max(ok)}] 秒')
    return rows


def replay_stale_token(client: Client):
    """反证：把**上一次运行**记录下来的 token 原样重放，看它是不是已经失效。

    这一条直接证伪「把浏览器里抓到的 token 硬编码复用」这条路——只要两次运行间隔超过 3 分钟，
    旧 token 必然 401。
    """
    log = os.path.join(DATA, 'spa2_runs.json')
    if not os.path.exists(log):
        print('\n[旧 token 重放] 还没有历史运行记录，跳过（先跑一次 spider.py 再来）')
        return None
    runs = json.load(open(log, encoding='utf-8'))
    old = runs[0]
    age = int(time.time()) - old['unix_ts']
    r = client.s.get(BASE + INDEX_PATH,
                     params={'limit': 1, 'offset': 0, 'token': old['first_index_token']}, timeout=20)
    client.n += 1
    print(f'\n[旧 token 重放] 重放 {old["run_at"]} 那次的 token（已过 {age} 秒）-> HTTP {r.status_code}'
          f'（超过 180 秒就该是 401）')
    return {'origin_run_at': old['run_at'], 'age_seconds': age, 'status': r.status_code,
            'token': old['first_index_token'], 'replayed_at': datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')}


def main():
    os.makedirs(DATA, exist_ok=True)
    started = datetime.now(timezone.utc).astimezone()
    print(f'[{started.isoformat(timespec="seconds")}] spa2 直连接口（无浏览器）')
    client = Client()

    stale = replay_stale_token(client)

    print('\n[列表页] /api/movie  token 参数 = ["/api/movie", offset, t]')
    movies, total, first_token = crawl(client)

    print(f'\n[详情页] /api/movie/{{key}}  token 参数 = [path, 0, t]（抽样 {DETAIL_SAMPLE} 条）')
    details = crawl_details(client, movies)

    window = probe_window(client) if '--window' in sys.argv else None

    slim = [{'id': m['id'], 'name': m['name'], 'alias': m.get('alias'),
             'categories': m.get('categories'), 'score': m.get('score'),
             'published_at': m.get('published_at'), 'regions': m.get('regions'),
             'minute': m.get('minute'), 'cover': m.get('cover')} for m in movies]
    out = os.path.join(DATA, 'spa2_movies.json')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump({'run_at': started.isoformat(timespec='seconds'), 'count': total,
                   'fetched': len(slim), 'results': slim}, f, ensure_ascii=False, indent=2)
    size = os.path.getsize(out)
    print(f'\n落盘 {out}（{size} 字节，{len(slim)} 条）')

    with open(os.path.join(DATA, 'spa2_details_sample.json'), 'w', encoding='utf-8') as f:
        json.dump(details, f, ensure_ascii=False, indent=2)
    if stale:
        path = os.path.join(DATA, 'spa2_stale_token_replay.json')
        hist = json.load(open(path, encoding='utf-8')) if os.path.exists(path) else []
        hist.append(stale)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(hist, f, ensure_ascii=False, indent=2)
    if window:
        with open(os.path.join(DATA, 'spa2_token_timewindow.json'), 'w', encoding='utf-8') as f:
            json.dump({'run_at': started.isoformat(timespec='seconds'), 'probe': window},
                      f, ensure_ascii=False, indent=2)

    log = os.path.join(DATA, 'spa2_runs.json')
    runs = json.load(open(log, encoding='utf-8')) if os.path.exists(log) else []
    runs.append({'run_at': started.isoformat(timespec='seconds'),
                 'unix_ts': int(started.timestamp()),
                 'requests': client.n, 'movies': len(slim), 'total': total,
                 'details': len(details), 'first_index_token': first_token})
    with open(log, 'w', encoding='utf-8') as f:
        json.dump(runs, f, ensure_ascii=False, indent=2)
    print(f'共发出 {client.n} 个请求；本次为第 {len(runs)} 次运行，记录追加到 {log}')


if __name__ == '__main__':
    main()
