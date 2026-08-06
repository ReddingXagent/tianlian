import fs from 'fs';
import path from 'path';

/**
 * F345: TextInput验证码族keyboardType×maxLength↔sms-otp autofill成对守卫(输入族第三枚)
 *
 * 缺口: 验证码输入(number-pad+短maxLength)只约束了按键集合与长度,
 * 不告诉系统这是"短信验证码"——缺autoComplete="sms-otp"(Android)与
 * textContentType="oneTimeCode"(iOS)时, 系统SMS验证码自动填充静默失效,
 * 用户切到短信app手抄6位码再切回。两prop均为optional, tsc盲区,
 * 与F330(数字键盘×maxLength)/F338(密码族×autofill)同族形态。
 *
 * 入族判定(静态可判定才入族, F330语义):
 * - keyboardType="number-pad"|"numeric"(静态字面量) 且
 * - maxLength={2..8的静态数字字面量}(验证码典型长度域, 与F330的
 *   "数字键盘族必须声明maxLength"义务衔接: 已声明且短才像验证码)
 * 两条件同时满足 → otp族; 任一缺失/={变量}/超域 → 族外豁免
 * (无入族信息即无义务, 不存在"默认即高危"前提)。
 * phone-pad(手机号11位)/decimal-pad(金额)键盘集外天然豁免。
 *
 * 不变量:
 * - otp族TextInput → 必须同时声明autoComplete="sms-otp"(Android)与
 *   textContentType="oneTimeCode"(iOS), 平台分治缺一侧即该平台
 *   SMS autofill静默失效(F338同语义)。
 *
 * 缺输入必须FAIL(F212): src下无可扫.tsx → 抛错。
 * 接入: jest全量跑自动入门禁(本仓无CI/Makefile, 走jest测试接入)。
 */

const SRC_DIR = path.join(__dirname, '..');

/** OTP键盘集: 纯数字短码输入的键盘形态(phone-pad/decimal-pad域外) */
const OTP_KEYBOARDS = new Set(['number-pad', 'numeric']);
/** 验证码典型长度域: 2~8位(6位主流, 4位银行/8位长码覆盖) */
const OTP_LEN_MIN = 2;
const OTP_LEN_MAX = 8;

/**
 * 提取source中全部<TextInput>开标签全文(支持多行props)。
 * 与F330/F338共享同一形态: 花括号深度扫描到配平后的首个`>`(F318铁律),
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
      throw new Error('F345: <TextInput开标签未配平(缺>), 提取失败——缺输入不静默');
    }
    tags.push(source.slice(start, end + 1));
    cursor = end + 1;
  }
  return tags;
}

/**
 * 判定开标签的验证码族:
 * - 'otp':     keyboardType∈OTP键盘集(字面量) 且 maxLength={2..8字面量}
 * - 'other':   键盘集外/长度域外/任一prop缺失(静态不入族)
 * - 'dynamic': keyboardType或maxLength为{变量}, 静态不可判定 → 族外豁免
 */
export function classifyOtpInput(openTag: string): 'otp' | 'other' | 'dynamic' {
  const kb = openTag.match(/\bkeyboardType\s*=\s*("([^"]*)"|\{([^}]*)\})/);
  if (!kb) return 'other';
  if (kb[3] !== undefined) return 'dynamic'; // {变量}不可判定
  const kbValue = kb[2] as string;
  if (!OTP_KEYBOARDS.has(kbValue)) return 'other';

  const ml = openTag.match(/\bmaxLength\s*=\s*(\{([^}]*)\}|(\d+))/);
  if (!ml) return 'other'; // maxLength缺失: F330守卫域管辖, 本守卫不入族
  if (ml[2] !== undefined) {
    const expr = ml[2].trim();
    if (/^\d+$/.test(expr)) {
      const len = Number(expr);
      return len >= OTP_LEN_MIN && len <= OTP_LEN_MAX ? 'otp' : 'other';
    }
    return 'dynamic'; // {变量}不可判定
  }
  const len = Number(ml[3]);
  return len >= OTP_LEN_MIN && len <= OTP_LEN_MAX ? 'otp' : 'other';
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

const ANDROID_OTP = /\bautoComplete\s*=\s*["'{](["']?)sms-otp\1["'}]/;
const IOS_OTP = /\btextContentType\s*=\s*["'{](["']?)oneTimeCode\1["'}]/;

describe('F345 TextInput验证码族keyboardType×maxLength↔sms-otp autofill成对守卫(输入族第三枚)', () => {
  it('缺输入必须FAIL: src下无.tsx可扫 → 抛错(F212)', () => {
    const files = collectTsxFiles(SRC_DIR);
    expect(files.length).toBeGreaterThan(0);
  });

  it('提取器: 多行props开标签完整提取(花括号深度扫描)', () => {
    const src = [
      '<TextInput',
      '  style={[styles.input, styles.codeInput]}',
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
    expect(tags[0]).toContain('keyboardType="number-pad"');
  });

  it('提取器: <TextInputXxx前缀碰撞不误提取(F318铁律)', () => {
    const src = '<TextInputMask keyboardType="number-pad" maxLength={6} value={v} />';
    expect(extractTextInputOpenTags(src)).toHaveLength(0);
  });

  it('分类: number-pad+maxLength={6} → otp族', () => {
    expect(classifyOtpInput('<TextInput keyboardType="number-pad" maxLength={6} value={c} />')).toBe('otp');
  });

  it('分类: numeric+maxLength={4} → otp族', () => {
    expect(classifyOtpInput('<TextInput keyboardType="numeric" maxLength={4} value={c} />')).toBe('otp');
  });

  it('分类: phone-pad+maxLength={11} → 族外豁免(键盘集外)', () => {
    expect(classifyOtpInput('<TextInput keyboardType="phone-pad" maxLength={11} value={p} />')).toBe('other');
  });

  it('分类: number-pad缺maxLength → 族外豁免(F330守卫域管辖)', () => {
    expect(classifyOtpInput('<TextInput keyboardType="number-pad" value={c} />')).toBe('other');
  });

  it('分类: number-pad+maxLength={12} → 族外豁免(长度域外)', () => {
    expect(classifyOtpInput('<TextInput keyboardType="number-pad" maxLength={12} value={c} />')).toBe('other');
  });

  it('分类: keyboardType={变量}静态不可判定 → 族外豁免', () => {
    expect(classifyOtpInput('<TextInput keyboardType={kb} maxLength={6} value={c} />')).toBe('dynamic');
  });

  it('分类: maxLength={变量}静态不可判定 → 族外豁免', () => {
    expect(classifyOtpInput('<TextInput keyboardType="number-pad" maxLength={codeLen} value={c} />')).toBe('dynamic');
  });

  it('合成: otp族缺autoComplete="sms-otp"(Android autofill) → 命中', () => {
    const tag =
      '<TextInput keyboardType="number-pad" maxLength={6} textContentType="oneTimeCode" value={c} />';
    expect(classifyOtpInput(tag)).toBe('otp');
    expect(ANDROID_OTP.test(tag)).toBe(false);
  });

  it('合成: otp族缺textContentType="oneTimeCode"(iOS autofill) → 命中', () => {
    const tag =
      '<TextInput keyboardType="number-pad" maxLength={6} autoComplete="sms-otp" value={c} />';
    expect(classifyOtpInput(tag)).toBe('otp');
    expect(IOS_OTP.test(tag)).toBe(false);
  });

  it('合成: otp族双平台autofill齐全 → 放行', () => {
    const tag =
      '<TextInput keyboardType="number-pad" maxLength={6} autoComplete="sms-otp" textContentType="oneTimeCode" value={c} />';
    expect(classifyOtpInput(tag)).toBe('otp');
    expect(ANDROID_OTP.test(tag)).toBe(true);
    expect(IOS_OTP.test(tag)).toBe(true);
  });

  it('全仓对账: 所有otp族<TextInput>必须声明双平台sms autofill(当前基线1实体)', () => {
    const files = collectTsxFiles(SRC_DIR);
    const violations: string[] = [];
    let otpCount = 0;
    for (const file of files) {
      const source = fs.readFileSync(file, 'utf8');
      for (const tag of extractTextInputOpenTags(source)) {
        if (classifyOtpInput(tag) !== 'otp') continue;
        otpCount++;
        if (!ANDROID_OTP.test(tag)) {
          violations.push(`${path.relative(SRC_DIR, file)}: 验证码TextInput缺autoComplete="sms-otp"(Android autofill)`);
        }
        if (!IOS_OTP.test(tag)) {
          violations.push(`${path.relative(SRC_DIR, file)}: 验证码TextInput缺textContentType="oneTimeCode"(iOS autofill)`);
        }
      }
    }
    // 当前基线: LoginScreen验证码输入1实体, 双平台autofill已声明(F345同轮修复)
    expect(violations).toEqual([]);
    expect(otpCount).toBe(1);
  });
});
