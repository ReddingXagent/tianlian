#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
调度引擎服务测试
"""
import pytest
from app.services.dispatch_engine import DispatchEngine

class TestDispatchEngine:
    def test_engine_initialization(self):
        engine = DispatchEngine()
        assert engine is not None

    def test_has_calculate_best_method(self):
        engine = DispatchEngine()
        assert hasattr(engine, "calculate_best_engineer")
        assert callable(engine.calculate_best_engineer)

    def test_has_dispatch_method(self):
        engine = DispatchEngine()
        assert hasattr(engine, "dispatch")
        assert callable(engine.dispatch)

    def test_engine_attributes(self):
        engine = DispatchEngine()
        attrs = [a for a in dir(engine) if not a.startswith('_')]
        assert len(attrs) > 0

    def test_calculate_best_engineer_returns_result(self):
        """calculate_best_engineer 应返回最佳工程师评分结果"""
        engine = DispatchEngine()
        workorder = {"device_type": "PV", "level": 2, "required_parts": ["inverter"]}
        engineers = [
            {"id": 1, "name": "张三", "status": "active", "location": {"lat": 30.5, "lon": 114.3},
             "skills": ["PV", "BAT"], "current_load": 2, "performance": {"completion_rate": 90, "satisfaction": 4.5, "avg_hours": 3}, "parts": ["inverter"]}
        ]
        station_location = {"lat": 30.6, "lon": 114.4}
        result = engine.calculate_best_engineer(workorder, engineers, station_location)
        assert result is not None
        assert "engineer" in result
        assert "total_score" in result
        assert "score_details" in result
        assert result["engineer"]["id"] == 1  # 应选中张三

    def test_calculate_best_engineer_multiple_engineers(self):
        """多个工程师中应选中得分最高的"""
        engine = DispatchEngine()
        workorder = {"device_type": "PV", "level": 2, "required_parts": ["inverter"]}
        engineers = [
            {"id": 1, "name": "张三", "status": "active", "location": {"lat": 30.5, "lon": 114.3},
             "skills": ["PV"], "current_load": 5, "performance": {}, "parts": []},
            {"id": 2, "name": "李四", "status": "active", "location": {"lat": 30.55, "lon": 114.35},
             "skills": ["光伏", "逆变器", "高压电工"], "current_load": 1, "performance": {"completion_rate": 95, "satisfaction": 4.8, "avg_hours": 2}, "parts": ["inverter", "cable"]},
        ]
        station_location = {"lat": 30.6, "lon": 114.4}
        result = engine.calculate_best_engineer(workorder, engineers, station_location)
        assert result is not None
        assert result["engineer"]["id"] == 2  # 李四技能/负载/绩效更优

    def test_calculate_best_engineer_no_match(self):
        """没有匹配的工程师时应返回 None"""
        engine = DispatchEngine()
        workorder = {"device_type": "unknown_type", "level": 1, "required_parts": []}
        engineers = []
        station_location = {"lat": 30.6, "lon": 114.4}
        result = engine.calculate_best_engineer(workorder, engineers, station_location)
        assert result is None

    def test_dispatch_returns_result(self):
        """dispatch 包装器应正确返回派单结果"""
        engine = DispatchEngine()
        workorder = {"device_type": "BAT", "level": 1, "required_parts": []}
        engineers = [
            {"id": 1, "name": "张三", "status": "active", "location": {"lat": 30.5, "lon": 114.3},
             "skills": ["BMS"], "current_load": 0, "performance": {}, "parts": []}
        ]
        station_location = {"lat": 30.6, "lon": 114.4}
        result = engine.dispatch(workorder, engineers, station_location)
        assert result is not None
        assert result["success"] is True
        assert result["engineer"]["id"] == 1

    def test_dispatch_no_engineers(self):
        """无可用工程师时返回失败结果"""
        engine = DispatchEngine()
        result = engine.dispatch(
            {"device_type": "PV", "level": 1, "required_parts": []},
            [],
            {"lat": 30.6, "lon": 114.4}
        )
        assert result is not None
        assert result["success"] is False
        assert result["engineer"] is None