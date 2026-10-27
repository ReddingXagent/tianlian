#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ml_model_service.extract_features 单点温度样本 polyfit LinAlgError 防御测试。

缺陷: 源码
    features['temperature_gradient'] = np.polyfit(range(len(all_temps)), all_temps, 1)[0]
当所有 temperature 列聚合后的非空温度点数 == 1 时, numpy 2.4 deg=1 polyfit 抛
LinAlgError (SVD did not converge in Linear Least Squares), 特征提取整体崩溃。

修复契约:
- 温度点数 >= 2: 正常 polyfit 拟合斜率 (行为不变, 多点路径不受影响)。
- 温度点数 == 1: temperature_gradient 降级为 0.0 (常量, 无梯度可拟合), 不抛异常。
- 只要存在 >=1 个温度点, temperature_gradient / temperature_mean 键始终存在。
"""
import pytest

from app.services.ml_model_service import MLModelService


@pytest.fixture
def svc(tmp_path):
    """隔离 model_dir 的 MLModelService 实例, 不污染全局 data/ml_models。"""
    return MLModelService(model_dir=str(tmp_path / "ml_models"))


class TestTemperatureGradientPolyfit:
    def test_single_temperature_point_degrades_to_zero(self, svc):
        """单温度列 + 仅 1 个非空温度点 -> 不抛异常, gradient=0.0, mean 保留, 键存在。"""
        df = svc.extract_features([{"battery_temperature": 35.0}])
        assert not df.empty
        row = df.iloc[0]
        assert "temperature_gradient" in row.index
        assert "temperature_mean" in row.index
        assert row["temperature_gradient"] == 0.0
        assert row["temperature_mean"] == pytest.approx(35.0)

    def test_single_point_when_other_rows_null(self, svc):
        """两行但仅一行温度非空 -> dropna 聚合后仍 1 点 -> 不崩, gradient=0.0。"""
        df = svc.extract_features([
            {"battery_temperature": 42.0},
            {"battery_temperature": None},
        ])
        assert not df.empty
        row = df.iloc[0]
        assert row["temperature_gradient"] == 0.0
        assert row["temperature_mean"] == pytest.approx(42.0)

    def test_multi_temperature_points_fit_slope(self, svc):
        """单温度列多点 -> 正常 polyfit, 斜率正确 (守卫不破坏多点拟合路径)。"""
        # 温度 30,40,50 位于位置 0,1,2 -> deg=1 拟合斜率为 10.0
        df = svc.extract_features([
            {"battery_temperature": 30.0},
            {"battery_temperature": 40.0},
            {"battery_temperature": 50.0},
        ])
        row = df.iloc[0]
        assert row["temperature_gradient"] == pytest.approx(10.0)
        assert row["temperature_mean"] == pytest.approx(40.0)
