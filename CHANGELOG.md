# Changelog — tianlian-edge-gateway

格式参考 Keep a Changelog。终端侧网关，云端协议以大圣 tianlian-v3 为准。

## [Unreleased]

### Fixed
- `systemd/tianlian-gateway.service`: 移除 `ProtectHome=read-only`（SQLite DB 在 /home 下，只读会导致写库全面失败）
- `scripts/watchdog.sh`: REPO_DIR 误指向 scripts/ → pgrep 永不匹配真实网关进程，看门狗形同虚设；改为仓库根

### Added
- `DEPLOYMENT.md`: 部署运行手册（deploy.sh/systemd/Docker 三方式 + watchdog + 踩坑记录 + 已知问题）


### Added
- `docs/API_REFERENCE.md`: 完整 API 参考手册（8 端点，含请求/响应示例 + curl 快速验证）
- `docs/DEVELOPMENT.md`: 开发贡献指南（环境搭建 / 项目结构 / 核心概念 / 扩展指南 / 测试规范）
- README: 新增「更多文档」导航段 + 目录结构补 docs/
- deploy.sh: `rollback` 子命令（`bash deploy.sh rollback <commit-hash>` 安全回滚）
- deploy.sh: `status` 子命令（快速查看 PID/健康检查/状态API/日志尾部）
- Dockerfile: `$BUILDPLATFORM`/`TARGETPLATFORM` 多架构支持（ARM64 Pi + AMD64 开发机）
- Makefile: `docker-build`/`docker-up`/`docker-down`/`docker-logs`/`docker-shell` Docker 快捷命令
- Makefile: `deploy-rollback` 目标（`make deploy-rollback REV=<hash>`）

### Changed
- Dockerfile: `FROM --platform=$BUILDPLATFORM` 支持多架构构建（buildx 多平台镜像）
- Makefile: `.PHONY` 补全 Docker + rollback 目标

### Added (历史)
- `Dockerfile`: 多阶段构建（python:3.10-slim + 非 root 运行 + HEALTHCHECK 健康检查 + 数据卷持久化）
- `docker-compose.yml`: 一键容器化部署（restart:unless-stopped + 日志轮转 + 时区同步 + 持久化卷）
- `.dockerignore`: 排除 .venv/.git/data 等，优化构建上下文
- `scripts/watchdog.sh`: 看门狗脚本（健康检查 + 自动重启 + 连续3次失败告警；支持 crontab 单次模式和 --loop 常驻模式）
- `systemd/tianlian-gateway.service`: systemd unit（Restart=always + RestartSec=5 + 安全加固 NoNewPrivileges/ProtectSystem/PrivateTmp）
- `systemd/README.md`: systemd 安装/管理/从 deploy.sh 迁移指南
- `systemd/logrotate.conf`: gateway.log 日志轮转（daily/rotate7/compress/copytruncate）
- deploy.sh: systemd 检测+迁移建议 / 日志轮转提示
- Makefile: systemd-install/start/stop/restart/status/logs 快捷命令
- `tianlian-edge-gateway.service`（旧记录）: systemd 单元初版
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
