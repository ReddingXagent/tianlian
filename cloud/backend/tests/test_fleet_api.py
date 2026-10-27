"""
车队管理 API 测试 - Phase43
覆盖: 车辆绑定/解绑、资金池交易、车队概览
"""
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


def _create_enterprise(name="测试企业", code="ENT001"):
    """创建测试企业，返回 enterprise_id"""
    from app.models.enterprise import Enterprise
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        ent = Enterprise(name=name, code=code, balance=1000.00)
        db.add(ent)
        db.commit()
        db.refresh(ent)
        return ent.id
    finally:
        db.close()


# ========== 车辆绑定/解绑 ==========

def test_list_enterprise_vehicles_empty():
    """获取空车辆列表"""
    ent_id = _create_enterprise()
    resp = client.get(
        f"/api/v1/enterprises/{ent_id}/vehicles",
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    data = resp.json()
    items = data.get("data", {}).get("items", [])
    assert items == []


def test_bind_vehicle():
    """绑定车辆"""
    ent_id = _create_enterprise()
    resp = client.post(
        f"/api/v1/enterprises/{ent_id}/vehicles",
        json={
            "plate_number": "豫A88888",
            "vin": "LSVAU2189N2188888",
            "driver_name": "张师傅",
            "driver_phone": "13800001234",
        },
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["plate_number"] == "豫A88888"
    assert data["vin"] == "LSVAU2189N2188888"
    assert data["driver_name"] == "张师傅"
    assert data["enterprise_id"] == ent_id
    assert data["status"] == "active"


def test_bind_duplicate_vin():
    """重复VIN绑定应返回400"""
    ent_id = _create_enterprise()
    payload = {"plate_number": "豫A88888", "vin": "LSVAU2189N2188888"}
    # 第一次
    resp1 = client.post(
        f"/api/v1/enterprises/{ent_id}/vehicles",
        json=payload,
        headers=_auth_headers(),
    )
    assert resp1.status_code == 200
    # 第二次（相同VIN）
    payload2 = {"plate_number": "豫B66666", "vin": "LSVAU2189N2188888"}
    resp2 = client.post(
        f"/api/v1/enterprises/{ent_id}/vehicles",
        json=payload2,
        headers=_auth_headers(),
    )
    assert resp2.status_code == 400


def test_unbind_vehicle():
    """解绑车辆"""
    ent_id = _create_enterprise()
    # 先绑定
    bind_resp = client.post(
        f"/api/v1/enterprises/{ent_id}/vehicles",
        json={"plate_number": "豫C33333", "vin": "LSVAU2189N3333333"},
        headers=_auth_headers(),
    )
    assert bind_resp.status_code == 200
    v_id = bind_resp.json()["data"]["id"]

    # 解绑
    unbind_resp = client.delete(
        f"/api/v1/enterprises/{ent_id}/vehicles/{v_id}",
        headers=_auth_headers(),
    )
    assert unbind_resp.status_code == 200

    # 验证已解绑
    list_resp = client.get(
        f"/api/v1/enterprises/{ent_id}/vehicles",
        headers=_auth_headers(),
    )
    assert list_resp.json()["data"]["items"] == []


def test_list_enterprise_vehicles_with_data():
    """获取有数据的车辆列表"""
    ent_id = _create_enterprise()
    for i in range(3):
        client.post(
            f"/api/v1/enterprises/{ent_id}/vehicles",
            json={
                "plate_number": f"豫A{i}8888",
                "vin": f"LSVAU2189N{i}888888",
                "driver_name": f"司机{i}",
            },
            headers=_auth_headers(),
        )
    resp = client.get(
        f"/api/v1/enterprises/{ent_id}/vehicles",
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] == 3
    assert len(data["items"]) == 3


# ========== 资金池交易 ==========

def test_list_transactions_empty():
    """获取空交易列表"""
    ent_id = _create_enterprise()
    resp = client.get(
        f"/api/v1/enterprises/{ent_id}/transactions",
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["items"] == []


def test_create_recharge_transaction():
    """创建充值交易并更新企业余额"""
    ent_id = _create_enterprise()
    resp = client.post(
        f"/api/v1/enterprises/{ent_id}/transactions",
        json={"type": "recharge", "amount": 500.00, "remark": "充值测试"},
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["type"] == "recharge"
    assert data["amount"] == 500.00
    assert data["balance_after"] == 1500.00  # 1000 + 500


def test_create_consume_transaction():
    """创建消费交易并更新企业余额"""
    ent_id = _create_enterprise()
    resp = client.post(
        f"/api/v1/enterprises/{ent_id}/transactions",
        json={"type": "consume", "amount": 200.00, "remark": "充电消费"},
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["type"] == "consume"
    assert data["amount"] == 200.00
    assert data["balance_after"] == 800.00  # 1000 - 200


def test_list_transactions_with_data():
    """获取有数据的交易列表"""
    ent_id = _create_enterprise()
    for t, a in [("recharge", 100), ("consume", 50), ("refund", 30)]:
        client.post(
            f"/api/v1/enterprises/{ent_id}/transactions",
            json={"type": t, "amount": a},
            headers=_auth_headers(),
        )
    resp = client.get(
        f"/api/v1/enterprises/{ent_id}/transactions",
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] == 3
    assert len(data["items"]) == 3


# ========== 车队概览 ==========

def test_fleet_overview_empty():
    """获取空车队概览"""
    ent_id = _create_enterprise()
    resp = client.get(
        f"/api/v1/fleet/overview?enterprise_id={ent_id}",
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["enterprise"]["id"] == ent_id
    assert data["total_vehicles"] == 0
    assert data["recent_transactions"] == []


def test_fleet_overview_with_data():
    """获取有数据的车队概览"""
    ent_id = _create_enterprise()
    # 绑定车辆
    client.post(
        f"/api/v1/enterprises/{ent_id}/vehicles",
        json={"plate_number": "豫D12345", "vin": "LSVAU2189ND111111"},
        headers=_auth_headers(),
    )
    # 创建交易
    client.post(
        f"/api/v1/enterprises/{ent_id}/transactions",
        json={"type": "recharge", "amount": 500.00},
        headers=_auth_headers(),
    )
    client.post(
        f"/api/v1/enterprises/{ent_id}/transactions",
        json={"type": "consume", "amount": 100.00},
        headers=_auth_headers(),
    )

    resp = client.get(
        f"/api/v1/fleet/overview?enterprise_id={ent_id}",
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["enterprise"]["id"] == ent_id
    assert data["total_vehicles"] == 1
    assert len(data["recent_transactions"]) == 2
