"""
AI 诊断引擎单元测试

测试 ai_diagnosis.py 核心功能：
- _parse_json_response() 各种JSON格式解析
- _build_analysis_prompt() prompt 构建
- analyze_device_logs() 完整流程（mock LLM调用）
- analyze_with_fallback() 降级逻辑
"""
import json
import socket
import subprocess

import pytest
import requests
from unittest.mock import patch, MagicMock, call

from app.core import url_safety as _url_safety

from app.services.ai_diagnosis import (
    _parse_json_response,
    _build_analysis_prompt,
    _call_llm,
    _call_hermes,
    analyze_device_logs,
    analyze_with_fallback,
    SYSTEM_PROMPT,
)
from app.services.ai_model_config import TaskType
import app.services.ai_diagnosis as ai_mod


# ===================================================================
# _parse_json_response 测试
# ===================================================================


class TestParseJsonResponse:
    def test_plain_json(self):
        """标准JSON"""
        content = '{"fault_type": "电网过压", "severity": "high"}'
        result = _parse_json_response(content)
        assert result["fault_type"] == "电网过压"
        assert result["severity"] == "high"

    def test_json_with_code_fence(self):
        """代码块包裹的JSON"""
        content = '```json\n{"fault_type": "电网过压", "severity": "high"}\n```'
        result = _parse_json_response(content)
        assert result["fault_type"] == "电网过压"

    def test_json_with_markdown_fence(self):
        """Markdown代码块包裹的JSON"""
        content = '```\n{"fault_type": "通讯异常", "confidence": 0.9}\n```'
        result = _parse_json_response(content)
        assert result["fault_type"] == "通讯异常"
        assert result["confidence"] == 0.9

    def test_json_with_trailing_text(self):
        """JSON后有额外文字"""
        content = '{"fault_type": "过温"} 以上是分析结果'
        result = _parse_json_response(content)
        assert result["fault_type"] == "过温"

    def test_json_with_leading_text(self):
        """JSON前有文字说明"""
        content = '分析结果：{"fault_type": "BMS故障"}'
        result = _parse_json_response(content)
        assert result["fault_type"] == "BMS故障"

    def test_json_with_fence_and_surrounding_text(self):
        """复杂格式 - 代码块+前后有文字"""
        content = """分析如下：
```json
{
  "fault_type": "绝缘故障",
  "fault_location": "光伏组件",
  "root_cause": "绝缘电阻下降",
  "severity": "critical",
  "confidence": 0.95
}
```
以上是根据日志的分析结果"""
        result = _parse_json_response(content)
        assert result["fault_type"] == "绝缘故障"
        assert result["fault_location"] == "光伏组件"
        assert result["severity"] == "critical"
        assert result["confidence"] == 0.95

    def test_complex_nested_json(self):
        """嵌套数组的JSON"""
        content = """{
  "fault_type": "通讯中断",
  "severity": "high",
  "possible_causes": ["CAN总线故障", "终端电阻异常"],
  "immediate_actions": ["检查CAN线缆", "检查终端电阻"],
  "repair_suggestions": ["更换CAN收发器"],
  "preventive_measures": ["定期检查通信线路"],
  "remote_fixable": false
}"""
        result = _parse_json_response(content)
        assert result["fault_type"] == "通讯中断"
        assert result["remote_fixable"] is False
        assert len(result["possible_causes"]) == 2
        assert result["possible_causes"][0] == "CAN总线故障"

    def test_empty_string_raises(self):
        """空字符串应抛出异常"""
        with pytest.raises(Exception):
            _parse_json_response("")

    def test_no_json_raises(self):
        """无JSON内容应抛出异常"""
        with pytest.raises(Exception):
            _parse_json_response("这是一个普通的文本说明")

    def test_invalid_json_raises(self):
        """无效JSON应抛出异常"""
        with pytest.raises(json.JSONDecodeError):
            _parse_json_response('{"fault_type": "测试", invalid}')

    def test_multiple_blocks_uses_first_json_fence(self):
        """多个代码块时优先匹配带有```json标记的"""
        # regex ```(?:json)? 会匹配第一个```代码块，不要求json标记
        # 所以第一个 ```python 会被匹配，print('hello')非JSON会失败
        content = '''
Here is the analysis:
```json
{"fault_type": "正确结果"}
```
```python
print("not this")
```'''
        result = _parse_json_response(content)
        assert result["fault_type"] == "正确结果"


# ===================================================================
# _build_analysis_prompt 测试
# ===================================================================


class TestBuildAnalysisPrompt:
    def test_basic_structure(self):
        """基本结构包含设备信息和日志"""
        device_info = {
            "id": 1,
            "name": "测试逆变器",
            "type_name": "inverter",
            "sn": "SN001",
            "station_name": "测试站点",
            "firmware_version": "v3.0.0",
        }
        logs = [
            "[INFO] 系统自检完成",
            "[WARN] 电压异常",
        ]
        prompt = _build_analysis_prompt(device_info, logs)

        assert "设备ID: 1" in prompt
        assert "设备名称: 测试逆变器" in prompt
        assert "设备类型: inverter" in prompt
        assert "设备SN: SN001" in prompt
        assert "所属站点: 测试站点" in prompt
        assert "固件版本: v3.0.0" in prompt
        assert "系统自检完成" in prompt
        assert "电压异常" in prompt
        assert "最近2条" in prompt

    def test_with_fault_context(self):
        """包含故障上下文的prompt"""
        device_info = {
            "id": 1,
            "name": "充电桩01",
            "type_name": "charger",
            "sn": "SN002",
            "station_name": "充电站A",
            "firmware_version": "v2.1.0",
        }
        logs = ["[ERROR] 急停按钮状态: PRESSED!"]
        fault_context = {
            "level": "high",
            "content": "急停按钮被按下",
            "fault_code": "0x0101",
            "fault_source": "硬件急停",
            "created_at": "2026-01-15T10:30:00",
        }
        prompt = _build_analysis_prompt(device_info, logs, fault_context)

        assert "设备ID: 1" in prompt
        assert "告警等级: high" in prompt
        assert "告警内容: 急停按钮被按下" in prompt
        assert "故障码: 0x0101" in prompt
        assert "故障源: 硬件急停" in prompt
        assert "发生时间: 2026-01-15T10:30:00" in prompt
        assert "急停按钮状态: PRESSED!" in prompt

    def test_without_fault_context(self):
        """无故障上下文时不应包含故障相关信息"""
        device_info = {"id": 1, "name": "设备1", "type_name": "unknown"}
        prompt = _build_analysis_prompt(device_info, ["test"])
        assert "告警等级" not in prompt
        assert "故障码" not in prompt

    def test_log_truncation(self):
        """超过50条日志只取最后50条"""
        device_info = {"id": 1, "name": "test", "type_name": "test"}
        logs = [f"log_{i}" for i in range(100)]
        prompt = _build_analysis_prompt(device_info, logs)
        assert "最近100条" in prompt
        # 应包含最后50条而非前50条
        assert "log_99" in prompt
        assert "log_0" not in prompt


# ===================================================================
# analyze_device_logs 测试
# ===================================================================


class TestAnalyzeDeviceLogs:
    FAKE_DEVICE = {"id": 1, "name": "测试设备", "type_name": "inverter"}
    FAKE_LOGS = ["[WARN] 电压异常: 265V"]
    FAKE_LLM_RESPONSE = """{
        "fault_type": "电网过压",
        "fault_location": "A相输入端",
        "root_cause": "电网波动",
        "severity": "high",
        "confidence": 0.85,
        "possible_causes": ["电网波动"],
        "immediate_actions": ["检查电网"],
        "repair_suggestions": ["调整阈值"],
        "preventive_measures": ["加装保护"],
        "remote_fixable": true
    }"""

    @patch("app.services.ai_diagnosis._call_llm")
    @patch("app.services.ai_diagnosis.model_manager")
    def test_success_call(self, mock_manager, mock_call_llm):
        """成功调用LLM并解析结果"""
        mock_manager.get_model_for_task.return_value = {
            "name": "TP/ModelB5.1",
            "model_id": "llm-b",
            "base_url": "https://test.url",
            "api_key": "test-key",
        }
        mock_call_llm.return_value = self.FAKE_LLM_RESPONSE

        result = analyze_device_logs(self.FAKE_DEVICE, self.FAKE_LOGS)

        assert result["success"] is True
        assert result["result"]["fault_type"] == "电网过压"
        assert result["result"]["severity"] == "high"
        assert result["result"]["confidence"] == 0.85
        assert result["result"]["remote_fixable"] is True
        assert result["model_used"] == "TP/ModelB5.1(llm-b)"
        assert result["duration_ms"] >= 0
        assert result["raw_response"] is not None

    @patch("app.services.ai_diagnosis._call_llm")
    @patch("app.services.ai_diagnosis.model_manager")
    def test_failed_llm_call(self, mock_manager, mock_call_llm):
        """LLM调用失败"""
        mock_manager.get_model_for_task.return_value = {
            "name": "TP/ModelB5.1",
            "model_id": "llm-b",
        }
        mock_call_llm.side_effect = Exception("API连接超时")

        result = analyze_device_logs(self.FAKE_DEVICE, self.FAKE_LOGS)

        assert result["success"] is False
        assert result["result"] is None
        assert result["error"]  # cc2272b84 安全脱敏: error 已泛化为通用消息, 仅验证失败返回了脱敏错误
        assert result["model_used"] is None

    @patch("app.services.ai_diagnosis._call_llm")
    @patch("app.services.ai_diagnosis.model_manager")
    def test_no_model_config(self, mock_manager, mock_call_llm):
        """无可用模型配置"""
        mock_manager.get_model_for_task.return_value = None

        result = analyze_device_logs(self.FAKE_DEVICE, self.FAKE_LOGS)

        assert result["success"] is False
        assert result["error"]  # cc2272b84 安全脱敏: 无模型配置异常也被泛化, 仅验证失败返回了 error
        mock_call_llm.assert_not_called()

    @patch("app.services.ai_diagnosis._call_llm")
    @patch("app.services.ai_diagnosis.model_manager")
    def test_invalid_llm_response(self, mock_manager, mock_call_llm):
        """LLM返回无效JSON"""
        mock_manager.get_model_for_task.return_value = {
            "name": "TP/ModelB5.1",
            "model_id": "llm-b",
        }
        mock_call_llm.return_value = "这不是JSON"

        result = analyze_device_logs(self.FAKE_DEVICE, self.FAKE_LOGS)

        assert result["success"] is False
        assert result["result"] is None
        # 应保存原始响应
        assert result["raw_response"] == "这不是JSON"

    @patch("app.services.ai_diagnosis._call_llm")
    @patch("app.services.ai_diagnosis.model_manager")
    def test_custom_task_type(self, mock_manager, mock_call_llm):
        """指定自定义任务类型"""
        mock_manager.get_model_for_task.return_value = {
            "name": "TP/DS4F",
            "model_id": "llm-fast-a",
        }
        mock_call_llm.return_value = self.FAKE_LLM_RESPONSE

        analyze_device_logs(
            self.FAKE_DEVICE, self.FAKE_LOGS,
            task_type=TaskType.FAULT_CLASSIFY
        )
        mock_manager.get_model_for_task.assert_called_once_with(
            TaskType.FAULT_CLASSIFY
        )


# ===================================================================
# analyze_with_fallback 测试
# ===================================================================


class TestAnalyzeWithFallback:
    FAKE_DEVICE = {"id": 1, "name": "test", "type_name": "inverter"}
    FAKE_LOGS = ["[WARN] test"]
    SUCCESS_RESULT = {
        "success": True,
        "result": {"fault_type": "test"},
        "model_used": "TP/ModelB5.1(llm-b)",
        "duration_ms": 1000,
    }
    FAILED_RESULT = {
        "success": False,
        "result": None,
        "error": "mock fail",
        "model_used": None,
        "duration_ms": 500,
    }

    @patch("app.services.ai_diagnosis.analyze_device_logs")
    def test_first_task_succeeds(self, mock_analyze):
        """第一个任务成功，直接返回"""
        mock_analyze.return_value = self.SUCCESS_RESULT

        result = analyze_with_fallback(self.FAKE_DEVICE, self.FAKE_LOGS)

        assert result["success"] is True
        assert result["result"]["fault_type"] == "test"
        # 应该只调用了第一次
        assert mock_analyze.call_count == 1

    @patch("app.services.ai_diagnosis.analyze_device_logs")
    def test_second_task_succeeds_after_first_fails(self, mock_analyze):
        """第一个失败，第二个成功"""
        mock_analyze.side_effect = [
            self.FAILED_RESULT,  # log_analysis 失败
            self.SUCCESS_RESULT,  # fault_classify 成功
        ]

        result = analyze_with_fallback(self.FAKE_DEVICE, self.FAKE_LOGS)

        assert result["success"] is True
        assert result["result"]["fault_type"] == "test"
        assert mock_analyze.call_count == 2

    @patch("app.services.ai_diagnosis.analyze_device_logs")
    def test_all_tasks_fail(self, mock_analyze):
        """所有任务都失败"""
        mock_analyze.return_value = self.FAILED_RESULT

        result = analyze_with_fallback(self.FAKE_DEVICE, self.FAKE_LOGS)

        assert result["success"] is False
        assert "所有诊断引擎均失败" in result["error"]
        # 应该重试了4个任务
        assert mock_analyze.call_count == 4

    @patch("app.services.ai_diagnosis.analyze_device_logs")
    def test_fallback_task_order(self, mock_analyze):
        """验证降级时的任务顺序"""
        mock_analyze.side_effect = [
            self.FAILED_RESULT,
            self.FAILED_RESULT,
            self.SUCCESS_RESULT,
            self.SUCCESS_RESULT,  # 不会被调用
        ]

        result = analyze_with_fallback(self.FAKE_DEVICE, self.FAKE_LOGS)

        assert result["success"] is True
        # 第三个任务成功后就返回了
        assert mock_analyze.call_count == 3

        # 验证调用参数：前三次的task_type分别是log_analysis, fault_classify, root_cause
        calls = mock_analyze.call_args_list
        assert calls[0].kwargs["task_type"] == TaskType.LOG_ANALYSIS
        assert calls[1].kwargs["task_type"] == TaskType.FAULT_CLASSIFY
        assert calls[2].kwargs["task_type"] == TaskType.ROOT_CAUSE


# ===================================================================
# _call_llm 测试 (直调服务商C CodingPlan API)
# ===================================================================


@pytest.fixture(autouse=True)
def _fake_public_dns(monkeypatch):
    """api.example.com 本机不可解析; SSRF 出站校验按公网 IP 放行(确定性)。"""
    real = socket.getaddrinfo

    def fake(host, *a, **kw):
        try:
            return real(host, *a, **kw)
        except (socket.gaierror, socket.error):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(_url_safety.socket, "getaddrinfo", fake)


class TestCallLlm:
    """直接测试 _call_llm 的请求构造、响应解析与异常分支。

    _call_llm 内部 `import requests` 再 requests.post，故 patch requests.post。
    """

    MODEL_CONFIG = {
        "name": "TP/ModelB5.1",
        "model_id": "llm-b",
        "base_url": "https://api.example.com/v1",
        "api_key": "sk-test-key",
        "max_tokens": 4096,
    }

    def _ok_response(self, content="诊断结果"):
        """构造 choices 非空的正常响应 mock。"""
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = {
            "choices": [{"message": {"content": content}}]
        }
        return resp

    @patch("requests.post")
    def test_success_returns_content(self, mock_post):
        """正常返回 choices[0].message.content。"""
        mock_post.return_value = self._ok_response("电网过压")
        assert _call_llm(self.MODEL_CONFIG, "sys", "usr") == "电网过压"

    @patch("requests.post")
    def test_url_strips_trailing_slash(self, mock_post):
        """base_url 末尾斜杠需剥离，再拼 /chat/completions。"""
        mock_post.return_value = self._ok_response()
        cfg = dict(self.MODEL_CONFIG, base_url="https://api.example.com/v1/")
        _call_llm(cfg, "sys", "usr")
        url = mock_post.call_args.args[0]
        assert url == "https://api.example.com/v1/chat/completions"

    @patch("requests.post")
    def test_url_without_trailing_slash(self, mock_post):
        """base_url 无末尾斜杠时直接拼接。"""
        mock_post.return_value = self._ok_response()
        _call_llm(self.MODEL_CONFIG, "sys", "usr")
        assert mock_post.call_args.args[0] == "https://api.example.com/v1/chat/completions"

    @patch("requests.post")
    def test_authorization_bearer_header(self, mock_post):
        """Authorization 头须为 Bearer {api_key}。"""
        mock_post.return_value = self._ok_response()
        _call_llm(self.MODEL_CONFIG, "sys", "usr")
        headers = mock_post.call_args.kwargs["headers"]
        assert headers["Authorization"] == "Bearer sk-test-key"
        assert headers["Content-Type"] == "application/json"

    @patch("requests.post")
    def test_payload_structure(self, mock_post):
        """payload 须含 model_id、system+user 双消息、temperature=0.3。"""
        mock_post.return_value = self._ok_response()
        _call_llm(self.MODEL_CONFIG, "SYS", "USR")
        payload = mock_post.call_args.kwargs["json"]
        assert payload["model"] == "llm-b"
        assert payload["messages"] == [
            {"role": "system", "content": "SYS"},
            {"role": "user", "content": "USR"},
        ]
        assert payload["temperature"] == 0.3
        assert payload["max_tokens"] == 4096

    @patch("requests.post")
    def test_default_max_tokens_when_absent(self, mock_post):
        """config 缺 max_tokens 时回落到默认 8192。"""
        mock_post.return_value = self._ok_response()
        cfg = {"name": "x", "model_id": "m", "base_url": "https://x", "api_key": "k"}
        _call_llm(cfg, "sys", "usr")
        assert mock_post.call_args.kwargs["json"]["max_tokens"] == 8192

    @patch("requests.post")
    def test_timeout_is_60_seconds(self, mock_post):
        """请求超时硬编码为 60 秒。"""
        mock_post.return_value = self._ok_response()
        _call_llm(self.MODEL_CONFIG, "sys", "usr")
        assert mock_post.call_args.kwargs["timeout"] == 60

    @patch("requests.post")
    def test_raises_on_http_error(self, mock_post):
        """非 2xx 响应 raise_for_status 抛 HTTPError。"""
        mock_post.return_value = MagicMock(
            raise_for_status=MagicMock(
                side_effect=requests.exceptions.HTTPError("500 Server Error")
            )
        )
        with pytest.raises(requests.exceptions.HTTPError):
            _call_llm(self.MODEL_CONFIG, "sys", "usr")

    @patch("requests.post")
    def test_raises_when_no_choices_key(self, mock_post):
        """响应无 choices 字段视为异常。"""
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = {"error": "rate limited"}
        mock_post.return_value = resp
        with pytest.raises(Exception, match="LLM返回异常"):
            _call_llm(self.MODEL_CONFIG, "sys", "usr")

    @patch("requests.post")
    def test_content_none_falls_back_to_reasoning_content(self, mock_post):
        """reasoning 模型 content=None 仅 reasoning_content → 返回 reasoning_content。"""
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = {
            "choices": [{"message": {"content": None, "reasoning_content": "诊断推理"}}]
        }
        mock_post.return_value = resp
        assert _call_llm(self.MODEL_CONFIG, "sys", "usr") == "诊断推理"

    @patch("requests.post")
    def test_both_content_and_reasoning_missing_raises(self, mock_post):
        """content 与 reasoning_content 均缺失 → 明确 ValueError, 不静默。"""
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = {"choices": [{"message": {"content": None}}]}
        mock_post.return_value = resp
        with pytest.raises(ValueError, match="LLM 返回空 content"):
            _call_llm(self.MODEL_CONFIG, "sys", "usr")

    @patch("requests.post")
    def test_raises_when_empty_choices(self, mock_post):
        """choices 为空列表同样视为异常。"""
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = {"choices": []}
        mock_post.return_value = resp
        with pytest.raises(Exception, match="LLM返回异常"):
            _call_llm(self.MODEL_CONFIG, "sys", "usr")


# ===================================================================
# _call_hermes 测试 (Hermes CLI 行为分支)
# ===================================================================
# 注: argv 安全 + shell=False 由 tests/test_shell_injection.py 覆盖;
#     本类补行为分支: 失败返回码 / 空 stderr / 空输出 / 超时。


class TestCallHermesBehavior:
    """_call_hermes 的行为分支 (returncode / 空 stdout / 超时)。"""

    @staticmethod
    def _fake_proc(returncode=0, stdout="ok\n", stderr=""):
        return MagicMock(returncode=returncode, stdout=stdout, stderr=stderr)

    def test_success_strips_stdout(self, monkeypatch):
        monkeypatch.setattr(ai_mod.subprocess, "run", lambda *a, **k: self._fake_proc(stdout="  reply\n"))
        assert _call_hermes("prompt") == "reply"

    def test_nonzero_returncode_with_stderr(self, monkeypatch):
        """returncode!=0 且有 stderr → 抛出含 stderr 的异常。"""
        monkeypatch.setattr(ai_mod.subprocess, "run", lambda *a, **k: self._fake_proc(returncode=1, stderr="boom"))
        with pytest.raises(Exception, match="Hermes调用失败: boom"):
            _call_hermes("prompt")

    def test_nonzero_returncode_empty_stderr(self, monkeypatch):
        """returncode!=0 且 stderr 为空 → 兜底'未知错误'。"""
        monkeypatch.setattr(ai_mod.subprocess, "run", lambda *a, **k: self._fake_proc(returncode=2, stderr=""))
        with pytest.raises(Exception, match="未知错误"):
            _call_hermes("prompt")

    def test_empty_stdout_raises(self, monkeypatch):
        """returncode=0 但 stdout 为空 → 抛'返回空结果'。"""
        monkeypatch.setattr(ai_mod.subprocess, "run", lambda *a, **k: self._fake_proc(stdout=""))
        with pytest.raises(Exception, match="Hermes返回空结果"):
            _call_hermes("prompt")

    def test_timeout_propagates(self, monkeypatch):
        """subprocess 超时异常不被吞，向上抛出。"""
        def boom(*a, **k):
            raise subprocess.TimeoutExpired(cmd="hermes", timeout=1)
        monkeypatch.setattr(ai_mod.subprocess, "run", boom)
        with pytest.raises(subprocess.TimeoutExpired):
            _call_hermes("prompt", timeout_seconds=1)

    def test_timeout_seconds_forwarded(self, monkeypatch):
        """timeout_seconds 须透传给 subprocess.run。"""
        captured = {}

        def fake_run(args, **kwargs):
            captured["timeout"] = kwargs.get("timeout")
            return self._fake_proc()

        monkeypatch.setattr(ai_mod.subprocess, "run", fake_run)
        _call_hermes("prompt", timeout_seconds=30)
        assert captured["timeout"] == 30

    def test_default_timeout_is_120(self, monkeypatch):
        captured = {}

        def fake_run(args, **kwargs):
            captured["timeout"] = kwargs.get("timeout")
            return self._fake_proc()

        monkeypatch.setattr(ai_mod.subprocess, "run", fake_run)
        _call_hermes("prompt")
        assert captured["timeout"] == 120


# ===================================================================
# analyze_device_logs 的 use_hermes 路径测试 (lines 173-185)
# ===================================================================


class TestAnalyzeDeviceLogsHermesPath:
    """use_hermes=True 分支: 成功直返 / 失败降级到直调 LLM。"""

    DEVICE = {"id": 1, "name": "测试设备", "type_name": "inverter"}
    LOGS = ["[WARN] 电压异常"]
    LLM_JSON = '{"fault_type": "电网过压", "severity": "high"}'

    @patch("app.services.ai_diagnosis._call_hermes")
    @patch("app.services.ai_diagnosis._call_llm")
    @patch("app.services.ai_diagnosis.model_manager")
    def test_hermes_success_returns_hermes_model(self, mock_manager, mock_llm, mock_hermes):
        """use_hermes=True 且 Hermes 成功 → model_used=Hermes, 不调 LLM。"""
        mock_hermes.return_value = self.LLM_JSON
        result = analyze_device_logs(self.DEVICE, self.LOGS, use_hermes=True)

        assert result["success"] is True
        assert result["model_used"] == "Hermes"
        assert result["result"]["fault_type"] == "电网过压"
        mock_llm.assert_not_called()

    @patch("app.services.ai_diagnosis._call_hermes")
    @patch("app.services.ai_diagnosis._call_llm")
    @patch("app.services.ai_diagnosis.model_manager")
    def test_hermes_failure_falls_back_to_llm(self, mock_manager, mock_llm, mock_hermes):
        """use_hermes=True 但 Hermes 失败 → 降级到直调 LLM 并成功。

        这条路径依赖 line 178 的 logging.warning —— 若未 `import logging`
        会抛 NameError, 降级失败。本测试即用于锁定该降级契约。
        """
        mock_hermes.side_effect = Exception("hermes down")
        mock_manager.get_model_for_task.return_value = {
            "name": "TP/ModelB5.1", "model_id": "llm-b",
            "base_url": "https://x", "api_key": "k",
        }
        mock_llm.return_value = self.LLM_JSON

        result = analyze_device_logs(self.DEVICE, self.LOGS, use_hermes=True)

        assert result["success"] is True
        assert result["model_used"] == "TP/ModelB5.1(llm-b)"
        # Hermes 失败后确实走了 LLM 降级
        mock_llm.assert_called_once()

    @patch("app.services.ai_diagnosis._call_hermes")
    @patch("app.services.ai_diagnosis._call_llm")
    @patch("app.services.ai_diagnosis.model_manager")
    def test_hermes_failure_and_llm_also_fails(self, mock_manager, mock_llm, mock_hermes):
        """Hermes 失败、降级 LLM 也失败 → 整体失败, 暴露真实错误。"""
        mock_hermes.side_effect = Exception("hermes down")
        mock_manager.get_model_for_task.return_value = {
            "name": "TP/ModelB5.1", "model_id": "llm-b",
        }
        mock_llm.side_effect = Exception("API 连接超时")

        result = analyze_device_logs(self.DEVICE, self.LOGS, use_hermes=True)

        assert result["success"] is False
        assert result["error"]  # cc2272b84 安全脱敏: 不再透传 "API 连接超时", 仅验证失败返回了脱敏 error


# ===================================================================
# analyze_device_logs 空日志边界测试
# ===================================================================


class TestAnalyzeDeviceLogsEmptyLogs:
    """空日志仍应正常编排 (不崩溃)。"""

    @patch("app.services.ai_diagnosis._call_llm")
    @patch("app.services.ai_diagnosis.model_manager")
    def test_empty_logs_still_runs(self, mock_manager, mock_llm):
        """空日志列表: prompt 仍构建, LLM 仍调用, 解析正常即返回成功。"""
        mock_manager.get_model_for_task.return_value = {
            "name": "TP/ModelB5.1", "model_id": "llm-b",
        }
        mock_llm.return_value = '{"fault_type": "无异常", "severity": "low"}'

        result = analyze_device_logs({"id": 1, "name": "d"}, [])

        assert result["success"] is True
        assert result["result"]["fault_type"] == "无异常"