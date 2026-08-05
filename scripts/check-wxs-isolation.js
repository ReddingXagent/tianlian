#!/usr/bin/env node
/**
 * wxs视图层隔离双向对账守卫 (F305, 2026-08-05 猴王自驱lint轮)
 *
 * 漂移场景: wxs是小程序视图层专属脚本语言(独立运行时, 仅wxml可消费),
 * 与逻辑层js完全隔离。三类静默漂移:
 *   ①孤儿wxs文件: 实体写了但没有wxml <wxs src>声明引用 → 永不执行,
 *     纯死代码(与F284孤儿组件/F258孤儿页同族反向盲区);
 *   ②悬空声明: wxml <wxs src>指向不存在的文件 → 开发者工具编译报错,
 *     但CI/上传链路若无编译步骤则静默通过, 页面渲染侧拿不到module;
 *   ③层级越界: 逻辑层js require/import .wxs文件 → wxs不在js运行时里,
 *     构建可能过但运行时炸/打包产物异常, 属"代码调用↔平台能力"双源失配。
 *
 * 不变量(双向):
 *   A. wxs文件实体集 ⊆ wxml <wxs src>声明解析集 (无孤儿wxs)
 *   B. wxml <wxs src>声明解析集 ⊆ wxs文件实体集 (无悬空声明)
 *   C. js require/import .wxs 调用点 = 0 (视图层脚本禁逻辑层引用)
 *
 * 提取口径: 实体侧全仓walk .wxs文件; 声明侧全仓walk .wxml剥<!-- -->
 * 注释后提取 <wxs ... src="..."> (内联<wxs module>无文件不参与对账);
 * src路径归一化: /开头=项目根相对, 否则声明方wxml目录相对, http(s)://
 * 外部引用豁免计数。js侧剥行/块注释(保字符串, require路径在字符串内),
 * 扫 app.js + pages/components/services/utils/config 全部.js,
 * __tests__豁免(F292口径——fixture是断言脚手架非 shipped 代码)。
 *
 * 零态合法性: 本仓当前未使用wxs(0实体/0声明)是合法一致态, exit 0
 * 且显式输出防误读(F302形态); 提取失败信号=全仓零wxml文件, exit 1。
 *
 * 用法: node scripts/check-wxs-isolation.js
 * 缺输入(零wxml文件)/任一断言失败 → exit 1 不放行 (F212缺输入不放行)
 */
'use strict';

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const SKIP_SEGMENTS = new Set(['__tests__', 'node_modules', 'miniprogram_npm']);

function toRelPosix(absPath) {
  return path.relative(ROOT, absPath).split(path.sep).join('/');
}

function *walk(dir, ext) {
  if (!fs.existsSync(dir)) return;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (SKIP_SEGMENTS.has(entry.name)) continue;
    if (entry.name.startsWith('.')) continue; // .git 等
    const abs = path.join(dir, entry.name);
    if (entry.isDirectory()) yield* walk(abs, ext);
    else if (entry.isFile() && entry.name.endsWith(ext)) yield abs;
  }
}

// 剥离注释, 保字符串内容(require路径在字符串内), 保行号(换原位换行)
// 状态机查表分发(F292同法, 每步函数低复杂度)
const QUOTE_STATES = { "'": 'sq', '"': 'dq', '`': 'tq' };

function stepCode(src, i) {
  const c = src[i];
  const c2 = src[i + 1] || '';
  if (c === '/' && c2 === '/') return { text: '  ', state: 'line', next: i + 2 };
  if (c === '/' && c2 === '*') return { text: '  ', state: 'block', next: i + 2 };
  return { text: c, state: QUOTE_STATES[c] || 'code', next: i + 1 };
}

function stepLineComment(src, i) {
  if (src[i] === '\n') return { text: '\n', state: 'code', next: i + 1 };
  return { text: ' ', state: 'line', next: i + 1 };
}

function stepBlockComment(src, i) {
  if (src[i] === '*' && src[i + 1] === '/') return { text: '  ', state: 'code', next: i + 2 };
  return { text: src[i] === '\n' ? '\n' : ' ', state: 'block', next: i + 1 };
}

function stepString(src, i, state) {
  const c = src[i];
  if (c === '\\') return { text: c + (src[i + 1] || ''), state, next: i + 2 };
  return { text: c, state: QUOTE_STATES[c] === state ? 'code' : state, next: i + 1 };
}

const STATE_STEPS = {
  code: stepCode,
  line: stepLineComment,
  block: stepBlockComment,
  sq: stepString,
  dq: stepString,
  tq: stepString,
};

function stripComments(src) {
  let out = '';
  let i = 0;
  let state = 'code';
  while (i < src.length) {
    const step = STATE_STEPS[state](src, i, state);
    out += step.text;
    state = step.state;
    i = step.next;
  }
  return out;
}

// --- 实体侧: 全仓 .wxs 文件 ---
const entities = new Map(); // relPosix -> abs
for (const abs of walk(ROOT, '.wxs')) entities.set(toRelPosix(abs), abs);

// --- 声明侧: 全仓 .wxml 的 <wxs src> ---
const wxmlFiles = [...walk(ROOT, '.wxml')];
if (wxmlFiles.length === 0) {
  console.error('❌ 缺输入: 全仓未扫到任何wxml文件(提取失败信号, F212不放行)');
  process.exit(1);
}
const declared = new Map(); // relPosix -> [声明位置]
let externalRefs = 0;
const WXS_SRC_RE = /<wxs\b[^>]*?\bsrc\s*=\s*["']([^"']+)["'][^>]*\/?>/g;
for (const abs of wxmlFiles) {
  const rel = toRelPosix(abs);
  const text = fs.readFileSync(abs, 'utf8').replace(/<!--[\s\S]*?-->/g, (m) => m.replace(/[^\n]/g, ' '));
  let m;
  WXS_SRC_RE.lastIndex = 0;
  while ((m = WXS_SRC_RE.exec(text)) !== null) {
    const raw = m[1];
    if (/^https?:\/\//.test(raw)) { externalRefs += 1; continue; }
    const resolved = raw.startsWith('/')
      ? path.join(ROOT, raw)
      : path.join(path.dirname(abs), raw);
    const relResolved = toRelPosix(path.resolve(resolved));
    if (!declared.has(relResolved)) declared.set(relResolved, []);
    declared.get(relResolved).push(rel);
  }
}

// --- 逻辑层越界侧: js require/import .wxs ---
const jsScopes = ['pages', 'components', 'services', 'utils', 'config'];
const jsFiles = [];
const appJs = path.join(ROOT, 'app.js');
if (fs.existsSync(appJs)) jsFiles.push(appJs);
for (const scope of jsScopes) {
  for (const abs of walk(path.join(ROOT, scope), '.js')) jsFiles.push(abs);
}
const REQUIRE_WXS_RE = /\brequire\s*\(\s*["'][^"']*\.wxs["']\s*\)/g;
const IMPORT_WXS_RE = /\bimport\b[^;'"]*?["'][^"']*\.wxs["']/g;
const jsHits = [];
let jsScanned = 0;
for (const abs of jsFiles) {
  jsScanned += 1;
  const text = stripComments(fs.readFileSync(abs, 'utf8'));
  const rel = toRelPosix(abs);
  for (const re of [REQUIRE_WXS_RE, IMPORT_WXS_RE]) {
    re.lastIndex = 0;
    let m;
    while ((m = re.exec(text)) !== null) {
      const line = text.slice(0, m.index).split('\n').length;
      jsHits.push(`${rel}:${line} ${m[0].trim()}`);
    }
  }
}

// --- 断言 ---
let failed = false;

for (const rel of [...entities.keys()].sort()) {
  if (!declared.has(rel)) {
    console.error(`❌ 孤儿wxs(实体无声明, 永不执行): ${rel}`);
    failed = true;
  }
}
for (const [rel, from] of [...declared.entries()].sort()) {
  if (!entities.has(rel)) {
    console.error(`❌ 悬空声明(<wxs src>指向不存在文件): ${rel} ← ${from.join(', ')}`);
    failed = true;
  }
}
for (const hit of jsHits) {
  console.error(`❌ 逻辑层越界引用wxs(wxs仅视图层可消费): ${hit}`);
  failed = true;
}
if (failed) {
  console.error('wxs隔离对账失败');
  process.exit(1);
}

if (entities.size === 0 && declared.size === 0 && jsHits.length === 0) {
  console.log(`✅ wxs隔离对账通过(未使用wxs, guard-first零命中: 0实体/0声明/0越界; ${wxmlFiles.length} wxml/${jsScanned} js扫描, ${externalRefs}外部引用豁免)`);
} else {
  console.log(`✅ wxs隔离对账通过: ${entities.size}实体=${declared.size}声明(双向吻合), 0越界引用(${wxmlFiles.length} wxml/${jsScanned} js扫描, ${externalRefs}外部引用豁免)`);
}
