#!/usr/bin/env node
/**
 * 孤儿组件反向对账守卫 (F284, 2026-08-05 猴王自驱lint轮)
 *
 * 漂移场景: 组件实体(component:true 的 json 声明, 声明侧)与
 * 各 json usingComponents 引用(调用侧)的反向零断言。
 * check-mp-structure.js 只挡正向(引用必须可解析), 反向是它的盲区:
 * 组件被页面删除引用后实体残留 → 死组件(小程序包体积白占,
 * 上架审核扫描面增大), 与 F258 孤儿页/F264 死handler同族反向补盲。
 *
 * 不变量(单向子集, F258/F264反向同向):
 *   组件实体集(json含component:true) ⊆ usingComponents 引用解析集
 *   (每个组件至少被一个页面/组件/app.json 引用)
 *
 * 提取范围: pages/ components/ 下全部 .json 及 app.json 的
 * usingComponents 值; 绝对路径(/开头, 项目根)与相对路径(引用方目录)
 * 均归一化为项目根相对无扩展路径, plugin:// 豁免(外部插件非本仓实体);
 * 解析逻辑与 check-mp-structure.js 同口径。
 *
 * 用法: node scripts/check-orphan-components.js
 * 缺输入(app.json不存在)/组件实体集为空/断言失败 → exit 1 不放行
 * (F212缺输入不放行)
 */
'use strict';

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const SKIP_SEGMENTS = new Set(['__tests__', 'node_modules', 'miniprogram_npm']);

// --- 声明侧: 组件实体集 (component:true) ---
const appJsonPath = path.join(ROOT, 'app.json');
if (!fs.existsSync(appJsonPath)) {
  console.error('❌ 缺输入: app.json 不存在');
  process.exit(1);
}
const entities = new Set(); // relNoExt (posix)
const jsonFiles = [path.join(ROOT, 'app.json')];

function *walkJson(dir) {
  if (!fs.existsSync(dir)) return;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (SKIP_SEGMENTS.has(entry.name)) continue;
    const abs = path.join(dir, entry.name);
    if (entry.isDirectory()) yield* walkJson(abs);
    else if (entry.isFile() && entry.name.endsWith('.json')) yield abs;
  }
}
for (const scope of ['pages', 'components']) {
  for (const abs of walkJson(path.join(ROOT, scope))) jsonFiles.push(abs);
}

function toRelPosix(absPath) {
  return path.relative(ROOT, absPath).split(path.sep).join('/');
}

for (const abs of jsonFiles) {
  let json;
  try {
    json = JSON.parse(fs.readFileSync(abs, 'utf8'));
  } catch (e) {
    console.error(`❌ JSON非法: ${toRelPosix(abs)} (${e.message})`);
    process.exit(1);
  }
  if (json && json.component === true) entities.add(toRelPosix(abs).replace(/\.json$/, ''));
}
if (entities.size === 0) {
  console.error('❌ 未提取到任何组件实体(声明侧提取为空, 检查 component:true 扫描逻辑)');
  process.exit(1);
}

// --- 调用侧: usingComponents 引用解析集 (与 check-mp-structure 同口径) ---
const referenced = new Set(); // relNoExt (posix)
let refCount = 0;

for (const abs of jsonFiles) {
  const json = JSON.parse(fs.readFileSync(abs, 'utf8'));
  if (!json || !json.usingComponents) continue;
  const fromDir = path.dirname(abs);
  for (const spec of Object.values(json.usingComponents)) {
    if (typeof spec !== 'string' || spec.startsWith('plugin://')) continue;
    refCount += 1;
    let target = spec.startsWith('/')
      ? path.join(ROOT, spec)
      : path.resolve(fromDir, spec);
    target = target.replace(/\.(js|json|wxml|wxss)$/, '');
    referenced.add(toRelPosix(target));
  }
}

// --- 断言: 实体集 ⊆ 引用集 ---
const orphans = [...entities].filter((e) => !referenced.has(e)).sort();
if (orphans.length > 0) {
  console.error(orphans.map((o) => `❌ 孤儿组件: ${o} (component:true 声明但无任何 usingComponents 引用)`).join('\n'));
  console.error('   含义: 死组件白占小程序包体积, 增大上架审核扫描面');
  console.error('   修复: 确认无用则删组件四件套; 仍需用则在引用方 json 补 usingComponents');
  process.exit(1);
}

console.log(`✅ 组件实体↔引用反向对账一致: ${entities.size} 个组件实体全部被引用 (usingComponents 引用 ${refCount} 处, 含绝对/相对路径归一化)`);
