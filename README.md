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
npm test             # jest 单测（200 用例全绿，coverage 80.8%）
npm run lint         # eslint（0 err / 84 warn）
npx expo-doctor      # 依赖健康检查（18/18 全过）
npx expo export --platform ios   # 产物构建验证（零警告）
```

- 测试覆盖：screens / components / hooks / services / store / utils 六层全覆盖
- 覆盖薄弱点（F27）：authStore 45%（branch 0%）/ stationStore+workOrderStore branch 25% / WorkOrderScreen 60% / NotificationCenter 69% / api.ts 73%
- warn 分布（F29）：require-imports×48 + unused-vars×23 + set-state-in-effect×10 + 其他×3

## 构建与部署

```bash
npx expo export --platform android   # OTA 更新包（JS bundle + assets）
npx expo export --platform ios       # 同上，iOS 平台
```

- ⚠️ 尚未配置 `eas.json`（F33）：原生 APK/IPA 构建需补 EAS profile（development/preview/production）
- ⚠️ EAS Update 通道未配（app.json 无 updates.url），OTA 需账号配置
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

## Roadmap / 已知缺口

- **F30**: react-native-chart-kit 已停更且 New Arch 未测（doctor 已 exclude）→ 待迁移 gifted-charts / victory
- **F31**: `api.ts` BASE_URL 硬编码生产 IP，缺 dev/mock 环境切换（同 ops-app F22）
- **F32**: 无 AppState / NetInfo 接入 → usePolling 后台不暂停（耗电/流量）+ 无离线检测
- **F27**: 覆盖率薄弱点见「质量门控」章节
- **F28**: 10 处 set-state-in-effect warn，待 screen 测试补齐后逐处收敛
- **F33**: 缺 eas.json，原生构建链路未建立
