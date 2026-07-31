# Changelog — tianlian-user-app

本仓库变更记录。格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号语义化。

## [Unreleased]

### Added
- 部署门控 `scripts/deploy-check.js` + `npm run deploy:check`：app.json/eas.json/expo-updates/凭证四步检查，退2设计内拦截待Expo账号（对齐user-mp deploy:check模式）
- 验证 `expo export --platform android` 产物管线可出 Hermes bundle（2.24MB）
- 新增 4 个 screen 测试（Profile/Wallet/OrderList/StationDetail），screen 测试 3→7，总测试数 108→135

### Fixed
- F51: export 崩溃（metro/expo-asset 嵌套未提升顶层致 @expo/cli MODULE_NOT_FOUND）→ 显式声明 metro@0.81.5(devDep) + expo-asset@~11.0.5
- eslint flat config 补 scripts/**/*.js node globals 豁免（新脚本 __dirname no-undef）

### Changed
- README 同步实际测试数（135）与 screen 测试覆盖（7/12）

### 已知债务
- `src/services/api.ts` BASE_URL 硬编码生产 IP，缺 dev/mock 环境切换
- screen 测试覆盖 7/12，剩余 5 个（Scan/Charging/OrderDetail/Payment/Vehicle）待补
- Web 导出未验证；EAS Update 渠道未配置

## [0.3.0] - 2026-07-31

### Added
- AppState/NetInfo 生命周期感知：新增 `useAppLifecycle` hook（前后台 + 联网状态聚合）
- `useChargingPolling` 接入生命周期感知：后台/确认离线自动暂停轮询，回前台/复网立即补拉；新增 `pauseWhenInactive` 开关
- 引入 `@react-native-community/netinfo@11.4.1`（expo install 钉版）
- jest.setup 全局 mock NetInfo + AppState 兜底（钉死 `currentState='active'`，规避 jest 自动 mock 坑）
- 新增 8 个测试（lifecycle 4 + 感知 4），总数达 108 全绿

### Changed
- 覆盖率棘轮上调：statements 32→34 / branches 22→24 / functions 26→28 / lines 33→34

## [0.2.0] - 2026-07-30

### Added
- ESLint 门控：`lint:ci` 棘轮 0 错误 / ≤21 警告（exhaustive-deps×13 + set-state×7 + axios×1）

## [0.1.1] - 2026-07-30

### Added
- CouponScreen 测试 + coverage 棘轮门控（coverageThreshold 入 package.json）

### Fixed
- 修复 tsc 5 处报错，同步 package-lock.json，构建门（npm ci + tsc）贯通

## [0.1.0] - 2026-07-29

### Added
- 项目骨架：Expo SDK 52 + TypeScript + Zustand + React Navigation
- 12 个页面：首页/站点详情/扫码/充电/订单列表/订单详情/支付/优惠券/钱包/车辆/个人中心/登录
- API 层（axios + SecureStore token 拦截器）、3 个 Zustand store
- 初始测试套件（components / stores / services）
