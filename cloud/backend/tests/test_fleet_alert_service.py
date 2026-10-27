"""
车队告警规则引擎服务单元测试 - app/services/fleet_alert_service.py

用 MagicMock 隔离 DB: session.query(Model) 经 side_effect 按模型分派,
.filter/.order_by/.limit/.join 链式返回自身, .all/.first 返回预设结果。
直接测三类检测(check_low_battery / check_abnormal_charging / check_overtime_parking)
的正常路径 + 去重 + 默认阈值 + 无规则短路 + 自有 session 关闭。
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import app.services.fleet_alert_service as fas
from app.models.fleet_alert_rule import (
    AlertRuleType,
    AlertRecordStatus,
    FleetAlertRecord,
)


# ======================================================================
# Mock 工具
# ======================================================================

def _mock_session(queries):
    """构造 MagicMock session。

    queries: {ModelClass: result_list}
      session.query(Model).<filter|order_by|limit|join>*().all()  -> result_list
      session.query(Model).<...>().first()                         -> result_list[0] or None
    """
    session = MagicMock()

    def _query(model, *args, **kwargs):
        q = MagicMock()
        result = queries.get(model, [])
        q.filter.return_value = q
        q.order_by.return_value = q
        q.limit.return_value = q
        q.join.return_value = q
        q.all.return_value = result
        q.first.return_value = result[0] if result else None
        return q

    session.query.side_effect = _query
    return session


def _rule(rule_type, threshold=None, rule_id=1):
    """构造启用规则对象。"""
    return SimpleNamespace(
        id=rule_id,
        rule_type=rule_type,
        threshold=threshold,
        enable=True,
    )


def _created_records(session):
    """从 session.add 调用中提取被 add 的 FleetAlertRecord 列表。"""
    return [call.args[0] for call in session.add.call_args_list]


# ======================================================================
# check_low_battery
# ======================================================================

def test_check_low_battery_no_rule_returns_empty():
    """无启用规则立即返回空, 不查队列、不 commit。"""
    session = _mock_session({})  # FleetAlertRule -> [] -> first() None
    result = fas.check_low_battery(10, db=session)
    assert result == []
    session.commit.assert_not_called()


def test_check_low_battery_no_low_soc_queues():
    """有规则但无低于阈值的队列 -> 空。"""
    session = _mock_session({
        fas.FleetAlertRule: [_rule(AlertRuleType.LOW_BATTERY, {"soc_below": 20})],
        fas.ChargingQueue: [],
    })
    assert fas.check_low_battery(10, db=session) == []


def test_check_low_battery_creates_records():
    """低于阈值的车辆生成告警, alert_value 格式 soc=XX.X%。"""
    queues = [
        SimpleNamespace(vehicle_id=101, current_soc=0.15),   # 15%
        SimpleNamespace(vehicle_id=102, current_soc=0.05),   # 5%
    ]
    session = _mock_session({
        fas.FleetAlertRule: [_rule(AlertRuleType.LOW_BATTERY, {"soc_below": 20})],
        fas.ChargingQueue: queues,
        fas.FleetAlertRecord: [],          # 无活跃记录 -> 不去重
        fas.EnterpriseVehicle: [],         # _vehicle_plate -> None
    })
    result = fas.check_low_battery(10, db=session)

    assert len(result) == 2
    session.commit.assert_called_once()
    session.refresh.call_count == 2
    recs = _created_records(session)
    assert {r.vehicle_id for r in recs} == {101, 102}
    assert all(r.enterprise_id == 10 for r in recs)
    assert all(r.status == AlertRecordStatus.ACTIVE for r in recs)
    values = sorted(r.alert_value for r in recs)
    assert values == ["soc=15.0%", "soc=5.0%"]


def test_check_low_battery_default_threshold_when_missing():
    """规则 threshold=None 时兜底 DEFAULT_LOW_BATTERY_SOC=20。"""
    # soc 0.19(19%) < 20 触发; 用 0.19 验证默认阈值生效
    queues = [SimpleNamespace(vehicle_id=1, current_soc=0.19)]
    session = _mock_session({
        fas.FleetAlertRule: [_rule(AlertRuleType.LOW_BATTERY, None)],
        fas.ChargingQueue: queues,
        fas.FleetAlertRecord: [],
        fas.EnterpriseVehicle: [],
    })
    result = fas.check_low_battery(10, db=session)
    assert len(result) == 1
    assert result[0].alert_value == "soc=19.0%"


def test_check_low_battery_skips_when_active_record_exists():
    """同一车辆已有 active 记录 -> 去重, 不重复生成。"""
    queues = [SimpleNamespace(vehicle_id=1, current_soc=0.10)]
    session = _mock_session({
        fas.FleetAlertRule: [_rule(AlertRuleType.LOW_BATTERY, {"soc_below": 20})],
        fas.ChargingQueue: queues,
        fas.FleetAlertRecord: [MagicMock()],   # _has_active_record -> True
        fas.EnterpriseVehicle: [],
    })
    assert fas.check_low_battery(10, db=session) == []
    session.add.assert_not_called()


def test_check_low_battery_uses_plate_from_vehicle():
    """_vehicle_plate 命中时记录写入车牌号。"""
    queues = [SimpleNamespace(vehicle_id=7, current_soc=0.10)]
    session = _mock_session({
        fas.FleetAlertRule: [_rule(AlertRuleType.LOW_BATTERY, {"soc_below": 20})],
        fas.ChargingQueue: queues,
        fas.FleetAlertRecord: [],
        fas.EnterpriseVehicle: [SimpleNamespace(plate_number="京A12345")],
    })
    result = fas.check_low_battery(10, db=session)
    assert result[0].plate_number == "京A12345"


def test_check_low_battery_opens_and_closes_own_session(monkeypatch):
    """db=None 时内部经 SessionLocal 新建 session 并在 finally 关闭。"""
    fake_session = _mock_session({})   # 无规则 -> 提前 return []
    fake_local = MagicMock(return_value=fake_session)
    monkeypatch.setattr("app.core.database.SessionLocal", fake_local)

    assert fas.check_low_battery(10, db=None) == []
    fake_local.assert_called_once()
    fake_session.close.assert_called_once()


def test_check_low_battery_does_not_close_passed_session():
    """传入 db 时 own=False, 不关闭(由调用方负责)。"""
    session = _mock_session({})  # 无规则
    fas.check_low_battery(10, db=session)
    session.close.assert_not_called()


# ======================================================================
# check_abnormal_charging
# 卡 6a1bdff2: ChargingQueue.assigned_device_id 全仓零写入 + status=charging 零赋值,
# 旧查询永远空 -> 数据源切换为 ChargingOrder(order_status=CHARGING, vehicle_id 关联企业)
# ======================================================================

def _order(vehicle_id=1, device_id=99, plate_number=None):
    return SimpleNamespace(vehicle_id=vehicle_id, device_id=device_id, plate_number=plate_number)


def test_check_abnormal_charging_no_rule_returns_empty():
    session = _mock_session({})
    assert fas.check_abnormal_charging(10, db=session) == []
    session.commit.assert_not_called()


def test_check_abnormal_charging_single_sample_skipped():
    """不足两条采样无法算突变 -> 跳过。"""
    session = _mock_session({
        fas.FleetAlertRule: [_rule(AlertRuleType.ABNORMAL_CHARGING, {"power_spike_kw": 30})],
        fas.ChargingOrder: [_order()],
        fas.TelemetryCharger: [SimpleNamespace(charger_power=50.0)],   # 仅 1 条
        fas.FleetAlertRecord: [],
        fas.EnterpriseVehicle: [],
    })
    assert fas.check_abnormal_charging(10, db=session) == []


def test_check_abnormal_charging_diff_below_threshold_skipped():
    """功率差值 < 阈值 -> 不算异常。"""
    session = _mock_session({
        fas.FleetAlertRule: [_rule(AlertRuleType.ABNORMAL_CHARGING, {"power_spike_kw": 30})],
        fas.ChargingOrder: [_order()],
        fas.TelemetryCharger: [
            SimpleNamespace(charger_power=39.9),
            SimpleNamespace(charger_power=10.0),
        ],   # diff=29.9 < 30
        fas.FleetAlertRecord: [],
        fas.EnterpriseVehicle: [],
    })
    assert fas.check_abnormal_charging(10, db=session) == []


def test_check_abnormal_charging_creates_record_at_boundary():
    """功率差值 == 阈值(>=) 触发告警, alert_value 格式 power_spike=XX.XkW。"""
    session = _mock_session({
        fas.FleetAlertRule: [_rule(AlertRuleType.ABNORMAL_CHARGING, {"power_spike_kw": 30})],
        fas.ChargingOrder: [_order(vehicle_id=1, device_id=99, plate_number="京B66666")],
        fas.TelemetryCharger: [
            SimpleNamespace(charger_power=40.0),
            SimpleNamespace(charger_power=10.0),
        ],   # diff=30.0 >= 30
        fas.FleetAlertRecord: [],
        fas.EnterpriseVehicle: [],
    })
    result = fas.check_abnormal_charging(10, db=session)
    assert len(result) == 1
    assert result[0].alert_value == "power_spike=30.0kW"
    assert result[0].vehicle_id == 1
    assert result[0].plate_number == "京B66666"
    session.commit.assert_called_once()


def test_check_abnormal_charging_default_threshold_when_missing():
    """规则 threshold=None 兜底 DEFAULT_POWER_SPIKE_KW=30。"""
    session = _mock_session({
        fas.FleetAlertRule: [_rule(AlertRuleType.ABNORMAL_CHARGING, None)],
        fas.ChargingOrder: [_order()],
        fas.TelemetryCharger: [
            SimpleNamespace(charger_power=80.0),
            SimpleNamespace(charger_power=10.0),
        ],   # diff=70 >= 默认 30
        fas.FleetAlertRecord: [],
        fas.EnterpriseVehicle: [],
    })
    assert len(fas.check_abnormal_charging(10, db=session)) == 1


def test_check_abnormal_charging_skips_when_active_record_exists():
    """已有 active 记录 -> 去重。"""
    session = _mock_session({
        fas.FleetAlertRule: [_rule(AlertRuleType.ABNORMAL_CHARGING, {"power_spike_kw": 30})],
        fas.ChargingOrder: [_order()],
        fas.TelemetryCharger: [
            SimpleNamespace(charger_power=100.0),
            SimpleNamespace(charger_power=10.0),
        ],
        fas.FleetAlertRecord: [MagicMock()],   # 去重
        fas.EnterpriseVehicle: [],
    })
    assert fas.check_abnormal_charging(10, db=session) == []
    session.add.assert_not_called()


def test_check_abnormal_charging_no_active_orders_returns_empty():
    """无在充订单 -> 空。"""
    session = _mock_session({
        fas.FleetAlertRule: [_rule(AlertRuleType.ABNORMAL_CHARGING, {"power_spike_kw": 30})],
        fas.ChargingOrder: [],
    })
    assert fas.check_abnormal_charging(10, db=session) == []


def test_check_abnormal_charging_multiple_vehicles_independent():
    """多台在充车辆各自独立按其 device_id 的采样判定。"""
    session = _mock_session({
        fas.FleetAlertRule: [_rule(AlertRuleType.ABNORMAL_CHARGING, {"power_spike_kw": 30})],
        fas.ChargingOrder: [_order(vehicle_id=1, device_id=99), _order(vehicle_id=2, device_id=100)],
        fas.TelemetryCharger: [
            SimpleNamespace(charger_power=40.0),
            SimpleNamespace(charger_power=10.0),
        ],
        fas.FleetAlertRecord: [],
        fas.EnterpriseVehicle: [],
    })
    result = fas.check_abnormal_charging(10, db=session)
    assert {r.vehicle_id for r in result} == {1, 2}


# ======================================================================
# check_overtime_parking
# ======================================================================

class _FixedDateTime(datetime):
    """固定 utcnow, 让 parked_minutes 可精确断言。"""
    _fixed = datetime(2026, 1, 1, 12, 0, 0)

    @classmethod
    def utcnow(cls):
        return cls._fixed

    @classmethod
    def now(cls, tz=None):
        # 模拟 datetime.now(timezone.utc): 返回 aware _fixed, 与源码 now(timezone.utc) 一致
        return cls._fixed.replace(tzinfo=timezone.utc)


def test_check_overtime_parking_no_rule_returns_empty():
    session = _mock_session({})
    assert fas.check_overtime_parking(10, db=session) == []
    session.commit.assert_not_called()


def test_check_overtime_parking_no_orders_returns_empty():
    session = _mock_session({
        fas.FleetAlertRule: [_rule(AlertRuleType.OVERTIME_PARKING, {"minutes": 120})],
        fas.ChargingOrder: [],
    })
    assert fas.check_overtime_parking(10, db=session) == []


def test_check_overtime_parking_creates_record(monkeypatch):
    """充满后占桩超时 -> 告警, alert_value 含 parked 分钟数。"""
    monkeypatch.setattr(fas, "datetime", _FixedDateTime)
    end_time = _FixedDateTime._fixed - timedelta(minutes=200)
    orders = [SimpleNamespace(vehicle_id=5, end_time=end_time, plate_number="沪B888")]
    session = _mock_session({
        fas.FleetAlertRule: [_rule(AlertRuleType.OVERTIME_PARKING, {"minutes": 120})],
        fas.ChargingOrder: orders,
        fas.FleetAlertRecord: [],
    })
    result = fas.check_overtime_parking(10, db=session)
    assert len(result) == 1
    assert result[0].alert_value == "parked=200min"
    assert result[0].plate_number == "沪B888"
    assert result[0].vehicle_id == 5
    session.commit.assert_called_once()


def test_check_overtime_parking_default_minutes_when_missing(monkeypatch):
    """规则 threshold=None 兜底 DEFAULT_OVERTIME_MINUTES=120。"""
    monkeypatch.setattr(fas, "datetime", _FixedDateTime)
    end_time = _FixedDateTime._fixed - timedelta(minutes=150)   # > 默认 120
    orders = [SimpleNamespace(vehicle_id=5, end_time=end_time, plate_number="沪B888")]
    session = _mock_session({
        fas.FleetAlertRule: [_rule(AlertRuleType.OVERTIME_PARKING, None)],
        fas.ChargingOrder: orders,
        fas.FleetAlertRecord: [],
    })
    assert len(fas.check_overtime_parking(10, db=session)) == 1


@pytest.mark.parametrize("dirty", [float("nan"), float("inf"), "NaN", "Infinity"])
def test_check_overtime_parking_nonfinite_minutes_falls_back_default(monkeypatch, dirty):
    """minutes 为 NaN/Inf(数值或字符串) -> 不抛异常, 回落 DEFAULT_OVERTIME_MINUTES=120。"""
    monkeypatch.setattr(fas, "datetime", _FixedDateTime)
    end_time = _FixedDateTime._fixed - timedelta(minutes=150)   # > 默认 120
    orders = [SimpleNamespace(vehicle_id=5, end_time=end_time, plate_number="沪B888")]
    session = _mock_session({
        fas.FleetAlertRule: [_rule(AlertRuleType.OVERTIME_PARKING, {"minutes": dirty})],
        fas.ChargingOrder: orders,
        fas.FleetAlertRecord: [],
    })
    result = fas.check_overtime_parking(10, db=session)
    assert len(result) == 1
    assert result[0].alert_value == "parked=150min"


def test_check_overtime_parking_negative_minutes_no_crash(monkeypatch):
    """minutes 为负 -> 负值是有限数不回落, 但 int()/timedelta() 不抛异常。"""
    monkeypatch.setattr(fas, "datetime", _FixedDateTime)
    end_time = _FixedDateTime._fixed - timedelta(minutes=90)
    orders = [SimpleNamespace(vehicle_id=5, end_time=end_time, plate_number="沪B888")]
    session = _mock_session({
        fas.FleetAlertRule: [_rule(AlertRuleType.OVERTIME_PARKING, {"minutes": -60})],
        fas.ChargingOrder: orders,
        fas.FleetAlertRecord: [],
    })
    result = fas.check_overtime_parking(10, db=session)
    assert isinstance(result, list)


def test_check_overtime_parking_normal_minutes_still_works(monkeypatch):
    """正常数值 minutes 不受 isfinite 防御影响。"""
    monkeypatch.setattr(fas, "datetime", _FixedDateTime)
    end_time = _FixedDateTime._fixed - timedelta(minutes=90)
    orders = [SimpleNamespace(vehicle_id=5, end_time=end_time, plate_number="沪B888")]
    session = _mock_session({
        fas.FleetAlertRule: [_rule(AlertRuleType.OVERTIME_PARKING, {"minutes": 60})],
        fas.ChargingOrder: orders,
        fas.FleetAlertRecord: [],
    })
    result = fas.check_overtime_parking(10, db=session)
    assert len(result) == 1
    assert result[0].alert_value == "parked=90min"


def test_check_overtime_parking_skips_when_active_record_exists(monkeypatch):
    """已有 active 记录 -> 去重。"""
    monkeypatch.setattr(fas, "datetime", _FixedDateTime)
    end_time = _FixedDateTime._fixed - timedelta(minutes=300)
    orders = [SimpleNamespace(vehicle_id=5, end_time=end_time, plate_number="沪B888")]
    session = _mock_session({
        fas.FleetAlertRule: [_rule(AlertRuleType.OVERTIME_PARKING, {"minutes": 120})],
        fas.ChargingOrder: orders,
        fas.FleetAlertRecord: [MagicMock()],   # 去重
    })
    assert fas.check_overtime_parking(10, db=session) == []
    session.add.assert_not_called()


def test_check_overtime_parking_closes_own_session(monkeypatch):
    """db=None 时自有 session 在 finally 关闭(即便提前 return)。"""
    fake_session = _mock_session({})   # 无规则
    fake_local = MagicMock(return_value=fake_session)
    monkeypatch.setattr("app.core.database.SessionLocal", fake_local)

    assert fas.check_overtime_parking(10, db=None) == []
    fake_local.assert_called_once()
    fake_session.close.assert_called_once()


# ======================================================================
# 内部 helper 直接覆盖
# ======================================================================

def test_open_session_reuses_passed_db():
    """传入 db 时 own=False, 原样返回。"""
    db = MagicMock()
    session, own = fas._open_session(db)
    assert session is db
    assert own is False


def test_has_active_record_no_vehicle_id_returns_false():
    """vehicle_id 为空时不查库, 直接 False(防 NULL 广播)。"""
    session = MagicMock()
    assert fas._has_active_record(session, rule_id=1, vehicle_id=None) is False
    session.query.assert_not_called()


def test_vehicle_plate_no_vehicle_id_returns_none():
    session = MagicMock()
    assert fas._vehicle_plate(session, None) is None
    session.query.assert_not_called()


def test_vehicle_plate_returns_none_when_not_found():
    session = _mock_session({fas.EnterpriseVehicle: []})
    assert fas._vehicle_plate(session, 999) is None


def test_records_are_fleet_alert_record_instances():
    """生成的记录是 FleetAlertRecord 实例, 字段齐全。"""
    queues = [SimpleNamespace(vehicle_id=1, current_soc=0.10)]
    session = _mock_session({
        fas.FleetAlertRule: [_rule(AlertRuleType.LOW_BATTERY, {"soc_below": 20}, rule_id=42)],
        fas.ChargingQueue: queues,
        fas.FleetAlertRecord: [],
        fas.EnterpriseVehicle: [],
    })
    result = fas.check_low_battery(7, db=session)
    rec = result[0]
    assert isinstance(rec, FleetAlertRecord)
    assert rec.rule_id == 42
    assert rec.enterprise_id == 7
    assert rec.notified is False
    assert rec.triggered_at is not None
