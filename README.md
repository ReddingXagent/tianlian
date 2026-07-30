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
pip install -r requirements.txt   # Python 3.10+（ruff target py313）
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
| `MQTT_BATCH_SIZE` / `MQTT_BATCH_INTERVAL` | `50` / `10` | 点位批量发布 |
| `MODBUS_HOST` / `MODBUS_PORT` / `MODBUS_REAL` | `127.0.0.1` / `502` / `false` | Modbus 设备（默认模拟器） |
| `OCPP_CHARGER_ID` / `OCPP_REAL` | `CHARGER-001` / `false` | OCPP 充电枪（默认模拟器） |

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

## 部署（树莓派）

```bash
bash deploy.sh   # 目标机: tl@192.168.31.10, 仓库 /home/tl/tianlian-edge-gateway-v3, 端口 8080
                 # v2: 自动探测仓库目录/全量装依赖/保留.env/git ff同步
```

## 目录结构

```
main.py            入口，编排各 adapter + 本地 API + 上云循环
config.py          dataclass 配置（环境变量覆盖）
adapters/          modbus / ocpp / mqtt / cloud_client
api/server.py      FastAPI 调试 API
models/            device / telemetry 数据模型
storage/           SQLite 遥测缓存（断网续传）
tests/             pytest 套件 + mock_csms_server
deploy.sh          树莓派一键部署
```
