# TianLian Cloud — 光储充一体化智能运维平台

> 覆盖光伏发电、储能管理、充电桩运维全链路的开源运维管理平台

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Backend](https://img.shields.io/badge/backend-FastAPI-009688.svg)](https://fastapi.tiangolo.com/)
[![Frontend](https://img.shields.io/badge/frontend-React%2018-61dafb.svg)](https://react.dev/)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)

**在线演示**：http://8.134.106.166/ （体验账户见下方「演示账户」）

---

## 项目简介

TianLian Cloud 是面向光储充行业的新一代智能运维平台，前后端分离架构，包含 Web 管理后台、FastAPI 后端、移动端三端。核心覆盖设备管理、多协议遥测采集、告警诊断、工单调度、运维自动化（Runbook / 自愈）、运营结算、车队管理、虚拟电厂（VPP）等业务。

**核心能力**：实时监控 · 智能诊断 · 工单调度 · 告警闭环 · 数据分析 · 运营结算 · 虚拟电厂 · 数字孪生

### 功能全景

| 模块 | 说明 |
|------|------|
| 设备管理 | 站点 / 设备台账 / 设备协议库 / 网关管理 |
| 遥测采集 | Modbus / MQTT / DLT645 / IEC104 多协议接入，WebSocket 实时推送 |
| 智能诊断 | 故障诊断 / 智能诊断 / 预测性维护 / 自愈（Healing） |
| 运维自动化 | Runbook 编排 / 审批流 / 巡检（InspectionOps）/ 值班（OnCall） |
| 工单系统 | 工单调度 / 统计 / 远程控制（RemoteControl） |
| 运营结算 | 订单 / 优惠券 / 积分 / 对账 / 折扣管理 |
| 能源业务 | 能耗报表 / 能源分析 / VPP 虚拟电厂 / 车队（Fleet） |
| 可视化 | 数字孪生（three.js）/ 数据大屏（LargeScreen）/ 电子地图 |
| 平台治理 | RBAC 权限 / 多租户（Tenants）/ 审计日志 / Webhooks / SSL 证书监控 |
| AI 辅助 | 日志分析 / 维修建议 / 预防性维护（可插拔 LLM 接入） |

## 设备模拟器（开箱即用）

没有真实现场设备也能跑通全链路——仓库内置多协议设备模拟器，覆盖光储充主要设备类型：

| 协议 | 模拟对象 |
|------|----------|
| Modbus-RTU | 储能逆变器 / PCS / 电表 |
| MQTT | 直流充电桩（国标协议） |
| REST | 光伏气象站等 HTTP 设备 |
| OCPP 1.6J | 充电桩 |
| DLT645 | 多功能电能表 |
| IEC104 | 电力远动规约 RTU |

另含**故障注入引擎**（7 类故障场景 + 随机模式）与**批量并发模拟**（100+ 设备同时在线），可直接复现告警、工单、自愈等完整业务流转。

详见 [backend/SIMULATOR_README.md](./backend/SIMULATOR_README.md)

## 技术栈

| 层级 | 技术 |
|------|------|
| Web 前端 | React 18 + Vite 5 + TypeScript，Ant Design 5 + ECharts + three.js |
| 移动端 | React Native（Expo） |
| 后端 | FastAPI + SQLAlchemy 2 + Pydantic v2，Python 3.10+，Celery 异步任务 |
| 数据库 | SQLite（开发）/ PostgreSQL（生产），Alembic 迁移 |
| 缓存/队列 | Redis（可选）：缓存 + Celery broker |
| 设备接入 | 边缘网关 + 多协议解析器（Modbus / MQTT / DLT645 / IEC104） |
| 实时推送 | WebSocket（`/ws/v1/`） |
| 可观测 | Prometheus 指标（`/metrics`）+ Loki 日志 + Grafana 面板 |
| 部署 | Docker Compose / Nginx，自动化部署脚本 |

## 快速开始

### 环境要求

- Python 3.10+
- Node.js 18+
- Docker & Docker Compose（可选，推荐生产部署方式）

### 1. 后端

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 初始化数据（含演示数据与演示账户）
python seed_data.py

# 启动开发服务
uvicorn app.main:app --reload --port 8000
```

API 文档：`http://localhost:8000/docs`

### 2. Web 前端

```bash
cd frontend
npm install
npm run dev
```

访问 `http://localhost:5173`

### 3. Docker 一键部署

```bash
cp .env.example .env       # 按需修改配置
docker compose up -d
```

## 演示账户

公开演示环境提供只读体验账户，**该账户参数已锁定**（禁止修改密码、资料与删除），可浏览全部只读功能：

| 项目 | 值 |
|------|-----|
| 用户名 | `demo` |
| 密码 | `demo12345` |
| 角色 | viewer（只读） |

> 演示账户的保护逻辑见 `backend/app/api/v1/users.py` 中的 `ensure_not_demo()`；
> 种子定义见 `backend/seed_data.py`。生产部署请删除该账户或修改 `DEMO_LOCKED_USERNAME`。

## 项目结构

```
tianlian-cloud/
├── backend/                 # FastAPI 后端（60+ API 模块）
│   ├── app/
│   │   ├── api/v1/          # REST API 路由
│   │   ├── core/            # 配置 / 安全 / 缓存 / 限流
│   │   ├── models/          # SQLAlchemy 数据模型
│   │   ├── schemas/         # Pydantic 模型
│   │   ├── services/        # 业务逻辑层
│   │   ├── gateway/         # IoT 网关（modbus/mqtt/rest）
│   │   ├── parsers/         # 协议解析器
│   │   ├── ws/              # WebSocket 路由
│   │   └── tasks/           # Celery 异步任务
│   ├── alembic/             # 数据库迁移
│   └── tests/               # 测试套件
├── frontend/                # React Web 管理后台
├── mobile/                  # React Native 移动端（Expo）
├── edge-gateway/            # 边缘网关（独立进程）
├── docs/                    # 架构与方案文档
├── deploy/                  # 部署脚本与配置
├── grafana/ loki/ alertmanager/  # 可观测栈配置
└── docker-compose.yml       # 一键编排
```

## 文档

- [系统架构](./ARCHITECTURE.md)
- [部署指南](./DEPLOYMENT.md)
- [用户手册](./USER_MANUAL.md)
- [接口规格](./SPEC.md)
- [更新日志](./CHANGELOG.md)

## 安全说明

- 全局认证：JWT Bearer + 路由白名单，C 端 / 运营端双 token 体系（aud 隔离）
- 防护机制：登录失败锁定、验证码防爆破、CSRF、安全响应头、请求限流、审计日志
- 上线前请务必：修改默认账户密码、更换 JWT 密钥、配置 HTTPS、删除演示账户

## 贡献

欢迎 Issue 与 PR。提交前请运行测试套件：

```bash
cd backend && python -m pytest
```

## 许可证

[MIT](./LICENSE)
