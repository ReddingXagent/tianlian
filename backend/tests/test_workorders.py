"""
工单管理 API 测试
覆盖: /work-orders — CRUD、状态流转(接单/开始/完成/验收/驳回/转单/催单)、日志、派单
"""
import pytest
from datetime import datetime
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


def _create_wo(headers, **overrides):
    defaults = dict(fault_desc="测试故障", type="repair", level="warning")
    defaults.update(overrides)
    resp = client.post("/api/v1/work-orders", json=defaults, headers=headers)
    assert resp.status_code == 200
    return resp.json()["data"]


def _seed_engineer(test_db, **overrides):
    from app.models.user import User, UserRole
    from app.api.v1.auth import get_password_hash
    defaults = dict(
        username=f"eng_{datetime.now().strftime('%H%M%S%f')}",
        password_hash=get_password_hash("test123"),
        role=UserRole.ENGINEER,
        status="active",
        real_name="测试工程师",
    )
    defaults.update(overrides)
    u = User(**defaults)
    db = test_db["SessionLocal"]()
    db.add(u)
    db.commit()
    db.refresh(u)
    uid = u.id
    db.close()
    return uid


# ========== 鉴权检查 ==========

def test_list_requires_auth(anon_client):
    resp = anon_client.get("/api/v1/work-orders")
    assert resp.status_code == 401


def test_create_requires_auth(anon_client):
    resp = anon_client.post("/api/v1/work-orders", json={"fault_desc": "test"})
    assert resp.status_code in (401, 403)


def test_get_requires_auth(anon_client):
    resp = anon_client.get("/api/v1/work-orders/WO-999")
    assert resp.status_code == 401


def test_delete_requires_auth(anon_client):
    resp = anon_client.delete("/api/v1/work-orders/WO-999")
    assert resp.status_code in (401, 403)


# ========== 列表与筛选 ==========

def test_list_empty():
    h = _auth_headers()
    resp = client.get("/api/v1/work-orders", headers=h)
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 200
    assert data["data"]["items"] == []


def test_list_after_create():
    h = _auth_headers()
    _create_wo(h)
    resp = client.get("/api/v1/work-orders", headers=h)
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert len(items) == 1


def test_list_filter_by_status():
    h = _auth_headers()
    _create_wo(h)
    resp = client.get("/api/v1/work-orders?status=pending", headers=h)
    assert resp.status_code == 200
    assert len(resp.json()["data"]["items"]) == 1


def test_list_filter_by_status_no_match():
    h = _auth_headers()
    _create_wo(h)
    resp = client.get("/api/v1/work-orders?status=completed", headers=h)
    assert resp.status_code == 200
    assert len(resp.json()["data"]["items"]) == 0


def test_list_pagination():
    h = _auth_headers()
    import time
    for i in range(3):
        _create_wo(h, fault_desc=f"故障{i}")
        time.sleep(1.1)
    resp = client.get("/api/v1/work-orders?page=1&page_size=2", headers=h)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data["items"]) == 2
    assert data["total"] == 3


# ========== 创建工单 ==========

def test_create_success():
    h = _auth_headers()
    wo = _create_wo(h)
    assert wo["fault_desc"] == "测试故障"
    assert wo["status"] == "pending"


def test_create_with_type_and_level():
    h = _auth_headers()
    wo = _create_wo(h, type="emergency", level="critical")
    assert wo["type"] == "emergency"
    assert wo["level"] == "critical"


# ========== 获取详情 ==========

def test_get_detail():
    h = _auth_headers()
    wo = _create_wo(h)
    resp = client.get(f"/api/v1/work-orders/{wo['id']}", headers=h)
    assert resp.status_code == 200
    assert resp.json()["code"] == 200


def test_get_not_found():
    h = _auth_headers()
    resp = client.get("/api/v1/work-orders/WO-NOTEXIST", headers=h)
    assert resp.status_code == 404


# ========== 更新工单 ==========

def test_update_fault_desc():
    h = _auth_headers()
    wo = _create_wo(h)
    resp = client.put(f"/api/v1/work-orders/{wo['id']}", json={"fault_desc": "更新描述"}, headers=h)
    assert resp.status_code == 200


def test_update_not_found():
    h = _auth_headers()
    resp = client.put("/api/v1/work-orders/WO-NOTEXIST", json={"fault_desc": "x"}, headers=h)
    assert resp.status_code == 404


# ========== 状态流转: 接单 ==========

def test_accept_success():
    h = _auth_headers()
    wo = _create_wo(h)
    resp = client.post(f"/api/v1/work-orders/{wo['id']}/accept", headers=h)
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "accepted"


def test_accept_wrong_status():
    h = _auth_headers()
    wo = _create_wo(h)
    client.post(f"/api/v1/work-orders/{wo['id']}/accept", headers=h)
    resp = client.post(f"/api/v1/work-orders/{wo['id']}/accept", headers=h)
    assert resp.status_code == 400


# ========== 状态流转: 开始处理 ==========

def test_start_after_accept():
    h = _auth_headers()
    wo = _create_wo(h)
    client.post(f"/api/v1/work-orders/{wo['id']}/accept", headers=h)
    resp = client.post(f"/api/v1/work-orders/{wo['id']}/start", headers=h)
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "processing"


def test_start_directly_from_pending():
    h = _auth_headers()
    wo = _create_wo(h)
    resp = client.post(f"/api/v1/work-orders/{wo['id']}/start", headers=h)
    assert resp.status_code == 200


# ========== 状态流转: 完成 ==========

def test_complete_from_processing():
    h = _auth_headers()
    wo = _create_wo(h)
    client.post(f"/api/v1/work-orders/{wo['id']}/accept", headers=h)
    client.post(f"/api/v1/work-orders/{wo['id']}/start", headers=h)
    resp = client.post(f"/api/v1/work-orders/{wo['id']}/complete?solution=已修复", headers=h)
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "pending_verify"


def test_complete_wrong_status():
    h = _auth_headers()
    wo = _create_wo(h)
    resp = client.post(f"/api/v1/work-orders/{wo['id']}/complete", headers=h)
    assert resp.status_code == 400


# ========== 状态流转: 验收 ==========

def test_verify_after_complete():
    h = _auth_headers()
    wo = _create_wo(h)
    client.post(f"/api/v1/work-orders/{wo['id']}/accept", headers=h)
    client.post(f"/api/v1/work-orders/{wo['id']}/start", headers=h)
    client.post(f"/api/v1/work-orders/{wo['id']}/complete", headers=h)
    resp = client.post(f"/api/v1/work-orders/{wo['id']}/verify", headers=h)
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "completed"


def test_verify_wrong_status():
    h = _auth_headers()
    wo = _create_wo(h)
    resp = client.post(f"/api/v1/work-orders/{wo['id']}/verify", headers=h)
    assert resp.status_code == 400


# ========== 状态流转: 驳回 ==========

def test_reject_after_complete():
    h = _auth_headers()
    wo = _create_wo(h)
    client.post(f"/api/v1/work-orders/{wo['id']}/accept", headers=h)
    client.post(f"/api/v1/work-orders/{wo['id']}/start", headers=h)
    client.post(f"/api/v1/work-orders/{wo['id']}/complete", headers=h)
    resp = client.post(f"/api/v1/work-orders/{wo['id']}/reject?reason=不合格", headers=h)
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "processing"


def test_reject_wrong_status():
    h = _auth_headers()
    wo = _create_wo(h)
    resp = client.post(f"/api/v1/work-orders/{wo['id']}/reject?reason=no", headers=h)
    assert resp.status_code == 400


# ========== 催单 ==========

def test_urge_success():
    h = _auth_headers()
    wo = _create_wo(h)
    resp = client.post(f"/api/v1/work-orders/{wo['id']}/urge", json={"message": "快处理"}, headers=h)
    assert resp.status_code == 200


def test_urge_completed_fails():
    h = _auth_headers()
    wo = _create_wo(h)
    client.post(f"/api/v1/work-orders/{wo['id']}/accept", headers=h)
    client.post(f"/api/v1/work-orders/{wo['id']}/start", headers=h)
    client.post(f"/api/v1/work-orders/{wo['id']}/complete", headers=h)
    client.post(f"/api/v1/work-orders/{wo['id']}/verify", headers=h)
    resp = client.post(f"/api/v1/work-orders/{wo['id']}/urge", headers=h)
    assert resp.status_code == 400


# ========== 删除 ==========

def test_delete_success():
    h = _auth_headers()
    wo = _create_wo(h)
    resp = client.delete(f"/api/v1/work-orders/{wo['id']}", headers=h)
    assert resp.status_code == 200


def test_delete_not_found():
    h = _auth_headers()
    resp = client.delete("/api/v1/work-orders/WO-NOTEXIST", headers=h)
    assert resp.status_code == 404


# ========== 日志 ==========

def test_logs_empty():
    h = _auth_headers()
    wo = _create_wo(h)
    resp = client.get(f"/api/v1/work-orders/{wo['id']}/logs", headers=h)
    assert resp.status_code == 200
    assert resp.json()["code"] == 200


def test_logs_after_accept():
    h = _auth_headers()
    wo = _create_wo(h)
    client.post(f"/api/v1/work-orders/{wo['id']}/accept", headers=h)
    resp = client.get(f"/api/v1/work-orders/{wo['id']}/logs", headers=h)
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert len(items) >= 1


# ========== 创建人追踪 + FK违约兜底 (卡片 1236b769) ==========

def test_create_records_real_creator_id(test_db):
    """创建工单 creator_id 必须记录真实操作人 (user.id)。

    回归锚点: 生产曾硬编码 creator_id=999 → PostgreSQL ForeignKeyViolation
    work_orders_creator_id_fkey (999 不在 users 表) → 500。绝不再硬编码。
    """
    from app.models.user import User
    s = test_db["SessionLocal"]()
    admin = s.query(User).filter(User.username == "admin").first()
    admin_id = admin.id
    s.close()

    h = _auth_headers()
    wo = _create_wo(h)
    assert wo["creator_id"] == admin_id
    assert wo["creator_id"] != 999  # 回归锚点: 绝不再硬编码


def test_create_fk_violation_returns_4xx(test_db):
    """FK违约 (关联不存在的 station_id) → IntegrityError 兜底 → 4xx, 绝不裸 500。

    生产 PostgreSQL 强制外键; SQLite 默认关闭 FK 校验, 故独立建
    PRAGMA foreign_keys=ON 引擎并 override get_db 复现真实外键约束。
    admin 豁免前置 station 校验 → 直达 db.commit 触发 FK 违约。
    """
    import os as _os
    import uuid as _uuid
    import bcrypt as _bcrypt
    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import sessionmaker
    from app.core.database import Base, get_db
    import app.models  # 注册全部模型到 Base.metadata

    db_path = f"/tmp/tianlian_fk_{_uuid.uuid4().hex}.db"
    eng = create_engine(
        f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
    )

    @event.listens_for(eng, "connect")
    def _enable_fk(dbapi_connection, record):
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(bind=eng)
    FKSession = sessionmaker(bind=eng)
    s = FKSession()
    from app.models.user import User, UserRole
    s.add(User(
        username="admin",
        password_hash=_bcrypt.hashpw(b"admin123", _bcrypt.gensalt()).decode(),
        role=UserRole.ADMIN,
        status="active",
    ))
    s.commit()

    from app.main import app as main_app
    main_app.dependency_overrides[get_db] = lambda: FKSession()
    try:
        token = _login()
        h = {"Authorization": f"Bearer {token}"}
        # station_id=999999 不存在 → commit 触发 FK 约束 (PRAGMA foreign_keys=ON)
        resp = client.post(
            "/api/v1/work-orders",
            json={"fault_desc": "fk违约测试", "station_id": 999999},
            headers=h,
        )
        assert resp.status_code != 500, "FK违约不得裸 500, 必须兜底为 4xx"
        assert resp.status_code == 400, f"期望兜底 400, 实际 {resp.status_code}"
    finally:
        main_app.dependency_overrides.pop(get_db, None)
        s.close()
        eng.dispose()
        if _os.path.exists(db_path):
            _os.unlink(db_path)


# ========== 审计归属 (卡 3dd8954e) ==========

def test_workorder_audit_attribution_card3dd8954e():
    """工单 update/accept 审计归属真实操作用户 (卡 3dd8954e, 修 user_id=0 硬编码)"""
    from app.models.audit_log import AuditLog
    import app.core.database as _dbmod
    from app.models.user import User
    s = _dbmod.SessionLocal()
    try:
        admin = s.query(User).filter(User.username == "admin").first()
        assert admin is not None and admin.id != 0

        h = _auth_headers()
        wo = _create_wo(h, fault_desc="审计归属工单")
        wo_id = wo["id"]

        resp = client.put(f"/api/v1/work-orders/{wo_id}",
                          json={"fault_desc": "审计归属更新"}, headers=h)
        assert resp.status_code == 200, resp.text
        log = (s.query(AuditLog)
               .filter(AuditLog.module == "workorders", AuditLog.action == "update",
                       AuditLog.target_id == wo_id)
               .order_by(AuditLog.id.desc()).first())
        assert log is not None, "工单更新应产生审计记录"
        assert log.user_id == admin.id, f"审计归属错误: user_id={log.user_id} 期望 {admin.id}"
        assert log.username == admin.username

        resp = client.post(f"/api/v1/work-orders/{wo_id}/accept", headers=h)
        assert resp.status_code == 200, resp.text
        log = (s.query(AuditLog)
               .filter(AuditLog.module == "workorders", AuditLog.action == "update",
                       AuditLog.target_id == wo_id)
               .order_by(AuditLog.id.desc()).first())
        assert log is not None, "接单应产生审计记录"
        assert log.user_id == admin.id, f"审计归属错误: user_id={log.user_id} 期望 {admin.id}"
        assert log.username == admin.username
    finally:
        s.close()
