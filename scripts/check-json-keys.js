#!/usr/bin/env node
/**
 * JSON 配置键白名单对账守卫 (F311)
 *
 * 微信小程序对 app.json / 页面 json / 组件 json 中的未知键一律**静默忽略**:
 * 拼写错误(如 navigationBarTitleTxt)编译零报错、上传零报错, 但运行时该配置
 * 永不生效——与 F295 同族的"静默 no-op 最恶漂移"。mp 无 tsc/schema 校验,
 * 此前零静态断言。
 *
 * 不变量:
 *   A. app.json 顶层键 ⊆ APP_KEYS; window/tabBar/networkTimeout 嵌套键各守白名单;
 *      permission 键必须 scope.* 前缀; preloadRule 键必须是已注册页路径。
 *   B. 页面 json 顶层键 ⊆ PAGE_KEYS。
 *   C. 组件 json (component:true) 顶层键 ⊆ COMPONENT_KEYS。
 *   D. 枚举值字段值域校验 (navigationBarTextStyle ∈ white|black 等):
 *      非法值同样静默回退默认。
 *   E. tabBar.list[].pagePath ⊆ app.json pages 注册集 (跨源对账)。
 *   F. 未知 json 配置文件(非豁免清单) = 漂移信号, 不放行。
 *
 * 活性断言 (F306/F308/F309 形态): app.json 存在且 pages≥1, 扫描配置文件数≥2,
 * 观测键集合非空——防豁免清单吞断言。
 *
 * 缺输入 (app.json 缺失/不可解析/pages 为空) → exit 1 (F212, 不静默放行)。
 *
 * 豁免清单 (自有 schema, 非 mp 页面配置键域): package.json/package-lock.json
 * (npm), project.config.json/project.private.config.json (开发者工具),
 * sitemap.json (微信索引规则 rules[]), theme.json (darkmode主题变量文件,
 * app.json themeLocation引用, 自有schema: light/dark两主题×导航/背景/tab键域),
 * node_modules/miniprogram_npm/coverage/__tests__ (依赖与测试脚手架, F292 口径),
 * .ua (gitignored Understand-Anything skill artifacts, 非工程内容).
 */
'use strict';

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');

// ---- 白名单 (微信官方配置键域) ----

const APP_KEYS = new Set([
  'pages', 'window', 'tabBar', 'permission', 'requiredPrivateInfos',
  'sitemapLocation', 'style', 'lazyCodeLoading', 'networkTimeout',
  'preloadRule', 'subpackages', 'subPackages', 'workers', 'debug',
  'entryPagePath', 'navigateToMiniProgramAppIdList', 'plugins',
  'usingComponents', 'resolveAlias', 'functionalPages', 'resizable',
  'useExtendedLib', 'requiredBackgroundModes', 'darkmode', 'themeLocation',
  'singlePage', 'renderer', 'rendererOptions', 'componentFramework',
]);

const WINDOW_KEYS = new Set([
  'navigationBarBackgroundColor', 'navigationBarTextStyle',
  'navigationBarTitleText', 'navigationStyle', 'homeButton',
  'backgroundColor', 'backgroundTextStyle', 'backgroundColorTop',
  'backgroundColorBottom', 'enablePullDownRefresh', 'onReachBottomDistance',
  'pageOrientation',
]);

const TABBAR_KEYS = new Set([
  'color', 'selectedColor', 'backgroundColor', 'borderStyle', 'position',
  'list', 'custom',
]);

const TABBAR_ITEM_KEYS = new Set([
  'pagePath', 'text', 'iconPath', 'selectedIconPath',
]);

const NETWORK_TIMEOUT_KEYS = new Set([
  'request', 'connectSocket', 'uploadFile', 'downloadFile',
]);

const PRELOAD_RULE_VALUE_KEYS = new Set(['network', 'packages']);

const PAGE_KEYS = new Set([
  'navigationBarBackgroundColor', 'navigationBarTextStyle',
  'navigationBarTitleText', 'navigationStyle', 'homeButton',
  'backgroundColor', 'backgroundTextStyle', 'backgroundColorTop',
  'backgroundColorBottom', 'enablePullDownRefresh', 'onReachBottomDistance',
  'pageOrientation', 'disableScroll', 'usingComponents',
  'initialRenderingCache', 'styleIsolation', 'componentPlaceholder',
  'restartStrategy', 'renderer', 'rendererOptions', 'enablePassiveEvent',
]);

const COMPONENT_KEYS = new Set([
  'component', 'usingComponents', 'styleIsolation', 'options',
  'componentGenerics',
]);

// 枚举值域 (非法值静默回退默认 → 值级对账)
const ENUMS = {
  'window.navigationBarTextStyle': ['white', 'black'],
  'window.backgroundTextStyle': ['dark', 'light'],
  'window.navigationStyle': ['default', 'custom'],
  'tabBar.position': ['bottom', 'top'],
  'tabBar.borderStyle': ['black', 'white'],
  'style': ['v2', 'v3'],
  'lazyCodeLoading': ['requiredComponents'],
};

// 非 mp 页面配置键域 json, 自有 schema (见文件头豁免清单)
const EXEMPT_FILES = new Set([
  'package.json', 'package-lock.json', 'project.config.json',
  'project.private.config.json', 'sitemap.json', 'theme.json',
]);
const EXEMPT_DIRS = new Set([
  'node_modules', 'miniprogram_npm', 'coverage', '__tests__', '.git', '.ua',
]);

function walkJsonFiles(dir, rel = '') {
  const out = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const relPath = rel ? `${rel}/${entry.name}` : entry.name;
    if (entry.isDirectory()) {
      if (!EXEMPT_DIRS.has(entry.name)) {
        out.push(...walkJsonFiles(path.join(dir, entry.name), relPath));
      }
    } else if (entry.name.endsWith('.json')) {
      out.push(relPath);
    }
  }
  return out;
}

function fail(msgs) {
  for (const m of msgs) console.error(`  ❌ ${m}`);
  process.exit(1);
}

// ---- 主流程 ----

const errors = [];
const appJsonPath = path.join(ROOT, 'app.json');
if (!fs.existsSync(appJsonPath)) {
  fail(['缺输入: app.json 不存在 (F212: 不放行)']);
}

let appConfig;
try {
  appConfig = JSON.parse(fs.readFileSync(appJsonPath, 'utf8'));
} catch (e) {
  fail([`缺输入: app.json 解析失败: ${e.message} (F212: 不放行)`]);
}

if (!Array.isArray(appConfig.pages) || appConfig.pages.length === 0) {
  fail(['缺输入: app.json pages 为空或缺失 (F212: 不放行)']);
}
const registeredPages = new Set(appConfig.pages);

// darkmode 主题变量引用解析 (微信官方能力: "darkmode": true + "themeLocation" 时,
// 配置值可用 "@key" 引用 theme.json light/dark 主题变量; 拼错键名=静默回退默认, F311同族)
let themeVars = null;
if (appConfig.darkmode === true && typeof appConfig.themeLocation === 'string') {
  const themePath = path.join(ROOT, appConfig.themeLocation);
  let parsed;
  if (!fs.existsSync(themePath)) {
    errors.push(`themeLocation "${appConfig.themeLocation}" 指向的文件不存在 (darkmode引用将静默回退默认)`);
  } else {
    try {
      parsed = JSON.parse(fs.readFileSync(themePath, 'utf8'));
    } catch (e) {
      errors.push(`${appConfig.themeLocation} 解析失败: ${e.message}`);
    }
  }
  if (parsed && typeof parsed === 'object' &&
      parsed.light && typeof parsed.light === 'object' &&
      parsed.dark && typeof parsed.dark === 'object') {
    themeVars = parsed;
  } else if (parsed !== undefined) {
    errors.push(`${appConfig.themeLocation} 结构异常: 需要 light/dark 两主题对象`);
  }
}

// 枚举字段值合法判定: 直接值 ∈ 值域, 或 "@变量" 引用且 theme.json light/dark 同名存在且均在值域
function enumValueOk(enumPath, value, legal) {
  if (legal.includes(value)) return true;
  if (typeof value === 'string' && value.startsWith('@') && themeVars) {
    const key = value.slice(1);
    const lv = themeVars.light[key];
    const dv = themeVars.dark[key];
    if (lv === undefined || dv === undefined) {
      errors.push(`app.json ${enumPath}="${value}" 主题变量在 ${appConfig.themeLocation} light/dark 缺失`);
      return false;
    }
    if (!legal.includes(lv) || !legal.includes(dv)) {
      errors.push(`app.json ${enumPath}="${value}" 主题变量值超值域 (light:"${lv}", dark:"${dv}", 合法: ${legal.join('|')})`);
      return false;
    }
    return true;
  }
  return false;
}

// 全部 @引用键与 theme.json 对账 (拼写错误=静默回退默认)
if (themeVars) {
  for (const [scope, obj] of [['window', appConfig.window], ['tabBar', appConfig.tabBar]]) {
    for (const [k, v] of Object.entries(obj || {})) {
      const key = typeof v === 'string' && v.startsWith('@') ? v.slice(1) : null;
      if (key && (themeVars.light[key] === undefined || themeVars.dark[key] === undefined)) {
        errors.push(`app.json ${scope}.${k} 引用主题变量 "${key}" 在 ${appConfig.themeLocation} light/dark 缺失 (静默回退默认)`);
      }
    }
  }
}

// A. app.json 顶层键
for (const key of Object.keys(appConfig)) {
  if (!APP_KEYS.has(key)) {
    errors.push(`app.json 未知顶层键 "${key}" (静默忽略=配置不生效)`);
  }
}

// A. window 嵌套键 + D. 枚举
if (appConfig.window !== undefined) {
  if (typeof appConfig.window !== 'object' || Array.isArray(appConfig.window)) {
    errors.push('app.json window 必须是对象');
  } else {
    for (const key of Object.keys(appConfig.window)) {
      if (!WINDOW_KEYS.has(key)) {
        errors.push(`app.json window 未知键 "${key}" (静默忽略)`);
      }
      const enumPath = `window.${key}`;
      if (ENUMS[enumPath] && !enumValueOk(enumPath, appConfig.window[key], ENUMS[enumPath])) {
        errors.push(`app.json window.${key}="${appConfig.window[key]}" 非法值 (合法: ${ENUMS[enumPath].join('|')} 或 @主题变量引用, 非法值静默回退默认)`);
      }
    }
  }
}

// A/D. tabBar + E. list[].pagePath 跨源对账
if (appConfig.tabBar !== undefined) {
  if (typeof appConfig.tabBar !== 'object' || Array.isArray(appConfig.tabBar)) {
    errors.push('app.json tabBar 必须是对象');
  } else {
    for (const key of Object.keys(appConfig.tabBar)) {
      if (!TABBAR_KEYS.has(key)) {
        errors.push(`app.json tabBar 未知键 "${key}" (静默忽略)`);
      }
      if (ENUMS[`tabBar.${key}`] && !enumValueOk(`tabBar.${key}`, appConfig.tabBar[key], ENUMS[`tabBar.${key}`])) {
        errors.push(`app.json tabBar.${key}="${appConfig.tabBar[key]}" 非法值 (合法: ${ENUMS[`tabBar.${key}`].join('|')} 或 @主题变量引用)`);
      }
    }
    const list = appConfig.tabBar.list;
    if (!Array.isArray(list) || list.length === 0) {
      errors.push('app.json tabBar.list 缺失或为空 (有 tabBar 无 list = 底栏空白)');
    } else {
      list.forEach((item, i) => {
        for (const key of Object.keys(item)) {
          if (!TABBAR_ITEM_KEYS.has(key)) {
            errors.push(`app.json tabBar.list[${i}] 未知键 "${key}" (静默忽略)`);
          }
        }
        if (!registeredPages.has(item.pagePath)) {
          errors.push(`app.json tabBar.list[${i}].pagePath "${item.pagePath}" 未在 pages 注册 (跨源漂移)`);
        }
      });
    }
  }
}

// A. networkTimeout 嵌套键
if (appConfig.networkTimeout !== undefined) {
  for (const key of Object.keys(appConfig.networkTimeout)) {
    if (!NETWORK_TIMEOUT_KEYS.has(key)) {
      errors.push(`app.json networkTimeout 未知键 "${key}" (静默忽略)`);
    } else if (typeof appConfig.networkTimeout[key] !== 'number') {
      errors.push(`app.json networkTimeout.${key} 必须是数字(ms)`);
    }
  }
}

// A. permission 键必须 scope.* 前缀
if (appConfig.permission !== undefined) {
  for (const key of Object.keys(appConfig.permission)) {
    if (!key.startsWith('scope.')) {
      errors.push(`app.json permission 键 "${key}" 必须是 scope.* 前缀 (静默忽略)`);
    }
  }
}

// A. preloadRule 键必须是已注册页 + 值键白名单
if (appConfig.preloadRule !== undefined) {
  for (const [pagePath, rule] of Object.entries(appConfig.preloadRule)) {
    if (!registeredPages.has(pagePath)) {
      errors.push(`app.json preloadRule 键 "${pagePath}" 未在 pages 注册 (静默忽略, 跨源漂移)`);
    }
    for (const key of Object.keys(rule)) {
      if (!PRELOAD_RULE_VALUE_KEYS.has(key)) {
        errors.push(`app.json preloadRule["${pagePath}"] 未知键 "${key}" (静默忽略)`);
      }
    }
    if (rule.network !== undefined && !['all', 'wifi'].includes(rule.network)) {
      errors.push(`app.json preloadRule["${pagePath}"].network="${rule.network}" 非法值 (合法: all|wifi)`);
    }
  }
}

// D. 顶层枚举 (style / lazyCodeLoading)
for (const key of ['style', 'lazyCodeLoading']) {
  if (appConfig[key] !== undefined && ENUMS[key] && !ENUMS[key].includes(appConfig[key])) {
    errors.push(`app.json ${key}="${appConfig[key]}" 非法值 (合法: ${ENUMS[key].join('|')})`);
  }
}

// B/C/F. 全仓 json 分类校验
const allJson = walkJsonFiles(ROOT);
const scanned = [];
const observedKeys = new Set();

for (const rel of allJson) {
  const base = path.basename(rel);
  if (EXEMPT_FILES.has(base)) continue;
  if (rel === 'app.json') { scanned.push(rel); continue; }

  let parsed;
  try {
    parsed = JSON.parse(fs.readFileSync(path.join(ROOT, rel), 'utf8'));
  } catch (e) {
    errors.push(`${rel} JSON 解析失败: ${e.message}`);
    continue;
  }
  if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
    errors.push(`${rel} 顶层必须是对象 (mp 配置 json)`);
    continue;
  }

  const isComponent = parsed.component === true;
  const isPage = registeredPages.has(rel.replace(/\.json$/, ''));
  let schema;
  let schemaName;
  if (isComponent) {
    schema = COMPONENT_KEYS; schemaName = '组件';
  } else if (isPage) {
    schema = PAGE_KEYS; schemaName = '页面';
  } else {
    errors.push(`${rel} 未知 mp 配置 json: 非注册页/非组件/非豁免清单 (F311-F: 不放行; 若为合法新类别, 更新豁免清单)`);
    continue;
  }

  scanned.push(rel);
  for (const key of Object.keys(parsed)) {
    observedKeys.add(key);
    if (!schema.has(key)) {
      errors.push(`${rel} ${schemaName}配置未知键 "${key}" (微信静默忽略=配置不生效)`);
    }
  }
}

// 活性断言 (F306/F308/F309 形态): 防豁免清单吞断言
if (scanned.length < 2) {
  errors.push(`活性断言失败: 扫描 mp 配置 json 仅 ${scanned.length} 个 (预期≥2: app.json+页面/组件 json), 提取器可能失效`);
}
if (observedKeys.size === 0) {
  errors.push('活性断言失败: 观测键集合为空, 页面/组件 json 未实际参与校验');
}

if (errors.length > 0) {
  fail(errors);
}

console.log(`✅ JSON配置键白名单对账守卫 (F311): ${scanned.length} 个配置文件 (app.json + ${scanned.length - 1} 页面/组件 json), ${observedKeys.size} 个观测键全部命中白名单, 枚举值域 ${Object.keys(ENUMS).length} 项通过, tabBar/preloadRule↔pages 跨源对账通过`);
process.exit(0);
