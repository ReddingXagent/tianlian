#!/usr/bin/env node
/**
 * auth存储键双源对账守卫 (F240, 2026-08-04 猴王自驱lint轮)
 *
 * 漂移场景: 'token'/'userInfo' 存储键名在 app.js(boot恢复侧) 与 services 认证层
 * (登录写入侧, 原services/api.js单体→拆分后写入散布 modules/*) 双源硬编码字面量, 无任何断言。任一侧单独改名(如 api.js 改写
 * 'authToken')→ boot恢复读旧键静默落空 → 用户持有有效token却被静默登出(半登录态
 * 漂移, F224双源漂移同族; eslint守卫F214只挡认证层外的直读写, 层内双源漂移不设防)。
 *
 * 不变量: app.js 读写的每个 storage 键都必须在 services/api.js 中以同名出现
 * (boot恢复读到的每一个键, 认证层必然以同名写入过)。单向往返子集断言:
 * keys(app.js) ⊆ keys(api.js)。
 *   - api.js侧改名 → 子集断言失败 (boot读的键认证层不再写)
 *   - app.js侧改名 → 子集断言失败 (boot读的键认证层从未写过)
 *
 * 提取范围: wx.get/set/removeStorage / wx.get/set/removeStorageSync 首参数字符串
 * 字面量, 以及异步对象形态 wx.getStorage({key:'x'}) 的 key 属性字面量(与F214
 * selector双形态对齐)。
 *
 * 用法: node scripts/check-auth-keys.js
 * 缺输入(任一文件不存在)/提取为空/子集断言失败 → exit 1 不放行 (F212缺输入不放行)
 */
'use strict';

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const APP_FILE = path.join(ROOT, 'app.js');
const SERVICES_DIR = path.join(ROOT, 'services');

// 写入侧提取范围: services/** 递归 .js (api.js barrel + modules/*, 排除 __tests__)
// 背景: api.js 拆分为12模块+barrel后, storage写入移入 modules/auth.js 等模块,
// 单文件提取源过时会导致提取空→守卫误报(F212提取空不放行), 故改为目录递归提取
function listServiceFiles(dir) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) return e.name === '__tests__' ? [] : listServiceFiles(p);
    return e.name.endsWith('.js') ? [p] : [];
  });
}

function extractStorageKeys(file) {
  if (!fs.existsSync(file)) {
    console.error(`❌ 缺输入: ${path.relative(ROOT, file)} 不存在`);
    process.exit(1);
  }
  const src = fs.readFileSync(file, 'utf8');
  const keys = new Set();
  // 同步/异步调用形态的首参数字符串字面量: wx.getStorageSync('token')
  const callRe = /wx\.(?:get|set|remove)Storage(?:Sync)?\(\s*['"]([^'"]+)['"]/g;
  let m;
  while ((m = callRe.exec(src)) !== null) keys.add(m[1]);
  // 异步对象形态: wx.getStorage({ key: 'token' })
  const objRe = /wx\.(?:get|set|remove)Storage\(\s*\{[^}]*\bkey:\s*['"]([^'"]+)['"]/g;
  while ((m = objRe.exec(src)) !== null) keys.add(m[1]);
  return keys;
}

const appKeys = extractStorageKeys(APP_FILE);
const apiKeys = new Set();
for (const f of listServiceFiles(SERVICES_DIR)) {
  for (const k of extractStorageKeys(f)) apiKeys.add(k);
}

if (appKeys.size === 0) {
  console.error('❌ app.js 未提取到任何 storage 键(提取逻辑失效或文件结构突变)');
  process.exit(1);
}
if (apiKeys.size === 0) {
  console.error('❌ services/** 未提取到任何 storage 键(提取逻辑失效或文件结构突变)');
  process.exit(1);
}

const missing = [...appKeys].filter((k) => !apiKeys.has(k));
if (missing.length > 0) {
  console.error(`❌ auth存储键双源漂移: app.js 使用的键 ${JSON.stringify(missing)} 未在 services/** 中出现`);
  console.error('   含义: boot恢复读的键认证层从未以同名写入 → 有效token静默丢失(半登录态)');
  console.error('   修复: 保持两侧键名严格一致(改名必须两侧同步)');
  process.exit(1);
}

console.log(`✅ auth存储键双源一致: app.js ${[...appKeys].sort().join(',')} ⊆ services/** ${[...apiKeys].sort().join(',')}`);
