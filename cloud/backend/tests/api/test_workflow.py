"""工单状态机 + 派单端点测试 — app/api/v1/workorders/routes_workflow.py

覆盖：dispatch / accept / start / complete / verify / reject / transfer / urge
维度：正常状态推进 × 非法状态(400) × 工单不存在(404) × 匿名(401) × team scoping(404) × 业务校验
"""
import pytest

from tests.api._helpers import WO_URL, login_as, login_admin, create_wo

# 各端点全路径
DISPATCH = WO_URL + "/{}/dispatch"
ACCEPT = WO_URL + "/{}/accept"
START = WO_URL + "/{}/start"
COMPLETE = WO_URL + "/{}/complete"
VERIFY = WO_URL + "/{}/verify"
REJECT = WO_URL + "/{}/reject"
TRANSFER = WO_URL + "/{}/transfer"
URGE = WO_URL + "/{}/urge"


class TestAccept:
    def test_accept_pending_ok(self, client):
        """pending → accepted"""
        wid = create_wo(client)
        r = client.post(ACCEPT.format(wid))
        assert r.status_code == 200
        assert r.json()["data"]["status"] == "accepted"
        assert r.json()["message"] == "接单成功"

    def test_accept_not_found(self, client):
        r = client.post(ACCEPT.format("WO-NONEXIST-001"))
        assert r.status_code == 404

    def test_accept_wrong_status(self, client):
        """已 accepted 再次接单 → 400"""
        wid = create_wo(client)
        client.post(ACCEPT.format(wid))
        r = client.post(ACCEPT.format(wid))
        assert r.status_code == 400
        assert "不允许接单" in r.json()["detail"]


class TestStart:
    def test_start_from_accepted(self, client):
        wid = create_wo(client)
        client.post(ACCEPT.format(wid))
        r = client.post(START.format(wid))
        assert r.status_code == 200
        assert r.json()["data"]["status"] == "processing"

    def test_start_from_pending(self, client):
        """pending 也允许直接开始"""
        wid = create_wo(client)
        r = client.post(START.format(wid))
        assert r.status_code == 200

    def test_start_wrong_status(self, client):
        """processing(经 start) → complete → pending_verify 后 start → 400"""
        wid = create_wo(client)
        client.post(ACCEPT.format(wid))
        client.post(START.format(wid))
        client.post(COMPLETE.format(wid), params={"solution": "修好了"})
        r = client.post(START.format(wid))
        assert r.status_code == 400
        assert "不允许开始" in r.json()["detail"]


class TestComplete:
    def test_complete_from_processing(self, client):
        wid = create_wo(client)
        client.post(ACCEPT.format(wid))
        client.post(START.format(wid))
        r = client.post(COMPLETE.format(wid), params={"solution": "更换部件"})
        assert r.status_code == 200
        assert r.json()["data"]["status"] == "pending_verify"

    def test_complete_wrong_status(self, client):
        """pending 状态直接 complete → 400"""
        wid = create_wo(client)
        r = client.post(COMPLETE.format(wid))
        assert r.status_code == 400
        assert "不允许完成" in r.json()["detail"]

    def test_complete_without_solution(self, client):
        """solution 可选"""
        wid = create_wo(client)
        client.post(ACCEPT.format(wid))
        client.post(START.format(wid))
        r = client.post(COMPLETE.format(wid))
        assert r.status_code == 200


class TestVerify:
    def test_verify_ok(self, client):
        """pending_verify → completed，记录验收人"""
        wid = create_wo(client)
        client.post(ACCEPT.format(wid))
        client.post(START.format(wid))
        client.post(COMPLETE.format(wid))
        r = client.post(VERIFY.format(wid))
        assert r.status_code == 200
        assert r.json()["data"]["status"] == "completed"
        assert r.json()["message"] == "验收完成"

    def test_verify_wrong_status(self, client):
        wid = create_wo(client)
        r = client.post(VERIFY.format(wid))
        assert r.status_code == 400
        assert "不允许验收" in r.json()["detail"]


class TestReject:
    def test_reject_ok(self, client):
        """pending_verify → reject → 回到 processing"""
        wid = create_wo(client)
        client.post(ACCEPT.format(wid))
        client.post(START.format(wid))
        client.post(COMPLETE.format(wid))
        r = client.post(REJECT.format(wid), params={"reason": "未解决"})
        assert r.status_code == 200
        assert r.json()["data"]["status"] == "processing"
        assert r.json()["data"]["reason"] == "未解决"

    def test_reject_wrong_status(self, client):
        wid = create_wo(client)
        r = client.post(REJECT.format(wid), params={"reason": "x"})
        assert r.status_code == 400

    def test_reject_missing_reason(self, client):
        """reason 为必填 query param → 422"""
        wid = create_wo(client)
        client.post(ACCEPT.format(wid))
        client.post(START.format(wid))
        client.post(COMPLETE.format(wid))
        r = client.post(REJECT.format(wid))
        assert r.status_code == 422


class TestDispatch:
    def test_dispatch_ok(self, client, seed_users, monkeypatch):
        """有工程师 + 引擎命中 → 派单成功，工单转 processing"""
        eng = seed_users["engineer1"]
        # mock 派单引擎，避免真实经纬度/绩效计算返回 None
        monkeypatch.setattr(
            "app.api.v1.workorders.routes_workflow.dispatch_engine.calculate_best_engineer",
            lambda wd, el, sl: {
                "engineer": {"id": eng.id, "name": "工程师张三"},
                "total_score": 88.5,
                "score_details": {"skill": 50},
            },
        )
        wid = create_wo(client)
        r = client.post(DISPATCH.format(wid), json={"auto": True})
        assert r.status_code == 200
        assert r.json()["data"]["engineer"]["id"] == eng.id
        assert r.json()["message"] == "派单成功"
        # 工单状态已转 processing
        detail = client.get(f"{WO_URL}/{wid}").json()["data"]
        assert detail["status"] == "processing"

    def test_dispatch_wrong_status(self, client, seed_users):
        """非 pending 工单派单 → 400"""
        wid = create_wo(client)
        client.post(ACCEPT.format(wid))
        r = client.post(DISPATCH.format(wid), json={"auto": True})
        assert r.status_code == 400
        assert "不允许派单" in r.json()["detail"]

    def test_dispatch_no_engineer(self, client, db_session):
        """无可用工程师 → 404"""
        wid = create_wo(client)
        r = client.post(DISPATCH.format(wid), json={"auto": True})
        assert r.status_code == 404
        assert "工程师" in r.json()["detail"]

    def test_dispatch_no_match(self, client, seed_users, monkeypatch):
        """引擎未找到合适工程师（返回 None）→ 404"""
        monkeypatch.setattr(
            "app.api.v1.workorders.routes_workflow.dispatch_engine.calculate_best_engineer",
            lambda wd, el, sl: None,
        )
        wid = create_wo(client)
        r = client.post(DISPATCH.format(wid), json={"auto": True})
        assert r.status_code == 404
        assert "合适工程师" in r.json()["detail"]


class TestTransfer:
    def test_transfer_ok(self, client, seed_users):
        """转给其他工程师 → 重置 pending"""
        eng = seed_users["engineer1"]
        wid = create_wo(client)
        r = client.post(TRANSFER.format(wid), json={"target_engineer_id": eng.id, "reason": "出差"})
        assert r.status_code == 200
        assert r.json()["data"]["status"] == "pending"
        assert r.json()["data"]["new_engineer"] == "工程师张三"

    def test_transfer_to_self(self, client, seed_users):
        """转给自己（assignee 已是该工程师）→ 400"""
        from app.models.workorder import WorkOrder, WorkOrderStatus
        eng = seed_users["engineer1"]
        wid = create_wo(client)
        # 先 dispatch 把 assignee 设成 eng
        s = client._sesh
        wo = s.query(WorkOrder).filter(WorkOrder.id == wid).first()
        wo.assignee_id = eng.id
        s.commit()
        r = client.post(TRANSFER.format(wid), json={"target_engineer_id": eng.id, "reason": "x"})
        assert r.status_code == 400
        assert "不能转给自己" in r.json()["detail"]

    def test_transfer_target_not_engineer(self, client, seed_users):
        """目标 id 不是 ENGINEER 角色 → 404"""
        viewer = seed_users["viewer1"]  # VIEWER 不是工程师
        wid = create_wo(client)
        r = client.post(TRANSFER.format(wid), json={"target_engineer_id": viewer.id, "reason": "x"})
        assert r.status_code == 404
        assert "目标工程师不存在" in r.json()["detail"]

    def test_transfer_wrong_status(self, client, seed_users):
        """已完成工单转单 → 400"""
        eng = seed_users["engineer1"]
        wid = create_wo(client)
        client.post(ACCEPT.format(wid))
        client.post(START.format(wid))
        client.post(COMPLETE.format(wid))
        client.post(VERIFY.format(wid))
        r = client.post(TRANSFER.format(wid), json={"target_engineer_id": eng.id, "reason": "x"})
        assert r.status_code == 400

    def test_transfer_invalid_body(self, client):
        """缺 target_engineer_id → 422"""
        wid = create_wo(client)
        r = client.post(TRANSFER.format(wid), json={"reason": "x"})
        assert r.status_code == 422


class TestUrge:
    def test_urge_ok(self, client):
        wid = create_wo(client)
        r = client.post(URGE.format(wid), json={"message": "尽快处理"})
        assert r.status_code == 200
        assert r.json()["data"]["note"] == "尽快处理"
        assert r.json()["message"] == "催单成功"

    def test_urge_default_message(self, client):
        """不带 body → 用默认文案"""
        wid = create_wo(client)
        r = client.post(URGE.format(wid))
        assert r.status_code == 200

    def test_urge_wrong_status(self, client):
        """已完成工单催单 → 400"""
        wid = create_wo(client)
        client.post(ACCEPT.format(wid))
        client.post(START.format(wid))
        client.post(COMPLETE.format(wid))
        client.post(VERIFY.format(wid))
        r = client.post(URGE.format(wid), json={"message": "x"})
        assert r.status_code == 400
        assert "不允许催单" in r.json()["detail"]


class TestTeamScoping:
    """非 admin 跨团队访问 → 404（不泄露存在）"""

    def _setup_cross_team(self, client, seed_users, seed_stations, wo_team_id=999, user_team_id=1):
        s = client._sesh
        eng = seed_users["engineer1"]
        eng.team_id = user_team_id
        station = seed_stations["station_a"]
        station.team_id = wo_team_id
        s.commit()
        return eng, station

    def test_cross_team_get_404(self, client, seed_users, seed_stations):
        eng, station = self._setup_cross_team(client, seed_users, seed_stations)
        wid = create_wo(client, station_id=station.id)
        login_as(client, "engineer1", "eng123")
        r = client.post(ACCEPT.format(wid))  # 写端点经 _check_workorder_team
        assert r.status_code == 404

    def test_same_team_ok(self, client, seed_users, seed_stations):
        """同团队访问放行"""
        s = client._sesh
        eng = seed_users["engineer1"]
        eng.team_id = 5
        station = seed_stations["station_a"]
        station.team_id = 5
        s.commit()
        wid = create_wo(client, station_id=station.id)
        login_as(client, "engineer1", "eng123")
        r = client.get(f"{WO_URL}/{wid}")
        assert r.status_code == 200


class TestAuth:
    def test_anon_denied(self, anon_client):
        """匿名访问 → 401"""
        r = anon_client.post(ACCEPT.format("WO-x-001"))
        assert r.status_code == 401

    def test_viewer_write_forbidden(self, client, seed_users):
        """viewer 无 workorder:edit 写权限 → 403"""
        wid = create_wo(client)
        seed_users  # 确保 viewer1 已建
        login_as(client, "viewer1", "view123")
        r = client.post(ACCEPT.format(wid))
        assert r.status_code == 403
