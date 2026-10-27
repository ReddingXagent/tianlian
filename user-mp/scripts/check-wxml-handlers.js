#!/usr/bin/env node
/**
 * WXML事件绑定↔JS方法定义双源对账守卫 (F252, 2026-08-05 猴王自驱lint轮)
 *
 * 漂移场景: wxml 事件绑定 (bindtap/catchtap/bindinput... 调用侧, 散布模板)
 * 按名字引用同目录 js 中 Page/Component 的方法 (声明侧), 双源零断言。
 * 任一侧单独变更即漂移:
 *   - JS 方法改名/删除 → wxml 绑定运行时静默失效(点击无反应/控制台报错)
 *   - wxml 绑定名拼错 → 同上, 编译期零拦截(小程序无tsc)
 * check-mp-structure.js 只挡四件套齐全/tabBar注册, 不挡绑定名↔方法集对账。
 *
 * 不变量(单向子集, F240/F243/F246同向):
 *   wxml 静态事件绑定名集 ⊆ 同目录 js 可用方法集
 *   Page: Page({}) 顶层键; Component: Component({methods:{}}) methods 块键
 *
 * 提取范围: pages/ components/ 下全部 *.wxml 的 (bind|catch)[:?]事件="名字";
 * 动态绑定(值含{{}})无法对账, 计数提示不拦(非双源漂移, F212变体)。
 *
 * 用法: node scripts/check-wxml-handlers.js
 * 缺输入(wxml无配对js/Page块缺失)/绑定集为空/断言失败 → exit 1 不放行
 * (F212缺输入不放行)
 */
'use strict';

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const SCAN_DIRS = ['pages', 'components'];
const BIND_RE = /(?:bind|catch):?[a-z]+\s*=\s*"([^"]+)"/g;
const SKIP_DIRS = new Set(['__tests__', 'node_modules', 'miniprogram_npm']);

function isIdent(s) {
  return /^[A-Za-z_$][\w$]*$/.test(s);
}

// 跳过字符串字面量(入口为引号), 返回字面量后的下标
function skipStr(src, i) {
  const q = src[i];
  let j = i + 1;
  while (j < src.length && src[j] !== q) {
    if (src[j] === '\\') j += 1;
    j += 1;
  }
  return j + 1;
}

// 若 i 处是字符串/注释则跳过返回新下标, 否则原样返回
function skipNonCode(src, i) {
  const c = src[i];
  if (c === "'" || c === '"' || c === '`') return skipStr(src, i);
  if (c === '/' && src[i + 1] === '/') {
    const nl = src.indexOf('\n', i);
    return nl === -1 ? src.length : nl + 1;
  }
  if (c === '/' && src[i + 1] === '*') {
    const end = src.indexOf('*/', i + 2);
    return end === -1 ? src.length : end + 2;
  }
  return i;
}

// Page({ 或 Component({ 的对象字面量 '{' 下标, 无则 -1
function rootObjectIndex(src) {
  const m = /(?:Page|Component)\s*\(\s*\{/.exec(src);
  if (!m) return -1;
  return m.index + m[0].length - 1;
}

// 在 i 处读一个候选键(字符串字面量或标识符); async 是修饰符不算键
// 非键字符(空白/冒号/括号等)返回 next=i: 调用侧回落主循环常规扫描,
// 不得因此清 wantKey, 否则键名前任意空白即致整块键集提取失效(接手轮复验撞出并修复)
function readKeyAt(src, i) {
  const c = src[i];
  if (c === "'" || c === '"') {
    const j = skipStr(src, i);
    return { key: src.slice(i + 1, j - 1), next: j };
  }
  const m = /^[A-Za-z_$][\w$]*/.exec(src.slice(i));
  if (!m) return { key: null, next: i };
  if (m[0] === 'async') return { key: null, next: i + m[0].length };
  return { key: m[0], next: i + m[0].length };
}

// 收集 openIdx 处对象字面量的深度1键集(跳过字符串/注释), 顺带计 spread 数
// parens 跟踪括号深度: 方法简写 key(a, b) {} 与箭头值 key: (a) => {} 的
// 参数列表在括号内, 其逗号/标识符不得当作键(F264撞出, F252同源修复)
function collectKeys(src, openIdx) {
  const keys = new Set();
  let spreads = 0;
  let depth = 0;
  let parens = 0;
  let wantKey = true;
  let i = openIdx;
  while (i < src.length) {
    const c = src[i];
    // 键位统一走 readKeyAt(字符串字面量键/标识符键单入口):
    // async 返回 next>i 且 key=null, 保持 wantKey 等真键;
    // 非键字符 next=i 回落主循环常规扫描(不吞逗号/花括号/spread)
    if (depth === 1 && wantKey && parens === 0) {
      const r = readKeyAt(src, i);
      if (r.next > i) {
        if (r.key !== null) {
          keys.add(r.key);
          wantKey = false;
        }
        i = r.next;
        continue;
      }
    }
    const j = skipNonCode(src, i);
    if (j !== i) {
      i = j;
      continue;
    }
    if (c === '(' || c === ')') {
      parens += c === '(' ? 1 : -1;
      i += 1;
      continue;
    }
    if (c === '{') {
      depth += 1;
      i += 1;
      continue;
    }
    if (c === '}') {
      depth -= 1;
      if (depth === 0) break;
      i += 1;
      continue;
    }
    if (depth !== 1) {
      i += 1;
      continue;
    }
    if (c === ',' && parens === 0) {
      wantKey = true;
      i += 1;
      continue;
    }
    if (parens !== 0 || !wantKey) {
      i += 1;
      continue;
    }
    if (src.slice(i, i + 3) === '...') {
      spreads += 1;
      wantKey = false;
      i += 3;
      continue;
    }
    i += 1;
  }
  return { keys, spreads };
}

// 在 openIdx 对象深度1找 keyName 键, 返回其值对象的 '{' 下标, 无则 -1
function findValueObject(src, openIdx, keyName) {
  let depth = 0;
  let wantKey = true;
  let i = openIdx;
  while (i < src.length) {
    const j = skipNonCode(src, i);
    if (j !== i) {
      i = j;
      continue;
    }
    const c = src[i];
    if (c === '{') {
      depth += 1;
      i += 1;
      continue;
    }
    if (c === '}') {
      depth -= 1;
      if (depth === 0) break;
      i += 1;
      continue;
    }
    if (depth !== 1) {
      i += 1;
      continue;
    }
    if (c === ',' && !wantKey) {
      wantKey = true;
      i += 1;
      continue;
    }
    const m = /^[A-Za-z_$][\w$]*/.exec(src.slice(i));
    if (!m) {
      i += 1;
      continue;
    }
    if (m[0] === keyName && wantKey) {
      const rest = src.slice(i + m[0].length);
      const colon = rest.indexOf(':');
      const brace = rest.indexOf('{');
      if (colon !== -1 && brace !== -1 && brace > colon) {
        return i + m[0].length + brace;
      }
      return -1;
    }
    wantKey = false;
    i += m[0].length;
  }
  return -1;
}

// 收集目录下全部 *.wxml (递归, 跳 SKIP_DIRS)
function collectWxml(dir, out) {
  if (!fs.existsSync(dir)) return;
  for (const ent of fs.readdirSync(dir, { withFileTypes: true })) {
    if (SKIP_DIRS.has(ent.name)) continue;
    const full = path.join(dir, ent.name);
    if (ent.isDirectory()) collectWxml(full, out);
    if (ent.isFile() && ent.name.endsWith('.wxml')) out.push(full);
  }
}

// 提取单个 wxml 的静态/动态绑定 [{name, line}]
function extractBindings(wxmlPath) {
  const lines = fs.readFileSync(wxmlPath, 'utf8').split('\n');
  const statics = [];
  let dynamic = 0;
  lines.forEach((line, idx) => {
    for (const m of line.matchAll(BIND_RE)) {
      const val = m[1].trim();
      if (val.includes('{{')) {
        dynamic += 1;
      } else {
        statics.push({ name: val, line: idx + 1 });
      }
    }
  });
  return { statics, dynamic };
}

// --- 主流程 ---
const wxmlFiles = [];
for (const d of SCAN_DIRS) collectWxml(path.join(ROOT, d), wxmlFiles);
if (wxmlFiles.length === 0) {
  console.error('❌ 缺输入: pages/ components/ 下未找到任何 wxml');
  process.exit(1);
}

const failures = [];
let totalStatic = 0;
let totalDynamic = 0;
let totalSpreads = 0;
let checkedFiles = 0;

for (const wxml of wxmlFiles) {
  const rel = path.relative(ROOT, wxml);
  const jsPath = wxml.replace(/\.wxml$/, '.js');
  if (!fs.existsSync(jsPath)) {
    console.error(`❌ 缺输入: ${rel} 无配对 js (${path.relative(ROOT, jsPath)})`);
    process.exit(1);
  }
  const src = fs.readFileSync(jsPath, 'utf8');
  const rootIdx = rootObjectIndex(src);
  if (rootIdx === -1) {
    console.error(`❌ 缺输入: ${path.relative(ROOT, jsPath)} 未找到 Page({/Component({ 块`);
    process.exit(1);
  }
  const isComponent = /Component\s*\(\s*\{/.test(src.slice(0, rootIdx + 1));
  let keyScope = rootIdx;
  if (isComponent) {
    keyScope = findValueObject(src, rootIdx, 'methods');
  }
  const { keys, spreads } = keyScope === -1
    ? { keys: new Set(), spreads: 0 }
    : collectKeys(src, keyScope);
  totalSpreads += spreads;
  const { statics, dynamic } = extractBindings(wxml);
  totalDynamic += dynamic;
  checkedFiles += 1;
  for (const b of statics) {
    totalStatic += 1;
    if (!isIdent(b.name)) {
      console.warn(`⚠ ${rel}:${b.line} 绑定值非常规标识符, 计数不拦: "${b.name}"`);
      continue;
    }
    if (!keys.has(b.name)) {
      failures.push(`${rel}:${b.line} 绑定 "${b.name}" → ${path.relative(ROOT, jsPath)} 方法集无此名`);
    }
  }
}

if (totalStatic === 0) {
  console.error('❌ wxml 静态事件绑定提取为空(提取逻辑疑似失效)');
  process.exit(1);
}

if (failures.length > 0) {
  console.error(`❌ WXML事件绑定↔JS方法 对账失败 (${failures.length} 处):`);
  for (const f of failures) console.error(`  - ${f}`);
  process.exit(1);
}

console.log(
  `✅ WXML事件绑定↔JS方法对账通过: ${checkedFiles} wxml / ${totalStatic} 静态绑定` +
  ` (动态绑定 ${totalDynamic} 计数不拦, 顶层spread ${totalSpreads} 计数)`
);
