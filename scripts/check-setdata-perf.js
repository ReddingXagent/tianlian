#!/usr/bin/env node
/**
 * setData 性能反模式静态守卫 (F298, 2026-08-05 猴王自驱lint轮)
 *
 * 小程序 setData = 逻辑层→渲染层跨线程序列化 + diff + 视图重排, 是渲染性能
 * 的第一瓶颈(微信官方性能指南反复强调"避免频繁/大量 setData")。小程序无
 * tsc/编译期约束, 两类高频反模式零静态断言:
 *   ① 循环体内 setData (for/while/do-while/数组迭代方法回调): N 次迭代 =
 *      N 次跨线程序列化+渲染(渲染风暴), 列表页初始化/批量操作最易踩
 *      ——正确形态是循环外组装好对象一次性 setData
 *   ② 相邻同步 setData 对 (this.setData(a); this.setData(b); 紧邻无间隔):
 *      两次调用间无异步/渲染间隙, 完全可合并为一次调用省一次跨线程往返
 * 两类都属"功能正确但性能静默劣化", 代码评审人肉难穷尽, 自动化为门禁。
 *
 * 不变量:
 *   A. .setData( 调用点集 ∩ 任一循环体区间 = ∅
 *   B. 任一 setData 调用的紧邻下一语句不得是另一 setData 调用
 * 循环体区间: for/while 括号平衡后语句体(花括号块或单语句)、do 块体、
 * 数组迭代方法(forEach/map/filter/some/every)回调体(花括号块或箭头表达式体)。
 * 嵌套循环双重命中按各循环独立报告(每层都是真渲染放大)。
 *
 * 提取基线: 字符级状态机同步剥注释+掩字符串内容(保长度, 行号不错位)——
 * 结构扫描(括号配平/循环体定位)在掩码文本上进行, 字符串内的括号/分号/
 * setData 字样不参与结构判定也不误报。
 *
 * 扫描范围: app.js + pages/ components/ services/ utils/ config/ 全部 .js
 * (排除 node_modules/scripts/coverage/dist/build/miniprogram_npm/__tests__;
 *  F292 口径——测试夹具模拟调用是断言脚手架不是出厂代码)。
 *
 * 用法: node scripts/check-setdata-perf.js
 * 缺输入(零个应用js)/setData调用点为零(提取器失效信号)/任一断言失败 → exit 1 不放行 (F212)
 */
'use strict';

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const SCAN_DIRS = ['pages', 'components', 'services', 'utils', 'config'];
const EXCLUDE_DIRS = new Set(['node_modules', 'scripts', 'coverage', 'dist', 'build', 'miniprogram_npm', '__tests__']);

const SETDATA_RE = /\.setData\s*\(/g;
const PAREN_LOOP_RE = /\b(?:for|while)\s*\(/g;
const DO_RE = /\bdo\b/g;
const ITER_RE = /\.(?:forEach|map|filter|some|every)\s*\(/g;
const SETDATA_AT_RE = /^(?:this|self|that)\.setData\s*\(/;
const STATE_QUOTES = { sq: "'", dq: '"', tq: '`' };
const QUOTE_STATES = { "'": 'sq', '"': 'dq', '`': 'tq' };

/**
 * 字符级状态机: code/line/block/sq/dq/tq 六态。注释与字符串内容替换为空格,
 * 换行原样保留(保长度→行号不错位)。结构扫描只信任掩码文本。
 */
function maskSource(src) {
  let out = '';
  let state = 'code';
  let i = 0;
  const n = src.length;
  while (i < n) {
    const c = src[i];
    const d = i + 1 < n ? src[i + 1] : '';
    if (state === 'line') {
      if (c === '\n') state = 'code';
      out += c === '\n' ? c : ' ';
      i += 1; continue;
    }
    if (state === 'block') {
      if (c === '*' && d === '/') { state = 'code'; out += '  '; i += 2; continue; }
      out += c === '\n' ? c : ' ';
      i += 1; continue;
    }
    if (state !== 'code') {
      // 字符串态: 内容掩码, 引号本体保留(结构上引号无害)
      if (c === '\\') { out += '  '; i += 2; continue; }
      if (c === STATE_QUOTES[state]) state = 'code';
      out += c === '\n' ? c : ' ';
      i += 1; continue;
    }
    if (c === '/' && d === '/') { state = 'line'; out += '  '; i += 2; continue; }
    if (c === '/' && d === '*') { state = 'block'; out += '  '; i += 2; continue; }
    const nextState = QUOTE_STATES[c];
    if (nextState) state = nextState;
    out += c; i += 1;
  }
  return out;
}

/** 从 openIdx 处 '(' 配平到对应 ')', 返回 ')' 下标; 失败返回 -1 */
function matchParen(text, openIdx) {
  let depth = 0;
  for (let i = openIdx; i < text.length; i += 1) {
    if (text[i] === '(') depth += 1;
    else if (text[i] === ')') { depth -= 1; if (depth === 0) return i; }
  }
  return -1;
}

/** 从 openIdx 处 '{' 配平到对应 '}', 返回 '}' 下标; 失败返回 -1 */
function matchBrace(text, openIdx) {
  let depth = 0;
  for (let i = openIdx; i < text.length; i += 1) {
    if (text[i] === '{') depth += 1;
    else if (text[i] === '}') { depth -= 1; if (depth === 0) return i; }
  }
  return -1;
}

function skipWs(text, i) {
  let j = i;
  while (j < text.length && /\s/.test(text[j])) j += 1;
  return j;
}

/** 循环头之后的语句体: 花括号块 [open,close] 或单语句 [start, ';'或行尾] */
function statementBody(text, afterParen) {
  const j = skipWs(text, afterParen);
  if (j >= text.length) return null;
  if (text[j] === '{') {
    const close = matchBrace(text, j);
    if (close < 0) return null;
    return [j, close];
  }
  let end = j;
  while (end < text.length && text[end] !== ';' && text[end] !== '\n') end += 1;
  return [j, end];
}

/** 迭代方法调用区间 [openParen, closeParen) 内的回调体; 找不到回调返回 null */
function callbackBody(text, openParen, closeParen) {
  const seg = text.slice(openParen + 1, closeParen);
  const arrowIdx = seg.indexOf('=>');
  const fnIdx = seg.search(/\bfunction\b/);
  let bodyRel; // 相对 seg (箭头分支赋值; function分支提前return)
  if (arrowIdx >= 0 && (fnIdx < 0 || arrowIdx < fnIdx)) {
    bodyRel = skipWs(seg, arrowIdx + 2);
  } else if (fnIdx >= 0) {
    const pOpen = seg.indexOf('(', fnIdx);
    if (pOpen < 0) return null;
    const pClose = matchParen(seg, pOpen);
    if (pClose < 0) return null;
    const bOpen = skipWs(seg, pClose + 1);
    if (seg[bOpen] !== '{') return null;
    const bClose = matchBrace(seg, bOpen);
    if (bClose < 0) return null;
    return [openParen + 1 + bOpen, openParen + 1 + bClose];
  } else {
    return null;
  }
  if (bodyRel >= seg.length) return null;
  if (seg[bodyRel] === '{') {
    const bClose = matchBrace(seg, bodyRel);
    if (bClose < 0) return null;
    return [openParen + 1 + bodyRel, openParen + 1 + bClose];
  }
  // 箭头表达式体: 到区间末尾
  return [openParen + 1 + bodyRel, closeParen];
}

/** 收集文件内全部循环体区间 [{kind, from, to}] */
function loopSpans(text) {
  const spans = [];
  let m;
  PAREN_LOOP_RE.lastIndex = 0;
  while ((m = PAREN_LOOP_RE.exec(text)) !== null) {
    const open = text.indexOf('(', m.index + m[0].length - 1);
    const close = matchParen(text, open);
    if (close < 0) continue;
    const body = statementBody(text, close + 1);
    if (body) spans.push({ kind: m[0].startsWith('for') ? 'for' : 'while', from: body[0], to: body[1] });
  }
  DO_RE.lastIndex = 0;
  while ((m = DO_RE.exec(text)) !== null) {
    const body = statementBody(text, m.index + 2);
    if (body) spans.push({ kind: 'do-while', from: body[0], to: body[1] });
  }
  ITER_RE.lastIndex = 0;
  while ((m = ITER_RE.exec(text)) !== null) {
    const open = m.index + m[0].length - 1;
    const close = matchParen(text, open);
    if (close < 0) continue;
    const body = callbackBody(text, open, close);
    if (body) spans.push({ kind: m[0].slice(1, -1).replace(/\s*\($/, ''), from: body[0], to: body[1] });
  }
  return spans;
}

function lineOf(text, idx) {
  let line = 1;
  for (let i = 0; i < idx && i < text.length; i += 1) {
    if (text[i] === '\n') line += 1;
  }
  return line;
}

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

const violations = [];
let setDataTotal = 0;
let loopTotal = 0;

for (const f of files) {
  const rel = path.relative(ROOT, f).split(path.sep).join('/');
  const text = maskSource(fs.readFileSync(f, 'utf8'));

  const sites = [];
  SETDATA_RE.lastIndex = 0;
  let m;
  while ((m = SETDATA_RE.exec(text)) !== null) sites.push(m.index);
  setDataTotal += sites.length;

  const spans = loopSpans(text);
  loopTotal += spans.length;

  // 断言 A: 循环体内禁 setData
  for (const sp of spans) {
    for (const idx of sites) {
      if (idx > sp.from && idx < sp.to) {
        violations.push(`   ${rel}:${lineOf(text, idx)} —— setData 在 ${sp.kind} 循环体内 (N次迭代=N次跨线程序列化+渲染; 循环外组装对象一次性 setData)`);
      }
    }
  }

  // 断言 B: 紧邻同步 setData 对可合并
  for (const idx of sites) {
    const open = text.indexOf('(', idx);
    const close = matchParen(text, open);
    if (close < 0) continue;
    const j = skipWs(text, close + 1);
    if (text[j] === ';') {
      const k = skipWs(text, j + 1);
      if (SETDATA_AT_RE.test(text.slice(k, k + 30))) {
        violations.push(`   ${rel}:${lineOf(text, idx)} —— 相邻两次 setData 间无异步/渲染间隔, 应合并为一次调用 (省一次跨线程往返)`);
      }
    }
  }
}

if (setDataTotal === 0) {
  console.error('❌ 提取器失效信号: 全仓零个 .setData( 调用点 (pages/ 页面应至少有一处)');
  process.exit(1);
}

if (violations.length > 0) {
  console.error(`❌ setData 性能反模式: ${violations.length} 处`);
  for (const v of violations) console.error(v);
  process.exit(1);
}

console.log(`✅ setData 性能反模式对账通过: ${setDataTotal} 个 setData 调用点零循环体命中零相邻对 (扫描 ${files.length} 个 .js, ${loopTotal} 个循环/迭代体区间)`);
