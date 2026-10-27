"""
工单创建人修复回归测试 [a51f4772]

生产事故: POST /api/v1/work-orders 全 500，journalctl 证据
psycopg2 ForeignKeyViolation work_orders_creator_id_fkey —
Key (creator_id)=(999) is not present in table "users"。

根因: create_workorder 硬编码 creator_id=999（开发 SQLite 恰有 id=999
用户，测试绿；生产 PG 无此用户，FK 违约 500）。

本套测试在 fresh DB（conftest 每 function fresh UUID 库，天然无 id=999）
下验证 creator_id 取自当前登录真实用户，杜绝硬编码回归。
"""
import inspect
import re
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    pass


def _login(username: str, password: str) -> str:
    resp = client.post(
        "/api/v1/auth/login",
        data={"username": username, "password": password},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    return data.get("token") or data.get("data", {}).get("token")


def _auth(username: str, password: str) -> dict:
    return {"Authorization": f"Bearer {_login(username, password)}"}


def _seed_user(test_db, username, password, role, team_id=None, real_name=None) -> int:
    from app.models.user import User
    from app.api.v1.auth import get_password_hash
    u = User(
        username=username,
        password_hash=get_password_hash(password),
        role=role,
        status="active",
        real_name=real_name or username,
        team_id=team_id,
    )
    db = test_db["SessionLocal"]()
    db.add(u)
    db.commit()
    db.refresh(u)
    uid = u.id
    db.close()
    return uid


def _seed_station(test_db, name, code, team_id) -> int:
    from app.models.station import Station, StationStatus
    st = Station(name=name, code=code, status=StationStatus.NORMAL, team_id=team_id)
    db = test_db["SessionLocal"]()
    db.add(st)
    db.commit()
    db.refresh(st)
    sid = st.id
    db.close()
    return sid


def _user_id(test_db, username) -> int:
    from app.models.user import User
    db = test_db["SessionLocal"]()
    u = db.query(User).filter(User.username == username).first()
    uid = u.id if u else None
    db.close()
    return uid


# ========== 普通用户创建: creator_id 必须绑定本人 ==========

def test_creator_id_binds_to_current_normal_user(test_db):
    """非 admin 用户带本 team station 创建工单 → creator_id == 该用户 id。

    未修前 creator_id 硬编码 999（fresh DB 无此用户），断言失败。
    """
    from app.models.user import UserRole
    team = 7001
    uid = _seed_user(
        test_db, "engineer_wo", "wo123", UserRole.ENGINEER,
        team_id=team, real_name="工单测试工程师",
    )
    sid = _seed_station(test_db, "工单测试站", "WOSTA01", team_id=team)

    h = _auth("engineer_wo", "wo123")
    resp = client.post(
        "/api/v1/work-orders",
        json={
            "fault_desc": "普通用户报修",
            "type": "repair",
            "level": "warning",
            "station_id": sid,
        },
        headers=h,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["creator_id"] == uid


# ========== admin 创建: creator_id 必须是 admin 本人 ==========

def test_creator_id_binds_to_admin(test_db):
    """admin 创建工单（可不指定 station）→ creator_id == admin.id。

    未修前 creator_id 硬编码 999（admin 在 fresh DB 为首个用户，id=1），断言失败。
    """
    h = _auth("admin", "admin123")
    resp = client.post(
        "/api/v1/work-orders",
        json={"fault_desc": "管理员建单", "type": "repair", "level": "warning"},
        headers=h,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["creator_id"] == _user_id(test_db, "admin")


# ========== 防回归: workorders 模块不得残留硬编码 creator_id=999 ==========

def test_no_hardcoded_creator_999_in_workorders_module():
    """workorders 模块源码不得再出现硬编码 creator_id=999（生产 FK 违约根因）。

    仅断言本卡范围 (app/api/v1/workorders.py)；其余模块 (scan/smart_diagnosis/
    health_monitor) 的 999 为系统/临时用户语义，属其他卡范围，不在此约束。
    """
    import app.api.v1.workorders as wo_mod
    src = inspect.getsource(wo_mod)
    assert re.search(r"creator_id\s*=\s*999\b", src) is None, (
        "workorders 模块残留硬编码 creator_id=999（生产 FK 违约根因）"
    )
