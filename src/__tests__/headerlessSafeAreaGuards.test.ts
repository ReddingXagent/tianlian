import fs from 'fs';
import path from 'path';

/**
 * F299: headerShown:false导航器×Screen根SafeArea对账守卫(移动端维度, 键盘族外缺陷形态)
 *
 * 缺口: 全仓SafeArea摸底撞真实存量——App.tsx挂了SafeAreaProvider, 但
 * provider只是"提供insets数据", 不消费=零防护。AuthStack.Navigator
 * screenOptions={{ headerShown: false }}下LoginScreen根是裸KAV:
 * 无原生header兜顶, iOS刘海屏状态栏直接叠在登录表单上方(顶部安全区
 * 无人消费); 全仓12个screen文件SafeAreaView/useSafeAreaInsets引用数=0。
 * Tab屏有原生header兜顶、详情屏走默认header, 唯headerShown:false导航器
 * 直挂的screen是安全区盲区——tsc盲区(SafeAreaView类型optional存在,
 * 不用不报错), 静态零信号, 只有真机刘海屏暴露。
 *
 * 不变量:
 * - AppNavigator.tsx中screenOptions含headerShown:false的<X.Navigator>块内,
 *   全部<X.Screen component={Y}>的Y解析到源文件后, 该文件必须消费安全区:
 *   import { SafeAreaView } from 'react-native-safe-area-context'且存在
 *   <SafeAreaView开标签, 或调用useSafeAreaInsets(手动padding形态)。
 * - import来源必须是react-native-safe-area-context: RN内置SafeAreaView
 *   仅iOS且已弃用, Android零防护, 属错误来源形态必拦。
 *
 * 豁免: 块内component为局部函数(无import解析)=嵌套导航器形态, 其内层
 * 导航器各自独立入对账(AuthNavigator/MainWithDetail即此形态), 不重复断言。
 *
 * 提取健壮性: Navigator开标签终点花括号深度扫描(screenOptions嵌套{{}}内
 * 的>不误断开标签); <X.NavigatorFoo前缀碰撞不误提取; 块未闭合抛错;
 * import解析到的screen文件不存在抛错(F212缺输入FAIL不静默);
 * <SafeAreaView前缀碰撞(<SafeAreaViewsFoo)不误判消费。
 * 接入: jest全量跑自动入门禁(本仓无CI/Makefile, 走jest测试接入, F278族同惯例)。
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

/** 提取source中全部headerShown:false的Navigator块文本(screenOptions级) */
export function extractHeaderlessNavigatorBlocks(source: string): string[] {
  const blocks: string[] = [];
  const re = /<([A-Za-z_$][\w$]*)\.Navigator(?=[\s>/])/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(source)) !== null) {
    const navName = m[1];
    const tagEnd = openTagEnd(source, m.index);
    const openTag = source.slice(m.index, tagEnd);
    const closeTag = `</${navName}.Navigator>`;
    const closeIdx = source.indexOf(closeTag, tagEnd);
    if (closeIdx === -1) {
      throw new Error(`${navName}.Navigator 块未闭合: 有开标签缺${closeTag}`);
    }
    if (/headerShown:\s*false/.test(openTag)) {
      blocks.push(source.slice(m.index, closeIdx + closeTag.length));
    }
  }
  return blocks;
}

/** 提取Navigator块内全部component={X}标识符 */
export function extractComponentIds(navigatorBlock: string): string[] {
  const ids: string[] = [];
  const re = /component=\{\s*([A-Za-z_$][\w$]*)\s*\}/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(navigatorBlock)) !== null) {
    ids.push(m[1]);
  }
  return ids;
}

/** 解析import: 标识符 → 相对源路径(default import形态); 无import=局部函数返回null */
export function tryResolveImportPath(navigatorSource: string, id: string): string | null {
  const re = new RegExp(`import\\s+${id}\\s+from\\s+['"]([^'"]+)['"]`);
  const m = re.exec(navigatorSource);
  return m ? m[1] : null;
}

/** 判定screen源文件是否消费安全区(SafeAreaView开标签须来自safe-area-context, 或useSafeAreaInsets) */
export function consumesSafeArea(screenSource: string): boolean {
  const hasTag = /<SafeAreaView(?=[\s>/])/.test(screenSource);
  const hasInsetsHook = /\buseSafeAreaInsets\s*\(/.test(screenSource);
  if (!hasTag && !hasInsetsHook) return false;
  if (hasInsetsHook) {
    return /import\s+\{[^}]*useSafeAreaInsets[^}]*\}\s+from\s+['"]react-native-safe-area-context['"]/.test(
      screenSource,
    );
  }
  // SafeAreaView形态: import来源必须是react-native-safe-area-context(RN内置版仅iOS且已弃用)
  const importRe = /import\s+\{([^}]*)\}\s+from\s+['"]([^'"]+)['"]/g;
  let m: RegExpExecArray | null;
  while ((m = importRe.exec(screenSource)) !== null) {
    const names = m[1].split(',').map((s) => s.trim());
    if (names.includes('SafeAreaView')) {
      return m[2] === 'react-native-safe-area-context';
    }
  }
  return false;
}

// ---------- 合成控制 ----------

describe('F299 提取健壮性(合成样例)', () => {
  test('花括号深度扫描: screenOptions嵌套{{}}内>不误断开标签', () => {
    const src =
      '<A.Navigator screenOptions={{ headerShown: false, x: a > b ? 1 : 0 }}>\n' +
      '<A.Screen name="L" component={LoginScreen} />\n' +
      '</A.Navigator>';
    const blocks = extractHeaderlessNavigatorBlocks(src);
    expect(blocks).toHaveLength(1);
    expect(extractComponentIds(blocks[0])).toEqual(['LoginScreen']);
  });

  test('headerShown:true导航器不入块', () => {
    const src =
      '<A.Navigator screenOptions={{ headerShown: true }}>\n' +
      '<A.Screen name="L" component={LoginScreen} />\n' +
      '</A.Navigator>';
    expect(extractHeaderlessNavigatorBlocks(src)).toHaveLength(0);
  });

  test('Navigator前缀碰撞不误提取(<A.NavigatorFoo)', () => {
    const src = '<A.NavigatorFoo screenOptions={{ headerShown: false }}></A.NavigatorFoo>';
    expect(extractHeaderlessNavigatorBlocks(src)).toHaveLength(0);
  });

  test('Navigator块未闭合抛错(F212缺输入FAIL)', () => {
    expect(() =>
      extractHeaderlessNavigatorBlocks(
        '<A.Navigator screenOptions={{ headerShown: false }}><A.Screen component={X} />',
      ),
    ).toThrow(/未闭合/);
  });

  test('component标识符无import解析返回null(嵌套导航器豁免形态)', () => {
    expect(tryResolveImportPath('const x = 1;', 'LoginScreen')).toBeNull();
  });

  test('SafeAreaView消费判定: 正确来源过/错误来源(RN内置)拦/前缀碰撞不误判', () => {
    const ok =
      "import { SafeAreaView } from 'react-native-safe-area-context';\n" +
      'const A = () => <SafeAreaView style={s}><View /></SafeAreaView>;';
    expect(consumesSafeArea(ok)).toBe(true);

    const wrongSource =
      "import { SafeAreaView } from 'react-native';\n" +
      'const A = () => <SafeAreaView />;';
    expect(consumesSafeArea(wrongSource)).toBe(false);

    const prefixCollision =
      "import { SafeAreaView } from 'react-native-safe-area-context';\n" +
      'const A = () => <SafeAreaViewsFoo />;';
    expect(consumesSafeArea(prefixCollision)).toBe(false);

    const insets =
      "import { useSafeAreaInsets } from 'react-native-safe-area-context';\n" +
      'const A = () => { const i = useSafeAreaInsets(); return null; };';
    expect(consumesSafeArea(insets)).toBe(true);

    expect(consumesSafeArea('const A = () => <View />;')).toBe(false);
  });
});

// ---------- 全仓对账 ----------

describe('F299 全仓对账: headerShown:false导航器×Screen根SafeArea', () => {
  const navPath = path.join(SRC_DIR, 'navigation', 'AppNavigator.tsx');
  const navSource = fs.readFileSync(navPath, 'utf-8');
  const blocks = extractHeaderlessNavigatorBlocks(navSource);
  const pairs: { id: string; relPath: string }[] = [];
  for (const block of blocks) {
    for (const id of extractComponentIds(block)) {
      const relPath = tryResolveImportPath(navSource, id);
      if (relPath === null) continue; // 局部函数=嵌套导航器, 其内层导航器独立入对账
      pairs.push({ id, relPath });
    }
  }

  test('对账清单非空且含已知screen(提取活性, 防豁免吞掉全部断言)', () => {
    expect(pairs.length).toBeGreaterThan(0);
    expect(pairs.map((p) => p.id)).toContain('LoginScreen');
  });

  test.each(pairs.map((p) => [`${p.id}(${p.relPath})`, p] as const))(
    '%s 必须消费安全区(SafeAreaView@safe-area-context或useSafeAreaInsets)',
    (_label, pair) => {
      // 相对路径以AppNavigator.tsx所在目录为基准(navigation/ → ../screens/)
      const filePath = path.resolve(path.dirname(navPath), `${pair.relPath}.tsx`);
      if (!fs.existsSync(filePath)) {
        throw new Error(`screen源文件不存在: ${filePath}(缺输入FAIL不静默)`);
      }
      const screenSource = fs.readFileSync(filePath, 'utf-8');
      expect(consumesSafeArea(screenSource)).toBe(true);
    },
  );
});
