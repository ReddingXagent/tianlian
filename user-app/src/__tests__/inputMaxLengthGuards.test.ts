import fs from 'fs';
import path from 'path';

/**
 * F330: TextInput×数字键盘↔maxLength成对守卫(输入族第一枚)
 *
 * 缺口: keyboardType=phone-pad/number-pad/numeric/decimal-pad只限定按键集合,
 * 不限定长度——缺maxLength时用户可无限输入(iOS number-pad甚至无Done键),
 * 与提交侧格式校验(手机号11位/验证码6位)静默脱节: 打完30位才在提交时撞错。
 * maxLength是optional prop, tsc盲区, 与F324(Image×onError)同族形态。
 *
 * 不变量:
 * - 任何<TextInput>的keyboardType落在数字键盘族(phone-pad/number-pad/
 *   numeric/decimal-pad) → 必须声明maxLength(输入长度契约的唯一声明源)
 * - keyboardType为其他值(default/email-address等) → 族外豁免
 * - keyboardType缺失(默认键盘) → 族外豁免
 * - keyboardType={变量}(静态不可判定键盘族) → 族外豁免(与Image source从严
 *   不同: 此处无键盘族信息即无法判定入族, 不存在"默认即高危"前提)
 *
 * 缺输入必须FAIL(F212): src下无可扫.tsx → 抛错。
 * 接入: jest全量跑自动入门禁(本仓无CI/Makefile, 走jest测试接入)。
 */

const SRC_DIR = path.join(__dirname, '..');

/** 数字键盘族(RN keyboardType取值中限定数字输入的子集) */
const NUMERIC_KEYBOARDS = ['phone-pad', 'number-pad', 'numeric', 'decimal-pad'];

/**
 * 提取source中全部<TextInput>开标签全文(支持多行props)。
 * 开标签=从`<TextInput`起, 按花括号深度扫描到配平后的首个`>`(F318铁律:
 * 花括号深度扫描, 不数字串——onChangeText={{...}}内可含任意嵌套)。
 * TextInput自闭合或仅开标签即可判props。
 */
export function extractTextInputOpenTags(source: string): string[] {
  const tags: string[] = [];
  let cursor = 0;
  for (;;) {
    const start = source.indexOf('<TextInput', cursor);
    if (start === -1) break;
    // 排除<TextInputXxx等更长组件名的前缀碰撞(F318铁律)
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
      throw new Error('F330: <TextInput开标签未配平(缺>), 提取失败——缺输入不静默');
    }
    tags.push(source.slice(start, end + 1));
    cursor = end + 1;
  }
  return tags;
}

/**
 * 判定开标签的键盘族:
 * - 'numeric': keyboardType字面量落在数字键盘族
 * - 'other':   keyboardType为其他字面量, 或缺失(默认键盘)
 * - 'dynamic': keyboardType={变量}, 静态不可判定 → 族外豁免
 */
export function classifyKeyboard(openTag: string): 'numeric' | 'other' | 'dynamic' {
  const m = openTag.match(/\bkeyboardType\s*=\s*("([^"]*)"|\{([^}]*)\})/);
  if (!m) return 'other';
  if (m[2] !== undefined) {
    return NUMERIC_KEYBOARDS.includes(m[2]) ? 'numeric' : 'other';
  }
  const expr = (m[3] || '').trim();
  if (/^["'][^"']*["']$/.test(expr)) {
    const literal = expr.slice(1, -1);
    return NUMERIC_KEYBOARDS.includes(literal) ? 'numeric' : 'other';
  }
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

describe('F330 TextInput数字键盘×maxLength成对守卫(输入族第一枚)', () => {
  it('缺输入必须FAIL: src下无.tsx可扫 → 抛错(F212)', () => {
    const files = collectTsxFiles(SRC_DIR);
    expect(files.length).toBeGreaterThan(0);
  });

  it('提取器: 多行props开标签完整提取(花括号深度扫描)', () => {
    const src = [
      '<TextInput',
      "  style={[styles.input, styles.codeInput]}",
      '  onChangeText={(text) => {',
      '    setCode(text);',
      '    setError(null);',
      '  }}',
      '  keyboardType="number-pad"',
      '  maxLength={6}',
      '/>',
    ].join('\n');
    const tags = extractTextInputOpenTags(src);
    expect(tags).toHaveLength(1);
    expect(tags[0]).toContain('keyboardType');
    expect(tags[0]).toContain('maxLength');
  });

  it('提取器: <TextInputXxx前缀碰撞不误提取(F318铁律)', () => {
    const src = '<TextInputMask value={v} />';
    expect(extractTextInputOpenTags(src)).toHaveLength(0);
  });

  it('合成: 数字键盘缺maxLength → 命中', () => {
    const tag = '<TextInput keyboardType="phone-pad" value={phone} onChangeText={setPhone} />';
    expect(classifyKeyboard(tag)).toBe('numeric');
    expect(/\bmaxLength\s*=/.test(tag)).toBe(false);
  });

  it('合成: 数字键盘带maxLength → 放行', () => {
    const tag = '<TextInput keyboardType="number-pad" maxLength={6} value={code} />';
    expect(classifyKeyboard(tag)).toBe('numeric');
    expect(/\bmaxLength\s*=/.test(tag)).toBe(true);
  });

  it('合成: 默认键盘缺maxLength → 族外豁免', () => {
    const tag = '<TextInput value={text} onChangeText={setText} />';
    expect(classifyKeyboard(tag)).toBe('other');
  });

  it('合成: 非数字键盘字面量(email-address) → 族外豁免', () => {
    const tag = '<TextInput keyboardType="email-address" value={email} />';
    expect(classifyKeyboard(tag)).toBe('other');
  });

  it('合成: keyboardType={变量}静态不可判定 → 族外豁免', () => {
    const tag = '<TextInput keyboardType={dynamicKeyboard} value={v} />';
    expect(classifyKeyboard(tag)).toBe('dynamic');
  });

  it('全仓对账: 所有数字键盘<TextInput>必须声明maxLength(当前基线2实体)', () => {
    const files = collectTsxFiles(SRC_DIR);
    const violations: string[] = [];
    let numericCount = 0;
    for (const file of files) {
      const source = fs.readFileSync(file, 'utf8');
      for (const tag of extractTextInputOpenTags(source)) {
        if (classifyKeyboard(tag) !== 'numeric') continue;
        numericCount++;
        if (!/\bmaxLength\s*=/.test(tag)) {
          violations.push(`${path.relative(SRC_DIR, file)}: 数字键盘TextInput缺maxLength`);
        }
      }
    }
    // 当前基线: LoginScreen手机号(phone-pad/11)+验证码(number-pad/6)共2实体, 均已声明
    expect(violations).toEqual([]);
    expect(numericCount).toBe(2);
  });
});
