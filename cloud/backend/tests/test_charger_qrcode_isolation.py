"""
充电桩二维码团队隔离测试 — 任务卡 708350b3

验证 /api/v1/operate/charger-qrcode/* 端点：
- 团队级用户只能操作本 team（经 device.station.team_id 校验）的充电桩；
- 伪造 X-Team-Id 不得越权生成/下载/列举他队设备二维码；
- admin/平台级跨团队可见。
"""
import bcrypt
import pytest


@pytest.fixture
def cross_team_chargers(client):
    """两团队 + 两团队级用户 + 两站点(分属两团队) + 两直流充电桩。"""
    from app.models.user import User, UserRole, Team
    from app.models.station import Station, StationStatus
    from app.models.device import Device, DeviceType, DeviceStatus

    s = client._sesh
    ta = Team(name="QR团队A", code="QRTA")
    tb = Team(name="QR团队B", code="QRTB")
    s.add_all([ta, tb])
    s.commit()
    s.refresh(ta)
    s.refresh(tb)

    pwd = "qr123456"
    ua = User(
        username="qr_eng_a", real_name="A工程师", role=UserRole.OPERATOR,
        team_id=ta.id, status="active",
        password_hash=bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode(),
    )
    ub = User(
        username="qr_eng_b", real_name="B工程师", role=UserRole.OPERATOR,
        team_id=tb.id, status="active",
        password_hash=bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode(),
    )
    s.add_all([ua, ub])
    s.commit()

    sa = Station(name="QR-A站", code="QRSA", team_id=ta.id, status=StationStatus.NORMAL)
    sb = Station(name="QR-B站", code="QRSB", team_id=tb.id, status=StationStatus.NORMAL)
    s.add_all([sa, sb])
    s.commit()
    s.refresh(sa)
    s.refresh(sb)

    da = Device(sn="QR-A-DEV", name="A充电桩", code="QRCHA",
                type=DeviceType.CHARGER_DC, status=DeviceStatus.ONLINE, station_id=sa.id)
    db = Device(sn="QR-B-DEV", name="B充电桩", code="QRCHB",
                type=DeviceType.CHARGER_DC, status=DeviceStatus.ONLINE, station_id=sb.id)
    s.add_all([da, db])
    s.commit()
    s.refresh(da)
    s.refresh(db)

    def _tok(username):
        r = client.post("/api/v1/auth/login", data={"username": username, "password": pwd})
        assert r.status_code == 200, f"登录失败 {username}: {r.text}"
        return r.json()["data"]["token"]

    return {
        "teams": {"a": ta, "b": tb},
        "devices": {"a": da, "b": db},
        "tokens": {"a": _tok("qr_eng_a"), "b": _tok("qr_eng_b")},
    }


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def test_generate_own_device_ok(client, cross_team_chargers):
    """团队级用户生成本 team 设备二维码 → 成功。"""
    da = cross_team_chargers["devices"]["a"]
    r = client.post(
        "/api/v1/operate/charger-qrcode/generate",
        json={"device_ids": [da.id]},
        headers=_h(cross_team_chargers["tokens"]["a"]),
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["total"] == 1
    assert data["failed"] == 0


def test_generate_other_team_device_blocked(client, cross_team_chargers):
    """A 用户生成 B 设备（伪造 X-Team-Id）→ 记 error，不生成。"""
    db = cross_team_chargers["devices"]["b"]
    r = client.post(
        "/api/v1/operate/charger-qrcode/generate",
        json={"device_ids": [db.id]},
        headers={**_h(cross_team_chargers["tokens"]["a"]),
                 "X-Team-Id": str(cross_team_chargers["teams"]["b"].id)},
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["total"] == 0
    assert data["failed"] == 1
    assert "无权" in data["errors"][0]["error"]


def test_list_filters_by_team(client, cross_team_chargers):
    """团队级用户列表只见本 team 充电桩；admin 看全部。"""
    da = cross_team_chargers["devices"]["a"]
    db = cross_team_chargers["devices"]["b"]

    # A 只看到 A 设备
    r = client.get(
        "/api/v1/operate/charger-qrcode/list",
        headers=_h(cross_team_chargers["tokens"]["a"]),
    )
    assert r.status_code == 200
    ids = [it["device_id"] for it in r.json()["data"]["items"]]
    assert da.id in ids
    assert db.id not in ids

    # admin 看全部
    r = client.get("/api/v1/operate/charger-qrcode/list")
    assert r.status_code == 200
    ids = [it["device_id"] for it in r.json()["data"]["items"]]
    assert da.id in ids
    assert db.id in ids


def test_download_other_team_404(client, cross_team_chargers):
    """A 用户下载 B 设备二维码 → 404（伪造 X-Team-Id 也无效）。"""
    db = cross_team_chargers["devices"]["b"]
    # 先让 B 生成二维码
    client.post(
        "/api/v1/operate/charger-qrcode/generate",
        json={"device_ids": [db.id]},
        headers=_h(cross_team_chargers["tokens"]["b"]),
    )
    r = client.get(
        f"/api/v1/operate/charger-qrcode/download/{db.id}",
        headers={**_h(cross_team_chargers["tokens"]["a"]),
                 "X-Team-Id": str(cross_team_chargers["teams"]["b"].id)},
    )
    assert r.status_code == 404


def test_download_own_device_ok(client, cross_team_chargers):
    """B 用户下载本 team 设备二维码 → 200。"""
    db = cross_team_chargers["devices"]["b"]
    client.post(
        "/api/v1/operate/charger-qrcode/generate",
        json={"device_ids": [db.id]},
        headers=_h(cross_team_chargers["tokens"]["b"]),
    )
    r = client.get(
        f"/api/v1/operate/charger-qrcode/download/{db.id}",
        headers=_h(cross_team_chargers["tokens"]["b"]),
    )
    assert r.status_code == 200
