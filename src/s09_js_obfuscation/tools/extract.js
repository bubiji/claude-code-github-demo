#!/usr/bin/env node
/*
 * extract.js —— 从**还原后**的 main.js 里取出 { key, players }（issue #12 / 阶段 9）
 *
 * 做法：给它一个假的 Vue，把 new Vue({...}) 的 options 接住，再调它的 data() 拿返回值。
 * 这不是「解析代码」，是「让代码自己把值算出来交给我们」—— 所以格式压成一行、
 * 属性名带转义、players 是变量还是字面量，都无所谓。
 *
 * CryptoJS 也给个桩：extract 阶段用不到加密，只要 getToken 定义时不报错即可。
 *
 * 用法: node extract.js <还原后的 main.js>   → stdout 输出 JSON
 */
'use strict';

const fs = require('fs');
const vm = require('vm');

const file = process.argv[2];
if (!file) { console.error('usage: node extract.js <deobfuscated.js>'); process.exit(2); }
const code = fs.readFileSync(file, 'utf8');

let captured = null;
function FakeVue(options) { captured = options; }
FakeVue.prototype = {};

// CryptoJS 桩：只需保证 getToken 方法体在**定义时**不炸；我们不在这里调它。
const stub = new Proxy(function () {}, {
  get: () => stub,
  apply: () => stub,
  construct: () => stub,
});

const sandbox = {
  Vue: FakeVue,
  CryptoJS: stub,
  console: { log() {}, error() {} },
  document: { getElementById: () => null, querySelector: () => null },
};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;
vm.createContext(sandbox);

try {
  vm.runInContext(code, sandbox, { timeout: 5000 });
} catch (e) {
  console.error('[extract] 执行报错: ' + e.message);
}

if (!captured) { console.error('[extract] 没有接到 new Vue(...)'); process.exit(1); }

let data = {};
try {
  data = typeof captured.data === 'function' ? captured.data.call({}) : (captured.data || {});
} catch (e) {
  console.error('[extract] data() 调用失败: ' + e.message);
  process.exit(1);
}

const players = (data.players || []).map((p) => ({
  name: p.name, image: p.image, birthday: p.birthday, height: p.height, weight: p.weight,
}));

process.stdout.write(JSON.stringify({ key: data.key, players }, null, 2));
