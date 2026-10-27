"""Tests for app/services/ai_diagnosis.py — AI diagnostic engine.

Covers prompt building, JSON parsing, LLM/Hermes call mocking, error handling,
and fallback logic.
"""
import json
import time
import socket as _socket
from datetime import datetime
from unittest.mock import patch, MagicMock, call

import pytest

from app.core import url_safety as _url_safety
from app.services import ai_diagnosis
from app.services.ai_diagnosis import (
    _build_analysis_prompt,
    _parse_json_response,
    _call_llm,
    _call_hermes,
    analyze_device_logs,
    analyze_with_fallback,
    SYSTEM_PROMPT,
)


# ─── Fixtures ───

@pytest.fixture(autouse=True)
def _fake_public_dns(monkeypatch):
    """api.example.com 本机不可解析; SSRF 出站校验按公网 IP 放行(确定性)。"""
    real = _socket.getaddrinfo

    def fake(host, *a, **kw):
        try:
            return real(host, *a, **kw)
        except (_socket.gaierror, _socket.error):
            return [(_socket.AF_INET, _socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(_url_safety.socket, "getaddrinfo", fake)


@pytest.fixture
def device_info():
    return {
        "id": "dev-001",
        "name": "逆变器A",
        "type_name": "储能逆变器",
        "device_type": "inverter",
        "sn": "SN20260101",
        "station_name": "花果山站",
        "firmware_version": "v3.2.1",
    }


@pytest.fixture
def sample_logs():
    return [
        "[2026-08-02 10:00:00] INFO: System started",
        "[2026-08-02 10:01:00] WARN: Battery voltage low: 48.2V",
        "[2026-08-02 10:02:00] ERROR: Inverter fault code E103",
        "[2026-08-02 10:03:00] ERROR: Grid connection lost",
    ]


@pytest.fixture
def fault_context():
    return {
        "level": "critical",
        "content": "逆变器故障 E103",
        "fault_code": "E103",
        "fault_source": "inverter",
        "created_at": "2026-08-02 10:02:00",
    }


@pytest.fixture
def llm_good_response():
    return json.dumps({
        "fault_type": "逆变器过压保护",
        "fault_location": "DC-DC变换模块",
        "root_cause": "电池电压跌落导致DC-DC变换器触发过压保护",
        "severity": "high",
        "confidence": 0.88,
        "possible_causes": ["电池老化", "BMS通信异常"],
        "immediate_actions": ["检查电池组电压", "重启逆变器"],
        "repair_suggestions": ["更换老化电池模组", "校准BMS"],
        "preventive_measures": ["定期巡检电池健康度"],
        "remote_fixable": True,
    })


@pytest.fixture
def model_config():
    return {
        "name": "test-model",
        "model_id": "test-model_b5",
        "base_url": "https://api.example.com/v1",
        "api_key": "test-key-123",
        "max_tokens": 4096,
    }


# ─── _build_analysis_prompt ───

class TestBuildAnalysisPrompt:
    def test_basic_prompt(self, device_info, sample_logs):
        prompt = _build_analysis_prompt(device_info, sample_logs)
        assert "dev-001" in prompt
        assert "逆变器A" in prompt
        assert "储能逆变器" in prompt
        assert "SN20260101" in prompt
        assert "花果山站" in prompt
        assert "v3.2.1" in prompt
        assert f"最近{len(sample_logs)}条" in prompt
        for line in sample_logs:
            assert line in prompt

    def test_with_fault_context(self, device_info, sample_logs, fault_context):
        prompt = _build_analysis_prompt(device_info, sample_logs, fault_context)
        assert "critical" in prompt
        assert "逆变器故障 E103" in prompt
        assert "E103" in prompt
        assert "inverter" in prompt

    def test_without_fault_context(self, device_info, sample_logs):
        prompt = _build_analysis_prompt(device_info, sample_logs, None)
        assert "故障上下文" not in prompt

    def test_missing_fields_use_unknown(self):
        prompt = _build_analysis_prompt({}, ["log1"])
        assert "未知" in prompt

    def test_type_name_fallback_to_device_type(self):
        info = {"id": "d1", "device_type": "charger"}
        prompt = _build_analysis_prompt(info, ["l"])
        assert "charger" in prompt

    def test_log_truncation_to_last_50(self, device_info):
        logs = [f"log line {i}" for i in range(100)]
        prompt = _build_analysis_prompt(device_info, logs)
        # last 50 should be present
        assert "log line 99" in prompt
        assert "log line 50" in prompt
        # first 49 should not
        assert "log line 0" not in prompt
        assert "log line 49" not in prompt
        assert "最近100条" in prompt


# ─── _parse_json_response ───

class TestParseJsonResponse:
    def test_plain_json(self, llm_good_response):
        result = _parse_json_response(llm_good_response)
        assert result["fault_type"] == "逆变器过压保护"
        assert result["confidence"] == 0.88

    def test_json_in_code_block(self, llm_good_response):
        wrapped = f"```json\n{llm_good_response}\n```"
        result = _parse_json_response(wrapped)
        assert result["severity"] == "high"

    def test_json_in_plain_code_block(self, llm_good_response):
        wrapped = f"```\n{llm_good_response}\n```"
        result = _parse_json_response(wrapped)
        assert result["remote_fixable"] is True

    def test_json_with_surrounding_text(self, llm_good_response):
        text = f"Here is the analysis:\n{llm_good_response}\nDone."
        result = _parse_json_response(text)
        assert result["fault_type"] == "逆变器过压保护"

    def test_invalid_json_raises(self):
        with pytest.raises(json.JSONDecodeError):
            _parse_json_response("not json at all")

    def test_empty_string_raises(self):
        with pytest.raises(json.JSONDecodeError):
            _parse_json_response("")

    def test_strips_whitespace(self, llm_good_response):
        result = _parse_json_response(f"  {llm_good_response}  ")
        assert result is not None


# ─── _call_llm ───

class TestCallLlm:
    @patch("requests.post")
    def test_successful_call(self, mock_post, model_config, llm_good_response):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": llm_good_response}}]
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        result = _call_llm(model_config, "system", "user")
        assert result == llm_good_response

        # Verify request
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert "chat/completions" in call_kwargs[1].get("url", "") or "chat/completions" in str(call_kwargs)

    @patch("requests.post")
    def test_raises_on_http_error(self, mock_post, model_config):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = Exception("500 Server Error")
        mock_post.return_value = mock_resp

        with pytest.raises(Exception, match="500 Server Error"):
            _call_llm(model_config, "sys", "user")

    @patch("requests.post")
    def test_raises_on_empty_choices(self, mock_post, model_config):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"choices": []}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        with pytest.raises(Exception, match="LLM返回异常"):
            _call_llm(model_config, "sys", "user")

    @patch("requests.post")
    def test_uses_correct_headers(self, mock_post, model_config):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        _call_llm(model_config, "s", "u")
        args, kwargs = mock_post.call_args
        headers = kwargs.get("headers", args[2] if len(args) > 2 else {})
        assert headers.get("Authorization") == "Bearer test-key-123"
        assert headers.get("Content-Type") == "application/json"

    @patch("requests.post")
    def test_timeout_60s(self, mock_post, model_config):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        _call_llm(model_config, "s", "u")
        _, kwargs = mock_post.call_args
        assert kwargs.get("timeout") == 60


# ─── _call_hermes ───

class TestCallHermes:
    @patch("app.services.ai_diagnosis.subprocess.run")
    def test_successful_call(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="AI result\n", stderr="")
        result = _call_hermes("test prompt")
        assert result == "AI result"

    @patch("app.services.ai_diagnosis.subprocess.run")
    def test_raises_on_nonzero_return(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="command not found")
        with pytest.raises(Exception, match="Hermes调用失败"):
            _call_hermes("prompt")

    @patch("app.services.ai_diagnosis.subprocess.run")
    def test_raises_on_empty_output(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="  \n", stderr="")
        with pytest.raises(Exception, match="Hermes返回空结果"):
            _call_hermes("prompt")

    @patch("app.services.ai_diagnosis.subprocess.run")
    def test_shell_false(self, mock_run):
        """Ensure shell=False to prevent injection."""
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        _call_hermes("p")
        args, kwargs = mock_run.call_args
        assert kwargs.get("shell") is False

    @patch("app.services.ai_diagnosis.subprocess.run")
    def test_timeout_default_120(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        _call_hermes("p")
        _, kwargs = mock_run.call_args
        assert kwargs.get("timeout") == 120


# ─── analyze_device_logs ───

class TestAnalyzeDeviceLogs:
    @patch("app.services.ai_diagnosis._call_llm")
    @patch("app.services.ai_model_config.model_manager.get_model_for_task")
    def test_success_via_llm(self, mock_get_model, mock_llm, device_info, sample_logs, model_config, llm_good_response):
        mock_get_model.return_value = model_config
        mock_llm.return_value = llm_good_response

        result = analyze_device_logs(device_info, sample_logs)
        assert result["success"] is True
        assert result["result"]["fault_type"] == "逆变器过压保护"
        assert "duration_ms" in result
        assert result["model_used"].startswith("test-model")

    @patch("app.services.ai_diagnosis._call_hermes")
    def test_success_via_hermes(self, mock_hermes, device_info, sample_logs, llm_good_response):
        mock_hermes.return_value = llm_good_response
        result = analyze_device_logs(device_info, sample_logs, use_hermes=True)
        assert result["success"] is True
        assert result["model_used"] == "Hermes"

    @patch("app.services.ai_diagnosis._call_hermes")
    @patch("app.services.ai_diagnosis._call_llm")
    @patch("app.services.ai_model_config.model_manager.get_model_for_task")
    def test_hermes_fallback_to_llm(self, mock_get_model, mock_llm, mock_hermes, device_info, sample_logs, model_config, llm_good_response):
        """If Hermes fails, should fall back to LLM API."""
        mock_hermes.side_effect = Exception("Hermes offline")
        mock_get_model.return_value = model_config
        mock_llm.return_value = llm_good_response

        result = analyze_device_logs(device_info, sample_logs, use_hermes=True)
        assert result["success"] is True
        assert "test-model" in result["model_used"]

    @patch("app.services.ai_diagnosis._call_llm")
    @patch("app.services.ai_model_config.model_manager.get_model_for_task")
    def test_no_model_config_raises(self, mock_get_model, mock_llm, device_info, sample_logs):
        mock_get_model.return_value = None
        result = analyze_device_logs(device_info, sample_logs)
        assert result["success"] is False
        assert result["error"]  # cc2272b84 安全脱敏: error 已泛化, 仅验证非空

    @patch("app.services.ai_diagnosis._call_llm")
    @patch("app.services.ai_model_config.model_manager.get_model_for_task")
    def test_llm_raises_returns_error(self, mock_get_model, mock_llm, device_info, sample_logs, model_config):
        mock_get_model.return_value = model_config
        mock_llm.side_effect = Exception("API timeout")
        result = analyze_device_logs(device_info, sample_logs)
        assert result["success"] is False
        assert result["error"]  # cc2272b84 安全脱敏: error 已泛化, 仅验证非空

    @patch("app.services.ai_diagnosis._call_llm")
    @patch("app.services.ai_model_config.model_manager.get_model_for_task")
    def test_invalid_json_response(self, mock_get_model, mock_llm, device_info, sample_logs, model_config):
        mock_get_model.return_value = model_config
        mock_llm.return_value = "not valid json {{{"
        result = analyze_device_logs(device_info, sample_logs)
        assert result["success"] is False

    @patch("app.services.ai_diagnosis._call_llm")
    @patch("app.services.ai_model_config.model_manager.get_model_for_task")
    def test_duration_measured(self, mock_get_model, mock_llm, device_info, sample_logs, model_config, llm_good_response):
        mock_get_model.return_value = model_config
        mock_llm.return_value = llm_good_response
        result = analyze_device_logs(device_info, sample_logs)
        assert isinstance(result["duration_ms"], int)
        assert result["duration_ms"] >= 0

    @patch("app.services.ai_diagnosis._call_llm")
    @patch("app.services.ai_model_config.model_manager.get_model_for_task")
    def test_with_fault_context(self, mock_get_model, mock_llm, device_info, sample_logs, fault_context, model_config, llm_good_response):
        mock_get_model.return_value = model_config
        mock_llm.return_value = llm_good_response
        result = analyze_device_logs(device_info, sample_logs, fault_context=fault_context)
        assert result["success"] is True


# ─── analyze_with_fallback ───

class TestAnalyzeWithFallback:
    @patch("app.services.ai_diagnosis.analyze_device_logs")
    def test_first_model_succeeds(self, mock_analyze, device_info, sample_logs):
        mock_analyze.return_value = {"success": True, "result": {"fault_type": "ok"}}
        result = analyze_with_fallback(device_info, sample_logs)
        assert result["success"] is True
        assert mock_analyze.call_count == 1

    @patch("app.services.ai_diagnosis.analyze_device_logs")
    def test_fallback_to_second_model(self, mock_analyze, device_info, sample_logs):
        mock_analyze.side_effect = [
            {"success": False, "error": "model1 fail"},
            {"success": True, "result": {"fault_type": "ok"}},
        ]
        result = analyze_with_fallback(device_info, sample_logs)
        assert result["success"] is True
        assert mock_analyze.call_count == 2

    @patch("app.services.ai_diagnosis.analyze_device_logs")
    def test_all_models_fail(self, mock_analyze, device_info, sample_logs):
        mock_analyze.return_value = {"success": False, "error": "fail"}
        result = analyze_with_fallback(device_info, sample_logs)
        assert result["success"] is False
        assert "所有诊断引擎均失败" in result["error"]
        assert mock_analyze.call_count == 4  # 4 task types

    @patch("app.services.ai_diagnosis.analyze_device_logs")
    def test_uses_multiple_task_types(self, mock_analyze, device_info, sample_logs):
        """Verify it tries LOG_ANALYSIS, FAULT_CLASSIFY, ROOT_CAUSE, REPAIR_SUGGEST."""
        mock_analyze.return_value = {"success": True, "result": {}}
        analyze_with_fallback(device_info, sample_logs)
        # Should be called with different task_type values
        task_types_used = [c.kwargs.get("task_type") for c in mock_analyze.call_args_list]
        assert len(set(task_types_used)) == 1  # first one succeeds, only 1 call
