# 天链运维 (tianlian-ops-app)

天链充电站**运维端**移动应用，面向场站运维人员，覆盖工单全流程、扫码巡检、故障诊断、知识库与监控看板。

## 技术栈

- **Expo SDK 52** + React Native 0.76 + TypeScript
- **状态管理**: zustand（authStore / workOrderStore / inspectionStore / dashboardStore）
- **导航**: react-navigation（native-stack + bottom-tabs）
- **网络**: axios（对接天链云端 API `/api/v1`）
- **存储**: expo-secure-store（token 安全存储）

## 功能模块

| 模块 | 入口 Screen | 说明 |
|------|-------------|------|
| 工作台 | Workbench | 运维首页，快捷入口聚合 |
| 工单 | WorkOrders / WorkOrderDetail / Create / Transfer | 工单列表、详情、创建、转派全流程 |
| 扫码 | Scan | 设备扫码定位（当前手动输码，见 Roadmap F21） |
| 巡检 | Inspection / InspectionDetail | 巡检计划与执行 |
| 监控 | Monitor | 设备实时状态 |
| 看板 | Dashboard | 运维数据统计 |
| 诊断 | Diagnosis | 故障诊断辅助 |
| 知识库 | Knowledge / KnowledgeDetail | 运维知识检索 |
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
npm test             # jest 单测（243 用例全绿）
npm run lint         # eslint（0 err / 0 warn）
npx expo export --platform ios   # 产物构建验证
```

- 测试覆盖率：Statements 83.62% | Branches 71.65% | Functions 77.34% | Lines 85.39%
- coverage 收集范围：`src/**`（排除 `*.d.ts` 与 `types/`）
- components / store 层 100% 覆盖；screens 层 15 个页面均已补测试（F17 ✅ 已解决）

## 构建与部署

```bash
npx expo export --platform android   # OTA 更新包（JS bundle + assets）
npx expo export --platform ios       # 同上，iOS 平台
eas build --profile preview          # 内测 APK（需 EAS 账号）
eas build --profile production       # 商店构建
```

- `eas.json`：development / preview(内部 APK) / production 三档 profile
- `assets/`：icon / adaptive-icon / splash / favicon 品牌占位图（蓝底白字 TL，待设计稿替换）
- 已知缺口：web 导出不可用（纯移动端，无 react-dom，F85 ✅ 确认预期行为）；BASE_URL 硬编码生产 IP 无环境切换（F22）；EAS Update 通道未配（需账号，F25）

## 目录结构

```
src/
├── screens/        # 15 个页面
├── components/     # 通用组件（StatusBadge/WorkOrderCard/EmptyState/LoadingSpinner）
├── hooks/          # usePolling 等
├── navigation/     # AppNavigator（Auth/Main 双栈）
├── services/       # api.ts（axios 封装）
├── store/          # zustand stores
└── types/          # 类型定义
```

## Roadmap / 已知缺口

- **F21**: ScanScreen 为手动输码，缺 expo-camera 真扫码能力
- **F22**: `api.ts` BASE_URL 硬编码生产 IP，缺 dev/mock 环境切换
- **F25**: EAS Update 通道未配，需 Expo 账号
- **F69**: InspectionDetailScreen 覆盖 57.4%、ScanScreen 65.62%、WorkOrderDetailScreen 65.45% 为薄弱 Screen
- **F70**: AppNavigator 0% 覆盖（导航层，测试成本高）
- **F74**: WorkOrderDetailScreen 测试有 act() 警告（不影响通过）
- **F82**: LoginScreen Animated act() 警告（不影响测试通过）
- **F86**: Branches 覆盖 71.65%，较上轮 64.19% 提升
- **F92**: InspectionDetailScreen 为本仓覆盖最薄弱 Screen（57.4%）

## 领域边界

本仓库属天链**终端 app** 领域（猴王负责）。云端后端 `tianlian-v3` 为独立领域，云端配合走大圣。
