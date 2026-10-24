#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
健康监控服务测试

覆盖 HealthMonitor 全部公开方法 + run_health_check 入口：
  - calculate_all_health: 空设备列表 / 多设备更新 health_score 并返回结果
  - check_and_create_alarms: 空列表 early return / 跳过健康设备 / CRITICAL / WARNING / 去重
  - get_device_health: 设备不存在返回 {} / 正常返回 dict
  - get_health_trend: stub 返回 []
  - _generate_mock_data: 各设备类型温度范围 / 20% 低健康分支 / None 类型
  - run_health_check: db=None 自建并关闭会话 / 传入 db 不关闭 / 返回 dict 结构

用真实测试 DB（test_db fixture）测 DB 交互，mock HealthEngine.calculate_health_score
消除随机性，monkeypatch random.random 控制 _generate_mock_data 分支。
"""
import logging
from unittest.mock import MagicMock

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app.services.health_monitor import HealthMonitor, health_monitor, run_health_check
from app.models.station import Station, StationStatus
from app.models.device import Device, DeviceType, DeviceStatus
from app.models.alarm import Alarm, AlarmLevel, AlarmStatus
from app.models.workorder import WorkOrder, WorkOrderLevel, WorkOrderStatus


# ──────────────────────────────────────────────
# 辅助：在测试 DB 中种子站点 / 设备
# ──────────────────────────────────────────────
def _seed_station(session, code="ST-HM-001"):
    station = Station(name="健康监控测试站", code=code, address="测试地址", status=StationStatus.NORMAL)
    session.add(station)
    session.flush()
    return station


def _seed_device(session, station_id, sn, name, code,
                 dtype=DeviceType.PV_INVERTER, health_score=None):
    device = Device(
        sn=sn, name=name, code=code, type=dtype,
        station_id=station_id, status=DeviceStatus.ONLINE,
        health_score=health_score,
    )
    session.add(device)
    session.flush()
    return device


# ──────────────────────────────────────────────
# 构造 / 结构
# ──────────────────────────────────────────────
class TestHealthMonitorInit:
    def test_class_initialization(self):
        monitor = HealthMonitor()
        assert monitor is not None
        assert monitor.engine is not None

    def test_module_level_singleton(self):
        assert isinstance(health_monitor, HealthMonitor)

    def test_public_methods_exist(self):
        monitor = HealthMonitor()
        for m in ("calculate_all_health", "check_and_create_alarms",
                  "get_device_health", "get_health_trend", "_generate_mock_data"):
            assert callable(getattr(monitor, m))


# ──────────────────────────────────────────────
# calculate_all_health
# ──────────────────────────────────────────────
class TestCalculateAllHealth:
    def test_empty_device_list(self, test_db):
        session = test_db["session"]
        monitor = HealthMonitor()
        # 无设备：仅 query + commit，返回空列表
        results = monitor.calculate_all_health(db=session)
        assert results == []

    def test_updates_health_score_and_returns_results(self, test_db, monkeypatch):
        session = test_db["session"]
        station = _seed_station(session)
        d1 = _seed_device(session, station.id, "SN-HM-001", "逆变器#1",
                          "HM-INV-001", DeviceType.PV_INVERTER)
        d2 = _seed_device(session, station.id, "SN-HM-002", "充电桩#1",
                          "HM-CHG-001", DeviceType.CHARGER_DC)
        session.commit()

        monitor = HealthMonitor()
        # mock 引擎：按设备类型给确定性分数，避免随机性
        def fake_score(device_data, historical_data=None, device_type=None):
            if device_type == "pv_inverter":
                return 55.0, {"electrical": 55}
            return 95.0, {"electrical": 95}
        monkeypatch.setattr(monitor.engine, "calculate_health_score", fake_score)

        results = monitor.calculate_all_health(db=session)

        assert len(results) == 2
        # health_score 已持久化（同 session identity map 内即为同一对象）
        session.refresh(d1)
        session.refresh(d2)
        assert d1.health_score == 55.0
        assert d2.health_score == 95.0
        # 结果结构
        r1 = next(r for r in results if r["device_id"] == d1.id)
        assert r1["code"] == "HM-INV-001"
        assert r1["health_score"] == 55.0
        assert r1["details"] == {"electrical": 55}


# ──────────────────────────────────────────────
# calculate_all_health — 批量加载策略 (卡 0a5b31db, 防 OOM)
# ──────────────────────────────────────────────
class TestCalculateAllHealthBatching:
    """batch_size 分批查询 Device + 每批 commit, 避免一次 .all() 加载全量设备。

    只验证加载策略(分批/每批commit), 不改业务逻辑: 全部设备仍被处理,
    health_score 仍持久化, 默认 batch_size=100。
    """

    def test_default_batch_size_is_100(self):
        """任务卡要求 batch_size=100 默认。"""
        import inspect
        sig = inspect.signature(HealthMonitor.calculate_all_health)
        assert sig.parameters["batch_size"].default == 100

    def test_empty_device_list_still_returns_empty(self, test_db):
        """无设备仍返回 [](兼容现有行为)。"""
        session = test_db["session"]
        monitor = HealthMonitor()
        assert monitor.calculate_all_health(db=session, batch_size=10) == []

    def test_batches_process_all_devices(self, test_db, monkeypatch):
        """5 设备 batch_size=2 -> 全部更新 health_score, 返回 5 条结果。"""
        session = test_db["session"]
        station = _seed_station(session)
        devices = [
            _seed_device(session, station.id, f"SN-BATCH-{i}", f"批量设备{i}",
                         f"BATCH-{i}", DeviceType.PV_INVERTER)
            for i in range(5)
        ]
        session.commit()

        monitor = HealthMonitor()
        monkeypatch.setattr(
            monitor.engine, "calculate_health_score",
            lambda data, device_type=None: (88.0, {"ok": 1}),
        )

        results = monitor.calculate_all_health(db=session, batch_size=2)

        assert len(results) == 5
        assert {r["health_score"] for r in results} == {88.0}
        # 全部设备 health_score 已持久化(commit 后从 DB 重读)
        for d in devices:
            session.refresh(d)
            assert d.health_score == 88.0

    def test_commit_called_once_per_batch(self, test_db, monkeypatch):
        """5 设备 batch_size=2 -> ceil(5/2)=3 批, commit 恰好调用 3 次。"""
        session = test_db["session"]
        station = _seed_station(session)
        for i in range(5):
            _seed_device(session, station.id, f"SN-COMMIT-{i}", f"提交设备{i}",
                         f"COMMIT-{i}", DeviceType.PV_INVERTER)
        session.commit()

        monitor = HealthMonitor()
        monkeypatch.setattr(
            monitor.engine, "calculate_health_score",
            lambda data, device_type=None: (70.0, {}),
        )

        commit_calls = 0
        real_commit = session.commit  # 替换前捕获原绑定方法, 避免递归

        def spy_commit():
            nonlocal commit_calls
            commit_calls += 1
            real_commit()

        monkeypatch.setattr(session, "commit", spy_commit)

        monitor.calculate_all_health(db=session, batch_size=2)
        assert commit_calls == 3  # ceil(5/2) = 3

    def test_batching_logs_count_and_duration(self, test_db, monkeypatch, caplog):
        """分批处理记日志: 含处理设备数。"""
        session = test_db["session"]
        station = _seed_station(session)
        for i in range(3):
            _seed_device(session, station.id, f"SN-LOG-{i}", f"日志设备{i}",
                         f"LOG-{i}", DeviceType.PV_INVERTER)
        session.commit()

        monitor = HealthMonitor()
        monkeypatch.setattr(
            monitor.engine, "calculate_health_score",
            lambda data, device_type=None: (90.0, {}),
        )

        with caplog.at_level(logging.INFO, logger="app.services.health_monitor"):
            monitor.calculate_all_health(db=session, batch_size=2)

        # 日志里出现设备总数 3
        assert any("3" in r.getMessage() for r in caplog.records)


# ──────────────────────────────────────────────
# check_and_create_alarms
# ──────────────────────────────────────────────
class TestCheckAndCreateAlarms:
    def test_empty_devices_early_return(self, test_db):
        session = test_db["session"]
        monitor = HealthMonitor()
        assert monitor.check_and_create_alarms(db=session) == []

    def test_skip_healthy_device(self, test_db):
        session = test_db["session"]
        station = _seed_station(session)
        _seed_device(session, station.id, "SN-HM-010", "健康设备",
                     "HM-OK-001", health_score=95.0)
        session.commit()

        monitor = HealthMonitor()
        created = monitor.check_and_create_alarms(db=session)

        assert created == []
        assert session.query(Alarm).filter(Alarm.alarm_type == "health").count() == 0
        assert session.query(WorkOrder).count() == 0

    def test_critical_alarm_for_low_score(self, test_db):
        session = test_db["session"]
        station = _seed_station(session)
        d = _seed_device(session, station.id, "SN-HM-011", "严重设备",
                         "HM-CRIT-001", health_score=45.0)
        session.commit()

        monitor = HealthMonitor()
        created = monitor.check_and_create_alarms(db=session)

        assert len(created) == 1
        assert created[0]["level"] == "critical"
        assert created[0]["score"] == 45.0
        assert created[0]["device"] == "严重设备"

        alarm = session.query(Alarm).filter(
            Alarm.alarm_type == "health", Alarm.device_id == d.id
        ).one()
        assert alarm.level == AlarmLevel.CRITICAL
        assert alarm.status == AlarmStatus.ACTIVE
        assert alarm.station_id == station.id

        wo = session.query(WorkOrder).filter(WorkOrder.device_id == d.id).one()
        # score<60 → CRITICAL 工单；PENDING；type=repair
        assert wo.level == WorkOrderLevel.CRITICAL
        assert wo.status == WorkOrderStatus.PENDING
        assert wo.type == "repair"
        assert created[0]["workorder_id"] == wo.id

    def test_warning_alarm_for_mid_score(self, test_db):
        session = test_db["session"]
        station = _seed_station(session)
        d = _seed_device(session, station.id, "SN-HM-012", "警告设备",
                         "HM-WARN-001", health_score=70.0)
        session.commit()

        monitor = HealthMonitor()
        created = monitor.check_and_create_alarms(db=session)

        assert len(created) == 1
        assert created[0]["level"] == "warning"
        alarm = session.query(Alarm).filter(Alarm.alarm_type == "health").one()
        assert alarm.level == AlarmLevel.WARNING
        wo = session.query(WorkOrder).one()
        # score>=60 → WARNING
        assert wo.level == WorkOrderLevel.WARNING

    def test_dedup_skips_existing_active_health_alarm(self, test_db):
        session = test_db["session"]
        station = _seed_station(session)
        d = _seed_device(session, station.id, "SN-HM-013", "已有告警设备",
                         "HM-DUP-001", health_score=40.0)
        session.flush()
        # 预置一条 ACTIVE + health 类型告警 → 命中去重
        session.add(Alarm(
            device_id=d.id, station_id=station.id, level=AlarmLevel.CRITICAL,
            alarm_type="health", content="已存在健康告警", status=AlarmStatus.ACTIVE,
        ))
        session.commit()

        monitor = HealthMonitor()
        created = monitor.check_and_create_alarms(db=session)

        assert created == []
        assert session.query(WorkOrder).count() == 0
        # 仍只有那一条预置 health 告警，未新增
        assert session.query(Alarm).filter(Alarm.alarm_type == "health").count() == 1

    def test_non_health_active_alarm_does_not_dedup(self, test_db):
        """非 health 类型的 ACTIVE 告警不应触发去重（用 WARNING 分支避开 WorkOrderLevel.HIGH bug）。"""
        session = test_db["session"]
        station = _seed_station(session)
        d = _seed_device(session, station.id, "SN-HM-014", "其他告警设备",
                         "HM-ND-001", health_score=70.0)
        session.flush()
        session.add(Alarm(
            device_id=d.id, station_id=station.id, level=AlarmLevel.WARNING,
            alarm_type="over_temp", content="温度告警", status=AlarmStatus.ACTIVE,
        ))
        session.commit()

        monitor = HealthMonitor()
        created = monitor.check_and_create_alarms(db=session)

        assert len(created) == 1  # 仍创建 health 告警
        assert session.query(Alarm).filter(Alarm.alarm_type == "health").count() == 1


# ──────────────────────────────────────────────
# get_device_health
# ──────────────────────────────────────────────
class TestGetDeviceHealth:
    def test_not_found_returns_empty(self, test_db):
        session = test_db["session"]
        monitor = HealthMonitor()
        assert monitor.get_device_health(device_id=99999, db=session) == {}

    def test_returns_dict_for_valid_device(self, test_db, monkeypatch):
        session = test_db["session"]
        station = _seed_station(session)
        d = _seed_device(session, station.id, "SN-HM-020", "设备X",
                         "HM-GET-001", DeviceType.PV_INVERTER)
        session.commit()

        monitor = HealthMonitor()
        monkeypatch.setattr(
            monitor.engine, "calculate_health_score",
            lambda data, historical_data=None, device_type=None: (88.0, {"thermal": 88}),
        )

        result = monitor.get_device_health(device_id=d.id, db=session)
        assert result["device_id"] == d.id
        assert result["code"] == "HM-GET-001"
        assert result["name"] == "设备X"
        assert result["health_score"] == 88.0
        assert result["details"] == {"thermal": 88}


# ──────────────────────────────────────────────
# get_health_trend (stub)
# ──────────────────────────────────────────────
class TestGetHealthTrend:
    def test_returns_empty_list(self, test_db):
        session = test_db["session"]
        monitor = HealthMonitor()
        assert monitor.get_health_trend(device_id=1, db=session, days=7) == []


# ──────────────────────────────────────────────
# _generate_mock_data
# ──────────────────────────────────────────────
class TestGenerateMockData:
    _EXPECTED_KEYS = {
        "insulation_resistance", "leakage_current", "temperature", "voltage",
        "current", "comm_success_rate", "plug_count", "power_factor", "harmonic_ratio",
    }

    def test_returns_all_expected_keys(self):
        monitor = HealthMonitor()
        data = monitor._generate_mock_data(DeviceType.PV_INVERTER)
        assert self._EXPECTED_KEYS.issubset(data.keys())

    @pytest.mark.parametrize("dtype", [
        DeviceType.PV_INVERTER, DeviceType.BATTERY_INVERTER, DeviceType.PCS,
        DeviceType.BATTERY, DeviceType.CHARGER_DC, DeviceType.CHARGER_AC,
        DeviceType.METER, DeviceType.GATEWAY,
    ])
    def test_normal_temperature_in_type_range(self, monkeypatch, dtype):
        """random.random()>=0.2 → 走正常温度范围分支。"""
        monitor = HealthMonitor()
        monkeypatch.setattr("random.random", lambda: 0.5)
        data = monitor._generate_mock_data(dtype)
        # 各类型正常温度上限均 ≤ 70
        assert 20 <= data["temperature"] <= 70

    def test_low_health_branch_produces_high_temp_and_degraded_metrics(self, monkeypatch):
        """random.random()<0.2 → 低健康度分支：高温 + 漏电流↑ + 通信成功率↓。"""
        monitor = HealthMonitor()
        monkeypatch.setattr("random.random", lambda: 0.1)
        data = monitor._generate_mock_data(DeviceType.PV_INVERTER)
        # pv_inverter 高温范围 (75, 95)
        assert 75 <= data["temperature"] <= 95
        assert 5 <= data["leakage_current"] <= 15
        assert 80 <= data["comm_success_rate"] <= 95

    def test_low_health_branch_default_high_range_for_unknown_type(self, monkeypatch):
        """未知设备类型走默认高温范围 (75, 95)。"""
        monitor = HealthMonitor()
        monkeypatch.setattr("random.random", lambda: 0.1)
        data = monitor._generate_mock_data("unknown_type")
        assert 75 <= data["temperature"] <= 95

    def test_none_device_type_uses_default_ranges(self, monkeypatch):
        """device_type=None → dt_lower='' → 默认范围。"""
        monitor = HealthMonitor()
        # 正常分支：默认 (25, 65)
        monkeypatch.setattr("random.random", lambda: 0.5)
        data_normal = monitor._generate_mock_data(None)
        assert 25 <= data_normal["temperature"] <= 65
        # 低健康分支：默认 (75, 95)
        monkeypatch.setattr("random.random", lambda: 0.1)
        data_low = monitor._generate_mock_data(None)
        assert 75 <= data_low["temperature"] <= 95


# ──────────────────────────────────────────────
# run_health_check
# ──────────────────────────────────────────────
class TestRunHealthCheck:
    def test_with_passed_db_does_not_close_session(self, test_db, monkeypatch):
        """传入 db → own_session=False，函数不应关闭该 session。"""
        session = test_db["session"]
        station = _seed_station(session)
        _seed_device(session, station.id, "SN-HM-030", "RHC-A", "HM-RHC-A")
        _seed_device(session, station.id, "SN-HM-031", "RHC-B", "HM-RHC-B")
        session.commit()

        # mock 模块单例引擎 → 分数为健康，避免触发告警（测 alarms=False 日志分支）
        monkeypatch.setattr(
            health_monitor.engine, "calculate_health_score",
            lambda data, historical_data=None, device_type=None: (95.0, {"x": 95}),
        )

        result = run_health_check(db=session)

        assert set(result.keys()) == {"health_results", "alarms_created"}
        assert result["health_results"] == 2
        assert result["alarms_created"] == 0
        # session 未被关闭：仍可执行查询
        session.execute(text("SELECT 1"))

    def test_db_none_creates_and_closes_own_session(self, test_db, monkeypatch):
        """db=None → 自建 SessionLocal，finally 关闭 own_session；并覆盖 alarms 非空时的日志分支。"""
        session = test_db["session"]
        station = _seed_station(session)
        _seed_device(session, station.id, "SN-HM-RHC-001", "RHC设备",
                     "HM-RHC-001", health_score=70.0)
        session.commit()

        import app.core.database as db_module
        closed = {"v": False}
        real_factory = sessionmaker(bind=test_db["engine"])

        def spy_factory():
            s = real_factory()
            orig_close = s.close

            def close_spy():
                closed["v"] = True
                orig_close()

            s.close = close_spy
            return s

        monkeypatch.setattr(db_module, "SessionLocal", spy_factory)
        # mock 单例引擎 → 确定性 WARNING 分数(70)，触发告警（覆盖 alarms=True 日志分支，
        # 同时避开 score<60 的 WorkOrderLevel.HIGH 崩溃 bug）
        monkeypatch.setattr(
            health_monitor.engine, "calculate_health_score",
            lambda data, historical_data=None, device_type=None: (70.0, {"x": 70}),
        )

        result = run_health_check(db=None)

        assert result["health_results"] == 1
        assert result["alarms_created"] == 1
        assert closed["v"] is True


# ──────────────────────────────────────────────
# 异常保护 (卡 8a22e879): DB 故障时 rollback + 记日志 + 返回安全默认值, 不向上抛
# 参考 charging_pricing.py (卡 01b3880b) 加固模式。get_health_trend 无 DB 操作, 不适用。
# ──────────────────────────────────────────────
class TestExceptionProtection:
    """DB 异常时各方法应 rollback + 记日志 + 返回安全默认值, 而非向上抛崩溃调用方。"""

    def test_calculate_all_health_db_failure_returns_empty(self, caplog):
        monitor = HealthMonitor()
        db = MagicMock()
        db.query.side_effect = RuntimeError("DB down")

        with caplog.at_level(logging.ERROR, logger="app.services.health_monitor"):
            result = monitor.calculate_all_health(db=db)

        assert result == []
        db.rollback.assert_called_once()
        assert any("calculate_all_health" in r.message for r in caplog.records)

    def test_check_and_create_alarms_db_failure_returns_empty(self, caplog):
        monitor = HealthMonitor()
        db = MagicMock()
        db.query.side_effect = RuntimeError("DB down")

        with caplog.at_level(logging.ERROR, logger="app.services.health_monitor"):
            result = monitor.check_and_create_alarms(db=db)

        assert result == []
        db.rollback.assert_called_once()
        assert any("check_and_create_alarms" in r.message for r in caplog.records)

    def test_get_device_health_db_failure_returns_empty(self, caplog):
        monitor = HealthMonitor()
        db = MagicMock()
        db.query.side_effect = RuntimeError("DB down")

        with caplog.at_level(logging.ERROR, logger="app.services.health_monitor"):
            result = monitor.get_device_health(device_id=1, db=db)

        assert result == {}
        db.rollback.assert_called_once()
        assert any("get_device_health" in r.message for r in caplog.records)
