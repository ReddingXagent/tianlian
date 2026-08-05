import fs from 'fs';
import path from 'path';

/**
 * F285: 滚动容器×键盘收起交互对账守卫(F278键盘族第二弹, 移动端维度)
 *
 * 缺口: F278挡住「Modal×键盘遮挡」后, 非Modal屏幕的同族缺口无人管——
 * HomeScreen搜索TextInput+站点列表ScrollView同屏, ScrollView未声明
 * keyboardShouldPersistTaps: 用户输完搜索点站点卡片, RN默认'never'语义
 * 下第一击只收键盘不触发onPress, 必须点两次才能进详情(F285摸底撞真实存量)。
 *
 * 不变量:
 * - 同文件(排除Modal子树)存在TextInput且存在<ScrollView>/<FlatList>
 *   → 滚动容器开标签必须声明keyboardShouldPersistTaps
 * - Modal豁免: Modal是独立native层, 其内TextInput(F271/F278已治)不与
 *   背景滚动容器交互, 先剥Modal块再判定
 *
 * 提取健壮性: TextInput判定数<TextInput开标签(import残留不误报);
 * 开标签用花括号深度扫描取>(refreshControl={<RefreshControl/>}
 * 等嵌套JSX prop内的>不误断); <ScrollableView/<FlatListFoo前缀碰撞不误提取;
 * 未闭合开标签抛错(F212缺输入FAIL不静默)。
 * 接入: jest全量跑自动入门禁(本仓无CI/Makefile, 走jest测试接入, F278同惯例)。
 */

const SRC_DIR = path.join(__dirname, '..');

export interface ScrollOpenTag {
  kind: 'ScrollView' | 'FlatList';
  /** 开标签全文(含多行props与嵌套JSX prop) */
  tag: string;
}

const SCROLL_KINDS = ['ScrollView', 'FlatList'] as const;

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
      // <ModalsFoo等前缀碰撞: 原样保留继续扫(与F278 extractModalBlocks同口径)
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
 * 提取source中全部<ScrollView>/<FlatList>开标签。
 * 花括号深度扫描: prop里的JSX({<RefreshControl ... />})内部的>在depth>0,
 * 只有depth=0的>才是开标签终点——naive indexOf('>')会在嵌套prop处误断。
 */
export function extractScrollOpenTags(source: string): ScrollOpenTag[] {
  const out: ScrollOpenTag[] = [];
  let cursor = 0;
  for (;;) {
    let best = -1;
    let kind: ScrollOpenTag['kind'] | '' = '';
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
      cursor = best + 1 + kind.length;
      continue;
    }
    let depth = 0;
    let end = -1;
    for (let i = best; i < source.length; i++) {
      const ch = source[i];
      if (ch === '{') depth++;
      else if (ch === '}') depth--;
      else if (ch === '>' && depth === 0) {
        end = i;
        break;
      }
    }
    if (end === -1) {
      throw new Error(`${kind} 开标签未闭合: 找不到depth=0的>`);
    }
    out.push({ kind, tag: source.slice(best, end + 1) });
    cursor = end + 1;
  }
  return out;
}

/**
 * 单文件违规清单(空=合规):
 * 剥Modal后仍有TextInput且滚动容器缺keyboardShouldPersistTaps → 逐容器报。
 */
export function findScrollKeyboardViolations(source: string): string[] {
  const stripped = stripModalBlocks(source);
  // 数<TextInput开标签而非'TextInput'字串: import语句/注释残留不构成同屏输入
  // (VehicleScreen全部<TextInput在Modal内, 剥除后仅剩import → 应豁免)
  if (!/<TextInput[\s>/]/.test(stripped)) return [];
  const violations: string[] = [];
  const tags = extractScrollOpenTags(stripped);
  tags.forEach((t, idx) => {
    if (!t.tag.includes('keyboardShouldPersistTaps')) {
      violations.push(
        `${t.kind}#${idx + 1}: 缺keyboardShouldPersistTaps(同屏有TextInput, 默认'never'语义下第一击只收键盘不触发onPress)`,
      );
    }
  });
  return violations;
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

describe('F285提取/判定正向控制(合成样例)', () => {
  it('合规形态: TextInput+ScrollView声明keyboardShouldPersistTaps → 零违规', () => {
    const src = `
      <TextInput value={x} onChangeText={setX} />
      <ScrollView keyboardShouldPersistTaps="handled">
        <Card onPress={go} />
      </ScrollView>`;
    expect(findScrollKeyboardViolations(src)).toEqual([]);
  });

  it('缺keyboardShouldPersistTaps → 精确命中', () => {
    const src = `
      <TextInput value={x} onChangeText={setX} />
      <ScrollView style={styles.list}>
        <Card onPress={go} />
      </ScrollView>`;
    expect(findScrollKeyboardViolations(src)).toEqual([
      expect.stringContaining('缺keyboardShouldPersistTaps'),
    ]);
  });

  it('FlatList缺声明 → kind正确上报', () => {
    const src = `
      <TextInput value={x} />
      <FlatList data={rows} renderItem={render} />`;
    const v = findScrollKeyboardViolations(src);
    expect(v).toHaveLength(1);
    expect(v[0]).toContain('FlatList#1');
  });

  it('TextInput仅在Modal内+背景FlatList → 豁免零违规(F278已治Modal族)', () => {
    const src = `
      <FlatList data={rows} renderItem={render} />
      <Modal visible={v} onRequestClose={close}>
        <KeyboardAvoidingView behavior="padding">
          <TextInput value={x} />
        </KeyboardAvoidingView>
      </Modal>`;
    expect(findScrollKeyboardViolations(src)).toEqual([]);
  });

  it('有滚动容器但无TextInput → 零违规不误伤', () => {
    const src = `<FlatList data={rows} renderItem={render} />`;
    expect(findScrollKeyboardViolations(src)).toEqual([]);
  });

  it('嵌套JSX prop(refreshControl)不误断开标签, 其后的属性仍可见', () => {
    const src = `
      <TextInput value={x} />
      <ScrollView
        refreshControl={<RefreshControl refreshing={r} onRefresh={f} />}
        keyboardShouldPersistTaps="handled"
      >
        <Card />
      </ScrollView>`;
    const tags = extractScrollOpenTags(src);
    expect(tags).toHaveLength(1);
    expect(tags[0].tag).toContain('keyboardShouldPersistTaps');
    expect(findScrollKeyboardViolations(src)).toEqual([]);
  });

  it('<ScrollableView/<FlatListFoo前缀碰撞不误提取', () => {
    const src = `<ScrollableView /><FlatListFoo data={x} />`;
    expect(extractScrollOpenTags(src)).toEqual([]);
    expect(findScrollKeyboardViolations(`${src}<TextInput />`)).toEqual([]);
  });

  it('仅import残留TextInput字串(无真实开标签) → 零违规不误报', () => {
    const src = `
      import { TextInput } from 'react-native';
      <FlatList data={rows} renderItem={render} />`;
    expect(findScrollKeyboardViolations(src)).toEqual([]);
  });

  it('未闭合<ScrollView → 抛错不静默(F212)', () => {
    expect(() => extractScrollOpenTags('<ScrollView style={s}')).toThrow(
      '未闭合',
    );
  });
});

describe('F285全仓对账(src/*.tsx)', () => {
  const files = walkTsx(SRC_DIR);

  it('输入健全: 有tsx可扫且滚动容器全部可提取', () => {
    expect(files.length).toBeGreaterThan(0);
    for (const f of files) {
      const src = fs.readFileSync(f, 'utf8');
      expect(() => extractScrollOpenTags(stripModalBlocks(src))).not.toThrow();
    }
  });

  it('同屏TextInput×滚动容器全声明keyboardShouldPersistTaps', () => {
    const all: string[] = [];
    for (const f of files) {
      const rel = path.relative(SRC_DIR, f);
      for (const v of findScrollKeyboardViolations(fs.readFileSync(f, 'utf8'))) {
        all.push(`${rel}: ${v}`);
      }
    }
    expect(all).toEqual([]);
  });
});
