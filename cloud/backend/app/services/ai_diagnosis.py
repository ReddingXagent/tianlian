#!/Users/xxx/.openclaw/workspace/projects/tianlian-v3/backend/venv/bin/python3
"""
AI 诊断引擎 - 分析设备日志，定位故障，给出处理建议

调用方式 (云服务器可部署):
1. 直调服务商CCodingPlan API (默认, 云服务器通用, 仅需API Key)
2. Hermes CLI (可选, 仅本地开发调试用)
"""
import json
import logging
import time
import re
import subprocess
from typing import Dict, List, Optional

from app.services.ai_model_config import model_manager, TaskType
from app.core.url_safety import UnsafeURLError, validate_external_url

logger = logging.getLogger(__name__)


# ========== Prompt 模板 ==========

SYSTEM_PROMPT = """你是一位资深的光储充运维故障诊断专家。你的任务是分析设备日志，定位故障原因，并给出处理建议。

## 设备类型
1. 储能逆变器 - 光伏储能系统的核心设备，连接光伏板、电池和电网
2. 直流充电桩 - 电动汽车充电设备
3. PCS (储能变流器) - 电池储能系统的能量转换设备

## 分析要求
请严格按照以下JSON格式输出分析结果，不要添加额外说明：

{
  "fault_type": "故障类型名称（简短）",
  "fault_location": "故障定位（具体到模块/组件）",
  "root_cause": "根因分析（详细说明可能的原因）",
  "severity": "low/medium/high/critical",
  "confidence": 0.95,
  "possible_causes": ["原因1", "原因2"],
  "immediate_actions": ["立即执行步骤1", "立即执行步骤2"],
  "repair_suggestions": ["维修建议1", "维修建议2"],
  "preventive_measures": ["预防措施1", "预防措施2"],
  "remote_fixable": true
}

注意：
- JSON必须合法，不要有尾随逗号
- 用中文输出
- 基于日志内容做出合理推断
- 不确定的不要乱猜，在confidence中体现
"""


def _build_analysis_prompt(
    device_info: Dict,
    logs: List[str],
    fault_context: Optional[Dict] = None
) -> str:
    """构建分析Prompt"""
    device_desc = f"""
## 设备信息
- 设备ID: {device_info.get('id')}
- 设备名称: {device_info.get('name', '未知')}
- 设备类型: {device_info.get('type_name', device_info.get('device_type', '未知'))}
- 设备SN: {device_info.get('sn', '未知')}
- 所属站点: {device_info.get('station_name', '未知')}
- 固件版本: {device_info.get('firmware_version', '未知')}
"""

    fault_desc = ""
    if fault_context:
        fault_desc = f"""
## 故障上下文
- 告警等级: {fault_context.get('level', '未知')}
- 告警内容: {fault_context.get('content', '未知')}
- 故障码: {fault_context.get('fault_code', '未知')}
- 故障源: {fault_context.get('fault_source', '未知')}
- 发生时间: {fault_context.get('created_at', '未知')}
"""

    log_text = "\n".join(logs[-50:])

    prompt = f"""{device_desc}{fault_desc}
## 设备日志（最近{len(logs)}条）
```
{log_text}
```

请分析以上日志，输出JSON格式的诊断结果。
"""
    return prompt


def _call_llm(model_config: Dict, system_prompt: str, user_prompt: str) -> str:
    """直接调用服务商CCodingPlan API (云服务器通用)"""
    import requests

    try:
        validate_external_url(model_config['base_url'])
    except UnsafeURLError:
        raise ValueError("AI模型 base_url 不安全(内网/环回/非 http(s)), 拒绝出站请求")
    url = f"{model_config['base_url'].rstrip('/')}/chat/completions"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {model_config['api_key']}"
    }

    payload = {
        "model": model_config["model_id"],
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.3,
        "max_tokens": model_config.get("max_tokens", 8192),
    }

    resp = requests.post(url, json=payload, headers=headers, timeout=60)
    resp.raise_for_status()
    data = resp.json()

    if "choices" in data and len(data["choices"]) > 0:
        # reasoning 模型(model_a-reasoner等)可能只返回 reasoning_content 而 content=None
        message = data["choices"][0].get("message", {}) or {}
        content = message.get("content") or message.get("reasoning_content") or ""
        if not content:
            raise ValueError("LLM 返回空 content")
        return content
    else:
        raise Exception(f"LLM返回异常: {data}")


def _call_hermes(prompt: str, timeout_seconds: int = 120) -> str:
    """通过Hermes CLI调用AI (仅本地开发可选)"""
    # shell=False + argv 列表: prompt 作为 -q 的数据参数原样传递, 无注入面
    cmd = ["hermes", "chat", "-q", prompt, "-Q"]
    proc = subprocess.run(cmd, shell=False, capture_output=True, text=True, timeout=timeout_seconds)
    if proc.returncode != 0:
        stderr = proc.stderr.strip() or "未知错误"
        raise Exception(f"Hermes调用失败: {stderr}")
    output = proc.stdout.strip()
    if not output:
        raise Exception("Hermes返回空结果")
    return output


def _parse_json_response(content: str) -> Dict:
    """从LLM响应中提取JSON"""
    content = content.strip()

    json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', content)
    if json_match:
        content = json_match.group(1).strip()

    start = content.find('{')
    end = content.rfind('}')
    if start >= 0 and end > start:
        content = content[start:end+1]

    return json.loads(content)


def analyze_device_logs(
    device_info: Dict,
    logs: List[str],
    fault_context: Optional[Dict] = None,
    task_type: str = TaskType.LOG_ANALYSIS,
    use_hermes: bool = False
) -> Dict:
    """
    分析设备日志，返回诊断结果

    默认: 直调服务商CCodingPlan API (云服务器通用)
    可选: use_hermes=True 使用Hermes CLI (仅本地)
    """
    start = time.time()
    raw_response = None
    model_used = None

    try:
        user_prompt = _build_analysis_prompt(device_info, logs, fault_context)
        combined_prompt = f"{SYSTEM_PROMPT}\n\n{user_prompt}"

        if use_hermes:
            try:
                raw_response = _call_hermes(combined_prompt)
                model_used = "Hermes"
            except Exception as hermes_err:
                logging.getLogger(__name__).warning("Hermes失败, 降级到直调API: %s", hermes_err)

        if raw_response is None:
            model_config = model_manager.get_model_for_task(task_type)
            if not model_config:
                raise Exception("没有可用的AI模型配置")
            raw_response = _call_llm(model_config, SYSTEM_PROMPT, user_prompt)
            model_used = f"{model_config['name']}({model_config['model_id']})"

        result = _parse_json_response(raw_response)
        duration = int((time.time() - start) * 1000)

        return {
            "success": True,
            "result": result,
            "raw_response": raw_response,
            "model_used": model_used,
            "duration_ms": duration
        }

    except Exception as e:
        duration = int((time.time() - start) * 1000)
        logger.exception("AI诊断调用失败: %s", e)
        return {
            "success": False,
            "result": None,
            "error": "服务内部错误，请稍后重试",
            "raw_response": raw_response,
            "model_used": model_used,
            "duration_ms": duration
        }


def analyze_with_fallback(
    device_info: Dict,
    logs: List[str],
    fault_context: Optional[Dict] = None
) -> Dict:
    """
    带fallback的分析 (云服务器版):
    1. 直调API - 主模型 (服务商CModelB5.1)
    2. 直调API - 备用模型 (服务商CDS4F)
    3. 全部失败
    """
    task_order = [
        TaskType.LOG_ANALYSIS,
        TaskType.FAULT_CLASSIFY,
        TaskType.ROOT_CAUSE,
        TaskType.REPAIR_SUGGEST,
    ]

    errors = []
    for task in task_order:
        result = analyze_device_logs(device_info, logs, fault_context, task_type=task, use_hermes=False)
        if result["success"]:
            return result
        errors.append(f"{task}: {result['error']}")

    return {
        "success": False,
        "result": None,
        "error": "所有诊断引擎均失败: " + "; ".join(errors),
        "raw_response": None,
        "model_used": None,
        "duration_ms": 0
    }
