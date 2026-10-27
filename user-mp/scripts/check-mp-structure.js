#!/usr/bin/env node
/**
 * 微信小程序结构构建门控 (无CLI构建的CI替代)
 * 校验: JSON合法性 / 页面四件套 / tabBar图标 / 组件引用解析 / component:true
 * 用法: node scripts/check-mp-structure.js  (错误退1, 警告不退)
 */
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const errors = [];
const warnings = [];
const PAGE_EXTS = ['.js', '.json', '.wxml', '.wxss'];

function readJson(rel) {
  const abs = path.join(ROOT, rel);
  if (!fs.existsSync(abs)) {
    errors.push(`JSON缺失: ${rel}`);
    return null;
  }
  try {
    return JSON.parse(fs.readFileSync(abs, 'utf8'));
  } catch (e) {
    errors.push(`JSON非法: ${rel} (${e.message})`);
    return null;
  }
}

function checkQuad(relNoExt, label) {
  for (const ext of PAGE_EXTS) {
    if (!fs.existsSync(path.join(ROOT, relNoExt + ext))) {
      errors.push(`${label}缺文件: ${relNoExt}${ext}`);
    }
  }
}

// --- app.json ---
const app = readJson('app.json');
const pageSet = new Set();
if (app) {
  const pages = [...(app.pages || [])];
  const subpackages = app.subpackages || app.subPackages || [];
  for (const sp of subpackages) {
    for (const p of sp.pages || []) pages.push(path.posix.join(sp.root, p));
  }
  for (const p of pages) {
    pageSet.add(p);
    checkQuad(p, '页面');
  }
  // tabBar
  for (const item of (app.tabBar && app.tabBar.list) || []) {
    if (!pageSet.has(item.pagePath)) errors.push(`tabBar引用未注册页面: ${item.pagePath}`);
    for (const key of ['iconPath', 'selectedIconPath']) {
      if (item[key] && !fs.existsSync(path.join(ROOT, item[key]))) {
        errors.push(`tabBar图标缺失: ${item[key]}`);
      }
    }
  }
  // sitemap
  const sitemap = app.sitemapLocation || 'sitemap.json';
  if (!fs.existsSync(path.join(ROOT, sitemap))) errors.push(`sitemap缺失: ${sitemap}`);
}

// --- project.config.json ---
const proj = readJson('project.config.json');
if (proj && proj.appid === 'wx0000000000000000') {
  warnings.push('appid为占位符 wx0000000000000000, 上架前需换真实 appid');
}

// --- 组件引用解析 ---
function resolveComponent(fromDir, spec) {
  const target = spec.startsWith('/')
    ? path.join(ROOT, spec)
    : path.resolve(fromDir, spec);
  return path.relative(ROOT, target);
}

const checkedComponents = new Set();
function checkComponent(relNoExt) {
  if (checkedComponents.has(relNoExt)) return;
  checkedComponents.add(relNoExt);
  checkQuad(relNoExt, '组件');
  const cj = readJson(relNoExt + '.json');
  if (cj && cj.component !== true) errors.push(`组件未声明component:true: ${relNoExt}.json`);
  scanUsingComponents(relNoExt + '.json', cj);
}

function scanUsingComponents(jsonRel, json) {
  if (!json || !json.usingComponents) return;
  const fromDir = path.dirname(path.join(ROOT, jsonRel));
  for (const [name, spec] of Object.entries(json.usingComponents)) {
    if (spec.startsWith('plugin://')) continue;
    const rel = resolveComponent(fromDir, spec);
    if (!fs.existsSync(path.join(ROOT, rel + '.json'))) {
      errors.push(`${jsonRel} 组件引用无法解析: ${name} -> ${spec}`);
      continue;
    }
    checkComponent(rel);
  }
}

// 扫描 pages/ 与 components/ 下所有 .json
for (const scope of ['pages', 'components']) {
  const scopeAbs = path.join(ROOT, scope);
  if (!fs.existsSync(scopeAbs)) continue;
  (function walk(dir) {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const abs = path.join(dir, entry.name);
      if (entry.isDirectory()) walk(abs);
      else if (entry.name.endsWith('.json')) {
        const rel = path.relative(ROOT, abs).split(path.sep).join('/');
        const json = readJson(rel);
        scanUsingComponents(rel, json);
      }
    }
  })(scopeAbs);
}

// --- 报告 ---
for (const w of warnings) console.warn(`⚠ ${w}`);
if (errors.length) {
  for (const e of errors) console.error(`✗ ${e}`);
  console.error(`\n构建门控 FAIL: ${errors.length} 错误, ${warnings.length} 警告`);
  process.exit(1);
}
console.log(`构建门控 PASS: 页面 ${pageSet.size} 个, 组件 ${checkedComponents.size} 个, 警告 ${warnings.length}`);
