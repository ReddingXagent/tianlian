import fs from 'fs';
import path from 'path';

/**
 * F306: FlatList/SectionList×keyExtractor成对守卫(移动端维度, 键盘族/安全区族外缺陷形态)
 *
 * 缺口: RN列表无keyExtractor时RN退化为index键并触发黄色警告——列表项
 * 增删/重排时diff按位置而非身份对齐, 复用错位导致状态串位(选中态/输入
 * 内容漂移到相邻行), 且VirtualizedList无法精准diff只能整段重建(滚动位置
 * 抖动+性能退化)。tsc盲区: keyExtractor是optional prop, 不传零类型信号,
 * 静态只有运行时console.warn, 真机重排场景才暴露。
 *
 * 不变量:
 * - 全仓src/**\/*.tsx(排除__tests__)中每个<FlatList或<SectionList开标签
 *   必须携带keyExtractor=属性。
 * - 零列表态合法显式输出(F302形态): 全仓无列表=0/0断言集, 守卫空跑放行。
 * - 缺输入(零tsx文件)抛错FAIL(F212不静默放行)。
 *
 * 提取健壮性: 花括号深度扫描——keyExtractor/data/renderItem等JSX表达式内
 * 嵌套{}里的>不误断开标签终点; <FlatListFoo前缀碰撞不误提取; 提取器计数
 * 只数开标签不数字串(F278族铁律)。
 *
 * 摸底现状: 全仓4处FlatList(OrderList/Vehicle/Wallet/Coupon)均已携带
 * keyExtractor={(item) => String(item.id)}——零命中=守卫先行非缺陷
 * (F258/F284/F293/F305型), 门禁防未来新列表欠账。
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

export interface ListOpenTag {
  component: 'FlatList' | 'SectionList';
  /** 开标签全文(含<与终点>) */
  tag: string;
  hasKeyExtractor: boolean;
}

/** 提取source中全部FlatList/SectionList开标签(前缀碰撞不误提取) */
export function extractListOpenTags(source: string): ListOpenTag[] {
  const tags: ListOpenTag[] = [];
  const re = /<(FlatList|SectionList)(?=[\s>/])/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(source)) !== null) {
    const tagEnd = openTagEnd(source, m.index);
    const tag = source.slice(m.index, tagEnd);
    tags.push({
      component: m[1] as ListOpenTag['component'],
      tag,
      hasKeyExtractor: /\bkeyExtractor\s*=/.test(tag),
    });
  }
  return tags;
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

// ---------- 合成控制 ----------

describe('F306 提取健壮性(合成样例)', () => {
  test('花括号深度扫描: keyExtractor表达式内>不误断开标签', () => {
    const src =
      '<FlatList\n' +
      '  data={items}\n' +
      '  keyExtractor={(item) => (item.id > 0 ? String(item.id) : `x-${item.key}`)}\n' +
      '  renderItem={({ item }) => <Row item={item} />}\n' +
      '/>';
    const tags = extractListOpenTags(src);
    expect(tags).toHaveLength(1);
    expect(tags[0].component).toBe('FlatList');
    expect(tags[0].hasKeyExtractor).toBe(true);
    // 标签必须完整包含renderItem行(若被item.id > 0的>误断则不含)
    expect(tags[0].tag).toContain('renderItem');
  });

  test('缺keyExtractor开标签命中', () => {
    const src = '<SectionList sections={secs} renderItem={renderRow} />';
    const tags = extractListOpenTags(src);
    expect(tags).toHaveLength(1);
    expect(tags[0].component).toBe('SectionList');
    expect(tags[0].hasKeyExtractor).toBe(false);
  });

  test('前缀碰撞不误提取(<FlatListFoo/<SectionLists)', () => {
    const src = '<FlatListFoo data={d} />\n<SectionLists x={1} />';
    expect(extractListOpenTags(src)).toHaveLength(0);
  });

  test('开标签未闭合抛错(缺输入FAIL不静默)', () => {
    expect(() => extractListOpenTags('<FlatList data={d}')).toThrow('开标签未闭合');
  });
});

// ---------- 全仓对账 ----------

describe('F306 全仓对账: FlatList/SectionList×keyExtractor成对', () => {
  const tsxFiles = collectTsxFiles(SRC_DIR);
  if (tsxFiles.length === 0) {
    throw new Error('src下零tsx文件: 缺输入FAIL不静默(F212)');
  }
  const findings = tsxFiles.flatMap((file) =>
    extractListOpenTags(fs.readFileSync(file, 'utf-8')).map((t) => ({
      relPath: path.relative(SRC_DIR, file),
      ...t,
    })),
  );

  test('提取活性: 对账清单含已知4处FlatList(防豁免吞掉全部断言)', () => {
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
    test('零列表态合法显式输出(F302形态): 全仓0 FlatList/SectionList, 守卫空跑放行', () => {
      expect(findings).toHaveLength(0);
    });
  }

  test.each(findings.map((f) => [`${f.relPath} <${f.component}>`, f] as const))(
    '%s 必须携带keyExtractor(index键致重排状态串位+diff整段重建)',
    (_label, finding) => {
      expect(finding.hasKeyExtractor).toBe(true);
    },
  );
});
