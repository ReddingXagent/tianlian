# Changelog

本项目所有显著变更均记录于此文件。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### Added
- scripts/bundle-size.sh: JS bundle 体积门控（WARN>2.75MB / FAIL>3.5MB；基线 android 2.19MB / ios 2.18MB hbc）
- Makefile: 新增 bundle-size 目标并接入 ci-local；export 产物体积可门禁
- GitHub Actions CI: export job 增加 bundle-size 门控步骤
- Makefile: 本地构建/检查/导出快捷命令 (help/install/dev/build/test/lint/check/ci-local/clean)
- GitHub Actions CI: .github/workflows/ci.yml 两阶段流水线 (check→export)
- DEPLOYMENT.md: 环境变量使用说明 + Makefile/CI 文档 + OTA 更新步骤

### Changed
- README 质量门控数据更新：243 测试全绿，eslint 0 err / 0 warn，覆盖率 83.62%
- README Roadmap 更新：F17 标记解决，新增 F69/F70/F92 等覆盖薄弱点记录

### Added
- 文档：screen 测试覆盖率明细表（InspectionDetailScreen 57.4% ~ DiagnosisScreen 100%）

### Fixed
- F79: 移除 40 处未使用的 React 默认导入（`4c8a8e7`）
- F86: eslint 警告清零，16→0（`ff9866d`）
- api.ts 全部 `any` 类型已消除，生产代码零 any（`2d462f0`）

### Added (前期)
- 部署链路补齐：eas.json（development/preview-APK/production 三档 profile）
- 品牌占位 assets：icon/adaptive-icon/splash/favicon（蓝底白字 TL，待设计稿替换）
- README 新增「构建与部署」章节（OTA 导出 / EAS 构建命令 + 已知缺口 F22/F24/F25）
- 项目 README：技术栈、功能模块、质量门控、目录结构、Roadmap 缺口说明
- 本 CHANGELOG 文件

## [1.0.0] - 2026-07-30

### Changed
- 移动端依赖对齐 Expo SDK 52：react-native 0.76.6 → 0.76.9（`01fe602`）

### Added
- 建立 eslint 门控（expo flat config），修复 3 处 hook 真问题（`480d0ff`）
- 补 LoadingSpinner / WorkOrderCard 组件测试，coverage 收集范围显式化（`c0a2922`）

### Fixed
- 补 expo-asset 直接依赖，修复 expo export Metro 找不到包（`35c6f84`）

## [0.2.0] - 2026-07

### Added
- B1 工单全流程对齐真云端 API 契约（`8878b6c`）

## [0.1.0] - 2026-07

### Added
- P1 完成：工单流转 / 扫码 / 故障诊断 / 知识库 / 巡检（`e5fff15`）
- 项目初始化（Expo RN + TS）
