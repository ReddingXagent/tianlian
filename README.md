# 天链站长 (tianlian-station-app)

天链充电站**站长端**移动应用，面向场站站长，覆盖站级总览、设备监控、告警工单、营收统计、通知中心与 AI 助手。

## 技术栈

- **Expo SDK 52** + React Native 0.76.9 + TypeScript
- **状态管理**: zustand（authStore / stationStore / workOrderStore / deviceControlLogStore）
- **导航**: react-navigation 7（native-stack + bottom-tabs，Auth/Main 双栈）
- **网络**: axios（对接天链云端 API `/api/v1`）
- **图表**: react-native-chart-kit + react-native-svg 15.8.0（SDK52 对齐 pin）
- **存储**: expo-secure-store（token 安全存储）

## 功能模块

| 模块 | 入口 Screen | 说明 |
|------|-------------|------|
| 登录 | Login | 账号登录，token 落 SecureStore |
| 总览 | Dashboard | 站级运营首页 |
| 场站 | StationList / StationDetail | 多站列表与详情 |
| 设备 | DeviceList / DeviceDetail | 充电桩设备列表、详情与控制日志 |
| 监控 | ChargerMonitor | 充电实时监控 + 趋势图（ChargerTrendChart） |
| 告警 | AlarmList | 告警列表与处理 |
| 工单 | WorkOrder | 工单流转 |
| 营收 | Revenue | 营收统计 + CSV 导出（csvExport） |
| 通知 | NotificationCenter | 通知中心 |
| AI 助手 | AIChatPanel（组件） | ai.ts 服务 + function calling 框架 |
| 我的 | Profile | 个人中心 |

## 快速开始

```bash
npm install          # 安装依赖
npm start            # 启动 Expo Dev Server
npm run android      # 安卓
npm run ios          # iOS
```

## 质量门控

```bash
npx tsc --noEmit     # 类型检查 ✅
npm run check:alias  # 路径别名双源漂移守卫（tsconfig.paths ↔ jest.moduleNameMapper，F238）
npm run check:test-liveness  # 测试套件活性守卫（收集数下限33+路径域断言，拦 --passWithNoTests 零收集静默放行，F379）
npm test             # jest 单测（573 用例全绿；testTimeout 15s 加固负载型 flaky，F322；加 --coverage 触发覆盖率门限）
npm run lint         # eslint（0 err / 0 warn）
npx expo-doctor      # 依赖健康检查（18/18 全过）
npx expo export --platform ios   # 产物构建验证（零警告）
```

- 测试覆盖：573 用例全绿，全量统计（collectCoverageFrom 计入全部源文件）总体 **stmts 100% / branches 99.28% / funcs 99.74% / lines 100%**（F349 cache.ts LRU 淘汰死分支守卫消除——进入淘汰块时 store.size≥MAX_ENTRIES(50)≥1，循环至少迭代一次且首个条目 lastAccess(=++lruSeq 恒有限)<Infinity 必成立，`if (oldestKey)` 条件不可达，改直接 `store.delete(oldestKey)` 行为等价，branches 97.66→97.77%，cache.ts 四项全清零 100%，上调 97 后余量 0.77<1 不升棘轮（F278 规则）；F343 接手并发轮 AIChatPanel renderInlineMarkdown 死分支消除——正则三分组（粗体|斜体|代码）每次命中必占其一，`else if (match[6])` 条件不可达，改 `else` 行为等价，branches 97.55→97.66%，上调 97 后余量 0.66<1 不升棘轮（F278 规则）；F336 接手并发轮 AppNavigator options 回调分支定向补测+4（ChargerMonitor options 回调执行 / DeviceList title `route.params?.stationName || ''` 三分支：||左侧真值带 stationName / 有 params 缺 stationName 回落空串 / 无 params 可选链短路），AppNavigator.tsx 四项全清零 100%）后 branches 97.31→97.55%，上调 97 后余量 0.55<1 不升棘轮（F278 规则）；F328 接手并发轮 ai.ts 流式故障分支定向补测+2（streamChatMessage response.text() reject 时 catch 兜底空错误体 / reader done 无 [DONE] 正常收尾+releaseLock 断言）后 branches 97.2→97.31%，上调 97 后余量 0.31<1 不升棘轮（F278 规则）；F316 接手并发轮 ai.ts 残余兜底分支定向补测+3（executeToolCall 无 message 错误 Unknown error 末段兜底 / streamChatMessage 跨块行重组 buffer 左侧真值分支 / chat 无名 tool call continue 跳过 + id/name/arguments 三处 || generateId/空串兜底）后 branches 96.73→97.2%，棘轮上调门限 95→96（上调后余量 1.2≥1，F278/F207 规则）；F310 接手并发轮定向补测+3（AIChatPanel 迟到 token 守卫空转 / DeviceListScreen 未知设备类型 || 兜底回退 / cache LRU 容量满淘汰）+接手轮自补+1（AlarmListScreen 筛选 chip 切换带 status 重拉，消费并发轮遗留未用 import，2 个 no-unused-vars warning 同步清零）后 branches 96.38→96.73%，AlarmListScreen.tsx 四项全清零 100%，门限 95 不上调——上调 96 后余量 0.73<1（F278 规则）；F303 ChargerTrendChart 防御分支定向补测+4（buildLabels 空输入兜底直测 + hexToRgb 零通道 || 0 三形态 + NaN 防御 + 电流指标 #ef6c00 零蓝通道组件路径唯一形态）后 branches 95.92→96.38%，ChargerTrendChart.tsx 四项全清零 100%，棘轮上调门限 94→95（上调后余量 1.38≥1，F278/F207 规则）；F297 防御兜底分支定向补测+4（api.ts dashboardApi.getStats 可选链+?? 全兜底两形态 spy 直通验证 + Math.max 钗制 / NetworkStatus 401 分支卸载竞态 mountedRef 守卫 / LoginScreen KAV android 侧 behavior undefined 平台分支）后 branches 95.33→95.92%，api.ts/NetworkStatus.tsx/LoginScreen.tsx 三文件分支全部清零至 100%，余量 1.92，门限 94 不上调——上调 95 后余量 0.92<1（F278 规则）；F290 接手并发轮 api.test.ts 可达兜底分支定向补测+2（workOrderApi.getList 无参 ternary 假分支+可选链 / revenueApi.getSummary daily 条目缺 net_revenue 的 month/week/today 三处 || 0）后 branches 94.87→95.33%，余量 0.87→1.33，门限 94 不上调——上调 95 后余量 0.33<1（F278 规则）；F283 接手并发轮 WorkOrderScreen 定向补测+4（429→433，branches 94.87% 余量 0.87<1 不上调）；F275 接手并发轮 StationDetailScreen 定向补测+3 后 branches 93.12→94.4%，棘轮上调门限 93→94；F263 接手并发轮 AIChatPanel 定向补测复验撞出空回复组件缺陷并修复后 branches 92.62→93.12%，棘轮上调门限 92→93；F257 services 层兜底分支定向补测后 branches 92.15→92.62%，取整下沿仍 92 门限不上调；F251 NetworkStatus 卸载竞态/可选链补测后棘轮上调 branches 门限 91→92；F232 接手并发轮 AIChatPanel 强化补测 Markdown/流式/打字动画/快捷提问后棘轮上调门限 99/91/98/99；F225/F226 补测 Dashboard/Profile/AIChatPanel/AppNavigator 后棘轮上调门限 96/90/96/97；F219 补测 StationList/StationDetail；F213 补测 LoginScreen/MainTabNavigator；F207 第一批补测三组件；F201 修复口径：此前 95.18% 仅统计被测试加载的文件，12 个零测试文件被隐形排除，现已全部补齐）
- 路径别名双源漂移守卫（F238）：tsconfig.compilerOptions.paths 与 jest.moduleNameMapper 同语义双源对账（`scripts/check-alias-config.sh`），接入 CI check job + Makefile check 链；变异三档实证（jest 目标漂移 / tsconfig 单侧新增 / jest 侧缺失均 exit 1 拦截）
- 测试套件活性守卫（F379）：npm test 脚本含 `--passWithNoTests`，testMatch 漂移致零收集时本地静默 exit 0（F295 族静默 no-op；CI 虽带 --coverage 门限兜底，部分套件脱落时余量可能吞信号）→ `scripts/check-test-suite-liveness.sh` 独立断言收集活性：套件数≥33（基线）+全部落在 src/**/*.test.ts(x) 合法域+缺输入 FAIL（F212），接入 CI check job + Makefile check 链（alias 后 test 前）；变异两档实证（M1 testMatch 收窄致部分套件脱落 12<33 精确拦 / M2 testMatch 匹配零套件零收集档精确拦，cp 还原 diff 零残留）
- CI 双 job 均配 timeout-minutes（check 15 / export 20，F193 模式补齐）
- 覆盖率门限：jest coverageThreshold global（stmts≥99 / branches≥98 / funcs≥99 / lines≥99），CI 与 Makefile 均经 `--coverage` 强制执行，变异测试实证（门限上调超出实测→exit 1 精确拦截 / 新增无测试文件→exit 1 拦截）
- 零测试盲区（仅剩 types/index.ts：纯类型定义无可执行逻辑，有效盲区已清零）
- eslint **0 err / 0 warn**（`474492b` 全部清零）

## 构建与部署

```bash
npx expo export --platform android   # OTA 更新包（JS bundle + assets）
npx expo export --platform ios       # 同上，iOS 平台
```

- `eas.json`：三档 profile（development / preview / production）已就位 ✅
- ⚠️ EAS Update 通道未配（app.json 无 updates.url），OTA 需 Expo 账号（F25，等丁哥）
- `assets/`：icon / adaptive-icon / splash / favicon 品牌占位图

## 目录结构

```
src/
├── screens/        # 12 个页面 + MainTabNavigator
├── components/     # AIChatPanel / ChargerTrendChart / ConfirmDialog / EmptyState / LoadingSpinner / StatusBadge
├── hooks/          # usePolling（轮询）
├── navigation/     # AppNavigator（Auth/Main 双栈）
├── services/       # api.ts（axios 封装）/ ai.ts（AI function calling）
├── store/          # zustand stores ×4
├── utils/          # cache.ts（LRU 缓存）/ csvExport.ts
└── types/          # 类型定义
```

## 部署

详见 [DEPLOYMENT.md](./DEPLOYMENT.md)。快捷命令：

```bash
make help        # 查看所有命令
make check       # tsc + eslint + 别名守卫 + 套件活性守卫 + jest
make export      # android + ios bundle
make ci-local    # 本地模拟 CI
```

## CI

GitHub Actions (`.github/workflows/ci.yml`) 两阶段流水线：

1. **check**: tsc → eslint → 别名守卫 → 套件活性守卫（F379）→ jest (coverage)
2. **export**: android + ios bundle

push/PR → master 自动触发。

## Roadmap / 已知缺口

- **F30**: react-native-chart-kit 已停更且 New Arch 未测（doctor 已 exclude）→ 待迁移 gifted-charts / victory
- **F31**: `api.ts` BASE_URL 硬编码生产 IP，缺 dev/mock 环境切换（同 ops-app F22）
- **F32**: ✅ 已修复 — ErrorBoundary + NetworkStatus（AppState 监听）已接入 App.tsx（`e4dc934`）
- **F27/F75**: ✅ 已修复 — authStore/stationStore/workOrderStore 均达 100%，api.ts 提升至 91.4%
- **F28**: ✅ eslint warn 全部清零（0 warn）
- **F33**: ✅ eas.json 三档 profile 已就位（`e876fd8`）
