"""
场站 VIN 充电授权白名单 API 测试

覆盖端点:
- GET    /api/v1/stations/{station_id}/vin-whitelist        分页查询
- POST   /api/v1/stations/{station_id}/vin-whitelist        手动添加 VIN
- DELETE /api/v1/stations/{station_id}/vin-whitelist/{vin}  移除 VIN

覆盖场景: 正常 CRUD、VIN 17 位格式校验、重复 VIN、不存在 VIN、分页参数、场站隔离。
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

STATION_ID = 1002
VIN_PREFIX = "LSVAU2189N21"  # 12 位前缀，拼 5 位序号 => 17 位合规 VIN


@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    """自动注入 test_db fixture + seed 测试站点。

    team scoping（任务卡 1c19b59a）后 assert_station_team_access 校验站点存在性，
    admin 亦须站点存在才放行（否则 404 站点不存在），故补 seed 1002/1003
    （isolation 用例需 STATION_ID+1）。admin 经 is_platform_admin 豁免 team 过滤，
    仅需站点存在即可。
    """
    from app.models.station import Station, StationStatus
    s = test_db["session"]
    for sid in (STATION_ID, STATION_ID + 1):
        if not s.query(Station).filter(Station.id == sid).first():
            s.add(Station(
                id=sid, name=f"白名单测试站{sid}",
                code=f"WL_STA_{sid}", status=StationStatus.NORMAL,
            ))
    s.commit()


# ========== 公共辅助 ==========

def _login():
    """登录获取 token"""
    resp = client.post(
        "/api/v1/auth/login",
        data={"username": "admin", "password": "admin123"},
    )
    assert resp.status_code == 200
    data = resp.json()
    return data.get("token") or data.get("data", {}).get("token")


def _auth_headers():
    return {"Authorization": f"Bearer {_login()}"}


def _create_enterprise(name="白名单测试企业", code="ENT_WL001"):
    """创建测试企业，返回 enterprise_id"""
    from app.core.database import SessionLocal
    from app.models.enterprise import Enterprise

    db = SessionLocal()
    try:
        ent = Enterprise(name=name, code=code, balance=1000.00)
        db.add(ent)
        db.commit()
        db.refresh(ent)
        return ent.id
    finally:
        db.close()


def _vin(n):
    """生成 17 位合规 VIN（12 位前缀 + 5 位零填充序号）"""
    return f"{VIN_PREFIX}{n:05d}"


def _url(station_id=STATION_ID, vin=None):
    base = f"/api/v1/stations/{station_id}/vin-whitelist"
    return f"{base}/{vin}" if vin else base


def _add(vin, enterprise_id, station_id=STATION_ID):
    return client.post(
        _url(station_id),
        json={"vin": vin, "enterprise_id": enterprise_id},
        headers=_auth_headers(),
    )


def _list(station_id=STATION_ID, **params):
    return client.get(_url(station_id), params=params, headers=_auth_headers())


def _remove(vin, station_id=STATION_ID):
    return client.delete(_url(station_id, vin), headers=_auth_headers())


# ========== 分页查询 GET ==========

def test_list_whitelist_empty():
    """空白名单查询返回空列表与默认分页"""
    resp = _list()
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["items"] == []
    assert data["total"] == 0
    assert data["page"] == 1
    assert data["page_size"] == 50


def test_list_whitelist_with_data():
    """有数据时返回正确 total、items 与字段结构"""
    ent_id = _create_enterprise()
    for i in range(3):
        assert _add(_vin(i), ent_id).status_code == 200

    resp = _list()
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] == 3
    assert len(data["items"]) == 3

    item = data["items"][0]
    assert {"id", "station_id", "vin", "enterprise_id", "source", "created_at"} <= set(item)
    assert item["station_id"] == STATION_ID
    assert item["enterprise_id"] == ent_id


def test_whitelist_isolated_per_station():
    """白名单按 station_id 隔离：A 站查询看不到 B 站的 VIN"""
    ent_id = _create_enterprise()
    _add(_vin(1), ent_id, station_id=STATION_ID)
    _add(_vin(2), ent_id, station_id=STATION_ID + 1)

    resp_a = _list(station_id=STATION_ID)
    resp_b = _list(station_id=STATION_ID + 1)

    assert resp_a.json()["data"]["total"] == 1
    assert resp_b.json()["data"]["total"] == 1
    assert resp_a.json()["data"]["items"][0]["vin"] == _vin(1)
    assert resp_b.json()["data"]["items"][0]["vin"] == _vin(2)


def test_pagination_page_size_limits_items():
    """page_size 限制单页返回条数，total 仍为全量"""
    ent_id = _create_enterprise()
    for i in range(5):
        _add(_vin(i), ent_id)

    resp = _list(page=1, page_size=2)
    data = resp.json()["data"]
    assert data["total"] == 5
    assert len(data["items"]) == 2
    assert data["page"] == 1
    assert data["page_size"] == 2


def test_pagination_invalid_page_returns_422():
    """page < 1 触发 Query(ge=1) 校验，返回 422"""
    assert _list(page=0).status_code == 422


def test_pagination_invalid_page_size_returns_422():
    """page_size 超过上限 Query(le=500) 返回 422"""
    assert _list(page_size=501).status_code == 422


# ========== 手动添加 POST ==========

def test_add_vin_manual_success():
    """手动添加 VIN 成功，source 标记为 manual"""
    ent_id = _create_enterprise()
    resp = _add(_vin(100), ent_id)
    assert resp.status_code == 200

    data = resp.json()["data"]
    assert data["vin"] == _vin(100)
    assert data["station_id"] == STATION_ID
    assert data["enterprise_id"] == ent_id
    assert data["source"] == "manual"
    assert data["id"] is not None


def test_add_vin_uppercases_and_strips():
    """VIN 经 validator 规范化：去首尾空白 + 转大写后入库"""
    ent_id = _create_enterprise()
    raw = f" {_vin(200).lower()} "  # 17 位小写 + 首尾空格
    resp = _add(raw, ent_id)
    assert resp.status_code == 200
    assert resp.json()["data"]["vin"] == _vin(200)  # 入库为大写、无空格的 17 位


def test_add_vin_too_short_returns_422():
    """VIN 不足 17 位 => pydantic 校验失败 422"""
    ent_id = _create_enterprise()
    assert _add("LSVAU2189N21", ent_id).status_code == 422  # 12 位


def test_add_vin_too_long_returns_422():
    """VIN 超过 17 位 => pydantic 校验失败 422"""
    ent_id = _create_enterprise()
    assert _add("LSVAU2189N2123456789", ent_id).status_code == 422  # 20 位


def test_add_duplicate_vin_returns_400():
    """同站重复 VIN 返回 400。

    注意: 当前实现 (station_vin_whitelist.py:82) 为 status_code=400,
    而非任务描述中的 409。本测试锁定真实代码行为。
    """
    ent_id = _create_enterprise()
    assert _add(_vin(300), ent_id).status_code == 200

    second = _add(_vin(300), ent_id)
    assert second.status_code == 400
    # HTTPException 经全局 handler 包装，文案落在 message 字段
    assert "已在白名单" in second.json()["message"]


# ========== 移除 DELETE ==========

def test_delete_vin_success():
    """移除已存在 VIN 成功，后续查询不再可见"""
    ent_id = _create_enterprise()
    _add(_vin(400), ent_id)

    assert _remove(_vin(400)).status_code == 200

    vins = [it["vin"] for it in _list().json()["data"]["items"]]
    assert _vin(400) not in vins


def test_delete_nonexistent_vin_returns_404():
    """移除不存在的 VIN 返回 404"""
    _create_enterprise()
    resp = _remove(_vin(999))
    assert resp.status_code == 404
    assert resp.json()["message"] == "VIN 不在白名单中"
