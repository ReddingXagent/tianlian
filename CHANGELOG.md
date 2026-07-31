# Changelog — tianlian-edge-gateway

格式参考 Keep a Changelog。终端侧网关，云端协议以大圣 tianlian-v3 为准。

## [Unreleased]

### Added
- README.md：架构、环境变量、本地 API、测试与部署说明（自驱文档轮补全，此前仓库无 README）
- 本 CHANGELOG
- README 补充故障排查（troubleshooting）段和配置文件说明

## 2026-07-31

### Changed
- `0f1c94f` lint(F841/UP035/UP042): 清零 3 类 ruff 债务（F841×4 unused-var 删除 / UP035×3 typing→collections.abc / UP042×11 str+Enum→StrEnum）；pyproject.toml ignore 列表同步移除 3 项
- `b97fe05` lint: 建立 ruff 门控并清零（283→0：273 自动修复 + 6 手工）；剩余债务以 ignore 登记（BLE001×29 生产 blind-except，逐条收窄），pyproject.toml 门控配置落定
- `97ce92d` test: 引入 pytest-timeout，OCPP 套件 `@pytest.mark.timeout(20)` 此前被静默忽略，现真正生效

### Fixed
- `e5bf45e` fix(F7): test_heartbeat_loop_cancelled 未 mock httpx，导致测试间网络泄漏
- `e1b2698` fix(deps): 补 httpx + websockets 缺失依赖（自驱构建轮发现，此前 requirements 声明不全）
