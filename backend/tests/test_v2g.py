"""
V2G 调度 API 测试

覆盖: /api/v1/devices/{device_id}/v2g/*
- POST /devices/{id}/v2g/dispatch          下发调度（设备校验 + V2G 类型校验 + 功率>0）
- GET  /devices/{id}/v2g/dispatch/history  调度历史（倒序分页）
- GET  /devices/v2g/dispatch/active        当前活跃调度

注: v2g.router 独立挂载于 /devices 前缀, 端点未声明 get_current_user, 故无需鉴权。
"""
import pytest

from app.models.device import Device, DeviceType, DeviceStatus


def _seed_device(client, dtype, sn="SN-V2G-001", name="V2G桩#1"):
    from app.models.station import Station, StationStatus
    s = client._sesh
    # 创建关联站点（device.station_id NOT NULL）
    st = Station(name=f"站点-{sn}", code=f"ST-{sn}", address="测试地址",
                 status=StationStatus.NORMAL)
    s.add(st)
    s.commit()
    s.refresh(st)
    dev = Device(
        sn=sn, name=name, code=sn.replace("SN-", "CODE-"),
        type=dtype, status=DeviceStatus.ONLINE, rated_power=100.0,
        station_id=st.id,
    )
    s.add(dev)
    s.commit()
    s.refresh(dev)
    return dev


def test_dispatch_success(client):
    """向 V2G 桩下发 discharge 指令，落库并返回 pending 记录"""
    dev = _seed_device(client, DeviceType.V2G_CHARGER)
    resp = client.post(f"/api/v1/devices/{dev.id}/v2g/dispatch", json={
        "dispatch_type": "discharge",
        "target_power_kw": 30.0,
    })
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["id"] > 0
    assert data["device_id"] == dev.id
    assert data["dispatch_type"] == "discharge"
    assert data["target_power_kw"] == 30.0
    assert data["actual_power_kw"] == 0.0
    assert data["status"] == "pending"


def test_dispatch_device_not_found(client):
    resp = client.post("/api/v1/devices/999999/v2g/dispatch", json={
        "dispatch_type": "charge", "target_power_kw": 10.0,
    })
    assert resp.status_code == 404


def test_dispatch_non_v2g_rejected(client):
    """非 V2G 桩（直流桩）下发调度返回 400"""
    dev = _seed_device(client, DeviceType.CHARGER_DC, sn="SN-DC-001", name="直流桩#1")
    resp = client.post(f"/api/v1/devices/{dev.id}/v2g/dispatch", json={
        "dispatch_type": "charge", "target_power_kw": 10.0,
    })
    assert resp.status_code == 400
    assert "不支持V2G" in resp.json()["detail"]


def test_dispatch_invalid_power(client):
    """target_power_kw 必须 > 0 → 0 触发 422"""
    dev = _seed_device(client, DeviceType.V2G_CHARGER)
    resp = client.post(f"/api/v1/devices/{dev.id}/v2g/dispatch", json={
        "dispatch_type": "charge", "target_power_kw": 0,
    })
    assert resp.status_code == 422


def test_dispatch_history(client):
    """下发两条不同类型指令，history 返回全部且不依赖时间排序断言"""
    dev = _seed_device(client, DeviceType.V2G_CHARGER)
    client.post(f"/api/v1/devices/{dev.id}/v2g/dispatch", json={
        "dispatch_type": "charge", "target_power_kw": 10.0})
    client.post(f"/api/v1/devices/{dev.id}/v2g/dispatch", json={
        "dispatch_type": "discharge", "target_power_kw": 20.0})

    resp = client.get(f"/api/v1/devices/{dev.id}/v2g/dispatch/history")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] == 2
    assert len(data["items"]) == 2
    types = {it["dispatch_type"] for it in data["items"]}
    assert types == {"charge", "discharge"}


def test_history_device_not_found(client):
    resp = client.get("/api/v1/devices/999999/v2g/dispatch/history")
    assert resp.status_code == 404


def test_active_dispatches(client):
    """pending/executing 调度进入活跃列表"""
    dev = _seed_device(client, DeviceType.V2G_CHARGER)
    client.post(f"/api/v1/devices/{dev.id}/v2g/dispatch", json={
        "dispatch_type": "charge", "target_power_kw": 15.0})

    resp = client.get("/api/v1/devices/v2g/dispatch/active")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] >= 1
    assert all(it["status"] in ("pending", "executing") for it in data["items"])


# ═══════════════════════════════════════════════════════════════
# V2G 放电价配置 (operate/v2g/pricing) — 卡 b2d7ff9c
# ═══════════════════════════════════════════════════════════════

import json as _tjson

from app.api.v1.operate import v2g as v2g_mod


@pytest.fixture(autouse=True)
def _isolate_pricing_file(tmp_path, monkeypatch):
    """pricing 测试类: _PRICING_FILE 重定向到 tmp, 不碰真实 data/v2g_pricing.json。"""
    monkeypatch.setattr(v2g_mod, "_PRICING_FILE", tmp_path / "v2g_pricing.json")


def _viewer_token(client):
    """seed VIEWER 用户并登录 (无 system:config 权限, 供 403 测试)。"""
    import bcrypt
    from app.models.user import User, UserRole
    s = client._sesh
    if not s.query(User).filter(User.username == "v2gviewer").first():
        s.add(User(
            username="v2gviewer",
            password_hash=bcrypt.hashpw(b"v2gview123", bcrypt.gensalt()).decode(),
            role=UserRole.VIEWER,
            status="active",
        ))
        s.commit()
    r = client.post("/api/v1/auth/login",
                    data={"username": "v2gviewer", "password": "v2gview123"})
    assert r.status_code == 200, r.text
    j = r.json()
    return j.get("data", {}).get("token") or j.get("token")


def _period(start, end, price=0.5, kind="buy", name=None):
    return {"name": name or f"{start}-{end}", "start": start, "end": end,
            "price": price, "kind": kind}


def test_v2g_pricing_get_default(client):
    """无配置文件时 GET 返回默认配置。"""
    r = client.get("/api/v1/operate/v2g/pricing")
    assert r.status_code == 200
    data = r.json()["data"]
    assert isinstance(data["periods"], list) and data["periods"]


def test_v2g_pricing_put_roundtrip(client):
    """正常 PUT 后 GET 往返一致, 落盘 JSON 合法。"""
    payload = {"periods": [
        _period("00:00", "08:00", 0.30, "buy", "谷"),
        _period("08:00", "23:59", 0.80, "sell", "峰"),
    ]}
    r = client.put("/api/v1/operate/v2g/pricing", json=payload)
    assert r.status_code == 200, r.text
    saved = r.json()["data"]["periods"]
    assert [(p["start"], p["end"], p["price"], p["kind"]) for p in saved] == [
        ("00:00", "08:00", 0.30, "buy"), ("08:00", "23:59", 0.80, "sell")]
    # 落盘 JSON 可被标准 json 解析 (无 NaN/Infinity 字面量)
    raw = v2g_mod._PRICING_FILE.read_text()
    assert _tjson.loads(raw)
    # GET 往返一致
    g = client.get("/api/v1/operate/v2g/pricing").json()["data"]
    assert g["periods"] == saved


def test_v2g_pricing_put_nan_rejected(client):
    """NaN/Infinity 价格 → 422。"""
    for bad in ("NaN", "Infinity", "-Infinity"):
        r = client.put("/api/v1/operate/v2g/pricing", json={
            "periods": [_period("00:00", "08:00", bad)]})
        assert r.status_code == 422, f"{bad} 应 422: {r.text}"


def test_v2g_pricing_put_bad_time_rejected(client):
    """非法时间格式 → 422。"""
    for start in ("9:3", "abc", "25:99", "0:00", "12:5", "12345"):
        r = client.put("/api/v1/operate/v2g/pricing", json={
            "periods": [_period(start, "08:00")]})
        assert r.status_code == 422, f"{start} 应 422: {r.text}"
    r = client.put("/api/v1/operate/v2g/pricing", json={
        "periods": [_period("00:00", "24:00")]})
    assert r.status_code == 422


def test_v2g_pricing_put_bad_kind_rejected(client):
    """kind 笔误 (SELL/sellx/缺失) → 422, 不静默强转。"""
    for kind in ("SELL", "Sell", "sell ", "buyx", ""):
        r = client.put("/api/v1/operate/v2g/pricing", json={
            "periods": [_period("00:00", "08:00", kind=kind)]})
        assert r.status_code == 422, f"kind={kind!r} 应 422: {r.text}"


def test_v2g_pricing_put_viewer_403(client):
    """无 system:config 权限用户 PUT → 403。"""
    r = client.put("/api/v1/operate/v2g/pricing",
                   json={"periods": [_period("00:00", "08:00")]},
                   headers={"Authorization": f"Bearer {_viewer_token(client)}"})
    assert r.status_code == 403
    # GET 仍登录可读
    r = client.get("/api/v1/operate/v2g/pricing",
                   headers={"Authorization": f"Bearer {_viewer_token(client)}"})
    assert r.status_code == 200


def test_v2g_pricing_put_overlap_rejected(client):
    """时段两两重叠 → 422。"""
    r = client.put("/api/v1/operate/v2g/pricing", json={"periods": [
        _period("00:00", "08:00"), _period("07:00", "12:00")]})
    assert r.status_code == 422
    r = client.put("/api/v1/operate/v2g/pricing", json={"periods": [
        _period("06:00", "09:00"), _period("00:00", "06:30")]})
    assert r.status_code == 422
    # 相邻不重叠合法
    r = client.put("/api/v1/operate/v2g/pricing", json={"periods": [
        _period("00:00", "08:00"), _period("08:00", "12:00")]})
    assert r.status_code == 200


def test_v2g_pricing_legacy_format_compat(client):
    """旧格式(谷/平/峰/尖固定字段)文件 → 读取时迁移为 periods。"""
    v2g_mod._PRICING_FILE.write_text(_tjson.dumps(
        {"valley": 0.25, "flat": 0.6, "peak": 1.0, "sharp": 1.3}))
    r = client.get("/api/v1/operate/v2g/pricing")
    assert r.status_code == 200
    periods = r.json()["data"]["periods"]
    assert {p["name"] for p in periods} == {"谷时", "平时", "峰时", "尖峰"}
    assert periods[0]["price"] == 0.25
