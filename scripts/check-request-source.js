#!/usr/bin/env node
/**
 * 请求出口↔URL声明单一源对账守卫 (F292, 2026-08-05 猴王自驱lint轮)
 *
 * 小程序网络栈无任何编译期约束: wx.request 随处可调, URL 字面量随处可写。
 * 本仓既定架构: services/api.js 是唯一请求出口(统一 token 注入/超时/重试/
 * {code,message,data}信封解析/错误提示), config/index.js 是唯一 URL 声明源
 * (dev/staging/prod 三环境 API_BASE_URL)。两类静默漂移:
 *   ① 出口旁路: 页面/组件直调 wx.request/wx.uploadFile/wx.downloadFile →
 *      绕过 token 注入(鉴权静默失败)+绕过信封解析(拿到裸response误当data)+
 *      绕过统一超时/重试/加载提示, 且真机域名白名单校验面扩大
 *   ② URL 多源: http(s):// 字面量散落在 api/config 之外 → 环境切换(dev/prod)
 *      时硬编码地址不跟随, 线上静默打错端点(与 F89 HTTPS 漂移同族前置)
 *
 * 不变量(双单一源成对):
 *   出口侧: wx.request/uploadFile/downloadFile 调用点集 ⊆ ALLOWED_REQUEST_FILES
 *   声明侧: http(s):// 字符串字面量出现点集 ⊆ ALLOWED_URL_FILES
 *   wx.requestPayment 是微信支付 API 非 HTTP 出口, 不在断言集(整词匹配排除)。
 *   注释中的 URL 不计(文档性引用无害), 用字符级状态机剥离注释(保字符串内容)。
 *
 * HTTPS 方案级断言不在本轮: prod 现为 http://, 微信正式版强制 HTTPS(F89),
 * 升级依赖云端 https 域名就绪(大圣侧)——届时在本守卫加方案断言同 commit 收敛。
 *
 * 扫描范围: app.js + pages/ components/ services/ utils/ config/ 全部 .js
 * (排除 node_modules/scripts/coverage/dist/build/miniprogram_npm/__tests__;
 *  F270 口径 + __tests__ 豁免——测试夹具钉死字面值是断言前提不是漂移)。
 *
 * 用法: node scripts/check-request-source.js
 * 缺输入(零个应用js)/任一集合为空(提取器失效信号)/任一断言失败 → exit 1 不放行 (F212)
 */
'use strict';

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const SCAN_DIRS = ['pages', 'components', 'services', 'utils', 'config'];
// __tests__ 排除: 测试夹具必须钉死字面值断言(config 值/URL 解析), 属验证脚手架非出厂代码
// (首跑撞出 api.test/perf.test/config.test 六处合法字面量, 同 commit 豁免)
const EXCLUDE_DIRS = new Set(['node_modules', 'scripts', 'coverage', 'dist', 'build', 'miniprogram_npm', '__tests__']);

// 唯一允许的请求出口文件(项目根相对, posix 分隔符)
const ALLOWED_REQUEST_FILES = ['services/api.js'];
// 唯一允许的 URL 字面量声明文件
const ALLOWED_URL_FILES = ['config/index.js'];

// HTTP 出口 API: request/uploadFile/downloadFile; requestPayment 整词不匹配(后缀Payment挡住\s*\()
const REQUEST_RE = /\bwx\.(?:request|uploadFile|downloadFile)\s*\(/g;
// URL 字面量(剥注释后匹配, 只落在字符串/模板串内)
const URL_RE = /https?:\/\/[^\s'"`)}\]>]+/g;

/**
 * 字符级状态机剥注释: code/line/block/sq/dq/tq 六态(查表驱动, 无长分支链)。
 * 字符串(含模板串)内容原样保留——URL 字面量在字符串里必须被匹配;
 * 注释内容丢弃——scan.js 类文档注释里的示例 URL 不得误报。
 */
const STATE_OF_QUOTE = { "'": 'sq', '"': 'dq', '`': 'tq' };
const QUOTE_OF_STATE = { sq: "'", dq: '"', tq: '`' };

function stripComments(src) {
  let out = '';
  let state = 'code';
  let i = 0;
  const n = src.length;
  while (i < n) {
    const c = src[i];
    const d = i + 1 < n ? src[i + 1] : '';
    if (state === 'line') {
      if (c === '\n') { state = 'code'; out += c; }
      i += 1; continue;
    }
    if (state === 'block') {
      if (c === '*' && d === '/') { state = 'code'; out += '  '; i += 2; continue; }
      if (c === '\n') out += c;
      i += 1; continue;
    }
    if (state !== 'code') {
      // 字符串态: 转义对整体保留
      if (c === '\\') { out += c + d; i += 2; continue; }
      if (QUOTE_OF_STATE[state] === c) state = 'code';
      out += c; i += 1; continue;
    }
    // code 态
    if (c === '/' && d === '/') { state = 'line'; out += '  '; i += 2; continue; }
    if (c === '/' && d === '*') { state = 'block'; out += '  '; i += 2; continue; }
    if (Object.hasOwn(STATE_OF_QUOTE, c)) state = STATE_OF_QUOTE[c];
    out += c; i += 1;
  }
  return out;
}

function collectJsFiles(dir, out) {
  if (!fs.existsSync(dir)) return;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (EXCLUDE_DIRS.has(entry.name)) continue;
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) collectJsFiles(full, out);
    else if (entry.isFile() && entry.name.endsWith('.js')) out.push(full);
  }
}

function lineOf(text, idx) {
  let line = 1;
  for (let i = 0; i < idx && i < text.length; i += 1) {
    if (text[i] === '\n') line += 1;
  }
  return line;
}

const files = [];
const appFile = path.join(ROOT, 'app.js');
if (fs.existsSync(appFile)) files.push(appFile);
for (const d of SCAN_DIRS) collectJsFiles(path.join(ROOT, d), files);

if (files.length === 0) {
  console.error('❌ 缺输入: 未找到任何应用侧 .js 文件 (app.js / pages / components / services / utils / config)');
  process.exit(1);
}

const requestSites = []; // { rel, line }
const urlSites = [];     // { rel, line, url }
let commentUrlSkipped = 0;

for (const f of files) {
  const raw = fs.readFileSync(f, 'utf8');
  const rel = path.relative(ROOT, f).split(path.sep).join('/');
  const stripped = stripComments(raw);
  // 注释里被剥掉的 URL 计数(报告用): 差集口径
  const rawUrls = raw.match(URL_RE) || [];
  const strippedUrls = stripped.match(URL_RE) || [];
  commentUrlSkipped += Math.max(0, rawUrls.length - strippedUrls.length);

  let m;
  REQUEST_RE.lastIndex = 0;
  while ((m = REQUEST_RE.exec(stripped)) !== null) {
    requestSites.push({ rel, line: lineOf(stripped, m.index) });
  }
  URL_RE.lastIndex = 0;
  while ((m = URL_RE.exec(stripped)) !== null) {
    urlSites.push({ rel, line: lineOf(stripped, m.index), url: m[0] });
  }
}

if (requestSites.length === 0) {
  console.error('❌ 提取器失效信号: 全仓零个 wx.request/uploadFile/downloadFile 调用点 (services/api.js 应至少有一处)');
  process.exit(1);
}
if (urlSites.length === 0) {
  console.error('❌ 提取器失效信号: 全仓零个 http(s):// URL 字面量 (config/index.js 应至少有一处 API_BASE_URL)');
  process.exit(1);
}

let failed = false;

const rogueRequests = requestSites.filter((s) => !ALLOWED_REQUEST_FILES.includes(s.rel));
if (rogueRequests.length > 0) {
  failed = true;
  console.error(`❌ 请求出口旁路: ${rogueRequests.length} 处 wx.request/uploadFile/downloadFile 在唯一出口之外`);
  for (const s of rogueRequests) {
    console.error(`   ${s.rel}:${s.line} —— 网络请求必须走 services/api.js 统一封装(token注入/超时/重试/信封解析)`);
  }
}

const rogueUrls = urlSites.filter((s) => !ALLOWED_URL_FILES.includes(s.rel));
if (rogueUrls.length > 0) {
  failed = true;
  console.error(`❌ URL 声明多源: ${rogueUrls.length} 处 http(s):// 字面量在唯一声明源之外`);
  for (const s of rogueUrls) {
    console.error(`   ${s.rel}:${s.line} ${s.url} —— 地址必须来自 config/index.js API_BASE_URL(环境切换单一源)`);
  }
}

if (failed) process.exit(1);

console.log(`✅ 请求单一源对账通过: ${requestSites.length} 个出口调用点全部在 ${ALLOWED_REQUEST_FILES.join(', ')}`);
console.log(`✅ URL 单一源对账通过: ${urlSites.length} 个 http(s):// 字面量全部在 ${ALLOWED_URL_FILES.join(', ')}`);
if (commentUrlSkipped > 0) {
  console.log(`   (注释内 URL ${commentUrlSkipped} 处已豁免)`);
}
console.log(`   扫描 ${files.length} 个 .js 文件`);
