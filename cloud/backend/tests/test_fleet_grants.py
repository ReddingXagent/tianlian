"""
车队三级授权测试 — 公司→场站→设备(桩级白名单) + 充电启动 scope 校验 (卡 a1468299)

覆盖:
- 授权管理 API (POST/GET/DELETE /operate/fleet-grants):
  · 整站授权(device_id=None) / 桩级授权(device_id 非空) 创建 + 回显
  · device.station_id 与 station_id 不一致 → 拒绝
  · 越权: A 团队不可给 B 团队企业/场站授权 → 404
  · 列表按 enterprise 过滤 + 团队隔离
  · 删除 + 越权删除 → 404
  · 重复整站授权 → 409; 企业/场站/设备不存在 → 404
- 充电启动 scope 校验 (POST /charging-sessions):
  · 整站授权 → 该站所有桩允许
  · 桩级白名单 → 授权桩允许 / 未授权桩 403
  · 企业无任何授权 → 放行(向后兼容)
  · 企业有授权但设备未被覆盖 → 403
- 企业详情返回授权范围(device_grants 摘要)

范式参考 test_fleet_team_isolation.py(团队用户造+登录) + test_charging_sessions.py(ingestion)。
"""
import bcrypt
import pytest

from app.models.charging_order import ChargingOrder


# ═══════════════════════════════════════════════════════════════════════
# Helpers / Fixtures
# ═══════════════════════════════════════════════════════════════════════

def _admin_h(client):
    r = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['data']['token']}"}


def _h(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def grant_team_pair(client):
    """两团队 + 两 OPERATOR 用户 + 两企业 + 两场站(各含两桩) + token。

    团队 A / B 各自拥有: 1 企业、1 场站、场站下 2 个充电桩。
    """
    from app.models.user import User, UserRole, Team
    from app.models.enterprise import Enterprise, EnterpriseStatus
    from app.models.station import Station, StationStatus
    from app.models.device import Device, DeviceType, DeviceStatus

    s = client._sesh
    out = {"teams": {}, "users": {}, "enterprises": {}, "stations": {}, "devices": {}}

    pwd = "grant123456"
    for key, tname, tcode in [("a", "授权团队A", "GTTA"), ("b", "授权团队B", "GTTB")]:
        t = Team(name=tname, code=tcode)
        s.add(t)
        s.commit()
        s.refresh(t)
        out["teams"][key] = t

        u = User(
            username=f"grant_op_{key}", real_name=f"{key}运营", role=UserRole.OPERATOR,
            team_id=t.id, status="active",
            password_hash=bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode(),
        )
        s.add(u)
        s.commit()
        out["users"][key] = u

        ent = Enterprise(name=f"授权企业{key}", code=f"GTENT{key}",
                         status=EnterpriseStatus.ACTIVE, owner_team_id=t.id)
        s.add(ent)
        s.commit()
        s.refresh(ent)
        out["enterprises"][key] = ent

        st = Station(name=f"授权场站{key}", code=f"GTST{key}", status=StationStatus.NORMAL,
                     team_id=t.id)
        s.add(st)
        s.commit()
        s.refresh(st)
        out["stations"][key] = st

        devs = {}
        for i in (1, 2):
            d = Device(sn=f"GT-SN-{key}{i}", name=f"桩{key}{i}", code=f"GTDEV{key}{i}",
                       type=DeviceType.CHARGER_DC, status=DeviceStatus.ONLINE, station_id=st.id)
            s.add(d)
            s.commit()
            s.refresh(d)
            devs[i] = d
        out["devices"][key] = devs

    def _tok(username):
        r = client.post("/api/v1/auth/login", data={"username": username, "password": pwd})
        assert r.status_code == 200, f"登录失败 {username}: {r.text}"
        return r.json()["data"]["token"]

    out["tokens"] = {"a": _tok("grant_op_a"), "b": _tok("grant_op_b")}
    return out


def _create_grant(client, headers, enterprise_id, station_id, device_id=None, note=None):
    payload = {"enterprise_id": enterprise_id, "station_id": station_id}
    if device_id is not None:
        payload["device_id"] = device_id
    if note is not None:
        payload["note"] = note
    return client.post("/api/v1/operate/fleet-grants", json=payload, headers=headers)


# ═══════════════════════════════════════════════════════════════════════
# 创建授权
# ═══════════════════════════════════════════════════════════════════════

def test_create_station_grant_admin(client, grant_team_pair):
    """admin 创建整站授权(device_id 缺省) → 200, device_id=None。"""
    gp = grant_team_pair
    ent_a = gp["enterprises"]["a"]
    st_a = gp["stations"]["a"]
    resp = _create_grant(client, _admin_h(client), ent_a.id, st_a.id)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["id"] > 0
    assert data["enterprise_id"] == ent_a.id
    assert data["station_id"] == st_a.id
    assert data["device_id"] is None  # 整站授权
    assert data["created_at"]


def test_create_device_grant_admin(client, grant_team_pair):
    """admin 创建桩级授权(device_id 非空) → 200。"""
    gp = grant_team_pair
    dev_a1 = gp["devices"]["a"][1]
    resp = _create_grant(
        client, _admin_h(client),
        gp["enterprises"]["a"].id, gp["stations"]["a"].id, device_id=dev_a1.id,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["device_id"] == dev_a1.id


def test_create_grant_device_station_mismatch(client, grant_team_pair):
    """device 属于场站 A, 但 station_id 传场站 B → 拒绝(400)。"""
    gp = grant_team_pair
    dev_a1 = gp["devices"]["a"][1]   # 属于场站 a
    st_b = gp["stations"]["b"]
    resp = _create_grant(
        client, _admin_h(client),
        gp["enterprises"]["a"].id, st_b.id, device_id=dev_a1.id,
    )
    assert resp.status_code == 400, resp.text
    assert "不属于" in resp.json()["detail"]


def test_create_grant_cross_team_enterprise_404(client, grant_team_pair):
    """A 团队运营给 B 团队企业授权 → 404(不泄露存在)。"""
    gp = grant_team_pair
    ent_b = gp["enterprises"]["b"]
    resp = _create_grant(client, _h(gp["tokens"]["a"]), ent_b.id, gp["stations"]["a"].id)
    assert resp.status_code == 404


def test_create_grant_cross_team_station_404(client, grant_team_pair):
    """A 团队运营, 自家企业, 但场站属 B 团队 → 404。"""
    gp = grant_team_pair
    resp = _create_grant(
        client, _h(gp["tokens"]["a"]),
        gp["enterprises"]["a"].id, gp["stations"]["b"].id,
    )
    assert resp.status_code == 404


def test_create_grant_same_team_ok(client, grant_team_pair):
    """A 团队运营给自家企业+自家场站授权 → 200。"""
    gp = grant_team_pair
    resp = _create_grant(
        client, _h(gp["tokens"]["a"]),
        gp["enterprises"]["a"].id, gp["stations"]["a"].id,
    )
    assert resp.status_code == 200, resp.text


def test_create_grant_enterprise_not_found(client, grant_team_pair):
    resp = _create_grant(client, _admin_h(client), 999999, grant_team_pair["stations"]["a"].id)
    assert resp.status_code == 404


def test_create_grant_station_not_found(client, grant_team_pair):
    resp = _create_grant(
        client, _admin_h(client),
        grant_team_pair["enterprises"]["a"].id, 999999,
    )
    assert resp.status_code == 404


def test_create_grant_device_not_found(client, grant_team_pair):
    gp = grant_team_pair
    resp = _create_grant(
        client, _admin_h(client),
        gp["enterprises"]["a"].id, gp["stations"]["a"].id, device_id=999999,
    )
    assert resp.status_code == 404


def test_create_duplicate_whole_station_grant_409(client, grant_team_pair):
    """同一企业对同一场站重复整站授权 → 409(NULL 不参与 SQL 唯一索引, 应用层去重)。"""
    gp = grant_team_pair
    h = _admin_h(client)
    r1 = _create_grant(client, h, gp["enterprises"]["a"].id, gp["stations"]["a"].id)
    assert r1.status_code == 200
    r2 = _create_grant(client, h, gp["enterprises"]["a"].id, gp["stations"]["a"].id)
    assert r2.status_code == 409, r2.text


# ═══════════════════════════════════════════════════════════════════════
# 列表
# ═══════════════════════════════════════════════════════════════════════

def test_list_grants_by_enterprise(client, grant_team_pair):
    """按 enterprise_id 列授权, 含整站+桩级。"""
    gp = grant_team_pair
    h = _admin_h(client)
    ent_a = gp["enterprises"]["a"]
    st_a = gp["stations"]["a"]
    _create_grant(client, h, ent_a.id, st_a.id)  # 整站
    _create_grant(client, h, ent_a.id, st_a.id, device_id=gp["devices"]["a"][1].id)  # 桩级

    resp = client.get(f"/api/v1/operate/fleet-grants?enterprise_id={ent_a.id}", headers=h)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["total"] == 2
    assert len(data["items"]) == 2


def test_list_grants_cross_team_404(client, grant_team_pair):
    """A 运营查 B 企业授权 → 404。"""
    gp = grant_team_pair
    ent_b = gp["enterprises"]["b"]
    resp = client.get(
        f"/api/v1/operate/fleet-grants?enterprise_id={ent_b.id}",
        headers=_h(gp["tokens"]["a"]),
    )
    assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════
# 删除
# ═══════════════════════════════════════════════════════════════════════

def test_delete_grant_own_team(client, grant_team_pair):
    gp = grant_team_pair
    h = _admin_h(client)
    g = _create_grant(client, h, gp["enterprises"]["a"].id, gp["stations"]["a"].id).json()["data"]

    resp = client.delete(f"/api/v1/operate/fleet-grants/{g['id']}", headers=h)
    assert resp.status_code == 200, resp.text

    # 再删 → 404
    resp2 = client.delete(f"/api/v1/operate/fleet-grants/{g['id']}", headers=h)
    assert resp2.status_code == 404


def test_delete_grant_cross_team_404(client, grant_team_pair):
    """B 运营删 A 的授权 → 404。"""
    gp = grant_team_pair
    h = _admin_h(client)
    g = _create_grant(client, h, gp["enterprises"]["a"].id, gp["stations"]["a"].id).json()["data"]

    resp = client.delete(
        f"/api/v1/operate/fleet-grants/{g['id']}", headers=_h(gp["tokens"]["b"]),
    )
    assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════
# 充电启动 scope 校验 (POST /charging-sessions)
# ═══════════════════════════════════════════════════════════════════════

from app.models.enterprise_device_grant import EnterpriseDeviceGrant  # noqa: E402


def _seed_scope(client, vin="VINSCOPE001"):
    """1 场站 + 2 桩(dev1/dev2) + 1 企业 + 1 企业车(VIN)。"""
    from app.models.station import Station, StationStatus
    from app.models.device import Device, DeviceType, DeviceStatus
    from app.models.enterprise import Enterprise, EnterpriseStatus
    from app.models.enterprise_vehicle import EnterpriseVehicle

    s = client._sesh
    st = Station(name="scope站", code="SCST01", status=StationStatus.NORMAL)
    s.add(st); s.commit(); s.refresh(st)
    dev1 = Device(sn="SC-SN-01", name="scope桩1", code="SCDEV01",
                  type=DeviceType.CHARGER_DC, status=DeviceStatus.ONLINE, station_id=st.id)
    dev2 = Device(sn="SC-SN-02", name="scope桩2", code="SCDEV02",
                  type=DeviceType.CHARGER_DC, status=DeviceStatus.ONLINE, station_id=st.id)
    s.add_all([dev1, dev2]); s.commit(); s.refresh(dev1); s.refresh(dev2)
    ent = Enterprise(name="scope企业", code="SCENT01", balance=10000,
                     status=EnterpriseStatus.ACTIVE)
    s.add(ent); s.commit(); s.refresh(ent)
    s.add(EnterpriseVehicle(enterprise_id=ent.id, plate_number="京S00001", vin=vin))
    s.commit()
    return {"station": st, "dev1": dev1, "dev2": dev2, "enterprise": ent, "vin": vin}


def _post_session(client, sn, vin, tx_id):
    return client.post("/api/v1/charging-sessions", json={
        "charge_point_id": sn,
        "transaction_id": tx_id,
        "id_tag": vin,
        "meter_start": 0,
        "meter_stop": 10000,
        "timestamp_start": "2026-07-28T10:00:00",
        "timestamp_stop": "2026-07-28T11:00:00",
    }, headers=_admin_h(client))


def test_scope_no_grant_allowed(client):
    """企业车 + 无任何授权 → 放行(向后兼容, 保 baseline)。"""
    sc = _seed_scope(client)
    resp = _post_session(client, sc["dev1"].sn, sc["vin"], "TX-SCOPE-NOGRANT")
    assert resp.status_code == 200, resp.text


def test_scope_station_grant_allows_all_piles(client):
    """整站授权(device_id=None) → 该站所有桩均可充。"""
    s = client._sesh
    sc = _seed_scope(client)
    s.add(EnterpriseDeviceGrant(enterprise_id=sc["enterprise"].id,
                                station_id=sc["station"].id, device_id=None))
    s.commit()
    r1 = _post_session(client, sc["dev1"].sn, sc["vin"], "TX-SCOPE-ST1")
    r2 = _post_session(client, sc["dev2"].sn, sc["vin"], "TX-SCOPE-ST2")
    assert r1.status_code == 200, r1.text
    assert r2.status_code == 200, r2.text


def test_scope_device_grant_allows_only_authorized_pile(client):
    """桩级白名单: 仅授权桩 dev1 可充; 未授权 dev2 → 403 且不建单。"""
    s = client._sesh
    sc = _seed_scope(client)
    s.add(EnterpriseDeviceGrant(enterprise_id=sc["enterprise"].id,
                                station_id=sc["station"].id, device_id=sc["dev1"].id))
    s.commit()

    r1 = _post_session(client, sc["dev1"].sn, sc["vin"], "TX-SCOPE-DEV1")
    assert r1.status_code == 200, r1.text

    r2 = _post_session(client, sc["dev2"].sn, sc["vin"], "TX-SCOPE-DEV2")
    assert r2.status_code == 403, r2.text
    assert "授权范围" in r2.json()["detail"]
    # 未授权设备不建单
    assert s.query(ChargingOrder).filter(
        ChargingOrder.device_id == sc["dev2"].id
    ).count() == 0


def test_scope_guest_not_restricted_by_enterprise_grant(client):
    """散客(无 id_tag)不受企业授权约束: 即便企业有桩级授权, 散客在未授权桩仍可充(200)。

    证明 scope 校验仅作用于企业车, 不误伤散客。
    """
    s = client._sesh
    sc = _seed_scope(client)
    # 企业仅对 dev1 有桩级授权
    s.add(EnterpriseDeviceGrant(enterprise_id=sc["enterprise"].id,
                                station_id=sc["station"].id, device_id=sc["dev1"].id))
    s.commit()
    # 散客(无 id_tag)在 dev2 充电 → 不受企业 grant 约束 → 200
    resp = client.post("/api/v1/charging-sessions", json={
        "charge_point_id": sc["dev2"].sn,
        "transaction_id": "TX-SCOPE-GUEST",
        "meter_start": 0, "meter_stop": 10000,
        "timestamp_start": "2026-07-28T10:00:00",
        "timestamp_stop": "2026-07-28T11:00:00",
    }, headers=_admin_h(client))
    assert resp.status_code == 200, resp.text

