# Changelog

本项目所有显著变更均记录于此文件。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### Added
- **覆盖率门控落地+口径纠偏（F201）**：①实测撞出jest配置缺`coverageThreshold`——覆盖率回退无声通过；②撞出统计口径幸存者偏差——coverage仅计被测试加载的20个文件，12个零测试文件（Login/Dashboard/StationList/StationDetail/Profile 5屏幕+AppNavigator/MainTabNavigator+AIChatPanel/ErrorBoundary/LoadingSpinner/NetworkStatus 4组件+types）不可见，此前README"95.18%"非真值→补`collectCoverageFrom`计入全部源文件，实测总体 **stmts 75.53%/branches 71.54%/funcs 75.14%/lines 74.93%**（328 tests全绿不变）；③设coverageThreshold global（stmts≥75/branches≥71/funcs≥74.5/lines≥74.5，实测值下沿留小缓冲）；④变异测试三档实证：探针A机制验证（override branches=99.9→exit 1报错精确）、探针B真实回归（新增无测试文件→stmts 75.53→74.91%/lines 74.26%→exit 1拦截，tests仍328绿但门控正确失败）、清理后exit 0；⑤CI调用点单一源：`npx jest --coverage --passWithNoTests`→`npm test -- --coverage`（F195模式，Makefile已委托）；⑥README质量门控章节同步（275/95.18%旧数纠正）
- **分支覆盖冲刺第四批（F194）**：branches 93.10%→**93.56%**（+0.46pp）、stmts 98.92%→**99.14%**、lines 99.64%→**99.88%**、全仓 325→**328 tests** 全绿。补：①WorkOrderScreen 86.36%→**89.39%** — **推翻F188"UI不可达"结论**: `!stationId`防御分支可通过"开modal后路由参数被改写→changeText触发re-render重读params"路径实测命中（Alert'请先选择站点'+createWorkOrder零调用双断言）+ stationId缺失时FAB隐藏行为测试；②ChargerTrendChart 86.48%→**89.18%** — 12点趋势抽稀分支（buildLabels step=2半数标签置空 + Math.max右侧，mock LineChart扩展labels计数输出实证labels=12,empty=6）；残留未覆盖均为不可达死分支（buildLabels空入参被调用侧points.length>0前置拦截 / hexToRgb '||0'兜底遇合法调色板恒短路）不强补；tsc 0err + eslint 0违规 + jest全量复验全过
- **分支覆盖冲刺第三批（F188）**：branches 90.81%→**93.10%**（+2.29pp，608/653）、stmts 98.50%→**98.92%**、全仓 319→**325 tests** 全绿。补：①DeviceDetailScreen 80.64%→提升（inverter/other图标分支 + undefined status回退offline badge + model/manufacturer空值'-'回退 + 45-60°C中间档温度颜色 + controlDevice无message默认文案回退）；②NotificationCenterScreen formatTime四档相对时间分支（刚刚/N分钟前/N小时前/N天前，动态Date.now()构造法）+ 未知通知类型📢兑底图标/原始type文本回退；③cache.ts debounce默认300ms参数分支；④WorkOrderScreen !stationId分支实测确认为UI不可达防御代码（"+"按钮本身在stationId块内渲染）不强补；tsc 0err + eslint 0违规复验全过；⚠️接手并发轮F187未提交工作区改动（319 tests/90.81%），随本commit链一并落盘推送
- **分支覆盖冲刺第二批（F187）**：branches 87.90%→**90.81%**（+2.91pp）、stmts 98.07%→**98.50%**、lines 99.16%→**99.64%**、全仓 307→**319 tests** 全绿。补：①ai.ts 78.78%→87.87%（streaming无body抛错分支 + tool call参数跨chunk累积分支〔existing累积/无arguments跳过〕）；②api.ts 85.61%→94.24%（handleAlarm/getDetail/createWorkOrder/completeWorkOrder data缺失→undefined兑底、getDetail空对象映射、complete无solution省params、getRecentAlarms默认limit、revenueApi summary/records空payload全兑底、num/numOrUndef '0'串/Infinity/strOrUndef非串边界）；③DeviceDetailScreen formatLogTime catch分支（toLocaleString按年份分流spy法，回退原始dateStr）；④ChargerTrendChart chartConfig.color()默认参数分支（mock无参调用）；tsc 0err + eslint 0违规复验全过
- **分支覆盖补齐（F181）**：store分支补齐 — stationStore 4个fetch的catch非Error拒绝分支 + authStore checkAuth空profile.data分支；两store全指标100%，全仓 302→**307 tests**，branches 87.13%→**87.90%**
- **分支覆盖冲刺（F180）**：branches 82.84%→**87.13%**（+4.29pp，569/653）、stmts 97.75%→**98.07%**、全仓 287→**302 tests** 全绿。补 api.ts helper/mapper 边缘分支（num/str/numOrUndef 数字串/空串/NaN/非串、mapStation 三态 status+字段回退、mapWorkOrder title/time 回退、mapPagination 空 raw+pageSize 别名、getList 未知 status 透传、createWorkOrder 未知 priority/deviceId 缺省、dashboardApi 空 payload 全兜底）+ usePolling 卸载竞态分支（无 options 默认值/非 Error 包装/卸载后 refresh/在途 resolve+reject 短路）；tsc + eslint --max-warnings 0 双门复验全过
- RevenueScreen 补测3条交互路径（下拉刷新isRefresh分支/Share失败导出告警/图表数据与颜色回调），单文件覆盖 85.41%→97.91%，函数覆盖 75%→100%；全仓 275 tests / 95.18%；顺手清零 NotificationCenterScreen.test 预存 eslint warning；README 覆盖明细按实测修正
- DeviceDetailScreen 补测6条路径（下拉刷新/遥测降级/错误重试/重启复位确认/在线禁启动/离线启动+电池图标+无心跳降级），单文件覆盖 87.32%→97.18%，函数覆盖 68%→100%；全仓 267 tests / 93.46%
- 全局错误边界 `ErrorBoundary.tsx`：捕获子树渲染异常防白屏，DEV 模式显示堆栈（`e4dc934`）
- Makefile 10 targets (install/dev/build/export/test/lint/check/ci-local/clean/help)（F136）
- GitHub Actions CI 两阶段流水线 (check: tsc+eslint+jest → export: android+ios bundle)（F137）
- DEPLOYMENT.md 完整部署指南 (环境变量/本地开发/CI/OTA/原生构建)（F138）
- `.env.example` 环境变量模板（F139）
- `build` / `export:android` / `export:ios` npm scripts（F140）
- 网络状态横幅 `NetworkStatus.tsx`：AppState 监听前后台切换，回前台 ping API 检测连通性，离线显示红色横幅；无需额外依赖（`e4dc934`）
- `App.tsx` 包裹 ErrorBoundary + NetworkStatus（`e4dc934`）
- `eas.json` 三档构建 profile：development / preview(APK) / production（`e876fd8`，关闭 F33）
- store 层覆盖率全面提升：authStore 45.8%→100% / stationStore 57.7%→100% / workOrderStore 65.7%→100%（F27/F75 已修复）
- api.ts 覆盖率提升：73.3%→91.4%（F75 已修复）

### Changed
- eslint 警告清零：84 → 0（`474492b`）
- WorkOrderScreen 补测5条真实交互路径（筛选chip带参重取/真实分页追加/下拉刷新/Modal onRequestClose安卓返回/优先级picker选中创建），单文件覆盖 86.86%→96.96%，函数覆盖 73.91%→100%；全仓 272 tests / 94.53%
- README 同步最新质量指标（coverage 94.53%、272 tests、eslint 0 warn）

### Fixed
- F32: 无 AppState / 网络状态检测 → ErrorBoundary + NetworkStatus 已接入 ✅
- F33: 缺 eas.json → 三档 profile 已配置 ✅
- F75: store/screen 覆盖率偏低 → authStore/stationStore/workOrderStore 均 100%，api.ts 91.4% ✅
- F80: eslint 84 warn → 全部清零 ✅
- F136-F140: 缺 Makefile/CI/DEPLOYMENT.md/.env.example/build script → 全部补齐 ✅

## [1.0.0] - 2026-07-31

### Changed
- 移动端依赖对齐 Expo SDK 52：react-native 0.76.6 → 0.76.9，react-native-svg pin 15.8.0（`967b420`）

### Added
- 建立 expo-doctor 门控：2 失败 → 18/18 全过（`967b420`）
- 建立 eslint 门控（expo flat config，0 err / 84 warn），修复 3 处 react-hooks v6 违规（`f2b0d54`）
- 品牌占位 assets：icon / adaptive-icon / splash / favicon（`8075856`）

### Fixed
- 修复 lockfile 嵌套 expo-asset 未提升致 expo export 失败（`8075856`）

## [0.3.0] - 2026-07

### Added
- 4 页面真云端 API 对齐，闭环战役 B2（`36b2cbe`）
- AI 助手集成：ai.ts 服务 + AIChatPanel 组件 + function calling 框架（`1c91dee`）

### Fixed
- LRU 缓存淘汰：Date.now() 重复键 → 递增序列号 lruSeq（`ac7d936`）

## [0.2.0] - 2026-07

### Added
- P1 完成：设备管理 / 告警工单 / 营收统计 / 通知中心（`4164299`）

## [0.1.0] - 2026-07

### Added
- 项目初始化（Expo RN + TS + zustand）
