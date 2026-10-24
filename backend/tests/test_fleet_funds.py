"""
车队资金账户管理测试 - 对齐前端 Fleet FundAccount 契约

覆盖:
- 列表: 空列表 / 企业筛选 / 企业不存在 404
- 创建: 基本字段 / 无企业账户 / 企业ID自动回填企业名 / 企业不存在 404 / 非法状态 400
- 详情: 正常 / 不存在 404
- 更新: 字段覆盖 / 不存在 404
- 删除: 删除后不可查 / 不存在 404
"""
from decimal import Decimal

from app.models.enterprise import Enterprise
from app.models.fund_pool import (
    FundPoolTransaction,
    FundTransactionType,
    FundTransactionStatus,
)


# ─── Helpers ───

def _seed_enterprise(db_session, code="FUND_TEST", name="资金测试企业"):
    ent = Enterprise(name=name, code=code, balance=10000.0)
    db_session.add(ent)
    db_session.commit()
    db_session.refresh(ent)
    return ent.id


_CREATE = {
    "account_name": "顺达运营资金",
    "account_type": "运营账户",
    "balance": 100000.50,
    "status": "active",
    "bank_name": "中国工商银行",
    "bank_account": "6222****1234",
    "currency": "¥",
    "description": "日常运营周转",
}


# ======================================================================
# 列表
# ======================================================================

def test_list_funds_empty(client, db_session):
    """无数据时列表为空, 分页结构正确。"""
    resp = client.get("/api/v1/fleet/funds")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] == 0
    assert data["items"] == []


def test_list_funds_filter_by_enterprise(client, db_session):
    """GET /fleet/funds 按 enterprise_id 筛选。"""
    ent_a = _seed_enterprise(db_session, code="FUND_A", name="顺达物流")
    ent_b = _seed_enterprise(db_session, code="FUND_B", name="鹏程货运")

    for _ in range(2):
        client.post("/api/v1/fleet/funds", json={"enterprise_id": ent_a, **_CREATE})
    client.post("/api/v1/fleet/funds", json={"enterprise_id": ent_b, **_CREATE})

    resp = client.get(f"/api/v1/fleet/funds?enterprise_id={ent_a}")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] == 2
    assert len(data["items"]) == 2
    assert all(it["enterprise_id"] == ent_a for it in data["items"])


def test_list_funds_enterprise_not_found(client, db_session):
    """按不存在企业筛选返回 404。"""
    resp = client.get("/api/v1/fleet/funds?enterprise_id=999999")
    assert resp.status_code == 404


# ======================================================================
# 创建
# ======================================================================

def test_create_fund(client, db_session):
    """POST 创建账户, 字段落库且回显正确; 传 enterprise_id 时企业名自动回填。"""
    ent_id = _seed_enterprise(db_session, name="顺达物流")
    resp = client.post("/api/v1/fleet/funds", json={"enterprise_id": ent_id, **_CREATE})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["id"] > 0
    assert data["enterprise_id"] == ent_id
    assert data["enterprise_name"] == "顺达物流"
    assert data["account_name"] == "顺达运营资金"
    assert data["account_type"] == "运营账户"
    assert data["balance"] == 100000.50
    assert data["status"] == "active"
    assert data["bank_name"] == "中国工商银行"
    assert data["currency"] == "¥"
    assert data["created_at"]


def test_create_fund_without_enterprise(client, db_session):
    """不传 enterprise_id 可建无企业账户, 且使用字段默认值。"""
    resp = client.post("/api/v1/fleet/funds", json={
        "account_name": "无主账户", "balance": 500.0,
    })
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["enterprise_id"] is None
    assert data["account_name"] == "无主账户"
    assert data["account_type"] == "运营账户"  # 默认值
    assert data["currency"] == "¥"             # 默认值
    assert data["status"] == "active"          # 默认值


def test_create_fund_enterprise_not_found(client, db_session):
    """创建时 enterprise_id 不存在返回 404。"""
    resp = client.post("/api/v1/fleet/funds", json={
        "enterprise_id": 999999, **_CREATE,
    })
    assert resp.status_code == 404


def test_create_fund_invalid_status(client, db_session):
    """非法 status 返回 400。"""
    resp = client.post("/api/v1/fleet/funds", json={
        "account_name": "坏状态", "status": "bogus",
    })
    assert resp.status_code == 422  # Literal 前置 (卡 6031add1)


# ======================================================================
# 详情
# ======================================================================

def test_get_fund(client, db_session):
    """GET /fleet/funds/{id} 返回详情。"""
    fid = client.post("/api/v1/fleet/funds", json=_CREATE).json()["data"]["id"]
    resp = client.get(f"/api/v1/fleet/funds/{fid}")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["id"] == fid
    assert data["account_name"] == "顺达运营资金"


def test_get_fund_not_found(client, db_session):
    """详情不存在返回 404。"""
    resp = client.get("/api/v1/fleet/funds/99999")
    assert resp.status_code == 404


# ======================================================================
# 更新
# ======================================================================

def test_update_fund(client, db_session):
    """PUT 更新字段, 回显新值。"""
    fid = client.post("/api/v1/fleet/funds", json=_CREATE).json()["data"]["id"]
    resp = client.put(f"/api/v1/fleet/funds/{fid}", json={
        "account_name": "顺达维修基金",
        "balance": 88888.00,
        "status": "frozen",
    })
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["account_name"] == "顺达维修基金"
    assert data["balance"] == 88888.00
    assert data["status"] == "frozen"


def test_update_fund_not_found(client, db_session):
    """更新不存在返回 404。"""
    resp = client.put("/api/v1/fleet/funds/99999", json={"balance": 1.0})
    assert resp.status_code == 404


# ======================================================================
# 删除
# ======================================================================

def test_delete_fund(client, db_session):
    """DELETE 零余额零流水干净账户后详情不可查 (卡 971fb88b: 有余额/流水账户拒绝删除)。"""
    fid = client.post("/api/v1/fleet/funds", json={
        "account_name": "干净账户", "balance": 0.0,
    }).json()["data"]["id"]
    resp = client.delete(f"/api/v1/fleet/funds/{fid}")
    assert resp.status_code == 200
    assert client.get(f"/api/v1/fleet/funds/{fid}").status_code == 404


def test_delete_fund_not_found(client, db_session):
    """删除不存在返回 404。"""
    resp = client.delete("/api/v1/fleet/funds/99999")
    assert resp.status_code == 404


# ======================================================================
# 资金流水审计 (卡 20fb69d6: 余额变动必须落 FundPoolTransaction)
# ======================================================================

def _txns(db_session, fund_id):
    return (
        db_session.query(FundPoolTransaction)
        .filter(FundPoolTransaction.fund_pool_id == fund_id)
        .order_by(FundPoolTransaction.id)
        .all()
    )


def test_create_fund_initial_balance_writes_txn(client, db_session):
    """创建时初始余额 >0 落一条 recharge 流水 (before=0, after=初始余额)。"""
    fid = client.post("/api/v1/fleet/funds", json={
        "account_name": "初始余额账户", "balance": 1000.50,
    }).json()["data"]["id"]

    txns = _txns(db_session, fid)
    assert len(txns) == 1
    tx = txns[0]
    assert tx.transaction_type == FundTransactionType.RECHARGE
    assert tx.status == FundTransactionStatus.SUCCESS
    assert tx.balance_before == Decimal("0.00")
    assert tx.balance_after == Decimal("1000.50")
    assert tx.amount == Decimal("1000.50")


def test_create_fund_zero_balance_no_txn(client, db_session):
    """创建时初始余额为 0 不落流水。"""
    fid = client.post("/api/v1/fleet/funds", json={
        "account_name": "零初始账户", "balance": 0.0,
    }).json()["data"]["id"]
    assert _txns(db_session, fid) == []


def test_update_fund_balance_increase_writes_recharge_txn(client, db_session):
    """PUT 余额上调落 recharge 流水, before/after 正确。"""
    fid = client.post("/api/v1/fleet/funds", json={
        "account_name": "调账账户", "balance": 100.00,
    }).json()["data"]["id"]
    assert len(_txns(db_session, fid)) == 1  # 建账初始流水

    resp = client.put(f"/api/v1/fleet/funds/{fid}", json={"balance": 250.75})
    assert resp.status_code == 200
    assert resp.json()["data"]["balance"] == 250.75

    txns = _txns(db_session, fid)
    assert len(txns) == 2
    tx = txns[1]
    assert tx.transaction_type == FundTransactionType.RECHARGE
    assert tx.status == FundTransactionStatus.SUCCESS
    assert tx.balance_before == Decimal("100.00")
    assert tx.balance_after == Decimal("250.75")
    assert tx.amount == Decimal("150.75")
    assert tx.remark and "手动调账" in tx.remark


def test_update_fund_balance_decrease_writes_consume_txn(client, db_session):
    """PUT 余额下调落 consume 流水。"""
    fid = client.post("/api/v1/fleet/funds", json={
        "account_name": "扣减账户", "balance": 500.00,
    }).json()["data"]["id"]

    resp = client.put(f"/api/v1/fleet/funds/{fid}", json={"balance": 120.00})
    assert resp.status_code == 200

    txns = _txns(db_session, fid)
    assert len(txns) == 2
    tx = txns[1]
    assert tx.transaction_type == FundTransactionType.CONSUME
    assert tx.balance_before == Decimal("500.00")
    assert tx.balance_after == Decimal("120.00")
    assert tx.amount == Decimal("380.00")


def test_update_fund_balance_unchanged_no_extra_txn(client, db_session):
    """PUT 余额设为相同值不落流水。"""
    fid = client.post("/api/v1/fleet/funds", json={
        "account_name": "等值账户", "balance": 300.00,
    }).json()["data"]["id"]

    resp = client.put(f"/api/v1/fleet/funds/{fid}", json={"balance": 300.00})
    assert resp.status_code == 200
    assert len(_txns(db_session, fid)) == 1  # 仅建账初始流水


def test_update_fund_other_fields_no_txn(client, db_session):
    """PUT 不传余额时零流水。"""
    fid = client.post("/api/v1/fleet/funds", json={
        "account_name": "改名账户", "balance": 100.00,
    }).json()["data"]["id"]

    resp = client.put(f"/api/v1/fleet/funds/{fid}", json={"account_name": "新名字"})
    assert resp.status_code == 200
    assert len(_txns(db_session, fid)) == 1


# ======================================================================
# 删除保护 + 流水读取 (卡 971fb88b)
# ======================================================================

def test_delete_fund_with_balance_rejected(client, db_session):
    """有余额账户 DELETE → 409, 账户保留。"""
    fid = client.post("/api/v1/fleet/funds", json={
        "account_name": "有余额账户", "balance": 100.00,
    }).json()["data"]["id"]
    resp = client.delete(f"/api/v1/fleet/funds/{fid}")
    assert resp.status_code == 409
    assert "余额" in resp.json()["detail"]
    assert client.get(f"/api/v1/fleet/funds/{fid}").status_code == 200


def test_delete_fund_with_transactions_rejected(client, db_session):
    """有流水但余额已清零的账户 DELETE → 409, 流水保留。"""
    fid = client.post("/api/v1/fleet/funds", json={
        "account_name": "有流水账户", "balance": 100.00,
    }).json()["data"]["id"]
    assert client.put(f"/api/v1/fleet/funds/{fid}", json={"balance": 0.0}).status_code == 200
    resp = client.delete(f"/api/v1/fleet/funds/{fid}")
    assert resp.status_code == 409
    assert "流水" in resp.json()["detail"]
    assert len(_txns(db_session, fid)) == 2


def test_delete_fund_clean_allowed(client, db_session):
    """零余额零流水干净账户 DELETE → 200。"""
    fid = client.post("/api/v1/fleet/funds", json={
        "account_name": "干净账户", "balance": 0.0,
    }).json()["data"]["id"]
    resp = client.delete(f"/api/v1/fleet/funds/{fid}")
    assert resp.status_code == 200
    assert client.get(f"/api/v1/fleet/funds/{fid}").status_code == 404


def test_list_fund_transactions_empty(client, db_session):
    """无流水账户 → 空列表分页结构。"""
    fid = client.post("/api/v1/fleet/funds", json={
        "account_name": "空流水账户", "balance": 0.0,
    }).json()["data"]["id"]
    resp = client.get(f"/api/v1/fleet/funds/{fid}/transactions")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] == 0
    assert data["page"] == 1
    assert data["page_size"] == 20
    assert data["items"] == []


def test_list_fund_transactions_fields(client, db_session):
    """有流水账户 → 返回流水列表且字段齐全, id 倒序。"""
    fid = client.post("/api/v1/fleet/funds", json={
        "account_name": "流水账户", "balance": 100.00,
    }).json()["data"]["id"]
    client.put(f"/api/v1/fleet/funds/{fid}", json={"balance": 250.00})

    resp = client.get(f"/api/v1/fleet/funds/{fid}/transactions")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] == 2
    items = data["items"]
    assert len(items) == 2
    assert items[0]["id"] > items[1]["id"]  # 倒序
    first = items[0]
    assert first["transaction_type"] == "recharge"
    assert first["amount"] == 150.0
    assert first["balance_before"] == 100.0
    assert first["balance_after"] == 250.0
    assert first["status"] == "success"
    assert first["remark"]
    assert first["created_at"]


def test_list_fund_transactions_pagination(client, db_session):
    """分页 page/page_size 正常。"""
    fid = client.post("/api/v1/fleet/funds", json={
        "account_name": "分页账户", "balance": 100.00,
    }).json()["data"]["id"]
    client.put(f"/api/v1/fleet/funds/{fid}", json={"balance": 200.00})

    resp = client.get(f"/api/v1/fleet/funds/{fid}/transactions?page=1&page_size=1")
    data = resp.json()["data"]
    assert data["total"] == 2
    assert len(data["items"]) == 1
    assert data["page_size"] == 1

    resp2 = client.get(f"/api/v1/fleet/funds/{fid}/transactions?page=2&page_size=1")
    data2 = resp2.json()["data"]
    assert len(data2["items"]) == 1
    assert data2["items"][0]["id"] < data["items"][0]["id"]


def test_list_fund_transactions_not_found(client, db_session):
    """不存在账户 → 404。"""
    resp = client.get("/api/v1/fleet/funds/999999/transactions")
    assert resp.status_code == 404
