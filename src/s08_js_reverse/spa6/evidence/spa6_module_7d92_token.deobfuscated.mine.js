// ⚠️ 这个文件不是原件，是我（本仓库作者）手写的还原版，用来读懂上面那份混淆代码。
// 原件在同目录 spa6_chunk-4dec7ef0_module_7d92_token.js，以那份为准；本文件只是注释。
//
// 还原方式：把 _0x 变量按用途重命名、['xxx'] 成员访问改回 .xxx、十六进制字面量换成十进制。
// 没有改动任何一步计算。

'7d92': function (module, exports, __webpack_require__) {
  'use strict';
  __webpack_require__('6b54');                                  // core-js polyfill，与算法无关
  var CryptoJS = __webpack_require__('3452');                   // crypto-js
  var Base64 = __webpack_require__('27ae').Base64;              // js-base64（spa2 这里用的是 CryptoJS.enc.Base64）

  function encrypt() {
    var t = Math.round(new Date().getTime() / 1000).toString(); // 0x3e8 = 1000，秒级时间戳
    var args = Array.prototype.slice.call(arguments);           // 原文是 for 循环手动拷 arguments
    args.push(t);                                               // 时间戳永远追加在最后一位
    var sha1hex = CryptoJS.SHA1(args.join(',')).toString(CryptoJS.enc.Hex);
    return Base64.encode([sha1hex, t].join(','));               // token = base64(sha1hex + "," + t)
  }

  exports['a'] = encrypt;
}
