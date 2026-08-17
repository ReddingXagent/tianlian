import fs from 'fs';
import path from 'path';

/**
 * F1359: 交互元素accessibilityRole声明静态守卫(ops-app, 维度20 a11y)
 *
 * 缺口: 全仓39个交互pressable×15文件×零accessibility声明。
 * TalkBack/VoiceOver用户进入app后所有按钮只被读作无意义容器或直接跳过。
 * RN不声明accessibilityRole不报错不警告, tsc盲区。
 *
 * 不变量:
 * - 全仓src/**\/*.tsx(排除__tests__)中每个携带onPress的
 *   <Pressable|TouchableOpacity|TouchableHighlight|TouchableWithoutFeedback>
 *   开标签必须声明accessibilityRole。
 * - accessibilityRole={变量}豁免(静态不可判定不从严)。
 * - 无onPress=非交互元素不入审。
 * - 缺输入(零tsx文件)抛错FAIL(F212不静默)。
 *
 * 接入: jest全量跑自动入门禁。
 */

const SRC_DIR = path.join(__dirname, '..');

/** 从startIdx(指向'<')扫描开标签终点: 花括号深度扫描 */
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

export interface AccessibilityFinding {
  component: string;
  relPath: string;
  hasRole: boolean;
  roleIsDynamic: boolean;
}

export function auditFile(relPath: string, source: string): AccessibilityFinding[] {
  const findings: AccessibilityFinding[] = [];
  const re = /<(Pressable|TouchableOpacity|TouchableHighlight|TouchableWithoutFeedback)(?=[\s>/])/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(source)) !== null) {
    const tag = source.slice(m.index, openTagEnd(source, m.index));
    if (!/\bonPress\s*=/.test(tag)) continue;
    const roleMatch = /accessibilityRole\s*=\s*(?:"([^"]*)"|\{([^}]*)\})/.exec(tag);
    findings.push({
      component: m[1],
      relPath,
      hasRole: roleMatch !== null,
      roleIsDynamic: roleMatch !== null && roleMatch[2] !== undefined,
    });
  }
  return findings;
}

function isViolation(f: AccessibilityFinding): boolean {
  if (f.roleIsDynamic) return false;
  return !f.hasRole;
}

// ---------- 合成控制 ----------

describe('F1359 提取健壮性(合成样例)', () => {
  const wrap = (body: string): string =>
    `import { View } from 'react-native';\nexport function X() { return (${body}); }\n`;

  test('交互元素零role声明→命中', () => {
    const src = wrap('<TouchableOpacity onPress={go}><Text>工单</Text></TouchableOpacity>');
    const findings = auditFile('synthetic/NoRole.tsx', src);
    expect(findings).toHaveLength(1);
    expect(isViolation(findings[0])).toBe(true);
  });

  test('role="button"声明→放行', () => {
    const src = wrap('<Pressable accessibilityRole="button" onPress={go} />');
    const findings = auditFile('synthetic/Role.tsx', src);
    expect(isViolation(findings[0])).toBe(false);
  });

  test('role={变量}→豁免', () => {
    const src = wrap('<Pressable accessibilityRole={dynamicRole} onPress={go} />');
    const findings = auditFile('synthetic/Dynamic.tsx', src);
    expect(findings[0].roleIsDynamic).toBe(true);
    expect(isViolation(findings[0])).toBe(false);
  });

  test('自闭合标签无role→命中', () => {
    const src = wrap('<Pressable onPress={go} />');
    const findings = auditFile('synthetic/SelfClosing.tsx', src);
    expect(isViolation(findings[0])).toBe(true);
  });

  test('多行开标签role在末行→检出放行', () => {
    const src = wrap('<TouchableOpacity\n  style={styles.btn}\n  onPress={go}\n  accessibilityRole="button"\n>');
    const findings = auditFile('synthetic/Multiline.tsx', src);
    expect(findings).toHaveLength(1);
    expect(isViolation(findings[0])).toBe(false);
  });

  test('无onPress非交互→不入审', () => {
    const src = wrap('<Pressable style={styles.card} />');
    expect(auditFile('synthetic/NonInteractive.tsx', src)).toHaveLength(0);
  });

  test('前缀碰撞不误提取', () => {
    const src = '<PressableFoo onPress={go} />';
    expect(auditFile('synthetic/Prefix.tsx', src)).toHaveLength(0);
  });
});

// ---------- 全仓对账 ----------

describe('F1359 全仓对账: 交互pressable必声明accessibilityRole', () => {
  const tsxFiles = collectTsxFiles(SRC_DIR);
  if (tsxFiles.length === 0) {
    throw new Error('src下零tsx文件: 缺输入FAIL不静默(F212)');
  }
  const findings = tsxFiles.flatMap((file) =>
    auditFile(path.relative(SRC_DIR, file), fs.readFileSync(file, 'utf-8')),
  );

  test('提取活性: 交互pressable≥39且已知五文件在场', () => {
    expect(findings.length).toBeGreaterThanOrEqual(39);
    const files = new Set(findings.map((f) => f.relPath));
    for (const known of [
      'screens/LoginScreen.tsx',
      'screens/DashboardScreen.tsx',
      'screens/WorkOrderListScreen.tsx',
      'screens/ScanScreen.tsx',
      'screens/ProfileScreen.tsx',
    ]) {
      expect(files).toContain(known);
    }
  });

  test('提取活性: 声明覆盖文件≥10个', () => {
    const files = new Set(findings.map((f) => f.relPath));
    expect(files.size).toBeGreaterThanOrEqual(10);
  });

  const violations = findings.filter(isViolation);
  if (violations.length > 0) {
    test.each(
      violations.map(
        (f) => [`${f.relPath} <${f.component}>`, f] as const,
      ),
    )('%s 缺accessibilityRole: 读屏用户无法感知交互语义', (_label, finding) => {
      expect(isViolation(finding)).toBe(false);
    });
  }

  if (violations.length === 0) {
    test('全仓交互pressable全声明accessibilityRole: F1359修复轮39处补齐后门禁防新欠账', () => {
      expect(violations).toHaveLength(0);
      expect(findings.length).toBeGreaterThanOrEqual(39);
    });
  }
});
