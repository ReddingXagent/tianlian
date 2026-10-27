import fs from 'fs';
import path from 'path';

/**
 * F312: FlatList/SectionList×extraData成对守卫(移动端维度, 列表族第二枚)
 *
 * 缺口: RN的FlatList/SectionList对data/extraData做浅比较决定item重渲染。
 * renderItem闭包捕获了组件useState状态(如充值中/筛选态/选中集)而未传
 * extraData时, 状态翻转但data引用不变→列表项永不重渲染, 按钮disabled态/
 * 文案/选中高亮全部停在旧值——F295族静默no-op: 无警告无报错, 用户看到
 * "点了没反应"。tsc盲区: extraData是optional prop, 不传零类型信号;
 * renderItem闭包捕获是词法作用域天然行为, 编译器无从感知。
 *
 * 不变量:
 * - 全仓src/**\/*.tsx(排除__tests__)中每个<FlatList或<SectionList开标签:
 *   若renderItem闭包(命名函数解析源或内联箭头)引用同文件useState声明的
 *   状态变量, 该列表必须携带extraData=属性。
 * - 只查状态读取不查setter(setX引用不构成陈旧渲染——setter身份恒定)。
 * - 零列表态合法显式输出(F302形态): 全仓无列表=0/0断言集, 守卫空跑放行。
 * - 缺输入(零tsx文件/renderItem命名引用解析不到定义)抛错FAIL(F212不静默)。
 *
 * 提取健壮性: 花括号深度扫描开标签终点(F306同源); renderItem={IDENT}精确
 * 标识符提取不误吞内联箭头; useState名按词边界+成员访问排除双重过滤
 * (page不误命中pageCount; item.brand不是闭包捕获——F312首跑自撞VehicleScreen
 * 假阳性后固化); 命名函数体支持=>(...)括号体/=>{...}块体/=>expr简洁体三形态。
 *
 * 摸底现状: 全仓4处FlatList(OrderList/Vehicle/Wallet/Coupon)renderItem均
 * 纯item渲染(模块常量+useCallback handler), 零useState捕获——零命中=
 * 守卫先行非缺陷(F258/F284/F293/F305/F306型), 门禁防未来列表挂状态欠账。
 *
 * 接入: jest全量跑自动入门禁(本仓无CI/Makefile, 走jest测试接入, F278族同惯例)。
 */

const SRC_DIR = path.join(__dirname, '..');

/** 从startIdx(指向'<')扫描开标签终点: 花括号深度扫描, 嵌套JSX表达式内的>不误断 */
export function openTagEnd(source: string, startIdx: number): number {
  let depth = 0;
  for (let i = startIdx; i < source.length; i++) {
    const ch = source[i];
    if (ch === '{') depth++;
    else if (ch === '}') depth--;
    else if (ch === '>' && depth === 0) return i + 1;
  }
  throw new Error('开标签未闭合: 找不到终点>');
}

/** 提取文件内全部useState声明的状态变量名(不含setter) */
export function extractUseStateNames(source: string): string[] {
  const names: string[] = [];
  const re = /\bconst\s+\[\s*([A-Za-z_$][\w$]*)\s*,\s*[A-Za-z_$][\w$]*\s*\]\s*=\s*useState/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(source)) !== null) names.push(m[1]);
  return names;
}

function escapeRe(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/** 从箭头函数起点(指向const NAME)扫描函数体全文: 支持=>(...)括号体/=>{...}块体/=>expr简洁体三形态 */
export function arrowBody(source: string, defIdx: number): string {
  const arrow = source.indexOf('=>', defIdx);
  if (arrow === -1) throw new Error('函数定义缺箭头: 无法定位函数体');
  let i = arrow + 2;
  while (i < source.length && /\s/.test(source[i])) i++;
  const open = source[i];
  if (open === '(' || open === '{') {
    const close = open === '(' ? ')' : '}';
    let depth = 0;
    for (let j = i; j < source.length; j++) {
      if (source[j] === open) depth++;
      else if (source[j] === close) {
        depth--;
        if (depth === 0) return source.slice(i, j + 1);
      }
    }
    throw new Error('函数体未闭合: 括号深度扫描到文件尾');
  }
  // 简洁体=>expr: 跟踪四类括号深度, 深度0遇;截断(无分号则到行尾)
  let depth = 0;
  for (let j = i; j < source.length; j++) {
    const ch = source[j];
    if ('([{'.includes(ch)) depth++;
    else if (')]}'.includes(ch)) depth--;
    else if (ch === ';' && depth === 0) return source.slice(i, j);
    else if ((ch === '\n') && depth === 0) return source.slice(i, j);
  }
  return source.slice(i);
}

/** 状态名在函数体内是否被"自由引用"(词边界命中且前缀非.成员访问——item.brand不是闭包捕获) */
export function hasFreeReference(body: string, name: string): boolean {
  const re = new RegExp(`\\b${escapeRe(name)}\\b`, 'g');
  let m: RegExpExecArray | null;
  while ((m = re.exec(body)) !== null) {
    if (m.index > 0 && body[m.index - 1] === '.') continue; // item.x / item?.x均排除
    return true;
  }
  return false;
}

/** 解析renderItem闭包体: 命名引用→全文件找const NAME定义; 内联箭头→直接扫 */
export function resolveRenderItemBody(source: string, tag: string): string {
  const named = /renderItem\s*=\s*\{\s*([A-Za-z_$][\w$]*)\s*\}/.exec(tag);
  if (named) {
    const defRe = new RegExp(`\\bconst\\s+${escapeRe(named[1])}\\s*=`);
    const def = defRe.exec(source);
    if (!def) throw new Error(`renderItem命名引用解析不到定义: ${named[1]}`);
    return arrowBody(source, def.index);
  }
  const inline = /renderItem\s*=\s*\{/.exec(tag);
  if (!inline) throw new Error('列表缺renderItem属性');
  const exprStart = tag.indexOf('{', inline.index + 'renderItem'.length);
  let depth = 0;
  for (let j = exprStart; j < tag.length; j++) {
    if (tag[j] === '{') depth++;
    else if (tag[j] === '}') {
      depth--;
      if (depth === 0) return tag.slice(exprStart, j + 1);
    }
  }
  throw new Error('renderItem表达式未闭合');
}

export interface ExtraDataFinding {
  component: 'FlatList' | 'SectionList';
  relPath: string;
  /** renderItem闭包引用的useState状态名 */
  capturedStates: string[];
  hasExtraData: boolean;
}

/** 递归收集目录下全部.tsx文件(排除__tests__与node_modules) */
export function collectTsxFiles(dir: string, out: string[] = []): string[] {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === '__tests__' || entry.name === 'node_modules') continue;
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) collectTsxFiles(full, out);
    else if (entry.isFile() && entry.name.endsWith('.tsx')) out.push(full);
  }
  return out;
}

/** 单文件对账: 每个列表开标签解析renderItem闭包捕获×extraData成对 */
export function auditFile(relPath: string, source: string): ExtraDataFinding[] {
  const stateNames = extractUseStateNames(source);
  const findings: ExtraDataFinding[] = [];
  const re = /<(FlatList|SectionList)(?=[\s>/])/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(source)) !== null) {
    const tag = source.slice(m.index, openTagEnd(source, m.index));
    const body = resolveRenderItemBody(source, tag);
    const capturedStates = stateNames.filter((name) => hasFreeReference(body, name));
    findings.push({
      component: m[1] as ExtraDataFinding['component'],
      relPath,
      capturedStates,
      hasExtraData: /\bextraData\s*=/.test(tag),
    });
  }
  return findings;
}

// ---------- 合成控制 ----------

describe('F312 提取健壮性(合成样例)', () => {
  test('捕获useState且缺extraData→命中', () => {
    const src =
      'const [selected, setSelected] = useState<string[]>([]);\n' +
      'const renderRow = ({ item }: { item: Row }) => (\n' +
      '  <View style={selected.includes(item.id) ? styles.on : styles.off} />\n' +
      ');\n' +
      'const el = <FlatList data={rows} keyExtractor={(i) => i.id} renderItem={renderRow} />;';
    const findings = auditFile('synthetic/Capture.tsx', src);
    expect(findings).toHaveLength(1);
    expect(findings[0].capturedStates).toEqual(['selected']);
    expect(findings[0].hasExtraData).toBe(false);
  });

  test('捕获useState且带extraData→放行', () => {
    const src =
      'const [selected, setSelected] = useState<string[]>([]);\n' +
      'const renderRow = ({ item }: { item: Row }) => (\n' +
      '  <View style={selected.includes(item.id) ? styles.on : styles.off} />\n' +
      ');\n' +
      'const el = (\n' +
      '  <FlatList data={rows} extraData={selected} keyExtractor={(i) => i.id} renderItem={renderRow} />\n' +
      ');';
    const findings = auditFile('synthetic/WithExtra.tsx', src);
    expect(findings).toHaveLength(1);
    expect(findings[0].capturedStates).toEqual(['selected']);
    expect(findings[0].hasExtraData).toBe(true);
  });

  test('无捕获缺extraData→放行(纯item渲染合法)', () => {
    const src =
      'const [loading, setLoading] = useState(true);\n' +
      'const renderRow = ({ item }: { item: Row }) => <Text>{item.name}</Text>;\n' +
      'const el = <FlatList data={rows} keyExtractor={(i) => i.id} renderItem={renderRow} />;';
    const findings = auditFile('synthetic/Pure.tsx', src);
    expect(findings).toHaveLength(1);
    expect(findings[0].capturedStates).toEqual([]);
  });

  test('内联箭头renderItem捕获状态缺extraData→命中', () => {
    const src =
      'const [activeFilter, setActiveFilter] = useState("");\n' +
      'const el = (\n' +
      '  <SectionList\n' +
      '    sections={secs}\n' +
      '    renderItem={({ item }) => <Text style={activeFilter ? styles.hl : null}>{item.t}</Text>}\n' +
      '  />\n' +
      ');';
    const findings = auditFile('synthetic/Inline.tsx', src);
    expect(findings).toHaveLength(1);
    expect(findings[0].component).toBe('SectionList');
    expect(findings[0].capturedStates).toEqual(['activeFilter']);
    expect(findings[0].hasExtraData).toBe(false);
  });

  test('块体renderItem(=>{})捕获可解析', () => {
    const src =
      'const [expanded, setExpanded] = useState(false);\n' +
      'const renderRow = ({ item }: { item: Row }) => {\n' +
      '  return <Text>{expanded ? item.full : item.short}</Text>;\n' +
      '};\n' +
      'const el = <FlatList data={rows} renderItem={renderRow} />;';
    const findings = auditFile('synthetic/Block.tsx', src);
    expect(findings[0].capturedStates).toEqual(['expanded']);
  });

  test('词边界: page不误命中pageCount', () => {
    const src =
      'const [page, setPage] = useState(1);\n' +
      'const renderRow = ({ item }: { item: Row }) => <Text>{item.pageCount}</Text>;\n' +
      'const el = <FlatList data={rows} renderItem={renderRow} />;';
    const findings = auditFile('synthetic/Boundary.tsx', src);
    expect(findings[0].capturedStates).toEqual([]);
  });

  test('成员访问不构成捕获(item.brand≠闭包brand, F312首跑自撞提取缺陷)', () => {
    const src =
      'const [brand, setBrand] = useState("");\n' +
      'const [color, setColor] = useState("");\n' +
      'const renderRow = ({ item }: { item: Row }) => (\n' +
      '  <Text>{item.brand} {item?.color}</Text>\n' +
      ');\n' +
      'const el = <FlatList data={rows} renderItem={renderRow} />;';
    const findings = auditFile('synthetic/Member.tsx', src);
    expect(findings[0].capturedStates).toEqual([]);
  });

  test('setter引用不构成捕获(setX身份恒定)', () => {
    const src =
      'const [page, setPage] = useState(1);\n' +
      'const renderRow = ({ item }: { item: Row }) => (\n' +
      '  <Text onPress={() => setPage(item.p)}>{item.t}</Text>\n' +
      ');\n' +
      'const el = <FlatList data={rows} renderItem={renderRow} />;';
    const findings = auditFile('synthetic/Setter.tsx', src);
    expect(findings[0].capturedStates).toEqual([]);
  });

  test('前缀碰撞不误提取(<FlatListFoo)', () => {
    const src = '<FlatListFoo data={d} renderItem={r} />';
    expect(auditFile('synthetic/Prefix.tsx', src)).toHaveLength(0);
  });

  test('renderItem命名引用解析不到定义抛错(缺输入FAIL不静默)', () => {
    const src = '<FlatList data={d} renderItem={ghostRender} />';
    expect(() => auditFile('synthetic/Ghost.tsx', src)).toThrow('解析不到定义');
  });
});

// ---------- 全仓对账 ----------

describe('F312 全仓对账: renderItem状态捕获×extraData成对', () => {
  const tsxFiles = collectTsxFiles(SRC_DIR);
  if (tsxFiles.length === 0) {
    throw new Error('src下零tsx文件: 缺输入FAIL不静默(F212)');
  }
  const findings = tsxFiles.flatMap((file) =>
    auditFile(path.relative(SRC_DIR, file), fs.readFileSync(file, 'utf-8')),
  );

  test('提取活性: 对账清单含已知4处列表(防豁免吞掉全部断言)', () => {
    expect(findings.length).toBeGreaterThanOrEqual(4);
    const files = findings.map((f) => f.relPath);
    for (const known of [
      'screens/OrderListScreen.tsx',
      'screens/VehicleScreen.tsx',
      'screens/WalletScreen.tsx',
      'screens/CouponScreen.tsx',
    ]) {
      expect(files).toContain(known);
    }
  });

  if (findings.length === 0) {
    test('零列表态合法显式输出(F302形态): 全仓0列表, 守卫空跑放行', () => {
      expect(findings).toHaveLength(0);
    });
  }

  const captures = findings.filter((f) => f.capturedStates.length > 0);
  if (captures.length > 0) {
    test.each(captures.map((f) => [`${f.relPath} <${f.component}> 捕获${f.capturedStates.join(',')}`, f] as const))(
      '%s 必须携带extraData(状态翻转item不重渲染=F295族静默陈旧)',
      (_label, finding) => {
        expect(finding.hasExtraData).toBe(true);
      },
    );
  }

  if (captures.length === 0) {
    test('全仓列表renderItem均纯item渲染: 零捕获=守卫先行非缺陷(F258/F306型)', () => {
      expect(captures).toHaveLength(0);
      expect(findings.length).toBeGreaterThanOrEqual(4);
    });
  }
});
