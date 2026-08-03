# Changelog

本项目所有显著变更均记录于此文件。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### Added
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
- README 同步最新质量指标（coverage 93.46%、267 tests、eslint 0 warn）

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
