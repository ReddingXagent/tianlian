"""
车队告警规则引擎测试 - SPEC §4.3
覆盖: 规则CRUD、告警记录查询、3类检测服务(低电量/异常充电/超时未离桩)、test触发端点、去重
"""
import pytest
from datetime import datetime, timezone, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.services.fleet_alert_service import (
    check_low_battery,
    check_abnormal_charging,
    check_overtime_parking,
)

client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    """每个测试使用独立数据库(test_db 已覆盖 SessionLocal)"""
    pass


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def _login():
    resp = client.post(
        "/api/v1/auth/login",
        data={"username": "admin", "password": "admin123"},
    )
    assert resp.status_code == 200
    data = resp.json()
    return data.get("token") or data.get("data", {}).get("token")


def _auth_headers():
    return {"Authorization": f"Bearer {_login()}"}


def _create_enterprise(code="ENT_ALERT_01"):
    from app.models.enterprise import Enterprise
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        ent = Enterprise(name=f"告警测试企业_{code}", code=code, balance=10000.00)
        db.add(ent)
        db.commit()
        db.refresh(ent)
        return ent.id
    finally:
        db.close()


def _create_vehicle(enterprise_id, plate="豫A-ALERT-001", vin="LSVAU2ALERT000001"):
    resp = client.post(
        f"/api/v1/enterprises/{enterprise_id}/vehicles",
        json={
            "plate_number": plate,
            "vin": vin,
            "driver_name": "测试司机",
            "driver_phone": "13800005678",
        },
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    return resp.json()["data"]["id"]


def _rule_payload(enterprise_id, rule_type="low_battery", threshold=None,
                  notify_channels=None, enable=True):
    return {
        "enterprise_id": enterprise_id,
        "rule_type": rule_type,
        "threshold": threshold if threshold is not None else {"soc_below": 20},
        "notify_channels": notify_channels if notify_channels is not None else ["im"],
        "enable": enable,
    }


def _create_station_and_device(sn_suffix="ALERT"):
    """创建一个充电桩 + 所属站点, 返回 (station_id, device_id)"""
    from app.models.device import Device, DeviceType, DeviceStatus
    from app.models.station import Station, StationStatus
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        station = Station(
            name=f"告警测试站_{sn_suffix}",
            code=f"STA_{sn_suffix}",
            address="告警测试地址",
            status=StationStatus.NORMAL,
        )
        db.add(station)
        db.commit()
        db.refresh(station)
        device = Device(
            sn=f"SN-{sn_suffix}",
            name=f"告警桩#{sn_suffix}",
            code=f"ALERT{sn_suffix}",
            type=DeviceType.CHARGER_DC,
            status=DeviceStatus.ONLINE,
            station_id=station.id,
            rated_power=120.0,
        )
        db.add(device)
        db.commit()
        db.refresh(device)
        return station.id, device.id
    finally:
        db.close()


def _create_charging_queue(enterprise_id, vehicle_id, device_id,
                           current_soc=0.15, status="charging"):
    from app.models.charging_queue import ChargingQueue
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        q = ChargingQueue(
            enterprise_id=enterprise_id,
            vehicle_id=vehicle_id,
            station_id=1,
            assigned_device_id=device_id,
            current_soc=current_soc,
            target_soc=0.8,
            status=status,
        )
        db.add(q)
        db.commit()
        db.refresh(q)
        return q.id
    finally:
        db.close()


def _create_charging_order(station_id, device_id, vehicle_id, plate, sn_suffix="X"):
    from app.models.charging_order import ChargingOrder, OrderStatus
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        o = ChargingOrder(
            order_no=f"NO-CHG-{sn_suffix}-{vehicle_id}",
            station_id=station_id,
            device_id=device_id,
            vehicle_id=vehicle_id,
            plate_number=plate,
            order_status=OrderStatus.CHARGING,
            start_time=datetime.now(timezone.utc) - timedelta(minutes=5),
        )
        db.add(o)
        db.commit()
        db.refresh(o)
        return o.id
    finally:
        db.close()


def _create_telemetry_charger(device_id, station_id, power_kw, minutes_ago=0):
    from app.models.telemetry_v2 import TelemetryCharger
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        t = TelemetryCharger(
            device_id=device_id,
            station_id=station_id,
            charger_power=power_kw,
            timestamp=datetime.now(timezone.utc) - timedelta(minutes=minutes_ago),
        )
        db.add(t)
        db.commit()
        db.refresh(t)
        return t.id
    finally:
        db.close()


def _create_completed_order(station_id, device_id, vehicle_id, plate, hours_ago=3):
    from app.models.charging_order import ChargingOrder, OrderStatus
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        end_time = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
        o = ChargingOrder(
            order_no=f"NO-ALERT-{vehicle_id}-{hours_ago}",
            station_id=station_id,
            device_id=device_id,
            vehicle_id=vehicle_id,
            plate_number=plate,
            order_status=OrderStatus.COMPLETED,
            start_time=end_time - timedelta(hours=1),
            end_time=end_time,
        )
        db.add(o)
        db.commit()
        db.refresh(o)
        return o.id
    finally:
        db.close()


# ======================================================================
# 规则 CRUD
# ======================================================================

class TestAlertRuleCRUD:
    """告警规则增删查改"""

    def test_create_rule(self):
        """创建低电量告警规则"""
        ent_id = _create_enterprise()
        resp = client.post(
            "/api/v1/fleet/alert-rules",
            json=_rule_payload(ent_id, "low_battery", {"soc_below": 20}),
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["enterprise_id"] == ent_id
        assert data["rule_type"] == "low_battery"
        assert data["threshold"] == {"soc_below": 20}
        assert data["notify_channels"] == ["im"]
        assert data["enable"] is True
        assert "id" in data and data["id"] > 0

    def test_create_rule_invalid_enterprise(self):
        """创建规则-企业不存在"""
        resp = client.post(
            "/api/v1/fleet/alert-rules",
            json=_rule_payload(999999, "low_battery"),
            headers=_auth_headers(),
        )
        assert resp.status_code == 404

    def test_create_rule_invalid_type(self):
        """创建规则-无效规则类型"""
        ent_id = _create_enterprise()
        payload = _rule_payload(ent_id, "unknown_type")
        resp = client.post(
            "/api/v1/fleet/alert-rules",
            json=payload,
            headers=_auth_headers(),
        )
        assert resp.status_code == 400

    def test_list_rules(self):
        """查询规则列表"""
        ent_id = _create_enterprise()
        for rt, th in [
            ("low_battery", {"soc_below": 20}),
            ("abnormal_charging", {"power_spike_kw": 30}),
            ("overtime_parking", {"minutes": 120}),
        ]:
            client.post(
                "/api/v1/fleet/alert-rules",
                json=_rule_payload(ent_id, rt, th),
                headers=_auth_headers(),
            )
        resp = client.get(
            f"/api/v1/fleet/alert-rules?enterprise_id={ent_id}",
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 3
        assert len(data["items"]) == 3

    def test_list_rules_filter_enterprise(self):
        """按企业过滤规则"""
        ent1 = _create_enterprise("ENT_A1")
        ent2 = _create_enterprise("ENT_A2")
        client.post("/api/v1/fleet/alert-rules", json=_rule_payload(ent1, "low_battery"), headers=_auth_headers())
        client.post("/api/v1/fleet/alert-rules", json=_rule_payload(ent2, "low_battery"), headers=_auth_headers())

        resp = client.get(
            f"/api/v1/fleet/alert-rules?enterprise_id={ent1}",
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["enterprise_id"] == ent1

    def test_update_rule(self):
        """更新规则阈值与启用状态"""
        ent_id = _create_enterprise()
        create_resp = client.post(
            "/api/v1/fleet/alert-rules",
            json=_rule_payload(ent_id, "low_battery", {"soc_below": 20}),
            headers=_auth_headers(),
        )
        rule_id = create_resp.json()["data"]["id"]

        resp = client.put(
            f"/api/v1/fleet/alert-rules/{rule_id}",
            json={"threshold": {"soc_below": 15}, "enable": False},
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["threshold"] == {"soc_below": 15}
        assert data["enable"] is False
        # rule_type 未传应保持不变
        assert data["rule_type"] == "low_battery"

    def test_update_rule_not_found(self):
        """更新不存在的规则"""
        resp = client.put(
            "/api/v1/fleet/alert-rules/99999",
            json={"enable": False},
            headers=_auth_headers(),
        )
        assert resp.status_code == 404

    def test_delete_rule(self):
        """删除规则"""
        ent_id = _create_enterprise()
        create_resp = client.post(
            "/api/v1/fleet/alert-rules",
            json=_rule_payload(ent_id, "low_battery"),
            headers=_auth_headers(),
        )
        rule_id = create_resp.json()["data"]["id"]

        del_resp = client.delete(
            f"/api/v1/fleet/alert-rules/{rule_id}",
            headers=_auth_headers(),
        )
        assert del_resp.status_code == 200

        # 再次删除/查询应 404
        resp = client.get(
            f"/api/v1/fleet/alert-rules?enterprise_id={ent_id}",
            headers=_auth_headers(),
        )
        assert resp.json()["data"]["total"] == 0

    def test_delete_rule_not_found(self):
        """删除不存在的规则"""
        resp = client.delete(
            "/api/v1/fleet/alert-rules/99999",
            headers=_auth_headers(),
        )
        assert resp.status_code == 404

    def test_delete_rule_cascades_records(self):
        """D3: 删除规则同时级联清理告警记录"""
        from app.models.fleet_alert_rule import FleetAlertRecord, AlertRecordStatus
        from app.core.database import SessionLocal

        ent_id = _create_enterprise("ENT_CASC")
        create_resp = client.post(
            "/api/v1/fleet/alert-rules",
            json=_rule_payload(ent_id, "low_battery"),
            headers=_auth_headers(),
        )
        rule_id = create_resp.json()["data"]["id"]

        # 写入 2 条记录
        db = SessionLocal()
        try:
            for i in range(2):
                db.add(FleetAlertRecord(
                    rule_id=rule_id,
                    enterprise_id=ent_id,
                    plate_number=f"豫A-C{i}",
                    triggered_at=datetime.now(timezone.utc),
                    alert_value="test",
                    status=AlertRecordStatus.ACTIVE,
                ))
            db.commit()
        finally:
            db.close()

        del_resp = client.delete(
            f"/api/v1/fleet/alert-rules/{rule_id}",
            headers=_auth_headers(),
        )
        assert del_resp.status_code == 200

        # 规则与记录均清除
        db = SessionLocal()
        try:
            assert db.query(FleetAlertRecord).filter(
                FleetAlertRecord.rule_id == rule_id
            ).count() == 0
        finally:
            db.close()

    def test_delete_rule_rollback_on_commit_failure(self):
        """D3: 级联删除 commit 失败必须 rollback + 500, 避免脏状态"""
        from app.api.v1.fleet_alerts import delete_rule
        from app.models.fleet_alert_rule import (
            FleetAlertRule,
            FleetAlertRecord,
            AlertRuleType,
            AlertRecordStatus,
        )
        from app.models.enterprise import Enterprise
        from app.models.user import User
        from app.core.database import SessionLocal
        from fastapi import HTTPException

        db = SessionLocal()
        try:
            ent = Enterprise(name="删除回滚企业", code="ENT_DELRB", balance=10000.00)
            db.add(ent)
            db.commit()
            db.refresh(ent)
            rule = FleetAlertRule(
                enterprise_id=ent.id,
                rule_type=AlertRuleType.LOW_BATTERY,
                threshold={"soc_below": 20},
                notify_channels=["im"],
                enable=True,
            )
            db.add(rule)
            db.commit()
            db.refresh(rule)
            db.add(FleetAlertRecord(
                rule_id=rule.id,
                enterprise_id=ent.id,
                plate_number="豫A-RB",
                triggered_at=datetime.now(timezone.utc),
                alert_value="test",
                status=AlertRecordStatus.ACTIVE,
            ))
            db.commit()
            rule_id = rule.id
            admin = db.query(User).filter(User.username == "admin").first()
            assert admin is not None
        finally:
            db.close()

        # 新 session, patch commit 抛错, 验证 rollback 被调用 + 返回 500
        s = SessionLocal()
        rollback_calls = []

        def _boom(*a, **k):
            raise RuntimeError("simulated commit failure")

        def _spy_rollback(*a, **k):
            rollback_calls.append(1)

        try:
            s.commit = _boom
            s.rollback = _spy_rollback
            with pytest.raises(HTTPException) as exc:
                delete_rule(rule_id, s, admin)
            assert exc.value.status_code == 500
        finally:
            s.close()
        assert len(rollback_calls) == 1, "commit 失败必须触发 rollback"


# ======================================================================
# 告警记录查询
# ======================================================================

class TestAlertRecords:
    """告警记录分页与筛选"""

    def test_list_records_filter_status(self):
        """按状态筛选告警记录 + 分页"""
        ent_id = _create_enterprise()
        veh_id = _create_vehicle(ent_id)

        # 创建规则并触发多条记录
        rule_resp = client.post(
            "/api/v1/fleet/alert-rules",
            json=_rule_payload(ent_id, "low_battery", {"soc_below": 20}),
            headers=_auth_headers(),
        )
        rule_id = rule_resp.json()["data"]["id"]

        from app.models.fleet_alert_rule import FleetAlertRecord, AlertRecordStatus
        from app.core.database import SessionLocal
        db = SessionLocal()
        try:
            # 卡 49aafa24 uq_fleet_alert_active: 同规则同车仅一条 ACTIVE →
            # 每条记录配独立 vehicle (本测试测列表筛选语义, 非重复 active 语义)
            veh_ids = [_create_vehicle(ent_id, vin=f"LSVAU2ALERT00F{i:03d}") for i in range(3)]
            for i in range(3):
                db.add(FleetAlertRecord(
                    rule_id=rule_id,
                    enterprise_id=ent_id,
                    vehicle_id=veh_ids[i],
                    plate_number=f"豫A-R{i}",
                    triggered_at=datetime.now(timezone.utc),
                    alert_value=f"soc=15.{i}%",
                    status=AlertRecordStatus.ACTIVE,
                ))
            db.add(FleetAlertRecord(
                rule_id=rule_id,
                enterprise_id=ent_id,
                vehicle_id=veh_ids[0],
                plate_number="豫A-RES",
                triggered_at=datetime.now(timezone.utc),
                alert_value="soc=10.0%",
                status=AlertRecordStatus.RESOLVED,
            ))
            db.commit()
        finally:
            db.close()

        # 按 active 状态筛选
        resp = client.get(
            f"/api/v1/fleet/alert-records?enterprise_id={ent_id}&status=active",
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 3
        assert len(data["items"]) == 3
        for item in data["items"]:
            assert item["status"] == "active"

    def test_list_records_pagination(self):
        """告警记录分页"""
        ent_id = _create_enterprise()
        veh_id = _create_vehicle(ent_id)
        rule_resp = client.post(
            "/api/v1/fleet/alert-rules",
            json=_rule_payload(ent_id, "low_battery"),
            headers=_auth_headers(),
        )
        rule_id = rule_resp.json()["data"]["id"]

        from app.models.fleet_alert_rule import FleetAlertRecord, AlertRecordStatus
        from app.core.database import SessionLocal
        db = SessionLocal()
        try:
            # 卡 49aafa24 uq_fleet_alert_active: 同规则同车仅一条 ACTIVE →
            # 每条记录配独立 vehicle (本测试测分页语义, 非重复 active 语义)
            veh_ids = [_create_vehicle(ent_id, vin=f"LSVAU2ALERT00P{i:03d}") for i in range(5)]
            for i in range(5):
                db.add(FleetAlertRecord(
                    rule_id=rule_id,
                    enterprise_id=ent_id,
                    vehicle_id=veh_ids[i],
                    plate_number=f"豫A-P{i}",
                    triggered_at=datetime.now(timezone.utc),
                    status=AlertRecordStatus.ACTIVE,
                ))
            db.commit()
        finally:
            db.close()

        resp = client.get(
            f"/api/v1/fleet/alert-records?enterprise_id={ent_id}&page=1&page_size=2",
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 5
        assert len(data["items"]) == 2


# ======================================================================
# 检测服务
# ======================================================================

class TestAlertDetectionServices:
    """三类告警检测服务"""

    def test_check_low_battery_triggers(self):
        """低电量检测: SOC低于阈值触发告警"""
        ent_id = _create_enterprise()
        veh_id = _create_vehicle(ent_id, plate="豫A-LOW-001")
        # 创建规则: SOC低于20%告警
        client.post(
            "/api/v1/fleet/alert-rules",
            json=_rule_payload(ent_id, "low_battery", {"soc_below": 20}),
            headers=_auth_headers(),
        )
        # 车辆当前SOC=15%
        _create_charging_queue(ent_id, veh_id, device_id=1, current_soc=0.15)

        records = check_low_battery(ent_id)
        assert len(records) == 1
        rec = records[0]
        assert rec.vehicle_id == veh_id
        assert rec.plate_number == "豫A-LOW-001"
        assert rec.status.value == "active"
        assert rec.notified is False
        assert "15" in (rec.alert_value or "")

    def test_check_low_battery_below_threshold_not_triggered(self):
        """SOC高于阈值不触发"""
        ent_id = _create_enterprise("ENT_LB2")
        veh_id = _create_vehicle(ent_id, plate="豫A-HI-001", vin="LSVAU2HI000000002")
        client.post(
            "/api/v1/fleet/alert-rules",
            json=_rule_payload(ent_id, "low_battery", {"soc_below": 20}),
            headers=_auth_headers(),
        )
        # SOC=80%, 远高于20%
        _create_charging_queue(ent_id, veh_id, device_id=1, current_soc=0.80)

        records = check_low_battery(ent_id)
        assert len(records) == 0

    def test_check_low_battery_no_enabled_rule(self):
        """无启用规则时不检测, 返回空"""
        ent_id = _create_enterprise("ENT_LB3")
        veh_id = _create_vehicle(ent_id, plate="豫A-NR-001", vin="LSVAU2NR000000003")
        _create_charging_queue(ent_id, veh_id, device_id=1, current_soc=0.05)

        records = check_low_battery(ent_id)
        assert len(records) == 0

    def test_check_low_battery_dedup(self):
        """重复调用不产生重复告警(去重)"""
        ent_id = _create_enterprise("ENT_LB4")
        veh_id = _create_vehicle(ent_id, plate="豫A-DD-001", vin="LSVAU2DD000000004")
        client.post(
            "/api/v1/fleet/alert-rules",
            json=_rule_payload(ent_id, "low_battery", {"soc_below": 20}),
            headers=_auth_headers(),
        )
        _create_charging_queue(ent_id, veh_id, device_id=1, current_soc=0.10)

        first = check_low_battery(ent_id)
        second = check_low_battery(ent_id)
        assert len(first) == 1
        assert len(second) == 0  # 已有 active 记录, 不重复触发

    def test_check_abnormal_charging_triggers(self):
        """异常充电检测: 功率突变触发告警"""
        ent_id = _create_enterprise("ENT_AC1")
        veh_id = _create_vehicle(ent_id, plate="豫A-AC-001", vin="LSVAU2AC000000010")
        client.post(
            "/api/v1/fleet/alert-rules",
            json=_rule_payload(ent_id, "abnormal_charging", {"power_spike_kw": 30}),
            headers=_auth_headers(),
        )
        station_id, device_id = _create_station_and_device("AC1")
        _create_charging_order(station_id, device_id, veh_id, "豫A-AC-001", sn_suffix="AC1")
        # 两次采样功率差=50kW > 30
        _create_telemetry_charger(device_id, station_id, power_kw=10, minutes_ago=2)
        _create_telemetry_charger(device_id, station_id, power_kw=60, minutes_ago=1)

        records = check_abnormal_charging(ent_id)
        assert len(records) == 1
        rec = records[0]
        assert rec.vehicle_id == veh_id
        assert rec.plate_number == "豫A-AC-001"
        assert rec.status.value == "active"

    def test_check_abnormal_charging_only_latest_two_samples_judged(self):
        """卡 0bf9a71d: 每设备仅 timestamp desc 最新 2 条参与判定, 旧数据突变不触发。

        3 设备各 3 条采样, 最新两条差值均 <30, 但各自更早的历史采样存在 >=30 突变
        (最早条 vs 中间条), 旧 N+1 逐单取 2 条语义下同样不触发 —— 本测试固化
        "只有最新 2 条算数"且窗口函数不把旧数据卷进来。
        """
        ent_id = _create_enterprise("ENT_AC2")
        for i in range(3):
            veh_id = _create_vehicle(
                ent_id, plate=f"豫A-AC-0{i+2}", vin=f"LSVAU2AC00000001{i+2}"
            )
            client.post(
                "/api/v1/fleet/alert-rules",
                json=_rule_payload(ent_id, "abnormal_charging", {"power_spike_kw": 30}),
                headers=_auth_headers(),
            )
            station_id, device_id = _create_station_and_device(f"AC2{i}")
            _create_charging_order(station_id, device_id, veh_id, f"豫A-AC-0{i+2}", sn_suffix=f"AC2{i}")
            # 旧数据: 历史上有 50kW 大突变(5min 前 5 → 4min 前 55), 但最新两条
            # (2min 前 55 → 1min 前 60) 差值仅 5 < 30 → 不触发
            _create_telemetry_charger(device_id, station_id, power_kw=5, minutes_ago=5)
            _create_telemetry_charger(device_id, station_id, power_kw=55, minutes_ago=4)
            _create_telemetry_charger(device_id, station_id, power_kw=60, minutes_ago=1)
            _create_telemetry_charger(device_id, station_id, power_kw=55, minutes_ago=2)

        records = check_abnormal_charging(ent_id)
        assert len(records) == 0

    def test_check_abnormal_charging_single_telemetry_sql_for_multi_device(self):
        """卡 0bf9a71d: 多设备在充订单 → 仅 1 条 telemetry SQL(窗口函数合并 N+1)。"""
        from sqlalchemy import event
        from app.core.database import SessionLocal as _SL

        ent_id = _create_enterprise("ENT_AC3")
        for i in range(3):
            veh_id = _create_vehicle(
                ent_id, plate=f"豫A-AC-1{i}", vin=f"LSVAU2AC00000002{i}"
            )
            client.post(
                "/api/v1/fleet/alert-rules",
                json=_rule_payload(ent_id, "abnormal_charging", {"power_spike_kw": 30}),
                headers=_auth_headers(),
            )
            station_id, device_id = _create_station_and_device(f"AC3{i}")
            _create_charging_order(station_id, device_id, veh_id, f"豫A-AC-1{i}", sn_suffix=f"AC3{i}")
            _create_telemetry_charger(device_id, station_id, power_kw=10, minutes_ago=2)
            _create_telemetry_charger(device_id, station_id, power_kw=60, minutes_ago=1)

        counter = {"n": 0}

        def _count(conn, cursor, statement, parameters, context, executemany):
            if "telemetry_charger" in statement and statement.lstrip().upper().startswith("SELECT"):
                counter["n"] += 1

        engine = _SL().get_bind()
        event.listen(engine, "before_cursor_execute", _count)
        try:
            records = check_abnormal_charging(ent_id)
        finally:
            event.remove(engine, "before_cursor_execute", _count)

        assert len(records) == 3          # 3 设备各自触发(diff=50)
        assert counter["n"] == 1          # 遥测仅 1 条 SELECT(旧实现为 3 条)

    def test_check_overtime_parking_triggers(self):
        """超时未离桩检测: 充电完成后占桩超时触发"""
        ent_id = _create_enterprise("ENT_OP1")
        veh_id = _create_vehicle(ent_id, plate="豫A-OP-001", vin="LSVAU2OP000000020")
        client.post(
            "/api/v1/fleet/alert-rules",
            json=_rule_payload(ent_id, "overtime_parking", {"minutes": 120}),
            headers=_auth_headers(),
        )
        station_id, device_id = _create_station_and_device("OP1")
        # 3小时前结束充电, 超过120分钟阈值
        _create_completed_order(station_id, device_id, veh_id, "豫A-OP-001", hours_ago=3)

        records = check_overtime_parking(ent_id)
        assert len(records) == 1
        rec = records[0]
        assert rec.vehicle_id == veh_id
        assert rec.plate_number == "豫A-OP-001"
        assert rec.status.value == "active"


# ======================================================================
# test 触发端点
# ======================================================================

class TestAlertTriggerEndpoint:
    """模拟触发端点"""

    def test_trigger_test_endpoint(self):
        """POST /alert-rules/{id}/test 模拟生成一条告警记录"""
        ent_id = _create_enterprise()
        veh_id = _create_vehicle(ent_id)
        create_resp = client.post(
            "/api/v1/fleet/alert-rules",
            json=_rule_payload(ent_id, "low_battery", {"soc_below": 20}),
            headers=_auth_headers(),
        )
        rule_id = create_resp.json()["data"]["id"]

        resp = client.post(
            f"/api/v1/fleet/alert-rules/{rule_id}/test",
            json={"vehicle_id": veh_id},
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["rule_id"] == rule_id
        assert data["enterprise_id"] == ent_id
        assert data["vehicle_id"] == veh_id
        assert data["status"] == "active"

        # 验证记录确实写入
        list_resp = client.get(
            f"/api/v1/fleet/alert-records?enterprise_id={ent_id}",
            headers=_auth_headers(),
        )
        assert list_resp.json()["data"]["total"] == 1

    def test_trigger_test_rule_not_found(self):
        """test 触发-规则不存在"""
        resp = client.post(
            "/api/v1/fleet/alert-rules/99999/test",
            json={"vehicle_id": 1},
            headers=_auth_headers(),
        )
        assert resp.status_code == 404

    def test_trigger_test_cross_enterprise_vehicle_ignored(self):
        """D1: 跨企业 vehicle_id 不泄露车牌, 记录归属仍为本企业"""
        ent1 = _create_enterprise("ENT_X1")
        ent2 = _create_enterprise("ENT_X2")
        # 企业1的车
        veh1 = _create_vehicle(ent1, plate="豫A-X1-001", vin="LSVAU2X1000000001")
        # 企业2的规则
        create_resp = client.post(
            "/api/v1/fleet/alert-rules",
            json=_rule_payload(ent2, "low_battery", {"soc_below": 20}),
            headers=_auth_headers(),
        )
        rule2_id = create_resp.json()["data"]["id"]

        # 用企业2的规则触发, payload 传企业1的车 → 必须被忽略
        resp = client.post(
            f"/api/v1/fleet/alert-rules/{rule2_id}/test",
            json={"vehicle_id": veh1},
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["enterprise_id"] == ent2
        assert data["vehicle_id"] is None        # 跨企业车辆不脏绑定
        assert data["plate_number"] is None      # 不泄露企业1车牌

    def test_trigger_test_nonexistent_vehicle_id(self):
        """D1: 不存在的 vehicle_id 优雅处理, 不报错"""
        ent_id = _create_enterprise("ENT_X3")
        create_resp = client.post(
            "/api/v1/fleet/alert-rules",
            json=_rule_payload(ent_id, "low_battery", {"soc_below": 20}),
            headers=_auth_headers(),
        )
        rule_id = create_resp.json()["data"]["id"]

        resp = client.post(
            f"/api/v1/fleet/alert-rules/{rule_id}/test",
            json={"vehicle_id": 99999999},
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["vehicle_id"] is None
        assert data["plate_number"] is None

    def test_trigger_test_invalid_vehicle_id_type(self):
        """D2: vehicle_id 非整数 → 422 (Pydantic 校验)"""
        ent_id = _create_enterprise("ENT_X4")
        create_resp = client.post(
            "/api/v1/fleet/alert-rules",
            json=_rule_payload(ent_id, "low_battery", {"soc_below": 20}),
            headers=_auth_headers(),
        )
        rule_id = create_resp.json()["data"]["id"]

        resp = client.post(
            f"/api/v1/fleet/alert-rules/{rule_id}/test",
            json={"vehicle_id": "not-a-number"},
            headers=_auth_headers(),
        )
        assert resp.status_code == 422

    def test_trigger_test_non_object_body(self):
        """D2: body 非 JSON 对象 → 422"""
        ent_id = _create_enterprise("ENT_X5")
        create_resp = client.post(
            "/api/v1/fleet/alert-rules",
            json=_rule_payload(ent_id, "low_battery", {"soc_below": 20}),
            headers=_auth_headers(),
        )
        rule_id = create_resp.json()["data"]["id"]

        resp = client.post(
            f"/api/v1/fleet/alert-rules/{rule_id}/test",
            content='"hello"',
            headers={**_auth_headers(), "Content-Type": "application/json"},
        )
        assert resp.status_code == 422
