#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ML 模型服务深度测试

覆盖范围：模型/缩放器存取与缓存、特征工程（数值/时序/复合/温度/告警）、
故障分类与异常检测训练-预测闭环、健康度回归、模型状态/删除、顶层便捷函数、
各错误分支（数据不足/特征不足/模型缺失/缩放器缺失/文件损坏）。

每个测试用独立 tmp_path 作为 model_dir，互不污染、不写全局 data/ml_models。
"""
import os
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import numpy as np
import pytest

from app.services.ml_model_service import (
    MLModelService,
    predict_fault as module_predict_fault,
    detect_anomaly as module_detect_anomaly,
)


# ===================== helpers =====================

def _batch(n, temp, alarm=0, **extra):
    """生成 n 条结构一致的遥测字典（temp 可为值或 callable(i)）。"""
    out = []
    base = datetime(2024, 1, 1)
    for i in range(n):
        t = temp(i) if callable(temp) else float(temp)
        d = {
            "battery_soc": 50.0 + (i % 10),
            "battery_soh": 95.0,
            "battery_temperature": t,
            "battery_voltage": 400.0,
            "battery_current": 10.0,
            "internal_temperature": t,
            "grid_voltage_a": 220.0,
            "grid_current_a": 5.0,
            "timestamp": (base + timedelta(minutes=i)).isoformat(),
            "bms_alarm_word": alarm,
        }
        d.update(extra)
        out.append(d)
    return out


# ===================== 初始化与路径 =====================

class TestInitAndPaths:
    def test_default_init_creates_dir(self, tmp_path):
        svc = MLModelService(model_dir=str(tmp_path / "ml"))
        assert os.path.isdir(str(tmp_path / "ml"))
        assert svc.models == {} and svc.scalers == {}

    def test_get_model_path_variants(self, tmp_path):
        svc = MLModelService(model_dir=str(tmp_path))
        assert svc._get_model_path("x", model_name="custom").endswith("custom.joblib")
        assert svc._get_model_path("x", device_id=5).endswith("x_device_5.joblib")
        assert svc._get_model_path("x").endswith("x_global.joblib")

    def test_get_scaler_path_variants(self, tmp_path):
        svc = MLModelService(model_dir=str(tmp_path))
        assert svc._get_scaler_path("x", device_id=5).endswith("scaler_x_device_5.joblib")
        assert svc._get_scaler_path("x").endswith("scaler_x_global.joblib")


# ===================== 存取与缓存 =====================

class TestSaveLoad:
    def test_save_load_model_roundtrip(self, tmp_path):
        svc = MLModelService(model_dir=str(tmp_path))
        obj = {"weights": [1, 2, 3]}
        path = svc.save_model(obj, "fault_classifier", device_id=1)
        assert os.path.exists(path)
        loaded = svc.load_model("fault_classifier", device_id=1)
        assert loaded == obj

    def test_load_model_cache_hit(self, tmp_path):
        svc = MLModelService(model_dir=str(tmp_path))
        obj = {"hi": 1}
        svc.save_model(obj, "fault_classifier", device_id=1)
        first = svc.load_model("fault_classifier", device_id=1)
        # 删除磁盘文件，第二次应从内存缓存返回同一对象
        os.remove(svc._get_model_path("fault_classifier", device_id=1))
        second = svc.load_model("fault_classifier", device_id=1)
        assert first is obj and second is obj

    def test_load_model_not_found(self, tmp_path):
        svc = MLModelService(model_dir=str(tmp_path))
        assert svc.load_model("fault_classifier", device_id=99) is None

    def test_load_model_from_disk(self, tmp_path):
        """save 同步写缓存 -> 清缓存后强制走 joblib.load 磁盘分支。"""
        svc = MLModelService(model_dir=str(tmp_path))
        obj = {"w": [1, 2, 3]}
        svc.save_model(obj, "fault_classifier", device_id=7)
        svc.models.clear()
        assert svc.load_model("fault_classifier", device_id=7) == obj

    def test_load_model_corrupt_file(self, tmp_path):
        svc = MLModelService(model_dir=str(tmp_path))
        path = svc._get_model_path("fault_classifier", device_id=1)
        with open(path, "w") as f:
            f.write("not a pickle")
        assert svc.load_model("fault_classifier", device_id=1) is None

    def test_save_load_scaler_roundtrip(self, tmp_path):
        svc = MLModelService(model_dir=str(tmp_path))
        scaler = {"mean": 0, "std": 1}
        path = svc.save_scaler(scaler, "fault_classifier", device_id=1)
        assert os.path.exists(path)
        assert svc.load_scaler("fault_classifier", device_id=1) == scaler

    def test_load_scaler_cache_hit(self, tmp_path):
        svc = MLModelService(model_dir=str(tmp_path))
        scaler = {"m": 1}
        svc.save_scaler(scaler, "anomaly_detector", device_id=2)
        first = svc.load_scaler("anomaly_detector", device_id=2)
        os.remove(svc._get_scaler_path("anomaly_detector", device_id=2))
        second = svc.load_scaler("anomaly_detector", device_id=2)
        assert first is scaler and second is scaler

    def test_load_scaler_not_found(self, tmp_path):
        svc = MLModelService(model_dir=str(tmp_path))
        assert svc.load_scaler("anomaly_detector", device_id=99) is None

    def test_load_scaler_from_disk(self, tmp_path):
        """清缓存后强制走 joblib.load 磁盘分支。"""
        svc = MLModelService(model_dir=str(tmp_path))
        scaler = {"mean": 0, "std": 1}
        svc.save_scaler(scaler, "anomaly_detector", device_id=7)
        svc.scalers.clear()
        assert svc.load_scaler("anomaly_detector", device_id=7) == scaler

    def test_load_scaler_corrupt_file(self, tmp_path):
        svc = MLModelService(model_dir=str(tmp_path))
        path = svc._get_scaler_path("anomaly_detector", device_id=1)
        with open(path, "w") as f:
            f.write("garbage")
        assert svc.load_scaler("anomaly_detector", device_id=1) is None


# ===================== 特征工程 =====================

class TestExtractFeatures:
    def test_empty_returns_empty_df(self, tmp_path):
        svc = MLModelService(model_dir=str(tmp_path))
        df = svc.extract_features([])
        assert df.empty

    def test_single_numeric(self, tmp_path):
        svc = MLModelService(model_dir=str(tmp_path))
        df = svc.extract_features([{"battery_soc": 50, "battery_temperature": 30,
                                    "battery_voltage": 400, "battery_current": 10}])
        assert not df.empty
        row = df.iloc[0]
        assert row["battery_soc_mean"] == 50
        assert row["battery_temperature_mean"] == 30
        assert "battery_resistance_est" in row  # 复合特征

    def test_single_temp_gradient_degenerate(self, tmp_path):
        """单个温度点(单温度列) -> polyfit 降级 0.0（避免 numpy LinAlgError）。"""
        svc = MLModelService(model_dir=str(tmp_path))
        df = svc.extract_features([{"battery_temperature": 30}])
        assert df.iloc[0]["temperature_gradient"] == 0.0

    def test_multi_point_temp_gradient_and_time_series(self, tmp_path):
        svc = MLModelService(model_dir=str(tmp_path))
        data = [
            {"battery_temperature": 30, "internal_temperature": 30, "timestamp": "2024-01-01T00:00:00"},
            {"battery_temperature": 40, "internal_temperature": 40, "timestamp": "2024-01-01T00:01:00"},
        ]
        df = svc.extract_features(data)
        row = df.iloc[0]
        assert "temperature_gradient" in row
        assert "time_interval_mean" in row

    def test_alarm_features_present(self, tmp_path):
        svc = MLModelService(model_dir=str(tmp_path))
        df = svc.extract_features([{"bms_alarm_word": 1}])
        assert df.iloc[0]["has_alarms"] == 1
        assert df.iloc[0]["alarm_frequency"] == 1.0

    def test_alarm_features_absent(self, tmp_path):
        svc = MLModelService(model_dir=str(tmp_path))
        df = svc.extract_features([{"bms_alarm_word": 0}])
        assert df.iloc[0]["has_alarms"] == 0

    def test_grid_impedance_feature(self, tmp_path):
        svc = MLModelService(model_dir=str(tmp_path))
        df = svc.extract_features([{"grid_voltage_a": 220, "grid_current_a": 5}])
        assert "grid_impedance_a" in df.iloc[0]


# ===================== 故障分类模型 =====================

class TestFaultClassifier:
    def test_train_insufficient_samples(self, tmp_path):
        svc = MLModelService(model_dir=str(tmp_path))
        res = svc.train_fault_classifier(1, _batch(30, 30.0), [0] * 30)
        assert res["status"] == "error"
        assert "50" in res["error"]

    def test_train_too_few_features(self, tmp_path):
        """60 个空字典 -> extract_features 全空 -> X 为空 -> 特征太少。"""
        svc = MLModelService(model_dir=str(tmp_path))
        res = svc.train_fault_classifier(1, [{}] * 60, [0] * 60)
        assert res["status"] == "error"
        assert res["samples"] == 0

    def test_train_success(self, tmp_path):
        svc = MLModelService(model_dir=str(tmp_path))
        # 30 条低温(正常) + 30 条高温(故障)
        data = _batch(30, 30.0) + _batch(30, 80.0)
        labels = [0] * 30 + [1] * 30
        res = svc.train_fault_classifier(1, data, labels)
        assert res["status"] == "success"
        assert res["model_type"] == "RandomForestClassifier"
        assert res["device_id"] == 1
        assert os.path.exists(res["model_path"])
        assert os.path.exists(res["scaler_path"])
        assert res["feature_count"] > 0

    def test_predict_model_not_trained(self, tmp_path):
        svc = MLModelService(model_dir=str(tmp_path))
        res = svc.predict_fault(1, _batch(10, 80.0))
        assert res["prediction"] == "unknown"
        assert res["confidence"] == 0.0
        assert "模型未训练" in res["error"]

    def test_predict_scaler_missing(self, tmp_path):
        svc = MLModelService(model_dir=str(tmp_path))
        data = _batch(30, 30.0) + _batch(30, 80.0)
        svc.train_fault_classifier(1, data, [0] * 30 + [1] * 30)
        # 删除 scaler -> 缩放器未找到分支
        os.remove(svc._get_scaler_path("fault_classifier", device_id=1))
        svc.scalers.clear()
        res = svc.predict_fault(1, _batch(10, 80.0))
        assert res["prediction"] == "unknown"
        assert "缩放器" in res["error"]

    def test_predict_no_extractable_features(self, tmp_path):
        svc = MLModelService(model_dir=str(tmp_path))
        svc.train_fault_classifier(1, _batch(30, 30.0) + _batch(30, 80.0),
                                   [0] * 30 + [1] * 30)
        res = svc.predict_fault(1, [{}] * 10)  # 最近10条全空
        assert res["prediction"] == "unknown"
        assert "无法提取特征" in res["error"]

    def test_predict_fault_path(self, tmp_path):
        svc = MLModelService(model_dir=str(tmp_path))
        svc.train_fault_classifier(1, _batch(30, 30.0) + _batch(30, 80.0),
                                   [0] * 30 + [1] * 30)
        res = svc.predict_fault(1, _batch(10, 90.0))  # 高温 -> 故障
        assert res["prediction"] == "fault"
        assert res["fault_samples"] > 0

    def test_predict_normal_path(self, tmp_path):
        svc = MLModelService(model_dir=str(tmp_path))
        svc.train_fault_classifier(1, _batch(30, 30.0) + _batch(30, 80.0),
                                   [0] * 30 + [1] * 30)
        res = svc.predict_fault(1, _batch(10, 20.0))  # 低温 -> 正常
        assert res["prediction"] == "normal"


# ===================== 异常检测模型 =====================

class TestAnomalyDetector:
    def test_train_insufficient_samples(self, tmp_path):
        svc = MLModelService(model_dir=str(tmp_path))
        res = svc.train_anomaly_detector(1, _batch(50, 30.0))
        assert res["status"] == "error"
        assert "100" in res["error"]

    def test_train_too_few_features(self, tmp_path):
        svc = MLModelService(model_dir=str(tmp_path))
        res = svc.train_anomaly_detector(1, [{}] * 100)
        assert res["status"] == "error"
        assert res["samples"] == 0

    def test_train_success(self, tmp_path):
        svc = MLModelService(model_dir=str(tmp_path))
        res = svc.train_anomaly_detector(1, _batch(100, 30.0))
        assert res["status"] == "success"
        assert res["model_type"] == "IsolationForest"
        assert os.path.exists(res["model_path"])
        assert "anomaly_rate" in res

    def test_detect_model_not_trained(self, tmp_path):
        svc = MLModelService(model_dir=str(tmp_path))
        res = svc.detect_anomalies(1, _batch(5, 30.0))
        assert res["anomalies"] == []
        assert "模型未训练" in res["error"]

    def test_detect_scaler_missing(self, tmp_path):
        svc = MLModelService(model_dir=str(tmp_path))
        svc.train_anomaly_detector(1, _batch(100, 30.0))
        os.remove(svc._get_scaler_path("anomaly_detector", device_id=1))
        svc.scalers.clear()
        res = svc.detect_anomalies(1, _batch(5, 30.0))
        assert "缩放器" in res["error"]

    def test_detect_no_extractable_features(self, tmp_path):
        svc = MLModelService(model_dir=str(tmp_path))
        svc.train_anomaly_detector(1, _batch(100, 30.0))
        res = svc.detect_anomalies(1, [{}] * 5)
        assert "无法提取特征" in res["error"]

    def test_detect_normal_run(self, tmp_path):
        """真实模型检测一批正常数据 -> 结构完整。"""
        svc = MLModelService(model_dir=str(tmp_path))
        svc.train_anomaly_detector(1, _batch(100, 30.0))
        res = svc.detect_anomalies(1, _batch(10, 30.0))
        assert res["device_id"] == 1
        assert res["total_samples"] == 10
        assert "anomaly_score" in res
        assert isinstance(res["anomalies"], list)

    def test_detect_severity_branches(self, tmp_path):
        """mock model 精确覆盖 severity high/medium/low 三分支。"""
        svc = MLModelService(model_dir=str(tmp_path))
        svc.train_anomaly_detector(1, _batch(100, 30.0))
        # 直接注入 mock 到内存缓存（joblib 无法序列化 MagicMock）；
        # detect 数据用与训练同结构的 _batch，保证特征列数与 scaler 匹配。
        model = MagicMock()
        model.predict.return_value = np.array([-1, -1, -1])
        model.decision_function.return_value = np.array([-0.6, -0.2, 0.1])
        svc.models["anomaly_detector_1_default"] = model
        res = svc.detect_anomalies(1, _batch(3, 30.0))
        assert res["anomaly_count"] == 3
        severities = {a["severity"] for a in res["anomalies"]}
        assert severities == {"high", "medium", "low"}


# ===================== 健康度评分模型 =====================

class TestHealthScorer:
    def test_train_insufficient_samples(self, tmp_path):
        svc = MLModelService(model_dir=str(tmp_path))
        res = svc.train_health_scorer(1, _batch(30, 30.0), [80.0] * 30)
        assert res["status"] == "error"
        assert "50" in res["error"]

    def test_train_too_few_features(self, tmp_path):
        svc = MLModelService(model_dir=str(tmp_path))
        res = svc.train_health_scorer(1, [{}] * 60, [80.0] * 60)
        assert res["status"] == "error"
        assert res["samples"] == 0

    def test_train_success(self, tmp_path):
        svc = MLModelService(model_dir=str(tmp_path))
        data = _batch(60, 30.0)
        scores = [60.0 + (i % 30) for i in range(60)]
        res = svc.train_health_scorer(1, data, scores)
        assert res["status"] == "success"
        assert res["model_type"] == "RandomForestRegressor"
        assert os.path.exists(res["model_path"])

    def test_predict_model_not_trained(self, tmp_path):
        svc = MLModelService(model_dir=str(tmp_path))
        res = svc.predict_health_score(1, _batch(5, 30.0))
        assert res["health_score"] == 70.0
        assert "模型未训练" in res["error"]

    def test_predict_scaler_missing(self, tmp_path):
        svc = MLModelService(model_dir=str(tmp_path))
        svc.train_health_scorer(1, _batch(60, 30.0), [60.0 + (i % 30) for i in range(60)])
        os.remove(svc._get_scaler_path("health_scorer", device_id=1))
        svc.scalers.clear()
        res = svc.predict_health_score(1, _batch(5, 30.0))
        assert res["health_score"] == 70.0
        assert "缩放器" in res["error"]

    def test_predict_no_extractable_features(self, tmp_path):
        svc = MLModelService(model_dir=str(tmp_path))
        svc.train_health_scorer(1, _batch(60, 30.0), [60.0 + (i % 30) for i in range(60)])
        res = svc.predict_health_score(1, [{}] * 5)
        assert res["health_score"] == 70.0
        assert "无法提取特征" in res["error"]

    def test_predict_success(self, tmp_path):
        svc = MLModelService(model_dir=str(tmp_path))
        svc.train_health_scorer(1, _batch(60, 30.0), [60.0 + (i % 30) for i in range(60)])
        res = svc.predict_health_score(1, _batch(5, 30.0))
        assert res["device_id"] == 1
        assert 0 <= res["health_score"] <= 100
        assert res["prediction_samples"] == 5
        assert "predictions" in res


# ===================== 模型管理 =====================

class TestModelManagement:
    def test_get_model_status_for_device(self, tmp_path):
        svc = MLModelService(model_dir=str(tmp_path))
        # 未训练
        status = svc.get_model_status(device_id=1)
        assert status["models"]["fault_classifier"]["has_model"] is False
        # 训练后
        svc.train_fault_classifier(1, _batch(30, 30.0) + _batch(30, 80.0),
                                   [0] * 30 + [1] * 30)
        status = svc.get_model_status(device_id=1)
        assert status["models"]["fault_classifier"]["has_model"] is True
        assert status["models"]["fault_classifier"]["has_scaler"] is True

    def test_get_model_status_global_lists_files(self, tmp_path):
        svc = MLModelService(model_dir=str(tmp_path))
        svc.train_fault_classifier(1, _batch(30, 30.0) + _batch(30, 80.0),
                                   [0] * 30 + [1] * 30)
        status = svc.get_model_status()
        assert status["total_models"] >= 1
        assert "models" in status
        # 至少识别到一个设备模型分组
        assert isinstance(status["models"], dict)

    def test_delete_existing_model(self, tmp_path):
        svc = MLModelService(model_dir=str(tmp_path))
        svc.train_fault_classifier(1, _batch(30, 30.0) + _batch(30, 80.0),
                                   [0] * 30 + [1] * 30)
        deleted = svc.delete_model("fault_classifier", device_id=1)
        assert deleted is True
        assert not os.path.exists(svc._get_model_path("fault_classifier", device_id=1))
        # 内存缓存也被清除
        assert "fault_classifier_1_default" not in svc.models

    def test_delete_nonexistent_model(self, tmp_path):
        svc = MLModelService(model_dir=str(tmp_path))
        deleted = svc.delete_model("fault_classifier", device_id=999)
        assert deleted is False

    def test_delete_model_with_loaded_cache(self, tmp_path):
        """已 load 进内存的模型删除时同步移除缓存。"""
        svc = MLModelService(model_dir=str(tmp_path))
        svc.save_model({"a": 1}, "anomaly_detector", device_id=3)
        svc.load_model("anomaly_detector", device_id=3)  # 进缓存
        assert "anomaly_detector_3_default" in svc.models
        svc.delete_model("anomaly_detector", device_id=3)
        assert "anomaly_detector_3_default" not in svc.models


# ===================== 顶层便捷函数 =====================

class TestModuleFunctions:
    def test_module_predict_fault_no_model(self):
        res = module_predict_fault(device_id=99998, temperature=85.0, voltage=220.0)
        assert isinstance(res, dict)
        assert res["prediction"] == "unknown"

    def test_module_predict_fault_empty_telemetry(self):
        res = module_predict_fault(device_id=99997)
        assert isinstance(res, dict)

    def test_module_detect_anomaly_no_data(self):
        res = module_detect_anomaly()
        assert isinstance(res, dict)
        assert "is_anomaly" in res

    def test_module_detect_anomaly_with_data(self):
        res = module_detect_anomaly(telemetry_data={"battery_temperature": 30})
        assert isinstance(res, dict)
        assert "anomaly_score" in res


# ===================== 向后兼容：基础结构测试 =====================

class TestMLModelServiceStructure:
    def test_service_module_exists(self):
        import app.services.ml_model_service as mod
        assert hasattr(mod, "MLModelService")

    def test_service_has_methods(self, tmp_path):
        svc = MLModelService(model_dir=str(tmp_path))
        for m in ("predict_fault", "predict_health_score", "detect_anomalies",
                  "train_fault_classifier", "train_anomaly_detector", "train_health_scorer"):
            assert callable(getattr(svc, m))
