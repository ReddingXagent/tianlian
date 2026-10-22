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
| 测试 | `npm run test:ci` | 927 全绿（111 suites）✅ |
| 覆盖率棘轮 | jest coverageThreshold（package.json） | 门限 statements 99 / branches 99 / functions 99 / lines 99（只升不降）；实测 100 / 99.72 / 100 / 100（927 tests，2026-10-23，jest 覆盖率表） |
| Lint 棘轮 | `npm run lint:ci` | 0 错误 / 0 警告（`--max-warnings=0`，只降不升；当前 0） |
| 部署门控 | `npm run deploy:check` | 退2 设计内拦截（F25/F33 已决策清零 08-05：Expo 账号当前阶段不需要——测试走 Expo Go 扫码、内部分发走 APK 直装；OTA 延后到发布候选期再定，届时接账号须 app.json updates.url ↔ eas.json projectId 两侧同步，F302 守卫形态） |

覆盖率与警告数均为棘轮门控：新增代码不得使指标回退。

## 项目结构

```
App.tsx                  # 入口：SafeAreaProvider + AppNavigator
src/
  navigation/            # AppNavigator（登录态切换 + Tab 导航）
  screens/               # 13 个页面（Home/Scan/Charging/Order/Payment/Profile/Coupon/Energy/Vehicle...）
  components/            # MapView / StationCard / StatusBadge / EmptyState / LoadingSpinner
  hooks/
    useAppLifecycle.ts   # 前后台(AppState) + 联网(NetInfo) 状态聚合
    useChargingPolling.ts# 充电轮询；后台/离线自动暂停，回前台/复网立即补拉
  services/api.ts        # axios 实例 + 全部 API 封装（token 拦截器自动附加）
  store/                 # Zustand stores
  types/                 # 共享类型定义
  utils/                 # format.ts（日期/距离/金额/电量单一源）+ scanCode.ts（扫码解析）
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

## 静态守卫族

本仓通过 jest 门禁内置 13 枚静态守卫（`src/__tests__/*Guards.test.ts`），覆盖 tsc 盲区的移动端 UX 缺陷模式。新增守卫自动接入门禁（jest 全量跑即入门），无需 CI/Makefile 接线。

| 守卫 | 维度 | 不变量 |
|------|------|--------|
| mobileKeyboardGuards | 键盘族① | Modal×TextInput → KeyboardAvoidingView 包裹 + onRequestClose 声明 |
| scrollKeyboardGuards | 键盘族② | 非 Modal 屏 TextInput×ScrollView → keyboardShouldPersistTaps 声明 |
| plainKeyboardGuards | 键盘族③ | 非 Modal/非滚动容器层 TextInput → KeyboardAvoidingView 包裹 |
| keyboardDismissGuards | 键盘族④ | 含 TextInput 文件的 ScrollView/FlatList → keyboardDismissMode 合法收起通道（'none' 形式声明必拦） |
| headerlessSafeAreaGuards | 安全区 | headerShown:false 导航器 Screen → SafeAreaView 消费 |
| listKeyGuards | 列表族① | FlatList/SectionList → keyExtractor 声明 |
| listExtraDataGuards | 列表族② | FlatList/SectionList renderItem 闭包捕获 useState → extraData 声明 |
| touchTargetGuards | 触控族 | Pressable/TouchableOpacity 固定尺寸 → height/width ≥ 44pt |
| imageErrorGuards | 图片族 | Image source=远程/变量 → onError 声明 |
| inputMaxLengthGuards | 输入族① | TextInput keyboardType=数字键盘 → maxLength 声明 |
| passwordAutofillGuards | 输入族② | TextInput secureTextEntry → 双平台 autofill 声明 |
| otpAutofillGuards | 输入族③ | TextInput 数字键盘×短 maxLength → sms-otp/oneTimeCode 双平台声明 |
| accessibilityRoleGuards | accessibility族① | 带 onPress 的 Pressable/TouchableOpacity → accessibilityRole 声明（读屏语义） |

## testID 锚点铺底

全部 13 屏已铺设 `testID` 锚点共 30 处（Login 7 / Home 3 / Profile 2 / Scan 1 / Charging 2 / Coupon 1 / Energy 2 / OrderDetail 2 / OrderList 2 / Payment 2 / StationDetail 2 / Vehicle 2 / Wallet 2），供 E2E（Detox/Maestro 类）选择器与无障碍调试定位使用。命名约定：`<屏名>-<元素>`（如 `login-btn`、`station-list-refresh`），动态列表项带后缀（`order-list-filter-${key}`、`station-detail-charger-${id}`）。新增交互元素时应同步补 testID，保持 E2E 可寻址性不回退。

## 已知限制

- Web 导出（`expo export --platform web`）未验证，web 部署待定（同 ops/station F24/F34）。
- EAS Update 渠道与 Expo 账号未配置，OTA 升级通道待开通（deploy:check 门控跟踪）。

## 关联仓库

- `tianlian-ops-app`（运维端）/ `tianlian-station-app`（场站端）/ `tianlian-user-mp`（用户小程序）
- `tianlian-shared`（共享 cli/docs/tests/cloud-mock）
- 云端后端为独立仓库，终端侧仅通过 HTTP API 对接。
