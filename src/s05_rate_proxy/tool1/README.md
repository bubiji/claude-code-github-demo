> issue: #8 · 案例: tool1 · 来源: https://proxypool.scrape.center/random

# tool1 · 代理池 API

案例描述（逐字引自 <https://scrape.center/>，未做任何改写）：

> 代理池 API 网站，访问即可获取随机可用公开代理，源代码来自 https://github.com/Python3WebSpider/ProxyPool

## 一、这个案例真正要产出的东西

不是「一堆能用的代理」，而是**一个诚实的可用率数字**。

阶段 5 的前三个案例都在被限流，很自然会想「换 IP 不就行了」。这个想法成不成立，
完全取决于代理池里到底有几个能用的代理。所以先量，再决定要不要依赖它。

接口很简单，GET 一次返回一条 `ip:port` 纯文本：

```
$ curl https://proxypool.scrape.center/random
8.138.217.152:21001
```

## 二、取 → 校验 → 剔除

`common.ProxyPool` 三个动作缺一不可：

| 动作 | 做什么 | 不做会怎样 |
|---|---|---|
| **取** | 反复 GET `/random` 直到凑够 N 个**去重**候选 | 接口不保证不重复，不去重会把同一个代理校验很多遍 |
| **校验** | 拿候选去打探针 URL，能在超时内返回期望内容才算活 | 把失败推迟到正式抓取时发生——**那时一次失败要赔上一次配额** |
| **剔除** | 使用中一失败（连不上/超时/被限流）立刻从池里删掉 | 公开代理的失败基本是永久性的，留着只会反复浪费配额 |

校验分三档，一档比一档严——**因为「代理活着」和「代理能干我要它干的事」是两回事**：

1. `connect/http` —— 能否走明文 HTTP（探针 `http://httpbin.org/ip`）
2. `https` —— 能否建 CONNECT 隧道（探针 `https://httpbin.org/ip`）。
   很多公开代理只支持明文，而 antispider5/6/7 **全是 HTTPS 站**，这一档挂了就等于没用。
3. `target/antispider5` —— 能否真的把目标站页面取回来
   （断言正文里有 `el-card item`，**防透明代理/运营商劫持页返回 200 却不是原页面**）

## 三、实测可用率

```
$ .venv/bin/python src/s05_rate_proxy/tool1/proxy_check.py --n 60

[19:56:44] [proxy] 取到 26 个去重候选（API 调用 240 次）
[connect/http] 11/26 存活（42.3%）  url=http://httpbin.org/ip
        失败原因 HTTP 503: 6
        失败原因 ProxyError: 6
        失败原因 ReadTimeout: 3
[https] 3/11 存活（27.3%）  url=https://httpbin.org/ip
        失败原因 HTTP 503: 3
        失败原因 ConnectionError: 3
        失败原因 ReadTimeout: 1
        失败原因 SSLError: 1
[target/antispider5] 2/3 存活（66.7%）  url=https://antispider5.scrape.center/page/1
        失败原因 ReadTimeout: 1
[19:57:24] [proxy] 剔除 114.236.137.41:21000（ReadTimeout），剩余 2
```

### 漏斗（分母统一取 26 个去重候选）

| 环节 | 存活 | 占候选比 |
|---|---:|---:|
| 取到的去重候选 | 26 | 100% |
| ① 能走明文 HTTP | 11 | **42.3%** |
| ② 能走 HTTPS | 3 | **11.5%** |
| ③ 能取回 antispider5 页面 | **2** | **7.7%** |

**端到端真实可用率 = 2 / 26 = 7.7%。**

还有一个更刺眼的数字：**240 次 API 调用只换来 26 个去重 IP**（重复率 89.2%）。
池子本身就只有二十几个条目，`--n 60` 要不到 60 个——不是取得不够多，是**池里没那么多**。

（更早的一轮 `--n 50` 测得 29 个去重候选 / HTTP 31.0% / HTTPS 6.9%，与本轮同一量级。
两轮结果都在 `data/proxy_report.json` 的口径下可复现，数字有波动是公开代理的常态。）

## 四、这对前三个案例意味着什么

**代理池撑不起「换 IP 绕过限流」这个方案。** 具体到三个案例：

| 案例 | 限的是什么 | 代理池有用吗 |
|---|---|---|
| antispider5 | IP | 理论上有用，但只有 2 个可用代理 → 配额从 10 次/5 分钟变成 30 次/5 分钟，量级没变，且这 2 个随时会死 |
| antispider6 | **账号** | **完全无效**——配额跟着 `sessionid` 走，换出口 IP 不改变任何事 |
| antispider7 | IP **且** 账号 | 只解一半，另一半照堵 |

所以本阶段三个案例的实际做法是**不用代理，纯靠主动控速**（35 秒间隔 / 9 次每 300 秒），
三个站实跑全部 **0 次限流命中、0 次封禁**。代理在 `PoliteClient` 里是可选依赖
（`proxy_pool=None` 时直连），留着只为两件事：

1. 意外挨封时不至于干等 10 分钟；
2. 做那些「会把 IP 打封」的实验时，让代理的 IP 去承担代价。

> 关于第 2 点，本次**没有**用那 2 个可用代理去把 antispider5 撞封来验证 IP 限流。
> 理由：那是拿别人的 IP 去换我的实验数据，而且 2 个样本的结论也不可靠。
> IP 限流的证据改由 antispider6 上的一次性账号探测提供（同族实现，同样的
> 10 次/5 分钟文案，实测第 12 次返回 403），见 `../antispider6/README.md` 第四节。

## 五、落盘

`data/proxy_report.json`（6.7 KB）：

- `funnel`：上面那张漏斗表的机读版；
- `items`：**每一个代理在每一档的原始判定**（状态码、失败异常类型、延迟），
  可用率是从这里数出来的，不是估的；
- `dropped_after_target_check` / `pool_state`：剔除动作的结果与池子终态。

## 六、跑法

```bash
PY=/Users/deanlee/Documents/Claude/Projects/git_github/.venv/bin/python

$PY proxy_check.py --n 60               # 三档全跑（会向 antispider5 发 ≤ 候选数 次请求，走代理）
$PY proxy_check.py --n 50 --no-target   # 只测通用可用性，完全不碰 antispider5
$PY proxy_check.py --n 60 --timeout 12  # 放宽超时（慢代理会多活几个）
```

> `--no-target` 存在的意义：目标档会通过代理去打 antispider5。代理一旦是透明的，
> 请求就会从**本机 IP** 发出去、白白吃掉限流配额。所以 antispider5 的正式抓取
> **正在跑的时候，不要跑目标档**。本次实测是在 antispider5 抓取全部结束之后才跑的。
