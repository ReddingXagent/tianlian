# Changelog — tianlian-edge-gateway

格式参考 Keep a Changelog。终端侧网关，云端协议以大圣 tianlian-v3 为准。

## [Unreleased]

### Added
- `scripts/check-log-paths.sh` (F261): 日志路径双源漂移守卫 — nohup模式日志写侧 deploy.sh 重定向目标(`nohup ... > gateway.log`)与 scripts/watchdog.sh LOG_FILE, 轮转侧 systemd/logrotate.conf 轮转目标, 两侧独立维护零断言: 任一侧单独改文件名→logrotate 轮转不存在路径(missingok 静默跳过)→真实日志无人轮转→Pi 磁盘被日志写满(静默, 边缘设备最恶故障); 另断言 logrotate 路径目录段 == unit WorkingDirectory 默认值(两段共用 make systemd-install 的 sed 渲染占位符, 目录段漂移→渲染不到→装出的轮转仍指旧路径) → 脚本断言轮转↔deploy↔watchdog basename 三源一致 + 目录段对账, 缺输入(F212不放行)/提取空/不等均 exit 1; unit模板路径取自 deploy.sh UNIT_FILE 默认值(F236已守三源同名)不硬编码; 接入 `make check`(log-paths-check target, check链委托单一源) + CI check job; 变异五档实测(deploy写侧改名/logrotate轮转目标改名/watchdog写侧改名/logrotate目录段漂移/mv走logrotate.conf缺输入均精确拦 exit 1, 每档 sed 反向还原后基线 exit 0 零残留); bash -n + YAML解析 + make -n OK; pytest 232绿; 顺手清 ruff 2债务(test_api.py I001 import排序 + PIE807 lambda→dict, 基线登记在案债务清零, make check 全绿)
- `scripts/check-env-keys.sh` (F255): 环境变量键名双源一致性守卫 — 读取侧 config.py os.getenv 键集合(20键: GATEWAY_*/CLOUD_*/MQTT_*/MODBUS_*/OCPP_*/STORAGE_DB_PATH/LOG_LEVEL, 代码实际读取的权威源) ↔ 模板侧 .env.example 键清单(部署者照抄模板, compose env_file: .env 由部署者从.example复制), 双源同名零断言: 代码新增 os.getenv 键而 .example 未登记→部署者漏配静默吃默认值(如 CLOUD_TOKEN 漏配→云端认证失败排障无从下手)/.example 残留代码已不读取的死键→误导部署者配置无效项 → 脚本提取两侧键集合双向对账(comm 双向差集), 缺输入/提取空/不等均 exit 1(F212不放行); 接入 `make check`(env-keys-check target, check链委托单一源) + CI check job; 变异三档实测(config.py 新增 os.getenv 键精确拦 exit 1 / .env.example 追加死键精确拦 exit 1 / mv走 .env.example 缺输入拦 exit 1, 每档 sed 反向还原后基线 exit 0 且 git diff 零残留); bash -n + YAML解析 + make -n OK; pytest 232绿
- `scripts/check-api-port.sh` (F249): API端口多源一致性守卫 — 声明侧 config.py LocalAPIConfig.port(api/server.py 实际 listen 端口), 探测/发布侧 deploy.sh PORT 默认值/docker-compose ports 映射/Dockerfile EXPOSE/Dockerfile HEALTHCHECK 探测端口, 多源同名零断言: 任一侧单独改端口→deploy.sh 健康探测旧端口永不亮(健康服务被报部署失败)/Docker HEALTHCHECK 探测旧端口=容器反复判不健康 → 脚本以声明侧默认值对账四源, 缺输入/提取空/不等均 exit 1(F212不放行); 接入 `make check`(api-port-check target, check链委托单一源) + CI check job; 变异四档实测(config.py声明侧改名精确拦 exit 1 / deploy.sh探测侧改名精确拦 exit 1 / Dockerfile HEALTHCHECK 改名精确拦 exit 1 / mv走 docker-compose.yml 缺输入拦 exit 1, 每档 sed 反向还原后基线 exit 0); bash -n + YAML解析 + make -n OK; pytest 232绿
- `scripts/check-deploy-endpoints.sh` (F243): 部署探测端点一致性守卫 — deploy.sh 部署成功判定(HEALTH_OK循环)+status子命令探测 `http://localhost:$PORT/health` 与 `/api/v1/status`, 路由声明在 api/server.py(@app.get装饰器), 两侧独立维护零断言: 服务端路由单独改名→部署成功判定循环永远不亮(健康服务被报部署失败)/status"不可达"; 探测侧单独改错→同果 → 脚本提取deploy.sh探测路径集合(排除$(hostname)展示行), 断言全部∈server.py声明路由集合, 任一侧缺输入/提取空/不一致均exit 1(F212不放行); 接入 `make check`(deploy-endpoints-check target, check链委托单一源) + CI check job; 变异三档实测(服务端/health→/healthz精确拦exit 1 / 探测侧/health→/healthcheck精确拦exit 1 / mv走server.py缺输入拦exit 1, 每档sed反向还原后基线exit 0); bash -n + YAML解析 + make -n OK; pytest 232绿

### Added
- `scripts/check-deploy-names.sh` (F236): 部署同名源一致性守卫 — SYSTEMD_MODE探测(F217/F230退位守卫)依赖 deploy.sh/watchdog.sh 的 UNIT_FILE 默认值与 Makefile systemd-install 实际安装路径**精确同名**, 三处任一单独改名→unit已装但探测失配→退位守卫整体失效(kill+nohup撞systemd Restart=always重启风暴); logrotate同理(Makefile安装名 vs deploy.sh部署尾提示探测名漂移→提示误报/漏报) → 脚本对账unit三源+logrotate双源, 不一致即exit 1, 并断言unit模板 systemd/<basename> 存在; 接入 `make check`(deploy-names-check target) + CI check job; 变异两档实测(watchdog UNIT_FILE改名→三源漂移精确拦截exit 1 / Makefile logrotate安装名改名→双源漂移精确拦截exit 1, 基线exit 0); pytest 232绿

### Fixed
- `scripts/watchdog.sh` (F230): systemd模式退位守卫 — F217同族漏网点: unit已装时systemd接管进程生死(Restart=always), watchdog仍按cron/loop定时kill+nohup重启: ①杀卡死进程后unit 5秒内复活, 与nohup第二实例撞端口(重启风暴); ②.pid被改写指向nohup实例, systemd实例失联 → 与deploy.sh一致的SYSTEMD_MODE探测(unit文件存在, `TIANLIAN_UNIT_FILE`可覆盖测试钩子), 命中即记日志+exit 0整体退位, 绝不启动第二进程, 恢复交给Restart=always; 变异三档实测(unit存在→exit 0+退位日志+未进flock/unit不存在+健康→过守卫正常exit 0零退位日志/bash -n通过); README+DEPLOYMENT.md同步说明

### Fixed
- `deploy.sh` rollback (F223): 迁移盲区守卫 — rollback只revert代码, 若回滚范围内含 db_migration.py 变更, 数据库schema已被新版本前移, revert后直接 `bash deploy.sh` 重部署会让旧代码跑在新schema上(“no such column”崩/数据错乱)且全程零提示 → revert前探测范围内迁移commit(`git log RANGE -- db_migration.py`), 命中即醒目警告+引导 `restore-db` 恢复迁移前备份并列出可用备份; 变异三档实测(范围含迁移commit→精确警告含commit清单/范围无迁移commit→零警告行为不变/ bash -n 语法通过); pytest 232绿

### Fixed
- `deploy.sh` (F217): 双模式冲突守卫 — unit已安装(make systemd-install)时, 主流程仍pgrep+kill停进程+nohup启新实例: `Restart=always`在kill后5秒内复活systemd进程, 与nohup第二实例撞端口(一者无限重启风暴/新代码未生效假部署); `restore-db`同型(kill后复活进程立即写回刚恢复的库) → 新增SYSTEMD_MODE探测(unit文件存在即systemd模式), 步骤6/7与restore-db停启全部委托`systemctl stop/start`(start后取MainPID接健康检查轮询), systemd模式下不写.pid/不nohup/日志提示切journalctl; stop失败即中止(exit 1, 不碰库); 变异三档实测(systemd模式stop+start调用链精确/直跑模式零systemctl调用行为不变/stop失败exit 1库不动); systemd/README.md新增自动探测章节

### Fixed
- `Makefile` systemd-install (F211): 路径漂移守卫 — unit/logrotate 模板硬编码 `/home/tl/tianlian-edge-gateway-v3`(Pi默认路径), 旧安装裸 `sudo cp`, 仓库位于其他目录时(deploy.sh REPO_DIR 自动探测支持任意含 main.py 目录)装出的 unit WorkingDirectory/EnvironmentFile 与 logrotate 路径指向不存在目录 → 服务起不来/日志轮转静默失效(missingok) → 安装时 sed 渲染为 $(CURDIR)；三档实测(非默认路径替换3处精确/默认路径 no-op diff零/ make -n CURDIR展开正确)；deploy.sh 两处提示+systemd/README.md 手动步骤同步收敛到 `make systemd-install`(F195单一源模式)

### Changed
- CI (ci.yml): 两 job 补 `timeout-minutes`（quality=15 / docker=20）— F193模式例行体检撞出：此前均无超时，挂死最多吃满 GitHub 默认 6h runner；YAML 解析+结构断言校验（timeout/concurrency/coverage产物 if:always 均实测确认）。本地无 act 环境，结构化校验替代

### Fixed
- `scripts/watchdog.sh` (F205): cron单次模式补 flock 互斥 — 恢复窗口(~75s: 3轮启动健康等待+RESTART_DELAY)可跨cron触发周期，此前两实例并发恢复会双启gateway、后启者覆盖`.pid`致先启进程成孤儿(占端口但pid失联)、后来者端口冲突反复失败 → `exec 9>lock + flock -n`拿不到锁即跳过本轮；变异实测双向(有锁: 并发实例13ms exit 0零日志贡献 / 无锁对照: 两实例同时进恢复, 探针有效)
- `.gitignore`: 补运行时产物 `.pid`/`.watchdog.lock`/`gateway.log`(deploy.sh/watchdog.sh在部署目录生成, F10同型噪音)
- `deploy.sh` (v8): 步骤5迁移失败黑洞 — 旧写法 `2>/dev/null || echo` 吞掉真失败（`db_migration.py` 幂等成功恒 exit 0，真失败 exit 1），带病继续会杀旧服务起新代码，旧schema库运行时即 "no such column" 崩 → 迁移失败即中止部署（此时旧服务未停，零影响）；实测坏库场景确认中止（exit 1）
- `deploy.sh` (v8): 备份同秒碰撞覆盖 — 时间戳备份名同秒重跑会静默覆盖上一份备份（实测复现：好备份被坏库内容覆盖）→ 目标已存在时追加 `-1/-2` 后缀，绝不覆盖旧备份

### Added
- `deploy.sh` (v8): 迁移前自动备份 `data/gateway.db` → `data/backups/gateway.db.<时间戳>.bak`（仅保留最近5份，轮转实测确认），备份失败即中止部署；新子命令 `restore-db [备份文件]`：停网关→恢复备份（缺省最新一份），实测旧schema库迁移6项+坏库中止+同秒双备份+恢复闭环全过；`make deploy-restore-db [BAK=...]` 委托单一源

### Fixed
- `deploy.sh` (v7): 步骤5迁移脚本真缺口 — 旧 `migrate_db.py` 只补 `cloud_synced`/`priority` 两列，旧schema库缺 `cached_at`/`retry_count`/`synced` 时迁移后 schema 仍不全，运行时查询即 "no such column" 崩；实测对比（旧schema临时库两脚本各跑+幂等复跑）确认 `db_migration.py` 全量补齐且幂等 → 切换 `migrate_db.py`→`db_migration.py`，旧脚本退役移除
- systemd 单元双源漂移修复：移除根目录旧版 `tianlian-edge-gateway.service`（无安全加固、Restart=on-failure+StartLimitBurst=3 崩溃3次后不再拉起、日志双写），唯一源为 `systemd/tianlian-gateway.service`；README 原安装指引指向旧版（误装会导致网关崩溃后永久下线）→ 改为方式五指向 systemd/ 版；DEPLOYMENT.md 说明同步
- `deploy.sh` (v6) + `Makefile deploy-rollback`: 回滚 stash 黑洞（F172遗留实测发现）— v5 先 stash 脏改动再 revert，但失败路径声称"恢复现场"却不 pop stash（用户未提交改动看似丢失），成功路径也不提 stash 去向 → 记录 stash 计数，失败自动 `git stash pop` 真正恢复现场，成功提示 `stash@{0}`；失败提示补 merge commit 场景（范围含 merge 时 revert 需 `-m`）与手动处理指引；Makefile deploy-rollback 从重复实现改为委托 `deploy.sh rollback`（单一源，防护一致）。临时仓库 5 用例实测：干净线性/脏树保留stash/merge+脏改动失败pop恢复/Makefile委托/无效commit与REV=HEAD防护 全过
- `deploy.sh` (v5) + `Makefile deploy-rollback`: 回滚语义bug — `git revert $REV` 只撤销单个commit，与"回滚到REV"语义不符（落后N个commit时只撤1个，其余N-1个坏提交仍在）→ 改 `git revert ${REV}..HEAD` 撤销目标好版本之后全部提交，工作区即REV状态；新增 无效commit校验/REV即HEAD短路/revert冲突自动abort 三重防护

### Added
- CI: 新增 `docker` job（与 quality 并行）— buildx 构建镜像(GHA缓存, 不推送) + 容器内无环境变量 `import main` 冒烟，Dockerfile/依赖损坏在 push 阶段即被拦截
- `.dockerignore`: 补 tests/docs/.github/systemd/*.log/coverage.xml → 运行时镜像瘦身
- `DEPLOYMENT.md`: 部署前门禁说明同步 CI docker 构建门

### Fixed
- `deploy.sh` (v4): `status` 子命令 `pgrep -f 'main.py'` 匹配过宽（会命中任意目录的 main.py）→ 改用 `$REPO_DIR/main.py` 精确匹配，REPO_DIR 探测提前到子命令之前
- `deploy.sh` (v4): 启动用相对路径 `main.py` 导致 cmdline 不含路径，step6/watchdog 的精确 pgrep 永不命中（杀旧全靠 .pid/fuser 兑底）→ 改绝对路径启动
- `scripts/watchdog.sh`: 同步改绝对路径启动，与 get_pid 匹配模式对齐

### Added
- `deploy.sh` (v4): Python 版本预检（<3.10 告警不阻断，兼容老环境）

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
