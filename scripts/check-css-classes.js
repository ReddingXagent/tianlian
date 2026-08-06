#!/usr/bin/env node
/**
 * CSS 死类守卫 (F380, 2026-08-06 猴王自驱lint轮)
 *
 * 背景: 小程序 wxss 类选择器零编译期引用检查——页面/组件 wxss 里定义的类
 * 若从未被任何 wxml class 属性引用, 即为死类: 重构遗漏(改名后旧类残留)、
 * 拼写分叉(定义 .card-titl 使用 .card-title, 样式静默不生效且旧类永驻包体)、
 * 值漂移无人感知(改死类样式零效果)。与 F373(变量层死代码)互补: F373 管
 * app.wxss page{} 的 CSS 变量声明↔var() 引用, 本守卫管页面/组件样式层的
 * 类定义↔wxml 使用。app.wxss 全局 utility/主题层是有意预留的公共工具箱
 * (mt-/flex-/text- 系列按需取用), 不入死类审计域。
 *
 * 不变量(单向子集, F240/F373同向):
 *   pages/+components/ wxss 中定义的每个类选择器, 必须至少被
 *   全仓 wxml 的 class 属性引用一次(静态token或{{}}内字面量),
 *   或被 js 侧字符串字面量引用(动态class绑定的值源, 见豁免)。
 *
 * 动态class豁免(F330语义——静态不可判定→豁免而非从严):
 *   class="{{statusClass}}" 形式的纯变量绑定, 类名值在 js 侧赋值
 *   (如 statusClass: 'charging'), 静态无法从 wxml 提取 → 将 js 侧
 *   全部字符串字面量(标识符形态)计入引用集作保守超集豁免。
 *   基线实证: status-used/status-expired/charging/finished/pending/
 *   tag-warning/tag-default 七类均由 js 动态注入, 全部被字面量集覆盖。
 *
 * 提取基线:
 *   定义侧: wxss 剥块注释后字符扫描, 只取选择器文本(花括号外且';'前
 *   重置声明残留), 提取 .identifier token; @media 嵌套选择器同样命中。
 *   使用侧: wxml 剥注释后提取 class="..." 属性值, 静态token(排除含{}
 *   的模板片段) + {{}} 内单引号字面量(三元表达式 'active'/'' 形态)。
 *
 * 活性断言(防豁免吞断言, F306/F317形态):
 *   审计域双根(pages/+components/)存在性(F212, 单根缺失=审计域静默收缩假绿, 接手轮补)
 *   + wxss文件≥1 + 定义类≥1 + wxml文件≥1 + class属性提取点≥1 + js文件≥1
 *   (基线: 14 wxss / 230 全局唯一定义类(逐文件合计267, 18类跨文件重定义) /
 *   14 wxml / 395 class属性点 / 21 js)。
 *
 * 扫描域: 定义=pages/+components/ 递归 wxss(app.wxss豁免);
 *   使用=pages/+components/ 递归 wxml;
 *   豁免=app.js + pages/components/services/utils/config 递归 .js
 *   (排除 node_modules/scripts/coverage/dist/build/miniprogram_npm/__tests__, F292口径)。
 *
 * 用法: node scripts/check-css-classes.js
 * 缺输入/提取器空/任一死类 → exit 1 不放行 (F212)
 */
'use strict';

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const EXCLUDE_DIRS = new Set(['node_modules', 'scripts', 'coverage', 'dist', 'build', 'miniprogram_npm', '__tests__']);
const CLASS_TOKEN_RE = /\.([a-zA-Z_][a-zA-Z0-9_-]*)/g;
const CLASS_ATTR_RE = /class\s*=\s*"([^"]*)"/g;
const INNER_SQ_RE = /'([a-zA-Z_][a-zA-Z0-9_-]*)'/g;
const JS_STR_RE = /['"]([a-zA-Z_][a-zA-Z0-9_-]*)['"]/g;

function collect(dir, ext, out) {
  if (!fs.existsSync(dir)) return;
  for (const name of fs.readdirSync(dir)) {
    if (EXCLUDE_DIRS.has(name)) continue;
    const full = path.join(dir, name);
    const stat = fs.statSync(full);
    if (stat.isDirectory()) collect(full, ext, out);
    else if (name.endsWith(ext)) out.push(full);
  }
}

/** wxss 选择器文本提取: 剥块注释, 字符扫描, '{'前的缓冲为选择器文本 */
function extractDefined(src) {
  const text = src.replace(/\/\*[\s\S]*?\*\//g, ' ');
  const out = new Set();
  let depth = 0;
  let buf = '';
  for (let i = 0; i < text.length; i += 1) {
    const c = text[i];
    if (c === '{') {
      const trimmed = buf.trim();
      if (trimmed && !trimmed.startsWith('@')) {
        let m;
        CLASS_TOKEN_RE.lastIndex = 0;
        while ((m = CLASS_TOKEN_RE.exec(trimmed)) !== null) out.add(m[1]);
      }
      buf = '';
      depth += 1;
    } else if (c === '}') {
      buf = '';
      depth = Math.max(0, depth - 1);
    } else if (c === ';' && depth >= 1) {
      buf = ''; // 声明语句结束, 防声明残留混入后续选择器
    } else {
      buf += c;
    }
  }
  return out;
}

/** wxml class 属性引用提取: 静态token + {{}}内单引号字面量 */
function extractUsed(src, counters) {
  const text = src.replace(/<!--[\s\S]*?-->/g, ' ');
  const out = new Set();
  let m;
  CLASS_ATTR_RE.lastIndex = 0;
  while ((m = CLASS_ATTR_RE.exec(text)) !== null) {
    counters.attrSites += 1;
    const val = m[1];
    for (const tok of val.split(/\s+/)) {
      if (tok && !/[{}]/.test(tok)) out.add(tok);
    }
    let q;
    INNER_SQ_RE.lastIndex = 0;
    while ((q = INNER_SQ_RE.exec(val)) !== null) out.add(q[1]);
  }
  return out;
}

// ---- 收集文件 ----
const wxssFiles = [];
collect(path.join(ROOT, 'pages'), '.wxss', wxssFiles);
collect(path.join(ROOT, 'components'), '.wxss', wxssFiles);

const wxmlFiles = [];
collect(path.join(ROOT, 'pages'), '.wxml', wxmlFiles);
collect(path.join(ROOT, 'components'), '.wxml', wxmlFiles);

const jsFiles = [];
const appJs = path.join(ROOT, 'app.js');
if (fs.existsSync(appJs)) jsFiles.push(appJs);
for (const d of ['pages', 'components', 'services', 'utils', 'config']) collect(path.join(ROOT, d), '.js', jsFiles);

// 审计域根存在性断言 (F212): pages/components 是声明的审计域双根, 单根整体缺失时
// 余根仍供文件 → 空列表断言不触发 → 审计域静默收缩假绿 (F380接手轮M2实证: 230类→21类仍exit 0)
for (const d of ['pages', 'components']) {
  if (!fs.existsSync(path.join(ROOT, d))) {
    console.error(`❌ 缺输入: 审计域根目录 ${d}/ 不存在 (审计域静默收缩即假绿)`);
    process.exit(1);
  }
}

if (wxssFiles.length === 0) {
  console.error('❌ 缺输入: 未找到任何 pages/components wxss 文件');
  process.exit(1);
}
if (wxmlFiles.length === 0) {
  console.error('❌ 缺输入: 未找到任何 pages/components wxml 文件');
  process.exit(1);
}
if (jsFiles.length === 0) {
  console.error('❌ 缺输入: 未找到任何应用侧 js 文件 (动态class豁免域)');
  process.exit(1);
}

// ---- 提取 ----
const defined = new Map(); // 类名 -> [定义文件]
for (const f of wxssFiles) {
  const rel = path.relative(ROOT, f).split(path.sep).join('/');
  for (const c of extractDefined(fs.readFileSync(f, 'utf8'))) {
    if (!defined.has(c)) defined.set(c, []);
    defined.get(c).push(rel);
  }
}

const counters = { attrSites: 0 };
const used = new Set();
for (const f of wxmlFiles) {
  for (const c of extractUsed(fs.readFileSync(f, 'utf8'), counters)) used.add(c);
}

const jsStr = new Set();
for (const f of jsFiles) {
  const src = fs.readFileSync(f, 'utf8');
  let m;
  JS_STR_RE.lastIndex = 0;
  while ((m = JS_STR_RE.exec(src)) !== null) jsStr.add(m[1]);
}

if (defined.size === 0) {
  console.error('❌ 提取器失效信号: 全仓 wxss 零个类选择器定义 (pages/components 必有样式)');
  process.exit(1);
}
if (counters.attrSites === 0) {
  console.error('❌ 提取器失效信号: 全仓 wxml 零个 class 属性提取点');
  process.exit(1);
}

// ---- 断言: 定义 ⊆ 使用 ∪ js字面量豁免 ----
const dead = [];
for (const [cls, files] of defined) {
  if (!used.has(cls) && !jsStr.has(cls)) {
    dead.push(`   ${files.join(', ')} —— .${cls} 定义后零引用 (wxml静态/模板字面量/js动态值源全无)`);
  }
}

if (dead.length > 0) {
  console.error(`❌ CSS 死类: ${dead.length} 个 (定义⊆引用对账失败)`);
  for (const d of dead) console.error(d);
  process.exit(1);
}

console.log(`✅ CSS 死类对账通过: ${defined.size} 个类定义全部被引用 (wxml ${counters.attrSites} 个class属性点 + js字面量豁免域 ${jsFiles.length} 个文件, app.wxss utility层豁免)`);
