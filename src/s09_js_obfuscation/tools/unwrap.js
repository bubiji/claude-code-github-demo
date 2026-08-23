#!/usr/bin/env node
/*
 * unwrap.js —— 通用「自解码型混淆」还原器（issue #12 / 阶段 9）
 *
 * 适用：JJEncode(spa10) / AAEncode(spa11) / JSFuck(spa12) 以及任何
 *      「一堆符号 → 最终拼出源码字符串 → 交给 Function/eval 执行」的混淆。
 *
 * 原理（这三种混淆的共同命门）：
 *   它们本身不隐藏语义，只是把「源码字符串」用符号运算重新拼出来，
 *   最后必须把这个字符串交给一个**代码执行入口**。JS 里能吃字符串当代码的入口只有两个：
 *     1) eval
 *     2) Function 构造器
 *   而混淆代码拿不到全局 `Function` 标识符（那太显眼），一律绕道原型链取：
 *     JJEncode : (1)["constructor"]["constructor"]   →  Number.constructor
 *     JSFuck   : [][ "filter" ]["constructor"]       →  Function.prototype.constructor
 *     AAEncode : (ﾟДﾟ)['_'] ，同样落到 constructor 上
 *   这三条路的终点都是 **Function.prototype.constructor**。
 *   所以只要把 Function.prototype.constructor 换成一个「先记账、再放行」的探针，
 *   payload 源码就会在执行前落到我们手里 —— 不需要看懂一个颜文字。
 *
 * 用法:
 *   node unwrap.js <混淆文件> [--out 输出文件] [--no-exec]
 *   --no-exec : 探针只记账不放行（更安全，但拿不到二级 payload）
 *
 * 安全说明：默认仍会在 Node 里执行还原出的代码。目标 payload 依赖 Vue / CryptoJS，
 * Node 里必然抛 ReferenceError —— 那时源码早已被捕获，报错反而是我们要的「刹车」。
 */
'use strict';

const fs = require('fs');
const path = require('path');

const args = process.argv.slice(2);
if (args.length === 0) {
  console.error('usage: node unwrap.js <file> [--out out.js] [--no-exec]');
  process.exit(2);
}
const src = fs.readFileSync(args[0], 'utf8');
const outIdx = args.indexOf('--out');
const outFile = outIdx >= 0 ? args[outIdx + 1] : null;
const allowExec = !args.includes('--no-exec');

const captured = [];
const RealFunction = Function;

function record(kind, code) {
  if (typeof code === 'string' && code.length > 0) {
    captured.push({ kind, len: code.length, code });
  }
}

// ---- 探针 1：Function 构造器（JJEncode / JSFuck / AAEncode 都走这条） ----
function FunctionProbe(...fnArgs) {
  const body = fnArgs.length ? fnArgs[fnArgs.length - 1] : '';
  record('Function', body);
  if (!allowExec) return function () { return ''; };
  try {
    return RealFunction(...fnArgs);
  } catch (e) {
    return function () { return ''; };
  }
}
FunctionProbe.prototype = RealFunction.prototype;

// 关键一步：改写原型上的 constructor，凡是绕道 x.constructor.constructor 的全部中招
Object.defineProperty(Function.prototype, 'constructor', {
  value: FunctionProbe,
  writable: true,
  configurable: true,
});

// ---- 探针 2：eval（packer 型混淆走这条） ----
const realEval = eval;
globalThis.eval = function (code) {
  record('eval', code);
  if (!allowExec) return undefined;
  try { return realEval(code); } catch (e) { return undefined; }
};

// 让 payload 里对 window/document 的引用不至于第一行就炸掉
if (typeof globalThis.window === 'undefined') globalThis.window = globalThis;

let runErr = null;
try {
  // 用 indirect eval 在全局作用域跑，尽量贴近浏览器
  (0, realEval)(src);
} catch (e) {
  runErr = e;
}

if (captured.length === 0) {
  console.error('[unwrap] 未捕获到任何 payload。');
  if (runErr) console.error('[unwrap] 执行报错:', runErr.message);
  process.exit(1);
}

// 取「最后捕获的那一段」作为最终 payload。
// 顺序即层级：JJEncode 先捕到 `return"<转义源码>"` 的包装层（更长），
// 紧接着才是真正被执行的源码（更短）。所以按长度挑是错的，按顺序挑才对。
console.error(`[unwrap] 捕获 ${captured.length} 段代码，入口顺序: ` +
  JSON.stringify(captured.map((c) => `${c.kind}/${c.len}B`)));
if (runErr) {
  console.error(`[unwrap] payload 执行在 Node 里抛错（预期内，缺 Vue/CryptoJS）: ${runErr.message}`);
}

let out = captured[captured.length - 1].code;
// 兜底：若最后一段仍是 `return"...."` 形式的包装层（--no-exec 时会这样），
// 用真 Function 把字符串字面量求值出来（含 \156 这类八进制转义，JSON.parse 处理不了）。
if (/^\s*return\s*['"]/.test(out)) {
  try { out = RealFunction(out)(); } catch (e) { /* keep raw */ }
}

if (outFile) {
  fs.mkdirSync(path.dirname(outFile), { recursive: true });
  fs.writeFileSync(outFile, out, 'utf8');
  console.error(`[unwrap] 已写出 ${outFile} (${out.length} bytes)`);
} else {
  process.stdout.write(out);
}
