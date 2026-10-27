#!/usr/bin/env node
/**
 * F386: 本地静态资源路径引用 ↔ 磁盘实体双向对账守卫（对账族第十九枚）
 *
 * 不变量A（正向: 引用⊆磁盘）: wxml/js/json 中 '/assets/...' 或 "assets/..."
 *   图片字面量(png/jpg/jpeg/gif/svg)必须在磁盘上存在。
 *   缺失 = image src 静默空白图 / map marker 静默回落默认形态
 *   （F295族静默no-op最恶漂移: 构建/测试全绿, 运行时才暴露且无报错）。
 * 不变量B（反向: 磁盘⊆引用, F327同族反向对账）: assets/ 下每个图片文件
 *   必须被至少一处引用（孤儿资源 = 包体死重量, 小程序包体积敏感）。
 * 活性断言（F212）: 引用点数 ≥ MIN_REFS 且磁盘文件数 ≥ MIN_FILES,
 *   零提取/扫描域缺失即 FAIL。
 * 动态 {{...}} 非字面量路径豁免（F330语义: 静态不可判定不从严）。
 * 扫描域排除: node_modules / miniprogram_npm / *.test.js / scripts/（守卫自身）。
 */
'use strict';

const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const IMG_EXTS = ['.png', '.jpg', '.jpeg', '.gif', '.svg'];
// 基线实测（F386落盘时）: 引用点10(空组件fallback 1 + buildMarkers 1 + tabBar 8)
// 磁盘文件10(tab图标8 + marker.png + empty.png)
const MIN_REFS = 10;
const MIN_FILES = 10;

const REF_RE = /['"](\/?assets\/[A-Za-z0-9_\-./]+\.(?:png|jpe?g|gif|svg))['"]/g;

function walk(dir, out) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    if (e.name === 'node_modules' || e.name === 'miniprogram_npm' ||
        e.name === '.git' || e.name === 'coverage') continue;
    const p = path.join(dir, e.name);
    if (e.isDirectory()) walk(p, out);
    else out.push(p);
  }
  return out;
}

let failed = false;
const refs = new Map(); // rel路径 -> 引用次数
const allFiles = walk(ROOT, []);

// ---- 不变量A: 正向 字面量引用 ⊆ 磁盘 ----
for (const f of allFiles) {
  const ext = path.extname(f);
  if (!['.wxml', '.js', '.json'].includes(ext)) continue;
  if (f.includes('.test.') || f.includes('__tests__')) continue;
  if (f.startsWith(path.join(ROOT, 'scripts'))) continue;
  const src = fs.readFileSync(f, 'utf8');
  let m;
  REF_RE.lastIndex = 0;
  while ((m = REF_RE.exec(src)) !== null) {
    const rel = m[1].replace(/^\/+/, '');
    refs.set(rel, (refs.get(rel) || 0) + 1);
    if (!fs.existsSync(path.join(ROOT, rel))) {
      console.error(`❌ 引用缺失磁盘实体: ${path.relative(ROOT, f)} -> ${m[1]}`);
      failed = true;
    }
  }
}

// ---- 不变量B: 反向 磁盘 ⊆ 引用 ----
const assetDir = path.join(ROOT, 'assets');
if (!fs.existsSync(assetDir)) {
  console.error('❌ assets/ 目录不存在（扫描域缺失）');
  failed = true;
}
let diskCount = 0;
for (const f of allFiles) {
  if (!f.startsWith(assetDir)) continue;
  if (!IMG_EXTS.includes(path.extname(f))) continue;
  diskCount++;
  const rel = path.relative(ROOT, f);
  if (!refs.has(rel)) {
    console.error(`❌ 磁盘孤儿资源(零引用): ${rel}`);
    failed = true;
  }
}

// ---- 活性断言 ----
let refPoints = 0;
for (const n of refs.values()) refPoints += n;
if (refPoints < MIN_REFS) {
  console.error(`❌ 引用点数 ${refPoints} < 基线 ${MIN_REFS}（提取域收缩？）`);
  failed = true;
}
if (diskCount < MIN_FILES) {
  console.error(`❌ 磁盘图片文件数 ${diskCount} < 基线 ${MIN_FILES}（资源丢失？）`);
  failed = true;
}

if (failed) {
  console.error('asset-refs-check: FAIL');
  process.exit(1);
}
console.log(`✅ asset-refs-check: 引用点${refPoints}/磁盘文件${diskCount} 双向对账通过`);
