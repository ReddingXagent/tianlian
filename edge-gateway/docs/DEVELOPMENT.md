# 开发贡献指南 — tianlian-edge-gateway

## 环境搭建

### 前置要求

- Python 3.10+（生产环境树莓派 = 3.10，开发机建议 3.12/3.13）
- pip, venv
- git（remote=origin 指向 NAS: `ssh://MonkeyKing@192.168.31.100:2222/volume1/homes/MonkeyKing/repos/tianlian-edge-gateway.git`）

### 初始化

```bash
git clone ssh://MonkeyKing@192.168.31.100:2222/volume1/homes/MonkeyKing/repos/tianlian-edge-gateway.git
cd tianlian-edge-gateway
make venv
make install      # 创建 .venv + 装依赖
```

### 验证安装

```bash
make check        # ruff lint + pytest 全绿
```

## 项目结构

```
main.py               入口，编排各 adapter + 本地 API + 上云循环
config.py             dataclass 配置（GatewayConfig.from_env()）
adapters/
  modbus_adapter.py   Modbus 设备采集（真实 pymodbus / 模拟器双模式）
  ocpp_adapter.py     OCPP 充电枪管理（真实 WebSocket / 模拟器双模式）
  mqtt_client.py      MQTT 点位批量发布
  cloud_client.py     云端 API 客户端（register/heartbeat/telemetry/alarm）
api/
  server.py           FastAPI 调试 API（13 端点，详见 docs/API_REFERENCE.md）
models/
  device.py           设备数据模型
  telemetry.py        遥测数据模型
storage/
  cache.py            SQLite 断网缓存（遥测 + 告警）
tests/                pytest 套件 + mock_csms_server
deploy.sh             树莓派一键部署 (v3)
Dockerfile            多架构容器构建
docker-compose.yml    容器化编排
Makefile              开发快捷命令
systemd/              systemd unit + logrotate + 安装指南
scripts/
  run_tests.sh        测试运行脚本
  watchdog.sh         看门狗（crontab/--loop 双模式）
```

## 核心概念

### 双模式适配器

所有适配器（Modbus / OCPP）支持 **真实模式** 和 **模拟器模式**：

- `use_real=False`（默认）: 使用内置模拟器，无需真实硬件，适合开发和测试
- `use_real=True`: 连接真实设备，适配器会先重试 `retry_count` 次，失败后自动降级到模拟器

### 数据流

```
设备(Modbus/OCPP) → adapter.on_telemetry() → TelemetryCache(SQLite)
                                           → MQTT批量发布
                                           → 云端批量上传(15s间隔)
```

断网时数据缓存在 SQLite，网络恢复后批量上传，保证不丢数据。

### 配置优先级

```
--config YAML > 环境变量 > .env 文件 > dataclass 默认值
```

## 测试

### 运行测试

```bash
make test               # 全量测试
.venv/bin/pytest -x -q  # 首个失败即停
.venv/bin/pytest tests/test_api_server.py -v  # 单文件
```

### 测试覆盖要求

- 核心模块（cache / cloud_client / api/server）覆盖率 ≥ 90%
- 新增功能必须附带测试
- OCPP 测试有 `@pytest.mark.timeout(20)` 防卡死

### 当前基线

| 指标 | 值 |
|------|------|
| 测试数 | 710 |
| 语句覆盖 | 76%+ |
| 套件 | 全绿 |
| ruff 债务 | 0 条（All checks passed） |

## Lint

```bash
make lint       # ruff check .
```

- 配置见 `pyproject.toml`，target Python 3.10
- 已知债务以 `noqa` / pyproject ignore 登记，不阻塞 CI
- 新代码 ruff 零债务

## 部署

详见 README.md 部署章节。四种方式：

1. **deploy.sh** — SSH 到树莓派一键部署
2. **systemd** — 开机自启 + 崩溃重启（推荐生产）
3. **Docker** — 容器化（多架构 ARM64/AMD64）
4. **watchdog.sh** — 无 systemd 场景的看门狗

## 扩展指南

### 新增 Modbus 寄存器映射

1. 在 `adapters/modbus_adapter.py` 的 `registers` 列表中添加地址
2. 在 `_read_registers()` 中解析新寄存器到遥测字段
3. 在 `tests/test_modbus_adapter.py` 中添加对应测试

### 新增 OCPP 功能

1. 在 `adapters/ocpp_adapter.py` 中实现 OCPP 动作（如 `RemoteStartTransaction`）
2. 在 `tests/test_ocpp_adapter.py` 中使用 mock CSMS 测试
3. 如需 API 暴露，在 `api/server.py` 中添加端点

### 新增 API 端点

1. 在 `api/server.py` 的 `create_app()` 内添加路由
2. 使用 Pydantic 模型定义请求/响应
3. 在 `tests/test_api_server.py` 中添加测试
4. 更新 `docs/API_REFERENCE.md`

## Git 工作流

- 主分支: `master`
- 提交格式: `type(scope): 描述`（如 `feat(api): 新增 /restart 端点`）
- push 到 NAS origin（`ssh://MonkeyKing@...`）
- 树莓派通过 `deploy.sh` 拉取最新代码
