#!/usr/bin/env node
/**
 * 导航目标↔页面注册双源对账守卫 (F246, 2026-08-04 猴王自驱lint轮)
 *
 * 漂移场景: 运行时 wx.navigateTo/redirectTo/switchTab/reLaunch 的 url 字面量
 * (调用侧, 散布各页面) 与 app.json pages 数组 (声明侧, 唯一注册源) 双源零断言。
 * 任一侧单独变更即漂移:
 *   - 页面目录改名/app.json移除注册 → 调用侧跳转运行时
 *     "navigateTo:fail page ... is not found"(F243探测集↔声明集同族)
 *   - tabBar页用 navigateTo/redirectTo 跳转 → 运行时 fail(tabBar页只能 switchTab)
 *   - 非tabBar页用 switchTab 跳转 → 运行时 fail
 * check-mp-structure.js 只挡"注册页四件套齐全/tabBar引用已注册页", 不挡
 * 运行时跳转字面量↔注册集的对账(调用侧是它的盲区)。
 *
 * 不变量(单向子集, F240/F243同向):
 *   1. 静态导航目标集 ⊆ app.json 注册页集(跳的每个页面必然注册过)
 *   2. switchTab 目标 ∈ tabBar 页集; navigateTo/redirectTo 目标 ∉ tabBar 页集
 *   (reLaunch 可跳任意注册页, 只查不变量1)
 *
 * 提取范围: pages/ services/ utils/ components/ app.js 中的
 * wx.(navigateTo|redirectTo|switchTab|reLaunch)({url:'...'}) 字面量,
 * 含模板字符串; query(?...)与插值(${...})截断取静态路径前缀;
 * 纯动态url(前缀为空)无法对账, 计数提示不拦(非双源漂移)。
 *
 * 用法: node scripts/check-nav-targets.js
 * 缺输入(app.json不存在)/注册页集为空/导航目标集为空/断言失败 → exit 1 不放行
 * (F212缺输入不放行)
 */
'use strict';

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const SCAN_DIRS = ['pages', 'services', 'utils', 'components'];
const SCAN_FILES = ['app.js'];
const SKIP_SEGMENTS = new Set(['__tests__', 'node_modules', 'miniprogram_npm']);

// --- 声明侧: app.json 注册页集 + tabBar页集 ---
const appJsonPath = path.join(ROOT, 'app.json');
if (!fs.existsSync(appJsonPath)) {
  console.error('❌ 缺输入: app.json 不存在');
  process.exit(1);
}
let app;
try {
  app = JSON.parse(fs.readFileSync(appJsonPath, 'utf8'));
} catch (e) {
  console.error(`❌ app.json 非法: ${e.message}`);
  process.exit(1);
}
const registered = new Set(app.pages || []);
for (const sp of app.subpackages || app.subPackages || []) {
  for (const p of sp.pages || []) registered.add(path.posix.join(sp.root, p));
}
const tabPages = new Set(((app.tabBar && app.tabBar.list) || []).map((i) => i.pagePath));
if (registered.size === 0) {
  console.error('❌ app.json 未注册任何页面(声明侧提取为空)');
  process.exit(1);
}

// --- 调用侧: 运行时导航 url 字面量提取 ---
function *walkJs(dir) {
  if (!fs.existsSync(dir)) return;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (SKIP_SEGMENTS.has(entry.name)) continue;
    const abs = path.join(dir, entry.name);
    if (entry.isDirectory()) yield* walkJs(abs);
    else if (entry.isFile() && entry.name.endsWith('.js')) yield abs;
  }
}

const navRe = /wx\.(navigateTo|redirectTo|switchTab|reLaunch)\(\s*\{[\s\S]{0,300}?\burl:\s*(['"`])([^'"`]*)\2/g;
const targets = []; // { file, api, path }
let dynamicCount = 0;

function extractFromFile(absFile) {
  const src = fs.readFileSync(absFile, 'utf8');
  const rel = path.relative(ROOT, absFile);
  let m;
  navRe.lastIndex = 0;
  while ((m = navRe.exec(src)) !== null) {
    const api = m[1];
    // 截断query与模板插值, 取静态路径前缀
    let p = m[3].split('?')[0].split('${')[0];
    if (p.startsWith('/')) p = p.slice(1);
    if (!p) { dynamicCount += 1; continue; }
    targets.push({ file: rel, api, path: p });
  }
}

const scanPaths = [...SCAN_DIRS.map((d) => path.join(ROOT, d)), ...SCAN_FILES.map((f) => path.join(ROOT, f))];
for (const file of scanPaths) {
  const stat = fs.existsSync(file) && fs.statSync(file);
  if (!stat) continue;
  if (stat.isDirectory()) {
    for (const js of walkJs(file)) extractFromFile(js);
  } else if (stat.isFile()) {
    extractFromFile(file);
  }
}

if (targets.length === 0 && dynamicCount === 0) {
  console.error('❌ 未提取到任何导航目标(调用侧提取逻辑失效或代码结构突变)');
  process.exit(1);
}

// --- 断言 ---
const errors = [];
for (const t of targets) {
  if (!registered.has(t.path)) {
    errors.push(`❌ 未注册页面跳转: ${t.file} wx.${t.api} → '${t.path}' 不在 app.json pages 注册集`);
  }
  if (t.api === 'switchTab' && !tabPages.has(t.path)) {
    errors.push(`❌ switchTab目标非tabBar页: ${t.file} → '${t.path}' (switchTab只能跳tabBar页)`);
  }
  if ((t.api === 'navigateTo' || t.api === 'redirectTo') && tabPages.has(t.path)) {
    errors.push(`❌ ${t.api}目标为tabBar页: ${t.file} → '${t.path}' (tabBar页只能用switchTab跳)`);
  }
}
if (errors.length > 0) {
  console.error(errors.join('\n'));
  console.error('   含义: 运行时跳转必然 fail(页面未注册/跳转API与tabBar属性不匹配)');
  console.error('   修复: 页面改名两侧同步(app.json+跳转字面量); tabBar页改用switchTab');
  process.exit(1);
}

console.log(`✅ 导航目标↔页面注册双源一致: ${targets.length} 个静态跳转目标 ⊆ ${registered.size} 个注册页, switchTab/navigateTo 与 tabBar 属性全部匹配${dynamicCount ? ` (纯动态url ${dynamicCount} 个不可对账, 已计数)` : ''}`);
