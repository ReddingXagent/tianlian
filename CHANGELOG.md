# Changelog — tianlian-edge-gateway

格式参考 Keep a Changelog。终端侧网关，云端协议以大圣 tianlian-v3 为准。

## [Unreleased]

### Added
- `tianlian-edge-gateway.service`: systemd 单元（开机自启 + Restart=on-failure + StartLimitBurst=3/60s）
- `.env.example`: 全量环境变量模板，18 个 key 与 `config.py` `os.getenv` 精确对齐
- `Makefile`: venv/install/run/test/lint/check/clean/deploy 开发快捷命令
- README.md：架构、环境变量、本地 API、测试与部署说明（自驱文档轮补全，此前仓库无 README）
- 本 CHANGELOG
- README 补充故障排查（troubleshooting）段和配置文件说明
- README 补全环境变量表（STORAGE_DB_PATH/LOG_LEVEL/MQTT_CLIENT_ID）和 .env 文件段

## 2026-08-01

### Changed
- `95cb038` style(lint): 修复 W292（EOF 缺换行×9）+ E501（行过长×6）
- `b3f8f22` fix(deploy): deploy.sh v3 — 端口释放等待循环 + 启动重试 + 健康轮询（解决旧进程杀后端口未释放致 bind 失败）
- `8ef586c` fix(deploy): .env 从未加载到环境变量——deploy.sh 启动前 source .env；kill -9 兜底确保端口释放
- `65faebd` fix(py310-compat): StrEnum→(str, Enum) 回退（Pi Python 3.10 无 StrEnum）
- `3da23cb` fix(py310-compat): datetime.UTC→timezone.utc（Pi 3.10 兼容）；deploy.sh 语法修复；pyproject target py310 + ignore UP017
- `192192a` fix(deploy): 修复 deploy.sh 两处语法损坏（REMOTE= 赋值被截断）

## 2026-07-31

### Changed
- `0f1c94f` lint(F841/UP035/UP042): 清零 3 类 ruff 债务（F841×4 unused-var 删除 / UP035×3 typing→collections.abc / UP042×11 str+Enum→StrEnum）；pyproject.toml ignore 列表同步移除 3 项
- `b97fe05` lint: 建立 ruff 门控并清零（283→0：273 自动修复 + 6 手工）；剩余债务以 ignore 登记（BLE001×29 生产 blind-except，逐条收窄），pyproject.toml 门控配置落定
- `97ce92d` test: 引入 pytest-timeout，OCPP 套件 `@pytest.mark.timeout(20)` 此前被静默忽略，现真正生效

### Fixed
- `e5bf45e` fix(F7): test_heartbeat_loop_cancelled 未 mock httpx，导致测试间网络泄漏
- `e1b2698` fix(deps): 补 httpx + websockets 缺失依赖（自驱构建轮发现，此前 requirements 声明不全）
