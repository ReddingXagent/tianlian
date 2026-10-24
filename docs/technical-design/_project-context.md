# 天链V3 项目上下文快照

## 工程概览

- **项目**: 天链光储充运维系统 V3
- **路径**: /Users/xxx/.openclaw/workspace/projects/tianlian-v3
- **Git分支**: stable-v3.0
- **提交数**: 500+

## 后端

- **框架**: FastAPI (Python)
- **数据库**: SQLite (开发) / PostgreSQL (生产)
- **缓存**: Redis (可选)
- **时序库**: TDengine (可选)
- **消息队列**: Celery
- **API端点**: 54个模块 (alarms, devices, stations, workorders, healing, analytics, ...)
- **数据模型**: 29个 (Station, Device, Gateway, Alarm, WorkOrder, User, Team, Tenant, ...)
- **服务层**: 33个 (dispatch_engine, healing_engine, health_engine, stats_service, ...)
- **数据管道**: gateway/ (Modbus/MQTT/REST) + parsers/ (协议解析)
- **WebSocket**: ws/ (realtime/digital_twin)

## 前端

- **框架**: React 18 + TypeScript + Vite
- **UI库**: Ant Design 5
- **路由**: React Router v6
- **状态管理**: Zustand (推测, 从hooks模式)
- **国际化**: i18n (zh/en)
- **页面数**: 50+ 页面组件
- **双入口**: platform (平台管理) + ops (运维管理)

## 目录结构

tianlian-v3/
├── backend/
│   ├── app/
│   │   ├── api/v1/        # 54个路由模块
│   │   ├── models/         # 29个数据模型
│   │   ├── services/       # 33个业务服务
│   │   ├── gateway/        # 数据管道 (Modbus/MQTT/REST)
│   │   ├── parsers/        # 协议解析
│   │   ├── ws/             # WebSocket
│   │   ├── middleware/      # 中间件 (auth/audit/security)
│   │   └── core/           # 配置/数据库/缓存
│   └── tests/
├── frontend/
│   ├── src/
│   │   ├── pages/          # 50+ 页面
│   │   ├── components/     # 通用组件
│   │   ├── api/            # API客户端
│   │   ├── hooks/          # React hooks
│   │   ├── config/         # 菜单/路由/WS配置
│   │   └── utils/          # 工具函数
│   └── docs/
└── docs/

## 规范文档

- MEMORY.md: 模型调度/编程策略/Agent协作
- AGENTS.md: 工作纪律
- SOUL.md: 人格/行为准则
