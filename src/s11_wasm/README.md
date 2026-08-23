> issue: #14 · 阶段 11 · 来源: https://scrape.center/

# 阶段 11 —— WASM 逆向

两个案例的差别只有一处：**数值型 vs 字符串型**。这正是 WASM 逆向的分水岭。

| | spa14（数值型） | spa15（字符串型） |
|---|---|---|
| wasm 体积 | 232 字节 | 19231 字节 |
| import | **0 个** | `wasi_snapshot_preview1.proc_exit` |
| 导出的 `encrypt` 签名 | `(i32, i32) -> i32` | `(i32, i32) -> i32`（**完全一样**） |
| 这些 i32 是什么 | 数值本身 | **线性内存指针** |
| JS 调用方式 | `$wasm.asm.encrypt(offset, ts)` | `$wasm.ccall("encrypt","string",["string","string"],[url, ts])` |
| 要不要管内存 | 不要 | 要：`stackSave` / `stackAlloc` / 写 UTF-8 / 读 NUL 结尾串 / `stackRestore` |
| 有没有 malloc | 无所谓 | **没有导出 malloc**，只能用影子栈 |
| 算法 | `sign = offset + trunc(ts/3) + 16358` | `token = base64(sha1_hex("/api/movie,"+ts) + "," + ts)` |
| 逆向手段 | 反汇编（5 条指令，一眼看穿） | 行为观测 + 数据段佐证（C++ 产物，627 行 wat） |
| 参数落点 | query `sign` | query `token` |
| offset 参与签名 | 是 | 否 |
| 时间窗口（实测） | `|ts - now| ≤ 150s` 通过，180s → 401 | 同左 |

**最容易翻车的一点**：两个模块导出的 `encrypt` 签名一字不差，都是 `(i32,i32)->i32`。
WASM 的类型系统里根本没有字符串，只有 i32/i64/f32/f64。到底是「数」还是「指针」，
**光看 wasm 判断不了，必须看 JS 怎么调它**。

两个案例的详细分析、逆向过程、实测输出与边界说明分别见：

- [`spa14/README.md`](spa14/README.md)
- [`spa15/README.md`](spa15/README.md)

## 共同的坑

1. **`.wasm` 的真实 URL**。Emscripten 胶水里写的是裸名 `Wasm.wasm`，实际在 `/js/Wasm.wasm`。
   请求 `/Wasm.wasm` 会拿到 **HTTP 200 的 `index.html`**（SPA fallback），
   只能靠 magic number `00 61 73 6d` 分辨，看状态码发现不了。
2. **WASM 只保护列表接口**。两个站的详情页组件里 `$wasm` 都没出现，
   详情 token 走的是 JS 侧 crypto-js（spa6 那一路）。本阶段只做列表接口，
   不为了凑数据把详情顺手实现掉。
3. **不许硬编码浏览器里抓来的参数**——有效期只有 ±150 秒。两个案例都提供
   `--twice --gap 200` 模式：跑两轮 + 中间重放旧参数做对照组，
   同时证明「本轮是现算的」和「旧参数确实会过期」。

## 额外依赖（不进仓库根 requirements.txt）

```bash
.venv/bin/pip install wasmtime      # 实测 48.0.0
brew install wabt                   # 实测 1.0.41，只在反汇编时需要
```
