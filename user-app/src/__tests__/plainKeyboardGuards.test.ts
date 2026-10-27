import fs from 'fs';
import path from 'path';

/**
 * F293: screen级孤立TextInput×KAV对账守卫(F278键盘族第三弹, 移动端维度)
 *
 * 缺口: F278挡住「Modal层×键盘遮挡」、F285挡住「非Modal同屏滚动容器层×
 * 键盘收起交互」后, 键盘族还剩第三层无人管——普通容器层(View/Screen根)
 * 的TextInput: 既不在Modal独立native层内, 也不在任何滚动容器内, 软键盘
 * 弹出时既无KAV抬升遮挡输入框, 又无滚动逃逸通道, 是键盘遮挡三重缺陷
 * (遮挡+无抬升+无收起通道)的最高密度形态。本仓摸底四门全绿后逐文件对账
 * 「含TextInput的tsx」×「KAV包裹」零命中——LoginScreen的TextInput在
 * ScrollView块内(F285层豁免, 其KAV属冗余但无害), Home/Scan的TextInput
 * 在ScrollView块内(F285层豁免)或顶部豁免区, Vehicle全在Modal内
 * (F278层豁免)——守卫先行非缺陷(F258/F284型)。
 *
 * 不变量:
 * - 剥Modal块(F278层豁免)后, 再剥ScrollView/FlatList块(F285层豁免:
 *   滚动容器内输入有滚动逃逸通道, taps交互由F285守卫治理),
 *   剩余<TextInput开标签>0的文件必须存在<KeyboardAvoidingView开标签,
 *   唯顶部工具栏层豁免: 全部普通层TextInput均位于首个滚动容器开标签之前
 *   (顶部搜索栏/工具栏形态——软键盘遮挡屏幕下半部, 顶部输入仍可见,
 *   F271文档化人肉豁免的自动化; Home搜索框即此形态)
 *
 * 提取健壮性: 开标签判定数开标签不数字串(import残留不误报); 开标签终点
 * 花括号深度扫描(嵌套JSX prop内的>不误断); <ModalsFoo/<ScrollableView/
 * <TextInputFoo/<KeyboardAvoidingViewFoo前缀碰撞不误提取; 自闭合滚动容器
 * (无children)不构成豁免域; Modal/滚动块未闭合抛错(F212缺输入FAIL不静默)。
 * 接入: jest全量跑自动入门禁(本仓无CI/Makefile, 走jest测试接入, F278/F285同惯例)。
 */

const SRC_DIR = path.join(__dirname, '..');

export interface BlockSpan {
  kind: 'ScrollView' | 'FlatList';
  /** 块起点(开标签<) */
  start: number;
  /** 块终点(闭合标签>后一位; 自闭合=开标签>后一位) */
  end: number;
}

const SCROLL_KINDS = ['ScrollView', 'FlatList'] as const;

/** 剥除全部<Modal>...</Modal>块(Modal独立native层, F278层已治其内键盘遮挡) */
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
      // <ModalsFoo等前缀碰撞: 原样保留继续扫(F278/F285同口径)
      out += source.slice(cursor, start + 6);
      cursor = start + 6;
      continue;
    }
    const closeIdx = source.indexOf('</Modal>', start);
    if (closeIdx === -1) {
      throw new Error('Modal 块未闭合: 有<Modal但缺</Modal>');
    }
    out += source.slice(cursor, start);
    cursor = closeIdx + '</Modal>'.length;
  }
  return out;
}

/**
 * 提取source中全部<ScrollView>/<FlatList>块的span。
 * 开标签终点花括号深度扫描(嵌套JSX prop内的>不误断); 自闭合(/> )无children,
 * span仅覆盖开标签本身, 不构成任何后续位置的豁免域; 非自闭合找</Kind>闭合,
 * 未闭合抛错(F212缺输入FAIL不静默)。
 */
export function extractScrollBlockSpans(source: string): BlockSpan[] {
  const out: BlockSpan[] = [];
  let cursor = 0;
  for (;;) {
    let best = -1;
    let kind: BlockSpan['kind'] | '' = '';
    for (const k of SCROLL_KINDS) {
      const idx = source.indexOf(`<${k}`, cursor);
      if (idx !== -1 && (best === -1 || idx < best)) {
        best = idx;
        kind = k;
      }
    }
    if (best === -1 || kind === '') break;
    const after = source[best + 1 + kind.length];
    if (after !== undefined && !/[\s>/]/.test(after)) {
      // <ScrollableView等前缀碰撞: 跳过继续
      cursor = best + 1 + kind.length;
      continue;
    }
    let depth = 0;
    let tagEnd = -1;
    for (let i = best; i < source.length; i++) {
      const ch = source[i];
      if (ch === '{') depth++;
      else if (ch === '}') depth--;
      else if (ch === '>' && depth === 0) {
        tagEnd = i;
        break;
      }
    }
    if (tagEnd === -1) {
      throw new Error(`${kind} 开标签未闭合: 找不到depth=0的>`);
    }
    if (source[tagEnd - 1] === '/') {
      // 自闭合: 无children, span仅覆盖开标签
      out.push({ kind, start: best, end: tagEnd + 1 });
      cursor = tagEnd + 1;
      continue;
    }
    const closeIdx = source.indexOf(`</${kind}>`, tagEnd);
    if (closeIdx === -1) {
      throw new Error(`${kind} 块未闭合: 有开标签但缺</${kind}>`);
    }
    out.push({ kind, start: best, end: closeIdx + `</${kind}>`.length });
    cursor = closeIdx + `</${kind}>`.length;
  }
  return out;
}

/** 数<TextInput开标签位置(开标签边界判定, import残留/前缀碰撞不误报) */
export function findTextInputPositions(source: string): number[] {
  const positions: number[] = [];
  let cursor = 0;
  for (;;) {
    const idx = source.indexOf('<TextInput', cursor);
    if (idx === -1) break;
    const after = source[idx + 10];
    if (after === undefined || /[\s>/]/.test(after)) {
      positions.push(idx);
    }
    cursor = idx + 10;
  }
  return positions;
}

/** 是否存在<KeyboardAvoidingView开标签(边界判定, 前缀碰撞不误认) */
export function hasKeyboardAvoidingView(source: string): boolean {
  let cursor = 0;
  for (;;) {
    const idx = source.indexOf('<KeyboardAvoidingView', cursor);
    if (idx === -1) return false;
    const after = source[idx + 21];
    if (after === undefined || /[\s>/]/.test(after)) return true;
    cursor = idx + 21;
  }
}

/**
 * 单文件违规清单(空=合规):
 * 剥Modal块与滚动块后仍有<TextInput开标签但无KeyboardAvoidingView → 报一条。
 */
export function findPlainKeyboardViolations(source: string): string[] {
  const stripped = stripModalBlocks(source);
  const spans = extractScrollBlockSpans(stripped);
  const positions = findTextInputPositions(stripped).filter(
    (pos) => !spans.some((s) => pos >= s.start && pos < s.end),
  );
  if (positions.length === 0) return [];
  // 顶部工具栏层豁免: 首个滚动容器开标签之前的输入(顶部搜索栏/工具栏形态,
  // 软键盘遮挡屏幕下半部但顶部输入仍可见); 无滚动容器时豁免不生效, 全部暴露
  const exposed =
    spans.length === 0
      ? positions
      : positions.filter((pos) => {
          const firstScrollStart = Math.min(...spans.map((s) => s.start));
          return pos > firstScrollStart;
        });
  if (exposed.length === 0) return [];
  if (hasKeyboardAvoidingView(stripped)) return [];
  return [
    `普通容器层TextInput×${exposed.length}: 无KeyboardAvoidingView包裹(既无Modal独立层又无滚动逃逸通道又非顶部工具栏层, 软键盘直接遮挡且无收起通道)`,
  ];
}

function walkTsx(dir: string): string[] {
  const out: string[] = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === '__tests__') continue;
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...walkTsx(full));
    else if (entry.isFile() && entry.name.endsWith('.tsx')) out.push(full);
  }
  return out;
}

describe('F293提取/判定正向控制(合成样例)', () => {
  it('合规形态: 普通容器层TextInput+KAV包裹 → 零违规', () => {
    const src = `
      <KeyboardAvoidingView behavior="padding">
        <View style={styles.form}>
          <TextInput value={x} onChangeText={setX} />
        </View>
      </KeyboardAvoidingView>`;
    expect(findPlainKeyboardViolations(src)).toEqual([]);
  });

  it('普通容器层TextInput无KAV → 精确命中', () => {
    const src = `
      <View style={styles.form}>
        <TextInput value={x} onChangeText={setX} />
      </View>`;
    const v = findPlainKeyboardViolations(src);
    expect(v).toHaveLength(1);
    expect(v[0]).toContain('无KeyboardAvoidingView包裹');
    expect(v[0]).toContain('TextInput×1');
  });

  it('TextInput仅在Modal内(无KAV) → F278层豁免零违规', () => {
    const src = `
      <Modal visible={v} onRequestClose={close}>
        <TextInput value={x} onChangeText={setX} />
      </Modal>`;
    expect(findPlainKeyboardViolations(src)).toEqual([]);
  });

  it('TextInput在ScrollView块内(无KAV) → F285层豁免零违规', () => {
    const src = `
      <ScrollView keyboardShouldPersistTaps="handled">
        <View><TextInput value={x} onChangeText={setX} /></View>
      </ScrollView>`;
    expect(findPlainKeyboardViolations(src)).toEqual([]);
  });

  it('TextInput在FlatList块内(无KAV) → F285层豁免零违规', () => {
    const src = `
      <FlatList
        data={rows}
        renderItem={({ item }) => <TextInput value={item.v} />}
      />`;
    expect(findPlainKeyboardViolations(src)).toEqual([]);
  });

  it('自闭合FlatList不构成豁免域, 外部裸TextInput无KAV仍命中', () => {
    const src = `
      <FlatList data={rows} renderItem={render} />
      <View><TextInput value={x} /></View>`;
    const v = findPlainKeyboardViolations(src);
    expect(v).toHaveLength(1);
    expect(v[0]).toContain('TextInput×1');
  });

  it('<KeyboardAvoidingViewFoo前缀碰撞不误认为KAV → 仍命中', () => {
    const src = `
      <KeyboardAvoidingViewFoo style={x}>
        <TextInput value={x} />
      </KeyboardAvoidingViewFoo>`;
    const v = findPlainKeyboardViolations(src);
    expect(v).toHaveLength(1);
  });

  it('<TextInputFoo前缀碰撞不计入输入 → 零违规不误伤', () => {
    const src = `<View><TextInputFoo value={x} /></View>`;
    expect(findPlainKeyboardViolations(src)).toEqual([]);
  });

  it('import残留不构成输入判定(数开标签不数字串)', () => {
    const src = `
      import { TextInput } from 'react-native';
      <View><Text>no input here</Text></View>`;
    expect(findPlainKeyboardViolations(src)).toEqual([]);
  });

  it('顶部工具栏层豁免: TextInput在首个滚动容器开标签之前(Home搜索框形态) → 零违规', () => {
    const src = `
      <View style={styles.container}>
        <View style={styles.searchRow}>
          <TextInput value={q} onChangeText={setQ} placeholder="搜索" />
        </View>
        <ScrollView keyboardShouldPersistTaps="handled">
          <View><Text>list</Text></View>
        </ScrollView>
      </View>`;
    expect(findPlainKeyboardViolations(src)).toEqual([]);
  });

  it('顶部豁免有界: 首个滚动容器之后再出现裸TextInput无KAV → 仍命中', () => {
    const src = `
      <View style={styles.container}>
        <View><TextInput value={q} onChangeText={setQ} /></View>
        <ScrollView keyboardShouldPersistTaps="handled">
          <View><Text>list</Text></View>
        </ScrollView>
        <View style={styles.footer}><TextInput value={note} /></View>
      </View>`;
    const v = findPlainKeyboardViolations(src);
    expect(v).toHaveLength(1);
    expect(v[0]).toContain('TextInput×1');
  });

  it('ScrollView块未闭合抛错(F212缺输入FAIL不静默)', () => {
    const src = `<ScrollView keyboardShouldPersistTaps="handled"><TextInput value={x} />`;
    expect(() => findPlainKeyboardViolations(src)).toThrow('ScrollView 块未闭合');
  });

  it('Modal块未闭合抛错(F212缺输入FAIL不静默)', () => {
    const src = `<Modal visible={v}><TextInput value={x} /></Modal`;
    expect(() => findPlainKeyboardViolations(src)).toThrow('Modal 块未闭合');
  });
});

describe('F293全仓对账(screen级孤立TextInput×KAV)', () => {
  const files = walkTsx(SRC_DIR);

  it('输入健全: 全仓tsx扫描面非空且覆盖全部已知输入屏', () => {
    expect(files.length).toBeGreaterThanOrEqual(4);
    const withInput = files.filter((f) =>
      /<TextInput[\s>/]/.test(fs.readFileSync(f, 'utf8')),
    );
    // Home/Login/Scan/Vehicle四屏均含TextInput开标签
    expect(withInput.length).toBeGreaterThanOrEqual(4);
  });

  it('双不变量: 剥Modal+滚动块后的TextInput全部有KAV层兜底(零违规)', () => {
    const all: string[] = [];
    files.forEach((f) => {
      const v = findPlainKeyboardViolations(fs.readFileSync(f, 'utf8'));
      v.forEach((msg) => all.push(`${path.relative(SRC_DIR, f)}: ${msg}`));
    });
    expect(all).toEqual([]);
  });
});
