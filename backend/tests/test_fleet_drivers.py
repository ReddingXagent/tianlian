"""
车队司机管理 API 测试 - Phase44
覆盖: 司机CRUD + 账户充值 + 交易(消费/退款) + 企业关联校验
"""
import pytest
from fastapi.testclient import TestClient


# ========== Fixtures ==========

def _create_enterprise(test_db):
    """创建测试企业，返回 enterprise_id"""
    from app.models.enterprise import Enterprise
    db = test_db["session"]
    ent = Enterprise(name="测试车队企业", code=f"ENT_D{ent_id_counter()}", balance=10000.00)
    db.add(ent)
    db.commit()
    db.refresh(ent)
    return ent.id


_counter = [0]
def ent_id_counter():
    _counter[0] += 1
    return _counter[0]


@pytest.fixture
def enterprise_id(test_db):
    """每个测试自动创建一个企业"""
    return _create_enterprise(test_db)


@pytest.fixture
def client(test_db):
    """构造绑定到 test_db 的 TestClient"""
    from app.main import app
    from app.core.database import get_db
    app.dependency_overrides[get_db] = lambda: test_db["session"]
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _login(client):
    """登录获取 token"""
    resp = client.post(
        "/api/v1/auth/login",
        data={"username": "admin", "password": "admin123"},
    )
    assert resp.status_code == 200
    data = resp.json()
    return data.get("token") or data.get("data", {}).get("token")


def _auth_headers(client):
    return {"Authorization": f"Bearer {_login(client)}"}


def _create_driver(client, enterprise_id, **overrides):
    """创建司机辅助函数"""
    payload = {
        "enterprise_id": enterprise_id,
        "name": "张师傅",
        "phone": "13800001111",
        "license_no": "410101199001011234",
        "license_type": "B2",
    }
    payload.update(overrides)
    resp = client.post(
        "/api/v1/fleet/drivers",
        json=payload,
        headers=_auth_headers(client),
    )
    assert resp.status_code == 200, f"创建司机失败: {resp.text}"
    return resp.json()["data"]


# ========== 司机 CRUD 测试 ==========

class TestDriverCRUD:
    """司机增删改查测试"""

    def test_list_drivers_empty(self, client, enterprise_id):
        """空列表"""
        resp = client.get(
            "/api/v1/fleet/drivers",
            headers=_auth_headers(client),
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["items"] == []

    def test_list_drivers_with_filter(self, client, enterprise_id):
        """按企业过滤"""
        _create_driver(client, enterprise_id, name="司机A")
        resp = client.get(
            f"/api/v1/fleet/drivers?enterprise_id={enterprise_id}",
            headers=_auth_headers(client),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["name"] == "司机A"

    def test_create_driver(self, client, enterprise_id):
        """创建司机"""
        data = _create_driver(client, enterprise_id, name="李师傅", phone="13900001234")
        assert data["name"] == "李师傅"
        assert data["phone"] == "13900001234"
        assert data["status"] == "active"
        assert data["enterprise_id"] == enterprise_id
        assert data["license_type"] == "B2"
        # 创建司机时自动创建账户
        assert data["account"] is not None
        assert data["account"]["balance"] == 0.0

    def test_create_driver_invalid_enterprise(self, client):
        """企业不存在时创建司机"""
        resp = client.post(
            "/api/v1/fleet/drivers",
            json={
                "enterprise_id": 99999,
                "name": "测试",
                "phone": "13800000000",
                "license_no": "999999999999999999",
            },
            headers=_auth_headers(client),
        )
        assert resp.status_code == 404

    def test_create_driver_duplicate_license(self, client, enterprise_id):
        """驾驶证号重复"""
        _create_driver(client, enterprise_id, license_no="DUP_LICENSE_001")
        resp = client.post(
            "/api/v1/fleet/drivers",
            json={
                "enterprise_id": enterprise_id,
                "name": "另一司机",
                "phone": "13700000000",
                "license_no": "DUP_LICENSE_001",
            },
            headers=_auth_headers(client),
        )
        assert resp.status_code == 400

    def test_create_driver_invalid_license_type(self, client, enterprise_id):
        """无效驾照类型"""
        resp = client.post(
            "/api/v1/fleet/drivers",
            json={
                "enterprise_id": enterprise_id,
                "name": "测试",
                "phone": "13800000000",
                "license_no": "LIC_INVALID_X",
                "license_type": "X9",
            },
            headers=_auth_headers(client),
        )
        assert resp.status_code == 400

    def test_get_driver_detail(self, client, enterprise_id):
        """获取司机详情"""
        created = _create_driver(client, enterprise_id, name="王师傅")
        resp = client.get(
            f"/api/v1/fleet/drivers/{created['id']}",
            headers=_auth_headers(client),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["id"] == created["id"]
        assert data["name"] == "王师傅"
        assert data["account"] is not None

    def test_get_driver_not_found(self, client):
        """司机不存在"""
        resp = client.get(
            "/api/v1/fleet/drivers/99999",
            headers=_auth_headers(client),
        )
        assert resp.status_code == 404

    def test_update_driver(self, client, enterprise_id):
        """更新司机信息"""
        created = _create_driver(client, enterprise_id, name="原名")
        resp = client.put(
            f"/api/v1/fleet/drivers/{created['id']}",
            json={"name": "新名", "phone": "13900009999", "status": "inactive"},
            headers=_auth_headers(client),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["name"] == "新名"
        assert data["phone"] == "13900009999"
        assert data["status"] == "inactive"

    def test_update_driver_duplicate_license(self, client, enterprise_id):
        """更新为已存在的驾驶证号"""
        d1 = _create_driver(client, enterprise_id, license_no="UNIQUE_LIC_A")
        _create_driver(client, enterprise_id, license_no="UNIQUE_LIC_B")
        resp = client.put(
            f"/api/v1/fleet/drivers/{d1['id']}",
            json={"license_no": "UNIQUE_LIC_B"},
            headers=_auth_headers(client),
        )
        assert resp.status_code == 400

    def test_delete_driver(self, client, enterprise_id):
        """删除司机"""
        created = _create_driver(client, enterprise_id, name="待删除")
        # 删除
        resp = client.delete(
            f"/api/v1/fleet/drivers/{created['id']}",
            headers=_auth_headers(client),
        )
        assert resp.status_code == 200
        # 验证已删除
        resp2 = client.get(
            f"/api/v1/fleet/drivers/{created['id']}",
            headers=_auth_headers(client),
        )
        assert resp2.status_code == 404

    def test_delete_driver_with_balance_rejected(self, client, enterprise_id):
        """有余额司机禁止删除（账本完整性保护, 卡 97a891bc）"""
        created = _create_driver(client, enterprise_id, name="有余额司机")
        resp = client.post(
            f"/api/v1/fleet/drivers/{created['id']}/account/recharge",
            json={"amount": 100.00, "remark": "充值后尝试删除"},
            headers=_auth_headers(client),
        )
        assert resp.status_code == 200
        resp = client.delete(
            f"/api/v1/fleet/drivers/{created['id']}",
            headers=_auth_headers(client),
        )
        assert resp.status_code == 409

    def test_delete_driver_with_transactions_rejected(self, client, enterprise_id):
        """有交易流水但零余额司机禁止删除（审计流水保护, 卡 97a891bc）"""
        created = _create_driver(client, enterprise_id, name="有流水司机")
        # 充值100再消费100: 余额归零但流水留存
        resp = client.post(
            f"/api/v1/fleet/drivers/{created['id']}/account/recharge",
            json={"amount": 100.00, "remark": "充值"},
            headers=_auth_headers(client),
        )
        assert resp.status_code == 200
        resp = client.post(
            f"/api/v1/fleet/drivers/{created['id']}/transactions",
            json={"type": "consume", "amount": 100.00, "remark": "消费清零"},
            headers=_auth_headers(client),
        )
        assert resp.status_code == 200, resp.text
        resp = client.delete(
            f"/api/v1/fleet/drivers/{created['id']}",
            headers=_auth_headers(client),
        )
        assert resp.status_code == 409

    def test_delete_driver_clean_zero_balance_no_tx(self, client, enterprise_id):
        """零余额零流水干净司机可删除（卡 97a891bc）"""
        created = _create_driver(client, enterprise_id, name="干净司机")
        resp = client.delete(
            f"/api/v1/fleet/drivers/{created['id']}",
            headers=_auth_headers(client),
        )
        assert resp.status_code == 200

    def test_delete_driver_not_found(self, client):
        """删除不存在的司机"""
        resp = client.delete(
            "/api/v1/fleet/drivers/99999",
            headers=_auth_headers(client),
        )
        assert resp.status_code == 404


# ========== 账户测试 ==========

class TestDriverAccount:
    """司机账户管理测试"""

    def test_get_account(self, client, enterprise_id):
        """获取司机账户信息"""
        created = _create_driver(client, enterprise_id)
        resp = client.get(
            f"/api/v1/fleet/drivers/{created['id']}/account",
            headers=_auth_headers(client),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["driver_id"] == created["id"]
        assert data["balance"] == 0.0
        assert data["status"] == "active"

    def test_recharge_account(self, client, enterprise_id):
        """账户充值"""
        created = _create_driver(client, enterprise_id)
        resp = client.post(
            f"/api/v1/fleet/drivers/{created['id']}/account/recharge",
            json={"amount": 500.00, "remark": "首次充值"},
            headers=_auth_headers(client),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["type"] == "recharge"
        assert data["amount"] == 500.0
        assert data["balance_after"] == 500.0

    def test_recharge_negative_amount(self, client, enterprise_id):
        """充值金额必须大于0"""
        created = _create_driver(client, enterprise_id)
        resp = client.post(
            f"/api/v1/fleet/drivers/{created['id']}/account/recharge",
            json={"amount": -100},
            headers=_auth_headers(client),
        )
        assert resp.status_code == 422

    def test_recharge_multiple_times(self, client, enterprise_id):
        """多次充值累计余额"""
        created = _create_driver(client, enterprise_id)
        for amount in [100, 200, 300]:
            resp = client.post(
                f"/api/v1/fleet/drivers/{created['id']}/account/recharge",
                json={"amount": amount},
                headers=_auth_headers(client),
            )
            assert resp.status_code == 200

        # 验证余额
        resp = client.get(
            f"/api/v1/fleet/drivers/{created['id']}/account",
            headers=_auth_headers(client),
        )
        assert resp.json()["data"]["balance"] == 600.0


# ========== 交易测试 ==========

class TestDriverTransactions:
    """司机账户交易测试"""

    def test_list_transactions_empty(self, client, enterprise_id):
        """空交易列表"""
        created = _create_driver(client, enterprise_id)
        resp = client.get(
            f"/api/v1/fleet/drivers/{created['id']}/transactions",
            headers=_auth_headers(client),
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["items"] == []

    def test_create_consume_transaction(self, client, enterprise_id):
        """创建消费交易"""
        created = _create_driver(client, enterprise_id)
        # 先充值
        client.post(
            f"/api/v1/fleet/drivers/{created['id']}/account/recharge",
            json={"amount": 1000.00},
            headers=_auth_headers(client),
        )
        # 消费
        resp = client.post(
            f"/api/v1/fleet/drivers/{created['id']}/transactions",
            json={"type": "consume", "amount": 200.00, "remark": "充电消费"},
            headers=_auth_headers(client),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["type"] == "consume"
        assert data["amount"] == 200.0
        assert data["balance_after"] == 800.0

    def test_create_refund_transaction(self, client, enterprise_id):
        """创建退款交易"""
        created = _create_driver(client, enterprise_id)
        # 先充值
        client.post(
            f"/api/v1/fleet/drivers/{created['id']}/account/recharge",
            json={"amount": 500.00},
            headers=_auth_headers(client),
        )
        # 消费
        client.post(
            f"/api/v1/fleet/drivers/{created['id']}/transactions",
            json={"type": "consume", "amount": 100.00},
            headers=_auth_headers(client),
        )
        # 退款
        resp = client.post(
            f"/api/v1/fleet/drivers/{created['id']}/transactions",
            json={"type": "refund", "amount": 50.00, "remark": "多收退款"},
            headers=_auth_headers(client),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["type"] == "refund"
        assert data["balance_after"] == 450.0  # 500 - 100 + 50

    def test_consume_insufficient_balance(self, client, enterprise_id):
        """余额不足消费"""
        created = _create_driver(client, enterprise_id)
        resp = client.post(
            f"/api/v1/fleet/drivers/{created['id']}/transactions",
            json={"type": "consume", "amount": 99999.00},
            headers=_auth_headers(client),
        )
        assert resp.status_code == 400

    def test_invalid_transaction_type(self, client, enterprise_id):
        """无效交易类型"""
        created = _create_driver(client, enterprise_id)
        resp = client.post(
            f"/api/v1/fleet/drivers/{created['id']}/transactions",
            json={"type": "invalid_type", "amount": 100},
            headers=_auth_headers(client),
        )
        assert resp.status_code == 422

    def test_list_transactions_with_data(self, client, enterprise_id):
        """获取有数据的交易列表"""
        created = _create_driver(client, enterprise_id)
        # 充值 + 消费
        client.post(
            f"/api/v1/fleet/drivers/{created['id']}/account/recharge",
            json={"amount": 500},
            headers=_auth_headers(client),
        )
        client.post(
            f"/api/v1/fleet/drivers/{created['id']}/transactions",
            json={"type": "consume", "amount": 100},
            headers=_auth_headers(client),
        )
        client.post(
            f"/api/v1/fleet/drivers/{created['id']}/transactions",
            json={"type": "consume", "amount": 50},
            headers=_auth_headers(client),
        )

        resp = client.get(
            f"/api/v1/fleet/drivers/{created['id']}/transactions",
            headers=_auth_headers(client),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 3  # 1 recharge + 2 consume
        assert len(data["items"]) == 3

    def test_total_spent_updated_on_consume(self, client, enterprise_id):
        """消费后 total_spent 自动累计"""
        created = _create_driver(client, enterprise_id)
        # 充值
        client.post(
            f"/api/v1/fleet/drivers/{created['id']}/account/recharge",
            json={"amount": 1000},
            headers=_auth_headers(client),
        )
        # 消费2次
        client.post(
            f"/api/v1/fleet/drivers/{created['id']}/transactions",
            json={"type": "consume", "amount": 150},
            headers=_auth_headers(client),
        )
        client.post(
            f"/api/v1/fleet/drivers/{created['id']}/transactions",
            json={"type": "consume", "amount": 250},
            headers=_auth_headers(client),
        )

        # 检查司机详情中的 total_spent
        resp = client.get(
            f"/api/v1/fleet/drivers/{created['id']}",
            headers=_auth_headers(client),
        )
        data = resp.json()["data"]
        assert data["total_spent"] == 400.0  # 150 + 250


# ========== 企业关联校验 ==========

class TestEnterpriseRelation:
    """企业关联校验"""

    def test_drivers_belong_to_enterprise(self, client, enterprise_id):
        """司机正确关联到企业"""
        d = _create_driver(client, enterprise_id, name="关联测试司机")
        assert d["enterprise_id"] == enterprise_id

    def test_filter_drivers_by_enterprise(self, client, test_db):
        """不同企业的司机互不影响"""
        # 创建两个企业
        from app.models.enterprise import Enterprise
        db = test_db["session"]
        ent1 = Enterprise(name="企业甲", code="FE_ENT_001", balance=5000)
        ent2 = Enterprise(name="企业乙", code="FE_ENT_002", balance=5000)
        db.add_all([ent1, ent2])
        db.commit()
        db.refresh(ent1)
        db.refresh(ent2)

        # 各创建一个司机
        _create_driver(client, ent1.id, name="甲企业司机", license_no="FE_LIC_001")
        _create_driver(client, ent2.id, name="乙企业司机", license_no="FE_LIC_002")

        # 过滤企业1
        resp = client.get(
            f"/api/v1/fleet/drivers?enterprise_id={ent1.id}",
            headers=_auth_headers(client),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["name"] == "甲企业司机"

        # 过滤企业2
        resp = client.get(
            f"/api/v1/fleet/drivers?enterprise_id={ent2.id}",
            headers=_auth_headers(client),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["name"] == "乙企业司机"


# ========== 卡 c4cbcbf1: hire_date ISO8601 解析 (py3.9 Z后缀误拒 + 坏值400) ==========
# 旧实现 datetime.fromisoformat 有 try/except→400, 但 py3.9 不识 'Z' → 合法 Z 输入
# 被误拒 400 (UX 缺口); 坏值本就 400。接入共享 helper: Z 归一后接受。
# naive DateTime 列存 aware 值时 SQLAlchemy 剥 tzinfo 存墙钟。

_VALID_HIRE_DATES = [
    pytest.param("2026-03-15T00:00:00Z", "2026-03-15T00:00:00", id="z"),
    pytest.param("2026-03-15T00:00:00+08:00", "2026-03-15T00:00:00", id="offset"),
    pytest.param("2026-03-15T00:00:00", "2026-03-15T00:00:00", id="naive"),
]


@pytest.mark.parametrize("value,stored", _VALID_HIRE_DATES)
def test_create_driver_hire_date_valid_formats(client, enterprise_id, value, stored):
    """创建: 合法 ISO8601 (Z/offset/naive) → 200, 墙钟落库回显一致。

    py3.9 旧实现拒 Z (UX 缺口); offset/naive 本就通过。
    """
    resp = client.post("/api/v1/fleet/drivers", json={
        "enterprise_id": enterprise_id, "name": "入职司机", "phone": "13900001111",
        "license_no": "LIC_C4CB_CREATE", "license_type": "C1",
        "hire_date": value,
    }, headers=_auth_headers(client))
    assert resp.status_code == 200, f"合法 hire_date={value} 应200, 实际 {resp.status_code}: {resp.text}"
    assert resp.json()["data"]["hire_date"] == stored


def test_create_driver_hire_date_bad_400(client, enterprise_id):
    """创建: 坏值 hire_date → 400。"""
    resp = client.post("/api/v1/fleet/drivers", json={
        "enterprise_id": enterprise_id, "name": "坏日期司机", "phone": "13900002222",
        "license_no": "LIC_C4CB_CREATE_BAD", "license_type": "C1",
        "hire_date": "not-a-date",
    }, headers=_auth_headers(client))
    assert resp.status_code == 400, f"坏值应400, 实际 {resp.status_code}: {resp.text}"


def _make_driver_for_update(client, enterprise_id, license_no):
    """建一个司机并返回其 data (用于 hire_date 更新测试)。"""
    resp = client.post("/api/v1/fleet/drivers", json={
        "enterprise_id": enterprise_id, "name": "待更新司机", "phone": "13900003333",
        "license_no": license_no, "license_type": "C1",
    }, headers=_auth_headers(client))
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


@pytest.mark.parametrize("value,stored", _VALID_HIRE_DATES)
def test_update_driver_hire_date_valid_formats(client, enterprise_id, value, stored):
    """更新: 合法 ISO8601 (Z/offset/naive) → 200, 墙钟回显一致 (line 269 同族)。"""
    did = _make_driver_for_update(client, enterprise_id, "LIC_C4CB_UPDATE")["id"]
    resp = client.put(
        f"/api/v1/fleet/drivers/{did}",
        json={"hire_date": value},
        headers=_auth_headers(client),
    )
    assert resp.status_code == 200, f"更新合法 hire_date={value} 应200, 实际 {resp.status_code}: {resp.text}"
    assert resp.json()["data"]["hire_date"] == stored


def test_update_driver_hire_date_bad_400(client, enterprise_id):
    """更新: 坏值 hire_date → 400 (line 269 同族)。"""
    did = _make_driver_for_update(client, enterprise_id, "LIC_C4CB_UPDATE_BAD")["id"]
    resp = client.put(
        f"/api/v1/fleet/drivers/{did}",
        json={"hire_date": "not-a-date"},
        headers=_auth_headers(client),
    )
    assert resp.status_code == 400, f"坏值应400, 实际 {resp.status_code}: {resp.text}"
