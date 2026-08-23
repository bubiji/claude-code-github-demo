> issue: #14 · 案例: spa15 · 来源: https://spa15.scrape.center

# spa15 —— 字符串型 WASM

## 案例描述（逐字引自 https://scrape.center/）

> 电影数据网站，数据通过 Ajax 加载，数据接口参数加密且有时间限制，加密过程通过字符串型 WASM 实现，适合 WASM 逆向分析。

以下内容为本仓库的分析与实现，与上面这段原文分开。

---

## 一、结论速览

| 项 | 值 |
|---|---|
| 受保护接口 | `GET https://spa15.scrape.center/api/movie/?limit=&offset=&token=` |
| wasm 文件 | `https://spa15.scrape.center/js/Wasm.wasm`，**19231 字节**，1 个 import（`wasi_snapshot_preview1.proc_exit`） |
| 导出函数 | `encrypt(i32, i32) -> i32`，**三个 i32 全是线性内存指针** |
| 浏览器调用方式 | `this.$wasm.ccall("encrypt","string",["string","string"],[url, ts])` |
| 签名输入 | `url = "/api/movie"`（**裸路径，末尾没有斜杠**）+ 秒级时间戳的十进制字符串 |
| 算法（实测反推 + 数据段佐证） | `token = base64( sha1_hex("/api/movie," + ts) + "," + ts )` |
| 时间窗口（实测） | 时间戳落在「过去 150 秒 ~ 未来 150 秒」内接受，180 秒即 `401` |
| offset | **不参与签名**，同一个 token 可用于任意 offset（实测 0 / 30 / 90 全 200） |
| 全量数据 | `count = 104`，11 页 × limit 10，全部抓下 |

## 二、为什么它叫「字符串型」，以及内存读写到底怎么做

先看一个容易翻车的事实：**spa15 的 `encrypt` 签名跟 spa14 一字不差**，都是 `(i32,i32) -> i32`。

```
spa14: encrypt :: func ['i32', 'i32'] -> ['i32']
spa15: encrypt :: func ['i32', 'i32'] -> ['i32']
```

WASM 的 MVP 类型系统里**只有 i32/i64/f32/f64 四种数**，压根没有「字符串」这个类型。
所谓「字符串型」，是指这些 i32 其实是**指向线性内存的地址**。光看导出签名分不出来，
只有看 JS 怎么调它才知道：

- spa14：`$wasm.asm.encrypt(n, ts)` —— 直调，数就是数
- spa15：`$wasm.ccall("encrypt","string",["string","string"], [...])` —— `ccall` 负责把
  JS 字符串搬进 wasm 内存，再把返回的指针读回成 JS 字符串

`ccall` 不是魔法，就是下面这五步。Emscripten 胶水的原文（混淆后）见
`evidence/glue-snippets.md` §4，对应关系是
`bt=stackSave`、`xt=stackAlloc`、`N=stringToUTF8`、`W=UTF8ToString`、`_t=stackRestore`。

### 1) `stackSave()` —— 记下栈指针

wasm 的「影子栈」就是线性内存里的一段，栈指针存在一个 mutable global 里。
先存一份，最后好整体回卷。

### 2) `stackAlloc(n)` —— 在影子栈上要 n 字节，拿到指针

**spa15 的模块没有导出 `malloc` / `free`**（`evidence/exports.txt` 可验），
所以只能用栈分配。Emscripten 按最坏情况分配 `1 + len*4` 字节
（每个 UTF-16 码元最多编成 4 字节 UTF-8，再加结尾的 `\0`）。
本仓库按实际 UTF-8 字节数 `+1` 分配，等价且更省。

### 3) `stringToUTF8(str, ptr)` —— 把字节真正写进 `memory.buffer`

这一步是「字符串型」区别于「数值型」的核心：JS/Python 的字符串对象在 wasm 里不存在，
必须自己编码成 UTF-8 字节序列、**末尾补一个 `\0`**、写到 `ptr` 起始的内存里。
wasmtime-py 的接口是 `memory.write(store, data: bytes, start: int)`。

### 4) 用**指针**调用导出函数，返回值也是**指针**

```python
p_ret = encrypt(store, p_url, p_ts)   # 三个都是 i32 地址
```

### 5) `UTF8ToString(ptr)` —— 从内存读回来

C 字符串没有长度字段，只有结尾的 `\0`。所以读的时候必须**从 ptr 往后扫到第一个 0 字节**，
再把这段 bytes 按 UTF-8 解码。胶水里对应这一行原文：

```js
function U(t,n,e){var r=n+e,i=n;while(t[i]&&!(i>=r))++i;
```

本仓库的 `_read_cstring()` 分块读 + `find(b"\x00")`，语义一致。

### 6) `stackRestore(sp)` —— 把栈指针拨回去

一次性释放这一轮所有 `stackAlloc`。**不做这一步，循环调用会把影子栈耗光**——
本案例要抓 11 页、调 11 次 `encrypt`，很容易撞上。

> 顺带一个细节：返回值的指针（实测 `5246480`）**不在影子栈里**，它比 `stackSave()` 拿到的
> 栈顶还高，是模块内部的静态/堆缓冲区。所以先读再 `stackRestore` 是安全的；
> 但保险起见代码仍然在 `finally` 之前读完。

### 实跑一遍（`python spa15.py --memdump` 的真实输出）

```
ccall("encrypt","string",["string","string"],['/api/movie', '1787482848'])
  stackSave() -> 5246112
    stackAlloc( 11) -> ptr=5246096   写入 b'/api/movie\x00'
    stackAlloc( 11) -> ptr=5246080   写入 b'1787482848\x00'
    encrypt(5246096, 5246080) -> ptr=5246480
    UTF8ToString(ptr=5246480) 扫到 NUL，长度 68 字节
  stackRestore(5246112)
  => token = ZjU1Njc1ZWJmM2RjNTRjM2NjNTcxZjVhYzUxZTY4NTU1YjdiZDQzZiwxNzg3NDgyODQ4
  base64 解开 = f55675ebf3dc54c3cc571f5ac51e68555b7bd43f,1787482848
  纯 Python 复现 = ZjU1Njc1ZWJmM2RjNTRjM2NjNTcxZjVhYzUxZTY4NTU1YjdiZDQzZiwxNzg3NDgyODQ4
  一致：True
```

注意 `stackAlloc` 返回的地址是**递减**的（5246096 → 5246080），影子栈向下生长；
每次分配还被对齐到 16 字节（11 字节要了 16）。

## 三、另一个坑：必须提供 WASI import

spa15 比 spa14 多一个 import：

```
== IMPORTS ==
  wasi_snapshot_preview1.proc_exit :: func ['i32'] -> []
```

wasmtime-py 的 `Instance(store, module, imports)` 按 `module.imports` 的**顺序位置**接收
import，少一个直接报错。给一个签名匹配的空桩就行：

```python
proc_exit = Func(store, FuncType([ValType.i32()], []), lambda code: None)
instance = Instance(store, module, [proc_exit])
```

（浏览器胶水里同样给了 `wasi_snapshot_preview1`，见 `evidence/glue-snippets.md`。）

## 四、算法反推

`encrypt` 是 func 24，wat 里 627 行 —— C++ 编译产物，带 `std::string` / `std::vector`，
手工反编译成本很高。所以走的是「行为观测 + 数据段佐证」：

1. 观测：token base64 解开后长这样 —— `f55675ebf3dc54c3cc571f5ac51e68555b7bd43f,1787482848`，
   即 `<40 位 hex>,<时间戳>`。40 位 hex = SHA-1。
2. 猜输入：`sha1("/api/movie,1787482374")` → `b2273c385051836f79b0ecdd6c216173ef3b0b83`，
   与实际 token 解出来的 hex **完全一致**（其余排列组合都不对，见下）：

```
'/api/movie,1787482374'   b2273c385051836f79b0ecdd6c216173ef3b0b83   ← 命中
'/api/movie1787482374'    98399d676c496a59f51cc341b739a3beb40c3769
'1787482374/api/movie'    3961dd60c1ef7101b7f4480e1c42fc9366f74fb3
'/api/movie|1787482374'   6ad086d392eb1feae5f4001cd7704d558c2f5b9c
```

3. 数据段佐证（`evidence/Wasm.encrypt.wat` 尾部原文）：

```wat
  (data (;3;) (i32.const 2048) "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/")
  (data (;4;) (i32.const 2128) "0123456789abcdef\00allocator<T>::allocate...
```

标准 base64 字母表 + 十六进制字母表，与「摘要转 hex → 拼时间戳 → base64」这条链路吻合。

4. 交叉验证：`spa15.py` **每次生成 token 都同时跑 wasm 路线和纯 Python 路线并比对**，
   不一致直接 `SystemExit`。11 页抓取 + 12 次探针 + 两轮实测，全程 0 次不一致。

> 诚实说明：这是**行为等价性**验证，不是逐指令反编译。627 行 wat 我没有逐条读完，
> 用的是「输入输出 + 常量表」的证据链。就本案例给出的所有输入（`/api/movie` + 任意时间戳）
> 而言两条路线完全一致，但我不能声称对任意输入都等价 —— 比如非 ASCII url 的行为没验过。
> 真要那种强度的结论，得把 func 24 逐条反编译，那是另一个量级的工作量。

## 五、url 必须是 `/api/movie`（不带斜杠）

签名串里的 url 取自 `$store.state.url.index`（`app.f2087057.js` 原文）：

```js
url:{index:"/api/movie",detail:"/api/movie/{key}"}
```

而实际请求打到的是 `/api/movie/`（Django 那边带斜杠）。**签名用的是不带斜杠的那个**。
故意用带斜杠的去签，实测直接 401：

```
[2026-08-23T20:03:16+09:00] 故意用 '/api/movie/'（多一个斜杠）签名 -> HTTP 401
```

## 六、代码

```
spa15/
├── README.md
├── spa15.py                    # 抓取 + 双路线对账 + 探针 + --memdump 教学模式
├── data/
│   ├── spa15_movies.json       # 104 条全量数据
│   ├── spa15_run.log
│   ├── spa15_probe.json        # 有效期 / offset 无关性 / 错误 url 探针
│   └── spa15_twice.json        # 间隔 200s 跑两轮的实测记录
└── evidence/
    ├── Wasm.wasm               # 19231 字节原件，来自 /js/Wasm.wasm
    ├── Wasm.encrypt.wat        # wasm2wat 输出中 func 24 + import/export 段（完整 wat 9269 行、232KB，不入库，可一键重生成）
    ├── exports.txt             # imports / exports 清单
    ├── glue-snippets.md        # ccall 胶水与调用点原文摘录（逐字）+ 混淆名对照表
    └── js/                     # 相关 JS 原件（未格式化，线上原样）
```

## 七、环境与运行

额外依赖（**不写进仓库根 `requirements.txt`**，本案例自己装）：

```bash
.venv/bin/pip install wasmtime      # 实测版本 wasmtime 48.0.0
brew install wabt                   # 实测版本 wabt 1.0.41（只在反汇编时需要）
```

运行：

```bash
cd src/s11_wasm/spa15
../../../.venv/bin/python spa15.py --memdump          # 看一遍内存读写全过程
../../../.venv/bin/python spa15.py                    # 全量抓取
../../../.venv/bin/python spa15.py --probe            # 有效期 / offset / url 探针
../../../.venv/bin/python spa15.py --twice --gap 200  # 间隔 200s 跑两轮
```

重新生成完整 wat：

```bash
wasm2wat evidence/Wasm.wasm -o /tmp/Wasm.wat   # 9269 行
```

## 八、实测输出

### 全量抓取（2026-08-23）

```
[2026-08-23T20:01:18+09:00] offset=0    ts=1787482878 token=YTY3NjBlODAwODVkOTk5Y2Q4MmYwYTdlNDcyYmVkMjQ0YTRlYmVlZSwxNzg3NDgyODc4 -> HTTP 200
[2026-08-23T20:01:20+09:00] offset=10   ts=1787482880 token=OGIyNDBhZTdjN2NmNmU1NjU5MDc5ODk3ZTc0Y2ZjNDJjYmZiYjIwYiwxNzg3NDgyODgw -> HTTP 200
[2026-08-23T20:01:22+09:00] offset=20   ts=1787482882 token=OTRmY2M0MGYzNjM2ODg4ZWVmZDZmNzVlOTYxZjZmYWNlYTdlM2JiMywxNzg3NDgyODgy -> HTTP 200
[2026-08-23T20:01:23+09:00] offset=30   ts=1787482883 token=YjFlZDI0M2ExYjA3N2RlNzBiNWFjZDEzMzI0ZjBlNDA4NWRhZmE1YiwxNzg3NDgyODgz -> HTTP 200
[2026-08-23T20:01:25+09:00] offset=40   ts=1787482885 token=ZDE4ZDkyYmRmY2MwZTIwODdmOGExNDMwMzE4MzEwMjEzODEzODdiMSwxNzg3NDgyODg1 -> HTTP 200
[2026-08-23T20:01:27+09:00] offset=50   ts=1787482887 token=YmY2OGNkMDM4MGRhZWZmNzI0ZjE2YTcxYWE1NGY4ODg1ZTdhMzVhNCwxNzg3NDgyODg3 -> HTTP 200
[2026-08-23T20:01:28+09:00] offset=60   ts=1787482888 token=NDg2NDc5NTMzYWEwNjdhOTQ4MGJkYmJkOTZkNDVkNmM4ODQ4ZTE0MCwxNzg3NDgyODg4 -> HTTP 200
[2026-08-23T20:01:30+09:00] offset=70   ts=1787482890 token=NjA4ZDU1OTg0N2VjNjllYjZhMzU3MmM3OWZlMzIwY2U0YjcxMTZiMCwxNzg3NDgyODkw -> HTTP 200
[2026-08-23T20:01:32+09:00] offset=80   ts=1787482892 token=NTFkZTliOWJiMGNiZmVhNGNjOWZlNzMwOWIwMzFmMGJjODVjNTEzYiwxNzg3NDgyODky -> HTTP 200
[2026-08-23T20:01:33+09:00] offset=90   ts=1787482893 token=ZDZhMjcyNjljYWY2ZmMzZjk2ZTNjMzI3OWY4MWEyZWIwMzdmMThkZSwxNzg3NDgyODkz -> HTTP 200
[2026-08-23T20:01:35+09:00] offset=100  ts=1787482895 token=MDM5MWJlMDUzY2MzZWQ5N2M4MWU5MjA0MDg1YmM1YjU2YmU0NzMyNiwxNzg3NDgyODk1 -> HTTP 200

count=104 实际取到 104 条
```

### 探针（2026-08-23）

```
[2026-08-23T20:02:56+09:00] age=    0s ts=1787482975 -> HTTP 200
[2026-08-23T20:02:57+09:00] age=   30s ts=1787482945 -> HTTP 200
[2026-08-23T20:02:59+09:00] age=   60s ts=1787482915 -> HTTP 200
[2026-08-23T20:03:00+09:00] age=  120s ts=1787482855 -> HTTP 200
[2026-08-23T20:03:01+09:00] age=  150s ts=1787482825 -> HTTP 200
[2026-08-23T20:03:02+09:00] age=  180s ts=1787482795 -> HTTP 401
[2026-08-23T20:03:04+09:00] age=  300s ts=1787482675 -> HTTP 401
[2026-08-23T20:03:05+09:00] age=  600s ts=1787482375 -> HTTP 401
[2026-08-23T20:03:06+09:00] age= 3600s ts=1787479375 -> HTTP 401
[2026-08-23T20:03:07+09:00] age=  -60s ts=1787483035 -> HTTP 200
[2026-08-23T20:03:09+09:00] age= -150s ts=1787483125 -> HTTP 200
[2026-08-23T20:03:10+09:00] age= -300s ts=1787483275 -> HTTP 401
[2026-08-23T20:03:12+09:00] 同一 token 用于 offset=0 -> HTTP 200
[2026-08-23T20:03:13+09:00] 同一 token 用于 offset=30 -> HTTP 200
[2026-08-23T20:03:15+09:00] 同一 token 用于 offset=90 -> HTTP 200
[2026-08-23T20:03:16+09:00] 故意用 '/api/movie/'（多一个斜杠）签名 -> HTTP 401
```

跟 spa14 对比：spa14 的 `sign` 把 offset 编进去了（错太多会顶出时间窗口），
spa15 的 `token` 完全不含 offset，同一个 token 在有效期内可用于任意分页。

### 隔 200 秒跑两轮（见 §九）

## 九、「不是硬编码」的证据

`--twice --gap 200`：第 1 轮全量抓取 → 等 200 秒（超过 150 秒窗口）→
先把第 1 轮的旧 token 原样重放做**对照组**（预期 401）→ 再跑第 2 轮全量抓取（预期全 200）。

实测记录见 `data/spa15_twice.json`，摘要：

```
[2026-08-23T20:03:28+09:00] offset=0    ts=1787483008 token=MmU4Yjg1MjdjMTVkNzIxYTczZmMwMGMxMTAwOGM4Y2I0M2NjZDgzZiwxNzg3NDgzMDA4 -> HTTP 200
[2026-08-23T20:03:30+09:00] offset=10   ts=1787483010 token=MGZjMGQ3MmZlOTIyYzlkZGViODYwMjNmNWRjMzhlNTc5ZTliOWVjYSwxNzg3NDgzMDEw -> HTTP 200
[2026-08-23T20:03:32+09:00] offset=20   ts=1787483012 token=MDk3NThkMWMyMjk1ZjQxZmIxMzZmOWE4ZjliMWY2ZWQ1YTRmMDg1ZCwxNzg3NDgzMDEy -> HTTP 200
[2026-08-23T20:03:33+09:00] offset=30   ts=1787483013 token=NzI3ZGYxMTgzMDk2NmIxZmE4N2UwMGQ1MGRlMzIzZThiZTdiNDE3ZiwxNzg3NDgzMDEz -> HTTP 200
[2026-08-23T20:03:35+09:00] offset=40   ts=1787483015 token=YzJmOTNiZjU0Mzk5MTdiZWI0YjBkN2Y2MGZlMmZkYmQ0MzhlMmRhMCwxNzg3NDgzMDE1 -> HTTP 200
[2026-08-23T20:03:37+09:00] offset=50   ts=1787483017 token=MzdhZmE4Nzk4ODcyZDg4MGRkMTFiMWEyZTYwMmEwYTVkYjY1NjA4YywxNzg3NDgzMDE3 -> HTTP 200
[2026-08-23T20:03:38+09:00] offset=60   ts=1787483018 token=OTY3YTM3ZTlkZGFhYjg3MzY2NTVhMTQwYjg2NTE2YmM5Mjk3NTA2OSwxNzg3NDgzMDE4 -> HTTP 200
[2026-08-23T20:03:41+09:00] offset=70   ts=1787483020 token=ZjhkMjVhMDExMWU5YjE2NjMzZjRjYmNmMTVhY2M5Y2NkZGM5NWE2ZSwxNzg3NDgzMDIw -> HTTP 200
[2026-08-23T20:03:42+09:00] offset=80   ts=1787483022 token=MGJmMTBhOTY3ZjU4MDJkODIyYmE0OWFhMWUzZTUwMDAwZjRjYzNiMSwxNzg3NDgzMDIy -> HTTP 200
[2026-08-23T20:03:44+09:00] offset=90   ts=1787483024 token=OWI5OTQ3MmM2YmNlMTY1NzYyYjZjNjMxMDg5MGJhYzRlY2ZkMDc2OCwxNzg3NDgzMDI0 -> HTTP 200
[2026-08-23T20:03:45+09:00] offset=100  ts=1787483025 token=NzNmZDMzMjg4ODVmNzNmOWZmODk1ZmFiNDc2M2I1YWE1N2Y4MjYzNywxNzg3NDgzMDI1 -> HTTP 200
第 1 轮：count=104 实际取到 104 条

--- 等待 200s（超过实测有效期）---
[2026-08-23T20:07:05+09:00] 对照组：复用第 1 轮的旧 token（ts=1787483008） -> HTTP 401
[2026-08-23T20:07:07+09:00] offset=0    ts=1787483227 token=NGEyODg3MTA0MTdlZWMzMTNmMjczMmIxMjI5NjE4N2NkNmRhYzA3OSwxNzg3NDgzMjI3 -> HTTP 200
[2026-08-23T20:07:09+09:00] offset=10   ts=1787483229 token=YzBhNWRjYzA2MjY1ZjY5NWRlOTI4YTFhZjg5MzBlOTk4NGYxNjQ2NSwxNzg3NDgzMjI5 -> HTTP 200
[2026-08-23T20:07:10+09:00] offset=20   ts=1787483230 token=NTk5ZDUyNjNhMTczOTc5ZDZmODY4ZGQ3YTZlNzgzYmExZmNiMzY1NSwxNzg3NDgzMjMw -> HTTP 200
[2026-08-23T20:07:12+09:00] offset=30   ts=1787483232 token=MTUwMDI0ZmU4ZDhlZTU2OGY3NTQzZTE0MjcyNGUxYTkwZTE1Nzg5YiwxNzg3NDgzMjMy -> HTTP 200
[2026-08-23T20:07:13+09:00] offset=40   ts=1787483233 token=NDllMTYwNWM0YTZhNjQ3YTE3MzBmNjc5NzI4NTYzMTU0MWYwMjk2NCwxNzg3NDgzMjMz -> HTTP 200
[2026-08-23T20:07:15+09:00] offset=50   ts=1787483235 token=M2VjOWU4YTNmODE3ZjEzYjYxYTg2NWM5MGVjNzI4YmUzZDMyMjg3YSwxNzg3NDgzMjM1 -> HTTP 200
[2026-08-23T20:07:17+09:00] offset=60   ts=1787483237 token=ODY0Yzg0M2Y5Mzk4MTc3OGRkMjI4Nzk1ZDc2YzVhNWVhMjY3NmY1MCwxNzg3NDgzMjM3 -> HTTP 200
[2026-08-23T20:07:18+09:00] offset=70   ts=1787483238 token=YmRiODQ3MGE5YWNlZTJiYjFhMzJmY2JmOTUzNGQ4MjMzZGMyYmMyOSwxNzg3NDgzMjM4 -> HTTP 200
[2026-08-23T20:07:20+09:00] offset=80   ts=1787483240 token=YWIyMmFkMjlhMGQ1OWFlOTAyYmE2YzhlYTZmNzgyZDJiZWI1YzBkYiwxNzg3NDgzMjQw -> HTTP 200
[2026-08-23T20:07:22+09:00] offset=90   ts=1787483242 token=YmNjYWRkOTJhNDE0MjI4ZGVhYjk2MTBhNDkwNmNkOGI5MWMzNDNlYSwxNzg3NDgzMjQy -> HTTP 200
[2026-08-23T20:07:23+09:00] offset=100  ts=1787483243 token=MDkxZmM2NDNmZjk2ZGFjN2Q2MDk1Mzc2MjJmZjI3NjdkMTZlZDM5ZCwxNzg3NDgzMjQz -> HTTP 200
第 2 轮：count=104 实际取到 104 条
```

两轮相隔 202 秒（20:03:45 → 20:07:07），对照组重放旧 token **401**，第 2 轮 11 次请求**全 200**。
第 2 轮的 11 个 token 与第 1 轮**没有一个相同** —— 每次都是现从 wasm 内存里算出来的。

## 十、边界说明（做到哪、没做哪）

- **只有列表接口 `/api/movie/` 是 WASM 保护的。** `chunk-6a576d2b.e92742fa.js`（详情页）里
  grep `$wasm` 无命中，详情页 token 走的是 JS 侧 crypto-js，与 spa14 情况相同。
  本阶段只做列表接口。
- `data/spa15_movies.json` 因此是列表字段，不含 drama / 演职员等详情字段。
- 算法等价性是**行为验证**而非逐指令反编译，边界见 §四末尾的说明。
