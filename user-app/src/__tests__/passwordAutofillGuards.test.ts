import fs from 'fs';
import path from 'path';

/**
 * F338: TextInput×secureTextEntry↔autoComplete/textContentType成对守卫(输入族第二枚)
 *
 * 缺口: secureTextEntry只把输入显示为掩码, 不告诉系统这是"密码"——缺
 * autoComplete="password"(Android)与textContentType="password"(iOS)时,
 * 系统密码自动填充/密码管理器保存静默失效, 用户手打密码; RN两侧prop
 * 平台分治(Android只认autoComplete/iOS只认textContentType), 缺一侧即
 * 该平台静默无autofill。两prop均为optional, tsc盲区, 与F330(数字键盘
 * ×maxLength)同族形态。
 *
 * 不变量:
 * - 任何<TextInput>声明secureTextEntry(裸布尔或={true}) → 必须同时声明
 *   autoComplete="password"与textContentType="password"(双平台密码
 *   autofill契约的完整声明)
 * - secureTextEntry缺失或={false} → 族外豁免
 * - secureTextEntry={变量}(静态不可判定) → 族外豁免(与F330键盘族同语义:
 *   无入族信息即无义务, 不存在"默认即高危"前提)
 *
 * 缺输入必须FAIL(F212): src下无可扫.tsx → 抛错。
 * 接入: jest全量跑自动入门禁(本仓无CI/Makefile, 走jest测试接入)。
 */

const SRC_DIR = path.join(__dirname, '..');

/**
 * 提取source中全部<TextInput>开标签全文(支持多行props)。
 * 与F330共享同一形态: 花括号深度扫描到配平后的首个`>`(F318铁律),
 * <TextInputXxx前缀碰撞不误提取(F318铁律)。
 */
export function extractTextInputOpenTags(source: string): string[] {
  const tags: string[] = [];
  let cursor = 0;
  for (;;) {
    const start = source.indexOf('<TextInput', cursor);
    if (start === -1) break;
    const nextCh = source[start + 10];
    if (nextCh && /[A-Za-z0-9_]/.test(nextCh)) {
      cursor = start + 10;
      continue;
    }
    let depth = 0;
    let i = start;
    let end = -1;
    for (; i < source.length; i++) {
      const ch = source[i];
      if (ch === '{') depth++;
      else if (ch === '}') depth--;
      else if (ch === '>' && depth === 0) {
        end = i;
        break;
      }
    }
    if (end === -1) {
      throw new Error('F338: <TextInput开标签未配平(缺>), 提取失败——缺输入不静默');
    }
    tags.push(source.slice(start, end + 1));
    cursor = end + 1;
  }
  return tags;
}

/**
 * 判定开标签的密码族:
 * - 'password': secureTextEntry裸布尔或={true}
 * - 'other':    secureTextEntry缺失或={false}
 * - 'dynamic':   secureTextEntry={变量}, 静态不可判定 → 族外豁免
 */
export function classifySecureInput(openTag: string): 'password' | 'other' | 'dynamic' {
  const m = openTag.match(/\bsecureTextEntry(\s*=\s*("([^"]*)"|\{([^}]*)\}))?/);
  if (!m) return 'other';
  if (m[1] === undefined) return 'password'; // 裸布尔
  if (m[3] !== undefined) {
    return m[3] === 'true' ? 'password' : 'other';
  }
  const expr = (m[4] || '').trim();
  if (expr === 'true') return 'password';
  if (expr === 'false') return 'other';
  return 'dynamic';
}

/** 收集src下全部非测试.tsx源码文件 */
function collectTsxFiles(dir: string): string[] {
  const out: string[] = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === '__tests__' || entry.name === 'node_modules') continue;
      out.push(...collectTsxFiles(full));
    } else if (entry.name.endsWith('.tsx') && !entry.name.endsWith('.test.tsx')) {
      out.push(full);
    }
  }
  return out;
}

const ANDROID_AUTOFILL = /\bautoComplete\s*=\s*["'{](["']?)password\1["'}]/;
const IOS_AUTOFILL = /\btextContentType\s*=\s*["'{](["']?)password\1["'}]/;

describe('F338 TextInput密码族secureTextEntry×autofill成对守卫(输入族第二枚)', () => {
  it('缺输入必须FAIL: src下无.tsx可扫 → 抛错(F212)', () => {
    const files = collectTsxFiles(SRC_DIR);
    expect(files.length).toBeGreaterThan(0);
  });

  it('提取器: 多行props开标签完整提取(花括号深度扫描)', () => {
    const src = [
      '<TextInput',
      '  style={styles.input}',
      '  onChangeText={(text) => {',
      '    setPassword(text);',
      '    setError(null);',
      '  }}',
      '  secureTextEntry',
      '  autoComplete="password"',
      '/>',
    ].join('\n');
    const tags = extractTextInputOpenTags(src);
    expect(tags).toHaveLength(1);
    expect(tags[0]).toContain('secureTextEntry');
  });

  it('提取器: <TextInputXxx前缀碰撞不误提取(F318铁律)', () => {
    const src = '<TextInputMask value={v} />';
    expect(extractTextInputOpenTags(src)).toHaveLength(0);
  });

  it('分类: 裸布尔secureTextEntry → password族', () => {
    expect(classifySecureInput('<TextInput secureTextEntry value={p} />')).toBe('password');
  });

  it('分类: secureTextEntry={true} → password族', () => {
    expect(classifySecureInput('<TextInput secureTextEntry={true} value={p} />')).toBe('password');
  });

  it('分类: secureTextEntry={false} → 族外豁免', () => {
    expect(classifySecureInput('<TextInput secureTextEntry={false} value={p} />')).toBe('other');
  });

  it('分类: secureTextEntry={变量}静态不可判定 → 族外豁免', () => {
    expect(classifySecureInput('<TextInput secureTextEntry={isSecret} value={p} />')).toBe('dynamic');
  });

  it('合成: 密码族缺autoComplete(Android autofill) → 命中', () => {
    const tag = '<TextInput secureTextEntry textContentType="password" value={p} />';
    expect(classifySecureInput(tag)).toBe('password');
    expect(ANDROID_AUTOFILL.test(tag)).toBe(false);
  });

  it('合成: 密码族缺textContentType(iOS autofill) → 命中', () => {
    const tag = '<TextInput secureTextEntry autoComplete="password" value={p} />';
    expect(classifySecureInput(tag)).toBe('password');
    expect(IOS_AUTOFILL.test(tag)).toBe(false);
  });

  it('合成: 密码族双平台autofill齐全 → 放行', () => {
    const tag =
      '<TextInput secureTextEntry autoComplete="password" textContentType="password" value={p} />';
    expect(classifySecureInput(tag)).toBe('password');
    expect(ANDROID_AUTOFILL.test(tag)).toBe(true);
    expect(IOS_AUTOFILL.test(tag)).toBe(true);
  });

  it('全仓对账: 所有secureTextEntry<TextInput>必须声明双平台autofill(当前基线1实体)', () => {
    const files = collectTsxFiles(SRC_DIR);
    const violations: string[] = [];
    let passwordCount = 0;
    for (const file of files) {
      const source = fs.readFileSync(file, 'utf8');
      for (const tag of extractTextInputOpenTags(source)) {
        if (classifySecureInput(tag) !== 'password') continue;
        passwordCount++;
        if (!ANDROID_AUTOFILL.test(tag)) {
          violations.push(`${path.relative(SRC_DIR, file)}: 密码TextInput缺autoComplete="password"(Android autofill)`);
        }
        if (!IOS_AUTOFILL.test(tag)) {
          violations.push(`${path.relative(SRC_DIR, file)}: 密码TextInput缺textContentType="password"(iOS autofill)`);
        }
      }
    }
    // 当前基线: LoginScreen密码输入1实体, 双平台autofill已声明(F338同轮修复)
    expect(violations).toEqual([]);
    expect(passwordCount).toBe(1);
  });
});
