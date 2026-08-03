# Changelog

本项目所有显著变更均记录于此文件。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### Changed
- CI健壮性加固: ①两job补 `timeout-minutes`(check=15/export=20) — 此前无超时, 挂死的export最多吃满GitHub默认6h runner; ②export job补 `upload-artifact`(always, 保留7天) — bundle-size回归/导出异常时可直接下载双平台hbc+资产取证, 门控失败也留现场(if: always); ③YAML解析+结构断言校验通过(timeout/artifact字段实测确认)

### Fixed
- bundle-size.sh 平台识别bug: `find | head -1` 不区分平台子目录, 同目录双平台(如 `dist/`)时 ios 误报 android 体积 → 改按 `_expo/static/js/<platform>/` 定位, 兼容旧布局单hbc兜底; 实测 `bundle-size.sh dist dist` android 2.19MB / ios 2.18MB 正确区分
- F167: `npm run build` 实际必挂 — `expo export` 默认含 web 平台但项目无 react-native-web/react-dom 依赖；app.json 加 `platforms: ["android","ios"]` 并移除无用的 web.favicon 配置，实测 build 全绿（android 2.3MB / ios 2.29MB）

### Changed
- expo-doctor 接入门禁自动化: CI check job 增加 `npx expo-doctor` 步骤 + Makefile 新增 `make doctor` 目标并接入 ci-local（此前 doctor 仅手动体检, 版本漂移无回归防护）; bundle-size.sh 门控加固 — 双平台导出目录都缺失时由静默通过改 FAIL（门控无对象可测不应放行）; 实测 doctor 18/18 全绿 + bundle-size 正常路径 android 2.19MB / ios 2.18MB 不受影响
- 构建依赖健康检查: 引入 `npx expo-doctor` 作为构建维度体检项 — 撞出 eslint-config-expo 与 SDK 版本漂移(doctor期望SDK52→~8.0.1); 实测8.0.1为legacy eslintrc配置(无 `/flat` 导出, 与本仓ESLint 9 flat config不兼容, require直接报错) → 保留57.0.1(flat原生, lint实测0 err/0 warn), package.json 钉 `expo.install.exclude: [eslint-config-expo]` 并向doctor声明该豁免, doctor复验18/18全绿
- Makefile ci-local 补 export-ios（原仅 android, 本地模拟CI漏掉iOS体积门控）; lint 目标改 `npm run lint` 与 CI 对齐（原 `eslint src/ --ext` 范围不一致）; clean 补删 `dist/`（npm run build 产物目录）

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
