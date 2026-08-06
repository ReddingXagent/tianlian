import appJson from '../../app.json';

/**
 * app.json 配置回归防护(接入门禁: jest全量跑)
 * - expo-camera 权限声明: 缺 NSCameraUsageDescription/Android CAMERA 权限,
 *   真机扫码权限请求直接失败(F196教训: 装了expo-camera却在plugins漏配)
 * - platforms 限定 android+ios(F179: 裸export曾误挂web)
 * - userInterfaceStyle 钉死 light(F400: 全仓零深色主题分支, 漂移automatic即原生容器静默深色分裂)
 * - orientation 钉死 portrait(F407: 全仓零响应式分支, 漂移default即横屏布局静默崩坏)
 */
describe('app.json 配置回归防护', () => {
  const expo = (appJson as { expo: Record<string, unknown> }).expo;

  it('plugins 含 expo-camera 且配置了中文权限文案', () => {
    const plugins = expo.plugins as (string | [string, Record<string, unknown>])[];
    const camera = plugins.find(
      (p) => Array.isArray(p) && p[0] === 'expo-camera'
    ) as [string, Record<string, unknown>] | undefined;
    expect(camera).toBeDefined();
    expect(typeof camera?.[1].cameraPermission).toBe('string');
    expect((camera?.[1].cameraPermission as string).length).toBeGreaterThan(0);
  });

  it('plugins 保留 expo-secure-store(token存储依赖)', () => {
    const plugins = expo.plugins as (string | [string, unknown])[];
    expect(
      plugins.some((p) => (Array.isArray(p) ? p[0] : p) === 'expo-secure-store')
    ).toBe(true);
  });

  it('platforms 限定 android+ios', () => {
    expect(expo.platforms).toEqual(['android', 'ios']);
  });

  it('userInterfaceStyle 钉死 light(全仓零深色主题分支, 漂移automatic即静默分裂)', () => {
    // 全仓366处硬编码色值、零 useColorScheme/Appearance 主题分支: 无深色主题实现。
    // 漂移 "automatic" 或删键(Expo缺省即automatic)→系统深色模式传入键盘/弹窗/状态栏
    // 等原生容器而RN内容仍浅色→外观静默分裂, tsc盲区(F25/F33决策门禁同族)。
    expect(expo.userInterfaceStyle).toBe('light');
  });

  it('orientation 钉死 portrait(全仓零响应式分支, 漂移default即横屏静默崩坏)', () => {
    // 全仓零 useWindowDimensions/Dimensions.get 使用点: 布局全静态零响应式分支。
    // 漂移 "default"/"landscape" 或删键(Expo缺省即default=全方向)→横屏时静态布局
    // 静默崩坏(元素错位/触控目标偏移), 构建全过运行时才暴露, tsc盲区(F400同族门禁)。
    expect(expo.orientation).toBe('portrait');
  });
});
