# Changelog — tianlian-user-app

本仓库变更记录。格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号语义化。

## [Unreleased]

### Added
- Android 硬件返回键治理（移动端真缺口）— 新增 useAndroidBackExit hook：此前任意 root tab 按硬件返回直接 exitApp（React Navigation 默认，充电中误退尤甚）；治理后：详情页盖住 tabs 不拦截（原生 back 弹栈）、非 Home tab 先跳 Home、Home tab 首按 toast「再按一次退出」+ 2s 内再按才 exitApp；iOS BackHandler 天然 no-op 无需分支；补测 7 条（265→272：拦截/不拦截/双击窗口/reset/state 未知 + AppNavigator mock 补 useNavigation）
- ScanScreen 真扫码落地（F21 修复）— 新增 expo-camera ~16.0.18 + CameraScanner 组件（相机权限请求/拒绝后引导去设置、QR 取景框、同码 2.5s 冷却去重）+ parseScanPayload 解析器（裸编码/URL/URL 末段路径三形态）；扫码成功自动查询并收起相机，手动输入保留兜底；补测 24 条（241→265：CameraScanner 权限/扫描、scanCode 解析、ScanScreen 相机交互）

### Fixed
- lint:ci 警告阈值红盘修复（F170 遗留闭环）— 清理 6 条 unused-vars（ErrorBoundary/AppNavigator/api 测试未用导入），warnings 62→56 ≤ 阈值 60，`npm run lint:ci` 由红转绿

### Fixed
- 回焦刷新收尾第三屏批次 — StationDetail/OrderDetail/Wallet 三屏此前仅 mount 拉取：桩位状态(空闲/占用/故障)、订单状态(充电中/完成/取消)、钱包余额+流水在离开页面期间变化后回屏陈旧；接入 useIsFocused 回焦静默重拉（Wallet 同拉 profile 同步余额，同 F170/F176 模式），补测 3 条（238→241）
- ProfileScreen 回焦静默刷新 — Profile 底部 Tab 切走保活不重建，仅 mount 拉一次统计/余额；接入 useIsFocused 回焦重拉 stats + authApi.getProfile（钱包充值/扣费后余额实时同步），补测 3 条（235→238）；收尾 F170 遗留的 mount-only 缺口

### Added
- 部署门控 `scripts/deploy-check.js` + `npm run deploy:check`：app.json/eas.json/expo-updates/凭证四步检查，退2设计内拦截待Expo账号（对齐user-mp deploy:check模式）
- 验证 `expo export --platform android` 产物管线可出 Hermes bundle（2.24MB）
- 新增 4 个 screen 测试（Profile/Wallet/OrderList/StationDetail），screen 测试 3→7，总测试数 108→135
- ErrorBoundary 全局错误边界组件（捕获渲染异常 + 友好降级 UI）
- eas.json 三档配置（development/preview/production）
- assets 占位图标集（adaptive-icon/favicon/icon/splash）
- API 环境化：`EXPO_PUBLIC_API_URL` 环境变量优先，回退生产地址（F107 修复）
- AppNavigator 测试（导航路由 + 登录态切换），screen 测试 7→8，总测试 135→190
- LoginScreen 测试补全（覆盖率 27%→73%）

### Fixed
- 主Tab回焦静默刷新（移动端陈旧数据真缺口）: Home/订单Tab为底部Tab, 切走后组件保活不重建, 此前仅mount拉取一次 → 切回时站点空闲/占用状态与订单状态陈旧; HomeScreen/OrderListScreen 接入 useIsFocused 回焦重拉, 搜索态不重拉避免冲掉搜索结果; 补测 3 条（总测试 232→235）; ⚠️同类遗留: ProfileScreen仍为mount-only拉取(影响小, 留后续移动端轮)
- ChargingScreen 轮询改用 useChargingPolling：后台/断网自动暂停、回前台/复网立即补拉（原裸 setInterval 3s 后台不停轮询费电耗流量）；单次请求失败不再永久停轮询致页面冻结，新增首帧失败错误页+重试按钮、轮询中失败黄条提示；补测 2 条（总测试 230→232）
- F51: export 崩溃（metro/expo-asset 嵌套未提升顶层致 @expo/cli MODULE_NOT_FOUND）→ 显式声明 metro@0.81.5(devDep) + expo-asset@~11.0.5
- eslint flat config 补 scripts/**/*.js node globals 豁免（新脚本 __dirname no-undef）

### Changed
- README 同步实际测试数（135）与 screen 测试覆盖（7/12）

### 已知债务
- screen 测试覆盖 8/12，剩余 4 个（Scan/Charging/OrderDetail/Payment/Vehicle）待补
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
