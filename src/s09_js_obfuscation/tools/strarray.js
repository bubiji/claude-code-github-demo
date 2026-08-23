#!/usr/bin/env node
/*
 * strarray.js —— javascript-obfuscator「字符串数组」还原器（issue #12 / 阶段 9，spa13）
 *
 * 针对 obfuscator.io（javascript-obfuscator）的默认三件套：
 *   ① 所有字面量抽进一个大数组      const _0x4afa = ['\x31\x39...', ...];
 *   ② 数组被旋转 N 次               (function(a,b){while(--b){a.push(a.shift())}}(_0x4afa, 0xed));
 *   ③ 取值走一个下标解码器          const _0x3431 = function(i){ return _0x4afa[i - 0x0] };
 *      并给解码器起若干别名          const _0x5e920f = _0x3431, _0x3c8dcd = _0x5e920f, ...
 *   ④ 剩下的标识符/属性名全部 \xNN 十六进制转义
 *
 * 还原三步（和上面一一对应，都不需要人肉读代码）：
 *   1. 把「数组声明 + 旋转 IIFE + 解码器声明」这段**前言**原样丢进 Node vm 跑一遍。
 *      旋转是运行时行为，静态读数组只会拿到错位的字符串 —— 必须真跑。
 *   2. 从 vm 里取出解码器，把源码里每一处 `别名('0x2f')` 就地换成它的真实返回值。
 *   3. 扫一遍字符串字面量，把 \xNN / \uNNNN 转义还原成可读字符，顺手做极简换行排版。
 *
 * 用法: node strarray.js <混淆文件> [--out 输出文件]
 */
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const args = process.argv.slice(2);
if (!args.length) {
  console.error('usage: node strarray.js <file> [--out out.js]');
  process.exit(2);
}
const src = fs.readFileSync(args[0], 'utf8');
const outIdx = args.indexOf('--out');
const outFile = outIdx >= 0 ? args[outIdx + 1] : null;

// ---------- 步骤 1：定位并执行「前言」 ----------
const arrDecl = /^(?:const|let|var)\s+(_0x[0-9a-f]+)\s*=\s*\[/.exec(src);
if (!arrDecl) { console.error('[strarray] 没找到字符串数组声明'); process.exit(1); }
const arrName = arrDecl[1];

// 解码器：形如 const _0x3431=function(a,b){ ... _0x4afa[a] ... };
// 注意不能取第一个匹配 —— 旋转 IIFE 内部也声明了一个 function，
// 真正的解码器的**判据是函数体里引用了字符串数组本身**。
const decRe = new RegExp(
  '(?:const|let|var)\\s+(_0x[0-9a-f]+)\\s*=\\s*function\\s*\\([^)]*\\)\\s*\\{[\\s\\S]*?\\};',
  'g'
);
let decM = null;
for (let m; (m = decRe.exec(src));) {
  if (m[0].includes(arrName)) { decM = m; break; }
}
if (!decM) { console.error('[strarray] 没找到下标解码器'); process.exit(1); }
const decName = decM[1];
const prologue = src.slice(0, decM.index + decM[0].length);

const ctx = { console };
vm.createContext(ctx);
vm.runInContext(prologue + `\n;globalThis.__dec = ${decName}; globalThis.__arr = ${arrName};`, ctx);
const dec = ctx.__dec;
console.error(`[strarray] 前言执行完成：数组 ${arrName}（${ctx.__arr.length} 项，已旋转），解码器 ${decName}`);

// ---------- 步骤 2：把解码器调用替换成真实字符串 ----------
// 先收集解码器的所有别名（obfuscator 会给每个函数作用域再起一个局部名）
const aliases = new Set([decName]);
let grew = true;
while (grew) {
  grew = false;
  for (const a of [...aliases]) {
    const re = new RegExp('(?:const|let|var)\\s+(_0x[0-9a-f]+)\\s*=\\s*' + a + '\\b', 'g');
    let m;
    while ((m = re.exec(src))) {
      if (!aliases.has(m[1])) { aliases.add(m[1]); grew = true; }
    }
  }
}
console.error(`[strarray] 解码器别名 ${aliases.size} 个: ${[...aliases].join(', ')}`);

const callRe = new RegExp('\\b(' + [...aliases].join('|') + ")\\s*\\(\\s*('(?:\\\\.|[^'])*'|\"(?:\\\\.|[^\"])*\")\\s*\\)", 'g');
let hits = 0;
let body = src.slice(prologue.length).replace(callRe, (whole, _fn, litRaw) => {
  let lit;
  try { lit = new Function('return ' + litRaw)(); } catch (e) { return whole; }
  let val;
  try { val = dec(lit); } catch (e) { return whole; }
  if (typeof val !== 'string') return whole;
  hits += 1;
  return JSON.stringify(val);
});
console.error(`[strarray] 替换解码器调用 ${hits} 处`);

// 去掉「解码器别名声明」这类还原后已无意义的残留
body = body.replace(/(?:const|let|var)\s+_0x[0-9a-f]+\s*=\s*(?:_0x[0-9a-f]+)\s*,\s*/g, 'const ');
body = body.replace(/(?:const|let|var)\s+_0x[0-9a-f]+\s*=\s*(?:_0x[0-9a-f]+)\s*;/g, '');

// ---------- 步骤 3：字符串字面量去转义 ----------
// 手写扫描器而不是全局正则：只有确定当前在字符串里，才敢动 \xNN。
// 同时记录哪些区间是字符串，后面两步（成员访问简化、排版）靠它避开字符串内部。
function detox(code) {
  let out = '';
  const strRanges = [];
  let i = 0;
  while (i < code.length) {
    const ch = code[i];
    if (ch === '"' || ch === "'" || ch === '`') {
      const quote = ch;
      let j = i + 1;
      while (j < code.length) {
        if (code[j] === '\\') { j += 2; continue; }
        if (code[j] === quote) break;
        j += 1;
      }
      const raw = code.slice(i, j + 1);
      let emit = raw;
      if (quote !== '`') {                 // 模板串原样保留
        try { emit = JSON.stringify(new Function('return ' + raw)()); } catch (e) { emit = raw; }
      }
      strRanges.push([out.length, out.length + emit.length]);
      out += emit;
      i = j + 1;
      continue;
    }
    out += ch;
    i += 1;
  }
  return { code: out, strRanges };
}

// obj["prop"] → obj.prop ，{"key": v} → {key: v}
// 只对「整体就是一个字符串字面量」的位置动手，所以不会碰到字符串内部的同形文本。
function simplifyAccess(code) {
  return code
    .replace(/\[\s*"([A-Za-z_$][\w$]*)"\s*\]/g, '.$1')
    .replace(/(^|[{,])\s*"([A-Za-z_$][\w$]*)"\s*:/g, '$1$2:');
}

// 极简排版：只在语句/结构边界换行，且靠 detox 重扫一遍来确定是否处在字符串里。
function format(code) {
  const { strRanges } = detox(code);
  const inStr = new Uint8Array(code.length);
  for (const [a, b] of strRanges) for (let k = a; k < b; k++) inStr[k] = 1;
  let out = '';
  let indent = 0;
  const nl = () => { out += '\n' + '  '.repeat(Math.max(0, indent)); };
  for (let i = 0; i < code.length; i++) {
    const ch = code[i];
    if (inStr[i]) { out += ch; continue; }
    if (ch === '{' || ch === '[') { indent += 1; out += ch; nl(); continue; }
    if (ch === '}' || ch === ']') { indent -= 1; nl(); out += ch; continue; }
    if (ch === ';' || ch === ',') { out += ch; nl(); continue; }
    out += ch;
  }
  return out.replace(/\n[ \t]*\n+/g, '\n');
}

const result = format(simplifyAccess(detox(body).code)).trim() + '\n';

if (outFile) {
  fs.mkdirSync(path.dirname(outFile), { recursive: true });
  fs.writeFileSync(outFile, result, 'utf8');
  console.error(`[strarray] 已写出 ${outFile} (${result.length} bytes)`);
} else {
  process.stdout.write(result);
}
