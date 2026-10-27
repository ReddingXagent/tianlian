"""
扫码二维码管理端点团队隔离测试 — 卡 fd236172

验证 /api/v1/scan/qrcode* 四端点：
- 团队级用户仅可操作本 team（device.station.team_id）设备；
- 跨团队 get/generate/delete → 404（不泄露存在）；
- list 仅见本 team 设备；admin 保持全量。
quick_repair / scan_device 属扫码报修业务，不在本卡范围。
"""
import bcrypt
import pytest


@pytest.fixture
def cross_team_env(client):
    """两团队 + 两团队级用户 + 两站点 + 两设备。"""
    from app.models.user import User, UserRole, Team
    from app.models.station import Station, StationStatus
    from app.models.device import Device, DeviceType, DeviceStatus

    s = client._sesh
    ta = Team(name="SCAN团队A", code="SCANTA")
    tb = Team(name="SCAN团队B", code="SCANTB")
    s.add_all([ta, tb])
    s.commit()
    s.refresh(ta)
    s.refresh(tb)

    pwd = "scan123456"
    ua = User(
        username="scan_eng_a", real_name="A工程师", role=UserRole.OPERATOR,
        team_id=ta.id, status="active",
        password_hash=bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode(),
    )
    ub = User(
        username="scan_eng_b", real_name="B工程师", role=UserRole.OPERATOR,
        team_id=tb.id, status="active",
        password_hash=bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode(),
    )
    s.add_all([ua, ub])
    s.commit()

    sa = Station(name="SCAN-A站", code="SCNSA", team_id=ta.id, status=StationStatus.NORMAL)
    sb = Station(name="SCAN-B站", code="SCNSB", team_id=tb.id, status=StationStatus.NORMAL)
    s.add_all([sa, sb])
    s.commit()
    s.refresh(sa)
    s.refresh(sb)

    da = Device(sn="SCAN-A-DEV", name="A设备", code="SCANCHA",
                type=DeviceType.CHARGER_DC, status=DeviceStatus.ONLINE, station_id=sa.id)
    db_ = Device(sn="SCAN-B-DEV", name="B设备", code="SCANCHB",
                 type=DeviceType.CHARGER_DC, status=DeviceStatus.ONLINE, station_id=sb.id)
    s.add_all([da, db_])
    s.commit()
    s.refresh(da)
    s.refresh(db_)

    def _tok(username):
        r = client.post("/api/v1/auth/login", data={"username": username, "password": pwd})
        assert r.status_code == 200, f"登录失败 {username}: {r.text}"
        return r.json()["data"]["token"]

    return {
        "devices": {"a": da, "b": db_},
        "tokens": {"a": _tok("scan_eng_a"), "b": _tok("scan_eng_b")},
    }


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def test_generate_own_device_ok(client, cross_team_env):
    da = cross_team_env["devices"]["a"]
    r = client.post(
        "/api/v1/scan/qrcode/generate",
        json={"device_id": da.id},
        headers=_h(cross_team_env["tokens"]["a"]),
    )
    assert r.status_code == 200


def test_generate_other_team_404(client, cross_team_env):
    """A 用户为 B 设备生成二维码 → 404。"""
    db_ = cross_team_env["devices"]["b"]
    r = client.post(
        "/api/v1/scan/qrcode/generate",
        json={"device_id": db_.id},
        headers=_h(cross_team_env["tokens"]["a"]),
    )
    assert r.status_code == 404


def test_get_other_team_404(client, cross_team_env):
    """A 用户读 B 设备二维码 → 404。"""
    db_ = cross_team_env["devices"]["b"]
    client.post(
        "/api/v1/scan/qrcode/generate",
        json={"device_id": db_.id},
        headers=_h(cross_team_env["tokens"]["b"]),
    )
    r = client.get(f"/api/v1/scan/qrcode/{db_.id}", headers=_h(cross_team_env["tokens"]["a"]))
    assert r.status_code == 404


def test_get_own_device_ok(client, cross_team_env):
    da = cross_team_env["devices"]["a"]
    client.post(
        "/api/v1/scan/qrcode/generate",
        json={"device_id": da.id},
        headers=_h(cross_team_env["tokens"]["a"]),
    )
    r = client.get(f"/api/v1/scan/qrcode/{da.id}", headers=_h(cross_team_env["tokens"]["a"]))
    assert r.status_code == 200


def test_delete_other_team_404(client, cross_team_env):
    """A 用户禁用 B 设备二维码 → 404。"""
    db_ = cross_team_env["devices"]["b"]
    client.post(
        "/api/v1/scan/qrcode/generate",
        json={"device_id": db_.id},
        headers=_h(cross_team_env["tokens"]["b"]),
    )
    r = client.delete(f"/api/v1/scan/qrcode/{db_.id}", headers=_h(cross_team_env["tokens"]["a"]))
    assert r.status_code == 404
    # B 侧二维码未被禁用
    r = client.get(f"/api/v1/scan/qrcode/{db_.id}", headers=_h(cross_team_env["tokens"]["b"]))
    assert r.status_code == 200


def test_delete_own_device_ok(client, cross_team_env):
    da = cross_team_env["devices"]["a"]
    client.post(
        "/api/v1/scan/qrcode/generate",
        json={"device_id": da.id},
        headers=_h(cross_team_env["tokens"]["a"]),
    )
    r = client.delete(f"/api/v1/scan/qrcode/{da.id}", headers=_h(cross_team_env["tokens"]["a"]))
    assert r.status_code == 200


def test_list_filters_by_team(client, cross_team_env):
    """团队级用户列表仅见本 team 设备；admin 全量。"""
    da = cross_team_env["devices"]["a"]
    db_ = cross_team_env["devices"]["b"]
    for dev, tok in ((da, cross_team_env["tokens"]["a"]), (db_, cross_team_env["tokens"]["b"])):
        r = client.post(
            "/api/v1/scan/qrcode/generate", json={"device_id": dev.id},
            headers=_h(tok),
        )
        assert r.status_code == 200, r.text

    r = client.get("/api/v1/scan/qrcodes", headers=_h(cross_team_env["tokens"]["a"]))
    assert r.status_code == 200
    ids = [it["device_id"] for it in r.json()["data"]["items"]]
    assert da.id in ids
    assert db_.id not in ids

    # admin 全量不回归（client 默认 admin 身份）
    r = client.get("/api/v1/scan/qrcodes")
    assert r.status_code == 200
    ids = [it["device_id"] for it in r.json()["data"]["items"]]
    assert da.id in ids
    assert db_.id in ids


def test_admin_cross_team_ok(client, cross_team_env):
    """admin 跨团队 generate/get/delete 均 200。"""
    db_ = cross_team_env["devices"]["b"]
    r = client.post("/api/v1/scan/qrcode/generate", json={"device_id": db_.id})
    assert r.status_code == 200
    r = client.get(f"/api/v1/scan/qrcode/{db_.id}")
    assert r.status_code == 200
    r = client.delete(f"/api/v1/scan/qrcode/{db_.id}")
    assert r.status_code == 200
