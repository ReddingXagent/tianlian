"""工单扩展端点测试 — app/api/v1/workorders/routes_extensions.py

覆盖：checkin / support / spare-parts / rate / acceptance(GET+POST)
维度：正常路径 × 状态校验(409) × 库存联动 × 重复评价(409) × 一站式验收(通过/驳回) × 404 × 匿名401
"""
import pytest

from tests.api._helpers import WO_URL, create_wo
from app.models.spare_part import SparePartInventory

ACCEPT = WO_URL + "/{}/accept"
START = WO_URL + "/{}/start"
COMPLETE = WO_URL + "/{}/complete"
VERIFY = WO_URL + "/{}/verify"


def _active_wo(client) -> str:
    """创建并 accept 工单 → ACCEPTED（在 _ACTIVE_STATUSES 内）。"""
    wid = create_wo(client)
    assert client.post(ACCEPT.format(wid)).status_code == 200
    return wid


def _pending_verify_wo(client) -> str:
    """推进到 PENDING_VERIFY（可验收）。"""
    wid = create_wo(client)
    client.post(ACCEPT.format(wid))
    client.post(START.format(wid))
    client.post(COMPLETE.format(wid))
    return wid


def _done_wo(client) -> str:
    """推进到 COMPLETED（可评价）。"""
    wid = _pending_verify_wo(client)
    client.post(VERIFY.format(wid))
    return wid


class TestCheckin:
    def test_checkin_ok(self, client):
        wid = _active_wo(client)
        r = client.post(f"{WO_URL}/{wid}/checkin", json={
            "latitude": 31.23, "longitude": 121.47,
            "address": "站点A", "note": "到场", "photo_url": "http://x/p.jpg",
        })
        assert r.status_code == 200
        assert r.json()["data"]["address"] == "站点A"
        assert r.json()["message"] == "签到成功"

    def test_checkin_wrong_status(self, client):
        """pending 状态签到 → 409"""
        wid = create_wo(client)
        r = client.post(f"{WO_URL}/{wid}/checkin", json={"address": "x"})
        assert r.status_code == 409
        assert "不允许签到" in r.json()["detail"]

    def test_checkin_not_found(self, client):
        r = client.post(f"{WO_URL}/WO-NOPE/checkin", json={"address": "x"})
        assert r.status_code == 404


class TestSupport:
    def test_support_ok(self, client):
        wid = _active_wo(client)
        r = client.post(f"{WO_URL}/{wid}/support", json={
            "target_engineer_id": None, "reason": "需高级协助", "remote": True,
        })
        assert r.status_code == 200
        assert r.json()["data"]["reason"] == "需高级协助"
        assert r.json()["data"]["remote"] is True

    def test_support_wrong_status(self, client):
        wid = create_wo(client)
        r = client.post(f"{WO_URL}/{wid}/support", json={"reason": "x"})
        assert r.status_code == 409

    def test_support_missing_reason(self, client):
        """reason 必填 → 422"""
        wid = _active_wo(client)
        r = client.post(f"{WO_URL}/{wid}/support", json={"remote": True})
        assert r.status_code == 422


class TestSpareParts:
    def test_no_inventory_passthrough(self, client):
        """未登记备件 → 放行，inventory_deducted=False"""
        wid = _active_wo(client)
        r = client.post(f"{WO_URL}/{wid}/spare-parts", json={
            "part_name": "未登记件", "part_model": "X1", "quantity": 2, "reason": "领用",
        })
        assert r.status_code == 200
        assert r.json()["data"]["inventory_deducted"] is False

    def test_inventory_deducted(self, client, db_session):
        """命中台账 → 扣减，inventory_deducted=True"""
        db_session.add(SparePartInventory(part_name="测试电缆", part_model="A1", available_quantity=10))
        db_session.commit()
        wid = _active_wo(client)
        r = client.post(f"{WO_URL}/{wid}/spare-parts", json={
            "part_name": "测试电缆", "part_model": "A1", "quantity": 3, "reason": "更换",
        })
        assert r.status_code == 200
        assert r.json()["data"]["inventory_deducted"] is True
        inv = db_session.query(SparePartInventory).filter_by(part_name="测试电缆").first()
        assert inv.available_quantity == 7

    def test_insufficient_stock(self, client, db_session):
        """库存不足 → 409"""
        db_session.add(SparePartInventory(part_name="稀有件", part_model="R1", available_quantity=1))
        db_session.commit()
        wid = _active_wo(client)
        r = client.post(f"{WO_URL}/{wid}/spare-parts", json={
            "part_name": "稀有件", "part_model": "R1", "quantity": 5, "reason": "x",
        })
        assert r.status_code == 409
        assert "库存不足" in r.json()["detail"]

    def test_spare_parts_wrong_status(self, client):
        wid = create_wo(client)
        r = client.post(f"{WO_URL}/{wid}/spare-parts", json={
            "part_name": "件", "quantity": 1, "reason": "x",
        })
        assert r.status_code == 409

    def test_invalid_quantity(self, client):
        """quantity < 1 → 422"""
        wid = _active_wo(client)
        r = client.post(f"{WO_URL}/{wid}/spare-parts", json={
            "part_name": "件", "quantity": 0, "reason": "x",
        })
        assert r.status_code == 422


class TestRate:
    def test_rate_ok(self, client):
        wid = _done_wo(client)
        r = client.post(f"{WO_URL}/{wid}/rate", json={
            "response_rating": 5, "quality_rating": 4, "attitude_rating": 5, "comment": "好",
        })
        assert r.status_code == 200
        assert r.json()["data"]["average_rating"] == round((5 + 4 + 5) / 3, 2)

    def test_rate_wrong_status(self, client):
        """未完成工单评价 → 409"""
        wid = _active_wo(client)
        r = client.post(f"{WO_URL}/{wid}/rate", json={
            "response_rating": 5, "quality_rating": 5, "attitude_rating": 5,
        })
        assert r.status_code == 409
        assert "未完成" in r.json()["detail"]

    def test_rate_duplicate(self, client):
        """重复评价同一工单 → 409（order_id unique）"""
        wid = _done_wo(client)
        body = {"response_rating": 5, "quality_rating": 5, "attitude_rating": 5}
        assert client.post(f"{WO_URL}/{wid}/rate", json=body).status_code == 200
        r = client.post(f"{WO_URL}/{wid}/rate", json=body)
        assert r.status_code == 409
        assert "已评价" in r.json()["detail"]

    def test_rate_invalid_score(self, client):
        """rating=6 超范围 → 422"""
        wid = _done_wo(client)
        r = client.post(f"{WO_URL}/{wid}/rate", json={
            "response_rating": 6, "quality_rating": 5, "attitude_rating": 5,
        })
        assert r.status_code == 422


class TestAcceptance:
    def test_get_acceptance_no_rating(self, client):
        """无评价记录 → rating=None"""
        wid = _pending_verify_wo(client)
        r = client.get(f"{WO_URL}/{wid}/acceptance")
        assert r.status_code == 200
        assert r.json()["data"]["rating"] is None
        assert r.json()["data"]["verify"]["status"] == "pending_verify"

    def test_submit_pass(self, client):
        """一站式验收通过 → completed + 创建评分"""
        wid = _pending_verify_wo(client)
        r = client.post(f"{WO_URL}/{wid}/acceptance", json={
            "response_rating": 4, "quality_rating": 4, "attitude_rating": 4,
            "comment": "通过", "reject": False,
        })
        assert r.status_code == 200
        assert r.json()["data"]["status"] == "completed"
        assert r.json()["data"]["rating"] is not None

    def test_submit_reject(self, client):
        """一站式验收驳回 → processing，不创建评分"""
        wid = _pending_verify_wo(client)
        r = client.post(f"{WO_URL}/{wid}/acceptance", json={
            "response_rating": 4, "quality_rating": 4, "attitude_rating": 4,
            "comment": "返工", "reject": True,
        })
        assert r.status_code == 200
        assert r.json()["data"]["status"] == "processing"
        assert r.json()["data"]["rating"] is None

    def test_submit_wrong_status(self, client):
        """非 pending_verify 工单验收 → 400"""
        wid = _active_wo(client)  # accepted
        r = client.post(f"{WO_URL}/{wid}/acceptance", json={
            "response_rating": 4, "quality_rating": 4, "attitude_rating": 4, "reject": False,
        })
        assert r.status_code == 400

    def test_submit_duplicate_rating(self, client):
        """已评价的工单再次一站式验收通过 → 409（order_id unique）"""
        from app.models.workorder import WorkOrderRating
        wid = _pending_verify_wo(client)
        # 直接 ORM 插入评价记录，模拟「已评价」
        s = client._sesh
        s.add(WorkOrderRating(order_id=wid, response_rating=5, quality_rating=5, attitude_rating=5))
        s.commit()
        r = client.post(f"{WO_URL}/{wid}/acceptance", json={
            "response_rating": 4, "quality_rating": 4, "attitude_rating": 4, "reject": False,
        })
        assert r.status_code == 409
        assert "已评价" in r.json()["detail"]


class TestAuth:
    def test_anon_denied(self, anon_client):
        r = anon_client.post(f"{WO_URL}/WO-x/checkin", json={"address": "x"})
        assert r.status_code == 401
