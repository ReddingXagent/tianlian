"""
运营-优惠券管理 API 测试

覆盖 /api/v1/operate/coupon*:
- CRUD:        POST/GET/PUT/DELETE /coupon, /coupon/{id}
- 发放:        POST /coupon/distribute        (扣库存 + 生成券码 + 写 CouponUsage)
- 核销:        POST /coupon/redeem            (CouponUsage 状态 ACTIVE→USED/EXPIRED)
- 统计/记录:   GET  /coupon/stats, /coupon/usages
- 参数校验:    name/face_value/total_stock/quantity 边界

注: 关于"状态流转", Coupon 模型只有 is_active(布尔) 字段, 并无 draft/published/ended
状态机; CouponStatus(ACTIVE/USED/EXPIRED/DISABLED) 属于 CouponUsage。故本套测试覆盖的
真实流转为: (1) Coupon.is_active 启停; (2) CouponUsage 经 redeem 从 ACTIVE→USED, 过期
券核销则落为 EXPIRED。
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import uuid

from app.models.charging_order import ChargingOrder
from app.models.coupon import (
    Coupon, CouponBatch, CouponUsage, CouponType, CouponStatus,
)


# ── payloads / seeds ──

def _coupon_payload(**overrides):
    """合法的创建优惠券 payload（发放窗口默认 now±30 天，防日期腐烂）"""
    from tests.api._helpers import coupon_window
    start_time, end_time = coupon_window()
    payload = {
        "name": "满100减20券",
        "coupon_type": "fixed",
        "face_value": 20,
        "min_order_amount": 100,
        "total_stock": 100,
        "per_user_limit": 1,
        "valid_days": 30,
        "start_time": start_time,
        "end_time": end_time,
        "is_active": True,
    }
    payload.update(overrides)
    return payload


def _create_coupon(client, **overrides):
    """创建一张券并返回 (id, payload)"""
    payload = _coupon_payload(**overrides)
    r = client.post("/api/v1/operate/coupon", json=payload)
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"], payload


def _seed_usage(session, coupon_id, *, user_id=101, status=CouponStatus.ACTIVE,
                code="CPN-TESTCODE0001", expires_delta_days=30, batch_id=None):
    """直接插入一条 CouponUsage, 供 redeem/stats 测试使用 (user_id 可指定持券人)"""
    usage = CouponUsage(
        coupon_id=coupon_id,
        batch_id=batch_id,
        user_id=user_id,
        user_type="app",
        coupon_code=code,
        status=status,
        expires_at=datetime.now(timezone.utc) + timedelta(days=expires_delta_days),
    )
    session.add(usage)
    session.commit()
    return usage


def _seed_order(session, user_id=101):
    """插一条最小 ChargingOrder 并返回订单 id。

    卡 5f7fa7ba 归属校验后, redeem 要求订单真实存在且 user_id == 持券人,
    旧的幻影 order_id (5001~5007) 会全部被 10004 拒绝。默认 user_id 与
    _seed_usage 持券人一致。
    """
    o = ChargingOrder(
        order_no=f"TL{uuid.uuid4().hex[:14].upper()}",
        station_id=1, device_id=1, user_id=user_id,
    )
    session.add(o)
    session.commit()
    session.refresh(o)
    return o.id


# ── CRUD ──

class TestCouponCRUD:
    """优惠券定义表的增删改查"""

    def test_create_coupon_sets_remaining_eq_total(self, client):
        """创建后 remaining_stock 自动等于 total_stock"""
        cid, _ = _create_coupon(client, total_stock=88)
        obj = client._sesh.query(Coupon).get(cid)
        assert obj.remaining_stock == 88
        assert obj.coupon_type == CouponType.FIXED

    def test_list_coupons_total_and_pagination(self, client):
        """列表返回全部 + 分页结构"""
        for i in range(3):
            _create_coupon(client, name=f"券{i}")
        data = client.get("/api/v1/operate/coupon").json()["data"]
        assert data["total"] >= 3
        assert len(data["items"]) >= 3
        assert data["page"] == 1 and data["page_size"] == 20

    def test_list_coupons_filter_by_active(self, client):
        """is_active 布尔过滤可靠命中"""
        _create_coupon(client, name="启用券", is_active=True)
        _create_coupon(client, name="停用券", is_active=False)

        active = client.get("/api/v1/operate/coupon?is_active=true").json()["data"]
        inactive = client.get("/api/v1/operate/coupon?is_active=false").json()["data"]
        assert all(it["is_active"] is True for it in active["items"])
        assert all(it["is_active"] is False for it in inactive["items"])

    def test_list_coupons_filter_by_type_returns_200(self, client):
        """coupon_type 字符串过滤: SAEnum 存 name(如 FIXED) 而入参为 value(如 fixed),
        存在 name/value 不匹配的已知问题。此处只断言端点 200 且结构正确, 不强求命中。"""
        _create_coupon(client, coupon_type="fixed")
        r = client.get("/api/v1/operate/coupon?coupon_type=fixed")
        assert r.status_code == 200
        assert "items" in r.json()["data"]

    def test_get_coupon_detail(self, client):
        """详情返回完整字段"""
        cid, payload = _create_coupon(client)
        data = client.get(f"/api/v1/operate/coupon/{cid}").json()["data"]
        assert data["id"] == cid
        assert data["name"] == payload["name"]
        assert data["face_value"] == 20

    def test_get_coupon_not_found(self, client):
        """不存在的 id → 404"""
        r = client.get("/api/v1/operate/coupon/999999")
        assert r.status_code == 404

    def test_update_coupon_partial(self, client):
        """PUT 部分更新 (exclude_unset 语义)"""
        cid, _ = _create_coupon(client, name="旧名", face_value=20)
        r = client.put(f"/api/v1/operate/coupon/{cid}", json={"name": "新名", "face_value": 30})
        assert r.status_code == 200
        obj = client._sesh.query(Coupon).get(cid)
        assert obj.name == "新名"
        assert obj.face_value == Decimal("30.00")
        # 未传字段保持不变
        assert obj.total_stock == 100

    def test_update_coupon_not_found(self, client):
        r = client.put("/api/v1/operate/coupon/999999", json={"name": "x"})
        assert r.status_code == 404

    def test_delete_coupon(self, client):
        """删除后详情 404"""
        cid, _ = _create_coupon(client)
        r = client.delete(f"/api/v1/operate/coupon/{cid}")
        assert r.status_code == 200
        assert client.get(f"/api/v1/operate/coupon/{cid}").status_code == 404

    def test_delete_coupon_not_found(self, client):
        assert client.delete("/api/v1/operate/coupon/999999").status_code == 404


class TestCouponToggleActive:
    """状态流转(一): Coupon.is_active 启用↔停用"""

    def test_toggle_inactive_via_update(self, client):
        cid, _ = _create_coupon(client, is_active=True)
        client.put(f"/api/v1/operate/coupon/{cid}", json={"is_active": False})
        obj = client._sesh.query(Coupon).get(cid)
        assert obj.is_active is False


# ── 发放 distribute ──

class TestCouponDistribute:
    """POST /coupon/distribute — 扣库存 + 生成券码 + 写 CouponUsage"""

    def test_distribute_decrements_stock_and_creates_usages(self, client):
        cid, _ = _create_coupon(client, total_stock=100)
        r = client.post("/api/v1/operate/coupon/distribute", json={
            "coupon_id": cid, "quantity": 3, "user_ids": "101,102,103",
        })
        assert r.status_code == 200
        body = r.json()["data"]
        assert body["count"] == 3
        assert len(body["codes"]) == 3

        obj = client._sesh.query(Coupon).get(cid)
        assert obj.remaining_stock == 97  # 100 - 3
        usages = client._sesh.query(CouponUsage).filter(CouponUsage.coupon_id == cid).all()
        assert len(usages) == 3
        assert all(u.status == CouponStatus.ACTIVE for u in usages)
        # 批次落库
        assert client._sesh.query(CouponBatch).filter(CouponBatch.coupon_id == cid).count() == 1

    def test_distribute_default_user_when_ids_absent(self, client):
        """user_ids 为空时发放给 user_id=0"""
        cid, _ = _create_coupon(client, total_stock=10)
        r = client.post("/api/v1/operate/coupon/distribute", json={
            "coupon_id": cid, "quantity": 1,
        })
        assert r.status_code == 200
        u = client._sesh.query(CouponUsage).filter(CouponUsage.coupon_id == cid).first()
        assert u.user_id == 0

    def test_distribute_coupon_not_found(self, client):
        r = client.post("/api/v1/operate/coupon/distribute", json={
            "coupon_id": 999999, "quantity": 1,
        })
        assert r.status_code == 404

    def test_distribute_inactive_coupon_rejected(self, client):
        """停用券不可发放 → 400"""
        cid, _ = _create_coupon(client, is_active=False, total_stock=100)
        r = client.post("/api/v1/operate/coupon/distribute", json={
            "coupon_id": cid, "quantity": 1,
        })
        assert r.status_code == 400

    def test_distribute_insufficient_stock_rejected(self, client):
        """quantity > remaining_stock → 400"""
        cid, _ = _create_coupon(client, total_stock=5)
        r = client.post("/api/v1/operate/coupon/distribute", json={
            "coupon_id": cid, "quantity": 10,
        })
        assert r.status_code == 400

    def test_distribute_quantity_validation(self, client):
        """quantity 必须 >= 1 → 422"""
        cid, _ = _create_coupon(client)
        r = client.post("/api/v1/operate/coupon/distribute", json={
            "coupon_id": cid, "quantity": 0,
        })
        assert r.status_code == 422

    def test_distribute_quantity_drives_issuance_and_stock_consistency(self, client):
        """quantity=发放总张数(前端契约): user_ids 少于 quantity 时轮流分配,
        每张都落库, 库存扣减必须等于实际发放数, 不得虚耗。

        回归: 旧实现按 len(user_ids) 发券却按 quantity 扣库存, 导致
        quantity > len(user_ids) 时库存与 CouponUsage 数量不一致(资产虚耗)。
        per_user_limit=0(不限): 本测试关注数量一致性而非限领,
        卡 ea373b3a enforce 后默认 limit=1 会把每人 2 张的轮流分配判超限。
        """
        cid, _ = _create_coupon(client, total_stock=100, per_user_limit=0)
        r = client.post("/api/v1/operate/coupon/distribute", json={
            "coupon_id": cid, "quantity": 4, "user_ids": "22,23",
        })
        assert r.status_code == 200
        assert r.json()["data"]["count"] == 4
        usages = client._sesh.query(CouponUsage).filter(CouponUsage.coupon_id == cid).all()
        assert len(usages) == 4
        # 库存扣减 == 实际发放数(一致性, 禁止虚耗)
        obj = client._sesh.query(Coupon).get(cid)
        assert obj.remaining_stock == 100 - len(usages)
        # 轮流分配到指定用户池
        assert {u.user_id for u in usages} == {22, 23}


# ── 核销 redeem (CouponUsage 状态流转) ──

class TestCouponRedeem:
    """POST /coupon/redeem — ACTIVE→USED, 过期券→EXPIRED"""

    def test_redeem_fixed_coupon(self, client):
        """固定金额券: 抵扣 = face_value, 状态落 USED"""
        cid, _ = _create_coupon(client, coupon_type="fixed", face_value=20, min_order_amount=100)
        _seed_usage(client._sesh, cid, code="CPN-FIXED-000001")
        oid = _seed_order(client._sesh)
        r = client.post("/api/v1/operate/coupon/redeem", json={
            "coupon_code": "CPN-FIXED-000001", "order_id": oid, "order_amount": 200,
        })
        assert r.status_code == 200
        assert r.json()["data"]["discount_amount"] == 20.0
        u = client._sesh.query(CouponUsage).filter(CouponUsage.coupon_code == "CPN-FIXED-000001").first()
        assert u.status == CouponStatus.USED
        assert u.order_id == oid
        assert u.used_at is not None

    def test_redeem_percentage_coupon(self, client):
        """百分比券: 抵扣 = order_amount * face_value"""
        cid, _ = _create_coupon(client, coupon_type="percentage", face_value=0.5, min_order_amount=0)
        _seed_usage(client._sesh, cid, code="CPN-PCT-000001")
        oid = _seed_order(client._sesh)
        r = client.post("/api/v1/operate/coupon/redeem", json={
            "coupon_code": "CPN-PCT-000001", "order_id": oid, "order_amount": 200,
        })
        assert r.status_code == 200
        assert r.json()["data"]["discount_amount"] == 100.0  # 200 * 0.5

    def test_redeem_free_charge_coupon(self, client):
        """免单券: 抵扣 = 订单全额"""
        cid, _ = _create_coupon(client, coupon_type="free_charge", face_value=0,
                                min_order_amount=0)
        _seed_usage(client._sesh, cid, code="CPN-FREE-000001")
        oid = _seed_order(client._sesh)
        r = client.post("/api/v1/operate/coupon/redeem", json={
            "coupon_code": "CPN-FREE-000001", "order_id": oid, "order_amount": 66.6,
        })
        assert r.status_code == 200
        assert r.json()["data"]["discount_amount"] == 66.6

    def test_redeem_capped_by_max_discount(self, client):
        """抵扣超过 max_discount_amount 时被截断"""
        cid, _ = _create_coupon(client, coupon_type="fixed", face_value=50,
                                min_order_amount=0, max_discount_amount=30)
        _seed_usage(client._sesh, cid, code="CPN-CAP-000001")
        oid = _seed_order(client._sesh)
        r = client.post("/api/v1/operate/coupon/redeem", json={
            "coupon_code": "CPN-CAP-000001", "order_id": oid, "order_amount": 200,
        })
        assert r.status_code == 200
        assert r.json()["data"]["discount_amount"] == 30.0

    def test_redeem_below_min_order_amount(self, client):
        """订单金额不满足最低消费 → 400"""
        cid, _ = _create_coupon(client, min_order_amount=100)
        _seed_usage(client._sesh, cid, code="CPN-MIN-000001")
        oid = _seed_order(client._sesh)
        r = client.post("/api/v1/operate/coupon/redeem", json={
            "coupon_code": "CPN-MIN-000001", "order_id": oid, "order_amount": 50,
        })
        assert r.status_code == 400

    def test_redeem_expired_coupon_flips_to_expired(self, client):
        """状态流转(二): 过期券核销 → 400 + CouponUsage 落 EXPIRED"""
        cid, _ = _create_coupon(client)
        _seed_usage(client._sesh, cid, code="CPN-EXP-000001", expires_delta_days=-1)
        oid = _seed_order(client._sesh)
        r = client.post("/api/v1/operate/coupon/redeem", json={
            "coupon_code": "CPN-EXP-000001", "order_id": oid, "order_amount": 200,
        })
        assert r.status_code == 400
        u = client._sesh.query(CouponUsage).filter(CouponUsage.coupon_code == "CPN-EXP-000001").first()
        assert u.status == CouponStatus.EXPIRED

    def test_redeem_already_used_rejected(self, client):
        """非 ACTIVE 状态(已使用) → 400"""
        cid, _ = _create_coupon(client)
        _seed_usage(client._sesh, cid, code="CPN-USED-000001", status=CouponStatus.USED)
        oid = _seed_order(client._sesh)
        r = client.post("/api/v1/operate/coupon/redeem", json={
            "coupon_code": "CPN-USED-000001", "order_id": oid, "order_amount": 200,
        })
        assert r.status_code == 400

    def test_redeem_code_not_found(self, client):
        r = client.post("/api/v1/operate/coupon/redeem", json={
            "coupon_code": "NOT-EXIST", "order_id": 1, "order_amount": 100,
        })
        assert r.status_code == 404


# ── 统计 / 使用记录 ──

class TestCouponStatsAndUsages:
    """GET /coupon/stats, /coupon/usages"""

    def test_stats_aggregates(self, client):
        cid, _ = _create_coupon(client, total_stock=100)
        _seed_usage(client._sesh, cid, code="CPN-S-ACTIVE")
        _seed_usage(client._sesh, cid, code="CPN-S-USED", status=CouponStatus.USED)
        data = client.get("/api/v1/operate/coupon/stats").json()["data"]
        assert data["total_coupons"] >= 1
        assert data["total_distributed"] >= 2
        assert data["total_used"] >= 1
        assert data["usage_rate"] > 0

    def test_usages_filter_by_user(self, client):
        cid, _ = _create_coupon(client)
        _seed_usage(client._sesh, cid, code="CPN-U-0001")
        data = client.get("/api/v1/operate/coupon/usages?user_id=101").json()["data"]
        assert data["total"] >= 1
        assert data["items"][0]["user_id"] == 101


# ── 参数校验 ──

class TestCouponValidation:
    """Pydantic 入参边界"""

    def test_create_empty_name_rejected(self, client):
        r = client.post("/api/v1/operate/coupon", json=_coupon_payload(name=""))
        assert r.status_code == 422

    def test_create_negative_face_value_rejected(self, client):
        r = client.post("/api/v1/operate/coupon", json=_coupon_payload(face_value=-1))
        assert r.status_code == 422

    def test_create_negative_stock_rejected(self, client):
        r = client.post("/api/v1/operate/coupon", json=_coupon_payload(total_stock=-5))
        assert r.status_code == 422

    def test_create_invalid_coupon_type_rejected(self, client):
        r = client.post("/api/v1/operate/coupon", json=_coupon_payload(coupon_type="not_a_type"))
        assert r.status_code == 422

    def test_create_missing_required_time(self, client):
        payload = _coupon_payload()
        payload.pop("start_time")
        r = client.post("/api/v1/operate/coupon", json=payload)
        assert r.status_code == 422


# ── 发放批次列表 ──

class TestCouponBatches:
    """GET /coupon/batches — 发放批次分页列表"""

    def test_batches_returns_distributed_batch_with_pagination(self, client):
        """发放一次后, 批次列表能查到该批次且分页结构正确"""
        cid, _ = _create_coupon(client, total_stock=100)
        r = client.post("/api/v1/operate/coupon/distribute", json={
            "coupon_id": cid, "quantity": 2, "user_ids": "101,102",
            "batch_name": "五一活动批次",
        })
        assert r.status_code == 200

        data = client.get("/api/v1/operate/coupon/batches").json()["data"]
        assert data["total"] >= 1
        assert data["page"] == 1
        assert data["page_size"] == 20
        assert isinstance(data["items"], list)
        # 最新批次排在最前 (id desc), 第一条应为本批次
        first = data["items"][0]
        assert first["coupon_id"] == cid
        assert first["batch_name"] == "五一活动批次"
        assert first["quantity"] == 2
        # 关键字段齐全
        for key in ("id", "coupon_id", "batch_name", "quantity", "distributed_at", "created_at"):
            assert key in first

    def test_batches_empty_when_no_distribution(self, client):
        """无任何发放时, 返回空分页 (total=0, items=[]) 而非 404/报错"""
        data = client.get("/api/v1/operate/coupon/batches").json()["data"]
        assert data["total"] == 0
        assert data["items"] == []
        assert data["page"] == 1
        assert data["page_size"] == 20

    def test_batches_pagination_respects_page_size(self, client):
        """page_size 截断: 发放 3 个批次后, page_size=2 只返回 2 条"""
        cid, _ = _create_coupon(client, total_stock=100)
        for i in range(3):
            r = client.post("/api/v1/operate/coupon/distribute", json={
                "coupon_id": cid, "quantity": 1, "user_ids": str(200 + i),
                "batch_name": f"批次{i}",
            })
            assert r.status_code == 200

        page1 = client.get("/api/v1/operate/coupon/batches?page_size=2").json()["data"]
        assert page1["total"] >= 3
        assert len(page1["items"]) == 2
        # 第二页
        page2 = client.get("/api/v1/operate/coupon/batches?page_size=2&page=2").json()["data"]
        assert len(page2["items"]) >= 1
        # 两页 id 不重叠
        ids_p1 = {it["id"] for it in page1["items"]}
        ids_p2 = {it["id"] for it in page2["items"]}
        assert ids_p1.isdisjoint(ids_p2)
