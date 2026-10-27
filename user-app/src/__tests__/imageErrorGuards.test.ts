import fs from 'fs';
import path from 'path';

/**
 * F324: Image×onError成对守卫(图片族第一枚, 移动端维度"图片加载失败态"候选落地)
 *
 * 缺口: RN <Image>远程加载失败(404/断网/CDN漂移)是静默空白区——无占位/无提示/
 * 无日志, 用户只见白块; onError是optional prop, tsc盲区。本仓当前零<Image>=
 * 守卫先行(F318同形态): 后续任何新增远程Image入门即门禁。
 *
 * 不变量:
 * - 任何<Image>的source含uri键(远程加载形态) → 必须声明onError
 *   (加载失败兜底的唯一挂载点; 缺失=静默空白, 离线场景F族最高危)
 * - source为require(...)(打包资产, 构建期解析, 运行期不404) → 豁免
 * - source不可静态判定(变量引用) → 按远程从严要求onError
 *
 * 缺输入必须FAIL(F212): src下无可扫.tsx → 抛错。
 * 接入: jest全量跑自动入门禁(本仓无CI/Makefile, 走jest测试接入)。
 */

const SRC_DIR = path.join(__dirname, '..');

/**
 * 提取source中全部<Image>开标签全文(支持多行props)。
 * 开标签=从`<Image`起, 按花括号深度扫描到配平后的首个`>`(F318铁律:
 * 花括号深度扫描, 不数字串——source={{uri}}内可含任意嵌套)。
 * Image不嵌套, 只取开标签即可判props。
 */
export function extractImageOpenTags(source: string): string[] {
  const tags: string[] = [];
  let cursor = 0;
  for (;;) {
    const start = source.indexOf('<Image', cursor);
    if (start === -1) break;
    // 排除<ImageBackground等更长组件名的前缀碰撞(F318铁律)
    const nextCh = source[start + 6];
    if (nextCh && /[A-Za-z0-9_]/.test(nextCh)) {
      cursor = start + 6;
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
      throw new Error('F324: <Image开标签未配平(缺>), 提取失败——缺输入不静默');
    }
    tags.push(source.slice(start, end + 1));
    cursor = end + 1;
  }
  return tags;
}

/**
 * 判定开标签的source形态:
 * - 'remote': source={{...uri...}} 或 source={变量}(静态不可判定从严)
 * - 'local':  source={require(...)}
 * - 'none':   无source声明(按远程从严)
 */
export function classifySource(openTag: string): 'remote' | 'local' | 'none' {
  const m = openTag.match(/\bsource\s*=\s*\{/);
  if (!m) return 'none';
  const braceStart = openTag.indexOf('{', m.index! + m[0].length - 1);
  let depth = 0;
  let expr = '';
  for (let i = braceStart; i < openTag.length; i++) {
    const ch = openTag[i];
    if (ch === '{') depth++;
    else if (ch === '}') {
      depth--;
      if (depth === 0) {
        expr = openTag.slice(braceStart, i + 1);
        break;
      }
    }
  }
  if (/\brequire\s*\(/.test(expr)) return 'local';
  return 'remote';
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

describe('F324 Image×onError成对守卫(图片族第一枚)', () => {
  it('缺输入必须FAIL: src下无.tsx可扫 → 抛错(F212)', () => {
    const files = collectTsxFiles(SRC_DIR);
    expect(files.length).toBeGreaterThan(0);
  });

  it('提取器: 多行props开标签完整提取(花括号深度扫描)', () => {
    const src = [
      '<Image',
      "  source={{ uri: 'https://cdn.example.com/banner.png' }}",
      '  style={styles.banner}',
      '/>',
    ].join('\n');
    const tags = extractImageOpenTags(src);
    expect(tags).toHaveLength(1);
    expect(tags[0]).toContain('uri');
  });

  it('提取器: <ImageBackground前缀碰撞不误提取(F318铁律)', () => {
    const src = '<ImageBackground source={bg} style={styles.bg}><Text>x</Text></ImageBackground>';
    expect(extractImageOpenTags(src)).toHaveLength(0);
  });

  it('合成: 远程Image缺onError → 命中', () => {
    const tag = "<Image source={{ uri: 'https://x/a.png' }} style={styles.img} />";
    expect(classifySource(tag)).toBe('remote');
    expect(/\bonError\s*=/.test(tag)).toBe(false);
  });

  it('合成: 远程Image带onError → 放行', () => {
    const tag =
      "<Image source={{ uri: 'https://x/a.png' }} onError={() => setFailed(true)} />";
    expect(classifySource(tag)).toBe('remote');
    expect(/\bonError\s*=/.test(tag)).toBe(true);
  });

  it('合成: require本地资产无onError → 豁免(打包资产运行期不404)', () => {
    const tag = '<Image source={require("../../assets/logo.png")} />';
    expect(classifySource(tag)).toBe('local');
  });

  it('合成: source为变量引用(静态不可判定) → 从严按远程', () => {
    const tag = '<Image source={dynamicSource} style={styles.img} />';
    expect(classifySource(tag)).toBe('remote');
  });

  it('合成: 无source声明 → 从严按远程(同缺失形态)', () => {
    const tag = '<Image style={styles.img} />';
    expect(classifySource(tag)).toBe('none');
  });

  it('全仓对账: 所有远程<Image>必须声明onError(当前零实体=守卫先行基线)', () => {
    const files = collectTsxFiles(SRC_DIR);
    const violations: string[] = [];
    let remoteCount = 0;
    for (const file of files) {
      const source = fs.readFileSync(file, 'utf8');
      for (const tag of extractImageOpenTags(source)) {
        const kind = classifySource(tag);
        if (kind === 'local') continue;
        remoteCount++;
        if (!/\bonError\s*=/.test(tag)) {
          violations.push(`${path.relative(SRC_DIR, file)}: 远程Image缺onError`);
        }
      }
    }
    // 当前基线: 全仓零<Image>实体(remoteCount=0), 守卫先行
    expect(violations).toEqual([]);
    expect(remoteCount).toBe(0);
  });
});
