import appJson from '../../app.json';

/**
 * app.json 配置回归防护(接入门禁: jest全量跑)
 * - expo-camera 权限声明: 缺 NSCameraUsageDescription/Android CAMERA 权限,
 *   真机扫码权限请求直接失败(F196教训: 装了expo-camera却在plugins漏配)
 * - platforms 限定 android+ios+web(F179: 裸export曾误挂web; 2026-09-24 开放 web 调试通道, web 为有意保留)
 * - userInterfaceStyle 钉死 automatic(F2783: 深色模式主题分支已全仓落地, 漂回light即原生容器拒绝深色)
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

  it('platforms 限定 android+ios+web(web 为调试通道, 2026-09-24 有意开启)', () => {
    expect(expo.platforms).toEqual(['android', 'ios', 'web']);
  });

  it('userInterfaceStyle 钉死 automatic(深色模式主题分支已全仓落地, 漂回light即拒绝深色)', () => {
    // F2783 Phase 1-4: useTheme 全仓覆盖(screen+component), 中性色/主蓝/语义色族均已语义化。
    // 漂移 "light" → 系统深色模式下原生容器(键盘/弹窗/状态栏)强制浅色,
    // 深色主题被容器层拒绝, F2783 适配失效(F400 反向门禁)。
    expect(expo.userInterfaceStyle).toBe('automatic');
  });

  it('orientation 钉死 portrait(全仓零响应式分支, 漂移default即横屏静默崩坏)', () => {
    // 全仓零 useWindowDimensions/Dimensions.get 使用点: 布局全静态零响应式分支。
    // 漂移 "default"/"landscape" 或删键(Expo缺省即default=全方向)→横屏时静态布局
    // 静默崩坏(元素错位/触控目标偏移), 构建全过运行时才暴露, tsc盲区(F400同族门禁)。
    expect(expo.orientation).toBe('portrait');
  });
});
