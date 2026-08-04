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
npm test             # jest 单测（400 用例全绿；加 --coverage 触发覆盖率门限）
npm run lint         # eslint（0 err / 0 warn）
npx expo-doctor      # 依赖健康检查（18/18 全过）
npx expo export --platform ios   # 产物构建验证（零警告）
```

- 测试覆盖：400 用例全绿，全量统计（collectCoverageFrom 计入全部源文件）总体 **stmts 99.02% / branches 91.92% / funcs 98.28% / lines 99.64%**（F232 接手并发轮 AIChatPanel 强化补测 Markdown/流式/打字动画/快捷提问后棘轮上调门限 99/91/98/99；F225/F226 补测 Dashboard/Profile/AIChatPanel/AppNavigator 后棘轮上调门限 96/90/96/97；F219 补测 StationList/StationDetail；F213 补测 LoginScreen/MainTabNavigator；F207 第一批补测三组件；F201 修复口径：此前 95.18% 仅统计被测试加载的文件，12 个零测试文件被隐形排除，现已全部补齐）
- 覆盖率门限：jest coverageThreshold global（stmts≥99 / branches≥91 / funcs≥98 / lines≥99），CI 与 Makefile 均经 `--coverage` 强制执行，变异测试实证（新增无测试文件→exit 1 拦截）
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
make check       # tsc + eslint + jest
make export      # android + ios bundle
make ci-local    # 本地模拟 CI
```

## CI

GitHub Actions (`.github/workflows/ci.yml`) 两阶段流水线：

1. **check**: tsc → eslint → jest (coverage)
2. **export**: android + ios bundle

push/PR → master 自动触发。

## Roadmap / 已知缺口

- **F30**: react-native-chart-kit 已停更且 New Arch 未测（doctor 已 exclude）→ 待迁移 gifted-charts / victory
- **F31**: `api.ts` BASE_URL 硬编码生产 IP，缺 dev/mock 环境切换（同 ops-app F22）
- **F32**: ✅ 已修复 — ErrorBoundary + NetworkStatus（AppState 监听）已接入 App.tsx（`e4dc934`）
- **F27/F75**: ✅ 已修复 — authStore/stationStore/workOrderStore 均达 100%，api.ts 提升至 91.4%
- **F28**: ✅ eslint warn 全部清零（0 warn）
- **F33**: ✅ eas.json 三档 profile 已就位（`e876fd8`）
