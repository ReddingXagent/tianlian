import fs from 'fs';
import path from 'path';

/**
 * F388: 交互元素accessibilityRole声明静态守卫(移动端维度, accessibility族第一枚)
 *
 * 缺口(F381全量化): 全仓38个交互pressable×16文件×零accessibility声明。
 * TalkBack/VoiceOver用户进入app后所有按钮只被读作"按钮"之外的无意义
 * 容器或直接跳过——充电场景夜间/户外强光下视障与低视力用户依赖读屏,
 * 零声明=功能不可达。RN不声明accessibilityRole不报错不警告, tsc盲区:
 * optional prop缺失类型系统无从感知(F330同族形态)。
 *
 * 不变量:
 * - 全仓src/**\/*.tsx(排除__tests__)中每个携带onPress的
 *   <Pressable|TouchableOpacity|TouchableHighlight|TouchableWithoutFeedback>
 *   开标签必须声明accessibilityRole。
 * - accessibilityRole={变量}豁免(F330语义: 静态不可判定不从严, 入族判定
 *   无信息时不存在"默认即高危"前提)。
 * - 无onPress=非交互元素不入审(F318同判据)。
 * - 零命中合法显式输出(F302形态): F388修复轮已补齐全部38处(36处机械
 *   role="button"+VehicleScreen defaultCheck特判checkbox×accessibilityState
 *   +CameraScanner closeBtn补accessibilityLabel), 门禁防未来新按钮欠账。
 * - 缺输入(零tsx文件)抛错FAIL(F212不静默)。
 *
 * 提取健壮性: 花括号深度扫描开标签终点(F306/F318同源); 前缀碰撞不误提取;
 * 多行开标签role在任意行均可检出。
 *
 * 接入: jest全量跑自动入门禁(本仓无CI/Makefile, 走jest测试接入,
 * F278/F306/F312族同惯例)。
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

/** 单文件对账: 每个带onPress的可点组件开标签必须声明accessibilityRole */
export function auditFile(relPath: string, source: string): AccessibilityFinding[] {
  const findings: AccessibilityFinding[] = [];
  const re = /<(Pressable|TouchableOpacity|TouchableHighlight|TouchableWithoutFeedback)(?=[\s>/])/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(source)) !== null) {
    const tag = source.slice(m.index, openTagEnd(source, m.index));
    if (!/\bonPress\s*=/.test(tag)) continue; // 无onPress=非交互, 不入审
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
  if (f.roleIsDynamic) return false; // {变量}静态不可判定豁免(F330语义)
  return !f.hasRole;
}

// ---------- 合成控制 ----------

describe('F388 提取健壮性(合成样例)', () => {
  const wrap = (body: string): string =>
    `import { View } from 'react-native';\nexport function X() { return (${body}); }\n`;

  test('交互元素零role声明→命中', () => {
    const src = wrap('<TouchableOpacity onPress={go}><Text>充电</Text></TouchableOpacity>');
    const findings = auditFile('synthetic/NoRole.tsx', src);
    expect(findings).toHaveLength(1);
    expect(isViolation(findings[0])).toBe(true);
  });

  test('role="button"声明→放行', () => {
    const src = wrap('<Pressable accessibilityRole="button" onPress={go} />');
    const findings = auditFile('synthetic/Role.tsx', src);
    expect(isViolation(findings[0])).toBe(false);
  });

  test('role={变量}→豁免(F330静态不可判定语义)', () => {
    const src = wrap('<Pressable accessibilityRole={dynamicRole} onPress={go} />');
    const findings = auditFile('synthetic/Dynamic.tsx', src);
    expect(findings[0].roleIsDynamic).toBe(true);
    expect(isViolation(findings[0])).toBe(false);
  });

  test('checkbox语义声明→放行(特判形态VehicleScreen defaultCheck)', () => {
    const src = wrap(
      '<TouchableOpacity accessibilityRole="checkbox" accessibilityState={{ checked: isOn }} onPress={go} />',
    );
    const findings = auditFile('synthetic/Checkbox.tsx', src);
    expect(isViolation(findings[0])).toBe(false);
  });

  test('自闭合标签无role→命中(icon-only形态)', () => {
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

  test('前缀碰撞不误提取(<PressableFoo)', () => {
    const src = '<PressableFoo onPress={go} />';
    expect(auditFile('synthetic/Prefix.tsx', src)).toHaveLength(0);
  });
});

// ---------- 全仓对账 ----------

describe('F388 全仓对账: 交互pressable必声明accessibilityRole', () => {
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
      'screens/VehicleScreen.tsx',
      'screens/ScanScreen.tsx',
      'components/CameraScanner.tsx',
      'components/StationCard.tsx',
    ]) {
      expect(files).toContain(known);
    }
  });

  test('提取活性: 声明覆盖文件≥15个(防审计域收缩F380形态, F1396 shared-ui提取后-1)', () => {
    const files = new Set(findings.map((f) => f.relPath));
    expect(files.size).toBeGreaterThanOrEqual(15);
  });

  const violations = findings.filter(isViolation);
  if (violations.length > 0) {
    test.each(
      violations.map(
        (f) => [`${f.relPath} <${f.component}>`, f] as const,
      ),
    )('%s 缺accessibilityRole: 读屏用户无法感知交互语义, 补role声明', (_label, finding) => {
      expect(isViolation(finding)).toBe(false);
    });
  }

  if (violations.length === 0) {
    test('全仓交互pressable全声明accessibilityRole: F388修复轮38处补齐后门禁防新欠账', () => {
      expect(violations).toHaveLength(0);
      expect(findings.length).toBeGreaterThanOrEqual(37);
    });
  }
});
