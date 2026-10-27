# 天链 V3 边缘网关

## 概述

边缘网关是天链 V3 平台的核心边缘组件，部署在充电站/储能站现场，负责：

- 向云端注册并维持心跳
- 通过 OCPP WebSocket 与充电桩通信
- 通过 Modbus TCP 采集设备数据
- 定时上报遥测数据到云端
- 网络中断时本地缓存，恢复后自动补传

## 架构

```
┌─────────────────────────────────────────────────────┐
│                  边缘网关 (Edge Gateway)              │
│                                                      │
│  ┌──────────────┐  ┌──────────────┐                  │
│  │ 注册心跳      │  │ 遥测上报      │                  │
│  │ (Registry)   │  │ (Telemetry)  │                  │
│  └──────┬───────┘  └──────┬───────┘                  │
│         │                 │                           │
│  ┌──────┴─────────────────┴───────┐                  │
│  │        断网续传                 │                  │
│  │      (Offline Buffer)          │                  │
│  └────────────────────────────────┘                  │
│                                                      │
│  ┌──────────────┐  ┌──────────────┐                  │
│  │ OCPP Server  │  │ Modbus Master│                  │
│  │ (WebSocket)  │  │ (TCP Poller) │                  │
│  └──────┬───────┘  └──────┬───────┘                  │
│         │                 │                           │
│    ┌────┴────┐      ┌─────┴─────┐                   │
│    │ 充电桩   │      │ 逆变器/电表 │                   │
│    └─────────┘      └───────────┘                   │
└─────────────────────────────────────────────────────┘
```

## 模块说明

### 1. 网关注册心跳 (`modules/registry.py`)
- 启动时向云端注册网关
- 定期发送心跳（默认 30s）
- 上报 CPU/内存/运行时长等指标
- 连接状态管理

### 2. OCPP WebSocket Server (`modules/ocpp_server.py`)
- 实现 OCPP 1.6J 协议服务端
- 支持 BootNotification, Heartbeat, StatusNotification
- 支持 StartTransaction, StopTransaction, MeterValues
- 远程控制：RemoteStart, RemoteStop, Reset

### 3. Modbus TCP Master (`modules/modbus_master.py`)
- Modbus TCP 主站，并发轮询多设备
- 支持 Holding Registers, Input Registers, Coils
- 自动重连机制
- 数据推送到遥测队列

### 4. 遥测上报 (`modules/telemetry_reporter.py`)
- 从 Modbus 和 OCPP 收集遥测数据
- 批量上报云端 API
- 数据格式转换（Modbus 寄存器 → 遥测格式）
- 失败重试机制

### 5. 断网续传 (`modules/offline_buffer.py`)
- SQLite 本地缓存
- 网络恢复自动补传
- 缓存大小和时长限制
- 过期数据自动清理

## 快速开始

### 安装依赖

```bash
cd edge-gateway
pip install -r requirements.txt
```

### 配置

编辑 `config/settings.yaml` 或通过环境变量覆盖：

```bash
export TL_GATEWAY__GATEWAY__SN=TL-GW-001
export TL_GATEWAY__CLOUD__API_BASE=http://demo.example.com/api/v1
```

### 启动

```bash
python -m app.main
```

### Docker 部署

```bash
docker build -t tianlian-edge-gateway .
docker run -d \
  -p 8080:8080 \
  -p 9000:9000 \
  -e TL_GATEWAY__GATEWAY__SN=TL-GW-001 \
  tianlian-edge-gateway
```

## 依赖锁定 / 可复现构建

`requirements.txt` 全部依赖使用 `==` 精确锁定（重叠依赖与 `backend/requirements.lock` 生产已验证版本对齐；ocpp/pymodbus/websockets 锁 PyPI 当前稳定版），保证 Docker 构建可复现、避免上游供应链漂移。

`requirements.lock` 为全量解析锁（含传递依赖，面向 Dockerfile 的 `python:3.11-slim`），需要严格复现容器环境时使用：

```bash
pip install -r requirements.lock
```

再生成方式（升级依赖时）：

```bash
python3 -m pip install --dry-run --report report.json --ignore-installed \
  --python-version 3.11 --only-binary :all: -r requirements.txt
python3 -c "import json; r=json.load(open('report.json')); \
  [print(i['metadata']['name']+'=='+i['metadata']['version']) \
   for i in sorted(r['install'], key=lambda x: x['metadata']['name'].lower())]" \
  > requirements.lock
```

## API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 网关信息 |
| `/health` | GET | 健康检查 |
| `/status` | GET | 详细状态 |
| `/ocpp/connections` | GET | OCPP 连接列表 |
| `/ocpp/{id}/start` | POST | 远程启动充电 |
| `/ocpp/{id}/stop` | POST | 远程停止充电 |
| `/ocpp/{id}/reset` | POST | 重置充电桩 |
| `/modbus/devices` | GET | Modbus 设备状态 |
| `/offline-buffer/flush` | POST | 手动补传缓存 |
| `/offline-buffer/stats` | GET | 缓存统计 |

## 项目结构

```
edge-gateway/
├── app/
│   ├── main.py              # 主入口 + FastAPI 管理 API
│   ├── core/
│   │   ├── config.py        # 配置管理
│   │   ├── logging.py       # 日志配置
│   │   └── http_client.py   # 云端 API 客户端
│   ├── modules/
│   │   ├── registry.py      # 网关注册心跳
│   │   ├── ocpp_server.py   # OCPP WS 服务端
│   │   ├── modbus_master.py # Modbus TCP 主站
│   │   ├── telemetry_reporter.py  # 遥测上报
│   │   └── offline_buffer.py      # 断网续传
│   └── utils/
│       └── helpers.py       # 工具函数
├── config/
│   └── settings.yaml        # 配置文件
├── data/                    # 运行时数据
├── tests/                   # 测试
├── requirements.txt
├── Dockerfile
└── README.md
```
