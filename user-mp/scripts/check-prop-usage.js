#!/usr/bin/env node
/**
 * 组件 properties ↔ wxml 使用属性对账守卫 (F323, 2026-08-06 猴王自驱lint轮)
 *
 * 小程序自定义组件的使用属性(wxml标签属性)与组件 properties 声明之间零编译期
 * 校验: 拼错一个属性名(如 `visble`/`show-action`写成`showactions`), 编译、上传、
 * 审核全程无错——微信对未声明属性**静默忽略**, 组件拿到默认值运行, 页面表现为
 * "属性没生效"的隐性降级(F295族'静默no-op是最恶漂移')。mp 无 tsc/schema 校验,
 * 此前零静态断言。
 *
 * 不变量:
 *   A. 使用侧注册 ⊆ 组件实体域 —— wxml 中出现的组件实体同名标签必须已在该
 *      wxml 同名 json(或 app.json 全局) usingComponents 注册; 未注册组件标签 =
 *      微信按未知元素静默不渲染(空态/加载态整块消失且零报错), exit 1。
 *   B. 使用侧属性 ⊆ 声明侧 properties ∪ 通用属性域 —— wxml 组件标签上的每个
 *      非通用属性必须命中该组件 properties 声明(kebab↔camel 归一化后比较);
 *      未声明属性 = 静默忽略漂移, exit 1。
 *   C. model:X 双向绑定剥离前缀后同样 ⊆ properties(绑定到未声明属性同样静默失效)。
 * 通用属性域(豁免): wx:* / data-* / id / class / style / hidden / slot / generic:*;
 * 事件绑定 bind系/catch系 整体豁免(事件侧无静态声明源, triggerEvent 运行时触发)。
 *
 * 声明侧提取: usingComponents 各条目 → 组件 js `properties` 对象顶层键
 * (字符级状态机剥注释+掩字符串后括号配平提取, 支持对象式与构造函数简写式)。
 * 路径解析失败(悬空声明) = 漂移, exit 1。
 *
 * 活性断言(F306/F308/F311形态, 防豁免吞断言): 组件实体 ≥1 + wxml 组件标签
 * 使用点 ≥1 + properties 声明键总数 ≥1 (本仓基线 3 实体 / 14 使用点 / 6 去重键)。
 *
 * 扫描范围: components/ 实体遍历(目录名=标签名) + app.json(全局声明, 若存在)
 * + pages/ components/ 下全部 wxml↔同名json。
 *
 * 用法: node scripts/check-prop-usage.js
 * 缺输入(零声明json)/零使用点(提取器失效信号)/悬空组件路径/任一断言失败 → exit 1 不放行 (F212)
 */
'use strict';

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');

const GENERIC_ATTRS = new Set(['id', 'class', 'style', 'hidden', 'slot']);

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

/** wxml 注释内容掩码(保长度, 行号不错位) */
function maskWxmlComments(src) {
  return src.replace(/<!--[\s\S]*?-->/g, (m) => m.replace(/[^\n]/g, ' '));
}

function lineOf(text, idx) {
  let line = 1;
  for (let i = 0; i < idx && i < text.length; i += 1) if (text[i] === '\n') line += 1;
  return line;
}

function kebabToCamel(s) {
  return s.replace(/-([a-z0-9])/g, (_, c) => c.toUpperCase());
}

function matchBrace(text, openIdx) {
  let depth = 0;
  for (let i = openIdx; i < text.length; i += 1) {
    if (text[i] === '{') depth += 1;
    else if (text[i] === '}') { depth -= 1; if (depth === 0) return i; }
  }
  return -1;
}

/** properties 对象顶层键提取(掩码文本): depth-1 的 IDENT: / "STR": / IDENT, 简写形态 */
function topLevelKeys(objMasked) {
  const keys = new Set();
  let depth = 0;
  let i = 0;
  const n = objMasked.length;
  while (i < n) {
    const c = objMasked[i];
    if (c === '{' || c === '[' || c === '(') {
      const closer = matchAny(objMasked, i);
      if (closer < 0) { i += 1; continue; }
      if (depth === 1) { i = closer + 1; continue; } // 嵌套整段跳过
      depth += 1; i += 1; continue;
    }
    if (c === '}' || c === ']' || c === ')') { depth -= 1; i += 1; continue; }
    if (depth === 1) {
      if (/[A-Za-z_$]/.test(c)) { const r = readIdentKey(objMasked, i); if (r[0]) keys.add(r[0]); i += r[1]; continue; }
      if (c === '"' || c === "'") { const r = readQuotedKey(objMasked, i); if (r[0]) keys.add(r[0]); i = r[1]; continue; }
    }
    i += 1;
  }
  return keys;
}

/** depth-1 标识符键读取: 后随 :/,/} 才计键; 返回 [键|null, 消费长度] */
function readIdentKey(text, i) {
  const m = /^[A-Za-z_$][\w$]*/.exec(text.slice(i));
  const ident = m[0];
  let j = i + ident.length;
  const n = text.length;
  while (j < n && /\s/.test(text[j])) j += 1;
  const isKey = text[j] === ':' || text[j] === ',' || text[j] === '}';
  return [isKey ? ident : null, ident.length];
}

/** depth-1 引号键读取: 后随 : 才计键; 返回 [键|null, 消费终点] */
function readQuotedKey(text, i) {
  const q = text[i];
  const n = text.length;
  let j = i + 1;
  let name = '';
  while (j < n && text[j] !== q) { name += text[j]; j += 1; }
  let k = j + 1;
  while (k < n && /\s/.test(text[k])) k += 1;
  if (text[k] === ':') return [name, j + 1];
  return [null, j + 1];
}

const CLOSERS = { '{': '}', '[': ']', '(': ')' };

function matchAny(text, openIdx) {
  const open = text[openIdx];
  const close = CLOSERS[open];
  let depth = 0;
  for (let i = openIdx; i < text.length; i += 1) {
    if (text[i] === open) depth += 1;
    else if (text[i] === close) { depth -= 1; if (depth === 0) return i; }
  }
  return -1;
}

/** 组件 js 的 properties 顶层键集合 */
function extractProperties(jsPath) {
  const src = fs.readFileSync(jsPath, 'utf8');
  const masked = maskSource(src);
  const idx = masked.search(/(^|[,{\s])properties\s*:/);
  if (idx < 0) return new Set();
  const colon = masked.indexOf(':', idx);
  let p = colon + 1;
  while (p < masked.length && /\s/.test(masked[p])) p += 1;
  if (masked[p] !== '{') return new Set(); // 非常规形态(变量引用等) → 声明不可提取, 按空集
  const end = matchBrace(masked, p);
  if (end < 0) return new Set();
  return topLevelKeys(masked.slice(p, end + 1));
}

/** usingComponents 条目 → 组件 js 绝对路径; 解析失败返回 null(悬空声明) */
function resolveComponentJs(fromJsonPath, compPath) {
  const base = compPath.startsWith('/') ? ROOT : path.dirname(fromJsonPath);
  const abs = path.resolve(base, compPath.replace(/^\//, ''));
  const candidates = [`${abs}.js`, path.join(abs, 'index.js')];
  for (const c of candidates) if (fs.existsSync(c)) return c;
  return null;
}

/** 收集 json→usingComponents 声明表: [{ jsonPath, map: { tagNameLower: propsSet } }] */
function collectDeclarations() {
  const decls = [];
  const jsonCandidates = [];
  const appJson = path.join(ROOT, 'app.json');
  if (fs.existsSync(appJson)) jsonCandidates.push(appJson);
  for (const dir of ['pages', 'components']) {
    const stack = [path.join(ROOT, dir)];
    while (stack.length > 0) {
      const d = stack.pop();
      if (!fs.existsSync(d)) continue;
      for (const ent of fs.readdirSync(d, { withFileTypes: true })) {
        if (ent.name === 'node_modules' || ent.name === 'miniprogram_npm') continue;
        const p = path.join(d, ent.name);
        if (ent.isDirectory()) stack.push(p);
        else if (ent.name.endsWith('.json')) jsonCandidates.push(p);
      }
    }
  }
  for (const jp of jsonCandidates) {
    let parsed;
    try { parsed = JSON.parse(fs.readFileSync(jp, 'utf8')); } catch { parsed = {}; }
    const uc = parsed.usingComponents;
    if (!uc || typeof uc !== 'object') continue;
    const map = new Map();
    for (const [tag, compPath] of Object.entries(uc)) {
      if (typeof compPath !== 'string') continue;
      const jsPath = resolveComponentJs(jp, compPath);
      if (jsPath === null) {
        console.error(`❌ 组件属性对账: ${path.relative(ROOT, jp)} usingComponents "${tag}" → ${compPath} 解析失败(悬空声明=漂移, F212)`);
        process.exit(1);
      }
      map.set(tag.toLowerCase(), extractProperties(jsPath));
    }
    decls.push({ jsonPath: jp, map });
  }
  return decls;
}

/** wxml 标签属性提取(掩码文本): 返回 [{ name, idx }] */
function extractAttrs(tagText) {
  const attrs = [];
  const re = /([A-Za-z_:][\w:.-]*)(?:\s*=\s*(?:"[^"]*"|'[^']*'))?/g;
  const body = tagText.replace(/^<[A-Za-z][\w-]*/, '');
  let m;
  while ((m = re.exec(body)) !== null) {
    attrs.push({ name: m[1], idx: m.index });
    if (m.index === re.lastIndex) re.lastIndex += 1;
  }
  return attrs;
}

/** 组件实体遍历: components/ 下含 component:true json 的目录, 目录名=标签名 */
function collectEntities() {
  const entities = new Map(); // tagNameLower -> props Set
  const cdir = path.join(ROOT, 'components');
  if (!fs.existsSync(cdir)) return entities;
  for (const ent of fs.readdirSync(cdir, { withFileTypes: true })) {
    if (!ent.isDirectory()) continue;
    const jp = path.join(cdir, ent.name, 'index.json');
    if (!fs.existsSync(jp)) continue;
    let parsed;
    try { parsed = JSON.parse(fs.readFileSync(jp, 'utf8')); } catch { parsed = {}; }
    if (parsed.component !== true) continue;
    const jsPath = path.join(cdir, ent.name, 'index.js');
    entities.set(ent.name.toLowerCase(), fs.existsSync(jsPath) ? extractProperties(jsPath) : new Set());
  }
  return entities;
}

function main() {
  const entities = collectEntities();
  if (entities.size === 0) {
    console.error('❌ 组件属性对账: 未找到任何组件实体(components/*/index.json component:true, 缺输入不放行, F212)');
    process.exit(1);
  }
  const decls = collectDeclarations();
  const appJsonPath = path.join(ROOT, 'app.json');
  const globalDecl = decls.find((d) => path.resolve(d.jsonPath) === appJsonPath);
  const globalMap = globalDecl ? globalDecl.map : new Map();

  const wxmlFiles = walkFiles(['pages', 'components'], '.wxml');
  let usageSites = 0;
  const violations = [];
  for (const wf of wxmlFiles) {
    const r = scanWxmlFile(wf, decls, globalMap, entities);
    usageSites += r.sites;
    violations.push(...r.violations);
  }
  const propKeyTotal = countEntityPropKeys(entities);

  if (usageSites === 0) {
    console.error('❌ 组件属性对账: wxml组件标签使用点为零(提取器失效信号, 不放行, F212)');
    process.exit(1);
  }
  if (propKeyTotal === 0) {
    console.error('❌ 组件属性对账: properties声明键总数为零(提取器失效或形态漂移信号, 不放行, F212)');
    process.exit(1);
  }
  if (violations.length > 0) {
    console.error(`❌ 组件属性对账发现 ${violations.length} 处未声明使用属性:`);
    violations.forEach((v) => console.error(`  - ${v}`));
    process.exit(1);
  }

  console.log(`✅ 组件属性对账: ${entities.size} 组件实体 / ${usageSites} 使用点 / ${propKeyTotal} 声明键 全部注册+属性命中(未注册标签=静默不渲染, 未声明属性=静默忽略, 零容忍)`);
}

/** 目录遍历收集指定后缀文件(排除 node_modules/miniprogram_npm) */
function walkFiles(dirs, ext) {
  const files = [];
  for (const dir of dirs) {
    const stack = [path.join(ROOT, dir)];
    while (stack.length > 0) {
      const d = stack.pop();
      if (!fs.existsSync(d)) continue;
      for (const ent of fs.readdirSync(d, { withFileTypes: true })) {
        if (ent.name === 'node_modules' || ent.name === 'miniprogram_npm') continue;
        const p = path.join(d, ent.name);
        if (ent.isDirectory()) stack.push(p);
        else if (ent.name.endsWith(ext)) files.push(p);
      }
    }
  }
  return files;
}

/** 实体 properties 声明键去重总数 */
function countEntityPropKeys(entities) {
  const counted = new Set();
  for (const props of entities.values()) for (const k of props) counted.add(k);
  return counted.size;
}

/** 单 wxml 扫描: 返回 { sites, violations } */
function scanWxmlFile(wf, decls, globalMap, entities) {
  const rel = path.relative(ROOT, wf);
  const masked = maskWxmlComments(fs.readFileSync(wf, 'utf8'));
  // 同名 json 声明 + 全局声明合并(局部优先)
  const localDecl = decls.find((d) => path.resolve(d.jsonPath) === path.resolve(wf.replace(/\.wxml$/, '.json')));
  const tagMap = new Map([...globalMap, ...(localDecl ? localDecl.map : [])]);
  const violations = [];
  let sites = 0;
  const tagRe = /<[A-Za-z][\w-]*(?:\s+[^<>]*?)?\/?>/g;
  let tm;
  while ((tm = tagRe.exec(masked)) !== null) {
    const tagText = tm[0];
    const tagName = /^<([A-Za-z][\w-]*)/.exec(tagText)[1];
    if (!entities.has(tagName.toLowerCase())) continue; // 非组件实体标签(原生标签)
    sites += 1;
    violations.push(...checkEntityTag(tagText, tagName, tagMap, rel, masked, tm.index));
  }
  return { sites, violations };
}

/** 单个组件实体标签: 注册校验 + 属性校验, 返回 violations */
function checkEntityTag(tagText, tagName, tagMap, rel, masked, tagIdx) {
  const props = tagMap.get(tagName.toLowerCase());
  if (!props) {
    const line = lineOf(masked, tagIdx);
    return [`${rel}:${line} <${tagName}> 组件标签未在 usingComponents 注册(微信按未知元素静默不渲染, 整块UI消失且零报错)`];
  }
  const violations = [];
  for (const attr of extractAttrs(tagText)) {
    const name = attr.name;
    if (isExemptAttr(name)) continue;
    let check = name;
    if (name.startsWith('model:')) check = name.slice('model:'.length);
    const camel = kebabToCamel(check);
    if (!props.has(check) && !props.has(camel)) {
      const line = lineOf(masked, tagIdx + tagText.indexOf(name));
      violations.push(`${rel}:${line} <${tagName}> 属性 "${name}" 未在组件 properties 声明(静默忽略漂移; 声明键: ${[...props].join('/') || '空'})`);
    }
  }
  return violations;
}

/** 通用属性域豁免判定 */
function isExemptAttr(name) {
  if (name.startsWith('wx:') || name.startsWith('data-') || name.startsWith('generic:')) return true;
  if (GENERIC_ATTRS.has(name)) return true;
  return /^(bind|catch)(:|$)/.test(name); // 事件绑定整体豁免
}

main();
