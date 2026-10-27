#!/usr/bin/env node
/**
 * 孤儿页面(反向可达性)双源对账守卫 (F258, 2026-08-05 猴王自驱lint轮)
 *
 * 漂移场景: app.json pages 注册集(声明侧) 与 运行时导航 url 字面量集(调用侧)
 * 的反方向零断言——F246(check-nav-targets.js)只挡"跳转目标⊆注册集"(跳到未注册页),
 * 不挡"注册页⊆可达集"(注册了但没有任何入口的页面)。任一侧单独变更即漂移:
 *   - 新注册页面未写任何导航入口 = 死页面(用户永远无法到达, 功能静默不可用)
 *   - 删除/改名全部跳转调用点但保留注册 = 孤儿页面(死代码+包体膨胀)
 *   - tabBar移除某页注册但pages保留 = 该页若无其他导航入口即成孤儿
 *
 * 不变量(单向子集, F240/F243/F246同族反向):
 *   注册页集 ⊆ 静态导航目标集 ∪ tabBar页集
 *   (每个注册页要么有静态跳转入口, 要么是tabBar页)
 *
 * 提取方法与 check-nav-targets.js 同款(单一提取口径): wx.(navigateTo|redirectTo|
 * switchTab|reLaunch) url 字面量, 截断query与${}插值取静态路径前缀;
 * 纯动态url(前缀为空)计数提示——存在纯动态url时反向断言理论上可能误判
 * (页面仅经动态拼接可达), 修复方向是把url静态前缀显式化, 不因计数放行断言(F212)。
 *
 * 用法: node scripts/check-orphan-pages.js
 * 缺输入(app.json不存在)/注册页集为空/导航目标集为空且无tabBar/断言失败 → exit 1
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

// --- 调用侧: 运行时导航 url 字面量提取(与check-nav-targets.js同款) ---
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
const targets = new Set();
let dynamicCount = 0;

function extractFromFile(absFile) {
  const src = fs.readFileSync(absFile, 'utf8');
  let m;
  navRe.lastIndex = 0;
  while ((m = navRe.exec(src)) !== null) {
    // 截断query与模板插值, 取静态路径前缀
    let p = m[3].split('?')[0].split('${')[0];
    if (p.startsWith('/')) p = p.slice(1);
    if (!p) { dynamicCount += 1; continue; }
    targets.add(p);
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

if (targets.size === 0 && tabPages.size === 0) {
  console.error('❌ 可达集为空(静态导航目标与tabBar均无, 提取逻辑失效或代码结构突变)');
  process.exit(1);
}

// --- 断言: 注册页 ⊆ 可达集(静态目标 ∪ tabBar) ---
const orphans = [...registered].filter((p) => !targets.has(p) && !tabPages.has(p));
if (orphans.length > 0) {
  console.error(orphans.map((p) => `❌ 孤儿页面: '${p}' 已注册但无任何静态导航入口且非tabBar页`).join('\n'));
  console.error('   含义: 用户永远无法到达该页面(死页面), 或全部跳转入口已被删除/改名');
  console.error('   修复: 补导航入口(跳转字面量/tabBar), 或从 app.json pages 移除注册');
  if (dynamicCount > 0) {
    console.error(`   提示: 存在 ${dynamicCount} 个纯动态url, 若孤儿页经动态拼接可达请将url静态前缀显式化`);
  }
  process.exit(1);
}

console.log(`✅ 注册页反向可达性一致: ${registered.size} 个注册页 ⊆ ${targets.size} 个静态导航目标 ∪ ${tabPages.size} 个tabBar页, 零孤儿${dynamicCount ? ` (纯动态url ${dynamicCount} 个已计数)` : ''}`);
