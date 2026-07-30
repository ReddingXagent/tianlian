# Changelog

本项目所有显著变更均记录于此文件。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### Added
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
