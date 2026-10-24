"""
工单验收记录测试 — maint-spec §2.2 站长确认/评分
覆盖: GET/POST /work-orders/{id}/acceptance 一站式验收 + 操作人追踪(verifier_id/user_id)
路径与契约对齐 frontend/src/api/index.ts。
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    pass


def _login():
    resp = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    data = resp.json()
    return data.get("token") or data.get("data", {}).get("token")


def _auth_headers():
    return {"Authorization": f"Bearer {_login()}"}


def _admin_id():
    """读取当前登录 admin 用户 id，用于断言操作人追踪。"""
    from app.core.database import SessionLocal
    from app.models.user import User
    s = SessionLocal()
    try:
        return s.query(User).filter(User.username == "admin").first().id
    finally:
        s.close()


def _create_wo(headers, **overrides):
    defaults = dict(fault_desc="测试故障", type="repair", level="warning")
    defaults.update(overrides)
    resp = client.post("/api/v1/work-orders", json=defaults, headers=headers)
    assert resp.status_code == 200
    return resp.json()["data"]


def _to_active(h, wo_id):
    """推进到处理中（接单 → 处理中）。"""
    client.post(f"/api/v1/work-orders/{wo_id}/accept", headers=h)
    client.post(f"/api/v1/work-orders/{wo_id}/start", headers=h)


def _to_pending_verify(h, wo_id):
    """推进到待验收（不执行验收，留待 acceptance 端点）。"""
    _to_active(h, wo_id)
    client.post(f"/api/v1/work-orders/{wo_id}/complete", headers=h)


def _to_completed(h, wo_id):
    """推进到已验收完成（独立 verify 端点）。"""
    _to_pending_verify(h, wo_id)
    client.post(f"/api/v1/work-orders/{wo_id}/verify", headers=h)


# ========== POST 一站式验收 ==========

def test_acceptance_submit_success():
    """pending_verify 工单一站式验收 → completed + 评分创建 + verifier 记录。"""
    h = _auth_headers()
    wo = _create_wo(h)
    _to_pending_verify(h, wo["id"])
    resp = client.post(f"/api/v1/work-orders/{wo['id']}/acceptance", json={
        "response_rating": 5, "quality_rating": 4, "attitude_rating": 5,
        "comment": "站长验收通过",
    }, headers=h)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["status"] == "completed"
    assert data["verify_time"] is not None
    assert data["verifier_id"] == _admin_id()
    rating = data["rating"]
    assert rating is not None
    assert rating["response_rating"] == 5
    assert rating["quality_rating"] == 4
    assert rating["attitude_rating"] == 5
    assert rating["comment"] == "站长验收通过"
    assert rating["average_rating"] == round((5 + 4 + 5) / 3, 2)
    assert rating["user_id"] == _admin_id()
    assert rating["verifier_id"] == _admin_id()


def test_acceptance_reject():
    """reject=true 驳回验收 → status=processing，不创建评分。"""
    h = _auth_headers()
    wo = _create_wo(h)
    _to_pending_verify(h, wo["id"])
    resp = client.post(f"/api/v1/work-orders/{wo['id']}/acceptance", json={
        "response_rating": 5, "quality_rating": 5, "attitude_rating": 5,
        "comment": "整改后复检", "reject": True,
    }, headers=h)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["status"] == "processing"
    assert data["verifier_id"] == _admin_id()
    # 驳回不产生评分记录
    assert data["rating"] is None


def test_acceptance_duplicate():
    """已验收(completed)工单再次提交验收 → 400。"""
    h = _auth_headers()
    wo = _create_wo(h)
    _to_pending_verify(h, wo["id"])
    r1 = client.post(f"/api/v1/work-orders/{wo['id']}/acceptance", json={
        "response_rating": 5, "quality_rating": 5, "attitude_rating": 5,
    }, headers=h)
    assert r1.status_code == 200
    r2 = client.post(f"/api/v1/work-orders/{wo['id']}/acceptance", json={
        "response_rating": 4, "quality_rating": 4, "attitude_rating": 4,
    }, headers=h)
    assert r2.status_code == 400


def test_acceptance_wrong_status():
    """非 pending_verify 状态(processing)提交验收 → 400。"""
    h = _auth_headers()
    wo = _create_wo(h)
    _to_active(h, wo["id"])  # 停在 processing
    resp = client.post(f"/api/v1/work-orders/{wo['id']}/acceptance", json={
        "response_rating": 5, "quality_rating": 5, "attitude_rating": 5,
    }, headers=h)
    assert resp.status_code == 400


def test_acceptance_invalid_rating():
    """评分超出 1-5 → 422。"""
    h = _auth_headers()
    wo = _create_wo(h)
    _to_pending_verify(h, wo["id"])
    resp = client.post(f"/api/v1/work-orders/{wo['id']}/acceptance", json={
        "response_rating": 6, "quality_rating": 5, "attitude_rating": 5,
    }, headers=h)
    assert resp.status_code == 422


def test_acceptance_not_found():
    h = _auth_headers()
    resp = client.post("/api/v1/work-orders/WO-NOTEXIST/acceptance", json={
        "response_rating": 5, "quality_rating": 5, "attitude_rating": 5,
    }, headers=h)
    assert resp.status_code == 404


# ========== GET 验收记录查询 ==========

def test_acceptance_get_with_rating():
    """一站式验收后 GET 返回 verify + rating 合并记录。"""
    h = _auth_headers()
    wo = _create_wo(h)
    _to_pending_verify(h, wo["id"])
    client.post(f"/api/v1/work-orders/{wo['id']}/acceptance", json={
        "response_rating": 5, "quality_rating": 4, "attitude_rating": 5,
        "comment": "非常好",
    }, headers=h)
    resp = client.get(f"/api/v1/work-orders/{wo['id']}/acceptance", headers=h)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["verify"]["verify_time"] is not None
    assert data["verify"]["status"] == "completed"
    assert data["verify"]["verifier_id"] == _admin_id()
    assert data["rating"] is not None
    assert data["rating"]["comment"] == "非常好"
    assert data["rating"]["average_rating"] == round((5 + 4 + 5) / 3, 2)


def test_acceptance_get_no_record():
    """未验收、未评分的工单 GET → rating 为 null。"""
    h = _auth_headers()
    wo = _create_wo(h)
    _to_pending_verify(h, wo["id"])
    resp = client.get(f"/api/v1/work-orders/{wo['id']}/acceptance", headers=h)
    assert resp.status_code == 200
    data = resp.json()["data"]
    # 未验收：verify_time 与 verifier_id 为 null
    assert data["verify"]["verify_time"] is None
    assert data["verify"]["verifier_id"] is None
    # 无评分记录
    assert data["rating"] is None


def test_acceptance_get_not_found():
    h = _auth_headers()
    resp = client.get("/api/v1/work-orders/WO-NOTEXIST/acceptance", headers=h)
    assert resp.status_code == 404


# ========== 操作人追踪（独立 verify/rate 端点） ==========

def test_verify_tracks_verifier():
    """独立 verify 端点注入 get_current_user → WorkOrder.verifier_id 被记录。"""
    h = _auth_headers()
    wo = _create_wo(h)
    _to_completed(h, wo["id"])  # 内含独立 verify
    resp = client.get(f"/api/v1/work-orders/{wo['id']}/acceptance", headers=h)
    assert resp.status_code == 200
    verify = resp.json()["data"]["verify"]
    assert verify["verifier_id"] == _admin_id()
    assert verify["verify_time"] is not None


def test_rate_tracks_user():
    """独立 rate 端点注入 get_current_user → rating.user_id 被记录。"""
    h = _auth_headers()
    wo = _create_wo(h)
    _to_completed(h, wo["id"])
    client.post(f"/api/v1/work-orders/{wo['id']}/rate", json={
        "response_rating": 5, "quality_rating": 5, "attitude_rating": 5,
        "comment": "好评",
    }, headers=h)
    resp = client.get(f"/api/v1/work-orders/{wo['id']}/acceptance", headers=h)
    assert resp.status_code == 200
    rating = resp.json()["data"]["rating"]
    assert rating is not None
    assert rating["user_id"] == _admin_id()
