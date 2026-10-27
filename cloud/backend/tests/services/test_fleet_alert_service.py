"""
车队告警规则引擎服务(fleet_alert_service)测试 - 覆盖率补强 ≥70%

被测: app/services/fleet_alert_service.py (290 行)
设计: 用 test_db 真 SQLite 走三类检测全链路。
覆盖:
- _open_session             db 传入复用 / None 新建(延迟 import SessionLocal)
- _get_enabled_rule         第一条启用规则 / enable=False / 类型不匹配 / id 排序
- _has_active_record        active 去重 / vehicle_id falsy / 非 active 状态不计
- _vehicle_plate            取车牌 / vehicle_id falsy / 不存在
- check_low_battery         SOC 阈值 / 按企业聚合 / 去重 / 阈值兜底
- check_abnormal_charging   功率突变 / 相邻采样 / 充电状态+已分配桩过滤 / 去重 / 兜底
- check_overtime_parking    完成超时 / join 企业 / 去重 / 兜底
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from sqlalchemy import update

import pytest

from app.services.fleet_alert_service import (
    DEFAULT_LOW_BATTERY_SOC,
    DEFAULT_POWER_SPIKE_KW,
    DEFAULT_OVERTIME_MINUTES,
    _open_session,
    _get_enabled_rule,
    _has_active_record,
    _vehicle_plate,
    check_low_battery,
    check_abnormal_charging,
    check_overtime_parking,
)
from app.models.fleet_alert_rule import (
    FleetAlertRule,
    FleetAlertRecord,
    AlertRuleType,
    AlertRecordStatus,
)
from app.models.charging_queue import ChargingQueue
from app.models.charging_order import ChargingOrder, OrderStatus
from app.models.enterprise_vehicle import EnterpriseVehicle
from app.models.telemetry_v2 import TelemetryCharger


ENT = 5001  # 任意企业 ID(SQLite FK 不强制, 无需真实 enterprise 行)


# ═══════════════════════════════════════════════════════════════
# helpers
# ═══════════════════════════════════════════════════════════════

_vin_seq = [0]


def _vin():
    _vin_seq[0] += 1
    return f"VINALERT{_vin_seq[0]:06d}"


def make_rule(db, enterprise_id, rule_type, threshold=None, enable=True):
    r = FleetAlertRule(
        enterprise_id=enterprise_id, rule_type=rule_type,
        threshold=threshold if threshold is not None else {},
        notify_channels=[], enable=enable,
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def make_vehicle(db, enterprise_id=ENT, plate="京A00001"):
    v = EnterpriseVehicle(
        enterprise_id=enterprise_id, plate_number=plate, vin=_vin(),
    )
    db.add(v)
    db.commit()
    db.refresh(v)
    return v


def make_queue(db, *, enterprise_id=ENT, vehicle_id=1, current_soc=None,
               status="waiting", assigned_device_id=None, station_id=1):
    q = ChargingQueue(
        station_id=station_id, vehicle_id=vehicle_id, enterprise_id=enterprise_id,
        current_soc=current_soc, status=status, assigned_device_id=assigned_device_id,
    )
    db.add(q)
    db.commit()
    db.refresh(q)
    return q


def make_telemetry(db, device_id, power, ts, station_id=1):
    t = TelemetryCharger(
        device_id=device_id, station_id=station_id,
        timestamp=ts, charger_power=power,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def make_order(db, *, vehicle_id, plate, end_time,
               status=OrderStatus.COMPLETED, station_id=1, device_id=1, order_no="FA-ORD-1"):
    o = ChargingOrder(
        order_no=order_no, station_id=station_id, device_id=device_id,
        vehicle_id=vehicle_id, plate_number=plate,
        order_status=status, end_time=end_time,
    )
    db.add(o)
    db.commit()
    db.refresh(o)
    return o


# ═══════════════════════════════════════════════════════════════
# 1. _open_session
# ═══════════════════════════════════════════════════════════════

class TestOpenSession:

    def test_reuses_passed_db(self, test_db):
        db = test_db["session"]
        session, own = _open_session(db)
        assert session is db
        assert own is False

    def test_creates_new_when_none(self, test_db):
        # test_db fixture 已 override app.core.database.SessionLocal → 新 session 连测试库
        session, own = _open_session(None)
        assert own is True
        assert session is not None
        session.close()


# ═══════════════════════════════════════════════════════════════
# 2. _get_enabled_rule
# ═══════════════════════════════════════════════════════════════

class TestGetEnabledRule:

    def test_returns_first_enabled(self, test_db):
        db = test_db["session"]
        r = make_rule(db, ENT, AlertRuleType.LOW_BATTERY, {"soc_below": 15})
        got = _get_enabled_rule(db, ENT, AlertRuleType.LOW_BATTERY)
        assert got.id == r.id

    def test_disabled_rule_returns_none(self, test_db):
        db = test_db["session"]
        make_rule(db, ENT, AlertRuleType.LOW_BATTERY, enable=False)
        assert _get_enabled_rule(db, ENT, AlertRuleType.LOW_BATTERY) is None

    def test_wrong_type_returns_none(self, test_db):
        db = test_db["session"]
        make_rule(db, ENT, AlertRuleType.LOW_BATTERY)
        assert _get_enabled_rule(db, ENT, AlertRuleType.ABNORMAL_CHARGING) is None

    def test_wrong_enterprise_returns_none(self, test_db):
        db = test_db["session"]
        make_rule(db, ENT, AlertRuleType.LOW_BATTERY)
        assert _get_enabled_rule(db, 99999, AlertRuleType.LOW_BATTERY) is None

    def test_picks_lowest_id_when_multiple(self, test_db):
        db = test_db["session"]
        r1 = make_rule(db, ENT, AlertRuleType.LOW_BATTERY, {"soc_below": 10})
        r2 = make_rule(db, ENT, AlertRuleType.LOW_BATTERY, {"soc_below": 20})
        got = _get_enabled_rule(db, ENT, AlertRuleType.LOW_BATTERY)
        assert got.id == min(r1.id, r2.id)


# ═══════════════════════════════════════════════════════════════
# 3. _has_active_record
# ═══════════════════════════════════════════════════════════════

class TestHasActiveRecord:

    def test_none_vehicle_returns_false(self, test_db):
        db = test_db["session"]
        assert _has_active_record(db, rule_id=1, vehicle_id=None) is False

    def test_zero_vehicle_returns_false(self, test_db):
        db = test_db["session"]
        assert _has_active_record(db, rule_id=1, vehicle_id=0) is False

    def test_active_record_returns_true(self, test_db):
        db = test_db["session"]
        rule = make_rule(db, ENT, AlertRuleType.LOW_BATTERY)
        v = make_vehicle(db, ENT)
        db.add(FleetAlertRecord(
            rule_id=rule.id, enterprise_id=ENT, vehicle_id=v.id,
            status=AlertRecordStatus.ACTIVE,
        ))
        db.commit()
        assert _has_active_record(db, rule.id, v.id) is True

    def test_no_record_returns_false(self, test_db):
        db = test_db["session"]
        rule = make_rule(db, ENT, AlertRuleType.LOW_BATTERY)
        v = make_vehicle(db, ENT)
        assert _has_active_record(db, rule.id, v.id) is False

    def test_resolved_record_not_counted(self, test_db):
        db = test_db["session"]
        rule = make_rule(db, ENT, AlertRuleType.LOW_BATTERY)
        v = make_vehicle(db, ENT)
        db.add(FleetAlertRecord(
            rule_id=rule.id, enterprise_id=ENT, vehicle_id=v.id,
            status=AlertRecordStatus.RESOLVED,
        ))
        db.commit()
        # RESOLVED 不算 active → 可再次告警
        assert _has_active_record(db, rule.id, v.id) is False


# ═══════════════════════════════════════════════════════════════
# 4. _vehicle_plate
# ═══════════════════════════════════════════════════════════════

class TestVehiclePlate:

    def test_none_vehicle_returns_none(self, test_db):
        db = test_db["session"]
        assert _vehicle_plate(db, None) is None

    def test_zero_vehicle_returns_none(self, test_db):
        db = test_db["session"]
        assert _vehicle_plate(db, 0) is None

    def test_returns_plate(self, test_db):
        db = test_db["session"]
        v = make_vehicle(db, ENT, plate="京B88888")
        assert _vehicle_plate(db, v.id) == "京B88888"

    def test_missing_vehicle_returns_none(self, test_db):
        db = test_db["session"]
        assert _vehicle_plate(db, 999999) is None


# ═══════════════════════════════════════════════════════════════
# 5. check_low_battery
# ═══════════════════════════════════════════════════════════════

class TestCheckLowBattery:

    def test_no_rule_returns_empty(self, test_db):
        db = test_db["session"]
        v = make_vehicle(db, ENT)
        make_queue(db, vehicle_id=v.id, current_soc=0.1)
        assert check_low_battery(ENT, db=db) == []

    def test_disabled_rule_returns_empty(self, test_db):
        db = test_db["session"]
        make_rule(db, ENT, AlertRuleType.LOW_BATTERY, enable=False)
        v = make_vehicle(db, ENT)
        make_queue(db, vehicle_id=v.id, current_soc=0.1)
        assert check_low_battery(ENT, db=db) == []

    def test_low_soc_triggers_alert(self, test_db):
        db = test_db["session"]
        rule = make_rule(db, ENT, AlertRuleType.LOW_BATTERY, {"soc_below": 20})
        v = make_vehicle(db, ENT, plate="京C11111")
        # SOC 10% < 20% 阈值
        make_queue(db, vehicle_id=v.id, current_soc=0.1)
        created = check_low_battery(ENT, db=db)
        assert len(created) == 1
        rec = created[0]
        assert rec.rule_id == rule.id
        assert rec.enterprise_id == ENT
        assert rec.vehicle_id == v.id
        assert rec.plate_number == "京C11111"
        assert rec.status == AlertRecordStatus.ACTIVE
        assert rec.notified is False
        assert rec.alert_value == "soc=10.0%"

    def test_high_soc_no_alert(self, test_db):
        db = test_db["session"]
        make_rule(db, ENT, AlertRuleType.LOW_BATTERY, {"soc_below": 20})
        v = make_vehicle(db, ENT)
        # SOC 80% 高于阈值
        make_queue(db, vehicle_id=v.id, current_soc=0.8)
        assert check_low_battery(ENT, db=db) == []

    def test_null_soc_not_queried(self, test_db):
        db = test_db["session"]
        make_rule(db, ENT, AlertRuleType.LOW_BATTERY, {"soc_below": 20})
        v = make_vehicle(db, ENT)
        q = make_queue(db, vehicle_id=v.id, current_soc=0.5)
        # 强制 current_soc = NULL: 模型 default=0.0 会把 ORM 层 None 转成 0.0, 故走 SQL update
        db.execute(update(ChargingQueue).where(ChargingQueue.id == q.id).values(current_soc=None))
        db.commit()
        assert check_low_battery(ENT, db=db) == []

    def test_default_threshold_when_missing(self, test_db):
        db = test_db["session"]
        # threshold 空 → 用 DEFAULT_LOW_BATTERY_SOC=20
        make_rule(db, ENT, AlertRuleType.LOW_BATTERY, {})
        v = make_vehicle(db, ENT)
        # SOC 18% < 默认 20% → 触发
        make_queue(db, vehicle_id=v.id, current_soc=0.18)
        created = check_low_battery(ENT, db=db)
        assert len(created) == 1
        assert created[0].alert_value == "soc=18.0%"
        # 边界: SOC 恰好 20% 不触发(严格小于)
        v2 = make_vehicle(db, ENT)
        make_queue(db, vehicle_id=v2.id, current_soc=0.20)
        assert check_low_battery(ENT, db=db) == []

    def test_dedup_skips_existing_active(self, test_db):
        db = test_db["session"]
        rule = make_rule(db, ENT, AlertRuleType.LOW_BATTERY, {"soc_below": 20})
        v = make_vehicle(db, ENT)
        make_queue(db, vehicle_id=v.id, current_soc=0.1)
        # 预置 active 记录 → 跳过
        db.add(FleetAlertRecord(
            rule_id=rule.id, enterprise_id=ENT, vehicle_id=v.id,
            status=AlertRecordStatus.ACTIVE,
        ))
        db.commit()
        assert check_low_battery(ENT, db=db) == []

    def test_multiple_vehicles_partial_dedup(self, test_db):
        db = test_db["session"]
        rule = make_rule(db, ENT, AlertRuleType.LOW_BATTERY, {"soc_below": 20})
        v1 = make_vehicle(db, ENT)
        v2 = make_vehicle(db, ENT)
        make_queue(db, vehicle_id=v1.id, current_soc=0.1)
        make_queue(db, vehicle_id=v2.id, current_soc=0.05)
        # v1 已有 active → 仅 v2 生成新记录
        db.add(FleetAlertRecord(
            rule_id=rule.id, enterprise_id=ENT, vehicle_id=v1.id,
            status=AlertRecordStatus.ACTIVE,
        ))
        db.commit()
        created = check_low_battery(ENT, db=db)
        assert len(created) == 1
        assert created[0].vehicle_id == v2.id

    def test_enterprise_isolation(self, test_db):
        db = test_db["session"]
        make_rule(db, ENT, AlertRuleType.LOW_BATTERY, {"soc_below": 20})
        make_rule(db, 5002, AlertRuleType.LOW_BATTERY, {"soc_below": 20})
        v_mine = make_vehicle(db, ENT)
        v_other = make_vehicle(db, 5002)
        make_queue(db, enterprise_id=ENT, vehicle_id=v_mine.id, current_soc=0.1)
        make_queue(db, enterprise_id=5002, vehicle_id=v_other.id, current_soc=0.1)
        created = check_low_battery(ENT, db=db)
        # 仅本企业车辆告警
        assert all(r.enterprise_id == ENT for r in created)
        assert all(r.vehicle_id == v_mine.id for r in created)

    def test_works_with_internal_session(self, test_db):
        # db=None → _open_session 新建 session(连测试库), finally 自动 close
        db = test_db["session"]
        rule = make_rule(db, ENT, AlertRuleType.LOW_BATTERY, {"soc_below": 20})
        v = make_vehicle(db, ENT)
        make_queue(db, vehicle_id=v.id, current_soc=0.1)
        created = check_low_battery(ENT, db=None)
        assert len(created) == 1
        # 记录已落库(同库可见)
        assert db.query(FleetAlertRecord).filter(
            FleetAlertRecord.rule_id == rule.id).count() == 1


# ═══════════════════════════════════════════════════════════════
# 6. check_abnormal_charging
# ═══════════════════════════════════════════════════════════════

class TestCheckAbnormalCharging:
    """卡 c7671386: 种子已对齐 ChargingOrder 数据源(卡 6a1bdff2 切换后的实现)。

    旧种子用 make_queue(status=charging, assigned_device_id=77), 但新实现查
    ChargingOrder(order_status=CHARGING).join(EnterpriseVehicle), 旧种子导致
    查询恒空 → 4 failed + 6 假通过。
    """

    def test_no_rule_returns_empty(self, test_db):
        db = test_db["session"]
        v = make_vehicle(db, ENT)
        make_order(db, vehicle_id=v.id, plate="京D10000",
                   status=OrderStatus.CHARGING, device_id=77,
                   end_time=None, order_no="AC-0")
        assert check_abnormal_charging(ENT, db=db) == []

    def test_power_spike_triggers(self, test_db):
        db = test_db["session"]
        rule = make_rule(db, ENT, AlertRuleType.ABNORMAL_CHARGING, {"power_spike_kw": 30})
        v = make_vehicle(db, ENT, plate="京D22222")
        make_order(db, vehicle_id=v.id, plate="京D22222",
                   status=OrderStatus.CHARGING, device_id=77,
                   end_time=None, order_no="AC-1")
        base = datetime(2026, 8, 2, 10, 0)
        make_telemetry(db, 77, power=10.0, ts=base)                            # 旧
        make_telemetry(db, 77, power=60.0, ts=base + timedelta(minutes=1))     # 新
        created = check_abnormal_charging(ENT, db=db)
        assert len(created) == 1
        rec = created[0]
        assert rec.vehicle_id == v.id
        assert rec.plate_number == "京D22222"
        # |60 - 10| = 50.0
        assert rec.alert_value == "power_spike=50.0kW"
        assert rec.status == AlertRecordStatus.ACTIVE

    def test_small_diff_no_alert(self, test_db):
        db = test_db["session"]
        make_rule(db, ENT, AlertRuleType.ABNORMAL_CHARGING, {"power_spike_kw": 30})
        v = make_vehicle(db, ENT)
        make_order(db, vehicle_id=v.id, plate="京D20000",
                   status=OrderStatus.CHARGING, device_id=77,
                   end_time=None, order_no="AC-2")
        base = datetime(2026, 8, 2, 10, 0)
        make_telemetry(db, 77, power=10.0, ts=base)
        make_telemetry(db, 77, power=15.0, ts=base + timedelta(minutes=1))  # diff 5 < 30
        assert check_abnormal_charging(ENT, db=db) == []

    def test_insufficient_samples_no_alert(self, test_db):
        db = test_db["session"]
        make_rule(db, ENT, AlertRuleType.ABNORMAL_CHARGING, {"power_spike_kw": 30})
        v = make_vehicle(db, ENT)
        make_order(db, vehicle_id=v.id, plate="京D20001",
                   status=OrderStatus.CHARGING, device_id=77,
                   end_time=None, order_no="AC-3")
        base = datetime(2026, 8, 2, 10, 0)
        make_telemetry(db, 77, power=10.0, ts=base)  # 仅 1 条
        assert check_abnormal_charging(ENT, db=db) == []

    def test_default_threshold_when_missing(self, test_db):
        db = test_db["session"]
        # threshold 空 → DEFAULT_POWER_SPIKE_KW=30.0
        make_rule(db, ENT, AlertRuleType.ABNORMAL_CHARGING, {})
        v = make_vehicle(db, ENT)
        make_order(db, vehicle_id=v.id, plate="京D20002",
                   status=OrderStatus.CHARGING, device_id=77,
                   end_time=None, order_no="AC-4")
        base = datetime(2026, 8, 2, 10, 0)
        make_telemetry(db, 77, power=0.0, ts=base)
        make_telemetry(db, 77, power=40.0, ts=base + timedelta(minutes=1))  # diff 40 > 30
        created = check_abnormal_charging(ENT, db=db)
        assert len(created) == 1
        assert created[0].alert_value == "power_spike=40.0kW"

    def test_skips_non_charging_order(self, test_db):
        db = test_db["session"]
        make_rule(db, ENT, AlertRuleType.ABNORMAL_CHARGING, {"power_spike_kw": 30})
        v = make_vehicle(db, ENT)
        # order_status=COMPLETED → 不在 CHARGING 查询范围
        make_order(db, vehicle_id=v.id, plate="京D20003",
                   status=OrderStatus.COMPLETED, device_id=77,
                   end_time=datetime.now(timezone.utc), order_no="AC-5")
        base = datetime(2026, 8, 2, 10, 0)
        make_telemetry(db, 77, power=10.0, ts=base)
        make_telemetry(db, 77, power=60.0, ts=base + timedelta(minutes=1))
        assert check_abnormal_charging(ENT, db=db) == []

    def test_no_telemetry_device_no_alert(self, test_db):
        db = test_db["session"]
        make_rule(db, ENT, AlertRuleType.ABNORMAL_CHARGING, {"power_spike_kw": 30})
        v = make_vehicle(db, ENT)
        # 订单指向 device_id=88(无任何遥测采样) → 不触发
        # (原 test_skips_unassigned_queue 的语义在新链路无等价态: device_id 为
        #  ChargingOrder 必填列, 不存在"未分配"订单, 改测遥测缺失分支)
        make_order(db, vehicle_id=v.id, plate="京D20004",
                   status=OrderStatus.CHARGING, device_id=88,
                   end_time=None, order_no="AC-6")
        assert check_abnormal_charging(ENT, db=db) == []

    def test_dedup_skips_existing_active(self, test_db):
        db = test_db["session"]
        rule = make_rule(db, ENT, AlertRuleType.ABNORMAL_CHARGING, {"power_spike_kw": 30})
        v = make_vehicle(db, ENT)
        make_order(db, vehicle_id=v.id, plate="京D20005",
                   status=OrderStatus.CHARGING, device_id=77,
                   end_time=None, order_no="AC-7")
        base = datetime(2026, 8, 2, 10, 0)
        make_telemetry(db, 77, power=10.0, ts=base)
        make_telemetry(db, 77, power=60.0, ts=base + timedelta(minutes=1))
        db.add(FleetAlertRecord(
            rule_id=rule.id, enterprise_id=ENT, vehicle_id=v.id,
            status=AlertRecordStatus.ACTIVE,
        ))
        db.commit()
        assert check_abnormal_charging(ENT, db=db) == []

    def test_null_power_treated_as_zero(self, test_db):
        db = test_db["session"]
        make_rule(db, ENT, AlertRuleType.ABNORMAL_CHARGING, {"power_spike_kw": 30})
        v = make_vehicle(db, ENT)
        make_order(db, vehicle_id=v.id, plate="京D20006",
                   status=OrderStatus.CHARGING, device_id=77,
                   end_time=None, order_no="AC-8")
        base = datetime(2026, 8, 2, 10, 0)
        make_telemetry(db, 77, power=None, ts=base)                        # None → 0
        make_telemetry(db, 77, power=40.0, ts=base + timedelta(minutes=1))
        created = check_abnormal_charging(ENT, db=db)
        assert len(created) == 1
        assert created[0].alert_value == "power_spike=40.0kW"

    def test_works_with_internal_session(self, test_db):
        # db=None → _open_session 新建 session(连测试库), finally 自动 close
        db = test_db["session"]
        rule = make_rule(db, ENT, AlertRuleType.ABNORMAL_CHARGING, {"power_spike_kw": 30})
        v = make_vehicle(db, ENT)
        make_order(db, vehicle_id=v.id, plate="京D20007",
                   status=OrderStatus.CHARGING, device_id=77,
                   end_time=None, order_no="AC-9")
        base = datetime(2026, 8, 2, 10, 0)
        make_telemetry(db, 77, power=10.0, ts=base)
        make_telemetry(db, 77, power=60.0, ts=base + timedelta(minutes=1))
        created = check_abnormal_charging(ENT, db=None)
        assert len(created) == 1
        assert db.query(FleetAlertRecord).filter(
            FleetAlertRecord.rule_id == rule.id).count() == 1


# 7. check_overtime_parking
# ═══════════════════════════════════════════════════════════════

class TestCheckOvertimeParking:

    def test_no_rule_returns_empty(self, test_db):
        db = test_db["session"]
        v = make_vehicle(db, ENT)
        make_order(db, vehicle_id=v.id, plate="京E33333",
                   end_time=datetime.now(timezone.utc) - timedelta(hours=5))
        assert check_overtime_parking(ENT, db=db) == []

    def test_overtime_triggers(self, test_db):
        db = test_db["session"]
        rule = make_rule(db, ENT, AlertRuleType.OVERTIME_PARKING, {"minutes": 120})
        v = make_vehicle(db, ENT)
        # end_time 5 小时前 → 超 120 分钟
        make_order(db, vehicle_id=v.id, plate="京E33333",
                   end_time=datetime.now(timezone.utc) - timedelta(hours=5), order_no="OT-1")
        created = check_overtime_parking(ENT, db=db)
        assert len(created) == 1
        rec = created[0]
        assert rec.rule_id == rule.id
        assert rec.vehicle_id == v.id
        assert rec.plate_number == "京E33333"
        assert rec.status == AlertRecordStatus.ACTIVE
        assert rec.alert_value.startswith("parked=")
        assert rec.alert_value.endswith("min")

    def test_uncompleted_order_no_alert(self, test_db):
        db = test_db["session"]
        make_rule(db, ENT, AlertRuleType.OVERTIME_PARKING, {"minutes": 120})
        v = make_vehicle(db, ENT)
        make_order(db, vehicle_id=v.id, plate="京E33334",
                   end_time=datetime.now(timezone.utc) - timedelta(hours=5),
                   status=OrderStatus.CHARGING, order_no="OT-2")
        assert check_overtime_parking(ENT, db=db) == []

    def test_completed_within_threshold_no_alert(self, test_db):
        db = test_db["session"]
        make_rule(db, ENT, AlertRuleType.OVERTIME_PARKING, {"minutes": 120})
        v = make_vehicle(db, ENT)
        # end_time 30 分钟前 → 未超 120 分钟
        make_order(db, vehicle_id=v.id, plate="京E33335",
                   end_time=datetime.now(timezone.utc) - timedelta(minutes=30), order_no="OT-3")
        assert check_overtime_parking(ENT, db=db) == []

    def test_null_end_time_no_alert(self, test_db):
        db = test_db["session"]
        make_rule(db, ENT, AlertRuleType.OVERTIME_PARKING, {"minutes": 120})
        v = make_vehicle(db, ENT)
        o = ChargingOrder(
            order_no="OT-4", station_id=1, device_id=1,
            vehicle_id=v.id, plate_number="京E33336",
            order_status=OrderStatus.COMPLETED, end_time=None,
        )
        db.add(o)
        db.commit()
        assert check_overtime_parking(ENT, db=db) == []

    def test_default_threshold_when_missing(self, test_db):
        db = test_db["session"]
        # threshold 空 → DEFAULT_OVERTIME_MINUTES=120
        make_rule(db, ENT, AlertRuleType.OVERTIME_PARKING, {})
        v = make_vehicle(db, ENT)
        # end_time 130 分钟前 → 超 120 默认阈值
        make_order(db, vehicle_id=v.id, plate="京E33337",
                   end_time=datetime.now(timezone.utc) - timedelta(minutes=130), order_no="OT-5")
        created = check_overtime_parking(ENT, db=db)
        assert len(created) == 1

    def test_dedup_skips_existing_active(self, test_db):
        db = test_db["session"]
        rule = make_rule(db, ENT, AlertRuleType.OVERTIME_PARKING, {"minutes": 120})
        v = make_vehicle(db, ENT)
        make_order(db, vehicle_id=v.id, plate="京E33338",
                   end_time=datetime.now(timezone.utc) - timedelta(hours=5), order_no="OT-6")
        db.add(FleetAlertRecord(
            rule_id=rule.id, enterprise_id=ENT, vehicle_id=v.id,
            status=AlertRecordStatus.ACTIVE,
        ))
        db.commit()
        assert check_overtime_parking(ENT, db=db) == []

    def test_enterprise_isolation_via_join(self, test_db):
        db = test_db["session"]
        make_rule(db, ENT, AlertRuleType.OVERTIME_PARKING, {"minutes": 120})
        make_rule(db, 5002, AlertRuleType.OVERTIME_PARKING, {"minutes": 120})
        v_mine = make_vehicle(db, ENT)
        v_other = make_vehicle(db, 5002)
        make_order(db, vehicle_id=v_mine.id, plate="MINE",
                   end_time=datetime.now(timezone.utc) - timedelta(hours=5), order_no="OT-7")
        make_order(db, vehicle_id=v_other.id, plate="OTHER",
                   end_time=datetime.now(timezone.utc) - timedelta(hours=5), order_no="OT-8")
        created = check_overtime_parking(ENT, db=db)
        # join 仅命中本企业车辆
        assert all(r.enterprise_id == ENT for r in created)
        assert all(r.vehicle_id == v_mine.id for r in created)

    def test_works_with_internal_session(self, test_db):
        # db=None → _open_session 新建, finally close
        db = test_db["session"]
        rule = make_rule(db, ENT, AlertRuleType.OVERTIME_PARKING, {"minutes": 120})
        v = make_vehicle(db, ENT)
        make_order(db, vehicle_id=v.id, plate="京E33339",
                   end_time=datetime.now(timezone.utc) - timedelta(hours=5), order_no="OT-9")
        created = check_overtime_parking(ENT, db=None)
        assert len(created) == 1
        assert db.query(FleetAlertRecord).filter(
            FleetAlertRecord.rule_id == rule.id).count() == 1


# 默认阈值常量存在性回归(防误删)
def test_default_threshold_constants():
    assert DEFAULT_LOW_BATTERY_SOC == 20
    assert DEFAULT_POWER_SPIKE_KW == 30.0
    assert DEFAULT_OVERTIME_MINUTES == 120


# ═══════════════════════════════════════════════════════════════
# 8. commit 异常 rollback 保护
# ═══════════════════════════════════════════════════════════════

class TestCommitRollbackProtection:
    """commit() 失败必须 rollback —— 防脏事务残留连接池, 异常向上传播。

    用 MagicMock session 隔离真实 DB: rule 存在 + queues/orders 空 → created 空 → 直达 commit。
    """

    @staticmethod
    def _session_with_rule():
        """mock session: _get_enabled_rule 命中(query.first→rule), 候选集空(query.all→[])。

        check_* 三函数共享 query 链: .first() 配在 order_by 节点, .all() 配在 filter 节点,
        两者不冲突。
        """
        session = MagicMock()
        rule = MagicMock()
        rule.id = 1
        rule.threshold = {}  # 空 → 走默认阈值
        session.query.return_value.filter.return_value.order_by.return_value.first.return_value = rule
        session.query.return_value.filter.return_value.all.return_value = []
        return session

    def test_check_low_battery_rollback_on_commit_error(self):
        session = self._session_with_rule()
        session.commit.side_effect = RuntimeError("db boom")

        with pytest.raises(RuntimeError):
            check_low_battery(ENT, db=session)

        session.commit.assert_called_once()
        session.rollback.assert_called_once()

    def test_check_abnormal_charging_rollback_on_commit_error(self):
        session = self._session_with_rule()
        session.commit.side_effect = RuntimeError("db boom")

        with pytest.raises(RuntimeError):
            check_abnormal_charging(ENT, db=session)

        session.commit.assert_called_once()
        session.rollback.assert_called_once()

    def test_check_overtime_parking_rollback_on_commit_error(self):
        session = self._session_with_rule()
        session.commit.side_effect = RuntimeError("db boom")

        with pytest.raises(RuntimeError):
            check_overtime_parking(ENT, db=session)

        session.commit.assert_called_once()
        session.rollback.assert_called_once()
