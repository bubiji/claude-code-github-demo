# spa15 WASM 相关原件片段

> 本文件中所有 `代码块` 内容均为**逐字照抄**站点线上文件（压缩后的原样，未格式化、未改写）。
> 代码块之外的中文是本仓库的分析说明。

抓取时间：2026-08-23（UTC+8）

## 1. 文件来源

| 本地存证 | 线上 URL |
|---|---|
| `Wasm.wasm` | `https://spa15.scrape.center/js/Wasm.wasm`（19231 字节） |
| `Wasm.encrypt.wat` | 由 `wasm2wat Wasm.wasm` 生成后截取 func 24 与 import/export 段（wabt 1.0.41）；完整 wat 9269 行 / 232 KB，不入库 |
| `js/app.f2087057.js` | `https://spa15.scrape.center/js/app.f2087057.js` |
| `js/chunk-1e26c652.6d5384a8.js` | `https://spa15.scrape.center/js/chunk-1e26c652.6d5384a8.js`（列表页 + Emscripten 胶水） |
| `js/chunk-6a576d2b.e92742fa.js` | `https://spa15.scrape.center/js/chunk-6a576d2b.e92742fa.js`（详情页） |

同 spa14：胶水里写的是裸名 `Wasm.wasm`，真实 URL 是 `/js/Wasm.wasm`；请求根路径的
`/Wasm.wasm` 会返回 SPA 的 `index.html`。

## 2. wasm 文件名（`chunk-1e26c652.6d5384a8.js` 原文）

```js
var lt="Wasm.wasm";function ht(t){try{if(t==lt&&E)return new Uint8Array(E);if(w)return w(t);throw"both async and sync fetching of the wasm failed"}catch(S){ot(S)}}
```

## 3. 调用点（`chunk-1e26c652.6d5384a8.js` 原文，列表页 `onFetchData`）

```js
onFetchData:function(){var t=this;this.loading=!0;var n=(this.page-1)*this.limit,e=this.$wasm.ccall("encrypt","string",["string","string"],[this.$store.state.url.index,Math.round((new Date).getTime()/1e3).toString()]);this.$axios.get(this.$store.state.url.index,{params:{limit:this.limit,offset:n,token:e}}).then((function(n){var e=n.data,r=e.results,i=e.count;t.loading=!1,t.movies=r,t.total=i}))}
```

`$store.state.url` 的定义（`app.f2087057.js` 原文）：

```js
url:{index:"/api/movie",detail:"/api/movie/{key}"}
```

说明（自撰）：

- `encrypt` 的两个入参是**字符串**：`"/api/movie"` 和秒级时间戳的**十进制字符串**
- 返回值也是**字符串**（`ccall` 的第二个参数 `"string"`）
- 注意这里跟 spa14 不同：offset 不参与签名，只有 URL 和时间戳参与

## 4. Emscripten `ccall` 的实现（`chunk-1e26c652.6d5384a8.js` 原文）

```js
function L(t,n,e,r,i){var o={string:function(t){var n=0;if(null!==t&&void 0!==t&&0!==t){var e=1+(t.length<<2);n=xt(e),N(t,n,e)}return n},array:function(t){var n=xt(t.length);return D(t,n),n}};function a(t){return"string"===n?W(t):"boolean"===n?Boolean(t):t}var c=I(t),u=[],s=0;if(r)for(var f=0;f<r.length;f++){var l=o[e[f]];l?(0===s&&(s=bt()),u[f]=l(r[f])):u[f]=r[f]}var h=c.apply(null,u);return h=a(h),0!==s&&_t(s),h}
```

说明（自撰）——**这段就是「字符串型 WASM」的全部机关**，混淆后的短名对应关系：

| 混淆名 | Emscripten 原名 | 作用 |
|---|---|---|
| `bt()` | `stackSave()` | 记下当前栈指针 |
| `xt(e)` | `stackAlloc(e)` | 在 wasm 线性内存的栈上分配 `e` 字节 |
| `N(t,n,e)` | `stringToUTF8(str, ptr, maxBytes)` | 把 JS 字符串按 UTF-8 写进 `memory.buffer[ptr..]`，补 `\0` |
| `W(t)` | `UTF8ToString(ptr)` | 从 `ptr` 读到第一个 `\0`，按 UTF-8 解码 |
| `_t(s)` | `stackRestore(s)` | 还原栈指针，释放这一轮分配 |
| `I(t)` | `getCFunc(name)` | 取 `Module.asm[name]` |

流程固定为：`stackSave` → 每个字符串参数 `stackAlloc(1 + len*4)` + `stringToUTF8` →
用**指针**（i32）调用导出函数 → 返回值是**指针**，`UTF8ToString` 读回 → `stackRestore`。

`1 + (t.length << 2)` 是按「每个 UTF-16 码元最多 4 字节 UTF-8」取的最坏上界；
本仓库的 Python 实现直接按实际 UTF-8 字节数 + 1 分配，等价。

`UTF8ToString` 的解码入口（`chunk-1e26c652.6d5384a8.js` 原文）：

```js
function U(t,n,e){var r=n+e,i=n;while(t[i]&&!(i>=r))++i;if(i-n>16&&t.subarray&&C)return C.decode(t.subarray(n,i));
```

即「从 ptr 往后扫到第一个 0 字节」——所以 Python 侧必须自己做同样的 NUL 扫描。

## 5. 导出与导入（`exports.txt`）

```
== IMPORTS ==
  wasi_snapshot_preview1.proc_exit :: func ['i32'] -> []
== EXPORTS ==
  memory :: MemoryType
  encrypt :: func ['i32', 'i32'] -> ['i32']
  __indirect_function_table :: TableType
  _initialize :: func [] -> []
  stackSave :: func [] -> ['i32']
  stackRestore :: func ['i32'] -> []
  stackAlloc :: func ['i32'] -> ['i32']
```

说明（自撰）：

1. `encrypt` 的签名是 `(i32, i32) -> i32` —— 跟 spa14 **一模一样**。光看签名分不出数值型
   还是字符串型，只有看 JS 调用方式（`asm.encrypt` 直调 vs `ccall(...,"string",...)`）才知道
   这三个 i32 是数值还是指针。这是本阶段最容易翻车的地方。
2. **没有 `malloc` / `free` 导出**，所以字符串只能走 `stackAlloc`（栈分配），这与 Emscripten
   `ccall` 的做法一致。
3. 有一个 WASI import `proc_exit`，脱离浏览器加载时必须提供（给个空实现即可）。

## 6. 数据段里的算法线索（`Wasm.encrypt.wat` 尾部，原样截取）

```wat
  (data (;3;) (i32.const 2048) "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/")
  (data (;4;) (i32.const 2128) "0123456789abcdef\00allocator<T>::allocate(size_t n) 'n' exceeds maximum supported size\00basic_string\00...
```

说明（自撰）：标准 base64 字母表 + 十六进制字母表 + C++ `std::string`/`std::vector` 的异常
字符串，指向「hex 摘要 → 拼接 → base64」这条链路，与实测结果吻合。

## 7. 详情页不是 WASM

`chunk-6a576d2b.e92742fa.js` 里 grep `$wasm` 无命中，与 spa14 一致：WASM 只保护列表接口。
