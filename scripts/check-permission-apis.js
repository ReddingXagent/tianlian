#!/usr/bin/env node
/**
 * 隐私API↔app.json声明双向对账守卫 (F277, 2026-08-05 猴王自驱lint轮)
 *
 * 漂移场景: 微信自2022隐私接口整改后, 涉及隐私的 wx.* API 必须在 app.json
 * requiredPrivateInfos 中声明, 否则**运行时直接拒绝调用**(fail: privacy permission is not allowed)。
 * app.json 声明侧与代码调用侧是典型双源, 无任何编译期/静态断言, 两类静默漂移:
 *   ① 调用未声明: 新增 wx.getLocation 类调用忘补 requiredPrivateInfos →
 *      开发工具不报(宽松), 真机运行时 fail → 功能静默挂(最恶形态: 提审通过线上才炸)
 *   ② 声明未调用: requiredPrivateInfos 残留无人调用的隐私项(如本守卫首跑撞出
 *      chooseLocation 声明但全仓无调用) → 隐私协议多列一项用户敏感权限,
 *      审核风险+用户信任成本, 且后续接手者误判"代码在用位置选择"
 *
 * 不变量(双向成对, F246/F258、F252/F264、F270 同族):
 *   正向: used(隐私API)映射值 ⊆ requiredPrivateInfos声明 —— 每个调用必有声明
 *   反向: requiredPrivateInfos声明 ⊆ used(隐私API)映射值 —— 每个声明必有调用
 *   附加(仅正向): 调用的API隐含的授权 scope 必须在 app.json permission 块中
 *   有非空 desc(微信强制: 无 desc 首次授权弹窗直接报错)。scope 反向不做断言
 *   (desc 声明是零运行时成本的文案, 删了反而破坏授权弹窗)。
 *
 * API→requiredPrivateInfos 映射(微信官方枚举): onLocationChange 归并到
 * startLocationUpdateBackground(后台定位变更监听依赖后台定位声明)。
 * openLocation/chooseMedia 等不采集隐私信息的API不在映射内(声明反而是错)。
 *
 * 用法: node scripts/check-permission-apis.js
 * 缺输入(app.json缺失/损坏、零个应用js)/任一方向断言失败/scope缺desc → exit 1 不放行 (F212)
 */
'use strict';

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const SCAN_DIRS = ['pages', 'components', 'services', 'utils', 'config'];
const EXCLUDE_DIRS = new Set(['node_modules', 'scripts', 'coverage', 'dist', 'build', 'miniprogram_npm']);

// API名 → requiredPrivateInfos 枚举值 (单一源, 微信官方清单)
const API_TO_INFO = {
  getLocation: 'getLocation',
  getFuzzyLocation: 'getFuzzyLocation',
  chooseLocation: 'chooseLocation',
  choosePoi: 'choosePoi',
  startLocationUpdate: 'startLocationUpdate',
  startLocationUpdateBackground: 'startLocationUpdateBackground',
  onLocationChange: 'startLocationUpdateBackground',
  chooseAddress: 'chooseAddress',
  chooseInvoiceTitle: 'chooseInvoiceTitle',
};

// API名 → 授权 scope (permission 块 desc 强制); choosePoi 无 scope 要求, 不入表
const API_TO_SCOPE = {
  getLocation: 'scope.userLocation',
  chooseLocation: 'scope.userLocation',
  startLocationUpdate: 'scope.userLocation',
  startLocationUpdateBackground: 'scope.userLocation',
  onLocationChange: 'scope.userLocation',
  getFuzzyLocation: 'scope.userFuzzyLocation',
  chooseAddress: 'scope.address',
  chooseInvoiceTitle: 'scope.invoiceTitle',
};

const API_RE = new RegExp(`wx\\.(${Object.keys(API_TO_INFO).join('|')})\\b`, 'g');

function collectJsFiles(dir, out) {
  if (!fs.existsSync(dir)) return;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (EXCLUDE_DIRS.has(entry.name)) continue;
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) collectJsFiles(full, out);
    else if (entry.isFile() && entry.name.endsWith('.js')) out.push(full);
  }
}

// ---- 读 app.json ----
const APP_JSON = path.join(ROOT, 'app.json');
if (!fs.existsSync(APP_JSON)) {
  console.error('❌ 缺输入: app.json 不存在');
  process.exit(1);
}
let appCfg;
try {
  appCfg = JSON.parse(fs.readFileSync(APP_JSON, 'utf8'));
} catch (e) {
  console.error(`❌ 缺输入: app.json 解析失败: ${e.message}`);
  process.exit(1);
}
const declaredInfos = new Set(Array.isArray(appCfg.requiredPrivateInfos) ? appCfg.requiredPrivateInfos : []);
const permissionBlock = appCfg.permission && typeof appCfg.permission === 'object' ? appCfg.permission : {};

// ---- 扫应用侧 js ----
const files = [];
const appFile = path.join(ROOT, 'app.js');
if (fs.existsSync(appFile)) files.push(appFile);
for (const d of SCAN_DIRS) collectJsFiles(path.join(ROOT, d), files);

if (files.length === 0) {
  console.error('❌ 缺输入: 未找到任何应用侧 .js 文件 (app.js / pages / components / services / utils / config)');
  process.exit(1);
}

const usedApis = new Map(); // api名 → [触点相对路径]
for (const f of files) {
  const src = fs.readFileSync(f, 'utf8');
  API_RE.lastIndex = 0;
  let m;
  while ((m = API_RE.exec(src)) !== null) {
    const rel = path.relative(ROOT, f);
    if (!usedApis.has(m[1])) usedApis.set(m[1], []);
    usedApis.get(m[1]).push(rel);
  }
}

const usedInfos = new Set([...usedApis.keys()].map((api) => API_TO_INFO[api]));
const usedScopes = new Set([...usedApis.keys()].filter((api) => API_TO_SCOPE[api]).map((api) => API_TO_SCOPE[api]));
const fmt = (s) => [...s].sort().join(', ');
const diff = (a, b) => [...a].filter((k) => !b.has(k)).sort();

let failed = false;

const undeclared = diff(usedInfos, declaredInfos);
if (undeclared.length > 0) {
  failed = true;
  for (const info of undeclared) {
    const apis = [...usedApis.keys()].filter((api) => API_TO_INFO[api] === info);
    const touches = apis.flatMap((api) => usedApis.get(api));
    console.error(`❌ 调用未声明(真机运行时拒绝): ${info} ← wx.${apis.join('/wx.')} @ ${touches.join(', ')}`);
  }
}

const deadDecls = diff(declaredInfos, usedInfos);
if (deadDecls.length > 0) {
  failed = true;
  console.error(`❌ 声明未调用(隐私协议多列敏感权限, 审核风险): ${deadDecls.join(', ')}`);
}

const missingScopes = [...usedScopes].filter((scope) => {
  const entry = permissionBlock[scope];
  return !entry || typeof entry.desc !== 'string' || entry.desc.trim() === '';
}).sort();
if (missingScopes.length > 0) {
  failed = true;
  console.error(`❌ 授权scope缺desc(首次授权弹窗直接报错): ${missingScopes.join(', ')} — app.json permission 块需非空 desc`);
}

if (failed) {
  console.error(`   声明: ${declaredInfos.size ? fmt(declaredInfos) : '(空)'} | 调用映射: ${usedInfos.size ? fmt(usedInfos) : '(空)'}`);
  console.error('   处置: 补 app.json requiredPrivateInfos 声明, 或确认 API 已废弃后删除声明(双向成对)');
  process.exit(1);
}

console.log(`✅ 隐私API↔app.json声明双向一致: 调用映射 ⊆ 声明 ⊆ 调用映射 (共 ${usedInfos.size ? fmt(usedInfos) : '(空)'}; scope desc: ${fmt(usedScopes)}; 扫描${files.length}个js)`);
