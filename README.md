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

基础四门：

```bash
npx tsc --noEmit     # 类型检查 ✅
npm test             # jest 单测（268 用例全绿）
npm run lint         # eslint（0 err / 0 warn）
npx expo export --platform ios   # 产物构建验证
```

- 测试覆盖率（`src/**` 全量口径，F248 起；排除 `*.d.ts` 与 `types/`）：Statements 84.24% | Branches 70.93% | Functions 79.6% | Lines 85.91%
- coverageThreshold 已配置（F348 落地高优卡）：global statements 84 / branches 70 / functions 79 / lines 85，取实测 84.24/70.93/79.6/85.91 下取整（station/user-app 同款下取整惯例），门限棘轮只升不降（F207）
- components / store 层 100% 覆盖；screens 层 15 个页面均已补测试（F17 ✅ 已解决）

`make ci-local` 模拟 CI 全流程 = `make check`（守卫链 + tsc + lint + jest）+ doctor 体检 + 双平台导出 + bundle 体积门控：

**构建守卫族十九枚**（`make check` 内 18 个 check:* 脚本 + bundle-size；每枚均三源接线 package.json↔Makefile↔CI，由 F250 guard-wiring 自动对账，ci-parity 25 门控）：

| 守卫 | 对账语义 | 编号 |
|------|---------|------|
| check:version | package.json.version ↔ app.json.expo.version 双源值级 | F224 |
| check:alias | tsconfig.paths ↔ jest.moduleNameMapper 双源 | F231 |
| check:node | engines.node ↔ CI node-version（逐 job） | F237 |
| check:guard-wiring | 守卫接线三源一致性（自身也在对账范围） | F250 |
| check:env-defaults | 代码读取 env 键 ↔ .env.example 模板键 + 内联 fallback 值级 | F256 |
| check:unused-deps | 未使用依赖（import/plugins/隐式白名单三形态） | F262 |
| check:ci-parity | ci.yml run 步骤 ↔ ci-local 递归展开集合双向 | F274 |
| check:engine-strict | .npmrc engine-strict ↔ engines.node 成对执行力 | F282 |
| check:app-version-source | eas.json appVersionSource=local ↔ app.json versionCode/buildNumber | F288 |
| check:expo-plugins | app.json expo.plugins ↔ package.json 依赖成对 | F296 |
| check:updates-channel | app.json updates.url ↔ eas.json projectId（双占位一致态放行） | F302 |
| check:brand-color | splash.backgroundColor ↔ adaptiveIcon.backgroundColor | F309 |
| check:build-number-parity | android.versionCode ↔ ios.buildNumber 数值配对 | F315 |
| check:easignore-secrets | .gitignore ↔ .easignore 敏感排除超集 | F321 |
| check:unused-assets | assets 磁盘 ↔ 引用源反向对账（死资产） | F327 |
| check:asset-size | assets 体积上限（单文件≤512KB / 总≤2048KB） | F334 |
| check:eas-env | eas.json 构建期 env ↔ .env.example 模板（EXPO_PUBLIC_* 键登记 + 值级，基线空=守卫先行） | F342 |
| check:app-identity | android.package ↔ ios.bundleIdentifier 跨平台身份一致性 | F354 |
| scripts/bundle-size.sh | JS Bundle 体积门控（双平台齐验，缺目录 FAIL） | F212 |

另有 jest 层 appConfig.test.ts 构建配置回归守卫（platforms 限定/plugins↔deps/应用标识双源/资产存在断言，F244 移植形态）。

**expo-doctor 体检**：`make doctor`（依赖版本/配置一致性，与 CI 同步骤）。

## 构建与部署

```bash
npx expo export --platform android   # OTA 更新包（JS bundle + assets）
npx expo export --platform ios       # 同上，iOS 平台
eas build --profile preview          # 内测 APK（EAS 云端构建）
eas build --profile production       # 商店构建
```

- `eas.json`：development / preview(内部 APK) / production 三档 profile
- 分发策略（08-05 决策，F25/F33 清零）：当前阶段不需要 Expo 账号——测试走 Expo Go 扫码，内部分发走 APK 直装/二维码（充电站运维场景不上架商店）；OTA 推送延后到发布候选期，届时 updates.url↔projectId 双侧同步接线（F302 守卫即为此决策的门禁形态）
- `assets/`：icon / adaptive-icon / splash / favicon 品牌占位图（蓝底白字 TL，待设计稿替换）
- 已知缺口：web 导出不可用（纯移动端，无 react-dom，F85 ✅ 确认预期行为）；BASE_URL 硬编码生产 IP 无环境切换（F22）；EAS Update 通道未接（08-05 决策延后到发布候选期，F25/F33 已清零）

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
- **F25**: ~~EAS Update 通道未配，需 Expo 账号~~ → 08-05 决策清零：当前阶段不需要 Expo 账号（测试 Expo Go 扫码/内部分发 APK 直装），OTA 延后到发布候选期
- **F69**: InspectionDetailScreen 覆盖 57.4%、ScanScreen 65.62%、WorkOrderDetailScreen 65.45% 为薄弱 Screen
- **F70**: AppNavigator 0% 覆盖（导航层，测试成本高）
- **F74**: WorkOrderDetailScreen 测试有 act() 警告（不影响通过）
- **F82**: LoginScreen Animated act() 警告（不影响测试通过）
- **F86**: Branches 覆盖 71.65%，较上轮 64.19% 提升
- **F92**: InspectionDetailScreen 为本仓覆盖最薄弱 Screen（57.4%）

## 领域边界

本仓库属天链**终端 app** 领域（猴王负责）。云端后端 `tianlian-v3` 为独立领域，云端配合走大圣。
