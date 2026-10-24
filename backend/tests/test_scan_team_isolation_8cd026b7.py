"""
扫码报修端点团队隔离测试 — 卡 8cd026b7 (审计 #7)

验证 /api/v1/scan/device 与 /api/v1/scan/quick-repair：
- 团队级用户扫本 team 设备（二维码/编码/SN 三路径）→ 200；
- 扫跨 team 设备（三路径）→ 404（不泄露 SN/站点/健康度）；
- 跨 team quick-repair → 404，不创建工单；
- 本 team quick-repair → 200；admin 豁免。
"""
import bcrypt
import pytest


@pytest.fixture
def cross_team_env(client):
    """两团队 + 两团队级用户 + 两站点 + 两设备（设备 B 生成二维码）。"""
    from app.models.user import User, UserRole, Team
    from app.models.station import Station, StationStatus
    from app.models.device import Device, DeviceType, DeviceStatus

    s = client._sesh
    ta = Team(name="SCNB团队A", code="SCNBTA")
    tb = Team(name="SCNB团队B", code="SCNBTB")
    s.add_all([ta, tb])
    s.commit()
    s.refresh(ta)
    s.refresh(tb)

    pwd = "scnb123456"
    ua = User(
        username="scnb_eng_a", real_name="A工程师", role=UserRole.OPERATOR,
        team_id=ta.id, status="active",
        password_hash=bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode(),
    )
    ub = User(
        username="scnb_eng_b", real_name="B工程师", role=UserRole.OPERATOR,
        team_id=tb.id, status="active",
        password_hash=bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode(),
    )
    s.add_all([ua, ub])
    s.commit()

    sa = Station(name="SCNB-A站", code="SCNBSA", team_id=ta.id, status=StationStatus.NORMAL)
    sb = Station(name="SCNB-B站", code="SCNBSB", team_id=tb.id, status=StationStatus.NORMAL)
    s.add_all([sa, sb])
    s.commit()
    s.refresh(sa)
    s.refresh(sb)

    da = Device(sn="SCNB-A-DEV", name="A设备", code="SCNBCA",
                type=DeviceType.CHARGER_DC, status=DeviceStatus.ONLINE, station_id=sa.id)
    db_ = Device(sn="SCNB-B-DEV", name="B设备", code="SCNBCB",
                 type=DeviceType.CHARGER_DC, status=DeviceStatus.ONLINE, station_id=sb.id)
    s.add_all([da, db_])
    s.commit()
    s.refresh(da)
    s.refresh(db_)

    # B 设备生成二维码（B 用户操作）
    def _tok(username):
        r = client.post("/api/v1/auth/login", data={"username": username, "password": pwd})
        assert r.status_code == 200, f"登录失败 {username}: {r.text}"
        return r.json()["data"]["token"]

    tok_a, tok_b = _tok("scnb_eng_a"), _tok("scnb_eng_b")
    r = client.post(
        "/api/v1/scan/qrcode/generate", json={"device_id": db_.id},
        headers={"Authorization": f"Bearer {tok_b}"},
    )
    assert r.status_code == 200, r.text
    qr_b = r.json()["data"]["qr_code"]

    return {
        "devices": {"a": da, "b": db_},
        "tokens": {"a": tok_a, "b": tok_b},
        "qr_b": qr_b,
    }


def _h(token):
    return {"Authorization": f"Bearer {token}"}


# ========== scan_device 三路径 ==========

def test_scan_own_device_by_code_ok(client, cross_team_env):
    da = cross_team_env["devices"]["a"]
    r = client.post(
        "/api/v1/scan/device", json={"qr_code": da.code},
        headers=_h(cross_team_env["tokens"]["a"]),
    )
    assert r.status_code == 200
    assert r.json()["data"]["device_id"] == da.id


def test_scan_own_device_by_sn_ok(client, cross_team_env):
    da = cross_team_env["devices"]["a"]
    r = client.post(
        "/api/v1/scan/device", json={"qr_code": da.sn},
        headers=_h(cross_team_env["tokens"]["a"]),
    )
    assert r.status_code == 200
    assert r.json()["data"]["device_id"] == da.id


def test_scan_other_team_by_qrcode_404(client, cross_team_env):
    r = client.post(
        "/api/v1/scan/device", json={"qr_code": cross_team_env["qr_b"]},
        headers=_h(cross_team_env["tokens"]["a"]),
    )
    assert r.status_code == 404


def test_scan_other_team_by_code_404(client, cross_team_env):
    db_ = cross_team_env["devices"]["b"]
    r = client.post(
        "/api/v1/scan/device", json={"qr_code": db_.code},
        headers=_h(cross_team_env["tokens"]["a"]),
    )
    assert r.status_code == 404


def test_scan_other_team_by_sn_404(client, cross_team_env):
    db_ = cross_team_env["devices"]["b"]
    r = client.post(
        "/api/v1/scan/device", json={"qr_code": db_.sn},
        headers=_h(cross_team_env["tokens"]["a"]),
    )
    assert r.status_code == 404


def test_scan_other_team_no_scan_count_leak(client, cross_team_env):
    """跨队扫码不得累计扫码统计（侧信道）。"""
    db_ = cross_team_env["devices"]["b"]
    from app.models.device_qrcode import DeviceQRCode
    s = client._sesh
    before = s.query(DeviceQRCode).filter(DeviceQRCode.device_id == db_.id).first().scan_count
    client.post(
        "/api/v1/scan/device", json={"qr_code": cross_team_env["qr_b"]},
        headers=_h(cross_team_env["tokens"]["a"]),
    )
    s.rollback()
    after = s.query(DeviceQRCode).filter(DeviceQRCode.device_id == db_.id).first().scan_count
    assert after == before


# ========== quick_repair ==========

def test_quick_repair_own_device_ok(client, cross_team_env):
    da = cross_team_env["devices"]["a"]
    r = client.post(
        "/api/v1/scan/quick-repair",
        json={"device_id": da.id, "fault_desc": "本队报修", "fault_level": "warning"},
        headers=_h(cross_team_env["tokens"]["a"]),
    )
    assert r.status_code == 200
    assert "WO-" in r.json()["data"]["workorder_id"]


def test_quick_repair_other_team_404_no_workorder(client, cross_team_env):
    """跨队报修 → 404，且不创建任何工单（不触发派单）。"""
    db_ = cross_team_env["devices"]["b"]
    from app.models.workorder import WorkOrder
    s = client._sesh
    before = s.query(WorkOrder).filter(WorkOrder.device_id == db_.id).count()
    r = client.post(
        "/api/v1/scan/quick-repair",
        json={"device_id": db_.id, "fault_desc": "越权报修", "fault_level": "critical"},
        headers=_h(cross_team_env["tokens"]["a"]),
    )
    assert r.status_code == 404
    s.rollback()
    after = s.query(WorkOrder).filter(WorkOrder.device_id == db_.id).count()
    assert after == before


def test_admin_exempt_ok(client, cross_team_env):
    """admin 跨队扫码/报修保持 200（client 默认 admin 身份）。"""
    db_ = cross_team_env["devices"]["b"]
    r = client.post("/api/v1/scan/device", json={"qr_code": db_.sn})
    assert r.status_code == 200
    r = client.post(
        "/api/v1/scan/quick-repair",
        json={"device_id": db_.id, "fault_desc": "admin报修", "fault_level": "warning"},
    )
    assert r.status_code == 200
