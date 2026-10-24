# 天链智能体系统 — 技术方案 v0.3

> 状态: 定稿  
> 日期: 2026-08-09  
> 作者: 大圣  
> 变更: v0.3 去掉虚胖，聚焦"无人值守"；v0.3.1 增加 Agent-native CLI 层

## 1. 一句话目标

**让天链从死程序变成活的光储充智能体系统——自己巡检、自己诊断、自己处理，搞不定才找人，找人时带着方案来。系统不仅给人用，也给智能体用。**

## 2. 设计哲学

```
自动处理（~90%）  规则引擎自愈，零人工
      ↓
给方案（~8%）     LLM诊断+操作指令，人一键确认
      ↓  
升级人工（~2%）   带诊断+方案+影响评估，IM通知
```

**设计原则**：
- 不造框架，不加外部依赖
- 复用天链已有 AI 基础设施（ai_chat / ai_diagnosis / channel_providers / Celery）
- 每个技能 = 一个 Celery 定时任务 + 调已有 Service 层
- 记忆 = 两张 PG 表
- 对话 = ai_chat.py 增强 function calling
- 前端 = 三板块助手面板

**数据核心原则**（丁哥 2026-08-09 确立）：
- **数据是核心财富**，其他能力都可以重建、提升
- **可回溯**：智能体干的每件事都要留痕（source + 时间戳 + 审计日志）
- **数据安全**：多租户铁墙，team_id 强制隔离，API Token scope 限制
- **完整性**：写操作 schema 校验，重要操作二次确认，批量操作有上限
- **生命周期**：finding resolved后保留90天归档，对话180天摘要压缩，低重要性记忆自动过期
- **可导出**：租户可随时导出全量数据（记忆+对话+巡检发现），数据归属租户

## 3. 已有基础（直接复用）

| 能力 | 文件 | 说明 |
|------|------|------|
| 模型管理 | ai_model_config.py | 多provider/fallback/任务映射 |
| AI对话 | ai_chat.py | RAG/team隔离/流式/语音 |
| 故障诊断 | ai_diagnosis.py | 日志→根因/SOP/置信度 |
| 预测维护 | lstm_predictor.py | LSTM故障预测 |
| 通知渠道 | channel_providers.py | IM/企微/短信/语音 |
| 告警聚合 | alarm_aggregation.py | 窗口聚合+防风暴 |
| 告警升级 | alarm_escalation.py | 三级升级+ack |
| 知识库 | KnowledgeArticle/FAQ | 文章+FAQ+team隔离 |
| 调度 | Celery beat (10+任务) | 已有运维骨架 |
| 能量仲裁 | arbitrator.py | 已在运行的领域智能体 |

## 4. Agent-native 设计（CLI 化）

核心观点：未来的系统不仅给人用，更多是给智能体用。天链要从一开始就把握这个趋势。

```
人用的：前端页面（点击/表单/图表）
智能体用的：CLI + 结构化API（命令/JSON输入输出）
                ↑
        同一套业务逻辑，两个入口
```

### 4.1 CLI 层（新增）

```bash
# 设备管理
tianlian device list --team 5 --status offline
tianlian device detail 123

# 告警管理
tianlian alarm list --team 5 --active
tianlian alarm ack 1234 --note "已派工"
tianlian alarm silence --device 123 --duration 60

# 巡检控制
tianlian patrol run maintenance --team 5
tianlian patrol run operations --team 5
tianlian patrol findings --team 5 --status open

# 诊断
tianlian diagnose run --device 123
tianlian diagnose history --device 123

# 运营
tianlian order query --team 5 --abnormal
tianlian station summary --team 5 --today
tianlian revenue daily --team 5 --date 2026-08-09

# 系统管理
tianlian health check
tianlian config get --team 5
tianlian agent model-config set --team 5 --provider model-b-provider --model model-b-5.2
```

**设计规范**：
- 所有命令支持 `--format json`（默认人类可读表格，json 给智能体用）
- 所有命令有 `--help` 自描述（智能体可自己发现系统能力）
- 所有命令可组合（管道 friendly）
- exit code 语义明确（0=成功，1=业务错误，2=参数错误，3=权限不足）
- CLI 同时给人用——运维 SSH 上去也能敲

### 4.2 API 层（已有，补充）

天链已有完整 REST API，补充：
- 增加 `/api/v1/agent/*` 命名空间，专为智能体设计
  - 批量查询（一次取多设备/多订单摘要）
  - 摘要端点（巡检结果摘要、运营日报摘要）
  - 动作端点（ack告警、静默、触发诊断）
- 错误响应增加 `suggested_action` 字段（告诉智能体下一步该做什么）

### 4.3 权限层

```python
# 现有: require_role("admin") — 给人用
# 新增: require_agent_token("patrol") — 给智能体用
# 智能体token有明确scope，只能做授权范围内操作
# 所有智能体操作记审计日志
```

**Agent Token 表**：
```sql
CREATE TABLE agent_api_token (
    id SERIAL PRIMARY KEY,
    team_id INTEGER REFERENCES teams(id),
    name VARCHAR(100) NOT NULL,         -- "运维巡检Agent"
    token_hash VARCHAR(64) NOT NULL,
    scopes TEXT[] NOT NULL,             -- ['device:read','alarm:ack','diagnose:run']
    enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_used_at TIMESTAMPTZ
);
```

## 5. 新增（四件事）

### 5.1 主动性 — 定时自己跑

在已有 Celery beat 加3个任务：

```python
# app/tasks/agent_patrol.py

@shared_task(name="agent.patrol.maintenance")
def patrol_maintenance():
    """每5分钟运维巡检 — 全租户"""
    for team in get_active_teams():
        run_maintenance_skills.delay(team.id)

@shared_task(name="agent.patrol.operations")  
def patrol_operations():
    """每10分钟运营巡检"""
    for team in get_active_teams():
        run_operations_skills.delay(team.id)

@shared_task(name="agent.patrol.platform")
def patrol_platform():
    """每30分钟平台巡检"""
    run_platform_skills.delay()
```

**运维巡检内容**（调已有Service，不调LLM）：

| 检查项 | 数据源 | 自动处理 | 升级人工 |
|--------|--------|---------|---------|
| 设备离线 | telemetry心跳 | 记录finding，3次连续离线→通知 | 离线>30min |
| 告警风暴 | alarm_aggregation | 已有防风暴自动聚合 | 同类>10条/min |
| 储能SOC异常 | telemetry_battery | 记录finding | SOC<10%持续 |
| 健康评分突降 | lstm_predictor | 记录finding+触发ai_diagnosis | 风险>0.8 |
| 桩功率异常 | telemetry_charger | 记录finding | 持续零功率但有订单 |

**运营巡检内容**：

| 检查项 | 数据源 | 自动处理 | 升级人工 |
|--------|--------|---------|---------|
| 异常订单 | charging_order | 标记+冻结 | 金额>阈值 |
| 场站收益突变 | analytics | 记录趋势 | 跌幅>50% |
| 低余额车队 | enterprise | 记录+通知租户 | 余额<0 |
| 配置缺失 | station_config | 记录finding | 关键配置空 |

**平台巡检内容**：

| 检查项 | 数据源 | 自动处理 | 升级人工 |
|--------|--------|---------|---------|
| API健康 | /health | 已有 | 连续3次失败 |
| 慢查询 | pg_stat | 记录 | >5s |
| 磁盘空间 | df | 清理日志 | >85% |
| Celery队列堆积 | celery inspect | 记录 | >1000待处理 |

### 5.2 记忆 — 越用越聪明

两张表：

```sql
-- 巡检发现 + 诊断结论 + 经验积累
CREATE TABLE agent_memory (
    id SERIAL PRIMARY KEY,
    team_id INTEGER NOT NULL REFERENCES teams(id),
    board VARCHAR(20) NOT NULL,        -- maintenance / operations / admin
    category VARCHAR(50) NOT NULL,     -- finding / diagnosis / decision / learning
    source VARCHAR(100),               -- patrol:device_offline / diagnosis:alarm_123
    title VARCHAR(200) NOT NULL,
    content TEXT NOT NULL,
    severity VARCHAR(20) DEFAULT 'info',
    metadata JSONB DEFAULT '{}',
    importance FLOAT DEFAULT 0.5,
    related_type VARCHAR(50),
    related_id VARCHAR(100),
    status VARCHAR(20) DEFAULT 'open', -- open / acknowledged / resolved
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ
);

CREATE INDEX idx_memory_team_board ON agent_memory(team_id, board, created_at DESC);
CREATE INDEX idx_memory_team_status ON agent_memory(team_id, status);

-- 对话历史
CREATE TABLE agent_conversation (
    id SERIAL PRIMARY KEY,
    team_id INTEGER NOT NULL REFERENCES teams(id),
    user_id INTEGER REFERENCES users(id),
    board VARCHAR(20) NOT NULL,
    role VARCHAR(20) NOT NULL,         -- user / assistant / system
    content TEXT NOT NULL,
    tool_calls JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_convo_team_board ON agent_conversation(team_id, board, created_at DESC);
```

前期用关键词搜索（天链已有模式），数据量大再加 pgvector。不提前引入复杂度。

### 5.3 行动力 — 能说也能做

ai_chat.py 增强：

```python
# 三板块角色
BOARD_PROMPTS = {
    "maintenance": "...运维专家（已有prompt）",
    "operations": "...运营分析助手",
    "admin": "...平台管理助手",  
}

# function calling 工具（调已有Service）
MAINTENANCE_TOOLS = [
    {"name": "query_devices", "handler": device_service.list_devices},
    {"name": "query_alerts", "handler": alarm_service.get_active_alarms},
    {"name": "query_telemetry", "handler": telemetry_service.get_latest},
    {"name": "diagnose_device", "handler": ai_diagnosis.diagnose},
    {"name": "search_memory", "handler": agent_memory_service.search},
    {"name": "get_station_summary", "handler": station_service.get_summary},
]

OPERATIONS_TOOLS = [
    {"name": "query_orders", "handler": order_service.list_orders},
    {"name": "query_revenue", "handler": analytics_service.get_revenue},
    {"name": "query_fleet", "handler": enterprise_service.get_fleet},
    {"name": "search_memory", "handler": agent_memory_service.search},
]

ADMIN_TOOLS = [
    {"name": "query_system_health", "handler": health_service.check},
    {"name": "query_audit_logs", "handler": audit_service.list_logs},
    {"name": "query_findings", "handler": agent_memory_service.findings},
    {"name": "search_memory", "handler": agent_memory_service.search},
]
```

**需要人工时**，助手回复格式：
```json
{
  "answer": "3号桩连续离线超过30分钟，疑似通信模块故障",
  "actions": [
    {"label": "查看设备详情", "url": "/devices/123"},
    {"label": "查看诊断记录", "url": "/diagnosis/456"}
  ],
  "recommended_action": "建议派工检修通信模块，预计2小时修复",
  "needs_human": true,
  "urgency": "high"
}
```

## 6. BYOK（租户自带模型）

一张表：

```sql
CREATE TABLE agent_team_model_config (
    team_id INTEGER PRIMARY KEY REFERENCES teams(id),
    provider VARCHAR(50) NOT NULL,
    endpoint TEXT NOT NULL,
    api_key_encrypted TEXT NOT NULL,
    model_name VARCHAR(100) NOT NULL,
    max_tokens INT DEFAULT 4096,
    temperature FLOAT DEFAULT 0.3,
    enabled BOOLEAN DEFAULT true,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

ai_model_config.py 增加：
```python
def get_model_for_team(team_id):
    """优先租户配置，fallback全局"""
    team_cfg = db.query(AgentTeamModelConfig).filter_by(team_id=team_id, enabled=True).first()
    if team_cfg:
        return decrypt(team_cfg)
    return get_model_for_task("chat_general")  # 已有逻辑
```

## 7. 通知（完全复用）

零新增。巡检发现 → 需要通知时直接调：
```python
from app.services.channel_providers import dispatch_real_channel
await dispatch_real_channel("im", payload, team_id)
```

## 8. 前端

### 三板块助手面板（侧边栏）
- 右上角 🤖 按钮开关
- 对话区 + 快捷操作按钮
- 快捷操作：一键巡检 / 今日摘要 / 设备诊断（运维）；收益概览 / 异常订单（运营）；系统健康 / 安全扫描（管理）

### Agent设置页（admin）
- 模型配置（BYOK）
- 巡检发现列表（open/resolved）
- 记忆管理

## 9. 实施

| 阶段 | 内容 | 新增代码 |
|------|------|---------|
| **P1 记忆+巡检** | 2张表 + agent_patrol.py + agent_memory_service.py | ~800行 |
| **P2 对话增强** | ai_chat.py 加function calling + 三板块prompt + 对话持久化 | ~500行 |
| **P3 CLI + BYOK** | CLI入口 + agent_team_model_config表 + agent_api_token表 | ~600行 |
| **P4 前端助手** | 侧边栏组件 + 设置页 | ~500行 |
| **合计** | | **~2400行** |

**P1做完**：天链会自己巡检、记录发现、自动通知 — 从"死"变"活"。
**P2做完**：用户可以跟助手对话查数据、触发诊断 — 能说能做。
**P3做完**：智能体（和运维）可以通过CLI操作天链 — Agent-native。
**全部做完**：无人值守的光储充智能体系统。

## 10. 不做清单（防虚胖）

- ❌ 不建技能注册框架 — Celery任务就是技能
- ❌ 不建工具注册框架 — function calling JSON够用
- ❌ 不引入pgvector — 前期关键词搜索够用
- ❌ 不引入外部智能体框架 — Hermes/Dify/CrewAI都不适合多租户企业场景
- ❌ 不建复杂工作板流转 — finding表open/resolved两态够用
- ❌ 不自建通知系统 — channel_providers已有

## 11. 后续（Phase 2）

- 光储充专精模型（微调）
- pgvector语义搜索（数据量大时）
- 跨租户知识共享（脱敏故障案例）
- 多模态诊断（设备照片）

---

*v0.3.1 定稿。核心：2400行代码让天链变活，且对智能体友好。*
