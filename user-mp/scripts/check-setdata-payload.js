#!/usr/bin/env node
/**
 * setData 负载体积静态守卫 (F317, 2026-08-06 猴王自驱lint轮)
 *
 * 小程序 setData = 逻辑层→渲染层跨线程序列化(JSON.stringify) + diff + 视图重排,
 * 序列化成本与负载体积线性相关。微信官方性能指南要求 setData 负载"小而精":
 * 单次大负载 = 一次长跨线程阻塞(渲染掉帧), 且大对象进 data 后每次 diff 都要
 * 深比较(常驻成本)。F298 已覆盖"循环体内 setData"与"相邻同步 setData 对"两类
 * 频次反模式, 但**单次负载体积本身**仍是零静态断言的盲区——人肉评审对
 * "这个字面量是不是塞太多了"没有客观标尺。
 *
 * 不变量(内联对象字面量调用点):
 *   A. 顶层静态键数 ≤ MAX_KEYS (8) —— 键多意味着一次调用搅动多个视图区域,
 *      应拆分为多次局部 setData(path 形式)或先组装
 *   B. 字面量源码长度 ≤ MAX_LEN (512字符) —— 序列化体积的直接代理指标
 * 阈值依据: 全仓实测基线 maxKeys=4 / maxLen=214 (72处内联字面量), 阈值取
 * ~2x 余量作棘轮——现状全绿, 体积膨胀一半即触发评审。
 * 含展开(...x)或计算键([k]:)的字面量键数不可信 → 只查 B 不查 A(不误报)。
 * 非字面量调用(setData(变量))体积不可静态判定 → 豁免(F298 频次族已覆盖其形态)。
 *
 * 活性断言(F306/F308/F311形态, 防豁免吞断言): 扫描js≥1 + setData调用点≥1 +
 * 内联字面量调用点≥1 (本仓基线 21 js / 76 调用点 / 72 字面量)。
 *
 * 提取基线: 字符级状态机同步剥注释+掩字符串内容(保长度, 行号不错位)——
 * 括号配平/字面量定位在掩码文本上进行, 字符串内的括号/花括号不参与结构判定。
 *
 * 扫描范围: app.js + pages/ components/ services/ utils/ config/ 全部 .js
 * (排除 node_modules/scripts/coverage/dist/build/miniprogram_npm/__tests__;
 *  F292 口径——测试夹具是断言脚手架不是出厂代码)。
 *
 * 用法: node scripts/check-setdata-payload.js
 * 缺输入(零个应用js)/调用点为零(提取器失效信号)/字面量为零/任一断言失败 → exit 1 不放行 (F212)
 */
'use strict';

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const SCAN_DIRS = ['pages', 'components', 'services', 'utils', 'config'];
const EXCLUDE_DIRS = new Set(['node_modules', 'scripts', 'coverage', 'dist', 'build', 'miniprogram_npm', '__tests__']);

const MAX_KEYS = 8;
const MAX_LEN = 512;

const QUOTE_STATES = { "'": 'sq', '"': 'dq', '`': 'tq' };
const STATE_QUOTES = { sq: "'", dq: '"', tq: '`' };

/** 字符级六态状态机: 注释/字符串内容替换为空格, 换行保留(保长度→行号不错位)。 */
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

function collectJsFiles(dir, out) {
  if (!fs.existsSync(dir)) return;
  for (const ent of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, ent.name);
    if (ent.isDirectory()) {
      if (EXCLUDE_DIRS.has(ent.name)) continue;
      collectJsFiles(p, out);
    } else if (ent.name.endsWith('.js')) {
      out.push(p);
    }
  }
}

function matchParen(text, openIdx) {
  let depth = 0;
  for (let i = openIdx; i < text.length; i += 1) {
    if (text[i] === '(') depth += 1;
    else if (text[i] === ')') { depth -= 1; if (depth === 0) return i; }
  }
  return -1;
}

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

/** setData 调用 '(' 之后首个非空白字符是 '{' → 内联对象字面量, 返回 [start,end]; 否则 null */
function findInlineLiteral(masked, openParen) {
  const p = skipWs(masked, openParen + 1);
  if (p >= masked.length || masked[p] !== '{') return null;
  const end = matchBrace(masked, p);
  if (end < 0) return null;
  return [p, end];
}

/**
 * 字面量(掩码)顶层(深度1)文本提取: 跳过嵌套 {} / [] / () 整段, 收集深度1字符。
 * 返回 { text, dynamic } —— dynamic: 出现展开(...)或顶层计算键([)。
 */
function topLevelText(litMasked) {
  let depth = 0;
  let text = '';
  let dynamic = false;
  let i = 0;
  const n = litMasked.length;
  while (i < n) {
    const c = litMasked[i];
    if (depth === 1 && c === '.' && litMasked.slice(i, i + 3) === '...') {
      dynamic = true;
    }
    if (depth === 1 && c === '[') dynamic = true;
    if (c === '{' || c === '[' || c === '(') {
      const closer = c === '(' ? matchParen(litMasked, i) : matchBrace(litMasked, i);
      if (c === '[' && closer < 0) { depth += 1; i += 1; continue; }
      if (closer < 0) { depth += 1; i += 1; continue; }
      if (depth === 1) { i = closer + 1; continue; } // 嵌套整段跳过
      depth += 1; i += 1; continue;
    }
    if (c === '}' || c === ']' || c === ')') { depth -= 1; i += 1; continue; }
    if (depth === 1) text += c;
    i += 1;
  }
  return { text, dynamic };
}

/** 顶层文本中的键计数: IDENT: 形式 + 简写 { IDENT } 形式 */
function countKeys(topText) {
  const matches = topText.match(/(?:^|[,{])\s*(?:[A-Za-z_$][\w$]*)\s*(?=:|,|$)/g);
  return matches ? matches.length : 0;
}

function lineOf(text, idx) {
  let line = 1;
  for (let i = 0; i < idx && i < text.length; i += 1) if (text[i] === '\n') line += 1;
  return line;
}

/** 单文件扫描: 返回 { callSites, literalSites, violations[] } */
function scanFile(f) {
  const src = fs.readFileSync(f, 'utf8');
  const masked = maskSource(src);
  const rel = path.relative(ROOT, f);
  const res = { callSites: 0, literalSites: 0, violations: [] };
  let i = 0;
  while ((i = masked.indexOf('.setData(', i)) >= 0) {
    res.callSites += 1;
    const open = masked.indexOf('(', i + 8);
    if (open < 0) break;
    const close = matchParen(masked, open);
    if (close < 0) { i = open + 1; continue; }
    const lit = findInlineLiteral(masked, open);
    if (lit !== null && lit[1] <= close) {
      res.literalSites += 1;
      checkLiteral(src, masked, rel, lit, res.violations);
    }
    i = close + 1;
  }
  return res;
}

/** 单个字面量的 A/B 不变量检查 */
function checkLiteral(src, masked, rel, lit, violations) {
  const [start, end] = lit;
  const litSrc = src.slice(start, end + 1);
  const line = lineOf(src, start);
  if (litSrc.length > MAX_LEN) {
    violations.push(`${rel}:${line} 字面量长度 ${litSrc.length} > ${MAX_LEN} (序列化体积过大, 拆分为多次局部setData/path形式)`);
  }
  const { text, dynamic } = topLevelText(masked.slice(start, end + 1));
  if (dynamic) return; // 键集不可静态判定 → 只查 B 不查 A(不误报)
  const keys = countKeys(text);
  if (keys > MAX_KEYS) {
    violations.push(`${rel}:${line} 顶层键数 ${keys} > ${MAX_KEYS} (一次调用搅动过多视图区域, 应拆分)`);
  }
}

function main() {
  const files = [];
  for (const d of SCAN_DIRS) collectJsFiles(path.join(ROOT, d), files);
  const appJs = path.join(ROOT, 'app.js');
  if (fs.existsSync(appJs)) files.push(appJs);

  if (files.length === 0) {
    console.error('❌ setData负载守卫: 未找到任何应用js文件(缺输入不放行, F212)');
    process.exit(1);
  }

  let callSites = 0;
  let literalSites = 0;
  const violations = [];
  for (const f of files) {
    const res = scanFile(f);
    callSites += res.callSites;
    literalSites += res.literalSites;
    violations.push(...res.violations);
  }

  if (callSites === 0) {
    console.error('❌ setData负载守卫: setData调用点为零(提取器失效信号, 不放行, F212)');
    process.exit(1);
  }
  if (literalSites === 0) {
    console.error('❌ setData负载守卫: 内联字面量调用点为零(提取器失效或形态漂移信号, 不放行, F212)');
    process.exit(1);
  }
  if (violations.length > 0) {
    console.error(`❌ setData负载守卫发现 ${violations.length} 处超标 (阈值: 键≤${MAX_KEYS}, 长度≤${MAX_LEN}):`);
    violations.forEach((v) => console.error(`  - ${v}`));
    process.exit(1);
  }

  console.log(`✅ setData负载守卫: ${files.length} js / ${callSites} 调用点 / ${literalSites} 内联字面量 全部 ≤ 键${MAX_KEYS}·长度${MAX_LEN}`);
}

main();
