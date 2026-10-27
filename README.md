# 天链光储充智慧运维平台

> 一套系统，管住光储充场站的全部资产与全部业务。
> 从光伏板的每一度发电，到储能柜的每一次充放，再到每一笔充电订单。

**开源 · MIT License · 支持私有化部署**

在线演示：http://8.134.106.166/ · 体验账户：`demo` / `demo12345`（只读）

---

## 平台总览

天链光储充智慧运维平台是**单一仓库的完整系统**，云端平台、边缘网关、三端移动应用与小程序全部收在本仓库内，各自独立迭代，合在一起是一套完整方案。

```
┌────────────────────────────────────────────────────────────┐
│                    天链光储充智慧运维平台                     │
├────────────────┬────────────────┬──────────────────────────┤
│   云端平台      │   边缘网关      │        移动端             │
│                │                │                          │
│ cloud/         │ edge-gateway/  │ station-app/             │
│ FastAPI + React│ OCPP/Modbus/   │ ops-app/                 │
│ 109 API 模块   │ MQTT 断网续传   │ user-app/                │
│ 70+ 页面       │                │ user-mp/                 │
└────────────────┴────────────────┴──────────────────────────┘
```

## 目录结构

| 目录 | 角色 | 技术栈 | 说明 |
|---|---|---|---|
| [cloud/](./cloud) | 云端平台 | FastAPI · React 18 · PostgreSQL | 109 个 API 模块，运维/运营/车队/平台/能源五大板块 |
| [edge-gateway/](./edge-gateway) | 边缘网关 | Python · OCPP · Modbus · MQTT | 部署在场站现场，断网本地缓存，恢复自动补传 |
| [station-app/](./station-app) | 站长 APP | React Native (Expo) | 站点总览、报修、工单验收、遥测查看 |
| [ops-app/](./ops-app) | 运维工程师 APP | React Native (Expo) | 工单处理、设备监控、告警响应、AI 诊断 |
| [user-app/](./user-app) | 用户 APP | React Native (Expo) | 扫码充电、订单管理、钱包、优惠券 |
| [user-mp/](./user-mp) | 用户微信小程序 | 原生小程序 | 扫码充电、订单、优惠券、积分 |

## 核心能力

- **设备接入**：光伏逆变器、储能 PCS/BMS/EMS、直流/交流充电桩、V2G 双向桩、变配电设备
- **协议支持**：Modbus RTU/TCP、MQTT、DL/T 645、IEC 104、OCPP，支持厂商私有协议扩展
- **智能运维**：AI 故障诊断、Runbook 自动化、告警自愈、预测性维护
- **运营闭环**：计费、订单、优惠、发票、结算、互联互通、市政监管对接
- **车队管理**：车辆/司机、排队调度、V2G、对账、碳资产
- **能源管理**：可编排能量流、储能多策略仲裁、省级电价模板、VPP

## 快速开始

```bash
git clone https://github.com/ReddingXagent/tianlian
cd tianlian
```

### 云端平台

```bash
cd cloud
make backend   # 启动后端 (端口 8000)
make dev       # 启动前端 (端口 3004)
```

### 边缘网关

```bash
cd edge-gateway
cp .env.example .env   # 配置云端地址
docker compose up -d
```

### 移动端（以站长 APP 为例）

```bash
cd station-app
npm install
cp .env.example .env   # 配置 API 地址
npm start
```

## 部署

| 方式 | 说明 |
|---|---|
| 本地试用 | `make backend` + `make dev`，SQLite 零依赖 |
| Docker | `docker compose up`，前端后端数据库全起 |
| 生产 | `deploy.sh` 六阶段自动部署，失败自动回滚 |

## 许可证

MIT License — 代码全部开放，可自建、可二次开发、可商用。

各子目录的 LICENSE 文件为准。
