import fs from 'fs';
import path from 'path';

/**
 * F374: 滚动容器×键盘收起通道对账守卫(F278键盘族第四弹, 移动端维度)
 *
 * 缺口: 键盘族前三弹治理遮挡/抬升/点击穿透(F278 Modal×KAV、F285
 * keyboardShouldPersistTaps、F293 孤立TextInput×KAV), 但「收起通道」无人管——
 * RN 滚动容器 keyboardDismissMode 默认 'none': 键盘打开后滚动列表不收起键盘。
 * F285 修复又加剧此形态: keyboardShouldPersistTaps="handled" 下点击全部穿透
 * 到组件, 列表铺满屏幕时无空白区可点, 键盘只能靠提交动作收起; HomeScreen
 * 搜索框+站点列表同屏, 输完关键词滚动看结果时键盘遮住半屏站点卡片,
 * 无滚动收起通道=用户被键盘困住(摸底实测三处ScrollView全仓零声明)。
 *
 * 不变量:
 * - 剥Modal块后(F278层豁免)同文件存在TextInput开标签且存在<ScrollView>/
 *   <FlatList开标签 → 滚动容器开标签必须声明 keyboardDismissMode
 * - 值域: 'on-drag'|'interactive'|'pad' 合法; 'none' = 显式声明默认值,
 *   形式声明静默no-op(F295族最恶漂移: 看似已治理实则零效果)必拦
 * - keyboardDismissMode={变量} 静态不可判定 → 豁免(F330语义: 无静态信息即无义务)
 * - 无TextInput的文件(纯展示列表)不入审: 无键盘即无收起义务
 *
 * 提取健壮性: 开标签判定数开标签不数字串(import残留不误报); 开标签终点
 * 花括号深度扫描(refreshControl={<RefreshControl/>}嵌套JSX prop内的>不误断);
 * <ScrollableView/<FlatListFoo/<TextInputFoo前缀碰撞不误提取;
 * Modal/滚动块未闭合抛错(F212缺输入FAIL不静默)。
 * 接入: jest全量跑自动入门禁(本仓无CI/Makefile, 走jest测试接入, F278族同惯例)。
 */

const SRC_DIR = path.join(__dirname, '..');

export interface ScrollOpenTag {
  kind: 'ScrollView' | 'FlatList';
  /** 开标签全文(含多行props与嵌套JSX prop) */
  tag: string;
  /** 开标签起始行号(1-based) */
  line: number;
}

const SCROLL_KINDS = ['ScrollView', 'FlatList'] as const;
const DISMISS_VALUES = new Set(['on-drag', 'interactive', 'pad']);

/** 剥除全部<Modal>...</Modal>块(Modal独立native层, 其内输入不与背景滚动交互) */
export function stripModalBlocks(source: string): string {
  let out = '';
  let cursor = 0;
  for (;;) {
    const start = source.indexOf('<Modal', cursor);
    if (start === -1) {
      out += source.slice(cursor);
      break;
    }
    const nextCh = source[start + 6];
    if (nextCh !== undefined && !/[\s>/]/.test(nextCh)) {
      // <ModalsFoo等前缀碰撞: 原样保留继续扫
      out += source.slice(cursor, start + 6);
      cursor = start + 6;
      continue;
    }
    const end = source.indexOf('</Modal>', start);
    if (end === -1) {
      throw new Error('F374: <Modal 块未闭合(缺 </Modal>), 缺输入FAIL不静默');
    }
    out += source.slice(cursor, start);
    out += ' '.repeat(end + '</Modal>'.length - start); // 等长占位保行号
    cursor = end + '</Modal>'.length;
  }
  return out;
}

/** 数<TextInput开标签(数开标签不数字串: 下一个字符必须是空白/>//=边界) */
export function countTextInputOpenTags(source: string): number {
  let count = 0;
  let cursor = 0;
  for (;;) {
    const idx = source.indexOf('<TextInput', cursor);
    if (idx === -1) {
      break;
    }
    const nextCh = source[idx + 10];
    if (nextCh === undefined || /[\s/>]/.test(nextCh)) {
      count += 1;
    }
    cursor = idx + 10;
  }
  return count;
}

/** 提取全部<ScrollView>/<FlatList开标签(花括号深度扫描取终点) */
export function extractScrollOpenTags(source: string): ScrollOpenTag[] {
  const tags: ScrollOpenTag[] = [];
  for (const kind of SCROLL_KINDS) {
    let cursor = 0;
    for (;;) {
      const idx = source.indexOf(`<${kind}`, cursor);
      if (idx === -1) {
        break;
      }
      const nextCh = source[idx + kind.length + 1];
      if (nextCh !== undefined && !/[\s/>]/.test(nextCh)) {
        // <ScrollableView等前缀碰撞: 跳过继续
        cursor = idx + kind.length + 1;
        continue;
      }
      // 花括号深度扫描取开标签终点>(嵌套JSX prop内的>不误断)
      let depth = 0;
      let end = -1;
      for (let i = idx; i < source.length; i += 1) {
        const ch = source[i];
        if (ch === '{') {
          depth += 1;
        } else if (ch === '}') {
          depth -= 1;
        } else if (ch === '>' && depth === 0) {
          end = i;
          break;
        }
      }
      if (end === -1) {
        throw new Error(`F374: <${kind} 开标签未闭合, 缺输入FAIL不静默`);
      }
      const line = source.slice(0, idx).split('\n').length;
      tags.push({ kind, tag: source.slice(idx, end + 1), line });
      cursor = end + 1;
    }
  }
  return tags.sort((a, b) => a.line - b.line);
}

/** 不变量判定: 返回违规描述列表(空=通过) */
export function findKeyboardDismissViolations(source: string): string[] {
  const stripped = stripModalBlocks(source);
  if (countTextInputOpenTags(stripped) === 0) {
    return []; // 无TextInput=无键盘=无收起义务
  }
  const violations: string[] = [];
  for (const { kind, tag, line } of extractScrollOpenTags(stripped)) {
    const staticMatch = tag.match(/keyboardDismissMode\s*=\s*"([^"]*)"/);
    if (staticMatch) {
      if (!DISMISS_VALUES.has(staticMatch[1])) {
        violations.push(
          `第${line}行 <${kind}> keyboardDismissMode="${staticMatch[1]}" 是静默no-op值(默认'none'的形式声明, F295族): 必须声明 'on-drag'|'interactive'|'pad' 之一提供真实收起通道`,
        );
      }
      continue;
    }
    if (/keyboardDismissMode\s*=\s*\{/.test(tag)) {
      continue; // {变量}静态不可判定豁免(F330语义)
    }
    violations.push(
      `第${line}行 <${kind}> 未声明 keyboardDismissMode: 同文件存在TextInput, 键盘打开后滚动不收起键盘(RN默认'none'), 用户被键盘困住——必须声明 'on-drag'|'interactive'|'pad' 之一`,
    );
  }
  return violations;
}

function walkTsx(dir: string): string[] {
  const out: string[] = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === '__tests__') {
        continue;
      }
      out.push(...walkTsx(full));
    } else if (entry.name.endsWith('.tsx')) {
      out.push(full);
    }
  }
  return out;
}

describe('F374 滚动容器×键盘收起通道对账守卫(键盘族第四弹)', () => {
  test('合成: TextInput+ScrollView声明on-drag → 0违规', () => {
    const src = `
      export function S() {
        return (
          <ScrollView keyboardShouldPersistTaps="handled" keyboardDismissMode="on-drag">
            <TextInput value={q} onChangeText={setQ} />
          </ScrollView>
        );
      }
    `;
    expect(findKeyboardDismissViolations(src)).toEqual([]);
  });

  test('合成: TextInput+ScrollView缺keyboardDismissMode → 1违规', () => {
    const src = `
      export function S() {
        return (
          <ScrollView keyboardShouldPersistTaps="handled">
            <TextInput value={q} onChangeText={setQ} />
          </ScrollView>
        );
      }
    `;
    const v = findKeyboardDismissViolations(src);
    expect(v).toHaveLength(1);
    expect(v[0]).toContain('未声明 keyboardDismissMode');
  });

  test('合成: keyboardDismissMode="none"形式声明静默no-op → 1违规', () => {
    const src = `
      export function S() {
        return (
          <ScrollView keyboardDismissMode="none">
            <TextInput value={q} onChangeText={setQ} />
          </ScrollView>
        );
      }
    `;
    const v = findKeyboardDismissViolations(src);
    expect(v).toHaveLength(1);
    expect(v[0]).toContain('静默no-op');
  });

  test('合成: interactive/pad合法值 → 0违规', () => {
    const srcA = '<ScrollView keyboardDismissMode="interactive"><TextInput /></ScrollView>';
    const srcB = '<ScrollView keyboardDismissMode="pad"><TextInput /></ScrollView>';
    expect(findKeyboardDismissViolations(srcA)).toEqual([]);
    expect(findKeyboardDismissViolations(srcB)).toEqual([]);
  });

  test('合成: TextInput+FlatList缺声明 → 1违规(FlatList同域)', () => {
    const src = `
      export function S() {
        return (
          <FlatList data={items} renderItem={renderItem}>
            <TextInput value={q} onChangeText={setQ} />
          </FlatList>
        );
      }
    `;
    const v = findKeyboardDismissViolations(src);
    expect(v).toHaveLength(1);
    expect(v[0]).toContain('<FlatList>');
  });

  test('合成: Modal内TextInput+Modal外ScrollView无声明 → 豁免(Modal独立native层)', () => {
    const src = `
      export function S() {
        return (
          <View>
            <Modal visible={v} onRequestClose={close}>
              <TextInput value={q} onChangeText={setQ} />
            </Modal>
            <ScrollView>
              <Text>list</Text>
            </ScrollView>
          </View>
        );
      }
    `;
    expect(findKeyboardDismissViolations(src)).toEqual([]);
  });

  test('合成: 无TextInput的纯展示ScrollView → 不入审0违规', () => {
    const src = '<ScrollView><Text>show</Text></ScrollView>';
    expect(findKeyboardDismissViolations(src)).toEqual([]);
  });

  test('合成: TextInput无滚动容器 → 0违规(无容器可声明)', () => {
    const src = '<View><TextInput value={q} onChangeText={setQ} /></View>';
    expect(findKeyboardDismissViolations(src)).toEqual([]);
  });

  test('合成: keyboardDismissMode={变量}静态不可判定 → 豁免(F330语义)', () => {
    const src = '<ScrollView keyboardDismissMode={mode}><TextInput /></ScrollView>';
    expect(findKeyboardDismissViolations(src)).toEqual([]);
  });

  test('缺输入: 滚动容器开标签未闭合 → 抛错FAIL不静默', () => {
    // 探针必须含 TextInput 才能越过"无键盘即无义务"早退分支进入提取路径(F374接手轮修正)
    const src = '<TextInput value={q} onChangeText={setQ} /><ScrollView keyboardDismissMode="on-drag"';
    expect(() => findKeyboardDismissViolations(src)).toThrow(/未闭合/);
  });

  test('全仓对账: src/**/*.tsx 剥Modal后含TextInput的滚动容器全部声明合法收起通道', () => {
    const files = walkTsx(SRC_DIR);
    expect(files.length).toBeGreaterThan(0);
    const all: string[] = [];
    for (const file of files) {
      const rel = path.relative(SRC_DIR, file);
      for (const v of findKeyboardDismissViolations(fs.readFileSync(file, 'utf8'))) {
        all.push(`${rel}: ${v}`);
      }
    }
    expect(all).toEqual([]);
  });

  test('活性断言: 义务清单非空——Home/Login/Scan三屏TextInput×滚动容器在场, 防豁免吞断言', () => {
    const obligated = ['screens/HomeScreen.tsx', 'screens/LoginScreen.tsx', 'screens/ScanScreen.tsx'];
    let count = 0;
    for (const rel of obligated) {
      const source = fs.readFileSync(path.join(SRC_DIR, rel), 'utf8');
      const stripped = stripModalBlocks(source);
      expect(countTextInputOpenTags(stripped)).toBeGreaterThan(0);
      expect(extractScrollOpenTags(stripped).length).toBeGreaterThan(0);
      count += 1;
    }
    expect(count).toBe(3);
  });
});
