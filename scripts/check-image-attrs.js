#!/usr/bin/env node
/**
 * 原生 <image> 组件属性白名单 + mode 值域守卫 (F337, 2026-08-06 猴王自驱lint轮)
 *
 * 背景: 微信原生内置组件的非法属性/非法枚举值零编译期校验——<image> 上拼错
 * 属性名(modes=)微信静默忽略(图片按默认行为渲染, 页面零报错), mode 拼错值
 * (aspectFitt)静默回落 scaleToFill(图片变形/拉伸, 零报错)。与 F323(自定义
 * 组件属性↔properties声明对账)互补: F323 管组件实体标签, 原生内置标签的
 * 属性域此前无任何静态断言(F295族静默no-op最恶漂移)。
 *
 * 不变量:
 *   A. <image> 标签上的属性名 ⊆ image官方属性域(src/mode/lazy-load/webp/
 *      show-menu-by-longpress/aria-role/aria-label) ∪ 通用豁免域(id/class/
 *      style/hidden/animation/wx:与data-前缀族) ∪ 事件绑定域(bind与catch与mut-bind与capture族,
 *      连字符式与冒号式)。
 *   B. mode 静态字面量值 ⊆ 官方值域(scaleToFill/aspectFit/aspectFill/widthFix/
 *      heightFix/top/bottom/center/left/right/top left/top right/bottom left/
 *      bottom right, 大小写敏感); {{...}} 动态绑定值静态不可判定→豁免
 *      (F330语义: 无信息时不存在"默认即高危"前提)。
 *
 * 活性断言(F306/F308/F311形态, 防豁免吞断言): wxml扫描数 ≥1 + <image> 标签
 * 数 ≥1 + mode 声明点数 ≥1 (基线 14 wxml / 2 标签 / 2 mode)。
 * 缺输入(wxml为零) / <image>标签为零(提取器失效信号) / 任一断言失败 -> exit 1 (F212)。
 *
 * 扫描域: pages/ components/ 全部 wxml + app.wxml(若存在); 注释掩码保长度,
 * 开标签终点用花括号深度扫描({{...}}内可能含>字符, F318铁律)。
 */
'use strict';

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');

/** image 官方属性域(大小写按官方字面量) */
const IMAGE_ATTRS = new Set([
  'src', 'mode', 'lazy-load', 'webp', 'show-menu-by-longpress', 'aria-role', 'aria-label',
]);
/** 通用豁免域(F323同口径扩展: 原生标签亦有 animation) */
const GENERIC_EXEMPT = new Set(['id', 'class', 'style', 'hidden', 'animation']);
/** mode 官方值域(大小写敏感; 九宫格含空格形态) */
const MODE_VALUES = new Set([
  'scaleToFill', 'aspectFit', 'aspectFill', 'widthFix', 'heightFix',
  'top', 'bottom', 'center', 'left', 'right',
  'top left', 'top right', 'bottom left', 'bottom right',
]);

function isExemptAttr(name) {
  if (GENERIC_EXEMPT.has(name)) return true;
  if (name.startsWith('wx:') || name.startsWith('data-')) return true;
  return /^(?:bind|catch|mut-bind|capture-bind|capture-catch)(?::|-)[\w-]+$/.test(name);
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

/** 从 startIdx('<'处)起花括号深度扫描开标签终点(F318铁律: {{...}}内的>不误断), 返回终点下标或-1 */
function findTagEnd(text, startIdx) {
  let depth = 0;
  let quote = null;
  for (let i = startIdx + 1; i < text.length; i += 1) {
    const c = text[i];
    if (quote) { if (c === quote) quote = null; continue; }
    if (c === '"' || c === "'") { quote = c; continue; }
    if (c === '{') { depth += 1; continue; }
    if (c === '}') { depth = Math.max(0, depth - 1); continue; }
    if (depth === 0 && c === '>') return i;
  }
  return -1;
}

/** 开标签属性提取(含值): 返回 [{ name, value(null=未赋值), idx }] */
function extractAttrs(tagText) {
  const attrs = [];
  const re = /([A-Za-z_:][\w:.-]*)(?:\s*=\s*("([^"]*)"|'([^']*)'))?/g;
  const body = tagText.replace(/^<[A-Za-z][\w-]*/, '');
  const base = tagText.length - body.length;
  let m;
  while ((m = re.exec(body)) !== null) {
    let value = null;
    if (m[3] !== undefined) value = m[3];
    else if (m[4] !== undefined) value = m[4];
    attrs.push({ name: m[1], value, idx: base + m.index });
    if (m.index === re.lastIndex) re.lastIndex += 1;
  }
  return attrs;
}

function walkWxml(dirs) {
  const out = [];
  for (const d of dirs) {
    const abs = path.join(ROOT, d);
    if (!fs.existsSync(abs)) continue;
    const stack = [abs];
    while (stack.length) {
      const cur = stack.pop();
      for (const ent of fs.readdirSync(cur, { withFileTypes: true })) {
        const p = path.join(cur, ent.name);
        if (ent.isDirectory()) stack.push(p);
        else if (ent.isFile() && p.endsWith('.wxml')) out.push(p);
      }
    }
  }
  const appWxml = path.join(ROOT, 'app.wxml');
  if (fs.existsSync(appWxml)) out.push(appWxml);
  return out;
}

function main() {
  const files = walkWxml(['pages', 'components']);
  if (files.length === 0) {
    console.error('❌ image属性守卫: 未找到任何wxml(pages/components, 缺输入不放行, F212)');
    process.exit(1);
  }

  const violations = [];
  let imageTags = 0;
  let modeSites = 0;

/** 单 wxml 扫描: <image> 标签属性白名单 + mode 值域, 返回 { tags, modes } */
function scanFile(f, out) {
  const rel = path.relative(ROOT, f);
  const masked = maskWxmlComments(fs.readFileSync(f, "utf8"));
  const re = /<image(?=[\s/>])/g;
  let tags = 0;
  let modes = 0;
  let m;
  while ((m = re.exec(masked)) !== null) {
    const end = findTagEnd(masked, m.index);
    if (end < 0) continue;
    const tagText = masked.slice(m.index, end + 1);
    tags += 1;
    for (const attr of extractAttrs(tagText)) {
      if (attr.name === "mode") {
        modes += 1;
        if (attr.value !== null && !attr.value.startsWith("{{") && !MODE_VALUES.has(attr.value)) {
          const line = lineOf(masked, m.index + tagText.indexOf("mode"));
          out.push(`${rel}:${line} <image> mode="${attr.value}" 不在官方值域(微信静默回落scaleToFill=图片变形零报错; 合法值: ${[...MODE_VALUES].join("/")})`);
        }
        continue;
      }
      if (IMAGE_ATTRS.has(attr.name) || isExemptAttr(attr.name)) continue;
      const line = lineOf(masked, m.index + attr.idx);
      out.push(`${rel}:${line} <image> 未知属性 "${attr.name}"(微信静默忽略=属性永不生效零报错; 官方属性域: ${[...IMAGE_ATTRS].join("/")})`);
    }
  }
  return { tags, modes };
}

  for (const f of files) {
    const r = scanFile(f, violations);
    imageTags += r.tags;
    modeSites += r.modes;
  }

  if (imageTags === 0) {
    console.error('❌ image属性守卫: <image>标签数为零(提取器失效信号, 不放行, F212)');
    process.exit(1);
  }
  if (modeSites === 0) {
    console.error('❌ image属性守卫: mode声明点为零(活性断言失败, 防豁免吞断言, F212)');
    process.exit(1);
  }

  if (violations.length > 0) {
    console.error(`❌ image属性白名单对账失败(${violations.length}处):`);
    for (const v of violations) console.error(`  - ${v}`);
    process.exit(1);
  }
  console.log(`✅ image属性守卫: ${files.length} wxml / ${imageTags} <image>标签 / ${modeSites} mode声明点, 属性名⊆官方域∪豁免域 + mode值⊆官方值域 全通过`);
}

main();
