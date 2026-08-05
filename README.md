# 天链用户端App（tianlian-user-app）

充电用户端 App（React Native + Expo SDK 52），面向 C 端充电用户。天链终端 app 矩阵之一，与 ops-app（运维端）/ station-app（场站端）/ user-mp（微信小程序）并列。

## 功能

- 附近站点搜索 + 地图导航
- 扫码充电（扫码 → 确认 → 启动）
- 实时充电监控（轮询充电状态，前后台/联网感知自动暂停恢复）
- 订单管理 + 支付
- 优惠券 / 钱包 / 充电记录
- 个人中心（车辆管理）

## 技术栈

- React Native（Expo SDK 52，纯 Expo 工作流，无原生构建脚本）
- TypeScript（严格模式，`tsc --noEmit` 为构建门）
- Zustand（状态管理：authStore / orderStore / stationStore）
- React Navigation（native-stack + bottom-tabs）
- axios（API 层，token 存 expo-secure-store）
- @react-native-community/netinfo（联网状态感知）

## 快速开始

```bash
npm ci            # 或 npm install
npx expo start    # 启动 Metro，Expo Go 扫码调试
```

平台脚本：`npm run android` / `npm run ios` / `npm run web`。

## 质量门控

| 门 | 命令 | 当前基线 |
|----|------|---------|
| 构建 | `npx tsc --noEmit` | 0 错误 ✅ |
| 测试 | `npm run test:ci` | 420 全绿（41 suites）✅ |
| 覆盖率棘轮 | jest coverageThreshold（package.json） | 门限 statements 78 / branches 70 / functions 77 / lines 78（只升不降）；实测 78.83 / 70.38 / 77.58 / 78.64（420 tests，2026-08-06） |
| Lint 棘轮 | `npm run lint:ci` | 0 错误 / ≤60 警告（`--max-warnings=60`，只降不升；当前 54） |
| 部署门控 | `npm run deploy:check` | 退2 设计内拦截（F25/F33 已决策清零 08-05：Expo 账号当前阶段不需要——测试走 Expo Go 扫码、内部分发走 APK 直装；OTA 延后到发布候选期再定，届时接账号须 app.json updates.url ↔ eas.json projectId 两侧同步，F302 守卫形态） |

覆盖率与警告数均为棘轮门控：新增代码不得使指标回退。

## 项目结构

```
App.tsx                  # 入口：SafeAreaProvider + AppNavigator
src/
  navigation/            # AppNavigator（登录态切换 + Tab 导航）
  screens/               # 12 个页面（Home/Scan/Charging/Order/Payment/Profile...）
  components/            # MapView / StationCard / StatusBadge / EmptyState / LoadingSpinner
  hooks/
    useAppLifecycle.ts   # 前后台(AppState) + 联网(NetInfo) 状态聚合
    useChargingPolling.ts# 充电轮询；后台/离线自动暂停，回前台/复网立即补拉
  services/api.ts        # axios 实例 + 全部 API 封装（token 拦截器自动附加）
  store/                 # Zustand stores
  types/                 # 共享类型定义
__mocks__/               # expo-secure-store / expo-status-bar 的 jest mock
jest.setup.ts            # 全局 mock（含 AppState/NetInfo 兜底，见下）
```

## 架构备注

- **生命周期感知轮询**：`useChargingPolling` 通过 `useAppLifecycle` 订阅 AppState 与 NetInfo，进入后台或确认离线时自动暂停轮询，回前台或复网立即补拉一次，避免无效请求与电量浪费（`pauseWhenInactive` 开关可控）。
- **Jest 原生模块坑**：jest 自动 mock 会导致 `AppState.currentState` 变成 `jest.fn()` 而非字符串，`??` 兜底无效；`jest.setup.ts` 中已将其钉死为 `'active'`，NetInfo 同理。新增原生模块 mock 时注意同型问题。
- **API 基址**：`src/services/api.ts` 通过 `EXPO_PUBLIC_API_URL` 环境变量配置，回退到生产云端地址。开发时可在 `.env` 或启动命令中覆盖（如 `EXPO_PUBLIC_API_URL=http://localhost:8000/api/v1 npx expo start`）。

## 部署

- **产物验证**：`npx expo export --platform android` 已验证可出 Hermes bundle（2.24MB）。
- **部署门控**：`npm run deploy:check`（`scripts/deploy-check.js`）四步检查 app.json → eas.json → expo-updates → 凭证；退出码 0=就绪 / 1=配置错误 / 2=外部依赖待就位（设计内拦截）。当前退2，就绪清单：Expo账号 → EXPO_TOKEN → `eas build:configure` → 装 expo-updates → 配 updates.url/channel。
- **依赖坑（F51）**：`metro`/`expo-asset` 若只被嵌套安装（未提升顶层），`@expo/cli` 顶层解析会 MODULE_NOT_FOUND 致 export 崩；本仓已显式声明 `metro@0.81.5`(dev) + `expo-asset@~11.0.5` 钉死。

- **全局错误边界**：`src/components/ErrorBoundary.tsx` 包裹根组件，捕获 React 渲染异常并展示友好降级 UI（c7cdd76）。
- **AppNavigator 测试**：导航逻辑（登录态切换 + Tab 路由）已补测试，覆盖率从 0% 提升至 76.92%（709cd04）。

## 已知限制

- Web 导出（`expo export --platform web`）未验证，web 部署待定（同 ops/station F24/F34）。
- EAS Update 渠道与 Expo 账号未配置，OTA 升级通道待开通（deploy:check 门控跟踪）。
- 12 个 screen 中 8 个有测试（Home/Login/Coupon/OrderList/Profile/StationDetail/Wallet + AppNavigator 导航），剩余 4 个（Scan/Charging/OrderDetail/Payment/Vehicle）为后续补强重点。

## 关联仓库

- `tianlian-ops-app`（运维端）/ `tianlian-station-app`（场站端）/ `tianlian-user-mp`（用户小程序）
- `tianlian-shared`（共享 cli/docs/tests/cloud-mock）
- 云端后端为独立仓库，终端侧仅通过 HTTP API 对接。
