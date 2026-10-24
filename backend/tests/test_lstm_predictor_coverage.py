"""lstm_predictor.py 行为覆盖测试

目标: 把 app/services/predictive_maintenance/lstm_predictor.py 覆盖率从 19% 提到 ≥70%。
环境无 torch, 因此仅覆盖 lightweight(numpy) 路径 + 全部辅助方法 + Service + 工具函数;
pytorch 专属分支 (_build_pytorch_model / _train_pytorch / predict·save·load 的 torch 分支)
在无 torch 环境下天然不可达, 不在本文件覆盖范围内。

所有断言针对真实行为, 不弱化。
"""
import json
import sys
from unittest import mock

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


# ============ 公共 fixtures / helpers ============

FEATURE_COLS = ["battery_soc", "battery_soh", "battery_temperature", "battery_voltage"]


def _small_config(**overrides) -> TrainingConfig:
    """小参数 config, 加速训练/推理; epochs=12 覆盖 epoch%5==0 与 (epoch+1)%10==0 两个 log 分支。"""
    base = dict(
        sequence_length=6,
        prediction_horizon=2,
        lstm_units=8,
        lstm_layers=1,
        dropout_rate=0.1,
        learning_rate=0.01,
        batch_size=4,
        epochs=12,
        feature_columns=list(FEATURE_COLS),
    )
    base.update(overrides)
    return TrainingConfig(**base)


def _make_rows(n: int, cols=None):
    """构造 n 行遥测 dict, 每列值互不相同(保证 fit 时 std>0)。"""
    cols = cols or FEATURE_COLS
    rows = []
    for i in range(n):
        rows.append({c: float(i * 3 + j) for j, c in enumerate(cols)})
    return rows


# ============ TrainingConfig ============


class TestTrainingConfig:
    def test_default_feature_columns_via_post_init(self):
        """feature_columns=None 时 __post_init__ 填充默认 15 列。"""
        cfg = TrainingConfig()
        assert cfg.feature_columns is not None
        assert len(cfg.feature_columns) == 15
        assert "battery_soc" in cfg.feature_columns
        assert "system_status" in cfg.feature_columns

    def test_explicit_feature_columns_kept(self):
        cfg = TrainingConfig(feature_columns=["a", "b"])
        assert cfg.feature_columns == ["a", "b"]

    def test_defaults(self):
        cfg = TrainingConfig()
        assert cfg.sequence_length == 24
        assert cfg.lstm_units == 64
        assert cfg.epochs == 50


# ============ DataPreprocessor ============


class TestDataPreprocessor:
    def test_fit_multivalue_singlevalue_and_missing_columns(self):
        """覆盖 fit 三条分支: 多值(std>0) / std==0→1.0 / 单值 else / 全None 不入 stats。"""
        cfg = TrainingConfig(feature_columns=["a", "b", "c", "d"])
        prep = DataPreprocessor(cfg)
        data = [
            {"a": 1.0, "b": 5.0, "c": None, "d": None},
            {"a": 3.0, "b": 5.0, "c": 7.0, "d": None},
            {"a": 5.0, "b": 5.0, "c": None, "d": None},
        ]
        prep.fit(data)

        # 'a' 多个不同值 → mean/std/min/max, std>0
        assert "a" in prep.feature_stats
        assert prep.feature_stats["a"]["std"] > 0
        assert prep.feature_stats["a"]["mean"] == pytest.approx(3.0)

        # 'b' 全相同 → std==0 走 1.0 分支
        assert prep.feature_stats["b"]["std"] == 1.0

        # 'c' 仅 1 个非 None → else 默认
        assert prep.feature_stats["c"] == {"mean": 0, "std": 1.0, "min": 0, "max": 1}

        # 'd' 全 None → 不进 stats
        assert "d" not in prep.feature_stats

    def test_transform_none_normalize_default_stats_and_clip(self):
        """覆盖 transform: val=None→0.0 / 归一化 / col 不在 stats 用默认 / clip(-5,5)。"""
        cfg = TrainingConfig(feature_columns=["a", "b", "c", "d"])
        prep = DataPreprocessor(cfg)
        # fit: a 多值, b 常量, c 仅1个, d 全 None(不入 stats)
        prep.fit([
            {"a": 1.0, "b": 5.0, "c": None, "d": None},
            {"a": 3.0, "b": 5.0, "c": 7.0, "d": None},
            {"a": 5.0, "b": 5.0, "c": None, "d": None},
        ])
        # transform: d 此处给非 None 值, 触发 stats.get(col, default) 默认分支
        out = prep.transform([{"a": 3.0, "b": 5.0, "c": 7.0, "d": 9.0}])
        assert out.shape == (1, 4)
        # a: (3-3)/std = 0
        assert out[0, 0] == pytest.approx(0.0, abs=1e-5)
        # b: (5-5)/1.0 = 0
        assert out[0, 1] == pytest.approx(0.0)
        # c: 默认 stats {mean:0,std:1} → (7-0)/1 = 7 → clip 到 5
        assert out[0, 2] == 5.0
        # d: 不在 stats → 默认 {mean:0,std:1} → (9-0)/1 = 9 → clip 到 5
        assert out[0, 3] == 5.0

    def test_transform_dtype_is_float32(self):
        cfg = TrainingConfig(feature_columns=["a"])
        prep = DataPreprocessor(cfg)
        prep.fit([{"a": 1.0}, {"a": 2.0}])
        out = prep.transform([{"a": 1.5}])
        assert out.dtype == np.float32

    def test_create_sequences_shapes(self):
        """覆盖 create_sequences 主循环 + _compute_fault_label(有异常)。"""
        cfg = TrainingConfig(sequence_length=3, prediction_horizon=1, feature_columns=["a", "b"])
        prep = DataPreprocessor(cfg)
        data = np.arange(1, 13, dtype=np.float32).reshape(6, 2)  # 6 行
        X, y = prep.create_sequences(data)
        # range(6 - 3 - 1) = 2 个序列
        assert X.shape == (2, 3, 2)
        assert y.shape == (2,)

    def test_create_sequences_empty_when_data_too_short(self):
        cfg = TrainingConfig(sequence_length=10, prediction_horizon=2, feature_columns=["a"])
        prep = DataPreprocessor(cfg)
        X, y = prep.create_sequences(np.zeros((3, 1), dtype=np.float32))
        assert X.shape[0] == 0
        assert y.shape[0] == 0

    def test_compute_fault_label_empty_window(self):
        """total_checks==0 → 0.0。"""
        cfg = TrainingConfig(feature_columns=["a"])
        prep = DataPreprocessor(cfg)
        label = prep._compute_fault_label(np.array([], dtype=np.float32).reshape(0, 2))
        assert label == 0.0

    def test_compute_fault_label_clipped_to_one(self):
        """异常占比高 → min(1.0, ...) 截断到 1.0。"""
        cfg = TrainingConfig(feature_columns=["a", "b"])
        prep = DataPreprocessor(cfg)
        # 1 个异常 / 4 总 → 1/(4*0.1)=2.5 → min=1.0
        window = np.array([[4.0, 0.0], [0.0, 0.0]], dtype=np.float32)
        assert prep._compute_fault_label(window) == 1.0

    def test_compute_fault_label_partial(self):
        cfg = TrainingConfig(feature_columns=["a", "b"])
        prep = DataPreprocessor(cfg)
        window = np.zeros((10, 2), dtype=np.float32)
        window[0, 0] = 3.5  # 1 异常 / 20 总 → 1/(20*0.1)=0.5
        assert prep._compute_fault_label(window) == pytest.approx(0.5)

    def test_save_and_load_stats_roundtrip(self, tmp_path):
        cfg = TrainingConfig(feature_columns=["a"])
        prep = DataPreprocessor(cfg)
        prep.fit([{"a": 1.0}, {"a": 3.0}, {"a": 5.0}])
        path = tmp_path / "stats.json"
        prep.save_stats(str(path))
        assert path.exists()

        prep2 = DataPreprocessor(cfg)
        prep2.load_stats(str(path))
        assert prep2.feature_stats == prep.feature_stats

    def test_normalize_features_std_zero(self):
        """feature_stats 中某列 std=0 (例如 load_stats 读到脏数据) 时 transform 不触发 ZeroDivisionError。

        fit() 在 std==0 时已存 1.0 做了保护, 这里绕过 fit 直接注入 std=0 的 stats,
        覆盖 transform 内 (val-mean)/stats['std'] 这一行。
        """
        cfg = TrainingConfig(feature_columns=["a"])
        prep = DataPreprocessor(cfg)
        prep.feature_stats = {"a": {"mean": 5.0, "std": 0, "min": 5, "max": 5}}
        # 修复前: (5.0-5.0)/0 → ZeroDivisionError; 修复后 std or 1.0 → 1.0 → 0.0
        out = prep.transform([{"a": 5.0}])
        assert out.shape == (1, 1)
        assert out[0, 0] == pytest.approx(0.0)


# ============ LSTMPredictor 核心 / 数学 ============


class TestLSTMPredictorMath:
    def test_try_import_pytorch_returns_false_without_torch(self):
        """无 torch 环境 → ImportError 分支, use_pytorch=False。

        本机可能已装 PyTorch (torch 2.8.0), 用 patch.dict(sys.modules) 把 torch
        相关键置 None, 使 `import torch` 触发 ImportError, 真正覆盖无 torch 分支。
        """
        p = LSTMPredictor(_small_config())
        torch_modules = {
            key: None
            for key in list(sys.modules)
            if key == "torch" or key.startswith("torch.")
        }
        torch_modules.setdefault("torch", None)
        torch_modules.setdefault("torch.nn", None)
        with mock.patch.dict(sys.modules, torch_modules, clear=False):
            assert p._try_import_pytorch() is False
        assert p.use_pytorch is False

    def test_initial_state(self):
        p = LSTMPredictor(_small_config())
        assert p.model is None
        assert p._weights is None
        assert p.trained is False
        assert p.training_history == []
        assert isinstance(p.preprocessor, DataPreprocessor)

    def test_sigmoid_extremes_and_center(self):
        p = LSTMPredictor(_small_config())
        assert p._sigmoid(0.0) == pytest.approx(0.5)
        assert p._sigmoid(1000.0) > 0.99  # clip(-500,500) 防溢出
        assert p._sigmoid(-1000.0) < 0.01

    def test_build_lightweight_model_shapes(self):
        p = LSTMPredictor(_small_config())
        p._build_lightweight_model(input_size=len(FEATURE_COLS))
        assert p._weights is not None
        assert p._weights["Wi"].shape == (len(FEATURE_COLS), 8)
        # forget gate bias 初始化为 1
        assert np.all(p._weights["bf"] == 1.0)
        assert p._weights["W_out"].shape == (8, 1)

    def test_lstm_forward_output_shape_and_range(self):
        p = LSTMPredictor(_small_config())
        p._build_lightweight_model(input_size=len(FEATURE_COLS))
        X = np.random.randn(5, 6, len(FEATURE_COLS)).astype(np.float32)
        out = p._lstm_forward(X)
        assert out.shape == (5,)
        # sigmoid 输出 ∈ [0,1]
        assert np.all(out >= 0.0) and np.all(out <= 1.0)


# ============ 训练 ============


class TestTraining:
    def test_train_real_data_lightweight(self):
        """25 行 → 17 序列 ≥10 → 走真实数据 lightweight 训练。"""
        np.random.seed(42)
        p = LSTMPredictor(_small_config())
        result = p.train(_make_rows(25))

        assert result["status"] == "success"
        assert result["framework"] == "lightweight_numpy"
        assert result["epochs"] == 12
        assert result["samples"] > 0
        assert p.trained is True
        assert p._weights is not None
        assert p._weights["Wi"].shape == (len(FEATURE_COLS), 8)
        assert len(p.training_history) == 12
        assert {k for k in p.training_history[0]} == {"epoch", "loss"}
        # 损失是有限正数
        assert np.isfinite(result["final_loss"])

    def test_train_synthetic_when_insufficient_sequences(self):
        """序列数 <10 → 触发 _generate_synthetic_data(500 样本)。"""
        np.random.seed(1)
        p = LSTMPredictor(_small_config())
        result = p.train(_make_rows(3))  # 3-6-2 < 0 → 0 序列
        assert result["status"] == "success"
        assert result["samples"] == 500

    def test_generate_synthetic_data_shapes_and_labels(self):
        p = LSTMPredictor(_small_config())
        np.random.seed(7)
        X, y = p._generate_synthetic_data()
        assert X.shape == (500, 6, len(FEATURE_COLS))
        assert y.shape == (500,)
        assert set(np.unique(y)).issubset({0.0, 1.0})
        # 前 70% 正常(label=0), 后 30% 异常(label=1)
        assert y[:350].sum() == 0
        assert y[350:].sum() == 150

    def test_train_lightweight_history_length(self):
        """直接调 _train_lightweight, 验证 training_history 与 best_loss 跟踪。"""
        np.random.seed(3)
        p = LSTMPredictor(_small_config())
        X = np.random.randn(12, 6, len(FEATURE_COLS)).astype(np.float32)
        y = np.array([0, 1] * 6, dtype=np.float32)
        result = p._train_lightweight(X, y, len(FEATURE_COLS))
        assert result["status"] == "success"
        assert p.trained is True
        assert len(p.training_history) == 12
        assert np.isfinite(result["final_loss"])

    def test_train_empty_loader(self):
        """_train_pytorch 收到空 loader (len==0) 时不应触发 ZeroDivisionError。

        无 torch 环境, 直接注入 mock torch/nn 并让 DataLoader 返回空可迭代,
        驱动代码走到 avg_loss = total_loss / len(loader) 这一行。
        """
        p = LSTMPredictor(_small_config())
        fake_torch = mock.MagicMock()
        # 关键: DataLoader 返回 len==0 的空可迭代, 使 epoch 内 for 循环不执行、total_loss=0
        fake_torch.utils.data.DataLoader.return_value = []
        p.torch = fake_torch
        p.nn = mock.MagicMock()
        p._build_pytorch_model = mock.MagicMock(return_value=mock.MagicMock())

        X = np.zeros((1, 6, len(FEATURE_COLS)), dtype=np.float32)
        y = np.zeros(1, dtype=np.float32)
        # 修复前: 0/0 → ZeroDivisionError; 修复后: avg_loss=0.0
        result = p._train_pytorch(X, y, len(FEATURE_COLS))

        assert result["status"] == "success"
        assert result["framework"] == "pytorch"
        assert p.trained is True
        # 每个 epoch 都正常记录 loss=0.0 (空 loader)
        assert len(p.training_history) == p.config.epochs
        assert all(h["loss"] == 0.0 for h in p.training_history)


# ============ 预测 ============


class TestPredict:
    def test_predict_raises_when_not_trained(self):
        p = LSTMPredictor(_small_config())
        with pytest.raises(RuntimeError, match="not trained"):
            p.predict(_make_rows(6), 1, "dev")

    def test_predict_full_result(self):
        np.random.seed(42)
        p = LSTMPredictor(_small_config())
        p.train(_make_rows(25))
        result = p.predict(_make_rows(6), device_id=1, device_name="dev-1")

        assert isinstance(result, PredictionResult)
        assert result.device_id == 1
        assert result.device_name == "dev-1"
        assert 0.0 <= result.failure_probability <= 1.0
        assert 0.0 <= result.anomaly_score <= 1.0
        assert result.risk_level in ("low", "medium", "high", "critical")
        assert result.health_trend in ("improving", "stable", "degrading", "critical")
        assert 0.0 <= result.confidence <= 0.95
        assert isinstance(result.key_indicators, list)
        assert isinstance(result.recommended_actions, list)

    def test_predict_pads_short_input(self):
        """recent_data 不足 sequence_length → 零填充分支。"""
        np.random.seed(42)
        p = LSTMPredictor(_small_config())
        p.train(_make_rows(25))
        result = p.predict(_make_rows(2), device_id=2, device_name="short")
        assert isinstance(result, PredictionResult)
        assert result.device_id == 2


# ============ 辅助指标计算 ============


class TestAuxiliaryComputations:
    def test_compute_anomaly_score_zero_and_positive(self):
        p = LSTMPredictor(_small_config())
        # 全正常 → 0
        assert p._compute_anomaly_score(np.zeros((6, 4))) == 0.0
        # total<20 → max(total*0.05,1)=1 → 1 异常/1 = 1.0
        data = np.array([[3.0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]], dtype=np.float32)
        assert p._compute_anomaly_score(data) == 1.0
        # total=40 → max(2,1)=2 → 1/2 = 0.5
        big = np.zeros((10, 4))
        big[0, 0] = 3.0
        assert p._compute_anomaly_score(big) == pytest.approx(0.5)

    def test_compute_health_trend_all_branches(self):
        p = LSTMPredictor(_small_config())
        # len<4 → stable
        assert p._compute_health_trend(np.zeros((3, 4))) == "stable"
        # 全正常 → stable
        assert p._compute_health_trend(np.zeros((6, 4))) == "stable"
        # critical: second_half >30% 异常
        crit = np.zeros((6, 4)); crit[3:6, :2] = 3.0  # 6/12=0.5 > 0.3
        assert p._compute_health_trend(crit) == "critical"
        # degrading: second 异常增多但不超 0.3, 且 > first*1.5
        deg = np.zeros((6, 4)); deg[3, 0] = 3.0  # second 1/12≈0.083, first 0
        assert p._compute_health_trend(deg) == "degrading"
        # improving: first 异常 > second*1.5
        imp = np.zeros((6, 4)); imp[0, 0] = 3.0
        assert p._compute_health_trend(imp) == "improving"

    def test_compute_risk_level_all_levels(self):
        p = LSTMPredictor(_small_config())
        assert p._compute_risk_level(1.0, 1.0) == "critical"   # 1.0 > 0.8
        assert p._compute_risk_level(0.7, 0.5) == "high"       # 0.64 > 0.5
        assert p._compute_risk_level(0.4, 0.4) == "medium"     # 0.4  > 0.3
        assert p._compute_risk_level(0.1, 0.1) == "low"        # 0.1  < 0.3

    def test_estimate_rul_branches(self):
        p = LSTMPredictor(_small_config())
        assert p._estimate_rul(0.5, []) is None                       # 空 data
        assert p._estimate_rul(0.5, [{"battery_soh": 10}]) == 100      # soh<20 → soh*10
        # 正常: soh=90, prob=0.5 → 90*100*0.5 = 4500
        assert p._estimate_rul(0.5, [{"battery_soh": 90}]) == 4500
        # soh 缺失 → 默认 90, prob=0 → 9000
        assert p._estimate_rul(0.0, [{}]) == 9000

    def test_extract_key_indicators_statuses(self):
        p = LSTMPredictor(_small_config())
        latest = {
            "battery_soc": 50,            # normal (递增阈值 20/40/60/80)
            "battery_soh": 30,            # critical (30 < 50)
            "battery_temperature": 36,    # 降序阈值 [45,40,35,30]，高温才算异常 → normal
            "battery_voltage": 400,       # thresholds None → normal
        }
        inds = p._extract_key_indicators(latest)
        assert len(inds) <= 8
        status = {i["key"]: i["status"] for i in inds}
        assert status["battery_soc"] == "normal"
        assert status["battery_soh"] == "critical"
        assert status["battery_temperature"] == "normal"
        assert status["battery_voltage"] == "normal"

    def test_temperature_threshold_design_quirk(self):
        """温度降序阈值按区间(仅高温异常)判定，常温/低温不再误判为 critical。"""
        p = LSTMPredictor(_small_config())
        bands = {
            25: "normal",    # 常温 → normal (原 bug: 恒 critical)
            36: "normal",    # 35-40 工作区间 → normal
            42: "warning",   # 超过次高阈值 40 → warning
            50: "critical",  # 超过最高阈值 45 → critical
        }
        for temp, expected in bands.items():
            inds = p._extract_key_indicators({"battery_temperature": temp})
            assert inds[0]["status"] == expected, f"battery_temperature={temp}"

    def test_extract_key_indicators_warning(self):
        p = LSTMPredictor(_small_config())
        # soh=60 → [50,70,85,95]: 60<70 → warning
        inds = p._extract_key_indicators({"battery_soh": 60})
        assert inds[0]["status"] == "warning"

    def test_extract_key_indicators_empty(self):
        p = LSTMPredictor(_small_config())
        assert p._extract_key_indicators({}) == []


class TestRecommendations:
    def _p(self):
        return LSTMPredictor(_small_config())

    def test_critical_risk(self):
        recs = self._p()._generate_recommendations("critical", 0.9, [])
        assert any("紧急" in r for r in recs)
        assert any("排查" in r for r in recs)

    def test_high_risk(self):
        recs = self._p()._generate_recommendations("high", 0.7, [])
        assert any("检修" in r for r in recs)

    def test_medium_risk(self):
        recs = self._p()._generate_recommendations("medium", 0.4, [])
        assert any("维护" in r or "潜在" in r for r in recs)

    def test_low_risk(self):
        recs = self._p()._generate_recommendations("low", 0.1, [])
        assert any("正常" in r for r in recs)

    def test_indicator_critical_temperature(self):
        inds = [{"name": "电池温度", "value": 50, "unit": "℃", "status": "critical"}]
        recs = self._p()._generate_recommendations("low", 0.1, inds)
        assert any("散热" in r for r in recs)

    def test_indicator_critical_soc(self):
        inds = [{"name": "电池SOC", "value": 10, "unit": "%", "status": "critical"}]
        recs = self._p()._generate_recommendations("low", 0.1, inds)
        assert any("充电" in r for r in recs)

    def test_indicator_critical_soh(self):
        inds = [{"name": "电池SOH", "value": 15, "unit": "%", "status": "critical"}]
        recs = self._p()._generate_recommendations("low", 0.1, inds)
        assert any("更换电池" in r for r in recs)

    def test_indicator_warning_temperature(self):
        inds = [{"name": "电池温度", "value": 45, "unit": "℃", "status": "warning"}]
        recs = self._p()._generate_recommendations("low", 0.1, inds)
        assert any("通风" in r for r in recs)

    def test_recommendations_capped_at_six(self):
        many = [{"name": "电池温度", "value": 50, "unit": "℃", "status": "critical"}] * 10
        recs = self._p()._generate_recommendations("critical", 0.9, many)
        assert len(recs) <= 6


# ============ 持久化 save / load ============


class TestPersistence:
    def test_save_and_load_lightweight_roundtrip(self, tmp_path):
        np.random.seed(42)
        p = LSTMPredictor(_small_config())
        p.train(_make_rows(25))

        model_path = tmp_path / "model"
        p.save(str(model_path))

        # 关键文件落盘
        assert (model_path / "preprocessor_stats.json").exists()
        assert (model_path / "config.json").exists()
        assert (model_path / "weights.npz").exists()        # lightweight 分支
        assert (model_path / "meta.json").exists()
        assert not (model_path / "model.pt").exists()       # 无 torch, 不走 pt 分支

        # meta 内容正确
        meta = json.loads((model_path / "meta.json").read_text())
        assert meta["trained"] is True
        assert meta["use_pytorch"] is False

        # load 到新实例, 仍可预测
        p2 = LSTMPredictor(_small_config())
        p2.load(str(model_path))
        assert p2.trained is True
        assert p2.use_pytorch is False
        assert p2._weights is not None
        result = p2.predict(_make_rows(6), 1, "loaded")
        assert isinstance(result, PredictionResult)

    def test_save_meta_includes_last_ten_history(self, tmp_path):
        np.random.seed(0)
        p = LSTMPredictor(_small_config(epochs=15))
        p.train(_make_rows(25))
        model_path = tmp_path / "m"
        p.save(str(model_path))
        meta = json.loads((model_path / "meta.json").read_text())
        # training_history 截断到最后 10 条
        assert len(meta["training_history"]) == 10


# ============ PredictiveMaintenanceService ============


class TestPredictiveMaintenanceService:
    async def test_train_device_model_persists_and_status(self, tmp_path):
        svc = PredictiveMaintenanceService(model_dir=str(tmp_path / "models"))
        result = await svc.train_device_model(1, _make_rows(25))
        assert result["status"] == "success"
        assert (tmp_path / "models" / "1" / "meta.json").exists()

        status = svc.get_model_status()
        assert "1" in status
        assert status["1"]["trained"] is True
        assert status["1"]["framework"] == "numpy"

    async def test_predict_failure_trains_when_untrained(self, tmp_path):
        svc = PredictiveMaintenanceService(model_dir=str(tmp_path / "models"))
        # 模型未训练 → predict_failure 内部先训练
        pred = await svc.predict_failure(5, _make_rows(25), "dev-5")
        assert isinstance(pred, PredictionResult)
        assert pred.device_id == 5
        assert pred.device_name == "dev-5"

    async def test_predict_failure_on_trained_predicts_directly(self, tmp_path):
        svc = PredictiveMaintenanceService(model_dir=str(tmp_path / "models"))
        await svc.train_device_model(7, _make_rows(25))
        pred = await svc.predict_failure(7, _make_rows(6), "dev-7")
        assert isinstance(pred, PredictionResult)

    async def test_get_or_create_predictor_loads_from_disk(self, tmp_path):
        models_dir = str(tmp_path / "models")
        svc1 = PredictiveMaintenanceService(model_dir=models_dir)
        await svc1.train_device_model(8, _make_rows(25))

        svc2 = PredictiveMaintenanceService(model_dir=models_dir)
        predictor = svc2.get_or_create_predictor(8)
        assert predictor.trained is True  # 从磁盘 meta 恢复
        pred = predictor.predict(_make_rows(6), 8, "dev-8")
        assert isinstance(pred, PredictionResult)

    async def test_batch_predict_multiple_devices(self, tmp_path):
        svc = PredictiveMaintenanceService(model_dir=str(tmp_path / "models"))
        reqs = [
            {"device_id": 11, "recent_data": _make_rows(25), "device_name": "a"},
            {"device_id": 12, "recent_data": _make_rows(25), "device_name": "b"},
        ]
        results = await svc.batch_predict(reqs)
        assert len(results) == 2
        assert {r.device_id for r in results} == {11, 12}

    async def test_batch_predict_swallows_per_device_errors(self, tmp_path):
        """坏数据(不可 float) → transform 抛 → predict_failure 抛 → batch_predict catch, 不影响其他设备。"""
        svc = PredictiveMaintenanceService(model_dir=str(tmp_path / "models"))
        bad_row = {
            "battery_soc": {"nested": "no"},  # float(dict) 抛 TypeError
            "battery_soh": 1, "battery_temperature": 1, "battery_voltage": 1,
        }
        reqs = [
            {"device_id": 21, "recent_data": [bad_row], "device_name": "bad"},
            {"device_id": 22, "recent_data": _make_rows(25), "device_name": "good"},
        ]
        results = await svc.batch_predict(reqs)
        # 坏设备被吞, 只剩好设备
        assert len(results) == 1
        assert results[0].device_id == 22

    def test_get_model_status_disk_scan(self, tmp_path):
        """磁盘存在但内存没有的模型 → 扫描 meta.json 上报。"""
        models_dir = tmp_path / "models"
        (models_dir / "99").mkdir(parents=True)
        (models_dir / "99" / "meta.json").write_text(
            json.dumps({"trained": True, "use_pytorch": False})
        )
        # 非数字目录应被忽略
        (models_dir / "not-a-device").mkdir()
        (models_dir / "not-a-device" / "meta.json").write_text("{}")

        svc = PredictiveMaintenanceService(model_dir=str(models_dir))
        status = svc.get_model_status()
        assert "99" in status
        assert status["99"]["trained"] is True
        assert status["99"]["on_disk"] is True
        assert "not-a-device" not in status

    async def test_get_model_status_skips_disk_entry_already_in_memory(self, tmp_path):
        """内存已有的设备, 磁盘扫描时跳过(不重复读 meta)。"""
        models_dir = str(tmp_path / "models")
        svc = PredictiveMaintenanceService(model_dir=models_dir)
        # 训练后设备 50 同时在内存与磁盘
        await svc.train_device_model(50, _make_rows(25))
        status = svc.get_model_status()
        assert "50" in status
        # 来自内存, 不带 on_disk 字段(磁盘扫描命中 int(d) not in self.models == False 跳过)
        assert "on_disk" not in status["50"]
        assert status["50"]["trained"] is True


# ============ 工具函数 ============


def _make_result(**overrides) -> PredictionResult:
    base = dict(
        device_id=1, device_name="d", prediction_time="2026-01-01T00:00:00",
        failure_probability=0.25, health_trend="stable", rul_hours=100.0,
        risk_level="medium", anomaly_score=0.1, key_indicators=[],
        recommended_actions=[], confidence=0.7,
    )
    base.update(overrides)
    return PredictionResult(**base)


class TestFormatDisplay:
    def test_basic_fields_and_percent(self):
        out = format_prediction_for_display(_make_result())
        assert out["failure_probability_display"] == "25.0%"
        assert out["rul_display"] == "100h"
        assert out["risk_emoji"] == "🟡"   # medium
        assert out["trend_emoji"] == "➡️"  # stable

    def test_rul_none_display(self):
        out = format_prediction_for_display(_make_result(rul_hours=None))
        assert out["rul_display"] == "N/A"

    def test_all_risk_emojis(self):
        m = {
            "low": "🟢", "medium": "🟡", "high": "🟠", "critical": "🔴",
        }
        for level, emoji in m.items():
            out = format_prediction_for_display(_make_result(risk_level=level))
            assert out["risk_emoji"] == emoji

    def test_all_trend_emojis(self):
        m = {
            "improving": "📈", "stable": "➡️", "degrading": "📉", "critical": "⬇️",
        }
        for trend, emoji in m.items():
            out = format_prediction_for_display(_make_result(health_trend=trend))
            assert out["trend_emoji"] == emoji

    def test_unknown_risk_and_trend_fallback_emoji(self):
        out = format_prediction_for_display(
            _make_result(risk_level="unknown", health_trend="unknown")
        )
        assert out["risk_emoji"] == "⚪"
        assert out["trend_emoji"] == "➡️"
