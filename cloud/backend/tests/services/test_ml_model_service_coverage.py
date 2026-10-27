#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ML 模型服务覆盖率补强测试 (ml_model_service.py)。

策略:
- 训练→预测闭环: 用真实 sklearn 模型 + 强断言 (status/指标/文件存在/预测结构)。
- 错误分支用真实条件触发 (样本不足 / 无可提取特征 / 缺 scaler / 缺 model), 不弱化断言。
- 每个 MLModelService 实例使用 tmp_path 隔离 model_dir, 不污染全局 data/ml_models。
- 不修改源码。

注: extract_features 第 197 行 np.polyfit 在聚合温度点数恰为 1 时会抛 LinAlgError
(numpy 2.4 + 当前 LAPACK), 属源码潜在缺陷; 本测试数据每条记录含 >=3 个温度字段,
聚合后温度点数 >=3, 规避该路径, 不触发。
"""
import os
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler

from app.services.ml_model_service import (
    MLModelService,
    detect_anomaly,
    predict_fault as predict_fault_fn,
)


# ============ 辅助构造 ============

def _make_telemetry(n, fault_from=None, with_alarm=False):
    """生成 n 条字段一致的遥测记录。

    fault_from: 从该 index 起记录视为故障 (温度/电压/电流异常), 让分类/回归模型可学习。
    所有记录字段集合完全一致, 保证 extract_features 输出特征维度一致, 可堆叠成数值矩阵。
    """
    records = []
    for i in range(n):
        is_fault = fault_from is not None and i >= fault_from
        rec = {
            "battery_soc": float(80 - (i % 30)),
            "battery_soh": float(95 - (i % 10)),
            "battery_temperature": float(78.0 if is_fault else 35.0 + (i % 10)),
            "battery_voltage": float(420.0 if is_fault else 400.0 + (i % 20)),
            "battery_current": float(2.0 if is_fault else 10.0 + (i % 5)),
            "grid_voltage_a": float(220.0 + (i % 5)),
            "grid_current_a": float(5.0 + (i % 3)),
            "inv_temperature": float(82.0 if is_fault else 40.0 + (i % 8)),
            "internal_temperature": float(60.0 if is_fault else 30.0 + (i % 6)),
            "timestamp": (datetime(2024, 1, 1, 0, 0, 0) + timedelta(minutes=i)).isoformat(),
        }
        if with_alarm:
            rec["bms_alarm_word"] = 1 if is_fault else 0
        records.append(rec)
    return records


def _featureless_records(n):
    """n 条不含任何已知数值/温度/告警字段的记录 -> extract_features 返回空 DataFrame。"""
    return [{"unknown_key": i} for i in range(n)]


def _dummy_estimator():
    """一个可被 joblib 序列化的真实 sklearn 估计器 (未拟合), 用于注入缓存测试缺 scaler/缺特征分支。"""
    return RandomForestClassifier(n_estimators=2, random_state=0)


@pytest.fixture
def svc(tmp_path):
    """隔离 model_dir 的 MLModelService 实例。"""
    return MLModelService(model_dir=str(tmp_path / "ml_models"))


# ============ 路径辅助 ============

class TestPathHelpers:
    def test_get_model_path_model_name_branch(self, svc):
        # model_name 优先 -> "{model_name}.joblib"
        path = svc._get_model_path("fault_classifier", model_name="custom_model")
        assert path.endswith("custom_model.joblib")

    def test_get_model_path_device_branch(self, svc):
        path = svc._get_model_path("fault_classifier", device_id=5)
        assert path.endswith("fault_classifier_device_5.joblib")

    def test_get_model_path_global_branch(self, svc):
        path = svc._get_model_path("fault_classifier")
        assert path.endswith("fault_classifier_global.joblib")

    def test_get_scaler_path_device_branch(self, svc):
        path = svc._get_scaler_path("fault_classifier", device_id=5)
        assert path.endswith("scaler_fault_classifier_device_5.joblib")

    def test_get_scaler_path_global_branch(self, svc):
        # 覆盖 device_id=None 的 else 分支
        path = svc._get_scaler_path("fault_classifier")
        assert path.endswith("scaler_fault_classifier_global.joblib")


# ============ 模型/缩放器 持久化与加载 ============

class TestPersistence:
    def test_save_and_load_model_disk(self, svc):
        model = _dummy_estimator()
        svc.save_model(model, "fault_classifier", device_id=1)
        # 清缓存, 强制走磁盘加载分支
        svc.models.clear()
        loaded = svc.load_model("fault_classifier", device_id=1)
        assert loaded is not None
        assert isinstance(loaded, RandomForestClassifier)

    def test_load_model_cache_hit(self, svc):
        model = _dummy_estimator()
        svc.save_model(model, "fault_classifier", device_id=1)
        # 缓存命中: 同一 key 直接返回内存对象 (身份相同)
        assert svc.load_model("fault_classifier", device_id=1) is model

    def test_load_model_missing_returns_none(self, svc):
        assert svc.load_model("fault_classifier", device_id=999) is None

    def test_load_model_corrupt_file_returns_none(self, svc, tmp_path):
        # 写入非 joblib 内容, 触发 except 分支
        path = svc._get_model_path("fault_classifier", device_id=7)
        with open(path, "wb") as f:
            f.write(b"not a joblib file")
        assert svc.load_model("fault_classifier", device_id=7) is None

    def test_save_and_load_scaler_disk(self, svc):
        scaler = StandardScaler()
        svc.save_scaler(scaler, "fault_classifier", device_id=1)
        svc.scalers.clear()
        loaded = svc.load_scaler("fault_classifier", device_id=1)
        assert loaded is not None
        assert isinstance(loaded, StandardScaler)

    def test_load_scaler_cache_hit(self, svc):
        scaler = StandardScaler()
        svc.save_scaler(scaler, "fault_classifier", device_id=1)
        assert svc.load_scaler("fault_classifier", device_id=1) is scaler

    def test_load_scaler_missing_returns_none(self, svc):
        assert svc.load_scaler("fault_classifier", device_id=999) is None

    def test_load_scaler_corrupt_file_returns_none(self, svc):
        path = svc._get_scaler_path("fault_classifier", device_id=7)
        with open(path, "wb") as f:
            f.write(b"not a joblib file")
        assert svc.load_scaler("fault_classifier", device_id=7) is None

    def test_save_model_with_name(self, svc):
        model = _dummy_estimator()
        path = svc.save_model(model, "fault_classifier", model_name="named_model")
        assert path.endswith("named_model.joblib")
        assert os.path.exists(path)
        # model_name 进入缓存 key
        assert svc.load_model("fault_classifier", model_name="named_model") is model


# ============ 特征工程 ============

class TestExtractFeatures:
    def test_empty_input_returns_empty_dataframe(self, svc):
        df = svc.extract_features([])
        assert isinstance(df, pd.DataFrame)
        assert df.empty

    def test_numeric_stats(self, svc):
        df = svc.extract_features([
            {"battery_soc": 50.0, "battery_voltage": 400.0},
            {"battery_soc": 60.0, "battery_voltage": 410.0},
        ])
        assert not df.empty
        row = df.iloc[0]
        assert row["battery_soc_mean"] == pytest.approx(55.0)
        assert row["battery_soc_min"] == pytest.approx(50.0)
        assert row["battery_soc_max"] == pytest.approx(60.0)
        assert row["battery_soc_range"] == pytest.approx(10.0)
        assert "battery_soc_std" in row.index
        assert row["battery_voltage_mean"] == pytest.approx(405.0)

    def test_timestamp_time_interval_features(self, svc):
        df = svc.extract_features(_make_telemetry(5))
        row = df.iloc[0]
        assert "time_interval_mean" in row.index
        assert "time_interval_std" in row.index
        assert "time_interval_cv" in row.index
        # 记录间隔为 60 秒
        assert row["time_interval_mean"] == pytest.approx(60.0)

    def test_compound_features(self, svc):
        df = svc.extract_features([{
            "battery_voltage": 400.0, "battery_current": 10.0,
            "grid_voltage_a": 220.0, "grid_current_a": 5.0,
        }])
        row = df.iloc[0]
        assert row["battery_resistance_est"] == pytest.approx(40.0)   # 400/10
        assert row["grid_impedance_a"] == pytest.approx(44.0)         # 220/5

    def test_temperature_features(self, svc):
        df = svc.extract_features([
            {"inv_temperature": 40.0},
            {"inv_temperature": 50.0},
        ])
        row = df.iloc[0]
        assert "temperature_mean" in row.index
        assert "temperature_gradient" in row.index
        assert row["temperature_mean"] == pytest.approx(45.0)
        assert row["temperature_gradient"] == pytest.approx(10.0)

    def test_alarm_features(self, svc):
        df = svc.extract_features([
            {"bms_alarm_word": 0}, {"bms_alarm_word": 1}, {"bms_alarm_word": 2},
        ])
        row = df.iloc[0]
        # 3 条里 2 条非 0
        assert row["alarm_frequency"] == pytest.approx(2.0 / 3.0)
        assert row["has_alarms"] == 1

    def test_alarm_features_no_alarms(self, svc):
        df = svc.extract_features([{"bms_alarm_word": 0}, {"bms_alarm_word": 0}])
        row = df.iloc[0]
        assert row["alarm_frequency"] == pytest.approx(0.0)
        assert row["has_alarms"] == 0

    def test_single_record_produces_features(self, svc):
        # 训练逐条调用 extract_features([data]); 单条记录须产出非空特征。
        # 单条不触发 timestamp 分支 (需 len(df)>1), 故无 time_interval_* 特征。
        df = svc.extract_features([_make_telemetry(1)[0]])
        assert not df.empty
        row = df.iloc[0]
        assert "battery_soc_mean" in row.index
        assert "battery_resistance_est" in row.index
        assert "time_interval_mean" not in row.index


# ============ 故障分类模型 ============

class TestFaultClassifier:
    def test_insufficient_samples(self, svc):
        result = svc.train_fault_classifier(1, _make_telemetry(49), [0] * 49)
        assert result["status"] == "error"
        assert "至少需要50" in result["error"]
        assert result["samples"] == 49

    def test_too_few_features(self, svc):
        # 50 条通过样本数检查, 但无可提取特征 -> 有效特征太少
        result = svc.train_fault_classifier(1, _featureless_records(50), [0] * 50)
        assert result["status"] == "error"
        assert result["samples"] == 0

    def test_train_success(self, svc):
        data = _make_telemetry(60, fault_from=30)
        labels = [0] * 30 + [1] * 30
        result = svc.train_fault_classifier(1, data, labels)
        assert result["status"] == "success"
        assert result["device_id"] == 1
        assert result["model_type"] == "RandomForestClassifier"
        for k in ("accuracy", "precision", "recall", "f1_score"):
            assert isinstance(result[k], (int, float))
        assert result["training_samples"] + result["test_samples"] == 60
        assert result["feature_count"] > 0
        assert len(result["feature_importance"]) == result["feature_count"]
        assert os.path.exists(result["model_path"])
        assert os.path.exists(result["scaler_path"])
        assert "trained_at" in result
        # 两类可分, 准确率应明显高于随机
        assert result["accuracy"] >= 0.7

    def test_predict_no_model(self, svc):
        result = svc.predict_fault(1, _make_telemetry(5))
        assert result["prediction"] == "unknown"
        assert result["confidence"] == 0.0
        assert result["error"] == "模型未训练"

    def test_predict_no_scaler(self, svc):
        svc.save_model(_dummy_estimator(), "fault_classifier", device_id=1)
        result = svc.predict_fault(1, _make_telemetry(5))
        assert result["prediction"] == "unknown"
        assert result["error"] == "特征缩放器未找到"

    def test_predict_no_features(self, svc):
        svc.save_model(_dummy_estimator(), "fault_classifier", device_id=1)
        svc.save_scaler(StandardScaler(), "fault_classifier", device_id=1)
        result = svc.predict_fault(1, [])
        assert result["prediction"] == "unknown"
        assert result["error"] == "无法提取特征"

    def test_predict_success_after_training(self, svc):
        data = _make_telemetry(60, fault_from=30)
        svc.train_fault_classifier(1, data, [0] * 30 + [1] * 30)
        pred = svc.predict_fault(1, _make_telemetry(10, fault_from=5))
        assert pred["device_id"] == 1
        assert pred["prediction"] in ("fault", "normal")
        assert 0.0 <= pred["confidence"] <= 1.0
        assert pred["total_samples"] == 10
        assert len(pred["predictions"]) == 10
        assert "probabilities" in pred
        assert "fault_probability" in pred


# ============ 异常检测模型 ============

class TestAnomalyDetector:
    def test_insufficient_samples(self, svc):
        result = svc.train_anomaly_detector(1, _make_telemetry(99))
        assert result["status"] == "error"
        assert "至少需要100" in result["error"]
        assert result["samples"] == 99

    def test_too_few_features(self, svc):
        # 100 条通过样本数检查, 但无特征 -> 有效特征太少
        result = svc.train_anomaly_detector(1, _featureless_records(100))
        assert result["status"] == "error"
        assert result["samples"] == 0

    def test_train_success(self, svc):
        result = svc.train_anomaly_detector(1, _make_telemetry(110))
        assert result["status"] == "success"
        assert result["device_id"] == 1
        assert result["model_type"] == "IsolationForest"
        assert result["training_samples"] == 110
        assert result["anomaly_count"] >= 0
        assert 0.0 <= result["anomaly_rate"] <= 1.0
        assert result["feature_count"] > 0
        assert os.path.exists(result["model_path"])
        assert os.path.exists(result["scaler_path"])

    def test_detect_no_model(self, svc):
        result = svc.detect_anomalies(1, _make_telemetry(5))
        assert result["anomalies"] == []
        assert result["error"] == "模型未训练"

    def test_detect_no_scaler(self, svc):
        svc.save_model(_dummy_estimator(), "anomaly_detector", device_id=1)
        result = svc.detect_anomalies(1, _make_telemetry(5))
        assert result["anomalies"] == []
        assert result["error"] == "特征缩放器未找到"

    def test_detect_no_features(self, svc):
        svc.save_model(_dummy_estimator(), "anomaly_detector", device_id=1)
        svc.save_scaler(StandardScaler(), "anomaly_detector", device_id=1)
        result = svc.detect_anomalies(1, [])
        assert result["anomalies"] == []
        assert result["error"] == "无法提取特征"

    def test_detect_success_after_training(self, svc):
        svc.train_anomaly_detector(1, _make_telemetry(110))
        data = _make_telemetry(30)
        result = svc.detect_anomalies(1, data)
        assert result["device_id"] == 1
        assert result["total_samples"] == 30
        assert result["anomaly_count"] == len(result["anomalies"])
        assert isinstance(result["anomaly_score"], float)
        assert len(result["predictions"]) == 30
        assert len(result["anomaly_scores"]) == 30
        # 异常项结构
        for anomaly in result["anomalies"]:
            assert "timestamp" in anomaly
            assert "severity" in anomaly
            assert "anomaly_score" in anomaly


# ============ 健康度评分模型 ============

class TestHealthScorer:
    def test_insufficient_samples(self, svc):
        result = svc.train_health_scorer(1, _make_telemetry(49), [80.0] * 49)
        assert result["status"] == "error"
        assert "至少需要50" in result["error"]
        assert result["samples"] == 49

    def test_too_few_features(self, svc):
        result = svc.train_health_scorer(1, _featureless_records(50), [80.0] * 50)
        assert result["status"] == "error"
        assert result["samples"] == 0

    def test_train_success(self, svc):
        data = _make_telemetry(60)
        scores = [80.0 - (i % 30) for i in range(60)]
        result = svc.train_health_scorer(1, data, scores)
        assert result["status"] == "success"
        assert result["device_id"] == 1
        assert result["model_type"] == "RandomForestRegressor"
        assert isinstance(result["mae"], (int, float))
        assert isinstance(result["r2_score"], (int, float))
        assert result["training_samples"] + result["test_samples"] == 60
        assert result["feature_count"] > 0
        assert len(result["feature_importance"]) == result["feature_count"]
        assert os.path.exists(result["model_path"])
        assert os.path.exists(result["scaler_path"])

    def test_predict_no_model_returns_default(self, svc):
        result = svc.predict_health_score(1, _make_telemetry(5))
        assert result["health_score"] == 70.0
        assert result["confidence"] == 0.0
        assert result["error"] == "模型未训练，使用默认值"

    def test_predict_no_scaler_returns_default(self, svc):
        svc.save_model(_dummy_estimator(), "health_scorer", device_id=1)
        result = svc.predict_health_score(1, _make_telemetry(5))
        assert result["health_score"] == 70.0
        assert result["error"] == "特征缩放器未找到，使用默认值"

    def test_predict_no_features_returns_default(self, svc):
        svc.save_model(_dummy_estimator(), "health_scorer", device_id=1)
        svc.save_scaler(StandardScaler(), "health_scorer", device_id=1)
        result = svc.predict_health_score(1, [])
        assert result["health_score"] == 70.0
        assert result["error"] == "无法提取特征，使用默认值"

    def test_predict_success_after_training(self, svc):
        data = _make_telemetry(60)
        svc.train_health_scorer(1, data, [80.0 - (i % 30) for i in range(60)])
        result = svc.predict_health_score(1, _make_telemetry(8))
        assert result["device_id"] == 1
        assert 0.0 <= result["health_score"] <= 100.0
        assert isinstance(result["confidence"], float)
        # health_scorer 仅使用最近 5 个点 (源码 telemetry_data[-5:])
        assert result["prediction_samples"] == 5
        assert len(result["predictions"]) == 5
        assert isinstance(result["score_std"], float)


# ============ 模型管理 ============

class TestModelManagement:
    def test_get_model_status_for_device(self, svc):
        status = svc.get_model_status(device_id=1)
        assert status["model_dir"] == svc.model_dir
        assert "models" in status
        for mtype in ("fault_classifier", "anomaly_detector", "health_scorer"):
            assert mtype in status["models"]
            assert "has_model" in status["models"][mtype]
            assert "has_scaler" in status["models"][mtype]

    def test_get_model_status_global_lists_files(self, svc):
        # 训练几个模型, 让 model_dir 出现 .joblib 文件
        svc.train_fault_classifier(1, _make_telemetry(60, fault_from=30), [0] * 30 + [1] * 30)
        svc.train_anomaly_detector(2, _make_telemetry(110))
        status = svc.get_model_status()  # 不传 device_id -> 全局扫描分支
        assert status["model_dir"] == svc.model_dir
        assert status["total_models"] >= 1
        assert isinstance(status["models"], dict)
        assert isinstance(status["loaded_models"], list)
        assert isinstance(status["loaded_scalers"], list)

    def test_get_model_status_global_empty_dir(self, svc):
        status = svc.get_model_status()
        assert status["total_models"] == 0
        assert status["models"] == {}

    def test_delete_model_removes_files_and_cache(self, svc):
        model = _dummy_estimator()
        scaler = StandardScaler()
        svc.save_model(model, "fault_classifier", device_id=1)
        svc.save_scaler(scaler, "fault_classifier", device_id=1)
        model_path = svc._get_model_path("fault_classifier", device_id=1)
        scaler_path = svc._get_scaler_path("fault_classifier", device_id=1)
        assert os.path.exists(model_path) and os.path.exists(scaler_path)
        assert "fault_classifier_1_default" in svc.models
        assert "fault_classifier_1" in svc.scalers

        deleted = svc.delete_model("fault_classifier", device_id=1)
        assert deleted is True
        assert not os.path.exists(model_path)
        assert not os.path.exists(scaler_path)
        assert "fault_classifier_1_default" not in svc.models
        assert "fault_classifier_1" not in svc.scalers

    def test_delete_model_not_exists_returns_false(self, svc):
        deleted = svc.delete_model("fault_classifier", device_id=999)
        assert deleted is False

    def test_delete_model_by_name(self, svc):
        svc.save_model(_dummy_estimator(), "fault_classifier", model_name="named")
        path = svc._get_model_path("fault_classifier", model_name="named")
        assert os.path.exists(path)
        assert svc.delete_model("fault_classifier", model_name="named") is True
        assert not os.path.exists(path)


# ============ 模块级独立函数 ============

class TestStandaloneFunctions:
    def test_predict_fault_fn_with_kwargs(self):
        # 全局单例无模型 -> 返回 模型未训练
        result = predict_fault_fn(device_id=1, temperature=85.0, voltage=220.0, extra="x")
        assert isinstance(result, dict)
        assert result.get("device_id") == 1

    def test_predict_fault_fn_no_sensor_args(self):
        result = predict_fault_fn(device_id=1)
        assert isinstance(result, dict)

    def test_detect_anomaly_with_data(self):
        result = detect_anomaly(telemetry_data={"temperature": 85.0})
        assert isinstance(result, dict)
        assert "is_anomaly" in result
        assert "anomaly_score" in result
        assert "anomalies" in result

    def test_detect_anomaly_none_input(self):
        result = detect_anomaly(telemetry_data=None)
        assert isinstance(result, dict)
        assert result["is_anomaly"] is False
        assert result["anomalies"] == []
