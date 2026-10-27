"""车队告警规则引擎生产接线测试 (卡 49aafa24)

覆盖:
- A. fleet.scan_fleet_alerts task 注册 + beat */5 调度 (queue=maintenance)
- A. task 手动调用: 有启用规则的企业被扫描 (低电量真落记录), 无规则企业不扫,
     只枚举有启用规则的企业 (enable=False 不入列)
- A. 单企业异常隔离: 一个企业 check 抛错不影响其他企业, 结果含 errors 且不炸
- B. 脏阈值不崩: threshold 非数字字符串 → 回落 DEFAULT_* 常量仍正常检测
- C. uq_fleet_alert_active 部分唯一索引拦截同规则同车第二条 ACTIVE

设计: task 测试走 test_db fixture (task/service 内懒加载 SessionLocal →
被 conftest 覆盖为测试库)。
"""
from datetime import datetime, timedelta, timezone

import pytest
import sqlalchemy as sa

import app.tasks.fleet_alert_tasks  # noqa: F401 触发 @shared_task 注册
from app.models.fleet_alert_rule import (
    FleetAlertRule,
    FleetAlertRecord,
    AlertRuleType,
    AlertRecordStatus,
)
from app.models.charging_queue import ChargingQueue
from app.models.enterprise_vehicle import EnterpriseVehicle
from app.services.fleet_alert_service import (
    DEFAULT_LOW_BATTERY_SOC,
    check_low_battery,
    _threshold_number,
)

ENT_A = 71001
ENT_B = 71002


def _make_rule(db, enterprise_id, rule_type, threshold=None, enable=True):
    r = FleetAlertRule(
        enterprise_id=enterprise_id, rule_type=rule_type,
        threshold=threshold if threshold is not None else {},
        notify_channels=[], enable=enable,
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def _make_vehicle(db, enterprise_id, plate="京B10001", vin="VINSCAN00000001"):
    v = EnterpriseVehicle(
        enterprise_id=enterprise_id, plate_number=plate, vin=vin,
    )
    db.add(v)
    db.commit()
    db.refresh(v)
    return v


def _make_low_soc_queue(db, enterprise_id, vehicle_id, soc=0.10):
    q = ChargingQueue(
        station_id=1, vehicle_id=vehicle_id, enterprise_id=enterprise_id,
        current_soc=soc, status="waiting",
    )
    db.add(q)
    db.commit()
    db.refresh(q)
    return q


# ═══════════════════════════════════════════════════════════════
# A. celery task 注册 + beat_schedule
# ═══════════════════════════════════════════════════════════════

class TestTaskRegistration:
    def test_task_registered_in_celery_app(self):
        from app.core.celery_app import celery_app
        assert "fleet.scan_fleet_alerts" in celery_app.tasks

    def test_in_beat_schedule_every_5min(self):
        from app.core.celery_app import celery_app
        sched = celery_app.conf.beat_schedule.get("fleet-alert-scan")
        assert sched is not None, "beat_schedule 缺 fleet-alert-scan"
        assert sched["task"] == "fleet.scan_fleet_alerts"
        assert str(sched["schedule"]._orig_minute) == "*/5"
        assert sched["options"].get("queue") == "maintenance"


# ═══════════════════════════════════════════════════════════════
# A. task 手动调用 (真实 DB)
# ═══════════════════════════════════════════════════════════════

class TestScanTaskRun:
    def test_scans_enterprises_with_enabled_rules(self, test_db):
        db = test_db["session"]
        _make_rule(db, ENT_A, AlertRuleType.LOW_BATTERY, {"soc_below": 20})
        v = _make_vehicle(db, ENT_A)
        _make_low_soc_queue(db, ENT_A, v.id, soc=0.10)

        from app.tasks.fleet_alert_tasks import scan_fleet_alerts_task
        result = scan_fleet_alerts_task.apply().get()

        assert result["status"] == "completed"
        assert result["enterprises"] == 1
        assert result["created"] == 1
        assert (
            db.query(FleetAlertRecord)
            .filter(FleetAlertRecord.enterprise_id == ENT_A)
            .count() == 1
        )

    def test_no_rules_nothing_scanned(self, test_db):
        db = test_db["session"]
        from app.tasks.fleet_alert_tasks import scan_fleet_alerts_task
        result = scan_fleet_alerts_task.apply().get()
        assert result["enterprises"] == 0
        assert result["created"] == 0
        assert db.query(FleetAlertRecord).count() == 0

    def test_disabled_rule_enterprise_excluded(self, test_db):
        db = test_db["session"]
        _make_rule(db, ENT_A, AlertRuleType.LOW_BATTERY, enable=False)
        from app.tasks.fleet_alert_tasks import scan_fleet_alerts_task
        result = scan_fleet_alerts_task.apply().get()
        assert result["enterprises"] == 0

    def test_single_enterprise_failure_isolated(self, test_db, monkeypatch, caplog):
        """企业A的check抛错 → 记录errors继续, 企业B不受影响。"""
        db = test_db["session"]
        _make_rule(db, ENT_A, AlertRuleType.LOW_BATTERY)
        _make_rule(db, ENT_B, AlertRuleType.LOW_BATTERY)
        v_b = _make_vehicle(db, ENT_B, plate="京B20002", vin="VINSCAN00000002")
        _make_low_soc_queue(db, ENT_B, v_b.id, soc=0.05)

        from app.services import fleet_alert_service as svc
        from app.tasks.fleet_alert_tasks import scan_fleet_alerts_task

        real_check = svc.check_low_battery
        calls = []

        def flaky(enterprise_id, db=None):
            calls.append(enterprise_id)
            if enterprise_id == ENT_A:
                raise RuntimeError("db boom")
            return real_check(enterprise_id, db)

        monkeypatch.setattr(
            "app.services.fleet_alert_service.check_low_battery", flaky
        )
        with caplog.at_level("ERROR"):
            result = scan_fleet_alerts_task.apply().get()

        assert ENT_A in calls and ENT_B in calls, "失败企业不应中断其他企业"
        assert result["status"] == "completed_with_errors"
        assert len(result["errors"]) == 1
        assert result["errors"][0]["enterprise_id"] == ENT_A
        assert any("db boom" in e["error"] for e in result["errors"])
        assert any(r.exc_info for r in caplog.records if r.levelname == "ERROR")
        # 企业B的告警正常落库
        assert (
            db.query(FleetAlertRecord)
            .filter(FleetAlertRecord.enterprise_id == ENT_B)
            .count() == 1
        )


# ═══════════════════════════════════════════════════════════════
# B. 阈值解析加固
# ═══════════════════════════════════════════════════════════════

class TestThresholdHardening:
    def test_threshold_number_dirty_values_fall_back(self):
        assert _threshold_number({"soc_below": "abc"}, "soc_below", 20) == 20.0
        assert _threshold_number({"soc_below": None}, "soc_below", 20) == 20.0
        assert _threshold_number({}, "soc_below", 20) == 20.0
        assert _threshold_number(None, "soc_below", 20) == 20.0
        assert _threshold_number({"soc_below": [1, 2]}, "soc_below", 20) == 20.0
        assert _threshold_number({"soc_below": "15"}, "soc_below", 20) == 15.0

    def test_check_low_battery_dirty_threshold_no_crash(self, test_db):
        """脏阈值 → 回落 DEFAULT_LOW_BATTERY_SOC(=20%) 仍检测, 不抛 ValueError。"""
        db = test_db["session"]
        rule = _make_rule(db, ENT_A, AlertRuleType.LOW_BATTERY, {"soc_below": "not-a-number"})
        v = _make_vehicle(db, ENT_A, plate="京B30003", vin="VINSCAN00000003")
        # SOC 19% < 默认 20% → 触发; SOC 25% > 20% → 不触发
        _make_low_soc_queue(db, ENT_A, v.id, soc=0.19)

        created = check_low_battery(ENT_A)
        assert len(created) == 1
        assert "soc=19.0%" in created[0].alert_value

    def test_check_overtime_dirty_threshold_no_crash(self, test_db):
        from app.services.fleet_alert_service import check_overtime_parking
        from app.models.charging_order import ChargingOrder, OrderStatus

        db = test_db["session"]
        _make_rule(db, ENT_A, AlertRuleType.OVERTIME_PARKING, {"minutes": "soon"})
        v = _make_vehicle(db, ENT_A, plate="京B40004", vin="VINSCAN00000004")
        o = ChargingOrder(
            order_no="FA-SCAN-ORD-1", station_id=1, device_id=1,
            vehicle_id=v.id, plate_number=v.plate_number,
            order_status=OrderStatus.COMPLETED,
            end_time=datetime.now(timezone.utc) - timedelta(hours=3),
        )
        db.add(o)
        db.commit()

        # 不抛 ValueError; 默认 120min 阈值下 3h 前完成的订单触发
        created = check_overtime_parking(ENT_A)
        assert len(created) == 1

    def test_check_abnormal_dirty_threshold_no_crash(self, test_db):
        from app.services.fleet_alert_service import check_abnormal_charging
        from app.models.telemetry_v2 import TelemetryCharger

        from app.models.charging_order import ChargingOrder, OrderStatus

        db = test_db["session"]
        _make_rule(db, ENT_A, AlertRuleType.ABNORMAL_CHARGING, {"power_spike_kw": {"bad": 1}})
        v = _make_vehicle(db, ENT_A, plate="京B50005", vin="VINSCAN00000005")
        # 卡 6a1bdff2 后数据源是 ChargingOrder(CHARGING) 关联 device_id
        db.add(ChargingOrder(
            order_no="FA-SCAN-ORD-2", station_id=1, device_id=99,
            vehicle_id=v.id, plate_number=v.plate_number,
            order_status=OrderStatus.CHARGING,
        ))
        now = datetime.now(timezone.utc)
        db.add(TelemetryCharger(
            device_id=99, station_id=1, timestamp=now, charger_power=60.0,
        ))
        db.add(TelemetryCharger(
            device_id=99, station_id=1,
            timestamp=now - timedelta(minutes=1), charger_power=10.0,
        ))
        db.commit()

        # 不抛; 默认 30kW 阈值下 50kW 突变触发
        created = check_abnormal_charging(ENT_A)
        assert len(created) == 1


# ═══════════════════════════════════════════════════════════════
# C. uq_fleet_alert_active 部分唯一索引
# ═══════════════════════════════════════════════════════════════

class TestActiveUniqueIndex:
    def test_second_active_same_rule_vehicle_blocked(self, test_db):
        db = test_db["session"]
        rule = _make_rule(db, ENT_A, AlertRuleType.LOW_BATTERY)
        v = _make_vehicle(db, ENT_A, plate="京B60006", vin="VINSCAN00000006")

        db.add(FleetAlertRecord(
            rule_id=rule.id, enterprise_id=ENT_A, vehicle_id=v.id,
            status=AlertRecordStatus.ACTIVE,
        ))
        db.commit()

        with pytest.raises(sa.exc.IntegrityError):
            db.add(FleetAlertRecord(
                rule_id=rule.id, enterprise_id=ENT_A, vehicle_id=v.id,
                status=AlertRecordStatus.ACTIVE,
            ))
            db.commit()
        db.rollback()

    def test_non_active_status_not_blocked(self, test_db):
        db = test_db["session"]
        rule = _make_rule(db, ENT_A, AlertRuleType.LOW_BATTERY)
        v = _make_vehicle(db, ENT_A, plate="京B70007", vin="VINSCAN00000007")

        db.add(FleetAlertRecord(
            rule_id=rule.id, enterprise_id=ENT_A, vehicle_id=v.id,
            status=AlertRecordStatus.ACTIVE,
        ))
        db.commit()
        # RESOLVED 与 ACTIVE 同规则同车可并存 (partial WHERE 只锁 ACTIVE)
        db.add(FleetAlertRecord(
            rule_id=rule.id, enterprise_id=ENT_A, vehicle_id=v.id,
            status=AlertRecordStatus.RESOLVED,
        ))
        db.commit()
        assert db.query(FleetAlertRecord).count() == 2

    def test_check_integrity_error_swallowed_not_raised(self, test_db):
        """commit 撞唯一索引 → 跳过本轮新增返回 [], 不向调用方抛 IntegrityError。"""
        db = test_db["session"]
        rule = _make_rule(db, ENT_A, AlertRuleType.LOW_BATTERY, {"soc_below": 20})
        v = _make_vehicle(db, ENT_A, plate="京B80008", vin="VINSCAN00000008")
        _make_low_soc_queue(db, ENT_A, v.id, soc=0.10)
        db.add(FleetAlertRecord(
            rule_id=rule.id, enterprise_id=ENT_A, vehicle_id=v.id,
            status=AlertRecordStatus.ACTIVE,
        ))
        db.commit()
        db.expire_all()

        # 绕过 service 去重直接撞索引: 删掉 active 记录的查询可见性不可行,
        # 改为模拟 —— monkeypatch _has_active_record 恒 False 让 insert 撞索引
        from unittest.mock import patch
        with patch("app.services.fleet_alert_service._has_active_record", return_value=False):
            created = check_low_battery(ENT_A)
        assert created == []
