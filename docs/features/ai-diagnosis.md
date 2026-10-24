# AI 智能诊断助手

## 概述

天链V3 AI 智能诊断助手通过集成大语言模型（LLM），自动分析光储充设备日志，实现故障定位、根因分析、处理建议等功能。

### 核心能力

- **手动日志分析**：用户粘贴设备日志或故障描述，AI自动诊断
- **告警自动触发**：告警产生时自动触发诊断流水线
- **知识库匹配**：诊断结果自动匹配已录入的故障码知识库
- **多模型降级**：支持多个AI模型，自动降级保障可用性
- **诊断历史**：所有诊断记录持久化，支持查询和追溯

---

## 架构

```
┌──────────────┐     ┌──────────────────┐     ┌───────────────┐
│  前端页面     │     │  API Router       │     │  数据库        │
│              │ ──▶ │  /api/v1/log-     │ ──▶ │  AI诊断记录表   │
│ - 故障诊断    │     │  analysis         │     └───────────────┘
│ - AI诊断面板  │     └────────┬─────────┘
└──────────────┘              │
                              │
                    ┌─────────▼─────────┐
                    │  诊断服务层         │
                    │                    │
                    │  ai_diagnosis.py   │
                    │  diagnostic_       │
                    │  pipeline.py       │
                    │  ai_model_config.py│
                    └─────────┬─────────┘
                              │
                    ┌─────────▼─────────┐
                    │  AI Model Provider │
                    │  (cloud-provider-token)    │
                    │  OpenAPI兼容       │
                    └───────────────────┘
```

### 组件说明

| 组件 | 文件 | 职责 |
|------|------|------|
| API路由 | `app/api/v1/log_analysis.py` | 处理HTTP请求，数据校验，入库 |
| 诊断引擎 | `app/services/ai_diagnosis.py` | 构建Prompt、调用LLM、解析响应 |
| 诊断流水线 | `app/services/diagnostic_pipeline.py` | 告警触发→读取日志→AI分析→匹配知识库→存储 |
| 模型配置 | `app/services/ai_model_config.py` | 多Provider管理、任务映射、fallback策略 |
| 日志模拟器 | `app/services/device_log_simulator.py` | 开发阶段模拟设备日志输出 |
| 数据模型 | `app/models/ai_diagnosis.py` | AIDiagnosisRecord ORM模型 |

---

## API 参考

所有 AI 诊断 API 前缀为 `/api/v1/log-analysis`，均需 JWT 认证。

### 手动日志分析

```
POST /api/v1/log-analysis/analyze
```

**请求体**:
```json
{
  "device_id": 1,
  "logs": [
    "[WARN] A相电压异常: 265V, 超过阈值264V",
    "[ERROR] 电网一段过压保护触发 (A相)"
  ],
  "fault_code": "0x01",
  "fault_description": "电网电压异常"
}
```

**响应**:
```json
{
  "code": 200,
  "message": "分析完成",
  "data": {
    "record_id": 1,
    "analysis": {
      "fault_type": "电网过压",
      "fault_location": "逆变器A相输入端",
      "root_cause": "电网电压超过保护阈值",
      "severity": "high",
      "confidence": 0.85,
      "immediate_actions": ["检查电网电压"],
      "repair_suggestions": ["调整过压保护阈值"],
      "preventive_measures": ["加装电涌保护器"],
      "remote_fixable": true
    },
    "model_used": "TP/ModelB5.1(llm-b)",
    "duration_ms": 2345
  }
}
```

### 触发告警诊断

```
POST /api/v1/log-analysis/trigger/{alarm_id}
```

触发告警的自动诊断流水线（将依次完成：读取日志→AI分析→知识库匹配→存储结果）。

### 获取诊断结果

```
GET /api/v1/log-analysis/{analysis_id}
```

### 诊断历史列表

```
GET /api/v1/log-analysis?page=1&page_size=20&status=completed&device_id=1
```

### 获取告警的诊断结果

```
GET /api/v1/log-analysis/alarm/{alarm_id}
```

### 模型配置管理

```bash
# 获取当前配置
GET /api/v1/log-analysis/model-config

# 更新Provider列表
POST /api/v1/log-analysis/model-config
Body: [{ "provider": "cloud-provider-token", "model_id": "...", ... }]

# 获取任务映射
GET /api/v1/log-analysis/model-config/task-mappings

# 更新任务映射
PUT /api/v1/log-analysis/model-config/task-mapping
Body: { "task_type": "log_analysis", "model_name": "TP/DS4P" }
```

---

## 模型配置指南

### 配置文件位置

`backend/app/ai_model_config.json`

### 配置结构

```json
{
  "providers": [
    {
      "provider": "cloud-provider-token",
      "model_id": "llm-b",
      "name": "TP/ModelB5.1",
      "base_url": "https://token-plan.cn-beijing.maas.cloud-providercs.com/compatible-mode/v1",
      "api_key": "",
      "context_window": 128000,
      "max_tokens": 16000,
      "enabled": true
    }
  ],
  "task_mappings": {
    "log_analysis": "TP/ModelB5.1",
    "fault_classify": "TP/DS4F",
    "root_cause": "TP/DS4P",
    "repair_suggest": "TP/ModelB5.1",
    "preventive": "TP/ModelB5.1"
  },
  "fallback_strategy": "next_available"
}
```

### 配置说明

| 字段 | 说明 |
|------|------|
| `provider` | 供应商标识（如 cloud-provider-token） |
| `model_id` | 模型ID（如 llm-pro-a, llm-b） |
| `name` | 显示名称（用于任务映射） |
| `base_url` | API地址（LlmGeneric兼容格式） |
| `api_key` | API密钥（可留空，从环境变量读取） |
| `enabled` | 是否启用 |

### 环境变量覆盖

API Key 优先从环境变量读取：

| 环境变量 | 对应 Provider |
|----------|---------------|
| `ALIYUN_TOKEN_API_KEY` | cloud-provider-token |

### 任务类型说明

| 任务类型 | 用途 | 推荐模型 |
|----------|------|----------|
| `log_analysis` | 日志分析 | ModelB5.1/DS4P |
| `fault_classify` | 故障分类 | DS4F（快速） |
| `root_cause` | 根因分析 | DS4P（强推理） |
| `repair_suggest` | 维修建议 | ModelB5.1 |
| `preventive` | 预防措施 | ModelB5.1 |

### Fallback 策略

当主模型不可用时，按以下顺序降级：
1. `log_analysis` → `fault_classify` → `root_cause` → `repair_suggest`
2. 每个任务的模型配置不同，分散风险

---

## 如何添加新的故障类型

### 1. 在日志模拟器中添加（开发调试用）

在 `app/services/device_log_simulator.py` 的 `INVERTER_FAULT_LOGS` 或 `CHARGER_FAULT_LOGS` 字典中添加：

```python
"0xNEW": [  # 新故障类型
    "[WARN] 故障描述1",
    "[ERROR] 故障触发",
]
```

### 2. 在知识库中添加故障码

通过知识库 API 添加对应的故障码记录，包含：
- 故障码（如 `0xNEW`）
- 故障名称
- 故障描述
- 可能的原因列表
- 维修建议列表

### 3. 调整 Prompt（如需改变分析粒度）

修改 `app/services/ai_diagnosis.py` 中的 `SYSTEM_PROMPT`：

- 在 `## 分析要求` 部分添加新字段描述
- 在 `JSON格式` 模板中添加新字段
- 在 `AIDiagnosisRecord` 模型中添加对应字段（如需持久化）

### 4. 验证

```bash
cd backend
source .venv/bin/activate
pytest tests/test_ai_diagnosis.py -v
pytest tests/test_log_analysis.py -v
```

---

## 诊断流水线

### 自动触发流程

```
告警创建
    │
    ▼
trigger_auto_diagnosis(alarm_id)
    │
    ▼
获取告警 + 设备 + 站点信息
    │
    ▼
远程读取设备日志（模拟器/真实）
    │
    ▼
AI 分析日志（analyze_with_fallback）
    │
    ▼
匹配知识库故障码
    │
    ▼
存储诊断记录到数据库
    │
    ▼
更新告警的诊断结果
```

### 字段映射

| AI输出字段 | 数据库字段 | 说明 |
|------------|-----------|------|
| fault_type | `fault_type` | 故障类型名称 |
| fault_location | `fault_location` | 故障定位 |
| root_cause | `root_cause` | 根因分析 |
| severity | `severity` | low/medium/high/critical |
| confidence | `confidence` | 置信度 0-1 |
| immediate_actions | `immediate_actions` | JSON数组 |
| repair_suggestions | `repair_suggestions` | JSON数组 |
| preventive_measures | `preventive_measures` | JSON数组 |
| remote_fixable | `remote_fixable` | 是否可远程修复 |

---

## 测试指南

### 运行测试

```bash
cd backend
source .venv/bin/activate

# 运行所有AI诊断相关测试
pytest tests/test_ai_diagnosis.py tests/test_log_analysis.py -v

# 运行全部测试
pytest -v
```

### 测试覆盖

| 测试文件 | 覆盖内容 |
|----------|----------|
| `tests/test_ai_diagnosis.py` | 核心诊断引擎单元测试 |
| `tests/test_log_analysis.py` | API路由集成测试 |

### 测试策略

- **核心引擎**：使用 `unittest.mock` 模拟 LLM 调用，专注于 prompt 构建、JSON 解析、fallback 逻辑
- **API 路由**：使用 FastAPI TestClient + mock 模拟内部服务调用
- **无需真实 API Key**：所有 AI 调用都被 mock 替代

### Mock 示例

```python
from unittest.mock import patch
from app.services.ai_diagnosis import analyze_device_logs

FAKE_RESPONSE = {
    "success": True,
    "result": {"fault_type": "电网过压", "severity": "high"},
    "model_used": "MockModel",
    "duration_ms": 1000,
}

@patch("app.services.ai_diagnosis._call_llm")
@patch("app.services.ai_diagnosis.model_manager")
def test_analysis(mock_manager, mock_call_llm):
    mock_manager.get_model_for_task.return_value = {
        "name": "Test", "model_id": "test-model",
    }
    mock_call_llm.return_value = '{"fault_type": "电网过压", "severity": "high"}'
    
    result = analyze_device_logs({"id": 1}, ["test log"])
    assert result["success"] is True
```

---

## 故障排查

### AI分析始终返回失败

1. 检查模型配置：`GET /api/v1/log-analysis/model-config`
2. 确认 API Key 已配置（文件或环境变量）
3. 检查网络连通性（云服务器是否能访问 API 地址）
4. 查看日志中的错误信息

### 诊断速度慢

1. 增大 `max_tokens` 限制
2. 减小输入日志数量（当前最多取最后50条）
3. 切换到较小的模型（如 `llm-fast-a`）
4. 调整 `temperature` 参数（越低越快）

### 诊断结果不准确

1. 检查 SYSTEM_PROMPT 中的分析要求是否明确
2. 尝试更强大的模型（如 `llm-pro-a`）
3. 提供更完整的设备日志（包括正常到异常的过渡）
4. 在 fault_context 中提供准确的故障码