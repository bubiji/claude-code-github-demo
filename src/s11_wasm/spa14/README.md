> issue: #14 · 案例: spa14 · 来源: https://spa14.scrape.center

# spa14 —— 数值型 WASM

## 案例描述（逐字引自 https://scrape.center/）

> 电影数据网站，数据通过 Ajax 加载，数据接口参数加密且有时间限制，加密过程通过数值型 WASM 实现，适合 WASM 逆向分析。

以下内容为本仓库的分析与实现，与上面这段原文分开。

---

## 一、结论速览

| 项 | 值 |
|---|---|
| 受保护接口 | `GET https://spa14.scrape.center/api/movie/?limit=&offset=&sign=` |
| wasm 文件 | `https://spa14.scrape.center/js/Wasm.wasm`，**232 字节**，0 个 import |
| 导出函数 | `encrypt(i32 offset, i32 timestamp) -> i32`（另有 `memory` / `_initialize` / `stackSave` / `stackRestore` / `stackAlloc` / `__indirect_function_table`） |
| 浏览器调用方式 | `this.$wasm.asm.encrypt(offset, parseInt(ts))` —— **直调导出函数，不经 `ccall`** |
| 算法（反汇编所得） | `sign = offset + trunc(ts / 3) + 16358` |
| 时间窗口（实测） | 时间戳落在「过去 150 秒 ~ 未来 150 秒」内接受，180 秒即 `401` |
| 全量数据 | `count = 104`，11 页 × limit 10，全部抓下 |

## 二、为什么它叫「数值型」

`encrypt` 的入参和返回值都是 i32 **数值**本身，不是指针。整条链路**完全不碰线性内存**：

- 不需要 `malloc` / `stackAlloc`
- 不需要往 `memory.buffer` 写字节
- 不需要 UTF-8 编解码
- 不需要读回内存

所以 Python 侧只要「把 .wasm 实例化 → 拿到导出函数 → 传两个 int」就完事了。
对比 `spa15/README.md` 里字符串型那一套内存管理，差距就是这个阶段的全部教学价值。

而且这份 wasm **一个 import 都没有**（`evidence/exports.txt` 可验），
`Instance(store, module, [])` 传空 import 列表即可，连 WASI 桩都不用。

## 三、逆向过程

### 1. 定位 wasm 文件（这里有个坑）

Emscripten 胶水里写的是**裸文件名**：

```js
var lt="Wasm.wasm";
```

真实 URL 是 webpack publicPath 拼出来的 `/js/Wasm.wasm`。
如果按直觉去请求 `https://spa14.scrape.center/Wasm.wasm`，会拿到 **HTTP 200 + 1007 字节的
`index.html`**（SPA 的 history fallback），看状态码根本发现不了错。判定只能靠 magic number：

```
$ curl -sS https://spa14.scrape.center/Wasm.wasm | xxd | head -1
00000000: 3c21 444f 4354 5950 4520 6874 6d6c 3e3c  <!DOCTYPE html><

$ curl -sS https://spa14.scrape.center/js/Wasm.wasm | xxd | head -1
00000000: 0061 736d 0100 0000 0117 0560 0000 6001  .asm.......`..`.
```

`00 61 73 6d`（`\0asm`）才是 wasm。

### 2. 找调用点

`js/chunk-67143ceb.69ecbfaf.js` 里列表页的 `onFetchData`（原文见 `evidence/glue-snippets.md`）：

```js
var n=(this.page-1)*this.limit,
    e=this.$wasm.asm.encrypt(n,parseInt(Math.round((new Date).getTime()/1e3).toString()));
this.$axios.get(this.$store.state.url.index,{params:{limit:this.limit,offset:n,sign:e}})
```

→ 入参就是 `offset` 和**秒级时间戳**，出参放进 query 的 `sign`。

### 3. 反汇编

`wasm2wat Wasm.wasm`（wabt 1.0.41）里 `encrypt` 是 func 4，函数体一共 5 条指令：

```wat
  (func (;4;) (type 4) (param i32 i32) (result i32)
    local.get 0
    local.get 1
    i32.const 3
    i32.div_s
    i32.add
    i32.const 16358
    i32.add)
```

即 `sign = offset + (ts i32.div_s 3) + 16358`。`i32.div_s` 向零截断，
Python 的 `//` 向下取整，负时间戳要修正符号（`sign_pure()` 里处理了；正常时间戳无差别）。

完整 wat 见 `evidence/Wasm.wat`（仅 41 行）。

### 4. 服务端到底校验什么（实测反推）

`sign` 里同时含 `offset` 和 `ts`，服务端能反解出 `ts ≈ (sign - 16358 - offset) * 3`，
再拿它跟当前时间比。所以 **offset 并不是被单独校验的**，而是折算成时间偏移：

```
[2026-08-23T20:02:41+09:00] offset=10  sign_for_offset=10  -> HTTP 200
[2026-08-23T20:02:42+09:00] offset=10  sign_for_offset=0   -> HTTP 200   ← 错位 10 → ts 偏 30s，还在窗口内
[2026-08-23T20:02:44+09:00] offset=0   sign_for_offset=10  -> HTTP 200
[2026-08-23T20:02:45+09:00] offset=100 sign_for_offset=0   -> HTTP 401   ← 错位 100 → ts 偏 300s，出窗口
[2026-08-23T20:02:46+09:00] offset=0   sign_for_offset=100 -> HTTP 401
```

这条实测同时反证了算法里 `/3` 和 `+offset` 两项都是真的。

## 四、代码

```
spa14/
├── README.md
├── spa14.py                    # 抓取 + 双路线对账 + 探针
├── data/
│   ├── spa14_movies.json       # 104 条全量数据
│   ├── spa14_run.log
│   ├── spa14_probe.json        # 有效期 / offset 绑定探针
│   └── spa14_twice.json        # 间隔 200s 跑两轮的实测记录
└── evidence/
    ├── Wasm.wasm               # 232 字节原件，来自 /js/Wasm.wasm
    ├── Wasm.wat                # wasm2wat 输出（41 行）
    ├── exports.txt             # imports / exports 清单
    ├── glue-snippets.md        # JS 胶水与调用点原文摘录（逐字）
    └── js/                     # 相关 JS 原件（未格式化，线上原样）
```

`spa14.py` 同时实现两条路线，**每次生成 sign 都互相对账，不一致直接退出**：

- A｜wasm 路线（`WasmSigner`）：`wasmtime` 加载 `.wasm`，调 `encrypt`
- B｜纯 Python 路线（`sign_pure`）：按上面 5 条指令复现

## 五、环境与运行

额外依赖（**不写进仓库根 `requirements.txt`**，本案例自己装）：

```bash
# 仓库根的 venv
.venv/bin/pip install wasmtime      # 实测版本 wasmtime 48.0.0
# 反汇编工具（可选，只在做逆向时需要）
brew install wabt                   # 实测版本 wabt 1.0.41
```

运行：

```bash
cd src/s11_wasm/spa14
../../../.venv/bin/python spa14.py                    # 全量抓取
../../../.venv/bin/python spa14.py --probe            # 有效期 / offset 探针
../../../.venv/bin/python spa14.py --twice --gap 200  # 间隔 200s 跑两轮
```

礼貌抓取：每次请求之间 `sleep 1`，全量 11 次请求。

## 六、实测输出

### 全量抓取（2026-08-23）

```
[2026-08-23T20:00:55+09:00] offset=0    ts=1787482855 sign=595843976 -> HTTP 200
[2026-08-23T20:00:57+09:00] offset=10   ts=1787482857 sign=595843987 -> HTTP 200
[2026-08-23T20:00:58+09:00] offset=20   ts=1787482858 sign=595843997 -> HTTP 200
[2026-08-23T20:01:00+09:00] offset=30   ts=1787482860 sign=595844008 -> HTTP 200
[2026-08-23T20:01:02+09:00] offset=40   ts=1787482861 sign=595844018 -> HTTP 200
[2026-08-23T20:01:03+09:00] offset=50   ts=1787482863 sign=595844029 -> HTTP 200
[2026-08-23T20:01:05+09:00] offset=60   ts=1787482865 sign=595844039 -> HTTP 200
[2026-08-23T20:01:07+09:00] offset=70   ts=1787482866 sign=595844050 -> HTTP 200
[2026-08-23T20:01:08+09:00] offset=80   ts=1787482868 sign=595844060 -> HTTP 200
[2026-08-23T20:01:10+09:00] offset=90   ts=1787482870 sign=595844071 -> HTTP 200
[2026-08-23T20:01:12+09:00] offset=100  ts=1787482871 sign=595844081 -> HTTP 200

count=104 实际取到 104 条
```

### 有效期探针（2026-08-23）

```
[2026-08-23T20:02:25+09:00] age=    0s ts=1787482944 sign=595844006 -> HTTP 200
[2026-08-23T20:02:26+09:00] age=   30s ts=1787482914 sign=595843996 -> HTTP 200
[2026-08-23T20:02:28+09:00] age=   60s ts=1787482884 sign=595843986 -> HTTP 200
[2026-08-23T20:02:29+09:00] age=  120s ts=1787482824 sign=595843966 -> HTTP 200
[2026-08-23T20:02:30+09:00] age=  150s ts=1787482794 sign=595843956 -> HTTP 200
[2026-08-23T20:02:31+09:00] age=  180s ts=1787482764 sign=595843946 -> HTTP 401
[2026-08-23T20:02:32+09:00] age=  300s ts=1787482644 sign=595843906 -> HTTP 401
[2026-08-23T20:02:33+09:00] age=  600s ts=1787482344 sign=595843806 -> HTTP 401
[2026-08-23T20:02:35+09:00] age= 3600s ts=1787479344 sign=595842806 -> HTTP 401
[2026-08-23T20:02:36+09:00] age=  -60s ts=1787483004 sign=595844026 -> HTTP 200
[2026-08-23T20:02:38+09:00] age= -150s ts=1787483094 sign=595844056 -> HTTP 200
[2026-08-23T20:02:39+09:00] age= -300s ts=1787483244 sign=595844106 -> HTTP 401
```

窗口是**双向**的（未来 150 秒也认），所以服务端做的是 `|ts - now| < 窗口` 的判断。

### 隔 200 秒跑两轮（见 §七）

## 七、「不是硬编码」的证据

`--twice --gap 200` 做三件事：

1. 第 1 轮全量抓取（现算 sign）
2. 等 200 秒（**超过实测的 150 秒窗口**）
3. 先拿第 1 轮的**旧 sign 原样重放**做对照组，再跑第 2 轮全量抓取

预期：对照组 `401`（旧参数确实失效了），第 2 轮全部 `200`（现算的参数照样好使）。
两者缺一都不能证明「不是硬编码」——只有第 2 轮成功说明不了参数没过期，
只有对照组失败说明不了本轮是现算的。

实测记录见 `data/spa14_twice.json`，摘要：

```
[2026-08-23T20:03:27+09:00] offset=0    ts=1787483006 sign=595844026 -> HTTP 200
[2026-08-23T20:03:28+09:00] offset=10   ts=1787483008 sign=595844037 -> HTTP 200
[2026-08-23T20:03:29+09:00] offset=20   ts=1787483009 sign=595844047 -> HTTP 200
[2026-08-23T20:03:31+09:00] offset=30   ts=1787483011 sign=595844058 -> HTTP 200
[2026-08-23T20:03:33+09:00] offset=40   ts=1787483013 sign=595844069 -> HTTP 200
[2026-08-23T20:03:34+09:00] offset=50   ts=1787483014 sign=595844079 -> HTTP 200
[2026-08-23T20:03:36+09:00] offset=60   ts=1787483016 sign=595844090 -> HTTP 200
[2026-08-23T20:03:38+09:00] offset=70   ts=1787483017 sign=595844100 -> HTTP 200
[2026-08-23T20:03:39+09:00] offset=80   ts=1787483019 sign=595844111 -> HTTP 200
[2026-08-23T20:03:42+09:00] offset=90   ts=1787483021 sign=595844121 -> HTTP 200
[2026-08-23T20:03:43+09:00] offset=100  ts=1787483023 sign=595844132 -> HTTP 200
第 1 轮：count=104 实际取到 104 条

--- 等待 200s（超过实测有效期）---
[2026-08-23T20:07:03+09:00] 对照组：复用第 1 轮的旧 sign=595844026 (ts=1787483006) -> HTTP 401
[2026-08-23T20:07:05+09:00] offset=0    ts=1787483225 sign=595844099 -> HTTP 200
[2026-08-23T20:07:07+09:00] offset=10   ts=1787483226 sign=595844110 -> HTTP 200
[2026-08-23T20:07:08+09:00] offset=20   ts=1787483228 sign=595844120 -> HTTP 200
[2026-08-23T20:07:10+09:00] offset=30   ts=1787483230 sign=595844131 -> HTTP 200
[2026-08-23T20:07:12+09:00] offset=40   ts=1787483232 sign=595844142 -> HTTP 200
[2026-08-23T20:07:13+09:00] offset=50   ts=1787483233 sign=595844152 -> HTTP 200
[2026-08-23T20:07:15+09:00] offset=60   ts=1787483235 sign=595844163 -> HTTP 200
[2026-08-23T20:07:17+09:00] offset=70   ts=1787483236 sign=595844173 -> HTTP 200
[2026-08-23T20:07:19+09:00] offset=80   ts=1787483238 sign=595844184 -> HTTP 200
[2026-08-23T20:07:20+09:00] offset=90   ts=1787483240 sign=595844194 -> HTTP 200
[2026-08-23T20:07:22+09:00] offset=100  ts=1787483242 sign=595844205 -> HTTP 200
第 2 轮：count=104 实际取到 104 条
```

两轮相隔 202 秒（20:03:43 → 20:07:05），对照组重放旧 sign **401**，第 2 轮 11 次请求**全 200**。

## 八、边界说明（做到哪、没做哪）

- **只有列表接口 `/api/movie/` 是 WASM 保护的。** 详情页 `/api/movie/{key}` 的 `token`
  来自 JS 模块 `7d92`（crypto-js 的 sha1），`$wasm` 在详情页组件里完全没出现
  （原文见 `evidence/glue-snippets.md` §5）。那条链路属于 spa6 那一路的作业，
  本阶段不做，也没必要为了凑数据把它顺手实现掉。
- 因此 `data/spa14_movies.json` 是**列表字段**（id / name / alias / cover / categories /
  published_at / minute / score / regions），不含 drama、演职员等详情字段。
