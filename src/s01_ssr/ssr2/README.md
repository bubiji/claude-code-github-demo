> issue: #4 · 案例: ssr2 · 来源: https://ssr2.scrape.center

# ssr2 —— HTTPS 证书校验

案例描述（**逐字引自** https://scrape.center/，未改写）：

> 电影数据网站，无反爬，无 HTTPS 证书，适合用作 HTTPS 证书验证。

## 先说一件实测到的事：**2026-08-23 这天，ssr2 的证书是好的**

案例设计的是「证书有问题、必须关校验」，但实跑下来对端证书完全合法，
开着校验也能正常访问。证据（`crawl.py` 每次运行都会打这一行，也存进 summary）：

```
[ssr2] 对端证书：subject=scrape.center issuer=Let's Encrypt/YE1
       有效期 Aug  1 04:22:48 2026 GMT → Oct 30 04:22:47 2026 GMT
       SAN=['*.scrape.center', 'scrape.center'] (TLSv1.2)
[ssr2] 开启校验试连：通过
```

用 openssl 交叉验证是同一个结论：

```
$ echo | openssl s_client -connect ssr2.scrape.center:443 -servername ssr2.scrape.center
subject=CN=scrape.center
issuer=C=US, O=Let's Encrypt, CN=YE1
X509v3 Subject Alternative Name: DNS:*.scrape.center, DNS:scrape.center
Verify return code: 0 (ok)
```

`*.scrape.center` 这张泛域名证书把 ssr2 这个子域也盖住了，所以「无 HTTPS 证书」这个
案例条件当前**复现不了**。这里如实记录，不改写案例原文，也不假装踩到了坑。
案例要练的那件事仍然照练：脚本用 `--insecure` 显式关闭校验跑完了全量。

## 怎么跑

```bash
cd src/s01_ssr/ssr2
python crawl.py                # 自动探测：能校验就 verify=True，不能才关
python crawl.py --insecure     # 强制 verify=False（复现案例设计意图，本次落盘用的就是它）
python crawl.py --strict       # 强制 verify=True，证书不过直接非 0 退出
```

三种模式的差别只在 `verify` 参数，翻页/解析/落盘完全共用 [`../common.py`](../common.py)。

## 关掉证书校验意味着什么（风险声明）

脚本一旦决定 `verify=False`，会往 stderr 打这段，而不是闷头跑：

```
!! 已关闭 TLS 证书校验（verify=False）。
!! 风险：不校验证书 = 无法确认对端真是 ssr2.scrape.center，任何能插进链路的人
!!       （公共 WiFi、劫持的 DNS、透明代理）都能出示自己的证书冒充服务端，
!!       明文读走并篡改全部往返内容——即中间人攻击（MITM）。HTTPS 的加密还在，
!!       但「加密给谁」这一半保证没了，等价于对一个陌生人加密。
!! 之所以在这里可接受：目标是案例作者公开提供的练习站（issue #4），抓的是公开
!!   电影数据，请求里不带任何凭证或隐私。生产环境的正解是修证书/配私有 CA，
!!   而不是 verify=False。
```

配套的三条纪律，都是为了不把「这次连接不可信」这件事藏起来：

1. **先探明再决定。** `probe_tls()` 先开着校验试连一次，失败就把 `SSLError` 原文打出来
   ——是过期、自签名，还是域名不匹配，各有各的正解，不能一律 `verify=False`。
2. **默认不关。** 无参运行时 `verify` 取探测结果；只有显式 `--insecure` 才强制关闭。
   关闭是一个有依据的决定，不是默认姿势。
3. **不消警告。** 脚本**故意不调用** `urllib3.disable_warnings()`，也不 `warnings.filterwarnings`。
   关校验后每个请求都会打一条 `InsecureRequestWarning`，刷屏就是提醒本身。
   本次全量运行刷了 111 条，一条没删。

> 真遇到自签名/私有 CA 的正解是 `verify="/path/to/ca.pem"`（把那张 CA 加进信任链），
> 而不是把校验整个关掉——前者仍能防 MITM，后者不能。

## 抓到什么（2026-08-23 真实运行，`--insecure`）

```
[ssr2] 对端证书：subject=scrape.center issuer=Let's Encrypt/YE1 ...
[ssr2] 开启校验试连：通过
[ssr2] https://ssr2.scrape.center · verify=False workers=1 delay=0.3s
...InsecureRequestWarning × 111...

[ssr2] 抓取完成
  记录数     : 100（列表页 10 页 / 详情页 100 个）
  请求数     : 111，失败 0
  单请求均值 : 1.03s
  总耗时     : 152.69s（列表 16.98s + 详情 135.71s）
  串行预估   : 114.23s（111 请求 × 均值 1.03s）
  落盘       : ssr2.json 482.8KB / ssr2.summary.json
```

- `data/ssr2.json` —— 100 条完整记录（字段同 ssr1）
- `data/ssr2.summary.json` —— 除统计外，多一个 `tls` 字段存下本次的
  `verify_used` / `verify_passed` / 证书 subject-issuer-有效期-SAN，便于日后回看当天证书状况
- 不再单独出 CSV：ssr1~ssr4 是同一套站的同一批数据，CSV 只在 [`../ssr1/data/ssr1.csv`](../ssr1/data/ssr1.csv) 留一份
- 跑 [`../verify.py`](../verify.py) 可验证本份数据与 ssr1 逐字段相同（`detail_url` 的 host 除外）

## 遇到的坑

1. **`getpeercert()` 在 `CERT_NONE` 下返回空字典。** 想在「不校验」的前提下把证书信息打出来，
   直接 `tls.getpeercert()` 只会拿到 `{}`。得取 `getpeercert(binary_form=True)` 的 DER，
   转成 PEM 再解析（`cert_info()` 里就是这么做的），否则风险声明里连「证书到底长什么样」都说不出来。

2. **`verify=False` 只关校验，不关加密。** 容易误以为「关了证书就等于明文 HTTP」。实际 TLS 握手
   照做、流量照样加密，丢的是**身份认证**那一半。这个区别决定了风险描述的写法：不是「被人看到」，
   而是「不知道在跟谁加密」。

3. **`requests` 的 `verify` 是 per-request 的。** `session.verify = False` 会被
   `session.get(..., verify=True)` 覆盖，反之亦然；把开关显式传进每次 `get()` 才不会两处打架。

4. **同样的 500 翻页终止逻辑。** 第 11 页返回 HTTP 500 而不是空列表，处理方式见 ssr1 README 第 1 条。
