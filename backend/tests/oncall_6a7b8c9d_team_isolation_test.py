"""
卡 6a7b8c9d (审计#6): on_call 跨队越权回归测试
覆盖: PUT /shifts/{id} 篡改、POST /shifts/handover 交接、GET/POST /logs 读写隔离
口径: 团队级不匹配 → 404 (对齐 assert_team_access); platform admin 全通; 列表收敛本队
"""
import pytest
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

PATH_RULES = "/api/v1/on-call/rules"


@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    from app.core.cache import clear_memory_cache
    clear_memory_cache()


def _login(username, password):
    resp = client.post("/api/v1/auth/login", data={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    return data.get("token") or data.get("data", {}).get("token")


def _headers(username, password):
    return {"Authorization": f"Bearer {_login(username, password)}"}


def _admin_headers():
    return _headers("admin", "admin123")


def _create_team(name):
    resp = client.post("/api/v1/teams", json={"name": name, "description": "卡6a7b8c9d"}, headers=_admin_headers())
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["id"]


def _create_team_user(test_db, username, team_id):
    from app.models.user import User, UserRole
    from app.api.v1.auth import get_password_hash
    db = test_db["SessionLocal"]()
    db.add(User(
        username=username,
        password_hash=get_password_hash("test123"),
        real_name=username,
        role=UserRole.ENGINEER,
        team_id=team_id,
        status="active",
    ))
    db.commit()
    user_id = db.query(User).filter(User.username == username).first().id
    db.close()
    return user_id


def _create_rule_and_shift(team_id, user_id):
    resp = client.post(
        f"{PATH_RULES}",
        json={
            "name": "卡6a7b8c9d规则",
            "team_id": team_id,
            "schedule_type": "weekly",
            "rotation_order": [user_id],
            "shift_duration_hours": 168,
            "overlap_minutes": 30,
            "escalation_level": 2,
            "escalation_timeout_minutes": 30,
        },
        headers=_admin_headers(),
    )
    assert resp.status_code == 200, resp.text
    rule_id = resp.json()["rule_id"]

    start = datetime.now(timezone.utc).isoformat()
    end = (datetime.now(timezone.utc) + timedelta(hours=8)).isoformat()
    resp = client.post(
        "/api/v1/on-call/shifts",
        json={"rule_id": rule_id, "user_id": user_id, "start_time": start, "end_time": end},
        headers=_admin_headers(),
    )
    assert resp.status_code == 200, resp.text
    shift_id = resp.json()["shift_id"]
    return rule_id, shift_id


@pytest.fixture
def scene(test_db):
    """team_a 持有规则/班次; user_a/user_b 分属两队的 ENGINEER"""
    team_a = _create_team("卡6a7b8c9d队A")
    team_b = _create_team("卡6a7b8c9d队B")
    user_a = _create_team_user(test_db, "card6a7b_user_a", team_a)
    user_b = _create_team_user(test_db, "card6a7b_user_b", team_b)
    rule_id, shift_id = _create_rule_and_shift(team_a, user_a)
    return {"team_a": team_a, "team_b": team_b, "user_a": user_a, "user_b": user_b,
            "rule_id": rule_id, "shift_id": shift_id,
            "ha": _headers("card6a7b_user_a", "test123"),
            "hb": _headers("card6a7b_user_b", "test123"),
            "hadmin": _admin_headers()}


def _log_payload(shift_id, user_id):
    return {"shift_id": shift_id, "user_id": user_id, "event_type": "note",
            "content": "卡6a7b8c9d日志", "severity": "info"}


# ── PUT /shifts/{id} ──

def test_update_shift_cross_team_denied(scene):
    resp = client.put(f"/api/v1/on-call/shifts/{scene['shift_id']}?status=cancelled", headers=scene["hb"])
    assert resp.status_code == 404


def test_update_shift_same_team_ok(scene):
    resp = client.put(f"/api/v1/on-call/shifts/{scene['shift_id']}?status=cancelled", headers=scene["ha"])
    assert resp.status_code == 200


def test_update_shift_platform_admin_ok(scene):
    resp = client.put(f"/api/v1/on-call/shifts/{scene['shift_id']}?status=active", headers=scene["hadmin"])
    assert resp.status_code == 200


# ── POST /shifts/handover ──

def test_handover_cross_team_denied(scene):
    resp = client.post("/api/v1/on-call/shifts/handover",
                       json={"shift_id": scene["shift_id"], "user_id": scene["user_b"], "notes": "越权交接"},
                       headers=scene["hb"])
    assert resp.status_code == 404


def test_handover_same_team_ok(scene):
    resp = client.post("/api/v1/on-call/shifts/handover",
                       json={"shift_id": scene["shift_id"], "user_id": scene["user_a"], "notes": "正常交接"},
                       headers=scene["ha"])
    assert resp.status_code == 200


# ── POST /logs ──

def test_create_log_cross_team_denied(scene):
    resp = client.post("/api/v1/on-call/logs", json=_log_payload(scene["shift_id"], scene["user_b"]),
                       headers=scene["hb"])
    assert resp.status_code == 404


def test_create_log_same_team_ok(scene):
    resp = client.post("/api/v1/on-call/logs", json=_log_payload(scene["shift_id"], scene["user_a"]),
                       headers=scene["ha"])
    assert resp.status_code == 200


# ── GET /logs ──

def test_list_logs_team_scoped(scene):
    # 本队先写一条日志
    resp = client.post("/api/v1/on-call/logs", json=_log_payload(scene["shift_id"], scene["user_a"]),
                       headers=scene["ha"])
    assert resp.status_code == 200

    # 他队: 列表收敛, 看不到 team_a 的日志
    resp = client.get("/api/v1/on-call/logs", headers=scene["hb"])
    assert resp.status_code == 200
    assert resp.json()["total"] == 0

    # 本队: 可见
    resp = client.get("/api/v1/on-call/logs", headers=scene["ha"])
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1

    # platform admin: 全通
    resp = client.get("/api/v1/on-call/logs", headers=scene["hadmin"])
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1
