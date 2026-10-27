# mobile npm audit triage 报告（卡 3f858a71 → 卡 46871d16 续篇）

日期：2026-09-01 · 范围：`mobile/` 全量依赖（`npm audit`）· 禁 force，未执行 `npm audit fix --force`

## 1. 结论

- 卡 3f858a71 终态：37 漏洞（工具链链占 35）
- **本卡（Expo 50→57 / RN 0.73→0.86.3 大迁移）后：`npm audit` → found 0 vulnerabilities**
- 迁移路径：50→51→52→53→54→55→56→57，每个大版本 `npx expo install --fix` + `tsc --noEmit` exit 0 后单独 commit
- `npx tsc --noEmit` exit 0 · `npx expo-doctor` 20/21 passed（唯一 fail 见 §4）
- `src/config/env.ts` 三环境 baseURL 零改动（`git diff HEAD -- src/` 为空），卡 808e895d 设计完整保留

## 2. 迁移过程（每个大版本一个 commit，全部带卡号 46871d16）

| SDK | RN | React | TS | audit | 关键动作 |
|---|---|---|---|---|---|
| 51.0.39 | 0.74.5 | 18.2.0 | 5.3 | 38→25 途中 | install --fix |
| 52.0.49 | 0.76.9 | 18.3.1 | 5.3 | 25 | 对齐 9 原生模块 |
| 53.0.27 | 0.79.6 | 19.0.0 | 5.8.3 | — | **前置升级 @types/react@19 解 ERESOLVE**（peerOptional ^19 vs 18.3.31） |
| 54.0.37 | 0.81.5 | 19.1.0 | 5.8.3 | 18 | @types/react@~19.1 再解 ERESOLVE（virtualized-lists 要 ^19.1.0） |
| 55.0.31 | 0.83.10 | 19.2.0 | 5.9 | 11 | 对齐 8 模块 |
| 56.0.21 | 0.85.3 | 19.2.3 | **6.0.3** | 12 | app.config.js 加 `expo-status-bar` 插件；tsconfig 加 `ignoreDeprecations:"6.0"`（baseUrl 弃用过渡） |
| 57.0.18 | 0.86.3 | 19.2.3 | 6.0.3 | 13→**0** | 见 §3 |

版本对齐细节：SDK 52 时 `expo install --fix` 曾静默不生效（npm pkg set 后未实装 expo 本体），用 `npm install expo@~52.0.0` 强制实装后 fix 才对齐——后续每步直接 npm install 实装。

## 3. SDK 57 收尾动作（audit 13→0）

| 动作 | 原因 |
|---|---|
| `splash` 字段移除，改 `expo-splash-screen` config plugin | SDK 57 schema 禁止顶层 splash |
| `android.usesClearTextTraffic` 移除，改 `expo-build-properties` 插件 `usesCleartextTraffic: IS_DEV` | schema 禁止该字段；**语义等价迁移：仍仅 dev 开明文 HTTP**，保卡 808e895d |
| 删除冗余 `app.json`（app.config.js 为唯一配置源） | expo-doctor：动态配置未读取静态配置 |
| `mobile/.expo/` 移出 git 跟踪 + 根 .gitignore | expo-doctor 要求（机器本地状态） |
| overrides 增补：`brace-expansion@2 → ^2.1.4`、`uuid → ^11.1.1` | 新链上新披露漏洞（glob9/minimatch8 链、xcode@3 链） |
| `@babel/core` 短暂试 8.0.1 后回退 7.29.7 | babel-plugin-module-resolver 与 expo 均 pin 7.x；7.29.7 已含修复 |

最终 overrides：shell-quote/form-data/nanoid/lodash/ws/js-yaml@3/js-yaml@4/brace-expansion@1/brace-expansion@2(^2.1.4)/uuid(^11.1.1)。

## 4. expo-doctor 剩余 1 项 fail（如实记录，需真机/原生验证）

> ✖ Check for app config fields that may not be synced in a non-CNG project

- 原因：仓库存在 `ios/`（历史 prebuild 产物）而 app.config.js 带原生配置字段。Expo 判定为 non-CNG，EAS Build 不会自动同步 orientation/icon/ios/android/plugins 到既有原生工程。
- 处置：属**结构性选择**而非错误——两条出路：① 走 CNG（删 ios/ 每次纯 prebuild）；② 保留 ios/ 并在下次原生构建时跑 `npx expo prebuild` 重新生成后再 EAS Build。涉及原生编译与真机回归，超出本卡本地验证边界，**留待下张原生构建卡**（build-android.sh / EAS 流程随之验证）。

## 5. 验证证据

- `npx tsc --noEmit` → exit 0（TS 6.0.3, strict）
- `npx expo install --check` → "Dependencies are up to date"
- `npx expo-doctor` → 20/21 passed
- `npm audit` → **found 0 vulnerabilities**（基线 46 → 37 → 0）
- `git diff HEAD -- src/` → 空（业务代码零改动，env.ts 三环境原样）
- 测试：mobile 无测试套件（无 test script、无测试文件），无 tsc 之外的本地自动化验证手段，如实说明。

## 6. 提交清单（分支内，未 push）

7be7321697 / 5ae083b62 / 9bb88e9ee / 201599304 / 0826a50fa / bd0338674 / c633745b0 + 本报告收尾 commit，全部标注 卡 46871d16。
