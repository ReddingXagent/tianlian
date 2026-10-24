"""契约§8 P2 §8.7: C端用户收藏场站 测试 (卡 36396f29)."""

import uuid

from app.models.end_user_favorite import EndUserFavorite
from app.models.station import Station, StationStatus

AUTH_URL = "/api/v1/business/auth/wx-login"
FAVORITES_URL = "/api/v1/business/favorites"


def _body(response, status=200):
    assert response.status_code == status, response.text
    assert response.json()["code"] == 0, response.text
    return response.json()["data"]


def _login(client, code):
    return _body(client.post(AUTH_URL, json={"code": code}))["token"]


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _seed_station(session, *, name="收藏测试站", status=StationStatus.NORMAL, power=120.0):
    st = Station(
        name=name,
        code=f"ST{uuid.uuid4().hex[:6].upper()}",
        address="测试地址 88 号",
        city="成都",
        status=status,
        total_power=power,
        gun_count=8,
    )
    session.add(st)
    session.commit()
    session.refresh(st)
    return st


def test_add_and_list_favorite_with_station_summary(client):
    session = client._sesh
    station = _seed_station(session, name="光储充一号站")
    token = _login(client, "fav-user-1")

    data = _body(client.post(
        FAVORITES_URL, json={"station_id": station.id}, headers=_headers(token)
    ))
    assert data["already"] is False
    assert data["station_id"] == station.id

    listing = _body(client.get(FAVORITES_URL, headers=_headers(token)))
    assert listing["total"] == 1
    item = listing["items"][0]
    assert item["station_id"] == station.id
    assert item["favorite_id"] == data["favorite_id"]
    summary = item["station"]
    assert summary["name"] == "光储充一号站"
    assert summary["address"] == "测试地址 88 号"
    assert summary["city"] == "成都"
    assert summary["status"] == "normal"
    assert summary["total_power"] == 120.0
    assert summary["gun_count"] == 8


def test_add_favorite_idempotent(client):
    session = client._sesh
    station = _seed_station(session)
    token = _login(client, "fav-user-2")

    first = _body(client.post(
        FAVORITES_URL, json={"station_id": station.id}, headers=_headers(token)
    ))
    second = _body(client.post(
        FAVORITES_URL, json={"station_id": station.id}, headers=_headers(token)
    ))
    assert second["already"] is True
    assert second["favorite_id"] == first["favorite_id"]  # 返回原收藏, 不新建

    assert client._sesh.query(EndUserFavorite).count() == 1


def test_add_favorite_race_returns_already_true_not_500(client):
    """并发双击竞态: 预检查漏检, INSERT 撞 uq_end_user_favorite_station (卡 d74344ed).

    模拟: patch Session.commit —— 本请求 commit 前, 用独立连接先插入与 pending
    收藏同 (end_user_id, station_id) 的行(并发请求先行落库且已提交), 随后原
    commit 必撞唯一约束 → IntegrityError。契约§8.7 幂等: 回查后 already:true
    + 原 favorite_id, 非 500。
    """
    from unittest.mock import patch

    from sqlalchemy import text

    session = client._sesh
    station = _seed_station(session)
    token = _login(client, "fav-user-2x")

    orig_commit = type(session).commit
    fired = {"on": True, "racing_id": None}

    def racing_commit(self):
        pending = [o for o in self.new if isinstance(o, EndUserFavorite)]
        if fired["on"] and pending:
            fired["on"] = False
            f = pending[0]
            conn = self.get_bind().connect()
            try:
                conn.execute(
                    text(
                        "INSERT INTO end_user_favorites (end_user_id, station_id)"
                        " VALUES (:u, :s)"
                    ),
                    {"u": f.end_user_id, "s": f.station_id},
                )
                conn.commit()
                fired["racing_id"] = conn.execute(
                    text("SELECT last_insert_rowid()")
                ).scalar()
            finally:
                conn.close()
        return orig_commit(self)

    with patch.object(type(session), "commit", racing_commit):
        resp = client.post(
            FAVORITES_URL, json={"station_id": station.id}, headers=_headers(token)
        )

    data = _body(resp)
    assert data["already"] is True
    assert data["favorite_id"] == fired["racing_id"]  # 返回并发方原收藏, 不新建
    assert session.query(EndUserFavorite).count() == 1  # 未产生第二行


def test_add_favorite_station_not_found_404(client):
    token = _login(client, "fav-user-3")
    resp = client.post(
        FAVORITES_URL, json={"station_id": 99999999}, headers=_headers(token)
    )
    assert resp.status_code == 404


def test_delete_favorite_idempotent(client):
    session = client._sesh
    station = _seed_station(session)
    token = _login(client, "fav-user-4")

    _body(client.post(
        FAVORITES_URL, json={"station_id": station.id}, headers=_headers(token)
    ))
    data = _body(client.delete(
        f"{FAVORITES_URL}/{station.id}", headers=_headers(token)
    ))
    assert data == {"station_id": station.id, "deleted": True}

    # 再删(本就没有) → 仍成功, deleted=false
    data2 = _body(client.delete(
        f"{FAVORITES_URL}/{station.id}", headers=_headers(token)
    ))
    assert data2 == {"station_id": station.id, "deleted": False}


def test_favorites_isolation_and_order(client):
    session = client._sesh
    st1 = _seed_station(session, name="早收藏站")
    st2 = _seed_station(session, name="晚收藏站")
    mine = _login(client, "fav-mine")
    other = _login(client, "fav-other")

    _body(client.post(FAVORITES_URL, json={"station_id": st1.id}, headers=_headers(other)))
    _body(client.post(FAVORITES_URL, json={"station_id": st1.id}, headers=_headers(mine)))
    _body(client.post(FAVORITES_URL, json={"station_id": st2.id}, headers=_headers(mine)))

    listing = _body(client.get(FAVORITES_URL, headers=_headers(mine)))
    assert listing["total"] == 2  # 只见本人收藏
    names = [item["station"]["name"] for item in listing["items"]]
    assert names == ["晚收藏站", "早收藏站"]  # 新收藏在前(倒序)

    # 删除他人收藏 → 幂等成功但 deleted=false(看不见即不存在)
    data = _body(client.delete(
        f"{FAVORITES_URL}/{st2.id}", headers=_headers(other)
    ))
    assert data["deleted"] is False
    assert session.query(EndUserFavorite).count() == 3  # mine 的收藏未被动


def test_favorite_deleted_station_returns_null_summary(client):
    """场站被物理删除: 收藏行保留, station=null."""
    session = client._sesh
    station = _seed_station(session, name="将被删除站")
    token = _login(client, "fav-user-5")
    _body(client.post(
        FAVORITES_URL, json={"station_id": station.id}, headers=_headers(token)
    ))

    session.query(Station).filter(Station.id == station.id).delete()
    session.commit()

    listing = _body(client.get(FAVORITES_URL, headers=_headers(token)))
    assert listing["total"] == 1
    assert listing["items"][0]["station"] is None


def test_operate_and_anonymous_rejected(client):
    resp = client.post(
        "/api/v1/auth/login", data={"username": "admin", "password": "admin123"}
    )
    assert resp.status_code == 200
    ops_headers = {"Authorization": f"Bearer {resp.json()['data']['token']}"}

    assert client.get(FAVORITES_URL, headers=ops_headers).status_code == 401
    assert client.post(
        FAVORITES_URL, json={"station_id": 1}, headers=ops_headers
    ).status_code == 401
    assert client.delete(f"{FAVORITES_URL}/1", headers=ops_headers).status_code == 401
    assert client.get(FAVORITES_URL).status_code == 401
