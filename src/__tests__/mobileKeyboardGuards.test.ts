import fs from 'fs';
import path from 'path';

/**
 * F278: Modal×键盘遮挡/Android返回键双向对账守卫(F271例行对账自动化)
 *
 * 缺口: F271在VehicleScreen落地"底部弹出表单KAV补全"并固化例行对账
 * 「含TextInput的Modal/弹层」×「KAV包裹」——但例行对账靠人肉grep,
 * 新增Modal时无门禁拦截, 复发只是时间问题。
 *
 * 不变量:
 * - 任何<Modal>块含TextInput → 必须含KeyboardAvoidingView
 *   (聚焦输入项时软键盘覆盖输入框/按钮, 底部弹出形态最高危F271)
 * - 任何<Modal>必须声明onRequestClose
 *   (Android硬件返回键关闭Modal的唯一通道, 类型上optional但运行时必需,
 *    缺失=Android用户按返回键无反应, tsc盲区)
 *
 * 缺输入必须FAIL(F212): src下无.tsx可扫/有</Modal>却提取失败 → 抛错。
 * 接入: jest全量跑自动入门禁(本仓无CI/Makefile, 走jest测试接入)。
 */

const SRC_DIR = path.join(__dirname, '..');

export interface ModalBlock {
  /** 开标签全文(<Modal ... >, 含多行props) */
  openTag: string;
  /** 开标签后到</Modal>的块体 */
  body: string;
}

/**
 * 提取source中全部<Modal>块。Modal不嵌套, 块体=首个</Modal>之前。
 * 有<Modal却无配对</Modal> → 抛错(F212缺输入FAIL, 不静默跳过)。
 */
export function extractModalBlocks(source: string): ModalBlock[] {
  const blocks: ModalBlock[] = [];
  let cursor = 0;
  for (;;) {
    const start = source.indexOf('<Modal', cursor);
    if (start === -1) break;
    // <Modals...等前缀碰撞排除: <Modal后必须是空白/>/换行
    const nextCh = source[start + 6];
    if (nextCh !== undefined && !/[\s>/]/.test(nextCh)) {
      cursor = start + 6;
      continue;
    }
    const closeIdx = source.indexOf('</Modal>', start);
    if (closeIdx === -1) {
      throw new Error('Modal 块未闭合: 有<Modal但缺</Modal>');
    }
    const tagEnd = source.indexOf('>', start);
    if (tagEnd === -1 || tagEnd > closeIdx) {
      throw new Error('Modal 开标签未闭合: >出现在</Modal>之后');
    }
    blocks.push({
      openTag: source.slice(start, tagEnd + 1),
      body: source.slice(tagEnd + 1, closeIdx),
    });
    cursor = closeIdx + '</Modal>'.length;
  }
  return blocks;
}

/**
 * 单文件违规清单(空=合规):
 * - TextInput无KAV / 缺onRequestClose
 */
export function findModalViolations(source: string): string[] {
  const violations: string[] = [];
  const blocks = extractModalBlocks(source);
  blocks.forEach((block, idx) => {
    const label = `Modal#${idx + 1}`;
    if (block.body.includes('TextInput') && !block.body.includes('KeyboardAvoidingView')) {
      violations.push(`${label}: 含TextInput但无KeyboardAvoidingView包裹(软键盘遮挡, F271形态)`);
    }
    if (!block.openTag.includes('onRequestClose')) {
      violations.push(`${label}: 缺onRequestClose(Android硬件返回键无法关闭)`);
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

describe('F278提取/判定正向控制(合成样例)', () => {
  it('合规形态: Modal+TextInput+KAV+onRequestClose → 零违规', () => {
    const src = `
      <Modal visible={v} transparent onRequestClose={close}>
        <KeyboardAvoidingView behavior="padding">
          <TextInput value={x} />
        </KeyboardAvoidingView>
      </Modal>`;
    expect(findModalViolations(src)).toEqual([]);
  });

  it('TextInput无KAV → 精确命中遮挡违规', () => {
    const src = `
      <Modal visible={v} onRequestClose={close}>
        <TextInput value={x} />
      </Modal>`;
    expect(findModalViolations(src)).toEqual([
      expect.stringContaining('无KeyboardAvoidingView'),
    ]);
  });

  it('缺onRequestClose → 精确命中Android返回键违规', () => {
    const src = `
      <Modal visible={v}>
        <View />
      </Modal>`;
    expect(findModalViolations(src)).toEqual([
      expect.stringContaining('缺onRequestClose'),
    ]);
  });

  it('双违规并存 → 两条全报', () => {
    const src = `
      <Modal visible={v}>
        <TextInput value={x} />
      </Modal>`;
    expect(findModalViolations(src)).toHaveLength(2);
  });

  it('无Modal文件 → 零违规不误伤', () => {
    expect(findModalViolations('<View><TextInput /></View>')).toEqual([]);
  });

  it('未闭合Modal → 抛错不静默(F212)', () => {
    expect(() => extractModalBlocks('<Modal visible={v}><TextInput />')).toThrow(
      '未闭合',
    );
  });

  it('<Modals前缀碰撞不误提取', () => {
    expect(extractModalBlocks('<ModalsFoo bar={1} />')).toEqual([]);
  });
});

describe('F278全仓对账(src/*.tsx)', () => {
  const files = walkTsx(SRC_DIR);

  it('输入健全: 有tsx可扫且含</Modal>标记的文件全部可提取', () => {
    expect(files.length).toBeGreaterThan(0);
    for (const f of files) {
      const src = fs.readFileSync(f, 'utf8');
      if (src.includes('</Modal>')) {
        expect(() => extractModalBlocks(src)).not.toThrow();
        expect(extractModalBlocks(src).length).toBeGreaterThan(0);
      }
    }
  });

  it('含TextInput的Modal全有KAV包裹 + 全Modal声明onRequestClose', () => {
    const all: string[] = [];
    for (const f of files) {
      const rel = path.relative(SRC_DIR, f);
      for (const v of findModalViolations(fs.readFileSync(f, 'utf8'))) {
        all.push(`${rel}: ${v}`);
      }
    }
    expect(all).toEqual([]);
  });
});
