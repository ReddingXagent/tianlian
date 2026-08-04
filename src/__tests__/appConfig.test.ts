import fs from 'fs';
import path from 'path';
import appJson from '../../app.json';
import pkgJson from '../../package.json';

/**
 * app.json 构建配置回归守卫(移植 user-app F179/F196 同型守卫, 接入门禁: jest全量跑)
 * - platforms 限定 android+ios (F179: 裸export曾误挂web)
 * - plugins↔deps 双源对账: 每个 plugin 必有已装 dep(缺=export/prebuild直接炸);
 *   已知原生模块 dep 必声明 plugin(缺=原生配置静默缺口, F196反向)
 * - android.package === ios.bundleIdentifier: 应用唯一标识同语义双源,
 *   单侧改名 = 双平台 OTA/商店归属漂移(F224 同族, 同文件内双源形态)
 * - icon/splash/adaptiveIcon 资产文件必须存在(缺=export后程失败, 提前FAIL)
 */
describe('app.json 构建配置回归守卫', () => {
  const expo = (appJson as { expo: Record<string, unknown> }).expo;
  const deps = Object.keys(
    (pkgJson as { dependencies: Record<string, string> }).dependencies
  );
  const pluginNames = (
    (expo.plugins as (string | [string, unknown])[]) || []
  ).map((p) => (Array.isArray(p) ? p[0] : p));

  it('platforms 限定 android+ios(防误挂 web)', () => {
    expect(expo.platforms).toEqual(['android', 'ios']);
  });

  it('每个 plugin 都有对应依赖(缺则 export/prebuild 直接失败)', () => {
    for (const name of pluginNames) {
      expect(deps).toContain(name);
    }
  });

  it('原生模块依赖均声明 plugin(静默方向, F196反向)', () => {
    const nativeDeps = ['expo-secure-store', 'expo-asset'];
    for (const name of nativeDeps) {
      expect(deps).toContain(name);
      expect(pluginNames).toContain(name);
    }
  });

  it('android.package 与 ios.bundleIdentifier 一致(应用标识同语义双源)', () => {
    const android = expo.android as { package: string };
    const ios = expo.ios as { bundleIdentifier: string };
    expect(android.package).toBe(ios.bundleIdentifier);
  });

  it('icon/splash/adaptiveIcon 资产文件存在', () => {
    const root = path.resolve(__dirname, '../..');
    const assetPaths = [
      expo.icon as string,
      (expo.splash as { image: string }).image,
      (expo.android as { adaptiveIcon: { foregroundImage: string } })
        .adaptiveIcon.foregroundImage,
    ];
    for (const a of assetPaths) {
      expect(fs.existsSync(path.join(root, a))).toBe(true);
    }
  });
});
