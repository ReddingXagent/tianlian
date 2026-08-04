# Changelog — tianlian-user-app

本仓库变更记录。格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号语义化。

## [Unreleased]

### Added
- Home 页站点地图挂载闭环（F234，移动端死代码对账，接手 18:50 轮被重启打断的未提交改动复验落盘）— MapView 自组件落地起就有完整实现（站点 marker 分布/可用-已满双色/距离标注/图例/点击导航）+单测，但全仓零挂载=死代码（F228 OfflineBanner 同款模式）：Home 列表顶部仅静态占位文案「共找到 N 个充电站」，站点空间分布/可用状态无可视化。修复：占位 View 替换为真 MapView（height=220，onStationPress 复用 StationCard 同款导航直达详情），删死样式 mapPlaceholder 三件套；补挂载守卫测试 2 条（295→297：非空列表图例「2 个站点」+marker 站点名进渲染树 / 空态分支不挂地图）；接手复验规矩全走：tsc 0err → jest 297 绿 → eslint 0err/54warn≤60 零增量；README 测试数同步 295→297
- OfflineBanner 离线提示条根级挂载（F228，移动端死代码对账）— 组件自 F32 延伸批次就有完整实现+单测（isConnected===false 确认离线才展示，NetInfo 首帧未知不闪条），但全仓零挂载=死代码：离线时 useAppLifecycle 只用于暂停充电轮询，用户看陈旧站点/订单/余额数据却无任何视觉告知。修复：AppNavigator 根级 flex 容器顶部挂 OfflineBanner（覆盖 Auth 登录态——登录需网——与 Main 全部页面）；补挂载守卫测试 2 条（293→295：在线零干扰/离线横幅出现于渲染树）；顺带清 README 门控表欠账两行：覆盖率行 67.77 虚标→实际门限 34/24/28/34+实测 78.38/68.91/76.64/78.17，lint 行 ≤21→实际 `--max-warnings=60`（当前 54）
- 首屏拉取失败不再伪装成空数据（F221，错误态一致性对账）— 逐屏对账「失败渲染」撞出两屏缺口：①OrderListScreen：orderStore 早已维护 error 态但页面未渲染，首拉失败落入「暂无订单/去充电」空态，网络故障被误读为无记录；②WalletScreen：首拉失败静默吞掉（catch 空处理），落入「暂无记录」空态，资金页误导更甚。修复：两屏补 `error && 列表为空` → EmptyState「加载失败」+错误文案+重试按钮（重试分别走 fetchOrders(保持当前筛选)/loadRecords），与 Coupon/Home/Vehicle/StationDetail/OrderDetail 既有模式对齐；已有数据时刷新/回焦失败保留列表可见（守卫含 `&& length===0`，F209 不闪屏模式）；补测 6 条（287→293：失败显示加载失败+重试×2 屏/点击重试恢复×2 屏/有数据时失败保留列表×2 屏）；全门 tsc 0err + jest 293 绿 + lint:ci 0err/54warn≤60 零增量；README 测试数基线同步 190→293（旧欠账顺带清）
- 优惠券/车辆页回焦刷新补齐 + 车辆页下拉刷新补齐（F215，接手并发轮改动复验落盘；F170/F209 交互一致性模式续打）— 回焦对账收尾撞出两屏缺口：①CouponScreen 仅 mount 拉取，支付/下单用券后返回券状态（已用/过期）陈旧 → 接 useIsFocused 回焦静默重拉（固定回第 1 页，分页态随之重置）；②VehicleScreen 同型 mount-only（默认车辆/车辆状态在支付/充电流程后变化不可见）→ 接 useIsFocused + FlatList 补 RefreshControl 下拉刷新（列表屏对齐），连带渲染守卫改 `loading && vehicles.length===0` / `error && vehicles.length===0`（回焦/下拉重拉不整屏闪 spinner、刷新失败不丢已有列表，F209 模式）；补测 4 条（283→287：回焦重拉×2 屏/下拉刷新+refreshing 复位/回焦重拉中列表保持可见——挂起第二刷探针）；全门 tsc 0err + jest 287 绿 + lint:ci 0err/54warn≤60
- 优惠券页刷新守卫纠偏（F209 模式续打，渲染守卫一致性对账）— 撞出 CouponScreen 与钱包页修复前同族缺口：`if (loading)` / `if (error)` 无条件整屏切换，下拉刷新重拉时已有列表整屏切 spinner（FlatList 卸载连 RefreshControl 指示器一起消失），刷新失败时已有列表整屏切错误页（用户丢失已加载数据）。修复：两守卫均改 `&& coupons.length === 0`（仅首屏无数据才切整屏态，与 WalletScreen/OrderListScreen 对齐）；补测 2 条（281→283：刷新中列表保持可见——挂起第二刷探针 / 刷新失败保留列表+refreshing 复位）；变异双探针实证（loading/error 守卫分别回退→对应测试精确失败）
- 钱包页下拉刷新补齐 + 刷新不闪屏（移动端一致性缺口 F209）— 订单/优惠券/首页/站点详情四屏均有下拉刷新，唯独钱包（资金敏感页：余额+流水）缺失，用户只能靠回焦静默重拉，无手动刷新手段。修复：WalletScreen FlatList 接 RefreshControl（下拉同时重拉流水+profile 同步最新余额，refreshing 复位）；连带修渲染守卫 `loading && records.length===0` 才切整屏 spinner（此前回焦/下拉重拉时列表整屏闪 spinner，资金页体验断裂），补测 2 条（279→281：下拉双拉+复位/刷新中列表保持可见）
- 分页列表无限滚动补齐（移动端真缺口）— 订单/钱包流水/优惠券三屏的 API 本就分页（PaginatedData），但 UI 只拉第一页：历史记录超出首页即永久不可见。修复：orderStore 新增 hasMore/loadingMore/loadMoreOrders（追加+按 id 去重+加载更多失败静默可重试+筛选条件随 loadMore 保持），OrderList/Wallet/Coupon 三屏 FlatList 接 onEndReached 触边加载下一页（加载中 footer spinner/到底显示「没有更多了」）；补测 4 条（275→279：hasMore 判定/追加+去重+筛选保持/no-op 门控/失败静默可重试）
- expo-camera 权限声明补齐 + 配置回归防护（移动端真缺口）— b3eb03c 装了 expo-camera 但 app.json plugins 漏配：iOS 缺 NSCameraUsageDescription（真机权限请求直接失败）/Android 缺 CAMERA 权限声明；补 `["expo-camera", {"cameraPermission": ...}]`，`expo config --type introspect` 实测两端声明均生效；新增 src/__tests__/appConfig.test.ts 接入 jest 门禁（camera 权限文案 + expo-secure-store 保留 + platforms 限定 android+ios 三项回归防护，F179 一并锁住），补测 3 条（272→275）
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
