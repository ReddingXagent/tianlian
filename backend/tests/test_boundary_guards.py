"""test_boundary_guards.py — 9 处除零/空列表 guard 的边界回归测试

被测对象: 卡片 b9a5870b 盘点的 9 个除零/空列表风险点。经 git blame + 源码核对,
当前 HEAD 这些位置全部已有 guard 覆盖, 无 bug 可修。本文件用边界输入锁定这些 guard,
防止将来被误删。

  #  guard (文件:行)                            保护语句                          边界输入
  -  -----------------------------------------  -------------------------------  -------------------------------
  1  device_data_service.get_statistics L218    sum(values)/len(values)          history 有记录但无该指标
  2  ml_model_service.extract_features L202     alarm_counts/len(alarm_data)     bms_alarm_word 全 NaN
  3  ml_model_service.train_anomaly_detector    anomaly_count/len(train_pred)    >=100 样本但有效特征 <20
     L402
  4  vpp.dispatch_optimizer                     sum(soc)/len(battery_resources)  battery 资源 soc 全 None
     get_aggregate_capacity L881
  5  charging.mode_balanced.evaluate L57        rated_power_kw/total             total=0 或 rated_power_kw=0
  6  charging_queue_service.compute_sort_score  (raw*weight)/total_weight        criteria 权重求和 = 0
     L93
  7  ai_chat._call_llm L203                     data["choices"][0]["message"]    choices=[]
  8  ai_chat._build_context_prompt L239         alarms[0]                        alarms=[]
  9  ai_diagnosis._call_llm L117                data["choices"][0]["message"]    choices=[]

每个测试喂入会让被保护语句抛 ZeroDivisionError / IndexError 的边界输入,
断言 (a) 不抛这些异常 (或转为约定的 error 异常), (b) 返回合理默认值 / error dict。
若 guard 被误删, 对应测试将以 ZeroDivisionError / IndexError 失败。
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services.ai_chat import _build_context_prompt
from app.services.ai_chat import _call_llm as chat_call_llm
from app.services.ai_diagnosis import _call_llm as diag_call_llm
from app.services.charging.mode_balanced import BalancedStrategy
from app.services.charging.strategy_base import ChargingContext
from app.services.charging_queue_service import compute_sort_score
from app.services.device_data_service import DeviceDataService
from app.services.ml_model_service import MLModelService
from app.services.vpp.dispatch_optimizer import (
    MultiStationCoordinator,
    ResourceCapability,
    ResourceType,
)


# ─── 公共 fixture / 工厂 ───

@pytest.fixture
def balanced():
    return BalancedStrategy()


def _ctx(**kw):
    """最小可用 ChargingContext, 默认额定 120kW / 需求 60kW。"""
    defaults = dict(station_id="s1", charger_id="c1", rated_power_kw=120, demand_power_kw=60)
    defaults.update(kw)
    return ChargingContext(**defaults)


def _model_config():
    """一份完整的最小 model_config (ai_chat / ai_diagnosis 共用)。"""
    return {
        "base_url": "https://api.example.com/v1/",
        "api_key": "sk-test",
        "model_id": "test-model",
        "name": "TestProvider",
        "max_tokens": 4096,
    }


def _json_resp(payload):
    """构造一个 mock HTTP 响应: raise_for_status 空操作, .json() 返回 payload。"""
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = payload
    return resp


# ═══════════════════════════════════════════════════════════════════
# Guard 1 — device_data_service.get_statistics L218 `if not values:`
# ═══════════════════════════════════════════════════════════════════

class TestDeviceDataStatisticsEmptyMetric:
    def test_history_without_metric_returns_error_not_zerodivision(self):
        """history_data 非空(过 L208 `if not history_data`) 但无任何记录含该指标
        -> values=[] -> L218 guard 返回 error dict, 而非 L223 `sum([])/len([])` 除零。"""
        svc = DeviceDataService(db=None)
        svc.get_history_data = lambda device_id, hours=24: [
            {"timestamp": None, "data": {"voltage": 220.0}, "device_id": device_id},
            {"timestamp": None, "data": {"current": 10.0}, "device_id": device_id},
        ]
        result = svc.get_statistics(device_id=1, metric="power", aggregation="avg")
        assert result == {"error": "无指标数据: power"}


# ═══════════════════════════════════════════════════════════════════
# Guard 2 — ml_model_service.extract_features L202 `if len(alarm_data) > 0:`
# ═══════════════════════════════════════════════════════════════════

class TestMlExtractFeaturesEmptyAlarm:
    def test_all_nan_alarm_word_skips_frequency_not_zerodivision(self):
        """bms_alarm_word 全 NaN -> dropna 后 alarm_data 为空 -> L202 guard 跳过
        L204 `alarm_counts / len(alarm_data)` (否则 0/0 除零)。"""
        svc = MLModelService()
        df = svc.extract_features([{"bms_alarm_word": None, "battery_soc": 50}])
        # 干净返回 (battery_soc 特征仍在), 且未计算 alarm_frequency
        assert not df.empty
        assert "alarm_frequency" not in df.columns


# ═══════════════════════════════════════════════════════════════════
# Guard 3 — ml_model_service.train_anomaly_detector L402 `if len(X) < 20:`
# ═══════════════════════════════════════════════════════════════════

class TestMlAnomalyDetectorInsufficientFeatures:
    def test_too_few_valid_features_returns_error_not_zerodivision(self, tmp_path):
        """>=100 样本(过 L386 `< 100` guard) 但每条都无识别字段 -> extract_features 全空
        -> X_list=[] -> len(X)=0 <20 -> L402 guard 返回 error dict,
        而非继续到 L425 `anomaly_count / len(train_pred)` (空数组除零/fit 崩溃)。"""
        svc = MLModelService(model_dir=str(tmp_path))
        telemetry = [{"unknown_key": i} for i in range(120)]
        result = svc.train_anomaly_detector(device_id=1, telemetry_data=telemetry)
        assert result["status"] == "error"
        assert "有效特征太少" in result["error"]
        assert result["samples"] == 0


# ═══════════════════════════════════════════════════════════════════
# Guard 4 — vpp.dispatch_optimizer.get_aggregate_capacity L881 `if battery_resources:`
# ═══════════════════════════════════════════════════════════════════

class TestVppAggregateCapacityNoBatterySoc:
    def test_battery_soc_all_none_returns_zero_avg_not_zerodivision(self):
        """注册一个 soc=None 的 battery 资源 -> 被 `r.soc is not None` 过滤 ->
        battery_resources=[] -> L881 guard 跳过 L882 `sum(...)/len([])` (否则除零),
        avg_soc 保持 0。"""
        coord = MultiStationCoordinator()
        coord.register_resource(ResourceCapability(
            resource_id="BAT-1",
            resource_type=ResourceType.BATTERY,
            station_id="ST-1",
            rated_power_kw=100,
            current_power_kw=0,
            available_power_kw=100,
            soc=None,  # 关键: 被过滤, battery_resources 为空
        ))
        result = coord.get_aggregate_capacity()
        assert result["avg_battery_soc"] == 0
        assert result["online_stations"] == 0


# ═══════════════════════════════════════════════════════════════════
# Guard 5 — charging.mode_balanced.evaluate L57 `if total > ctx.rated_power_kw > 0:`
# ═══════════════════════════════════════════════════════════════════

class TestBalancedRatedPowerGuard:
    def test_zero_total_no_zerodivision(self, balanced):
        """无需求 + 无源 -> total=0 -> L57 `total > rated > 0` 为 False -> 跳过
        L58 `scale = rated_power_kw / total` (否则 rated/0 除零)。"""
        ctx = _ctx(rated_power_kw=5, demand_power_kw=0, pv_output_kw=0)
        decision = balanced.evaluate(ctx)
        assert decision.target_power_kw == 0.0

    def test_zero_rated_skips_clamp_no_zerodivision(self, balanced):
        """rated_power_kw=0 -> `> 0` 为 False -> 不进入钳位分支,
        光伏全额消纳 (若丢掉 `> 0` 改成 `total > rated`, 则 scale=0/total 把各源清零)。"""
        ctx = _ctx(rated_power_kw=0, demand_power_kw=10, pv_output_kw=10)
        decision = balanced.evaluate(ctx)
        assert decision.pv_power_kw == 10.0
        assert decision.target_power_kw == 10.0


# ═══════════════════════════════════════════════════════════════════
# Guard 6 — charging_queue_service.compute_sort_score L93 `sum(...) or 1.0`
# ═══════════════════════════════════════════════════════════════════

class TestComputeSortScoreZeroWeight:
    def test_zero_total_weight_falls_back_to_one_not_zerodivision(self):
        """直接传 weight=0 的 criteria (绕过 _parse_criteria 的 weight>0 过滤)
        -> sum(weights)=0 -> L93 `or 1.0` 兜底为 1.0, 避免 L103 `(raw*weight)/0` 除零。"""
        entry = SimpleNamespace(
            priority=1, arrival_time=None,
            required_energy_kwh=10, target_soc=0.8, current_soc=0.2,
        )
        criteria = [{"field": "priority", "weight": 0, "direction": "asc"}]
        score = compute_sort_score(entry, criteria)
        assert isinstance(score, float)
        # weight=0 -> 贡献 0; total_weight 兜底 1.0 -> 综合 0.0
        assert score == 0.0


# ═══════════════════════════════════════════════════════════════════
# Guard 7 — ai_chat._call_llm L203 `if "choices" in data and len(data["choices"]) > 0:`
# ═══════════════════════════════════════════════════════════════════

class TestAiChatCallLlmEmptyChoices:
    def test_empty_choices_raises_value_error_not_index_error(self, monkeypatch):
        """choices=[] -> L203 guard 不取 [0], 转 L217 raise ValueError,
        而非 L204 `data["choices"][0]["message"]["content"]` 抛 IndexError。"""
        import app.services.ai_chat as mod

        # base_url 安全校验已由 url_safety 套件覆盖, 此处精确放行以触达 LLM 响应分支
        monkeypatch.setattr(mod, "validate_external_url", lambda url: url)
        monkeypatch.setattr(mod.model_manager, "get_model_for_task", lambda task: _model_config())
        monkeypatch.setattr(mod.requests, "post", lambda *a, **k: _json_resp({"choices": []}))

        with pytest.raises(ValueError, match="LLM返回异常"):
            chat_call_llm(messages=[{"role": "user", "content": "hi"}])


# ═══════════════════════════════════════════════════════════════════
# Guard 8 — ai_chat._build_context_prompt L239 `if context.get("alarms") and len(...) > 0:`
# ═══════════════════════════════════════════════════════════════════

class TestAiChatBuildContextPromptEmptyAlarms:
    def test_empty_alarms_does_not_index(self):
        """alarms=[] -> `context.get("alarms")` 为假 -> L239 guard 跳过
        L241 `alarms[0]` (否则 IndexError)。"""
        out = _build_context_prompt({"alarms": []})
        assert isinstance(out, str)
        assert "当前告警" not in out  # 空告警不应进入上下文提示


# ═══════════════════════════════════════════════════════════════════
# Guard 9 — ai_diagnosis._call_llm L117 `if "choices" in data and len(data["choices"]) > 0:`
# ═══════════════════════════════════════════════════════════════════

class TestAiDiagnosisCallLlmEmptyChoices:
    def test_empty_choices_raises_clean_exception_not_index_error(self, monkeypatch):
        """choices=[] -> L117 guard 不取 [0], 转 L120 raise Exception,
        而非 L118 `data["choices"][0]["message"]["content"]` 抛 IndexError。

        注: ai_diagnosis._call_llm 函数体内 `import requests`, 引用的是全局
        requests 模块对象, 故直接 patch 其 post 属性。"""
        import requests as _req

        import app.services.ai_diagnosis as _diag_mod
        # base_url 安全校验已由 url_safety 套件覆盖, 此处精确放行以触达 LLM 响应分支
        monkeypatch.setattr(_diag_mod, "validate_external_url", lambda url: url)
        monkeypatch.setattr(_req, "post", lambda *a, **k: _json_resp({"choices": []}))

        with pytest.raises(Exception, match="LLM返回异常"):
            diag_call_llm(
                model_config=_model_config(),
                system_prompt="s",
                user_prompt="u",
            )
