"""LSTMPredictor 单元测试 — LSTM 故障预测模型 (Phase10)

torch 未安装时自动走轻量 numpy 路径; pytorch 路径用 MagicMock 隔离。
覆盖:
- PredictionResult / TrainingConfig 数据结构
- DataPreprocessor (fit/transform/create_sequences/save_stats/load_stats/故障标签)
- LSTMPredictor (init/train 轻量/predict/save/load + 内部辅助: 风险/趋势/异常/RUL/指标/建议)
- PredictiveMaintenanceService (async: 缓存/训练/自动训练/批量/状态)
- format_prediction_for_display
"""
import sys
import types

import numpy as np
import pytest

from app.services.predictive_maintenance.lstm_predictor import (
    DataPreprocessor,
    LSTMPredictor,
    PredictionResult,
    PredictiveMaintenanceService,
    TrainingConfig,
    format_prediction_for_display,
)

try:
    import torch  # noqa: F401
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False


def _small_config(**kw):
    """快速训练用的小配置, 默认 2 特征 + 短序列。"""
    base = dict(
        sequence_length=4, prediction_horizon=1, epochs=1, lstm_units=8,
        feature_columns=["battery_soc", "battery_soh"],
    )
    base.update(kw)
    return TrainingConfig(**base)


def _train_data(n=20):
    return [{"battery_soc": 50 + i, "battery_soh": 90 - i} for i in range(n)]


# ─── 数据结构 ───

class TestTrainingConfig:
    def test_defaults(self):
        cfg = TrainingConfig()
        assert cfg.sequence_length == 24
        assert cfg.prediction_horizon == 6
        assert cfg.lstm_units == 64
        assert cfg.lstm_layers == 2
        assert cfg.dropout_rate == 0.2
        assert cfg.learning_rate == 0.001
        assert cfg.epochs == 50
        assert len(cfg.feature_columns) == 15

    def test_default_feature_columns_populated(self):
        # __post_init__: feature_columns=None → 填充默认 15 列
        assert "battery_soc" in TrainingConfig().feature_columns
        assert "bms_alarm_word" in TrainingConfig().feature_columns

    def test_custom_feature_columns_preserved(self):
        cfg = TrainingConfig(feature_columns=["a", "b"])
        assert cfg.feature_columns == ["a", "b"]


class TestPredictionResult:
    def test_construction(self):
        r = PredictionResult(
            device_id=1, device_name="d", prediction_time="t",
            failure_probability=0.5, health_trend="stable", rul_hours=100.0,
            risk_level="medium", anomaly_score=0.3, key_indicators=[],
            recommended_actions=[], confidence=0.8,
        )
        assert r.device_id == 1
        assert r.failure_probability == 0.5
        assert r.rul_hours == 100.0
        assert r.risk_level == "medium"


# ─── DataPreprocessor ───

class TestDataPreprocessor:
    def test_fit_stats(self):
        pre = DataPreprocessor(TrainingConfig(feature_columns=["battery_soc"]))
        pre.fit([{"battery_soc": 80}, {"battery_soc": 60}])
        stats = pre.feature_stats["battery_soc"]
        assert stats["mean"] == 70.0
        assert stats["std"] == 10.0  # np.std ddof=0
        assert stats["min"] == 60.0
        assert stats["max"] == 80.0

    def test_fit_single_value_uses_defaults(self):
        # 单值 (len<=1) → 占位统计 {mean:0, std:1, min:0, max:1}
        pre = DataPreprocessor(TrainingConfig(feature_columns=["x"]))
        pre.fit([{"x": 5}])
        assert pre.feature_stats["x"] == {"mean": 0, "std": 1.0, "min": 0, "max": 1}

    def test_transform_normalization(self):
        pre = DataPreprocessor(TrainingConfig(feature_columns=["battery_soc"]))
        pre.fit([{"battery_soc": 80}, {"battery_soc": 60}])  # mean70 std10
        out = pre.transform([{"battery_soc": 80}])
        assert out.shape == (1, 1)
        assert out[0][0] == pytest.approx(1.0)  # (80-70)/10

    def test_transform_missing_value_becomes_zero(self):
        pre = DataPreprocessor(TrainingConfig(feature_columns=["a", "b"]))
        pre.fit([{"a": 10, "b": 20}, {"a": 30, "b": 40}])  # a: mean20 std10
        out = pre.transform([{"a": 10}])  # b 缺失
        assert out[0][0] == pytest.approx(-1.0)  # (10-20)/10
        assert out[0][1] == 0.0  # 缺失 → 0

    def test_transform_clips_to_five(self):
        pre = DataPreprocessor(TrainingConfig(feature_columns=["x"]))
        pre.fit([{"x": 0}, {"x": 0}])  # mean0, std0→1
        out = pre.transform([{"x": 100}])  # 100 → clip 5
        assert out[0][0] == 5.0

    def test_create_sequences_shape(self):
        cfg = TrainingConfig(sequence_length=3, prediction_horizon=1, feature_columns=["x"])
        pre = DataPreprocessor(cfg)
        data = np.arange(10).reshape(10, 1).astype(np.float32)
        X, y = pre.create_sequences(data)
        assert X.shape == (6, 3, 1)  # len - seq - horizon = 10-3-1
        assert y.shape == (6,)

    def test_create_sequences_too_short_returns_empty(self):
        cfg = TrainingConfig(sequence_length=3, prediction_horizon=1, feature_columns=["x"])
        pre = DataPreprocessor(cfg)
        data = np.arange(3).reshape(3, 1).astype(np.float32)
        X, y = pre.create_sequences(data)
        assert len(X) == 0  # range(3-3-1)=range(-1) 空

    def test_compute_fault_label_normal(self):
        pre = DataPreprocessor(TrainingConfig())
        window = np.zeros((2, 3), dtype=np.float32)
        assert pre._compute_fault_label(window) == 0.0

    def test_compute_fault_label_anomaly_saturates(self):
        pre = DataPreprocessor(TrainingConfig())
        window = np.full((2, 1), 4.0, dtype=np.float32)  # 全超 3σ
        # 2 anomalies / (2 checks * 0.1) = 10 → min(1, 10) = 1.0
        assert pre._compute_fault_label(window) == 1.0

    def test_save_load_stats_roundtrip(self, tmp_path):
        pre = DataPreprocessor(TrainingConfig(feature_columns=["x"]))
        pre.fit([{"x": 10}, {"x": 20}])
        path = str(tmp_path / "stats.json")
        pre.save_stats(path)
        pre2 = DataPreprocessor(TrainingConfig(feature_columns=["x"]))
        pre2.load_stats(path)
        assert pre2.feature_stats == pre.feature_stats


# ─── LSTMPredictor 基础 ───

class TestPredictorBasics:
    def test_init_defaults(self):
        p = LSTMPredictor(TrainingConfig())
        assert p.use_pytorch is False
        assert p.trained is False
        assert p.model is None
        assert p._weights is None
        assert p.training_history == []
        assert isinstance(p.preprocessor, DataPreprocessor)

    def test_try_import_pytorch_false_without_torch(self):
        if HAS_TORCH:
            pytest.skip("torch 已安装, 跳过无 torch 分支")
        p = LSTMPredictor(TrainingConfig())
        assert p._try_import_pytorch() is False
        assert p.use_pytorch is False

    def test_try_import_pytorch_true_with_mock(self, monkeypatch):
        # 用真实 ModuleType 构造可导入的 fake torch 包 (含 __path__ + nn 子模块)
        fake_torch = types.ModuleType("torch")
        fake_torch.__path__ = []  # 标记为 package, 否则 `import torch.nn` 失败
        fake_nn = types.ModuleType("torch.nn")
        fake_torch.nn = fake_nn
        monkeypatch.setitem(sys.modules, "torch", fake_torch)
        monkeypatch.setitem(sys.modules, "torch.nn", fake_nn)

        p = LSTMPredictor(TrainingConfig())
        assert p._try_import_pytorch() is True
        assert p.use_pytorch is True
        assert p.torch is fake_torch
        assert p.nn is fake_nn

    def test_sigmoid(self):
        p = LSTMPredictor(TrainingConfig())
        assert p._sigmoid(0.0) == 0.5
        assert p._sigmoid(1000.0) == pytest.approx(1.0)  # clip 500
        assert p._sigmoid(-1000.0) == pytest.approx(0.0)

    def test_build_lightweight_model_weights_shape(self):
        p = LSTMPredictor(TrainingConfig(lstm_units=8, feature_columns=["a", "b", "c"]))
        p._build_lightweight_model(3)
        assert p._weights["Wi"].shape == (3, 8)
        assert p._weights["W_out"].shape == (8, 1)
        assert np.all(p._weights["bi"] == 0)   # input gate bias 初始 0
        assert np.all(p._weights["bf"] == 1)   # forget gate bias 初始 1

    def test_generate_synthetic_data_shape(self):
        cfg = TrainingConfig(sequence_length=4, feature_columns=["a", "b"])
        p = LSTMPredictor(cfg)
        X, y = p._generate_synthetic_data()
        assert X.shape == (500, 4, 2)
        assert y.shape == (500,)


# ─── 训练 / 预测 ───

class TestTrainAndPredict:
    def test_train_lightweight_path(self):
        p = LSTMPredictor(_small_config())
        result = p.train(_train_data(20))
        assert result["status"] == "success"
        assert result["framework"] == "lightweight_numpy"
        assert result["epochs"] == 1
        assert result["samples"] == 15  # 20-4-1
        assert p.trained is True
        assert p._weights is not None
        assert len(p.training_history) == 1

    def test_train_synthetic_when_insufficient(self):
        # 数据太少无法生成序列 → 合成 500 样本
        cfg = TrainingConfig(sequence_length=24, prediction_horizon=6, epochs=1,
                             feature_columns=["battery_soc"])
        p = LSTMPredictor(cfg)
        result = p.train([{"battery_soc": 50 + i} for i in range(5)])
        assert result["samples"] == 500

    def test_predict_not_trained_raises(self):
        p = LSTMPredictor(TrainingConfig(feature_columns=["a"]))
        with pytest.raises(RuntimeError, match="not trained"):
            p.predict([{"a": 1}], device_id=1)

    def test_predict_returns_result(self):
        p = LSTMPredictor(_small_config())
        p.train(_train_data(20))
        recent = [{"battery_soc": 55 + i, "battery_soh": 88 - i} for i in range(6)]
        result = p.predict(recent, device_id=7, device_name="桩A")
        assert isinstance(result, PredictionResult)
        assert result.device_id == 7
        assert result.device_name == "桩A"
        assert 0.0 <= result.failure_probability <= 1.0
        assert result.risk_level in ("low", "medium", "high", "critical")
        assert result.health_trend in ("improving", "stable", "degrading", "critical")
        assert 0.0 <= result.anomaly_score <= 1.0
        assert 0.0 <= result.confidence <= 0.95

    def test_predict_pads_short_data(self):
        # recent 行数 < sequence_length → 前端补零后仍可预测
        p = LSTMPredictor(_small_config())
        p.train(_train_data(20))
        recent = [{"battery_soc": 55, "battery_soh": 88},
                  {"battery_soc": 56, "battery_soh": 87}]
        result = p.predict(recent, device_id=1)
        assert isinstance(result, PredictionResult)

    def test_save_load_roundtrip(self, tmp_path):
        p = LSTMPredictor(_small_config())
        p.train(_train_data(20))
        path = str(tmp_path / "model")
        p.save(path)

        p2 = LSTMPredictor(_small_config())
        p2.load(path)
        assert p2.trained is True
        assert p2.use_pytorch is False
        assert p2._weights is not None
        assert p2.config.sequence_length == 4


# ─── 内部辅助指标 ───

class TestAuxiliaryMetrics:
    def test_compute_risk_level_thresholds(self):
        p = LSTMPredictor(TrainingConfig())
        assert p._compute_risk_level(1.0, 1.0) == "critical"  # combined 1.0 > 0.8
        assert p._compute_risk_level(1.0, 0.0) == "high"      # 0.7 > 0.5
        assert p._compute_risk_level(0.5, 0.5) == "medium"    # 0.5, 严格 > 不成立 → medium
        assert p._compute_risk_level(0.0, 0.0) == "low"       # 0

    def test_compute_anomaly_score_zero(self):
        p = LSTMPredictor(TrainingConfig(feature_columns=["a", "b"]))
        assert p._compute_anomaly_score(np.zeros((4, 2), dtype=np.float32)) == 0.0

    def test_compute_anomaly_score_saturates(self):
        p = LSTMPredictor(TrainingConfig(feature_columns=["a"]))
        data = np.full((4, 1), 3.0, dtype=np.float32)  # 全 > 2.5
        assert p._compute_anomaly_score(data) == 1.0

    def test_health_trend_stable(self):
        p = LSTMPredictor(TrainingConfig(feature_columns=["a"]))
        assert p._compute_health_trend(np.zeros((8, 1), dtype=np.float32)) == "stable"

    def test_health_trend_critical(self):
        p = LSTMPredictor(TrainingConfig(feature_columns=["a"]))
        data = np.zeros((8, 1), dtype=np.float32)
        data[4:] = 3.0  # 后半全异常 → second_anomaly=1.0 > 0.3
        assert p._compute_health_trend(data) == "critical"

    def test_health_trend_degrading(self):
        p = LSTMPredictor(TrainingConfig(feature_columns=["a"]))
        data = np.zeros((8, 1), dtype=np.float32)
        data[4] = 3.0  # 后半 1/4=0.25 异常 (不>0.3), 但 > first(0)*1.5
        assert p._compute_health_trend(data) == "degrading"

    def test_health_trend_improving(self):
        p = LSTMPredictor(TrainingConfig(feature_columns=["a"]))
        data = np.zeros((8, 1), dtype=np.float32)
        data[0] = 3.0  # 前半 0.25 异常, 后半干净 → first > second*1.5
        assert p._compute_health_trend(data) == "improving"

    def test_health_trend_short_data_stable(self):
        # len < 4 → 直接 stable
        p = LSTMPredictor(TrainingConfig(feature_columns=["a"]))
        assert p._compute_health_trend(np.full((3, 1), 3.0, dtype=np.float32)) == "stable"

    def test_estimate_rul_empty_data_none(self):
        p = LSTMPredictor(TrainingConfig())
        assert p._estimate_rul(0.5, []) is None

    def test_estimate_rul_low_soh(self):
        # soh < 20 → soh * 10
        p = LSTMPredictor(TrainingConfig())
        assert p._estimate_rul(0.5, [{"battery_soh": 10}]) == 100.0

    def test_estimate_rul_normal(self):
        # base = soh*100, *(1 - failure_prob)
        p = LSTMPredictor(TrainingConfig())
        assert p._estimate_rul(0.2, [{"battery_soh": 80}]) == 6400.0  # 8000*0.8

    def test_estimate_rul_default_soh(self):
        # latest 无 soh → 默认 90
        p = LSTMPredictor(TrainingConfig())
        assert p._estimate_rul(0.0, [{}]) == 9000.0  # 90*100*(1-0)

    def test_extract_key_indicators_status(self):
        p = LSTMPredictor(TrainingConfig())
        indicators = p._extract_key_indicators(
            {"battery_soc": 50, "battery_soh": 80, "battery_voltage": 400}
        )
        by_key = {i["key"]: i for i in indicators}
        assert by_key["battery_soc"]["status"] == "normal"
        assert by_key["battery_soh"]["status"] == "normal"
        assert by_key["battery_voltage"]["status"] == "normal"  # thresholds None → normal
        assert by_key["battery_voltage"]["unit"] == "V"

    def test_extract_key_indicators_critical_soc(self):
        p = LSTMPredictor(TrainingConfig())
        indicators = p._extract_key_indicators({"battery_soc": 10})  # < 20 → critical
        assert indicators[0]["status"] == "critical"

    def test_extract_key_indicators_warning_soc(self):
        p = LSTMPredictor(TrainingConfig())
        indicators = p._extract_key_indicators({"battery_soc": 30})  # < 40 → warning
        assert indicators[0]["status"] == "warning"

    def test_generate_recommendations_critical(self):
        p = LSTMPredictor(TrainingConfig())
        recs = p._generate_recommendations("critical", 0.9, [])
        assert any("紧急" in r for r in recs)

    def test_generate_recommendations_low(self):
        p = LSTMPredictor(TrainingConfig())
        recs = p._generate_recommendations("low", 0.1, [])
        assert any("正常" in r for r in recs)

    def test_generate_recommendations_indicator_based(self):
        p = LSTMPredictor(TrainingConfig())
        indicator = {"name": "电池温度", "status": "critical", "value": 50, "unit": "℃"}
        recs = p._generate_recommendations("low", 0.1, [indicator])
        assert any("散热" in r for r in recs)


# ─── PredictiveMaintenanceService (async) ───

class TestPredictiveMaintenanceService:
    def test_get_or_create_predictor_caches(self, tmp_path):
        svc = PredictiveMaintenanceService(model_dir=str(tmp_path / "m"))
        svc.default_config = _small_config()
        p1 = svc.get_or_create_predictor(1)
        p2 = svc.get_or_create_predictor(1)
        assert p1 is p2  # 同 device_id 返回缓存实例

    async def test_train_device_model(self, tmp_path):
        svc = PredictiveMaintenanceService(model_dir=str(tmp_path / "m"))
        svc.default_config = _small_config()
        result = await svc.train_device_model(1, _train_data(20))
        assert result["status"] == "success"
        assert (tmp_path / "m" / "1").exists()  # 模型已落盘

    async def test_predict_failure_auto_trains(self, tmp_path):
        # 模型未训练 → 自动训练后预测
        svc = PredictiveMaintenanceService(model_dir=str(tmp_path / "m"))
        svc.default_config = _small_config()
        result = await svc.predict_failure(1, _train_data(20), device_name="桩A")
        assert isinstance(result, PredictionResult)
        assert result.device_name == "桩A"

    async def test_batch_predict_multiple(self, tmp_path):
        svc = PredictiveMaintenanceService(model_dir=str(tmp_path / "m"))
        svc.default_config = _small_config()
        data = _train_data(20)
        results = await svc.batch_predict([
            {"device_id": 1, "recent_data": data, "device_name": "a"},
            {"device_id": 2, "recent_data": data, "device_name": "b"},
        ])
        assert len(results) == 2
        assert {r.device_id for r in results} == {1, 2}

    async def test_batch_predict_swallows_failure(self, tmp_path, monkeypatch):
        # 单设备预测抛错 → try/except 吞掉, 其余正常返回
        svc = PredictiveMaintenanceService(model_dir=str(tmp_path / "m"))
        good = PredictionResult(
            device_id=1, device_name="d1", prediction_time="t", failure_probability=0.1,
            health_trend="stable", rul_hours=100.0, risk_level="low",
            anomaly_score=0.1, key_indicators=[], recommended_actions=[], confidence=0.9,
        )

        async def fake_predict(device_id, recent_data, device_name=""):
            if device_id == 2:
                raise RuntimeError("boom")
            return good

        monkeypatch.setattr(svc, "predict_failure", fake_predict)
        results = await svc.batch_predict([{"device_id": 1}, {"device_id": 2}])
        assert len(results) == 1
        assert results[0].device_id == 1

    def test_get_model_status(self, tmp_path):
        svc = PredictiveMaintenanceService(model_dir=str(tmp_path / "m"))
        svc.default_config = _small_config()
        p = svc.get_or_create_predictor(1)
        p.train(_train_data(20))
        status = svc.get_model_status()
        assert "1" in status
        assert status["1"]["trained"] is True
        assert status["1"]["framework"] == "numpy"


# ─── 格式化 ───

class TestFormatPrediction:
    def test_display_fields(self):
        r = PredictionResult(
            device_id=1, device_name="桩A", prediction_time="2026",
            failure_probability=0.25, health_trend="degrading", rul_hours=120.0,
            risk_level="medium", anomaly_score=0.2, key_indicators=[],
            recommended_actions=[], confidence=0.8,
        )
        d = format_prediction_for_display(r)
        assert d["device_id"] == 1
        assert d["failure_probability_display"] == "25.0%"
        assert d["risk_emoji"] == "🟡"
        assert d["trend_emoji"] == "📉"
        assert d["rul_display"] == "120h"

    def test_display_rul_na(self):
        r = PredictionResult(
            device_id=1, device_name="", prediction_time="t",
            failure_probability=0.1, health_trend="stable", rul_hours=None,
            risk_level="low", anomaly_score=0.1, key_indicators=[],
            recommended_actions=[], confidence=0.6,
        )
        assert format_prediction_for_display(r)["rul_display"] == "N/A"
