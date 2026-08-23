#!/usr/bin/env node
/*
 * reftoken.js —— 用**站点自带的 crypto-js.min.js** 算一次 token，作为 Python 实现的对照基准
 * （issue #12 / 阶段 9）
 *
 * 逆向最容易骗自己的一步是「我照着还原后的代码写了 Python，看起来对」。
 * 这个脚本把还原出来的 JS 原样跑一遍（用的就是站点下发的那份 crypto-js），
 * 输出和 Python 逐字节比对 —— 对不上就是复刻错了，不是「大概齐」。
 *
 * crypto-js.min.js 来自 https://spa8.scrape.center/js/crypto-js.min.js（六站同一份），
 * 存放于 ../vendor/crypto-js.min.js。
 *
 * 用法: node reftoken.js <site_key> '<player JSON>'
 */
'use strict';

const path = require('path');
const CryptoJS = require(path.join(__dirname, '..', 'vendor', 'crypto-js.min.js'));

const siteKey = process.argv[2];
const player = JSON.parse(process.argv[3]);

// ↓↓↓ 以下 6 行是六个站还原后一字不差的 getToken 方法体 ↓↓↓
let key = CryptoJS.enc.Utf8.parse(siteKey);
const { name, birthday, height, weight } = player;
let base64Name = CryptoJS.enc.Base64.stringify(CryptoJS.enc.Utf8.parse(name));
let encrypted = CryptoJS.DES.encrypt(`${base64Name}${birthday}${height}${weight}`, key, {
  mode: CryptoJS.mode.ECB,
  padding: CryptoJS.pad.Pkcs7,
});
process.stdout.write(encrypted.toString());
