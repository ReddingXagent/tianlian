"""
ML 模型服务 (app/services/ml_model_service.py) 单元测试

被测: MLModelService —— 设备故障预测 / 异常检测 / 健康度评分。
隔离: model_dir 指向 pytest tmp_path (真实 joblib 往返), 训练用小数据集;
      predict/* 用 MagicMock 注入 model+scaler 精确控制分支。
覆盖: 正常路径 + 边界条件 + 异常处理。
"""
import os

import numpy as np
import pytest

from app.services.ml_model_service import (
    MLModelService,
    predict_fault as module_predict_fault,
    detect_anomaly as module_detect_anomaly,
)


@pytest.fixture
def svc(tmp_path):
    """每个测试用独立临时 model_dir, 互不污染。"""
    return MLModelService(model_dir=str(tmp_path))


# ═══════════════════════════════════════════════════════════════════
# 初始化
# ═══════════════════════════════════════════════════════════════════
class TestInit:
    def test_init_creates_model_dir(self, tmp_path):
        target = str(tmp_path / "ml_models")
        s = MLModelService(model_dir=target)
        assert os.path.isdir(target)
        assert s.model_dir == target
        assert s.models == {}
        assert s.scalers == {}

    def test_init_default_model_dir_exists(self):
        # 不传 model_dir → 用默认目录, 已被 import 时创建
        s = MLModelService()
        assert os.path.isdir(s.model_dir)


# ═══════════════════════════════════════════════════════════════════
# 路径生成 (三分支优先级: model_name > device_id > global)
# ═══════════════════════════════════════════════════════════════════
class TestPaths:
    def test_model_path_with_name(self, svc):
        assert svc._get_model_path("rf", model_name="custom").endswith("custom.joblib")

    def test_model_path_with_device(self, svc):
        assert svc._get_model_path("rf", device_id=7).endswith("rf_device_7.joblib")

    def test_model_path_global(self, svc):
        assert svc._get_model_path("rf").endswith("rf_global.joblib")

    def test_model_path_name_overrides_device(self, svc):
        # model_name 优先于 device_id
        p = svc._get_model_path("rf", device_id=7, model_name="m")
        assert p.endswith("m.joblib")

    def test_scaler_path_with_device(self, svc):
        assert svc._get_scaler_path("rf", device_id=3).endswith("scaler_rf_device_3.joblib")

    def test_scaler_path_global(self, svc):
        assert svc._get_scaler_path("rf").endswith("scaler_rf_global.joblib")


# ═══════════════════════════════════════════════════════════════════
# save / load 往返 + 异常
# ═══════════════════════════════════════════════════════════════════
class TestSaveLoad:
    def test_save_then_load_cache_hit(self, svc):
        model = {"w": [1, 2, 3]}
        path = svc.save_model(model, "rf", device_id=1)
        assert os.path.exists(path)
        # 缓存: 同对象直接返回, 不读盘
        assert svc.load_model("rf", device_id=1) is model

    def test_load_model_from_disk_after_cache_clear(self, svc):
        model = {"w": [1, 2, 3]}
        svc.save_model(model, "rf", device_id=1)
        svc.models.clear()
        loaded = svc.load_model("rf", device_id=1)
        assert loaded == model

    def test_load_model_not_exist_returns_none(self, svc):
        assert svc.load_model("nonexistent_model") is None

    def test_load_model_joblib_corrupt_returns_none(self, svc):
        # 写一个非 joblib 文件 → joblib.load 抛异常 → 吞掉返回 None
        bad_path = svc._get_model_path("bad")
        with open(bad_path, "w") as f:
            f.write("not a joblib payload")
        assert svc.load_model("bad") is None

    def test_save_then_load_scaler_cache_hit(self, svc):
        scaler = {"mean": 0.5}
        path = svc.save_scaler(scaler, "rf", device_id=2)
        assert os.path.exists(path)
        assert svc.load_scaler("rf", device_id=2) is scaler

    def test_load_scaler_from_disk_after_cache_clear(self, svc):
        scaler = {"mean": 0.5, "std": 0.1}
        svc.save_scaler(scaler, "rf", device_id=2)
        svc.scalers.clear()
        assert svc.load_scaler("rf", device_id=2) == scaler

    def test_load_scaler_not_exist_returns_none(self, svc):
        assert svc.load_scaler("nonexistent_scaler") is None


# ═══════════════════════════════════════════════════════════════════
# 特征工程
# ═══════════════════════════════════════════════════════════════════
class TestExtractFeatures:
    def test_empty_data_returns_empty_df(self, svc):
        assert svc.extract_features([]).empty

    def test_numeric_stats(self, svc):
        df = svc.extract_features([
            {"battery_soc": 80, "battery_voltage": 50},
            {"battery_soc": 60, "battery_voltage": 40},
        ])
        assert not df.empty
        row = df.iloc[0]
        assert row["battery_soc_mean"] == 70
        assert row["battery_soc_max"] == 80
        assert row["battery_soc_min"] == 60
        assert row["battery_soc_range"] == 20
        assert row["battery_voltage_range"] == 10

    def test_temperature_single_point_gradient_zero(self, svc):
        # 仅 1 个温度点 → polyfit 降级为 0.0, 不抛 LinAlgError
        df = svc.extract_features([{"inv_temperature": 45}])
        assert df.iloc[0]["temperature_gradient"] == 0.0

    def test_temperature_multi_point_gradient(self, svc):
        df = svc.extract_features([
            {"inv_temperature": 40},
            {"inv_temperature": 50},
            {"inv_temperature": 60},
        ])
        # 线性递增, 一阶拟合斜率 = 10
        assert df.iloc[0]["temperature_gradient"] == pytest.approx(10.0)

    def test_alarm_frequency_feature(self, svc):
        df = svc.extract_features([{"bms_alarm_word": 0}, {"bms_alarm_word": 1}])
        row = df.iloc[0]
        assert row["has_alarms"] == 1
        assert row["alarm_frequency"] == 0.5

    def test_no_alarm_when_all_zero(self, svc):
        df = svc.extract_features([{"bms_alarm_word": 0}, {"bms_alarm_word": 0}])
        assert df.iloc[0]["has_alarms"] == 0
        assert df.iloc[0]["alarm_frequency"] == 0.0

    def test_composite_resistance_feature(self, svc):
        df = svc.extract_features([{"battery_voltage": 48, "battery_current": 12}])
        # resistance = voltage.mean / max(current.mean, 0.001) = 4.0
        assert df.iloc[0]["battery_resistance_est"] == pytest.approx(4.0)

    def test_composite_resistance_zero_current_guarded(self, svc):
        # current=0 → max(0, 0.001) 防除零
        df = svc.extract_features([{"battery_voltage": 50, "battery_current": 0}])
        assert df.iloc[0]["battery_resistance_est"] == pytest.approx(50000.0)

    def test_time_interval_feature(self, svc):
        df = svc.extract_features([
            {"battery_soc": 50, "timestamp": "2026-01-01 00:00:00"},
            {"battery_soc": 51, "timestamp": "2026-01-01 00:01:00"},
        ])
        assert "time_interval_mean" in df.columns
        # 两次采样间隔 60 秒
        assert df.iloc[0]["time_interval_mean"] == pytest.approx(60.0)


# ═══════════════════════════════════════════════════════════════════
# 故障分类: train / predict
# ═══════════════════════════════════════════════════════════════════
class TestFaultClassifier:
    def test_train_insufficient_data(self, svc):
        r = svc.train_fault_classifier(1, [{"battery_soc": 50}] * 10, [0] * 10)
        assert r["status"] == "error"
        assert "至少需要50" in r["error"]
        assert r["samples"] == 10

    def test_train_too_few_valid_features(self, svc):
        # 60 条样本但都无可提取特征 → X 空 → 有效特征太少
        data = [{"unknown_field": "x"} for _ in range(60)]
        r = svc.train_fault_classifier(1, data, [0] * 60)
        assert r["status"] == "error"
        assert "有效特征太少" in r["error"]

    def test_train_success(self, svc):
        data, labels = [], []
        for i in range(60):
            if i < 30:
                data.append({"battery_soc": 20.0 + i * 0.1, "battery_voltage": 40.0})
                labels.append(1)
            else:
                data.append({"battery_soc": 80.0 + i * 0.1, "battery_voltage": 55.0})
                labels.append(0)
        r = svc.train_fault_classifier(1, data, labels)
        assert r["status"] == "success"
        assert r["model_type"] == "RandomForestClassifier"
        assert r["device_id"] == 1
        assert "accuracy" in r and "f1_score" in r
        assert isinstance(r["feature_importance"], list)
        assert os.path.exists(r["model_path"])
        assert os.path.exists(r["scaler_path"])
        assert r["training_samples"] + r["test_samples"] == 60

    def test_predict_model_not_trained(self, svc):
        r = svc.predict_fault(1, [{"battery_soc": 50}])
        assert r["prediction"] == "unknown"
        assert r["confidence"] == 0.0
        assert r["error"] == "模型未训练"

    def test_predict_scaler_not_found(self, svc):
        svc.models["fault_classifier_1_default"] = object()  # 模型在缓存, scaler 不在
        r = svc.predict_fault(1, [{"battery_soc": 50}])
        assert r["error"] == "特征缩放器未找到"

    def test_predict_cannot_extract_features(self, svc):
        svc.models["fault_classifier_1_default"] = object()
        svc.scalers["fault_classifier_1"] = object()
        r = svc.predict_fault(1, [{"unknown_field": "x"}])
        assert r["error"] == "无法提取特征"

    def test_predict_majority_normal(self, svc):
        model, scaler = _mock_predict_pair(
            preds=[0, 0, 1], proba=[[0.8, 0.2], [0.7, 0.3], [0.6, 0.4]]
        )
        svc.models["fault_classifier_1_default"] = model
        svc.scalers["fault_classifier_1"] = scaler
        r = svc.predict_fault(1, [{"battery_soc": 50}, {"battery_soc": 51}, {"battery_soc": 52}])
        assert r["prediction"] == "normal"
        # fault_prob_mean = mean(0.2,0.3,0.4) = 0.3; confidence = 1 - 0.3 = 0.7
        assert r["confidence"] == pytest.approx(0.7)
        assert r["fault_samples"] == 1
        assert r["total_samples"] == 3

    def test_predict_majority_fault(self, svc):
        model, scaler = _mock_predict_pair(
            preds=[1, 1, 0], proba=[[0.1, 0.9], [0.2, 0.8], [0.7, 0.3]]
        )
        svc.models["fault_classifier_1_default"] = model
        svc.scalers["fault_classifier_1"] = scaler
        r = svc.predict_fault(1, [{"battery_soc": 50}] * 3)
        assert r["prediction"] == "fault"
        # is_fault=True → confidence = fault_prob_mean
        assert r["confidence"] == pytest.approx((0.9 + 0.8 + 0.3) / 3)
        assert r["fault_samples"] == 2


# ═══════════════════════════════════════════════════════════════════
# 异常检测: train / detect
# ═══════════════════════════════════════════════════════════════════
class TestAnomalyDetector:
    def test_train_insufficient_data(self, svc):
        r = svc.train_anomaly_detector(1, [{"battery_soc": 50}] * 50)
        assert r["status"] == "error"
        assert "至少需要100" in r["error"]

    def test_train_success(self, svc):
        rng = np.random.RandomState(0)
        data = [
            {"battery_soc": float(rng.randint(0, 100)), "battery_voltage": float(rng.randint(40, 60))}
            for _ in range(110)
        ]
        r = svc.train_anomaly_detector(1, data)
        assert r["status"] == "success"
        assert r["model_type"] == "IsolationForest"
        assert "anomaly_rate" in r and "anomaly_count" in r
        assert os.path.exists(r["model_path"])

    def test_detect_model_not_trained(self, svc):
        r = svc.detect_anomalies(1, [{"battery_soc": 50}])
        assert r["error"] == "模型未训练"
        assert r["anomalies"] == []

    def test_detect_scaler_not_found(self, svc):
        svc.models["anomaly_detector_1_default"] = object()
        r = svc.detect_anomalies(1, [{"battery_soc": 50}])
        assert r["error"] == "特征缩放器未找到"

    def test_detect_cannot_extract_features(self, svc):
        svc.models["anomaly_detector_1_default"] = object()
        svc.scalers["anomaly_detector_1"] = object()
        r = svc.detect_anomalies(1, [{"unknown_field": "x"}])
        assert r["error"] == "无法提取特征"

    def test_detect_success_with_anomalies(self, svc):
        from unittest.mock import MagicMock
        model = MagicMock()
        model.predict.return_value = np.array([-1, 1])
        model.decision_function.return_value = np.array([-0.6, 0.2])
        scaler = _mock_scaler()
        svc.models["anomaly_detector_1_default"] = model
        svc.scalers["anomaly_detector_1"] = scaler
        r = svc.detect_anomalies(1, [
            {"battery_soc": 50, "timestamp": "t1"},
            {"battery_soc": 51, "timestamp": "t2"},
        ])
        assert r["anomaly_count"] == 1
        assert r["anomalies"][0]["severity"] == "high"  # score -0.6 < -0.5
        assert r["anomalies"][0]["timestamp"] == "t1"
        assert r["total_samples"] == 2
        assert r["anomaly_rate"] == 0.5
        assert r["anomaly_score"] == pytest.approx((-0.6 + 0.2) / 2)


# ═══════════════════════════════════════════════════════════════════
# 健康度评分: train / predict
# ═══════════════════════════════════════════════════════════════════
class TestHealthScorer:
    def test_train_insufficient_data(self, svc):
        r = svc.train_health_scorer(1, [{"battery_soc": 50}] * 10, [80.0] * 10)
        assert r["status"] == "error"
        assert "至少需要50" in r["error"]

    def test_train_success(self, svc):
        data = [{"battery_soc": float(i % 100), "battery_voltage": 50.0} for i in range(60)]
        scores = [float(i % 100) for i in range(60)]
        r = svc.train_health_scorer(1, data, scores)
        assert r["status"] == "success"
        assert r["model_type"] == "RandomForestRegressor"
        assert "mae" in r and "r2_score" in r
        assert os.path.exists(r["model_path"])

    def test_predict_model_not_trained_default_70(self, svc):
        r = svc.predict_health_score(1, [{"battery_soc": 50}])
        assert r["health_score"] == 70.0
        assert r["confidence"] == 0.0
        assert r["error"] == "模型未训练，使用默认值"

    def test_predict_scaler_not_found_default_70(self, svc):
        svc.models["health_scorer_1_default"] = object()
        r = svc.predict_health_score(1, [{"battery_soc": 50}])
        assert r["health_score"] == 70.0
        assert r["error"] == "特征缩放器未找到，使用默认值"

    def test_predict_cannot_extract_features_default_70(self, svc):
        svc.models["health_scorer_1_default"] = object()
        svc.scalers["health_scorer_1"] = object()
        r = svc.predict_health_score(1, [{"unknown_field": "x"}])
        assert r["health_score"] == 70.0
        assert r["error"] == "无法提取特征，使用默认值"

    def test_predict_success_and_clamp_high(self, svc):
        from unittest.mock import MagicMock
        model = MagicMock()
        model.predict.return_value = np.array([120.0, 130.0])  # 均值 125 → clamp 100
        svc.models["health_scorer_1_default"] = model
        svc.scalers["health_scorer_1"] = _mock_scaler()
        r = svc.predict_health_score(1, [{"battery_soc": 50}] * 2)
        assert r["health_score"] == 100.0
        # std=5 → confidence = 1 - 5/100 = 0.95
        assert r["confidence"] == pytest.approx(0.95)
        assert r["prediction_samples"] == 2

    def test_predict_clamp_low(self, svc):
        from unittest.mock import MagicMock
        model = MagicMock()
        model.predict.return_value = np.array([-10.0, -20.0])  # 均值 -15 → clamp 0
        svc.models["health_scorer_1_default"] = model
        svc.scalers["health_scorer_1"] = _mock_scaler()
        r = svc.predict_health_score(1, [{"battery_soc": 50}] * 2)
        assert r["health_score"] == 0.0


# ═══════════════════════════════════════════════════════════════════
# 模型管理: status / delete
# ═══════════════════════════════════════════════════════════════════
class TestModelManagement:
    def test_status_specific_device(self, svc):
        svc.save_model({"a": 1}, "fault_classifier", device_id=1)
        st = svc.get_model_status(device_id=1)
        assert "fault_classifier" in st["models"]
        assert st["models"]["fault_classifier"]["has_model"] is True
        # 未存 scaler
        assert st["models"]["fault_classifier"]["has_scaler"] is False
        assert st["loaded_models"] == ["fault_classifier_1_default"]

    def test_status_global_lists_files(self, svc):
        svc.save_model({"a": 1}, "fault_classifier", device_id=1)
        st = svc.get_model_status()
        assert st["total_models"] == 1
        # 文件名 fault_classifier_device_1.joblib → parts[2] = 'device'
        assert "device" in st["models"]
        assert "fault_classifier" in st["models"]["device"]

    def test_delete_removes_files_and_cache(self, svc):
        svc.save_model({"x": 1}, "fault_classifier", device_id=1)
        svc.save_scaler({"m": 0}, "fault_classifier", device_id=1)
        assert "fault_classifier_1_default" in svc.models
        assert "fault_classifier_1" in svc.scalers
        deleted = svc.delete_model("fault_classifier", device_id=1)
        assert deleted is True
        assert not os.path.exists(svc._get_model_path("fault_classifier", device_id=1))
        assert not os.path.exists(svc._get_scaler_path("fault_classifier", device_id=1))
        assert "fault_classifier_1_default" not in svc.models
        assert "fault_classifier_1" not in svc.scalers

    def test_delete_when_not_exist_returns_false(self, svc):
        assert svc.delete_model("nonexistent", device_id=1) is False


# ═══════════════════════════════════════════════════════════════════
# 模块级便捷函数
# ═══════════════════════════════════════════════════════════════════
class TestModuleFunctions:
    def test_predict_fault_builds_telemetry_from_kwargs(self):
        from unittest.mock import patch
        with patch("app.services.ml_model_service.ml_model_service") as mock_svc:
            mock_svc.predict_fault.return_value = {"device_id": 5, "prediction": "normal"}
            r = module_predict_fault(device_id=5, temperature=30, voltage=48, extra=1)
            assert r["prediction"] == "normal"
            dev_id, telemetry = mock_svc.predict_fault.call_args.args
            assert dev_id == 5
            assert telemetry[0]["temperature"] == 30
            assert telemetry[0]["voltage"] == 48
            assert telemetry[0]["extra"] == 1

    def test_predict_fault_empty_when_no_metrics(self):
        from unittest.mock import patch
        with patch("app.services.ml_model_service.ml_model_service") as mock_svc:
            mock_svc.predict_fault.return_value = {"device_id": 5, "prediction": "unknown"}
            module_predict_fault(device_id=5)
            assert mock_svc.predict_fault.call_args.args[1] == []

    def test_detect_anomaly_with_data(self):
        from unittest.mock import patch
        with patch("app.services.ml_model_service.ml_model_service") as mock_svc:
            mock_svc.detect_anomalies.return_value = {
                "anomalies": [{"i": 1}], "anomaly_score": -0.5,
            }
            r = module_detect_anomaly({"battery_soc": 50})
            assert r["is_anomaly"] is True
            assert r["anomaly_score"] == -0.5
            assert len(r["anomalies"]) == 1

    def test_detect_anomaly_no_data_returns_not_anomaly(self):
        from unittest.mock import patch
        with patch("app.services.ml_model_service.ml_model_service") as mock_svc:
            mock_svc.detect_anomalies.return_value = {"anomalies": [], "anomaly_score": 0.0}
            r = module_detect_anomaly(None)
            assert r["is_anomaly"] is False
            # device_id=0 + 空 data
            assert mock_svc.detect_anomalies.call_args.kwargs["device_id"] == 0
            assert mock_svc.detect_anomalies.call_args.kwargs["telemetry_data"] == []


# ═══════════════════════════════════════════════════════════════════
# helpers
# ═══════════════════════════════════════════════════════════════════
def _mock_scaler():
    from unittest.mock import MagicMock
    sc = MagicMock()
    sc.transform.return_value = np.array([[1.0, 2.0]])
    return sc


def _mock_predict_pair(preds, proba):
    """返回 (model, scaler) MagicMock 对, 预设 predict/predict_proba 输出。"""
    from unittest.mock import MagicMock
    model = MagicMock()
    model.predict.return_value = np.array(preds)
    model.predict_proba.return_value = np.array(proba)
    return model, _mock_scaler()
