# Changelog

本项目所有显著变更均记录于此文件。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### Added
- **NetworkStatus 卸载竞态补测 + branches 棘轮上调（F251）**：NetworkStatus 组件 branches 75%（全仓分支覆盖洼地之一）— 补齐 3 条守卫用例：卸载后 ping 才 resolve / 卸载后 ping 才 reject（mountedRef 守卫拦截 setState，React 无警告）+ AppState 订阅对象无 remove 方法时清理可选链不崩（subscription?.remove?.()）；全仓 405→**408 tests** 全绿，全量 branches 91.92→**92.15%**（NetworkStatus 自身 75→91.66%）；coverageThreshold 棘轮上调 branches 91→**92**（实测下沿取整，F207 规矩只升不降；其余三项 99/98/99 已在实测下沿无余量）；变异档实证（门限上调 99→jest --coverage exit 1 精确拦截，还原后 exit 0）；全门复验 tsc 0err + eslint 0err/0warn；README 质量门控章节测试数/覆盖率/门限同步
### Added
- **app.json 构建配置回归守卫（F245，F244 跨仓移植）**：app.json 是构建/导出的配置声明源，四类零断言补齐 — ①platforms 限定 android+ios（防误挂 web，F179 同型）②plugins↔deps 双向对账（每 plugin 必有已装 dep，缺则 export/prebuild 直接炸；expo-secure-store/expo-asset 等已知原生模块必声明 plugin，F196 反向静默缺口）③android.package↔ios.bundleIdentifier 应用标识同语义双源一致（同文件内双源形态，单侧改名=双平台 OTA/商店归属漂移，F224 同族）④icon/splash/adaptiveIcon 资产文件存在断言（缺=导出后程失败提前 FAIL）；新增 `src/__tests__/appConfig.test.ts`（ops-app F244 模板结构同构零改复用，F238 移植模式），jest 全量跑自动接入 CI check job 零额外接线；变异三档实证（platforms 加 web / android.package 单侧改名 / 移除 expo-asset plugin，均精确拦截 1 failed，sed 反向还原后基线 5/5 + git diff 零残留，变异档保持 JSON 合法性，F244 花絮教训）；全门复验 tsc 0err + eslint 0err/0warn + jest 400→**405 tests** 全绿（33 suites，coverageThreshold 99/91/98/99 棘轮不受影响，测试文件不入覆盖率口径）；README 质量门控章节测试数同步 400→405；RN 三仓 app.json 配置自洽守卫至此全覆盖（user-app F196 / ops-app F244 / station-app 本条）

### Added
- **路径别名双源漂移守卫（F238）**：tsconfig.compilerOptions.paths（tsc 侧）与 package.json jest.moduleNameMapper（测试侧）同语义双源零断言，只改一侧即 tsc/jest 解析分叉（F231 双源模式 ops-app→station-app 移植）；修法：`scripts/check-alias-config.sh`（node 归一化两侧别名集合+目标目录双向断言，精确别名不处理）+ `npm run check:alias` 接入 CI check job 与 Makefile check 链（alias-check target，委托单一源）；变异三档实证（jest 目标漂移 src2 / tsconfig 单侧新增 @components / jest 侧 moduleNameMapper 缺失，均 exit 1 精确拦截，恢复后 exit 0）；顺带补齐 CI 双 job timeout-minutes（check 15 / export 20，F193 模式）；全门复验 tsc 0err + eslint 0err/0warn + jest **400 tests** 全绿（coverageThreshold 99/91/98/99 棘轮下 exit 0）；README 质量门控章节同步

### Added
- **AIChatPanel 强化补测第六批（F232，接手并发轮改动复验落盘）**：接手并发轮未提交改动 — AIChatPanel 4 条强化补测（Markdown 渲染 h2/h3标题+有序列表+行内粗体/斜体/代码与前置普通文本不丢 / 流式渲染 onToken 逐 token 占位消息增量更新 / 打字指示器 400ms 点动画循环与 scroll 定时回调安全触发 / 快捷提问 chip 填值+仪表盘概览 focus 分支双验证）；全仓 396→**400 tests** 全绿，全量覆盖 stmts 96.65→**99.02%** / branches 90.28→**91.92%** / funcs 96.57→**98.28%** / lines 97.13→**99.64%**；coverageThreshold棘轮上调 96/90/96/97→**99/91/98/99**（实测下沿取整，上调后 jest --coverage 复验 exit 0）；接手复验规矩全走：tsc 0err → jest 400绿 → coverage 逐项比对吻合 → eslint 全门复验；README 质量门控章节同步新数

### Added
- **零测试文件补测第五批（F226，接手并发轮改动复验落盘）**：补齐 AIChatPanel（头部/欢迎语/快捷提问/发送走ai.chat/流式渲染/错误兑底）+ AppNavigator（挂载checkAuth/isLoading加载态/未认证入Auth栈渲染LoginScreen/已认证入Main栈四Tab标签齐备默认Dashboard）；全仓 385→**396 tests** 全绿，全量覆盖 stmts 87.03→**96.65%** / branches 83.37→**90.28%** / funcs 88→**96.57%** / lines 87.19→**97.13%**；coverageThreshold棘轮上调 87/83/88/87→**96/90/96/97**（实测下沿留小缓冲）；剩余零测试文件仅 types/index.ts（纯类型定义无可执行逻辑，有效盲区清零）；接手时清理25条lint warning（AppNavigator缺文件级 eslint-disable no-require-imports 头×24 + AIChatPanel改named import消no-named-as-default×1，与既有8个测试文件模式一致）；同步补 F225 遗漏的 README/CHANGELOG 文档账；tsc 0err + eslint 0err/0warn + jest --coverage 全门复验通过；README质量门控章节同步新数
- **零测试文件补测第四批（F225）**：补齐 ProfileScreen（用户卡片/角色映射/空user兑底/设置菜单/退出登录确认+取消+异常静默）+ DashboardScreen（三源拉取/统计API值优先/API失败回退本地口径/营收两位小数/快捷导航/空态/下拉刷新）；全仓 368→**385 tests** 全绿，覆盖 83.6→**87.03%**；coverageThreshold棘轮 83/78/83/83→**87/83/88/87**（文档账由 F226 轮补记）

### Added
- **零测试文件补测第三批（F219，接手并发轮改动复验落盘）**：补齐 StationListScreen（8条：挂载拉取默认参数/卡片三态徽章渲染/告警徽章仅alarmCount>0/点击携带stationId跳详情/搜索提交重拉/下拉刷新refreshing复位/loading指示器/空态文案）+ StationDetailScreen（9条：挂载并行拉详情+设备+告警使用路由stationId/头部渲染/快捷操作跳转/设备列表计数/设备超5台"查看全部设备"跳转/最近告警渲染/双空态/loading指示器/下拉并行重拉refreshing复位）；全仓 351→**368 tests** 全绿，全量覆盖 stmts 80.34→**83.6%** / branches 75.05→**78.8%** / funcs 79.14→**83.71%** / lines 79.94→**83.52%**；coverageThreshold棘轮上调 80/75/79/79→**83/78/83/83**（上调后 jest --coverage --ci 复验通过 exit 0）；剩余 4 个零测试文件（AppNavigator/Dashboard/Profile/types，types纯类型有效目标3个）；接手时清理3条lint warning（两文件多余eslint-disable no-require-imports头+1处未用import TouchableOpacity）；tsc 0err + eslint 0err/0warn + jest --coverage --ci 全门复验通过；README质量门控章节同步新数

### Added
- **零测试文件补测第二批（F213）**：补齐 LoginScreen（资金/认证敏感页，7条：表单渲染/用户名空拦截/密码空白拦截/trim用户名+原始密码透传/Error失败弹服务端文案并复位按钮/非Error失败兜底文案/加载中spinner+按钮禁用挂起探针验证复位）+ MainTabNavigator（2条：五Tab中文标签齐备getAllByText容忍header/title双匹配/默认落首页）；全仓 342→**351 tests** 全绿，全量覆盖 stmts 78.87→**80.34%** / branches 73.77→**75.05%** / funcs 78.28→**79.14%** / lines 78.33→**79.94%**；coverageThreshold棘轮上调 78/73/78/78→**80/75/79/79**（上调后 jest --coverage --ci 复验通过）；剩余 6 个零测试文件（AppNavigator/Dashboard/Profile/StationDetail/StationList/types）待后续测试轮；tsc 0err + eslint 0err/0warn（--max-warnings 0）+ jest --coverage --ci 全门复验通过；README质量门控章节同步新数
- 测试工程要点：jest.mock工厂被hoisting，工厂内引用顶层import会TDZ，须工厂内require（文件级加 eslint-disable no-require-imports，与既有测试模式一致）；mock组件用命名函数避免 react/display-name；加载态断言用 UNSAFE_getAllByType(TouchableOpacity) 取稳定容器引用（文本子节点会卸载致旧引用失效）

### Added
- **零测试文件补测第一批（F207）**：补齐 F201 撞出的 12 个零测试文件中 3 个小组件 — ①LoadingSpinner 4条（默认/自定义文案/空文案隐藏/size+color透传）②ErrorBoundary 4条（正常透传/抛错fallback😵+重试按钮/componentDidCatch日志/重试后恢复渲染，模块级flag确定性控制抛错时机）③NetworkStatus 6条（在线null/网络错误横幅/401视为在线/回前台重新ping/非active态不检查/卸载移除AppState订阅，api.get全mock）；全仓 328→**342 tests** 全绿，全量覆盖 stmts 75.53→**78.87%** / branches 71.54→**73.77%** / funcs 75.14→**78.28%** / lines 74.93→**78.33%**；coverageThreshold棘轮上调 75/71/74.5/74.5→**78/73/78/78**（实测下沿留小缓冲，防回退无声通过）；剩余 8 个零测试文件（AppNavigator/MainTabNavigator/Dashboard/Login/Profile/StationDetail/StationList/types）待后续测试轮；tsc 0err + eslint 0err/0warn（--max-warnings 0）+ jest --coverage --ci 全门复验通过；README质量门控章节同步新数

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
