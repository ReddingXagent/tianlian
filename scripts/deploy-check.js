#!/usr/bin/env node
/**
 * 天链用户端App 部署门控脚本 (Expo/EAS 管线就绪检查)
 * 流程: app.json校验 → eas.json校验 → expo-updates(OTA)校验 → 凭证校验
 * 用法:
 *   npm run deploy:check          # 验证部署管线就绪(不构建/不上传)
 *   node scripts/deploy-check.js  # 同上
 * 退出码:
 *   0 = 管线就绪(可执行 eas build / eas update)
 *   1 = 配置错误(app.json/eas.json 损坏或缺关键字段)
 *   2 = 等待外部依赖(Expo账号/EXPO_TOKEN/eas-cli) — 设计内拦截
 * 阻塞项追踪: F25/F33(EAS Update通道+Expo账号) F43(部署管线空白)
 */
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
let failures = 0;
let blockers = 0;

function ok(msg) { console.log(`  ✓ ${msg}`); }
function fail(msg) { console.error(`  ✗ ${msg}`); failures += 1; }
function blocked(msg) { console.error(`  ⚠ ${msg}`); blockers += 1; }

function readJson(file) {
  const p = path.join(ROOT, file);
  if (!fs.existsSync(p)) return null;
  try { return JSON.parse(fs.readFileSync(p, 'utf8')); }
  catch (e) { console.error(`  ✗ ${file} 解析失败: ${e.message}`); failures += 1; return null; }
}

console.log('▶ 步骤1/4 app.json 校验...');
const appCfg = readJson('app.json');
if (!appCfg || !appCfg.expo) {
  fail('app.json 缺失或无 expo 字段');
} else {
  const e = appCfg.expo;
  if (e.slug) ok(`slug=${e.slug}`); else fail('expo.slug 缺失');
  if (e.version) ok(`version=${e.version}`); else fail('expo.version 缺失');
  const pkg = e.android && e.android.package;
  const bid = e.ios && e.ios.bundleIdentifier;
  if (pkg && !pkg.includes('placeholder')) ok(`android.package=${pkg}`); else fail('android.package 缺失或占位');
  if (bid && !bid.includes('placeholder')) ok(`ios.bundleIdentifier=${bid}`); else fail('ios.bundleIdentifier 缺失或占位');
  if (e.updates && e.updates.url) ok(`updates.url=${e.updates.url}`);
  else blocked('app.json 未配置 expo.updates.url (EAS Update启用后需补: https://u.expo.dev/<project-id>)');
}

console.log('▶ 步骤2/4 eas.json 校验...');
const eas = readJson('eas.json');
if (!eas) {
  blocked('eas.json 缺失 — Expo账号就位后执行 `npx eas build:configure` 生成 (F25/F33)');
} else {
  if (eas.build && Object.keys(eas.build).length > 0) ok(`build profiles: ${Object.keys(eas.build).join(',')}`);
  else fail('eas.json 无 build profiles');
  const channels = [];
  for (const [name, prof] of Object.entries(eas.build || {})) {
    const ch = prof.channel || (prof.env && prof.env.UPDATES_CHANNEL);
    if (ch) channels.push(`${name}→${ch}`);
  }
  if (channels.length > 0) ok(`update channels: ${channels.join(', ')}`);
  else blocked('eas.json build profiles 未绑定 channel (OTA需 production/preview 通道)');
}

console.log('▶ 步骤3/4 expo-updates (OTA) 校验...');
const pkgJson = readJson('package.json');
const deps = Object.assign({}, pkgJson && pkgJson.dependencies, pkgJson && pkgJson.devDependencies);
if (deps['expo-updates']) {
  ok(`expo-updates@${deps['expo-updates']}`);
} else {
  blocked('expo-updates 未安装 — OTA热更新需 `npx expo install expo-updates` (与eas.json同步补)');
}

console.log('▶ 步骤4/4 凭证校验...');
if (process.env.EXPO_TOKEN) {
  ok('EXPO_TOKEN 已设置 (CI模式)');
} else {
  blocked('EXPO_TOKEN 未设置 — 需创建 Expo 账号后生成 access token (F25/F33)');
}

console.log('');
if (failures > 0) {
  console.error(`✗ 部署门控未通过: ${failures} 项配置错误需修复`);
  process.exit(1);
}
if (blockers > 0) {
  console.error(`⚠ 部署管线未就绪: ${blockers} 项外部依赖待就位(设计内拦截)`);
  console.error('  就绪清单: Expo账号 → EXPO_TOKEN → eas build:configure → install expo-updates → 配updates.url/channel');
  process.exit(2);
}
console.log('✓ 部署管线就绪, 可执行 eas build / eas update');
process.exit(0);
