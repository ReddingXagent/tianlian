#!/usr/bin/env node
/**
 * 死handler反向可达性双源对账守卫 (F264, 2026-08-05 猴王自驱lint轮)
 *
 * F252 的反向补盲(F246/F258 同款双向成对模式): F252 正向挡
 * "wxml绑定引用了js不存在的方法"(运行时静默失效, 显性), 本守卫反向挡
 * "js方法既无wxml绑定也无js调用"(死handler, 隐性死实体)。
 * 漂移场景: 重构改名/删wxml绑定后 js 方法残留, 编译期零拦截(小程序无tsc),
 * 死方法长期累积增大维护面与误读成本。
 *
 * 不变量(反向子集):
 *   Page 顶层方法键 / Component methods 键 ⊆ (同目录wxml绑定名集 ∪ 同文件this调用引用集)
 *   - 生命周期/框架键(onLoad/data等)非handler, 白名单排除
 *   - 引用形态: 同文件 this|self|that .NAME (含回调传递形态, 不要求带括号);
 *     同目录 wxml 文本中整词出现(覆盖 {{}} 动态绑定名/data驱动场景)计数不拦
 *   - selectComponent 跨组件调用在本仓不存在(已摸底), 不列入豁免
 *
 * 提取口径与 check-wxml-handlers.js 完全同源(单口径复制, F258模式):
 *   Page: Page({}) 顶层键; Component: Component({methods:{}}) methods 块键;
 *   wxml: pages/ components/ 下全部 *.wxml 的 (bind|catch)[:?]事件="名字"
 *
 * 用法: node scripts/check-dead-handlers.js
 * 缺输入(配对js无Page/Component块)/方法集提取为空/断言失败 → exit 1 不放行
 * (F212缺输入不放行); 首跑零死handler=守卫先行(F258), 非缺陷
 */
'use strict';

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const SCAN_DIRS = ['pages', 'components'];
const BIND_RE = /(?:bind|catch):?[a-z]+\s*=\s*"([^"]+)"/g;
const SKIP_DIRS = new Set(['__tests__', 'node_modules', 'miniprogram_npm']);
// Page 顶层非handler键(生命周期+数据), 不参与死handler判定
const PAGE_FRAMEWORK_KEYS = new Set([
  'data', 'onLoad', 'onShow', 'onReady', 'onHide', 'onUnload',
  'onPullDownRefresh', 'onReachBottom', 'onShareAppMessage',
  'onShareTimeline', 'onPageScroll', 'onResize', 'onTabItemTap',
  'onAddToFavorites', 'onSaveExitState',
]);

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

// 收集目录下全部子目录(跳 SKIP_DIRS), 返回含配对js的 {dir, jsF} 列表
// 配对双命名惯例: page=同名<dirname>.js, component=index.js(接手轮复验撞出:
// 原只认同名js致 components 层整体漏扫, 反向守卫盲区)
function collectPageDirs(base, out) {
  if (!fs.existsSync(base)) return;
  for (const ent of fs.readdirSync(base, { withFileTypes: true })) {
    if (SKIP_DIRS.has(ent.name)) continue;
    const full = path.join(base, ent.name);
    if (!ent.isDirectory()) continue;
    const named = path.join(full, ent.name + '.js');
    const jsF = fs.existsSync(named) ? named : path.join(full, 'index.js');
    if (fs.existsSync(jsF)) out.push({ dir: full, jsF });
    collectPageDirs(full, out);
  }
}

// 提取 js 中的 handler 候选方法集: Page顶层键(排框架键) 或 Component methods 键
function extractMethods(src, relJs) {
  const openIdx = rootObjectIndex(src);
  if (openIdx === -1) {
    console.error(`FAIL ${relJs}: 未找到 Page({ 或 Component({ 块(缺输入不放行, F212)`);
    process.exit(1);
  }
  const isComponent = /Component\s*\(\s*\{/.test(src.slice(0, openIdx + 12));
  if (isComponent) {
    const mIdx = findValueObject(src, openIdx, 'methods');
    if (mIdx === -1) return new Set(); // Component 无 methods 块 = 无handler
    const { keys } = collectKeys(src, mIdx);
    return keys;
  }
  const { keys } = collectKeys(src, openIdx);
  const methods = new Set();
  for (const k of keys) {
    if (!PAGE_FRAMEWORK_KEYS.has(k) && isIdent(k)) methods.add(k);
  }
  return methods;
}

// 同文件 this|self|that .NAME 引用数(含回调传递形态, 不要求带括号)
function countThisRefs(src, name) {
  const re = new RegExp('\\b(?:this|self|that)\\.' + name + '\\b', 'g');
  return (src.match(re) || []).length;
}

// 同目录 wxml 文本中 NAME 整词出现数(覆盖动态绑定名/data驱动引用)
function countWxmlWordRefs(wxmlSources, name) {
  const re = new RegExp('\\b' + name + '\\b', 'g');
  let n = 0;
  for (const w of wxmlSources) n += (w.match(re) || []).length;
  return n;
}

const dead = [];
let methodTotal = 0;
let scanned = 0;

for (const sd of SCAN_DIRS) {
  const dirs = [];
  collectPageDirs(path.join(ROOT, sd), dirs);
  for (const { dir, jsF } of dirs) {
    const src = fs.readFileSync(jsF, 'utf8');
    const methods = extractMethods(src, path.relative(ROOT, jsF));
    if (methods.size === 0) continue;
    scanned += 1;
    methodTotal += methods.size;
    // 同目录 wxml: 绑定集 + 全文
    const wxmlFiles = [];
    collectWxml(dir, wxmlFiles);
    const binds = new Set();
    const wxmlSources = [];
    for (const wf of wxmlFiles) {
      const w = fs.readFileSync(wf, 'utf8');
      wxmlSources.push(w);
      let m;
      BIND_RE.lastIndex = 0;
      while ((m = BIND_RE.exec(w)) !== null) binds.add(m[1]);
    }
    for (const mn of methods) {
      if (binds.has(mn)) continue;
      if (countThisRefs(src, mn) > 0) continue;
      if (countWxmlWordRefs(wxmlSources, mn) > 0) continue;
      dead.push(`${path.relative(ROOT, jsF)} :: ${mn}`);
    }
  }
}

if (methodTotal === 0) {
  console.error('FAIL: 未提取到任何 handler 候选方法(提取口径异常, 缺输入不放行 F212)');
  process.exit(1);
}

if (dead.length > 0) {
  console.error(`FAIL: ${dead.length} 个死handler(js方法既无wxml绑定也无this调用):\n  ` + dead.join('\n  '));
  console.error('处置: 确认废弃→删除方法; 仍在使用→补wxml绑定或检查动态引用形态');
  process.exit(1);
}

console.log(`OK: 死handler反向对账通过 — ${scanned} 个js, ${methodTotal} 个候选方法, 0 死handler`);
