#!/usr/bin/env node
/**
 * 原生组件属性域对账守卫 (F344 泛化 F337, 2026-08-06 猴王自驱lint轮)
 *
 * 背景: 微信原生内置组件的非法属性/非法枚举值零编译期校验——属性名拼错
 * (modes=/diabled=)微信静默忽略(属性永不生效, 页面零报错), 枚举值拼错
 * (aspectFitt/tyep=primary)静默回落默认值(图片变形/按钮样式错, 零报错)。
 * F337 只覆盖 <image>; F344 泛化为原生组件登记簿形态, 本轮纳入 <button>
 * (11文件使用, disabled/form-type/open-type 拼错=按钮能力静默失效) 与
 * <input> (3文件使用, type/confirm-type 拼错=键盘形态静默回落)。与 F323
 * (自定义组件属性↔properties声明对账)互补: F323 管组件实体标签, 原生内置
 * 标签的属性域由本守卫静态断言(F295族静默no-op最恶漂移)。
 *
 * 不变量(对登记簿内每个原生标签):
 *   A. 标签上的属性名 ⊆ 该标签官方属性域 ∪ 通用豁免域(id/class/style/
 *      hidden/animation/wx:与data-前缀族) ∪ 事件绑定域(bind与catch族分隔符
 *      可省(bindtap/bind:tap均合法), mut-bind与capture-bind与capture-catch
 *      冒号式)。
 *   B. 已登记枚举属性(image.mode/button.size/type/form-type/lang/
 *      open-type; input.type/confirm-type)的静态字面量值 ⊆ 官方值域
 *      (大小写敏感); {{...}} 动态绑定值静态不可判定→豁免(F330语义:
 *      无信息时不存在"默认即高危"前提)。未登记枚举属性的值不做域检查
 *      (hover-class/placeholder等自由文本域)。
 *
 * 活性断言(F306/F308/F311形态, 防豁免吞断言): wxml扫描数 ≥1 + 各登记标签
 * 数 ≥1 (基线 image 2 / button 15 / input 3) + image mode 声明点 ≥1
 * (基线 2; button/input 的枚举位点静态可为零——open-type 基线未使用,
 * 值域在出现时自动激活, 不设位点下限以免脆断)。
 * 缺输入(wxml为零) / 任一登记标签数为零(提取器失效信号) / 任一断言失败
 * -> exit 1 (F212)。
 *
 * 扫描域: pages/ components/ 全部 wxml + app.wxml(若存在); 注释掩码保长度,
 * 开标签终点用花括号深度扫描({{...}}内可能含>字符, F318铁律)。
 */
'use strict';

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');

/** 原生组件登记簿: 标签 -> { attrs: 官方属性域, enums: 属性 -> 官方值域 } */
const NATIVE_TAGS = {
  image: {
    attrs: new Set([
      'src', 'mode', 'lazy-load', 'webp', 'show-menu-by-longpress', 'aria-role', 'aria-label',
    ]),
    enums: {
      mode: new Set([
        'scaleToFill', 'aspectFit', 'aspectFill', 'widthFix', 'heightFix',
        'top', 'bottom', 'center', 'left', 'right',
        'top left', 'top right', 'bottom left', 'bottom right',
      ]),
    },
  },
  button: {
    attrs: new Set([
      'size', 'type', 'plain', 'disabled', 'loading', 'form-type', 'open-type',
      'hover-class', 'hover-start-time', 'hover-stay-time', 'lang', 'session-from',
      'send-message-title', 'send-message-path', 'send-message-img', 'app-parameter',
      'show-message-card', 'group-id', 'public-id', 'guild-id', 'business-id',
      'aria-role', 'aria-label',
    ]),
    enums: {
      size: new Set(['default', 'mini']),
      type: new Set(['primary', 'default', 'warn']),
      'form-type': new Set(['submit', 'reset']),
      lang: new Set(['zh_CN', 'zh_TW', 'en']),
      'open-type': new Set([
        'contact', 'share', 'getPhoneNumber', 'getRealTimePhoneNumber', 'getUserProfile',
        'launchApp', 'openSetting', 'feedback', 'chooseAvatar', 'agreePrivacyAuthorization',
        'addGroupApp', 'chooseAddress', 'chooseInvoiceTitle', 'subscribe', 'login', 'im',
      ]),
    },
  },
  input: {
    attrs: new Set([
      'value', 'type', 'password', 'placeholder', 'placeholder-style', 'placeholder-class',
      'aria-label', 'disabled', 'maxlength', 'cursor-spacing', 'focus', 'confirm-type',
      'confirm-hold', 'cursor', 'selection-start', 'selection-end', 'adjust-position',
      'hold-keyboard', 'controlled', 'always-embed', 'safe-password-cert',
      'safe-password-length', 'safe-password-timeout', 'safe-password-confirm',
      'safe-password-encryption', 'ignore-focus-event',
    ]),
    enums: {
      type: new Set(['text', 'number', 'idcard', 'digit', 'safe-password', 'nickname']),
      'confirm-type': new Set(['send', 'search', 'next', 'go', 'done']),
    },
  },
};
/** 通用豁免域(F323同口径扩展: 原生标签亦有 animation) */
const GENERIC_EXEMPT = new Set(['id', 'class', 'style', 'hidden', 'animation']);

/**
 * 事件绑定域判定。微信形态: bindtap/bind:tap/catchtap/catch:tap(分隔符可省,
 * F344修正: F337原正则要求bind/catch后必有:-分隔, 会误拦主流bindtap形态) +
 * mut-bind:tap/capture-bind:tap/capture-catch:tap(冒号式)。
 */
function isExemptAttr(name) {
  if (GENERIC_EXEMPT.has(name)) return true;
  if (name.startsWith('wx:') || name.startsWith('data-')) return true;
  if (/^(?:bind|catch)(?::|-)?[\w-]+$/.test(name)) return true;
  return /^mut-bind(?::|-)[\w-]+$/.test(name) || /^capture-(?:bind|catch)(?::|-)[\w-]+$/.test(name);
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
    console.error('❌ 原生组件属性守卫: 未找到任何wxml(pages/components, 缺输入不放行, F212)');
    process.exit(1);
  }

  const violations = [];
  const tagCounts = Object.fromEntries(Object.keys(NATIVE_TAGS).map((t) => [t, 0]));
  let modeSites = 0;

  /** 单标签扫描: 属性白名单 + 枚举值域, 返回 { count, modes } */
  function scanTag(masked, rel, tag, spec, out) {
    const re = new RegExp(`<${tag}(?=[\\s/>])`, 'g');
    let count = 0;
    let modes = 0;
    let m;
    while ((m = re.exec(masked)) !== null) {
      const end = findTagEnd(masked, m.index);
      if (end < 0) continue;
      const tagText = masked.slice(m.index, end + 1);
      count += 1;
      for (const attr of extractAttrs(tagText)) {
        const enumDomain = spec.enums[attr.name];
        if (enumDomain) {
          if (tag === 'image' && attr.name === 'mode') modes += 1;
          if (attr.value !== null && !attr.value.startsWith('{{') && !enumDomain.has(attr.value)) {
            const line = lineOf(masked, m.index + tagText.indexOf(attr.name));
            out.push(`${rel}:${line} <${tag}> ${attr.name}="${attr.value}" 不在官方值域(微信静默回落默认值零报错; 合法值: ${[...enumDomain].join('/')})`);
          }
          continue;
        }
        if (spec.attrs.has(attr.name) || isExemptAttr(attr.name)) continue;
        const line = lineOf(masked, m.index + attr.idx);
        out.push(`${rel}:${line} <${tag}> 未知属性 "${attr.name}"(微信静默忽略=属性永不生效零报错; 官方属性域: ${[...spec.attrs].join('/')})`);
      }
    }
    return { count, modes };
  }

  /** 单 wxml 扫描: 登记簿内各原生标签 */
  function scanFile(f, out) {
    const rel = path.relative(ROOT, f);
    const masked = maskWxmlComments(fs.readFileSync(f, 'utf8'));
    for (const [tag, spec] of Object.entries(NATIVE_TAGS)) {
      const r = scanTag(masked, rel, tag, spec, out);
      tagCounts[tag] += r.count;
      modeSites += r.modes;
    }
  }

  for (const f of files) scanFile(f, violations);

  for (const [tag, n] of Object.entries(tagCounts)) {
    if (n === 0) {
      console.error(`❌ 原生组件属性守卫: <${tag}>标签数为零(提取器失效信号, 不放行, F212)`);
      process.exit(1);
    }
  }
  if (modeSites === 0) {
    console.error('❌ 原生组件属性守卫: image mode声明点为零(活性断言失败, 防豁免吞断言, F212)');
    process.exit(1);
  }

  if (violations.length > 0) {
    console.error(`❌ 原生组件属性域对账失败(${violations.length}处):`);
    for (const v of violations) console.error(`  - ${v}`);
    process.exit(1);
  }
  const counts = Object.entries(tagCounts).map(([t, n]) => `${n} <${t}>`).join(' / ');
  console.log(`✅ 原生组件属性守卫: ${files.length} wxml / ${counts} / ${modeSites} mode声明点, 属性名⊆官方域∪豁免域 + 枚举值⊆官方值域 全通过`);
}

main();
