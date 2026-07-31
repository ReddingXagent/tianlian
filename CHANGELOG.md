# Changelog

本项目所有显著变更均记录于此文件。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### Added
- 项目 README：技术栈、功能模块、质量门控（200 用例 / coverage 80.8% / doctor 18/18）、目录结构、Roadmap 缺口（F27/F28/F30/F31/F32/F33）
- 本 CHANGELOG 文件

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
