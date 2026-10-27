#!/usr/bin/env node
/**
 * 组件 triggerEvent 事件名 ↔ wxml 使用侧事件绑定对账守卫 (F329, 2026-08-06 猴王自驱lint轮)
 *
 * 小程序自定义组件的事件契约是纯字符串对接: 组件内 `this.triggerEvent('fav')`
 * 触发, 使用侧 `<station-card bind:fav="onFav">` 接收——两侧之间零编译期校验。
 * 任一侧拼错(组件改成 `favorit` / 使用侧写成 `bind:favoriate`)编译、上传、审核
 * 全程无错, 微信对未触发的自定义事件绑定**静默忽略**: 用户点击收藏按钮, handler
 * 永远不执行, 页面无报错无提示(F295族'静默no-op是最恶漂移')。F323 对账守卫
 * 覆盖了组件的属性侧(properties↔wxml属性), 事件侧当时整体豁免(无静态声明源)——
 * 本守卫补全事件侧: triggerEvent 调用点就是事件名的声明源。
 *
 * 事件绑定语法语义(守卫分档依据):
 *   - 冒号式 bind:X / catch:X 是自定义事件的专用绑定语法(基础库2.8.1+引入冒号
 *     形态即为消除与原生事件名的歧义) → **严格档**: X 必须命中组件 triggerEvent
 *     触发名集合, 否则该绑定永不触发 = 漂移, exit 1。
 *   - 无冒号式 bindX / catchX 在组件标签上语义二可(自定义事件名 or 原生事件名)
 *     → **宽松档**: X ∈ 触发名集合 ∪ 原生事件白名单 才放行, 避免平台语义歧义
 *     造成误报; 拼错的非原生名(tapp)仍精确拦截。
 *   - 本仓既有绑定全部为冒号式(5处), 宽松档是前瞻防线。
 *
 * 不变量:
 *   A. 组件标签上的冒号式事件绑定名 ⊆ 该组件 triggerEvent 触发名集合(严格)。
 *   B. 组件标签上的无冒号式事件绑定名 ⊆ 触发名集合 ∪ NATIVE_EVENTS(宽松)。
 *   C. 组件 js 中 triggerEvent 参数为变量(静态不可判定)时, 该组件整体豁免并
 *      打印提示(豁免面窄化到单组件, 不吞全量断言)。
 * 反向(触发名无绑定方)不拦: 可选事件(如取消类回调)无绑定方是合法形态。
 *
 * 触发名提取: 组件 js 字符级状态机剥注释(字符串字面量原样保留, 首参在串内)后,
 * 正则提取 triggerEvent('name'/'name') 字面量首参; 触发名允许字母数字下划线连字符。
 * 组件定位与 F323 同源: usingComponents 声明解析(局部json+app.json全局)→组件js;
 * 未注册组件标签由 F323 拦截, 本守卫跳过不重复报。
 *
 * 活性断言(F306/F308/F311形态, 防豁免吞断言): 组件实体 ≥1 + 可判定触发组件 ≥1
 * + wxml 组件标签使用点 ≥1 + 组件标签上的事件绑定点 ≥1 + 去重触发名总数 ≥1
 * (本仓基线 3 实体 / 2 可判定触发组件 / 14 使用点 / 5 绑定点 / 4 去重触发名)。
 *
 * 用法: node scripts/check-event-usage.js
 * 缺输入(零组件实体)/零使用点/零绑定点/零触发名(提取器失效信号)/任一断言失败
 * → exit 1 不放行 (F212)
 */
'use strict';

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');

/** 原生事件白名单(宽松档豁免域: view/button/scroll-view 等原生元素事件名) */
const NATIVE_EVENTS = new Set([
  'tap', 'longpress', 'longtap',
  'touchstart', 'touchmove', 'touchend', 'touchcancel',
  'transitionend', 'animationstart', 'animationiteration', 'animationend'
]);

const QUOTE_STATES = { "'": 'sq', '"': 'dq', '`': 'tq' };
const STATE_QUOTES = { sq: "'", dq: '"', tq: '`' };

/** 字符级六态状态机: 注释内容替换为空格, 字符串字面量原样保留(triggerEvent首参在字符串内, 掩串=抹掉提取目标, F329接手轮修复), 换行保留(保长度→行号不错位)。 */
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
      if (c === '\\') { out += c + d; i += 2; continue; }
      if (c === STATE_QUOTES[state]) state = 'code';
      out += c; i += 1; continue;
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

/** 组件 js 的 triggerEvent 触发名提取: { fired:Set, decidable:boolean } */
function extractTriggerEvents(jsPath) {
  const src = fs.readFileSync(jsPath, 'utf8');
  const masked = maskSource(src);
  const fired = new Set();
  const re = /triggerEvent\s*\(\s*(['"])([\w-]+)\1/g;
  let m;
  while ((m = re.exec(masked)) !== null) fired.add(m[2]);
  // 参数非字面量(变量/表达式) = 静态不可判定信号
  const dynamicRe = /triggerEvent\s*\(\s*[^'"`\s)]/;
  const decidable = !dynamicRe.test(masked);
  return { fired, decidable };
}

/** usingComponents 条目 → 组件 js 绝对路径; 解析失败返回 null(悬空声明) */
function resolveComponentJs(fromJsonPath, compPath) {
  const base = compPath.startsWith('/') ? ROOT : path.dirname(fromJsonPath);
  const abs = path.resolve(base, compPath.replace(/^\//, ''));
  const candidates = [`${abs}.js`, path.join(abs, 'index.js')];
  for (const c of candidates) if (fs.existsSync(c)) return c;
  return null;
}

/** 收集 json→usingComponents 声明表: [{ jsonPath, map: { tagNameLower: {fired, decidable} } }] */
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
        // 悬空声明由 F323(prop-usage)拦截, 本守卫跳过避免重复报
        continue;
      }
      map.set(tag.toLowerCase(), extractTriggerEvents(jsPath));
    }
    decls.push({ jsonPath: jp, map });
  }
  return decls;
}

/** 组件实体遍历: components/ 下含 component:true json 的目录, 目录名=标签名 */
function collectEntities() {
  const entities = new Map(); // tagNameLower -> { fired, decidable }
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
    entities.set(ent.name.toLowerCase(), fs.existsSync(jsPath)
      ? extractTriggerEvents(jsPath)
      : { fired: new Set(), decidable: true });
  }
  return entities;
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

/** 单 wxml 扫描: 返回 { sites, bindSites, violations, exempted } */
function scanWxmlFile(wf, decls, globalMap, entities) {
  const rel = path.relative(ROOT, wf);
  const masked = maskWxmlComments(fs.readFileSync(wf, 'utf8'));
  const localDecl = decls.find((d) => path.resolve(d.jsonPath) === path.resolve(wf.replace(/\.wxml$/, '.json')));
  const tagMap = new Map([...globalMap, ...(localDecl ? localDecl.map : [])]);
  const violations = [];
  const exempted = new Set();
  let sites = 0;
  let bindSites = 0;
  const tagRe = /<[A-Za-z][\w-]*(?:\s+[^<>]*?)?\/?>/g;
  let tm;
  while ((tm = tagRe.exec(masked)) !== null) {
    const tagText = tm[0];
    const tagName = /^<([A-Za-z][\w-]*)/.exec(tagText)[1];
    if (!entities.has(tagName.toLowerCase())) continue; // 非组件实体标签(原生标签)
    sites += 1;
    const entry = tagMap.get(tagName.toLowerCase());
    if (!entry) continue; // 未注册组件标签 → F323 拦截, 本守卫不重复报
    for (const attr of extractAttrs(tagText)) {
      const name = attr.name;
      const colonMatch = /^(bind|catch):(.+)$/.exec(name);
      const glueMatch = /^(bind|catch)([A-Za-z][\w-]*)$/.exec(name);
      if (!colonMatch && !glueMatch) continue;
      bindSites += 1;
      if (!entry.decidable) { exempted.add(tagName); continue; } // 动态triggerEvent组件窄化豁免
      const isColon = Boolean(colonMatch);
      const eventName = isColon ? colonMatch[2] : glueMatch[2];
      const ok = entry.fired.has(eventName) || (!isColon && NATIVE_EVENTS.has(eventName));
      if (!ok) {
        const line = lineOf(masked, tm.index + tagText.indexOf(name));
        const hint = entry.fired.size > 0 ? [...entry.fired].join('/') : '空(该组件无triggerEvent触发点)';
        violations.push(`${rel}:${line} <${tagName}> ${isColon ? '冒号式' : '无冒号式'}事件绑定 "${name}" 的事件名 "${eventName}" 未在组件 triggerEvent 触发名集合(绑定永不触发=静默no-op; 触发名: ${hint})`);
      }
    }
  }
  return { sites, bindSites, violations, exempted };
}

function main() {
  const entities = collectEntities();
  if (entities.size === 0) {
    console.error('❌ 组件事件对账: 未找到任何组件实体(components/*/index.json component:true, 缺输入不放行, F212)');
    process.exit(1);
  }
  const decls = collectDeclarations();
  const appJsonPath = path.join(ROOT, 'app.json');
  const globalDecl = decls.find((d) => path.resolve(d.jsonPath) === appJsonPath);
  const globalMap = globalDecl ? globalDecl.map : new Map();

  const wxmlFiles = walkFiles(['pages', 'components'], '.wxml');
  let usageSites = 0;
  let bindSites = 0;
  const violations = [];
  const exempted = new Set();
  for (const wf of wxmlFiles) {
    const r = scanWxmlFile(wf, decls, globalMap, entities);
    usageSites += r.sites;
    bindSites += r.bindSites;
    violations.push(...r.violations);
    r.exempted.forEach((t) => exempted.add(t));
  }

  const decidableFiring = [...entities.values()].filter((e) => e.decidable && e.fired.size > 0);
  const firedNames = new Set();
  for (const e of entities.values()) for (const n of e.fired) firedNames.add(n);

  if (decidableFiring.length === 0) {
    console.error('❌ 组件事件对账: 无任何可静态判定的triggerEvent触发组件(提取器失效或形态漂移信号, 不放行, F212)');
    process.exit(1);
  }
  if (usageSites === 0) {
    console.error('❌ 组件事件对账: wxml组件标签使用点为零(提取器失效信号, 不放行, F212)');
    process.exit(1);
  }
  if (bindSites === 0) {
    console.error('❌ 组件事件对账: 组件标签上的事件绑定点为零(提取器失效信号, 不放行, F212)');
    process.exit(1);
  }
  if (firedNames.size === 0) {
    console.error('❌ 组件事件对账: triggerEvent触发名总数为零(提取器失效或形态漂移信号, 不放行, F212)');
    process.exit(1);
  }
  if (violations.length > 0) {
    console.error(`❌ 组件事件对账发现 ${violations.length} 处绑定-触发名失配:`);
    violations.forEach((v) => console.error(`  - ${v}`));
    process.exit(1);
  }

  if (exempted.size > 0) console.log(`ℹ️ 动态triggerEvent豁免组件(跳过绑定校验): ${[...exempted].join('/')}`);
  console.log(`✅ 组件事件对账: ${entities.size} 组件实体 / ${usageSites} 使用点 / ${bindSites} 事件绑定点 / ${firedNames.size} 去重触发名 全部命中(冒号式绑定名⊆triggerEvent触发名, 失配=绑定永不触发的静默no-op, 零容忍)`);
}

main();
