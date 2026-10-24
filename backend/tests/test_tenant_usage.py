"""
租户用量统计 API 测试
覆盖: /tenants/{id}/usage — 鉴权、空历史、用量记录创建+查询、日期筛选、聚合容错
"""
from datetime import date
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    """自动注入 test_db fixture，每个测试使用独立数据库"""
    pass


def _login():
    """登录获取 token"""
    resp = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    data = resp.json()
    return data.get("token") or data.get("data", {}).get("token")


def _auth_headers():
    return {"Authorization": f"Bearer {_login()}"}


def _create_tenant(name="用量测试租户", code="USAGE_001"):
    """创建测试租户，返回 tenant_id"""
    resp = client.post(
        "/api/v1/tenants",
        json={"name": name, "code": code},
        headers=_auth_headers(),
    )
    assert resp.status_code == 200, f"创建租户失败: {resp.text}"
    return resp.json()["data"]["id"]


def _insert_usage(tenant_id, record_date, station_count=0, device_count=0,
                  user_count=0, storage_used_gb=0.0, api_calls_today=0):
    """直接向测试库写入一条用量快照（绕过 API，模拟定时任务落库）"""
    from app.models.tenant_usage import TenantUsage
    import app.core.database as db_module
    s = db_module.SessionLocal()
    try:
        s.add(TenantUsage(
            tenant_id=tenant_id,
            record_date=record_date,
            station_count=station_count,
            device_count=device_count,
            user_count=user_count,
            storage_used_gb=storage_used_gb,
            api_calls_today=api_calls_today,
        ))
        s.commit()
    finally:
        s.close()


# ========== 鉴权检查 ==========

def test_get_usage_requires_auth():
    """无 token 访问用量应返回401"""
    client.headers.pop("Authorization", None)  # 清除 autouse 注入的 admin token，测真匿名拒绝
    assert client.get("/api/v1/tenants/1/usage").status_code == 401


# ========== 404 ==========

def test_get_usage_tenant_not_found():
    """不存在的租户查询用量应返回404"""
    resp = client.get("/api/v1/tenants/999999/usage", headers=_auth_headers())
    assert resp.status_code == 404


# ========== 空历史 + 实时聚合容错 ==========

def test_get_usage_empty_history():
    """无历史快照时返回空 history，current 因 Station/Device/User 无 tenant_id 全为 0"""
    tenant_id = _create_tenant("空用量租户", "EMPTY_USAGE_001")
    resp = client.get(f"/api/v1/tenants/{tenant_id}/usage", headers=_auth_headers())
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["tenant_id"] == tenant_id
    assert data["history"] == []
    assert data["current"] == {
        "station_count": 0,
        "device_count": 0,
        "user_count": 0,
    }


# ========== 用量记录查询 ==========

def test_get_usage_with_history():
    """写入快照后查询应返回历史趋势，按日期升序"""
    tenant_id = _create_tenant("历史用量租户", "HISTORY_USAGE_001")
    _insert_usage(tenant_id, date(2026, 7, 23), station_count=3, device_count=30,
                  user_count=5, storage_used_gb=1.2, api_calls_today=120)
    _insert_usage(tenant_id, date(2026, 7, 25), station_count=5, device_count=50,
                  user_count=8, storage_used_gb=2.5, api_calls_today=200)

    resp = client.get(f"/api/v1/tenants/{tenant_id}/usage", headers=_auth_headers())
    assert resp.status_code == 200
    history = resp.json()["data"]["history"]
    assert len(history) == 2
    # 升序：7/23 在前
    assert history[0]["record_date"] == "2026-07-23"
    assert history[0]["station_count"] == 3
    assert history[1]["record_date"] == "2026-07-25"
    assert history[1]["api_calls_today"] == 200
    assert history[1]["storage_used_gb"] == 2.5


# ========== 日期筛选 ==========

def test_get_usage_date_filter():
    """date_from/date_to 筛选应只返回区间内的快照"""
    tenant_id = _create_tenant("筛选用量租户", "FILTER_USAGE_001")
    _insert_usage(tenant_id, date(2026, 7, 20), station_count=1)
    _insert_usage(tenant_id, date(2026, 7, 23), station_count=2)
    _insert_usage(tenant_id, date(2026, 7, 25), station_count=3)
    _insert_usage(tenant_id, date(2026, 7, 28), station_count=4)

    # 区间 [2026-07-23, 2026-07-25]
    resp = client.get(
        f"/api/v1/tenants/{tenant_id}/usage?date_from=2026-07-23&date_to=2026-07-25",
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    history = resp.json()["data"]["history"]
    assert len(history) == 2
    assert {h["record_date"] for h in history} == {"2026-07-23", "2026-07-25"}


def test_get_usage_date_from_only():
    """仅 date_from 应返回该日期及之后的快照"""
    tenant_id = _create_tenant("从日用量租户", "FROM_USAGE_001")
    _insert_usage(tenant_id, date(2026, 7, 20), station_count=1)
    _insert_usage(tenant_id, date(2026, 7, 25), station_count=2)

    resp = client.get(
        f"/api/v1/tenants/{tenant_id}/usage?date_from=2026-07-23",
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    history = resp.json()["data"]["history"]
    assert len(history) == 1
    assert history[0]["record_date"] == "2026-07-25"


def test_get_usage_invalid_date_format():
    """非法日期格式应返回400"""
    tenant_id = _create_tenant("非法日期租户", "BADDATE_USAGE_001")
    resp = client.get(
        f"/api/v1/tenants/{tenant_id}/usage?date_from=2026/07/23",
        headers=_auth_headers(),
    )
    assert resp.status_code == 400


# ========== 聚合函数容错（直接单测）==========

def test_compute_current_usage_tolerates_missing_tenant_id(test_db):
    """聚合函数容错: Station/Device/User 无 tenant_id 字段时返回 0，不抛异常"""
    from app.services.tenant_usage_service import compute_current_usage
    import app.core.database as db_module
    s = db_module.SessionLocal()
    try:
        result = compute_current_usage(s, 9999)
        assert result == {"station_count": 0, "device_count": 0, "user_count": 0}
    finally:
        s.close()
