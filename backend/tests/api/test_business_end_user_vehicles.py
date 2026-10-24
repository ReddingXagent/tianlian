"""契约§8 P2 §8.6: C端用户车辆管理 测试 (卡 36396f29)."""

from app.models.end_user_vehicle import EndUserVehicle

AUTH_URL = "/api/v1/business/auth/wx-login"
VEHICLES_URL = "/api/v1/business/vehicles"


def _body(response, status=200):
    assert response.status_code == status, response.text
    assert response.json()["code"] == 0, response.text
    return response.json()["data"]


def _login(client, code):
    return _body(client.post(AUTH_URL, json={"code": code}))["token"]


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _add(client, token, plate, vin=None, **extra):
    payload = {"plate_number": plate, **extra}
    if vin is not None:
        payload["vin"] = vin
    return client.post(VEHICLES_URL, json=payload, headers=_headers(token))


def test_add_and_list_vehicle(client):
    token = _login(client, "v-user-1")
    first = _body(_add(client, token, "川A12345", vin="LSVAA1234EXXXXXXX", brand="比亚迪"))
    assert first["plate_number"] == "川A12345"
    assert first["vin"] == "LSVAA1234EXXXXXXX"
    assert first["is_default"] is True  # 首辆车自动默认

    second = _body(_add(client, token, "川B67890"))
    assert second["vin"] is None  # VIN 可空
    assert second["is_default"] is False

    data = _body(client.get(VEHICLES_URL, headers=_headers(token)))
    assert data["total"] == 2
    plates = [item["plate_number"] for item in data["items"]]
    assert plates == ["川A12345", "川B67890"]  # 默认车在前
    assert data["items"][0]["brand"] == "比亚迪"


def test_add_vehicle_validation(client):
    token = _login(client, "v-user-2")
    # 车牌必填且 strip 后非空
    assert _add(client, token, "   ").status_code == 422
    assert client.post(
        VEHICLES_URL, json={}, headers=_headers(token)
    ).status_code == 422
    # vin 非 17 位
    assert _add(client, token, "川A11111", vin="SHORT").status_code == 422


def test_add_vehicle_duplicate_plate_409(client):
    token = _login(client, "v-user-3")
    assert _add(client, token, "川C11111").status_code == 200
    resp = _add(client, token, "川C11111")
    assert resp.status_code == 409
    assert resp.json()["detail"] == "VEHICLE_DUPLICATE_PLATE"


def test_add_vehicle_race_duplicate_plate_409_not_500(client):
    """并发双击竞态: 预检查漏检, INSERT 撞 uq_end_user_vehicle_plate (卡 d74344ed).

    模拟: patch Session.commit —— 本请求 commit 前, 用独立连接先插入与 pending
    车辆同 (end_user_id, plate_number) 的行(并发请求先行落库且已提交), 随后原
    commit 必撞唯一约束 → IntegrityError。契约§8.6: 回查后 409, 非 500。
    """
    from unittest.mock import patch

    from sqlalchemy import text

    token = _login(client, "v-user-3x")
    session = client._sesh
    orig_commit = type(session).commit
    fired = {"on": True}

    def racing_commit(self):
        pending = [o for o in self.new if isinstance(o, EndUserVehicle)]
        if fired["on"] and pending:
            fired["on"] = False
            v = pending[0]
            conn = self.get_bind().connect()
            try:
                conn.execute(
                    text(
                        "INSERT INTO end_user_vehicles (end_user_id, plate_number)"
                        " VALUES (:u, :p)"
                    ),
                    {"u": v.end_user_id, "p": v.plate_number},
                )
                conn.commit()
            finally:
                conn.close()
        return orig_commit(self)

    with patch.object(type(session), "commit", racing_commit):
        resp = _add(client, token, "川C33333")

    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"] == "VEHICLE_DUPLICATE_PLATE"
    # 只剩并发方那一行, 本请求的 INSERT 未落库
    assert session.query(EndUserVehicle).count() == 1


def test_duplicate_plate_across_users_allowed(client):
    """不同 C 端用户可以有同名车牌 —— C端车辆是私有资产, 非车队全局唯一."""
    token_a = _login(client, "v-user-4a")
    token_b = _login(client, "v-user-4b")
    assert _add(client, token_a, "川D99999").status_code == 200
    assert _add(client, token_b, "川D99999").status_code == 200


def test_set_default_vehicle(client):
    token = _login(client, "v-user-5")
    a = _body(_add(client, token, "川E00001"))
    b = _body(_add(client, token, "川E00002"))

    data = _body(client.patch(
        f"{VEHICLES_URL}/{b['vehicle_id']}/default", headers=_headers(token)
    ))
    assert data["is_default"] is True

    session = client._sesh
    rows = session.query(EndUserVehicle).order_by(EndUserVehicle.id).all()
    assert [r.is_default for r in rows] == [False, True]  # 原默认被清除

    # 幂等: 已是默认再设一次仍成功
    again = _body(client.patch(
        f"{VEHICLES_URL}/{b['vehicle_id']}/default", headers=_headers(token)
    ))
    assert again["is_default"] is True


def test_delete_vehicle(client):
    token = _login(client, "v-user-6")
    a = _body(_add(client, token, "川F00001"))
    data = _body(client.delete(f"{VEHICLES_URL}/{a['vehicle_id']}", headers=_headers(token)))
    assert data["deleted"] is True
    assert _body(client.get(VEHICLES_URL, headers=_headers(token)))["total"] == 0
    # 再删同一辆 → 404
    assert client.delete(
        f"{VEHICLES_URL}/{a['vehicle_id']}", headers=_headers(token)
    ).status_code == 404


def test_vehicle_isolation_between_users(client):
    """他人车辆 404: 查不到、删不掉、设不了默认."""
    owner = _login(client, "v-owner")
    other = _login(client, "v-other")
    vehicle = _body(_add(client, owner, "川G00001"))

    assert _body(client.get(VEHICLES_URL, headers=_headers(other)))["total"] == 0
    assert client.delete(
        f"{VEHICLES_URL}/{vehicle['vehicle_id']}", headers=_headers(other)
    ).status_code == 404
    assert client.patch(
        f"{VEHICLES_URL}/{vehicle['vehicle_id']}/default", headers=_headers(other)
    ).status_code == 404


def test_operate_token_rejected(client):
    """运营 token (aud 不符) 调 C端车辆端点必须 401."""
    resp = client.post(
        "/api/v1/auth/login", data={"username": "admin", "password": "admin123"}
    )
    assert resp.status_code == 200
    headers = {"Authorization": f"Bearer {resp.json()['data']['token']}"}

    assert client.get(VEHICLES_URL, headers=headers).status_code == 401
    assert client.post(
        VEHICLES_URL, json={"plate_number": "川H00001"}, headers=headers
    ).status_code == 401


def test_anonymous_rejected(client):
    assert client.get(VEHICLES_URL).status_code == 401
