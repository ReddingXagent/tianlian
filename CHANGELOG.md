# Changelog — tianlian-edge-gateway

格式参考 Keep a Changelog。终端侧网关，云端协议以大圣 tianlian-v3 为准。

## [Unreleased]

### Added
- README.md：架构、环境变量、本地 API、测试与部署说明（自驱文档轮补全，此前仓库无 README）
- 本 CHANGELOG

## 2026-07-31

### Changed
- `b97fe05` lint: 建立 ruff 门控并清零（283→0：273 自动修复 + 6 手工）；剩余债务以 ignore 登记（BLE001×33 最大宗），逐条收窄
- `97ce92d` test: 引入 pytest-timeout，OCPP 套件 `@pytest.mark.timeout(20)` 此前被静默忽略，现真正生效

### Fixed
- `e1b2698` fix(deps): 补 httpx + websockets 缺失依赖（自驱构建轮发现，此前 requirements 声明不全）
