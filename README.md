# 天链V3 边缘网关 (tianlian-edge-gateway)

充电桩场站侧边缘网关：采集 Modbus 设备遥测，经 OCPP 管理充电枪，通过 MQTT 汇聚点位，本地 FastAPI 提供调试 API，并断网缓存 + 批量上云（register / heartbeat / telemetry / alarm）。

## 架构

```
 Modbus Adapter ─┐                 ┌─ Local API (FastAPI :8080)
 OCPP Adapter  ──┼─ on_telemetry ──┤
 MQTT Client   ──┘        │        └─ Telemetry Cache (SQLite, 断网续传)
                          ▼
                    Cloud API (register/heartbeat/alarm/upload)
```

- 云端入口默认 `http://8.134.106.166/api/v1`（大圣 tianlian-v3 统一入口）
- 上云批量间隔 15s（T-1202），心跳 30s，均可配

## 快速开始

```bash
pip install -r requirements.txt   # Python 3.10+（ruff target py310）
python main.py                    # 默认配置
python main.py --config cfg.yaml  # 自定义配置
GATEWAY_ID=GW-002 python main.py  # 环境变量覆盖
```

## 环境变量

| 变量 | 默认 | 说明 |
|------|------|------|
| `GATEWAY_ID` / `GATEWAY_NAME` | `GW-001` / `RaspberryPi-Gateway` | 网关身份 |
| `CLOUD_BASE_URL` | `http://8.134.106.166` | 云端入口 |
| `CLOUD_TOKEN` / `CLOUD_USERNAME` / `CLOUD_PASSWORD` | 空 | 云端认证 |
| `CLOUD_REGISTER` / `CLOUD_DEREGISTER` | `true` | 启停时自动注册/注销 |
| `MQTT_HOST` / `MQTT_PORT` | `localhost` / `1883` | MQTT broker |
| `MQTT_CLIENT_ID` | 空 | MQTT 客户端 ID（空=自动生成） |
| `MQTT_BATCH_SIZE` / `MQTT_BATCH_INTERVAL` | `50` / `10` | 点位批量发布 |
| `MODBUS_HOST` / `MODBUS_PORT` / `MODBUS_REAL` | `127.0.0.1` / `502` / `false` | Modbus 设备（默认模拟器） |
| `OCPP_CHARGER_ID` / `OCPP_REAL` | `CHARGER-001` / `false` | OCPP 充电枪（默认模拟器） |
| `STORAGE_DB_PATH` | `data/gateway.db` | SQLite 缓存路径 |
| `LOG_LEVEL` | `INFO` | 日志级别（DEBUG/INFO/WARNING/ERROR） |

## 本地 API（默认 :8080）

| 端点 | 说明 |
|------|------|
| `GET /health` | 健康检查 |
| `GET /api/v1/status` | 网关状态 |
| `GET /api/v1/telemetry/latest` | 最新遥测 |
| `GET /api/v1/devices` | 设备列表 |
| `GET /api/v1/cache/stats` | 缓存统计 |
| `GET /api/v1/dashboard` | 调试仪表盘 |
| `GET /api/v1/perf` | 性能指标 |
| `POST /api/v1/simulate/telemetry` / `simulate/alarm` | 模拟注入 |

## 测试与质量

```bash
bash scripts/run_tests.sh   # 装依赖 + pytest + coverage
python -m pytest tests/     # 198 用例全绿（含 mock CSMS）
ruff check .                # lint 门控（配置见 pyproject.toml，债务以 ignore 登记并逐条收窄）
```

## .env 文件

除环境变量和 YAML 外，启动目录的 `.env` 文件会被 `deploy.sh` 自动 `source`（key=value 格式，无需 `export`）。优先级：`--config` YAML > 已有环境变量 > `.env` > 默认值。

## 部署（树莓派）

### 方式一: deploy.sh 一键部署

```bash
bash deploy.sh   # 目标机: tl@192.168.31.10, 仓库 /home/tl/tianlian-edge-gateway-v3, 端口 8080
                 # v3: 端口释放等待+启动重试+健康轮询；deploy.sh 自动 source .env
                 # v2: 自动探测仓库目录/全量装依赖/保留.env/git ff同步
```

### 方式二: systemd 服务（开机自启 + 崩溃重启）

详见 `systemd/README.md`，或使用 Makefile 快捷命令：

```bash
make systemd-install   # 安装 unit + logrotate
make systemd-start     # 启动
make systemd-status    # 状态
make systemd-logs      # 实时日志
```

### 方式三: Docker 容器化部署

```bash
# 构建并启动
docker compose up -d

# 查看日志
docker compose logs -f

# 重建（代码更新后）
docker compose up -d --build

# 停止
docker compose down
```

容器特性：非 root 运行、HEALTHCHECK 每 30s 检查、日志轮转 10m×3、数据卷持久化、时区同步。

### 方式四: 看门狗（无 systemd/Docker 场景）

```bash
# crontab 每 2 分钟检查
crontab -e
# */2 * * * * /path/to/scripts/watchdog.sh

# 或常驻后台
nohup bash scripts/watchdog.sh --loop > /dev/null 2>&1 &
```

> F230: 已装 systemd unit 时 watchdog 自动退位（恢复交给 Restart=always），
> 避免 kill+nohup 双启与 unit 复活进程撞端口。本方式仅用于无 systemd/Docker 场景。

### 方式五: systemd（推荐, 开机自启+崩溃重启）

```bash
# 在树莓派上(以 systemd/ 目录版为准, 含安全加固+ProtectHome=false写库保护):
sudo cp systemd/tianlian-gateway.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now tianlian-gateway
# 查看日志:
journalctl -u tianlian-gateway -f
```

### 环境配置

```bash
cp .env.example .env  # 复制模板, 填入 CLOUD_TOKEN
make install          # 创建 venv + 装依赖
make run              # 启动网关
make test             # 跑测试
make lint             # ruff 检查
make check            # 部署守卫十三项(同名源/探测端点/API端口/env键/日志路径/数据路径/入口文件/健康探测路径/Python版本多源/模板渲染路径/备份写读对账/pid文件写读对账/启动解释器多源) + lint + test 一键门控
```

## 配置文件

除环境变量外，可通过 YAML 配置文件覆盖默认值：

```bash
python main.py --config my-gateway.yaml
```

YAML 字段与 `GatewayConfig` dataclass 一一对应（参见 `config.py`）。命令行 `--config` > 环境变量 > 默认值。

## 故障排查

| 症状 | 排查 |
|------|------|
| 启动报 `ModuleNotFoundError` | `pip install -r requirements.txt`，确认 Python ≥ 3.10 |
| OCPP 连接超时 | 检查 `OCPP_REAL=true` 时 CSMS 地址可达；默认模拟器 `OCPP_REAL=false` |
| Modbus 读取失败 | `MODBUS_REAL=true` 需真实设备；模拟器 `MODBUS_REAL=false` 仅供调试 |
| 云端心跳 401 | `CLOUD_TOKEN` 过期或未设；可改用 `CLOUD_USERNAME` + `CLOUD_PASSWORD` 自动签发 |
| 缓存持续增长 | `GET /api/v1/cache/stats` 查看；断网时正常，恢复后批量上传自动消减 |
| `/api/v1/status` cache_size > cache_max | 已知观察点（F15），疑似缓存淘汰未生效，关注但不阻塞 |
| 树莓派部署失败 | `deploy.sh v2` 自动探测仓库路径；确认 `tl@192.168.31.10` SSH 可达 |

## 更多文档

- [部署运行手册](DEPLOYMENT.md) — deploy.sh/systemd/Docker 三方式 + 回滚 + 踩坑记录
- [API 参考手册](docs/API_REFERENCE.md) — 全端点请求/响应示例 + curl 验证
- [移动端集成指南](docs/MOBILE_INTEGRATION.md) — RN/微信小程序对接网关 API
- [开发贡献指南](docs/DEVELOPMENT.md) — 环境搭建 / 项目结构 / 扩展指南
- [CHANGELOG](CHANGELOG.md) — 版本变更记录
- [systemd 部署指南](systemd/README.md) — 开机自启 + 日志轮转

## 目录结构

```
main.py            入口，编排各 adapter + 本地 API + 上云循环
config.py          dataclass 配置（环境变量覆盖）
adapters/          modbus / ocpp / mqtt / cloud_client
api/server.py      FastAPI 调试 API
models/            device / telemetry 数据模型
storage/           SQLite 遥测缓存（断网续传）
docs/             API参考手册 + 移动端集成指南 + 开发贡献指南
tests/             pytest 套件 + mock_csms_server
deploy.sh          树莓派一键部署（v3: 端口等待+重试+健康轮询）
Dockerfile         多阶段容器构建（python:3.10-slim, 非 root, HEALTHCHECK）
docker-compose.yml 一键容器化部署（restart + 日志轮转 + 持久化卷）
scripts/watchdog.sh 看门狗（健康检查+自动重启, crontab/--loop 双模式）
systemd/           systemd unit + logrotate + README（唯一 systemd 单元源）
.env.example       环境变量模板（所有 key 与 config.py 精确对齐）
Makefile           开发快捷命令 (install/run/test/lint/check/deploy/systemd-*)
```
