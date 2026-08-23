// issue: #11 · 案例: spa7 · 来源: https://spa7.scrape.center
//
// 交叉验证器：用 spa7 站点自己的 crypto-js.min.js（evidence/crypto-js.min.js，原样下载）
// 重跑 main.js 里的 getToken，输出 JSON 到 stdout，供 spider.py 与纯 Python DES 结果逐条比对。
//
// 用法: node verify_with_node.js <players.json>
//   players.json 形如 {"key": "...", "players": [{name,birthday,height,weight}, ...]}

const fs = require('fs');
const path = require('path');
const CryptoJS = require(path.join(__dirname, 'evidence', 'crypto-js.min.js'));

const input = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));

// 下面 5 行是 https://spa7.scrape.center/js/main.js 里 getToken 的原样逻辑（逐字，仅把 this.key 换成入参）
function getToken(player, rawKey) {
  let key = CryptoJS.enc.Utf8.parse(rawKey);
  const { name, birthday, height, weight } = player;
  let base64Name = CryptoJS.enc.Base64.stringify(CryptoJS.enc.Utf8.parse(name));
  let encrypted = CryptoJS.DES.encrypt(`${base64Name}${birthday}${height}${weight}`, key, {
    mode: CryptoJS.mode.ECB,
    padding: CryptoJS.pad.Pkcs7
  });
  return encrypted.toString();
}

const out = {};
for (const p of input.players) out[p.name] = getToken(p, input.key);
process.stdout.write(JSON.stringify(out, null, 2));
