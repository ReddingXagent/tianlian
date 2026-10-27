import fs from 'fs';
import path from 'path';

/**
 * F318: 触控目标最小尺寸静态守卫(移动端维度, 触控族第一枚)
 *
 * 缺口: iOS HIG最小触控目标44pt。RN中TouchableOpacity/Pressable携带
 * 固定height/width < 44时点击区即视觉尺寸, 用户(尤其户外充电场景
 * 单手操作)频繁误触/点不中——无警告无报错, 表现为"按钮不灵"。
 * tsc盲区: 尺寸是样式数值, 类型系统无从感知; 既有列表族/键盘族守卫
 * 均不覆盖可点元素尺寸维度。
 *
 * 不变量:
 * - 全仓src/**\/*.tsx(排除__tests__)中每个携带onPress的
 *   <Pressable|TouchableOpacity|TouchableHighlight|TouchableWithoutFeedback>
 *   开标签: 解析其style引用的同文件StyleSheet定义+内联对象字面量,
 *   顶层height/width数值字面量<44即命中。
 * - 嵌套对象剥离: shadowOffset/transform等嵌套{...}内的width/height
 *   不是布局尺寸, 只解析样式对象顶层属性(原型首跑StationCard.card的
 *   shadowOffset{width:0,height:1}误报后固化)。
 * - hitSlop显式携带→豁免(RN官方小目标补偿机制, 扩大命中区不改视觉)。
 * - 无onPress=非交互元素不入审; 百分比/flex/无尺寸声明=静态不可判定
 *   豁免(保守棘轮只查静态可判定的固定值)。
 * - 零命中合法显式输出(F302形态): 全仓基线38个交互pressable零固定
 *   小尺寸=守卫先行非缺陷, 门禁防未来小按钮欠账。
 * - 缺输入(零tsx/style引用解析不到定义)抛错FAIL(F212不静默)。
 *
 * 提取健壮性: 花括号深度扫描开标签终点(F306同源); styles.X引用按词
 * 边界提取不误吞前缀碰撞; StyleSheet定义体嵌套剥离后顶层正则; 内联
 * 对象字面量同样剥嵌套再取顶层数值。
 *
 * 摸底现状: 全仓38个交互pressable/50处styles引用, 小尺寸样式(22x22
 * radio/checkbox、36x36 markerDot等)均挂内层View装饰而非pressable
 * 自身→零命中。变异档: 固定高度36注入/嵌套shadowOffset不命中/
 * hitSlop豁免/未解析引用抛错, 合成样例全覆盖。
 *
 * 接入: jest全量跑自动入门禁(本仓无CI/Makefile, 走jest测试接入,
 * F278/F306/F312族同惯例)。
 */

const SRC_DIR = path.join(__dirname, '..');
/** iOS HIG最小触控目标(pt) */
export const MIN_TOUCH_TARGET = 44;

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

/** 剥掉嵌套对象只留顶层属性文本(shadowOffset/transform内数值不参与判定) */
export function stripNested(body: string): string {
  let out = '';
  let depth = 0;
  for (let i = 0; i < body.length; i++) {
    const ch = body[i];
    if (ch === '{') depth++;
    else if (ch === '}') depth--;
    else if (depth === 0) out += ch;
  }
  return out;
}

/** 从样式对象顶层文本提取固定height/width数值(百分比字符串=静态不可判定, 不提取) */
export function extractFixedSizes(topLevel: string): { height?: number; width?: number } {
  const h = /(^|[,{\s])height:\s*(\d+(?:\.\d+)?)(?![\w%'])/.exec(topLevel);
  const w = /(^|[,{\s])width:\s*(\d+(?:\.\d+)?)(?![\w%'])/.exec(topLevel);
  return { height: h ? Number(h[2]) : undefined, width: w ? Number(w[2]) : undefined };
}

/** 提取文件内StyleSheet.create全部样式名→顶层固定尺寸映射 */
export function extractStyleSheetSizes(source: string): Map<string, { height?: number; width?: number }> {
  const map = new Map<string, { height?: number; width?: number }>();
  const anchor = /StyleSheet\.create\s*\(/.exec(source);
  if (!anchor) return map;
  const blockStart = source.indexOf('{', anchor.index + anchor[0].length);
  let depth = 0;
  let blockEnd = blockStart;
  for (let j = blockStart; j < source.length; j++) {
    if (source[j] === '{') depth++;
    else if (source[j] === '}') {
      depth--;
      if (depth === 0) {
        blockEnd = j;
        break;
      }
    }
  }
  const block = source.slice(blockStart + 1, blockEnd);
  const nameRe = /([A-Za-z_$][\w$]*):\s*\{/g;
  let m: RegExpExecArray | null;
  while ((m = nameRe.exec(block)) !== null) {
    const bodyStart = block.indexOf('{', m.index + m[1].length);
    let d = 0;
    let bodyEnd = bodyStart;
    for (let j = bodyStart; j < block.length; j++) {
      if (block[j] === '{') d++;
      else if (block[j] === '}') {
        d--;
        if (d === 0) {
          bodyEnd = j;
          break;
        }
      }
    }
    map.set(m[1], extractFixedSizes(stripNested(block.slice(bodyStart + 1, bodyEnd))));
    nameRe.lastIndex = bodyEnd;
  }
  return map;
}

/** 提取style属性表达式内全部styles.X引用名(词边界, 前缀碰撞不误吞) */
export function extractStyleRefs(tag: string): string[] {
  const refs: string[] = [];
  const re = /styles\.([A-Za-z_$][\w$]*)/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(tag)) !== null) refs.push(m[1]);
  return refs;
}

/** 提取style属性内内联对象字面量(数组元素中{...}形态)的顶层固定尺寸 */
export function extractInlineSizes(tag: string): { height?: number; width?: number } {
  const styleAttr = /style\s*=\s*\{/.exec(tag);
  if (!styleAttr) return {};
  const exprStart = tag.indexOf('{', styleAttr.index + 'style'.length);
  let depth = 0;
  let exprEnd = exprStart;
  for (let j = exprStart; j < tag.length; j++) {
    if (tag[j] === '{') depth++;
    else if (tag[j] === '}') {
      depth--;
      if (depth === 0) {
        exprEnd = j;
        break;
      }
    }
  }
  const expr = tag.slice(exprStart, exprEnd + 1);
  // 只收"样式对象位置"的对象字面量: wrapper直挂根对象字面量(style={{...}}
  // 与三元分支, 此时stack仅剩wrapper一层) / 数组元素(parent为[)。
  // 对象内嵌对象是shadowOffset/transform类属性值, 不是样式对象, 不入候选
  // (首跑内联shadowOffset误报后固化)。注意expr首个{是JSX表达式wrapper而非
  // 样式对象——style={{...}}双层花括号漏检即此处wrapper判定修复(F318接手轮)。
  const merged: { height?: number; width?: number } = {};
  const stack: string[] = [];
  for (let i = 0; i < expr.length; i++) {
    const ch = expr[i];
    if (ch === '{') {
      const isWrapper = stack.length === 0;
      const parent = stack.length > 0 ? stack[stack.length - 1] : null;
      if (!isWrapper && (parent === '[' || stack.length === 1)) {
        let d = 0;
        let end = i;
        for (let j = i; j < expr.length; j++) {
          if (expr[j] === '{') d++;
          else if (expr[j] === '}') {
            d--;
            if (d === 0) {
              end = j;
              break;
            }
          }
        }
        const sizes = extractFixedSizes(stripNested(expr.slice(i + 1, end)));
        if (sizes.height !== undefined) merged.height = sizes.height;
        if (sizes.width !== undefined) merged.width = sizes.width;
      }
      stack.push('{');
    } else if (ch === '}') stack.pop();
    else if (ch === '[') stack.push('[');
    else if (ch === ']') stack.pop();
  }
  return merged;
}

export interface TouchTargetFinding {
  component: string;
  relPath: string;
  styleRefs: string[];
  fixedHeight?: number;
  fixedWidth?: number;
  hasHitSlop: boolean;
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

/** 单文件对账: 每个带onPress的可点组件开标签解析固定尺寸×44门限 */
export function auditFile(relPath: string, source: string): TouchTargetFinding[] {
  const sheet = extractStyleSheetSizes(source);
  const findings: TouchTargetFinding[] = [];
  const re = /<(Pressable|TouchableOpacity|TouchableHighlight|TouchableWithoutFeedback)(?=[\s>/])/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(source)) !== null) {
    const tag = source.slice(m.index, openTagEnd(source, m.index));
    if (!/\bonPress\s*=/.test(tag)) continue; // 无onPress=非交互, 不入审
    const styleRefs = extractStyleRefs(tag);
    let fixedHeight: number | undefined;
    let fixedWidth: number | undefined;
    for (const ref of styleRefs) {
      if (!sheet.has(ref)) throw new Error(`style引用解析不到定义: styles.${ref}`);
      const sizes = sheet.get(ref) ?? {};
      if (sizes.height !== undefined) fixedHeight = sizes.height;
      if (sizes.width !== undefined) fixedWidth = sizes.width;
    }
    const inline = extractInlineSizes(tag);
    if (inline.height !== undefined) fixedHeight = inline.height;
    if (inline.width !== undefined) fixedWidth = inline.width;
    findings.push({
      component: m[1],
      relPath,
      styleRefs,
      fixedHeight,
      fixedWidth,
      hasHitSlop: /\bhitSlop\s*=/.test(tag),
    });
  }
  return findings;
}

function isViolation(f: TouchTargetFinding): boolean {
  if (f.hasHitSlop) return false;
  return (
    (f.fixedHeight !== undefined && f.fixedHeight < MIN_TOUCH_TARGET) ||
    (f.fixedWidth !== undefined && f.fixedWidth < MIN_TOUCH_TARGET)
  );
}

// ---------- 合成控制 ----------

describe('F318 提取健壮性(合成样例)', () => {
  const wrap = (body: string): string =>
    `import { StyleSheet } from 'react-native';\nexport function X() { return (${body}); }\n`;

  test('固定height<44→命中', () => {
    const src =
      wrap('<TouchableOpacity style={styles.tiny} onPress={go} />') +
      'const styles = StyleSheet.create({ tiny: { height: 36, backgroundColor: "#fff" } });';
    const findings = auditFile('synthetic/Tiny.tsx', src);
    expect(findings).toHaveLength(1);
    expect(isViolation(findings[0])).toBe(true);
    expect(findings[0].fixedHeight).toBe(36);
  });

  test('固定width<44→命中(图标按钮窄宽)', () => {
    const src =
      wrap('<Pressable style={styles.iconBtn} onPress={go} />') +
      'const styles = StyleSheet.create({ iconBtn: { width: 32, height: 48 } });';
    const findings = auditFile('synthetic/Narrow.tsx', src);
    expect(isViolation(findings[0])).toBe(true);
  });

  test('边界: height=44→放行(>=门限)', () => {
    const src =
      wrap('<TouchableOpacity style={styles.ok} onPress={go} />') +
      'const styles = StyleSheet.create({ ok: { height: 44 } });';
    const findings = auditFile('synthetic/Boundary.tsx', src);
    expect(isViolation(findings[0])).toBe(false);
  });

  test('嵌套shadowOffset的width/height不误报(原型首跑StationCard.card假阳性固化)', () => {
    const src =
      wrap('<TouchableOpacity style={styles.card} onPress={go} />') +
      'const styles = StyleSheet.create({ card: { padding: 16, shadowOffset: { width: 0, height: 1 } } });';
    const findings = auditFile('synthetic/Shadow.tsx', src);
    expect(findings[0].fixedHeight).toBeUndefined();
    expect(isViolation(findings[0])).toBe(false);
  });

  test('hitSlop携带→豁免(RN官方小目标补偿)', () => {
    const src =
      wrap('<TouchableOpacity style={styles.tiny} onPress={go} hitSlop={{ top: 10, bottom: 10 }} />') +
      'const styles = StyleSheet.create({ tiny: { height: 30 } });';
    const findings = auditFile('synthetic/HitSlop.tsx', src);
    expect(findings[0].hasHitSlop).toBe(true);
    expect(isViolation(findings[0])).toBe(false);
  });

  test('数组style条件引用可解析', () => {
    const src =
      wrap('<TouchableOpacity style={[styles.base, active && styles.baseActive]} onPress={go} />') +
      'const styles = StyleSheet.create({ base: { height: 56 }, baseActive: { opacity: 0.7 } });';
    const findings = auditFile('synthetic/Array.tsx', src);
    expect(findings[0].styleRefs).toEqual(['base', 'baseActive']);
    expect(isViolation(findings[0])).toBe(false);
  });

  test('内联对象字面量height<44→命中', () => {
    const src = wrap('<Pressable style={{ height: 28, width: 100 }} onPress={go} />');
    const findings = auditFile('synthetic/Inline.tsx', src);
    expect(findings[0].fixedHeight).toBe(28);
    expect(isViolation(findings[0])).toBe(true);
  });

  test('内联嵌套对象不误报', () => {
    const src = wrap('<Pressable style={{ shadowOffset: { width: 0, height: 2 } }} onPress={go} />');
    const findings = auditFile('synthetic/InlineNested.tsx', src);
    expect(isViolation(findings[0])).toBe(false);
  });

  test('百分比height静态不可判定→豁免', () => {
    const src =
      wrap("<TouchableOpacity style={styles.half} onPress={go} />") +
      "const styles = StyleSheet.create({ half: { height: '50%' } });";
    const findings = auditFile('synthetic/Percent.tsx', src);
    expect(findings[0].fixedHeight).toBeUndefined();
    expect(isViolation(findings[0])).toBe(false);
  });

  test('无onPress非交互→不入审', () => {
    const src =
      wrap('<View style={styles.tiny} />') +
      'const styles = StyleSheet.create({ tiny: { height: 20 } });';
    expect(auditFile('synthetic/NonInteractive.tsx', src)).toHaveLength(0);
  });

  test('前缀碰撞不误提取(<TouchableOpacityFoo)', () => {
    const src = '<TouchableOpacityFoo style={s} onPress={go} />';
    expect(auditFile('synthetic/Prefix.tsx', src)).toHaveLength(0);
  });

  test('style引用解析不到定义抛错(缺输入FAIL不静默)', () => {
    const src = wrap('<TouchableOpacity style={styles.ghost} onPress={go} />');
    expect(() => auditFile('synthetic/Ghost.tsx', src)).toThrow('解析不到定义');
  });
});

// ---------- 全仓对账 ----------

describe('F318 全仓对账: 交互pressable固定尺寸×44门限', () => {
  const tsxFiles = collectTsxFiles(SRC_DIR);
  if (tsxFiles.length === 0) {
    throw new Error('src下零tsx文件: 缺输入FAIL不静默(F212)');
  }
  const findings = tsxFiles.flatMap((file) =>
    auditFile(path.relative(SRC_DIR, file), fs.readFileSync(file, 'utf-8')),
  );

  test('提取活性: 交互pressable≥37且已知五文件在场(防豁免吞掉全部断言)', () => {
    expect(findings.length).toBeGreaterThanOrEqual(37);
    const files = new Set(findings.map((f) => f.relPath));
    for (const known of [
      'screens/LoginScreen.tsx',
      'screens/HomeScreen.tsx',
      'screens/VehicleScreen.tsx',
      'screens/PaymentScreen.tsx',
      'screens/ProfileScreen.tsx',
    ]) {
      expect(files).toContain(known);
    }
  });

  test('提取活性: styles引用解析≥49处(StyleSheet定义对账通路活着)', () => {
    const refCount = findings.reduce((acc, f) => acc + f.styleRefs.length, 0);
    expect(refCount).toBeGreaterThanOrEqual(49);
  });

  const violations = findings.filter(isViolation);
  if (violations.length > 0) {
    test.each(
      violations.map(
        (f) =>
          [
            `${f.relPath} <${f.component}> h=${f.fixedHeight ?? '-'} w=${f.fixedWidth ?? '-'}`,
            f,
          ] as const,
      ),
    )('%s 触控目标<44pt: 加hitSlop或扩大尺寸(iOS HIG)', (_label, finding) => {
      expect(isViolation(finding)).toBe(false);
    });
  }

  if (violations.length === 0) {
    test('全仓交互pressable零固定小尺寸: 零命中=守卫先行非缺陷(F258/F306/F312型)', () => {
      expect(violations).toHaveLength(0);
      expect(findings.length).toBeGreaterThanOrEqual(37);
    });
  }
});
