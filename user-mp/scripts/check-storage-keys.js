#!/usr/bin/env node
/**
 * storage键生命周期双向对账守卫 (F270, 2026-08-05 猴王自驱lint轮)
 *
 * F240 只守 auth 层双源(app.js boot恢复 ⊆ api.js 登录写入), 且为单向。
 * 反向摸底撞出: api.js 侧 favorites 键 app.js 从不触碰——同层单向子集
 * 无法表达全仓 storage 键的完整生命周期。本守卫升维到全仓双向:
 *
 * 漂移场景: 小程序 storage 键名全仓字面量散布(无任何集中声明), 写入侧(set)
 * 与读取侧(get)分源硬编码。两类静默漂移:
 *   ① 死写(set后全仓无人get): 残留数据永久占位, 登出/清缓存路径漏清→
 *      换账号后旧数据静默串号(半登录态漂移同族, 最恶形态是隐私残留)
 *   ② 孤儿读(get但全仓无人set): 读取永远落空走fail/默认值,
 *      功能静默降级且无任何报错
 *
 * 不变量(双向成对, F246/F258与F252/F264同族):
 *   正向: keys(get) ⊆ keys(set)  —— 每个被读的键必有写入侧
 *   反向: keys(set) ⊆ keys(get)  —— 每个被写的键必有读取侧
 *   remove 键不参与断言(清理未写入的键是无害no-op), 仅计数报告。
 *
 * 提取范围(F240同源双形态): wx.get/set/removeStorage(Sync)?('k') 首参数字符串
 * 字面量 + 异步对象形态 wx.getStorage({key:'k'}) 的 key 属性字面量。
 * 扫描范围: app.js + pages/ components/ services/ utils/ config/ 下全部 .js
 * (排除 node_modules/scripts/coverage/dist/build)。
 *
 * 用法: node scripts/check-storage-keys.js
 * 缺输入(零个应用js)/任一方向集合为空/任一方向断言失败 → exit 1 不放行 (F212)
 */
'use strict';

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const SCAN_DIRS = ['pages', 'components', 'services', 'utils', 'config'];
const EXCLUDE_DIRS = new Set(['node_modules', 'scripts', 'coverage', 'dist', 'build', 'miniprogram_npm']);

// 首参数字符串字面量形态: wx.setStorageSync('token')
const CALL_RE = /wx\.(get|set|remove)Storage(?:Sync)?\(\s*['"]([^'"]+)['"]/g;
// 异步对象形态: wx.getStorage({ key: 'token' })
const OBJ_RE = /wx\.(get|set|remove)Storage\(\s*\{[^}]*?key\s*:\s*['"]([^'"]+)['"]/g;

function collectJsFiles(dir, out) {
  if (!fs.existsSync(dir)) return;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (EXCLUDE_DIRS.has(entry.name)) continue;
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) collectJsFiles(full, out);
    else if (entry.isFile() && entry.name.endsWith('.js')) out.push(full);
  }
}

const files = [];
const appFile = path.join(ROOT, 'app.js');
if (fs.existsSync(appFile)) files.push(appFile);
for (const d of SCAN_DIRS) collectJsFiles(path.join(ROOT, d), files);

if (files.length === 0) {
  console.error('❌ 缺输入: 未找到任何应用侧 .js 文件 (app.js / pages / components / services / utils / config)');
  process.exit(1);
}

const getKeys = new Set();
const setKeys = new Set();
const removeKeys = new Set();

function add(op, key) {
  if (op === 'get') getKeys.add(key);
  else if (op === 'set') setKeys.add(key);
  else removeKeys.add(key);
}

for (const f of files) {
  const src = fs.readFileSync(f, 'utf8');
  for (const re of [CALL_RE, OBJ_RE]) {
    re.lastIndex = 0;
    let m;
    while ((m = re.exec(src)) !== null) add(m[1], m[2]);
  }
}

if (getKeys.size === 0 || setKeys.size === 0) {
  console.error(`❌ 提取为空: get键=${getKeys.size} set键=${setKeys.size} (扫描${files.length}个js) — 提取器疑似失效, 不放行 (F212)`);
  process.exit(1);
}

const fmt = (s) => [...s].sort().join(', ');
const diff = (a, b) => [...a].filter((k) => !b.has(k)).sort();

const orphanReads = diff(getKeys, setKeys); // 读但无人写 → 静默落空
const deadWrites = diff(setKeys, getKeys); // 写但无人读 → 静默残留

let failed = false;
if (orphanReads.length > 0) {
  failed = true;
  console.error(`❌ 孤儿读(全仓无人写入, 读取永远落空): ${orphanReads.join(', ')}`);
}
if (deadWrites.length > 0) {
  failed = true;
  console.error(`❌ 死写(全仓无人读取, 残留数据静默累积): ${deadWrites.join(', ')}`);
}
if (failed) {
  console.error(`   get键: ${fmt(getKeys)} | set键: ${fmt(setKeys)}`);
  console.error('   处置: 补写入/读取侧, 或确认该键已废弃后删除全部触点(含remove清理路径)');
  process.exit(1);
}

console.log(`✅ storage键生命周期双向一致: get键 ⊆ set键 ⊆ get键 (共 ${fmt(getKeys)}; remove键: ${removeKeys.size ? fmt(removeKeys) : '无'}; 扫描${files.length}个js)`);
