#!/usr/bin/env node
/**
 * CSS 变量死代码守卫 (F373, 2026-08-06 猴王自驱lint轮)
 *
 * 背景: app.wxss 在 page 选择器上声明了 12 个主题 CSS 变量
 * (--primary / --danger / --warning / --text-* / --bg-* / ...)。
 * 变量声明后不被任何 var() 引用即为死代码——变量值漂移无人感知
 * (改了颜色零效果), 或是重构遗漏 (本应引用但手写硬编码色值)。
 *
 * --warning: #FFC300 基线即死代码: .tag-warning 类使用 #FFF8E1/#F57F17
 * 硬编码而非 var(--warning), --warning 值改动对全仓零效果。
 *
 * 不变量(单向子集, F240/F246同向):
 *   app.wxss page{} 内声明的每个 --variable, 必须在全仓 wxss 中
 *   至少被 var(--variable) 引用一次(自身声明行除外)。
 *
 * 活性断言(防豁免吞断言, F306形态):
 *   声明变量数 ≥ 1 + 引用变量数 ≥ 1 (提取器失效信号)。
 *
 * 扫描域: app.wxss + pages (递归) + components (递归) 全部 wxss;
 * 声明提取: `--name: value;` 在 page{} 块内;
 * 引用提取: `var(--name)` 在任意 wxss 文件内(含 app.wxss 自身非声明行)。
 *
 * 缺输入(无wxss文件/无声明变量) / 任一死变量 / 提取器空 -> exit 1 (F212)。
 */
'use strict';

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');

/** 收集全部 wxss 文件 */
function collectWxss() {
  const files = [];
  function scan(dir) {
    if (!fs.existsSync(dir)) return;
    for (const name of fs.readdirSync(dir)) {
      const full = path.join(dir, name);
      const stat = fs.statSync(full);
      if (stat.isDirectory()) scan(full);
      else if (name.endsWith('.wxss')) files.push(full);
    }
  }
  scan(path.join(ROOT, 'pages'));
  scan(path.join(ROOT, 'components'));
  const appWxss = path.join(ROOT, 'app.wxss');
  if (fs.existsSync(appWxss)) files.push(appWxss);
  return files;
}

/** 从 app.wxss page{} 块提取声明的 CSS 变量名 */
function extractDeclaredVars(appWxssPath) {
  const content = fs.readFileSync(appWxssPath, 'utf8');
  // 匹配 page { ... } 块内的 --var: value; 声明
  const pageMatch = content.match(/page\s*\{([^}]*)\}/s);
  if (!pageMatch) return new Set();
  const block = pageMatch[1];
  const vars = new Set();
  const re = /(--[a-z][-a-z0-9]*)\s*:/g;
  let m;
  while ((m = re.exec(block)) !== null) {
    vars.add(m[1]);
  }
  return vars;
}

/** 从所有 wxss 文件提取 var() 引用的变量名(去除声明行) */
function extractReferencedVars(files, _appWxssPath) {
  const refs = new Set();

  for (const file of files) {
    const content = fs.readFileSync(file, 'utf8');
    const lines = content.split('\n');
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      // 跳过声明行 (--var: value;)
      if (/^\s*--[a-z][-a-z0-9]*\s*:/.test(line)) continue;
      // 提取 var(--name)
      const re = /var\(\s*(--[a-z][-a-z0-9]*)/g;
      let m;
      while ((m = re.exec(line)) !== null) {
        refs.add(m[1]);
      }
    }
  }
  return refs;
}

// Main
const files = collectWxss();
const appWxss = path.join(ROOT, 'app.wxss');

if (files.length === 0) {
  console.error('✗ CSS变量死代码守卫: 未找到任何 wxss 文件');
  process.exit(1);
}

const declared = extractDeclaredVars(appWxss);
if (declared.size === 0) {
  console.error('✗ CSS变量死代码守卫: app.wxss page{} 块内未声明任何 CSS 变量');
  process.exit(1);
}

const referenced = extractReferencedVars(files, appWxss);
if (referenced.size === 0) {
  console.error('✗ CSS变量死代码守卫: 全仓 wxss 未发现任何 var() 引用');
  process.exit(1);
}

const dead = [];
for (const v of declared) {
  if (!referenced.has(v)) {
    dead.push(v);
  }
}

if (dead.length > 0) {
  console.error(`✗ CSS变量死代码守卫: ${dead.length} 个声明变量从未被 var() 引用:`);
  for (const v of dead) {
    console.error(`  ${v}`);
  }
  process.exit(1);
}

console.log(`✓ CSS变量死代码守卫: ${declared.size} 个变量全部被引用 (扫描 ${files.length} 个 wxss 文件)`);
