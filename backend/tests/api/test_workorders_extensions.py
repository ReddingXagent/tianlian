"""tests/api/test_workorders_extensions.py — 工单扩展端点覆盖

被测文件: app/api/v1/workorders/routes_extensions.py
端点 (6): checkin / support / spare-parts / rate / acceptance(GET) / acceptance(POST)

覆盖矩阵:
- checkin: 活跃态签到成功 / 非活跃态 409 / 不存在 404 / 跨团队 404
- support: 活跃态支援成功 / 非活跃态 409
- spare-parts: 未登记备件放行 / 命中库存扣减 / 库存不足 409 / 非活跃态 409
- rate: 完成态评价成功 + average / 未完成 409 / 重复评价 409
- acceptance GET: 无评价返回 verify 块 + rating=None / 有评价返回两者
- acceptance POST: 通过 → completed + rating / 驳回 → processing + 无 rating /
                   非 pending_verify 400 / 重复评价 409

活跃态 _ACTIVE_STATUSES = [accepted, processing, pending_verify]
完成态 _DONE_STATUSES = [completed, resolved, closed]
"""
import uuid

import bcrypt
import pytest

from app.models.spare_part import SparePartInventory
from app.models.station import Station, StationStatus
from app.models.user import User, UserRole
from app.models.workorder import (
    WorkOrder,
    WorkOrderCheckin,
    WorkOrderRating,
    WorkOrderSparePart,
    WorkOrderStatus,
    WorkOrderSupportRequest,
)
from tests.api._helpers import WO_URL, login_as, login_admin


# ─── helpers ───

def _uname(base: str) -> str:
    return f"{base}_{uuid.uuid4().hex[:8]}"


def _add_user(s, username, *, role=UserRole.OPERATOR, team_id=None,
              password="pass123") -> User:
    u = User(
        username=username,
        password_hash=bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode(),
        real_name=username,
        role=role,
        status="active",
        team_id=team_id,
    )
    s.add(u)
    s.commit()
    s.refresh(u)
    return u


def _make_wo(s, *, status=WorkOrderStatus.PROCESSING, station_id=None,
             wo_id=None) -> WorkOrder:
    wo = WorkOrder(
        id=wo_id or f"WO-EX-{uuid.uuid4().hex[:12]}",
        fault_desc="扩展测试工单",
        type="repair",
        level="warning",
        status=status,
        station_id=station_id,
    )
    s.add(wo)
    s.commit()
    s.refresh(wo)
    return wo


def _make_team_station(s, team_id: int) -> Station:
    sta = Station(
        name=f"扩展站{team_id}",
        code=f"EX{team_id}",
        address="测试地址",
        status=StationStatus.NORMAL,
        team_id=team_id,
    )
    s.add(sta)
    s.commit()
    s.refresh(sta)
    return sta


# ════════════════════════════════════════════════════════════════════
# checkin
# ════════════════════════════════════════════════════════════════════


class TestCheckin:
    def test_checkin_active_status_ok(self, client):
        s = client._sesh
        wo = _make_wo(s, status=WorkOrderStatus.PROCESSING)
        r = client.post(f"{WO_URL}/{wo.id}/checkin", json={
            "latitude": 31.23, "longitude": 121.47,
            "address": "现场", "note": "到场", "photo_url": "http://x/p.jpg",
        })
        assert r.status_code == 200, r.text[:300]
        d = r.json()["data"]
        assert d["latitude"] == 31.23
        assert d["address"] == "现场"
        assert d["photo_url"] == "http://x/p.jpg"
        # 落库
        assert s.query(WorkOrderCheckin).filter(WorkOrderCheckin.order_id == wo.id).count() == 1

    def test_checkin_pending_409(self, client):
        """pending 不在活跃态 (accepted/processing/pending_verify) → 409。"""
        s = client._sesh
        wo = _make_wo(s, status=WorkOrderStatus.PENDING)
        r = client.post(f"{WO_URL}/{wo.id}/checkin", json={"note": "x"})
        assert r.status_code == 409

    def test_checkin_completed_409(self, client):
        s = client._sesh
        wo = _make_wo(s, status=WorkOrderStatus.COMPLETED)
        r = client.post(f"{WO_URL}/{wo.id}/checkin", json={"note": "x"})
        assert r.status_code == 409

    def test_checkin_not_found_404(self, client):
        r = client.post(f"{WO_URL}/WO-NOPE-0001/checkin", json={"note": "x"})
        assert r.status_code == 404

    def test_checkin_cross_team_404(self, client):
        s = client._sesh
        sta = _make_team_station(s, 6101)
        wo = _make_wo(s, status=WorkOrderStatus.PROCESSING, station_id=sta.id)
        other = _add_user(s, _uname("op_ck_cross"), team_id=9999)
        try:
            login_as(client, other.username, "pass123")
            r = client.post(f"{WO_URL}/{wo.id}/checkin", json={"note": "x"})
            assert r.status_code == 404
        finally:
            login_admin(client)


# ════════════════════════════════════════════════════════════════════
# support
# ════════════════════════════════════════════════════════════════════


class TestSupport:
    def test_support_active_status_ok(self, client):
        s = client._sesh
        wo = _make_wo(s, status=WorkOrderStatus.PROCESSING)
        r = client.post(f"{WO_URL}/{wo.id}/support", json={
            "reason": "需要高级工程师", "remote": True,
        })
        assert r.status_code == 200, r.text[:300]
        d = r.json()["data"]
        assert d["reason"] == "需要高级工程师"
        assert d["remote"] is True
        assert d["status"] == "pending"
        assert s.query(WorkOrderSupportRequest).filter(
            WorkOrderSupportRequest.order_id == wo.id).count() == 1

    def test_support_with_target_engineer(self, client):
        s = client._sesh
        eng = _add_user(s, _uname("eng_target"), role=UserRole.ENGINEER)
        wo = _make_wo(s, status=WorkOrderStatus.ACCEPTED)  # accepted 也属活跃态
        r = client.post(f"{WO_URL}/{wo.id}/support", json={
            "target_engineer_id": eng.id, "reason": "求助",
        })
        assert r.status_code == 200
        assert r.json()["data"]["target_engineer_id"] == eng.id

    def test_support_non_active_409(self, client):
        s = client._sesh
        wo = _make_wo(s, status=WorkOrderStatus.PENDING)
        r = client.post(f"{WO_URL}/{wo.id}/support", json={"reason": "x"})
        assert r.status_code == 409

    def test_support_not_found_404(self, client):
        r = client.post(f"{WO_URL}/WO-NOPE-0002/support", json={"reason": "x"})
        assert r.status_code == 404


# ════════════════════════════════════════════════════════════════════
# spare-parts
# ════════════════════════════════════════════════════════════════════


class TestSpareParts:
    def test_unregistered_part_passes(self, client):
        """未登记备件 (无库存台账) → 放行, 仅记录领用, inventory_deducted=False。"""
        s = client._sesh
        wo = _make_wo(s, status=WorkOrderStatus.PROCESSING)
        r = client.post(f"{WO_URL}/{wo.id}/spare-parts", json={
            "part_name": "新型模块", "part_model": "M-NEW",
            "quantity": 3, "reason": "更换",
        })
        assert r.status_code == 200, r.text[:300]
        d = r.json()["data"]
        assert d["inventory_deducted"] is False
        assert d["quantity"] == 3
        assert d["status"] == "requested"
        assert s.query(WorkOrderSparePart).filter(
            WorkOrderSparePart.order_id == wo.id).count() == 1

    def test_registered_part_deducts_inventory(self, client):
        """命中库存台账 → 扣减 available_quantity, inventory_deducted=True。"""
        s = client._sesh
        inv = SparePartInventory(
            part_name="熔断器", part_model="F-10A",
            total_quantity=100, available_quantity=10, warehouse="W1",
        )
        s.add(inv)
        s.commit()
        s.refresh(inv)
        wo = _make_wo(s, status=WorkOrderStatus.PROCESSING)

        r = client.post(f"{WO_URL}/{wo.id}/spare-parts", json={
            "part_name": "熔断器", "part_model": "F-10A",
            "quantity": 4, "reason": "更换",
        })
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["inventory_deducted"] is True
        s.expire_all()
        inv_db = s.query(SparePartInventory).filter(SparePartInventory.id == inv.id).one()
        assert inv_db.available_quantity == 6  # 10 - 4

    def test_insufficient_inventory_409(self, client):
        """库存不足 → 409, 不扣减。"""
        s = client._sesh
        inv = SparePartInventory(
            part_name="继电器", part_model="R-5",
            total_quantity=50, available_quantity=2, warehouse="W1",
        )
        s.add(inv)
        s.commit()
        s.refresh(inv)
        wo = _make_wo(s, status=WorkOrderStatus.PROCESSING)

        r = client.post(f"{WO_URL}/{wo.id}/spare-parts", json={
            "part_name": "继电器", "part_model": "R-5",
            "quantity": 5, "reason": "更换",
        })
        assert r.status_code == 409
        assert "库存不足" in r.json()["detail"]
        # 未扣减
        s.expire_all()
        assert s.query(SparePartInventory).filter(SparePartInventory.id == inv.id).one().available_quantity == 2

    def test_spare_parts_non_active_409(self, client):
        s = client._sesh
        wo = _make_wo(s, status=WorkOrderStatus.PENDING)
        r = client.post(f"{WO_URL}/{wo.id}/spare-parts", json={
            "part_name": "x", "quantity": 1, "reason": "y",
        })
        assert r.status_code == 409

    def test_spare_parts_not_found_404(self, client):
        r = client.post(f"{WO_URL}/WO-NOPE-0003/spare-parts", json={
            "part_name": "x", "quantity": 1, "reason": "y",
        })
        assert r.status_code == 404


# ════════════════════════════════════════════════════════════════════
# rate
# ════════════════════════════════════════════════════════════════════


class TestRate:
    def test_rate_completed_ok(self, client):
        s = client._sesh
        wo = _make_wo(s, status=WorkOrderStatus.COMPLETED)
        r = client.post(f"{WO_URL}/{wo.id}/rate", json={
            "response_rating": 5, "quality_rating": 4, "attitude_rating": 4,
            "comment": "满意",
        })
        assert r.status_code == 200, r.text[:300]
        d = r.json()["data"]
        # average = (5+4+4)/3 = 4.33
        assert d["average_rating"] == round((5 + 4 + 4) / 3, 2)
        assert d["comment"] == "满意"
        assert s.query(WorkOrderRating).filter(WorkOrderRating.order_id == wo.id).count() == 1

    def test_rate_unfinished_409(self, client):
        """未完成 (非 done 状态) → 409。"""
        s = client._sesh
        wo = _make_wo(s, status=WorkOrderStatus.PROCESSING)
        r = client.post(f"{WO_URL}/{wo.id}/rate", json={
            "response_rating": 5, "quality_rating": 5, "attitude_rating": 5,
        })
        assert r.status_code == 409

    def test_rate_duplicate_409(self, client):
        """重复评价 (order_id unique) → 409。"""
        s = client._sesh
        wo = _make_wo(s, status=WorkOrderStatus.COMPLETED)
        payload = {"response_rating": 5, "quality_rating": 5, "attitude_rating": 5}
        r1 = client.post(f"{WO_URL}/{wo.id}/rate", json=payload)
        assert r1.status_code == 200
        r2 = client.post(f"{WO_URL}/{wo.id}/rate", json=payload)
        assert r2.status_code == 409
        assert "已评价" in r2.json()["detail"]

    def test_rate_invalid_score_422(self, client):
        """评分越界 (0 < 1) → Pydantic 422。"""
        s = client._sesh
        wo = _make_wo(s, status=WorkOrderStatus.COMPLETED)
        r = client.post(f"{WO_URL}/{wo.id}/rate", json={
            "response_rating": 0, "quality_rating": 5, "attitude_rating": 5,
        })
        assert r.status_code == 422

    def test_rate_not_found_404(self, client):
        r = client.post(f"{WO_URL}/WO-NOPE-0004/rate", json={
            "response_rating": 5, "quality_rating": 5, "attitude_rating": 5,
        })
        assert r.status_code == 404


# ════════════════════════════════════════════════════════════════════
# acceptance GET
# ════════════════════════════════════════════════════════════════════


class TestGetAcceptance:
    def test_acceptance_no_rating(self, client):
        """无评价: 返回 verify 块 (verifier_id/verify_time/status) + rating=None。"""
        s = client._sesh
        wo = _make_wo(s, status=WorkOrderStatus.COMPLETED)
        r = client.get(f"{WO_URL}/{wo.id}/acceptance")
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["rating"] is None
        assert d["verify"]["status"] == "completed"

    def test_acceptance_with_rating(self, client):
        s = client._sesh
        wo = _make_wo(s, status=WorkOrderStatus.COMPLETED)
        # 先经 /rate 端点产生评价
        client.post(f"{WO_URL}/{wo.id}/rate", json={
            "response_rating": 4, "quality_rating": 5, "attitude_rating": 5,
        })
        r = client.get(f"{WO_URL}/{wo.id}/acceptance")
        d = r.json()["data"]
        assert d["rating"] is not None
        assert d["rating"]["average_rating"] == round((4 + 5 + 5) / 3, 2)

    def test_acceptance_get_not_found_404(self, client):
        r = client.get(f"{WO_URL}/WO-NOPE-0005/acceptance")
        assert r.status_code == 404


# ════════════════════════════════════════════════════════════════════
# acceptance POST (一站式验收)
# ════════════════════════════════════════════════════════════════════


class TestSubmitAcceptance:
    def test_accept_pass_to_completed(self, client):
        """reject=False → completed + verify_time + 创建评分。"""
        s = client._sesh
        wo = _make_wo(s, status=WorkOrderStatus.PENDING_VERIFY)
        r = client.post(f"{WO_URL}/{wo.id}/acceptance", json={
            "response_rating": 5, "quality_rating": 5, "attitude_rating": 5,
            "comment": "通过", "reject": False,
        })
        assert r.status_code == 200, r.text[:300]
        d = r.json()["data"]
        assert d["status"] == "completed"
        assert d["verify_time"] is not None
        assert d["rating"] is not None
        assert d["rating"]["average_rating"] == 5.0
        s.expire_all()
        wo_db = s.query(WorkOrder).filter(WorkOrder.id == wo.id).one()
        assert wo_db.status == WorkOrderStatus.COMPLETED
        assert wo_db.verify_time is not None

    def test_accept_reject_back_to_processing(self, client):
        """reject=True → processing, 不创建评分。"""
        s = client._sesh
        wo = _make_wo(s, status=WorkOrderStatus.PENDING_VERIFY)
        r = client.post(f"{WO_URL}/{wo.id}/acceptance", json={
            "response_rating": 5, "quality_rating": 5, "attitude_rating": 5,
            "comment": "不合格", "reject": True,
        })
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["status"] == "processing"
        assert d["rating"] is None
        s.expire_all()
        assert s.query(WorkOrder).filter(WorkOrder.id == wo.id).one().status == WorkOrderStatus.PROCESSING
        assert s.query(WorkOrderRating).filter(WorkOrderRating.order_id == wo.id).count() == 0

    def test_accept_non_pending_verify_400(self, client):
        """非 pending_verify (如 processing) 一站式验收 → 400。"""
        s = client._sesh
        wo = _make_wo(s, status=WorkOrderStatus.PROCESSING)
        r = client.post(f"{WO_URL}/{wo.id}/acceptance", json={
            "response_rating": 5, "quality_rating": 5, "attitude_rating": 5, "reject": False,
        })
        assert r.status_code == 400

    def test_accept_duplicate_rating_409(self, client):
        """已评价的工单 (rating 已存在) 再次验收通过 → unique 约束 409。"""
        s = client._sesh
        wo = _make_wo(s, status=WorkOrderStatus.PENDING_VERIFY)
        # 第一次验收通过, 创建评分
        r1 = client.post(f"{WO_URL}/{wo.id}/acceptance", json={
            "response_rating": 5, "quality_rating": 5, "attitude_rating": 5, "reject": False,
        })
        assert r1.status_code == 200
        # 重新置回 pending_verify 模拟二次验收
        s.expire_all()
        wo_db = s.query(WorkOrder).filter(WorkOrder.id == wo.id).one()
        wo_db.status = WorkOrderStatus.PENDING_VERIFY
        s.commit()
        r2 = client.post(f"{WO_URL}/{wo.id}/acceptance", json={
            "response_rating": 4, "quality_rating": 4, "attitude_rating": 4, "reject": False,
        })
        assert r2.status_code == 409

    def test_accept_not_found_404(self, client):
        r = client.post(f"{WO_URL}/WO-NOPE-0006/acceptance", json={
            "response_rating": 5, "quality_rating": 5, "attitude_rating": 5, "reject": False,
        })
        assert r.status_code == 404


# ════════════════════════════════════════════════════════════════════
# team scoping 跨团队回归 (复用 _check_workorder_team, 端点级保护)
# ════════════════════════════════════════════════════════════════════


class TestCrossTeamScoping:
    """各扩展端点跨团队访问有团队工单 → 404 (不泄露存在)。

    _check_workorder_team 为共用守卫, checkin 已覆盖; 这里补 support/spare-parts/
    rate/acceptance 的端点级回归, 防止任一端点遗漏 team 校验调用。
    """

    def _setup_cross_team_wo(self, s, *, status):
        """建一个挂团队站的工单 + 一个跨团队(9999)用户, 返回 (wo, other)。"""
        sta = _make_team_station(s, 6901)
        wo = _make_wo(s, status=status, station_id=sta.id)
        other = _add_user(s, _uname("op_ext_cross"), team_id=9999)
        return wo, other

    def test_support_cross_team_404(self, client):
        s = client._sesh
        wo, other = self._setup_cross_team_wo(s, status=WorkOrderStatus.PROCESSING)
        try:
            login_as(client, other.username, "pass123")
            r = client.post(f"{WO_URL}/{wo.id}/support", json={"reason": "x"})
            assert r.status_code == 404
        finally:
            login_admin(client)

    def test_spare_parts_cross_team_404(self, client):
        s = client._sesh
        wo, other = self._setup_cross_team_wo(s, status=WorkOrderStatus.PROCESSING)
        try:
            login_as(client, other.username, "pass123")
            r = client.post(f"{WO_URL}/{wo.id}/spare-parts", json={
                "part_name": "x", "quantity": 1, "reason": "y",
            })
            assert r.status_code == 404
        finally:
            login_admin(client)

    def test_rate_cross_team_404(self, client):
        s = client._sesh
        wo, other = self._setup_cross_team_wo(s, status=WorkOrderStatus.COMPLETED)
        try:
            login_as(client, other.username, "pass123")
            r = client.post(f"{WO_URL}/{wo.id}/rate", json={
                "response_rating": 5, "quality_rating": 5, "attitude_rating": 5,
            })
            assert r.status_code == 404
        finally:
            login_admin(client)

    def test_acceptance_get_cross_team_404(self, client):
        s = client._sesh
        wo, other = self._setup_cross_team_wo(s, status=WorkOrderStatus.COMPLETED)
        try:
            login_as(client, other.username, "pass123")
            r = client.get(f"{WO_URL}/{wo.id}/acceptance")
            assert r.status_code == 404
        finally:
            login_admin(client)

    def test_acceptance_post_cross_team_404(self, client):
        s = client._sesh
        wo, other = self._setup_cross_team_wo(s, status=WorkOrderStatus.PENDING_VERIFY)
        try:
            login_as(client, other.username, "pass123")
            r = client.post(f"{WO_URL}/{wo.id}/acceptance", json={
                "response_rating": 5, "quality_rating": 5, "attitude_rating": 5, "reject": False,
            })
            assert r.status_code == 404
        finally:
            login_admin(client)
