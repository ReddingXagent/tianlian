# -*- coding: utf-8 -*-
"""时间窗参数上界测试 — 卡 1abf2c01

背景: hours / shift_duration_hours 无上界时, `timedelta(hours=<超大值>)` 抛
`OverflowError: Python int too large to convert to C int` → 端点 500。
修复: schema 层 Field(ge=1, le=720) 前置拒绝, 越界 → 422。

覆盖:
- POST /predictives/predict hours=10**12 → 422 (不 500)
- POST /predictives/batch-predict hours=10**12 → 422
- POST /on-call/rules shift_duration_hours=10**12 → 422
- 边界合法值 hours=720 / shift_duration_hours=720 通过 schema (不抛 OverflowError)
"""
import pytest

ONCALL = "/api/v1/on-call"
PM = "/api/v1/predictive-maintenance"


@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    pass


@pytest.fixture
def test_station(test_db):
    db = test_db["session"]
    from app.models.station import Station, StationStatus
    station = Station(name="HB-站点", code="HB-STATION-001", status=StationStatus.NORMAL)
    db.add(station)
    db.commit()
    db.refresh(station)
    return station


@pytest.fixture
def test_device(test_db, test_station):
    db = test_db["session"]
    from app.models.device import Device, DeviceType, DeviceStatus, ProtocolType
    device = Device(
        sn="HB-DEV-001", name="边界设备",
        type=DeviceType.PV_INVERTER, status=DeviceStatus.ONLINE,
        station_id=test_station.id, protocol_type=ProtocolType.MODBUS_RTU,
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return device


class TestHoursUpperBound:
    """超大 hours / shift_duration_hours → 422 (Pydantic 前置拒绝, 不 500)"""

    def test_predict_hours_overflow_rejected(self, client, test_device):
        r = client.post(f"{PM}/predict",
                        json={"device_id": test_device.id, "hours": 10**12})
        assert r.status_code == 422, f"应 422: {r.status_code} {r.text[:300]}"

    def test_batch_predict_hours_overflow_rejected(self, client, test_device):
        r = client.post(f"{PM}/batch-predict",
                        json={"device_ids": [test_device.id], "hours": 10**12})
        assert r.status_code == 422, f"应 422: {r.status_code} {r.text[:300]}"

    def test_oncall_shift_duration_overflow_rejected(self, client):
        s = client._sesh
        from app.models.user import User, Team
        admin = s.query(User).filter(User.username == "admin").first()
        assert admin is not None
        team = s.query(Team).first()
        if team is None:
            team = Team(name="HB-值班团队", code="HBTEAM")
            s.add(team)
            s.commit()
            s.refresh(team)
        r = client.post(f"{ONCALL}/rules", json={
            "name": "溢出规则",
            "rotation_order": [admin.id],
            "team_id": team.id,
            "shift_duration_hours": 10**12,
        })
        assert r.status_code == 422, f"应 422: {r.status_code} {r.text[:300]}"

    def test_predict_hours_boundary_720_no_overflow(self, client, test_device):
        """边界值 720 通过 schema 校验 (422 校验不因上界触发; 也不 500 OverflowError)。"""
        r = client.post(f"{PM}/predict",
                        json={"device_id": test_device.id, "hours": 720})
        assert r.status_code != 422, f"720 是合法上界, 不应 422: {r.text[:300]}"
        assert r.status_code != 500, f"不应 500 OverflowError: {r.text[:300]}"

    def test_oncall_shift_duration_boundary_720_no_overflow(self, client):
        s = client._sesh
        from app.models.user import User, Team
        admin = s.query(User).filter(User.username == "admin").first()
        assert admin is not None
        team = s.query(Team).first()
        if team is None:
            team = Team(name="HB-值班团队", code="HBTEAM")
            s.add(team)
            s.commit()
            s.refresh(team)
        r = client.post(f"{ONCALL}/rules", json={
            "name": "边界规则",
            "rotation_order": [admin.id],
            "team_id": team.id,
            "shift_duration_hours": 720,
        })
        assert r.status_code == 200, f"720 合法应 200: {r.status_code} {r.text[:300]}"
