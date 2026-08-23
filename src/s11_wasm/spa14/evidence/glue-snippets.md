# spa14 WASM 相关原件片段

> 本文件中所有 `代码块` 内容均为**逐字照抄**站点线上文件（压缩后的原样，未格式化、未改写）。
> 代码块之外的中文是本仓库的分析说明。

抓取时间：2026-08-23（UTC+8）

## 1. 文件来源

| 本地存证 | 线上 URL |
|---|---|
| `Wasm.wasm` | `https://spa14.scrape.center/js/Wasm.wasm`（232 字节） |
| `Wasm.wat` | 由 `wasm2wat Wasm.wasm` 生成（wabt 1.0.41） |
| `js/app.f40e6942.js` | `https://spa14.scrape.center/js/app.f40e6942.js` |
| `js/chunk-67143ceb.69ecbfaf.js` | `https://spa14.scrape.center/js/chunk-67143ceb.69ecbfaf.js`（列表页 + Emscripten 胶水） |
| `js/chunk-6a576d2b.a19c781e.js` | `https://spa14.scrape.center/js/chunk-6a576d2b.a19c781e.js`（详情页） |

说明：`.wasm` 的落点容易踩坑——Emscripten 胶水里只写了裸文件名 `Wasm.wasm`，实际 URL 是
`/js/Wasm.wasm`（webpack publicPath 拼上去的）。直接请求 `https://spa14.scrape.center/Wasm.wasm`
会拿到 SPA 的 `index.html`（HTTP 200，1007 字节，开头是 `<!DOCTYPE html>`），不是 wasm，
靠 magic number `00 61 73 6d` 才能分辨。

## 2. wasm 文件名（`chunk-67143ceb.69ecbfaf.js` 原文）

```js
var lt="Wasm.wasm";function ht(t){try{if(t==lt&&E)return new Uint8Array(E);if(w)return w(t);throw"both async and sync fetching of the wasm failed"}catch(S){ot(S)}}
```

## 3. 实例化（`chunk-67143ceb.69ecbfaf.js` 原文）

```js
function vt(){var n={env:gt,wasi_snapshot_preview1:gt};function e(n,e){var r=n.exports;t["asm"]=r,j=t["asm"]["memory"],B(j.buffer),G=t["asm"]["__indirect_function_table"],it("wasm-instantiate")}
```

说明：胶水给出了 `env` 与 `wasi_snapshot_preview1` 两个 import 对象，但 spa14 的这份 wasm
**一个 import 都没有**（见 `exports.txt`），所以脱离浏览器加载时不需要提供任何 import。

## 4. 调用点（`chunk-67143ceb.69ecbfaf.js` 原文，列表页 `onFetchData`）

```js
onFetchData:function(){var t=this;this.loading=!0;var n=(this.page-1)*this.limit,e=this.$wasm.asm.encrypt(n,parseInt(Math.round((new Date).getTime()/1e3).toString()));this.$axios.get(this.$store.state.url.index,{params:{limit:this.limit,offset:n,sign:e}}).then((function(n){var e=n.data,r=e.results,i=e.count;t.loading=!1,t.movies=r,t.total=i}))}
```

说明（自撰）：

- `n` = `(page-1) * limit` = offset
- 第二个入参是**秒级时间戳**（`Date.getTime()/1000` 四舍五入后 `parseInt`）
- 直接走 `$wasm.asm.encrypt(...)`，**不经过 `ccall`**——因为两个入参和返回值都是数字，
  不需要线性内存参与。这正是「数值型 WASM」的定义。
- 结果放进 query 参数 `sign`

## 5. 详情页不是 WASM（`chunk-6a576d2b.a19c781e.js` 原文）

```js
onFetchData:function(){var t=this;this.loading=!0;var s=n(this.$store.state.url.detail,{key:this.key}),e=Object(o["a"])(s);this.$axios.get(s,{params:{token:e}}).then((function(s){var e=s.data;t.loading=!1,t.movie=e}))}
```

其中模块引用为：

```js
i=[],o=(e("a481"),e("7d92")),r=e("3e22"),n=e("1a7b"),l={name:"Det
```

说明（自撰）：详情页的 `token` 来自 JS 模块 `7d92`（crypto-js 的 sha1，属 spa6 那一路），
`$wasm` 在详情页组件里**完全没出现**。所以 spa14 的 WASM 只保护列表接口 `/api/movie/`，
本阶段的作业范围就到列表接口为止。

## 6. 反汇编结论

`Wasm.wat` 里 `encrypt` 是 func 4，整个函数体只有 5 条指令：

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

即 `sign = offset + trunc(ts / 3) + 16358`。
