import fs from 'fs';
import path from 'path';

/**
 * F247: 导航路由声明↔注册双源一致性守卫(F246方法移植RN侧)
 *
 * 缺口: tsc只挡"注册名∈ParamList"与"带类型navigate字面量∈ParamList",
 * 反方向"ParamList键必须有对应Screen注册"零断言——ParamList幽灵键
 * navigate('Ghost')编译通过, 运行时"No route named 'Ghost'";
 * 嵌套导航 navigate('Main', { screen: 'X' }) 的X须∈MainTabParamList。
 *
 * 不变量(单向子集, F240/F243/F246同向):
 * - 注册名集 ⊆ ParamList键集
 * - ParamList键集 ⊆ 注册名集(幽灵键拦截, tsc盲区)
 * - navigate/replace/push字面量 ⊆ ParamList键集
 * - 嵌套 navigate('Main', {screen:'X'}) 的X ⊆ MainTabParamList键集
 * - 配置驱动导航 screen:'X' 字面量(ProfileScreen菜单形态) ⊆ ParamList键集
 * 接入: jest全量跑自动入门禁(本仓无CI/Makefile, 走jest测试接入)。
 */

const TYPES_PATH = path.join(__dirname, '../types/index.ts');
const NAV_PATH = path.join(__dirname, '../navigation/AppNavigator.tsx');
const SRC_DIR = path.join(__dirname, '..');

// 花括号平衡提取type体(值可含嵌套对象如 { stationId: number })
function extractParamListKeys(source: string, listName: string): string[] {
  const anchor = `export type ${listName} = {`;
  const start = source.indexOf(anchor);
  if (start === -1) {
    throw new Error(`ParamList 声明缺失: ${listName}`);
  }
  let depth = 0;
  let body = '';
  for (let i = start + anchor.length - 1; i < source.length; i += 1) {
    const ch = source[i];
    if (ch === '{') depth += 1;
    else if (ch === '}') {
      depth -= 1;
      if (depth === 0) break;
    } else if (depth === 1) {
      body += ch;
    }
  }
  const keys: string[] = [];
  for (const line of body.split('\n')) {
    const km = /^\s*([A-Za-z_][A-Za-z0-9_]*)\s*:/.exec(line);
    if (km) keys.push(km[1]);
  }
  if (keys.length === 0) {
    throw new Error(`ParamList 键提取为空: ${listName}`);
  }
  return keys;
}

function extractRegisteredNames(navSource: string): string[] {
  const names: string[] = [];
  const re = /\bname="([A-Za-z][A-Za-z0-9_]*)"/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(navSource)) !== null) {
    names.push(m[1]);
  }
  if (names.length === 0) {
    throw new Error('AppNavigator 未提取到任何 Screen 注册名');
  }
  return names;
}

function walkSourceFiles(dir: string, out: string[] = []): string[] {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === '__tests__' || entry.name === 'node_modules') continue;
      walkSourceFiles(full, out);
    } else if (/\.(ts|tsx)$/.test(entry.name)) {
      out.push(full);
    }
  }
  return out;
}

function collectSourceText(): string {
  return walkSourceFiles(SRC_DIR)
    .map((f) => fs.readFileSync(f, 'utf8'))
    .join('\n');
}

describe('导航路由声明↔注册双源一致性守卫', () => {
  const typesSource = fs.readFileSync(TYPES_PATH, 'utf8');
  const navSource = fs.readFileSync(NAV_PATH, 'utf8');
  const allSource = collectSourceText();

  const rootKeys = extractParamListKeys(typesSource, 'RootStackParamList');
  const authKeys = extractParamListKeys(typesSource, 'AuthStackParamList');
  const tabKeys = extractParamListKeys(typesSource, 'MainTabParamList');
  const allParamKeys = new Set([...rootKeys, ...authKeys, ...tabKeys]);
  const registered = extractRegisteredNames(navSource);
  const registeredSet = new Set(registered);

  it('注册名集 ⊆ ParamList键集(注册的每个Screen必有路由类型声明)', () => {
    const orphan = registered.filter((n) => !allParamKeys.has(n));
    expect(orphan).toEqual([]);
  });

  it('ParamList键集 ⊆ 注册名集(幽灵键拦截: 声明的路由必须真实注册)', () => {
    const ghosts = [...allParamKeys].filter((k) => !registeredSet.has(k));
    expect(ghosts).toEqual([]);
  });

  it('navigate/replace/push 字面量 ⊆ ParamList键集', () => {
    const hits: string[] = [];
    const re = /\b(?:navigate|replace|push|reset)\(\s*'([A-Za-z][A-Za-z0-9_]*)'/g;
    let m: RegExpExecArray | null;
    while ((m = re.exec(allSource)) !== null) {
      hits.push(m[1]);
    }
    expect(hits.length).toBeGreaterThan(0);
    const bad = hits.filter((h) => !allParamKeys.has(h));
    expect(bad).toEqual([]);
  });

  it('嵌套导航 navigate("Main", {screen:X}) 的X ⊆ MainTabParamList键集', () => {
    const hits: string[] = [];
    const re = /navigate\(\s*'Main'\s*,\s*\{\s*screen:\s*'([A-Za-z][A-Za-z0-9_]*)'/g;
    let m: RegExpExecArray | null;
    while ((m = re.exec(allSource)) !== null) {
      hits.push(m[1]);
    }
    expect(hits.length).toBeGreaterThan(0);
    const tabSet = new Set(tabKeys);
    const bad = hits.filter((h) => !tabSet.has(h));
    expect(bad).toEqual([]);
  });

  it('配置驱动导航 screen 字面量 ⊆ ParamList键集', () => {
    const hits: string[] = [];
    const re = /\bscreen:\s*'([A-Za-z][A-Za-z0-9_]*)'/g;
    let m: RegExpExecArray | null;
    while ((m = re.exec(allSource)) !== null) {
      hits.push(m[1]);
    }
    expect(hits.length).toBeGreaterThan(0);
    const bad = hits.filter((h) => !allParamKeys.has(h));
    expect(bad).toEqual([]);
  });

  it('三张ParamList键集均非空且无重复键', () => {
    for (const keys of [rootKeys, authKeys, tabKeys]) {
      expect(new Set(keys).size).toBe(keys.length);
    }
  });
});
