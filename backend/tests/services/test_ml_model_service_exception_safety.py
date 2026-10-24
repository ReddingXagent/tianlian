#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ml_model_service 异常安全加固测试 (工作板卡片 88b757ec)。

背景: ml_model_service.py 仅 2 处 try/except, 但做模型训练/预测, 输入是真实遥测脏数据。
fit/transform/predict 对 NaN/Inf/标签错配/特征维度漂移 会抛原始异常, 直传 API 层 -> 500。
本套件验证四类脏输入下, 服务返回结构化错误 (与既有 status:error / 域默认值风格一致),
而非抛异常。

四类脏输入:
1. 空数据      —— 空遥测 / 空标签 (标签数 != 样本数)
2. 全 NaN/Inf  —— 非有限值混入特征矩阵 (.dropna 不剔除 inf -> mean=inf, std=nan)
3. 单样本/schema 退化 —— 预测时特征维度 != 训练时 (scaler.transform 抛 ValueError)
4. 单类标签    —— 分类器训练标签仅含单一类别 (静默训练出无用模型)

每个 MLModelService 实例使用 tmp_path 隔离 model_dir, 不污染全局 data/ml_models。
"""
import pytest

from app.services.ml_model_service import MLModelService


# ===================== 辅助构造 =====================

def _rich(n, fault_from=None):
    """n 条字段丰富的遥测 (训练用): 多个数值列 + 多个温度列 -> extract_features 产出高维特征。

    fault_from: 从该 index 起记录温度/电压抬高, 让分类/回归模型可学习两类分布。
    所有记录字段集合一致, 保证特征维度一致可堆叠成数值矩阵。
    """
    records = []
    for i in range(n):
        is_fault = fault_from is not None and i >= fault_from
        records.append({
            "battery_soc": float(80 - (i % 30)),
            "battery_soh": float(95 - (i % 10)),
            "battery_temperature": float(78.0 if is_fault else 35.0 + (i % 10)),
            "battery_voltage": float(420.0 if is_fault else 400.0 + (i % 20)),
            "battery_current": float(2.0 if is_fault else 10.0 + (i % 5)),
            "grid_voltage_a": float(220.0 + (i % 5)),
            "grid_current_a": float(5.0 + (i % 3)),
            "inv_temperature": float(82.0 if is_fault else 40.0 + (i % 8)),
            "internal_temperature": float(60.0 if is_fault else 30.0 + (i % 6)),
        })
    return records


def _sparse(n):
    """n 条仅含单一数值字段的遥测 (预测用): 特征维度远小于训练 -> scaler.transform 维度不匹配。"""
    return [{"battery_soc": 50.0 + i} for i in range(n)]


def _inf_rich(n):
    """n 条与 _rich 同结构(同字段集)的遥测, 但 battery_soc=inf:
    dropna 不剔除 inf -> 该列 mean=inf/std=nan 混入特征矩阵, 维度与 _rich 一致。"""
    return [{
        "battery_soc": float("inf"),
        "battery_soh": float(95 - (i % 10)),
        "battery_temperature": 35.0 + (i % 10),
        "battery_voltage": 400.0 + (i % 20),
        "battery_current": 10.0 + (i % 5),
        "grid_voltage_a": 220.0 + (i % 5),
        "grid_current_a": 5.0 + (i % 3),
        "inv_temperature": 40.0 + (i % 8),
        "internal_temperature": 30.0 + (i % 6),
    } for i in range(n)]


@pytest.fixture
def svc(tmp_path):
    """隔离 model_dir 的 MLModelService 实例。"""
    return MLModelService(model_dir=str(tmp_path / "ml_models"))


# ===================== 1. 空数据 =====================

class TestEmptyInput:
    def test_extract_features_empty_list_returns_empty_df(self, svc):
        """空遥测列表 -> 空 DataFrame (既有契约, 不抛)。"""
        df = svc.extract_features([])
        assert df.empty

    def test_train_fault_classifier_empty_labels_returns_error(self, svc):
        """空标签列表 (标签数 0 != 样本数 60) -> 结构化 error, 不抛。"""
        res = svc.train_fault_classifier(1, _rich(60), [])
        assert res["status"] == "error"
        assert res["samples"] == 60

    def test_train_health_scorer_empty_scores_returns_error(self, svc):
        """空评分列表 (数量 != 样本数) -> 结构化 error, 不抛。"""
        res = svc.train_health_scorer(1, _rich(60), [])
        assert res["status"] == "error"
        assert res["samples"] == 60


# ===================== 2. 全 NaN / Inf =====================

class TestNonFiniteValues:
    def test_train_anomaly_detector_inf_cleaned_and_trains(self, svc):
        """inf 混入特征矩阵 (dropna 不剔除 inf -> mean=inf/std=nan) ->
        fit 前 _sanitize_matrix 清洗(->0)后 IsolationForest 正常训练 (success), 不抛 500。"""
        res = svc.train_anomaly_detector(1, _inf_rich(110))
        assert res["status"] == "success"
        assert res["model_type"] == "IsolationForest"

    def test_predict_fault_inf_input_returns_unknown(self, svc):
        """已训练模型, 预测输入含 inf -> scaler.transform 抛 ValueError ->
        预测守卫返回结构化 unknown (在线预测对脏输入保守降级, 不伪造预测值), 不抛。"""
        svc.train_fault_classifier(1, _rich(60, fault_from=30), [0] * 30 + [1] * 30)
        res = svc.predict_fault(1, _inf_rich(10))
        assert res["prediction"] == "unknown"
        assert res["confidence"] == 0.0
        assert "error" in res


# ===================== 3. 单样本 / schema 退化 (预测时特征维度不一致) =====================

class TestFeatureDimensionMismatch:
    @pytest.fixture
    def trained(self, svc):
        """训练用富字段 -> 预测用单字段, 制造维度漂移。"""
        svc.train_fault_classifier(1, _rich(60, fault_from=30), [0] * 30 + [1] * 30)
        svc.train_health_scorer(1, _rich(60), [80.0 - (i % 30) for i in range(60)])
        svc.train_anomaly_detector(1, _rich(110))
        return svc

    def test_predict_fault_dimension_mismatch(self, trained):
        """预测特征维度 < 训练 -> scaler.transform ValueError -> 结构化 unknown, 不抛。"""
        res = trained.predict_fault(1, _sparse(10))
        assert res["prediction"] == "unknown"
        assert res["confidence"] == 0.0
        assert "error" in res

    def test_predict_health_score_dimension_mismatch(self, trained):
        """维度不匹配 -> 结构化默认值 (health_score=70.0), 不抛。"""
        res = trained.predict_health_score(1, _sparse(5))
        assert res["health_score"] == 70.0
        assert res["confidence"] == 0.0
        assert "error" in res

    def test_detect_anomalies_dimension_mismatch(self, trained):
        """维度不匹配 -> 结构化空结果, 不抛。"""
        res = trained.detect_anomalies(1, _sparse(5))
        assert res["anomalies"] == []
        assert res["anomaly_score"] == 0.0
        assert "error" in res


# ===================== 特征提取自身的防御 =====================

class TestExtractFeaturesExceptionSafety:
    def test_bad_timestamp_string_returns_empty_df(self, svc):
        """2+ 条不可解析的 timestamp -> pd.to_datetime 抛 DateParseError
        -> extract_features 守卫返回空 DataFrame, 不抛 (单条记录不进 timestamp 分支, 需 >=2 条触发)。"""
        df = svc.extract_features([
            {"battery_temperature": 30, "timestamp": "not-a-date"},
            {"battery_temperature": 40, "timestamp": "also-bad"},
        ])
        assert df.empty


# ===================== 4. 单类标签 =====================

class TestSingleClassLabels:
    def test_train_fault_classifier_single_class_returns_error(self, svc):
        """60 条正常数据 + 标签全 0 -> 单一类别, 训练出无用模型(f1=0)。
        加固后应检测并返回结构化 error, 而非静默 success。"""
        res = svc.train_fault_classifier(1, _rich(60), [0] * 60)
        assert res["status"] == "error"
        assert "samples" in res

    def test_train_fault_classifier_two_classes_still_success(self, svc):
        """回归: 两类标签不受单类守卫影响, 仍正常训练 (守卫不误伤正常路径)。"""
        res = svc.train_fault_classifier(1, _rich(60, fault_from=30), [0] * 30 + [1] * 30)
        assert res["status"] == "success"
