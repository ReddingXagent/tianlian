"""工单流转端点补充测试 (app/api/v1/workorders/routes_workflow.py)

与 test_workorders_workflow.py (复数, 已覆盖 8 端点的状态机/并发/越权/team scoping)
互补, 本文件聚焦该文件未覆盖的独立维度:

  ① 权限门 (router-level require_write_permission("workorder:edit")):
       POST 写端点对 VIEWER → 403 (viewer 不持任何写权限);
       匿名 → 401。GET 读端点仅认证即可。
     现有文件全程用 admin/engineer, 未验证 VIEWER 被守卫拦截。
  ② 422 参数校验: reject 缺 reason query / transfer 缺 target_engineer_id body。
     现有 transfer 测了 400/404 但未覆盖 schema 缺字段 422。
  ③ WS 广播触发: accept/start/complete/verify 等流转动作触发 _broadcast_wo。
     现有文件未断言广播。
  ④ dispatch 带 device 的完整路径 + WorkOrderLog 日志落库。

工程要点:
- helpers._broadcast_wo 内部 try/except 吞所有异常, 故 mock 失败不会 500;
  改 monkeypatch helpers 模块的 broadcast_workorder 符号验证调用。
- 权限守卫在 body 解析前执行, viewer 写请求即使 body 非法也先 403。
"""
import uuid

import bcrypt
import pytest

import app.api.v1.workorders.helpers as wo_helpers
from app.models.station import Station, StationStatus
from app.models.user import User, UserRole
from app.models.workorder import WorkOrder, WorkOrderStatus, WorkOrderLog
from tests.api._helpers import WO_URL, advance_wo, create_wo, login_admin, login_as


# ─── helpers ───

def _uname(base: str) -> str:
    return f"{base}_{uuid.uuid4().hex[:8]}"


def _add_user(s, username, *, role=UserRole.ENGINEER, team_id=None, password="pass123"):
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


def _make_wo(s, *, station_id=None, device_id=None, assignee_id=None,
             status=WorkOrderStatus.PENDING, wo_id=None) -> WorkOrder:
    wo = WorkOrder(
        id=wo_id or f"WO-WF2-{uuid.uuid4().hex[:12]}",
        fault_desc="测试故障",
        type="repair",
        level="warning",
        status=status,
        station_id=station_id,
        device_id=device_id,
        assignee_id=assignee_id,
    )
    s.add(wo)
    s.commit()
    s.refresh(wo)
    return wo


def _make_station(s, team_id=None) -> Station:
    sta = Station(
        name=f"流转站{uuid.uuid4().hex[:4]}",
        code=f"WF{uuid.uuid4().hex[:6].upper()}",
        address="测试地址",
        status=StationStatus.NORMAL,
        team_id=team_id,
    )
    s.add(sta)
    s.commit()
    s.refresh(sta)
    return sta


@pytest.fixture
def viewer(client):
    """VIEWER 角色 (不持 workorder:edit 写权限)。

    不在此处切换 client 身份: 测试需先以 admin 建好工单 (create_wo 是写操作,
    viewer 会被 workorder:edit 拦成 403), 再 login_as 切 viewer 发起被测写请求。
    测完由调用方切回 admin。
    """
    return _add_user(client._sesh, _uname("wf_viewer"), role=UserRole.VIEWER)


# ════════════════════════════════════════════════════════════════════
# ① 权限门: VIEWER 写 → 403, 匿名 → 401
# ════════════════════════════════════════════════════════════════════

class TestPermissionGate:
    def test_viewer_accept_403(self, client, viewer):
        wo_id = create_wo(client, fault_desc="权限门")  # admin 建单
        login_as(client, viewer.username, "pass123")
        try:
            r = client.post(f"{WO_URL}/{wo_id}/accept")
            assert r.status_code == 403
        finally:
            login_admin(client)

    def test_viewer_dispatch_403(self, client, viewer):
        wo_id = create_wo(client)
        login_as(client, viewer.username, "pass123")
        try:
            r = client.post(f"{WO_URL}/{wo_id}/dispatch", json={"auto": True})
            assert r.status_code == 403
        finally:
            login_admin(client)

    def test_viewer_transfer_403(self, client, viewer):
        wo_id = create_wo(client)
        login_as(client, viewer.username, "pass123")
        try:
            r = client.post(f"{WO_URL}/{wo_id}/transfer",
                            json={"target_engineer_id": 1, "reason": "x"})
            assert r.status_code == 403
        finally:
            login_admin(client)

    def test_anonymous_accept_401(self, client):
        client.headers.pop("Authorization", None)
        r = client.post(f"{WO_URL}/WO-GHOST-0001/accept")
        assert r.status_code == 401


# ════════════════════════════════════════════════════════════════════
# ② 422 参数校验 (schema 缺字段)
# ════════════════════════════════════════════════════════════════════

class TestSchemaValidation:
    def test_reject_missing_reason_422(self, client):
        """reject 的 reason 是必填 query param, 缺失 → 422。"""
        wo_id = create_wo(client)
        advance_wo(client, wo_id, "accept", "start", "complete")  # → pending_verify
        r = client.post(f"{WO_URL}/{wo_id}/reject")  # 不传 reason
        assert r.status_code == 422

    def test_transfer_missing_target_engineer_id_422(self, client):
        """transfer body 缺必填 target_engineer_id → 422 (Pydantic)。"""
        wo_id = create_wo(client)
        advance_wo(client, wo_id, "accept", "start")  # → processing
        r = client.post(f"{WO_URL}/{wo_id}/transfer", json={"reason": "缺目标"})
        assert r.status_code == 422

    def test_transfer_missing_reason_422(self, client):
        wo_id = create_wo(client)
        advance_wo(client, wo_id, "accept", "start")
        r = client.post(f"{WO_URL}/{wo_id}/transfer", json={"target_engineer_id": 1})
        assert r.status_code == 422


# ════════════════════════════════════════════════════════════════════
# ③ WS 广播触发
# ════════════════════════════════════════════════════════════════════

class TestBroadcast:
    """mock 签名随卡 434f741a 更新: broadcast_workorder(payload, team_id=None) —
    记录 (payload, team_id) 二元组, 顺带断言 team_id 与工单归属一致 (无站点 → None)。"""

    def _mock(self, calls):
        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(
            wo_helpers, "broadcast_workorder",
            lambda payload, team_id=None: calls.append((payload, team_id)),
        )
        return monkeypatch

    def test_accept_broadcasts(self, client, monkeypatch):
        calls = []
        mp = self._mock(calls)
        try:
            wo_id = create_wo(client)
            client.post(f"{WO_URL}/{wo_id}/accept")
        finally:
            mp.undo()
        assert any(c.get("event") == "accepted" and c.get("id") == wo_id
                   for c, _ in calls)
        # create_wo 的工单未挂站点 → 广播 team_id=None (只发 admin)
        assert all(tid is None for _, tid in calls)

    def test_complete_broadcasts(self, client, monkeypatch):
        calls = []
        mp = self._mock(calls)
        try:
            wo_id = create_wo(client)
            advance_wo(client, wo_id, "accept", "start")
            client.post(f"{WO_URL}/{wo_id}/complete", params={"solution": "done"})
        finally:
            mp.undo()
        assert any(c.get("event") == "completed" for c, _ in calls)

    def test_verify_broadcasts(self, client, monkeypatch):
        calls = []
        mp = self._mock(calls)
        try:
            wo_id = create_wo(client)
            advance_wo(client, wo_id, "accept", "start", "complete")
            client.post(f"{WO_URL}/{wo_id}/verify")
        finally:
            mp.undo()
        assert any(c.get("event") == "verified" and c.get("status") == "completed"
                   for c, _ in calls)

    def test_reject_broadcasts(self, client, monkeypatch):
        calls = []
        mp = self._mock(calls)
        try:
            wo_id = create_wo(client)
            advance_wo(client, wo_id, "accept", "start", "complete")
            client.post(f"{WO_URL}/{wo_id}/reject", params={"reason": "no"})
        finally:
            mp.undo()
        assert any(c.get("event") == "rejected" and c.get("reason") == "no"
                   for c, _ in calls)


# ════════════════════════════════════════════════════════════════════
# ④ dispatch 带 device + 日志落库
# ════════════════════════════════════════════════════════════════════

class TestDispatchAndLogs:
    def test_dispatch_with_device_writes_log(self, client):
        """派单成功后 WorkOrderLog 落一条 action='dispatch' 日志。"""
        s = client._sesh
        eng = _add_user(s, _uname("eng_dev"))
        sta = _make_station(s)
        # 借 seed_devices 不便, 直接挂一个 Device (type 必填枚举)
        from app.models.device import Device, DeviceType, DeviceStatus
        dev = Device(sn=f"SN-{uuid.uuid4().hex[:6]}", name="派单设备",
                     code="DEV-WF2", type=DeviceType.CHARGER_DC,
                     status=DeviceStatus.ONLINE, station_id=sta.id, rated_power=120.0)
        s.add(dev)
        s.commit()
        s.refresh(dev)

        wo = _make_wo(s, status=WorkOrderStatus.PENDING, station_id=sta.id, device_id=dev.id)
        r = client.post(f"{WO_URL}/{wo.id}/dispatch", json={"auto": True})
        assert r.status_code == 200, r.text

        logs = (s.query(WorkOrderLog)
                .filter(WorkOrderLog.order_id == wo.id, WorkOrderLog.action == "dispatch")
                .all())
        assert len(logs) == 1
        assert "派单给" in logs[0].description

    def test_accept_writes_accepted_log(self, client):
        s = client._sesh
        wo_id = create_wo(client, fault_desc="接单日志")
        client.post(f"{WO_URL}/{wo_id}/accept")
        logs = (s.query(WorkOrderLog)
                .filter(WorkOrderLog.order_id == wo_id, WorkOrderLog.action == "accepted")
                .all())
        assert len(logs) == 1

    def test_transfer_writes_transferred_log(self, client):
        s = client._sesh
        sta = _make_station(s)
        e1 = _add_user(s, _uname("eng_tfrom"))
        e2 = _add_user(s, _uname("eng_tto"))
        wo = _make_wo(s, status=WorkOrderStatus.PROCESSING, assignee_id=e1.id, station_id=sta.id)
        client.post(f"{WO_URL}/{wo.id}/transfer",
                    json={"target_engineer_id": e2.id, "reason": "调整"})
        logs = (s.query(WorkOrderLog)
                .filter(WorkOrderLog.order_id == wo.id, WorkOrderLog.action == "transferred")
                .all())
        assert len(logs) == 1
        assert "转给" in logs[0].description

    def test_urge_writes_urged_log_no_status_change(self, client):
        s = client._sesh
        wo_id = create_wo(client)
        advance_wo(client, wo_id, "accept", "start")  # processing
        client.post(f"{WO_URL}/{wo_id}/urge", json={"message": "快"})
        logs = (s.query(WorkOrderLog)
                .filter(WorkOrderLog.order_id == wo_id, WorkOrderLog.action == "urged")
                .all())
        assert len(logs) == 1
        # status 未变
        assert client.get(f"{WO_URL}/{wo_id}").json()["data"]["status"] == "processing"
