"""
工单 dispatch_type + source 字段测试 (maint-platform-spec §4 缺口)

dispatch_type: assign=指派 / grab=抢单  (默认 assign)
source: manual/alarm/app/inspection      (默认 manual)

覆盖:
- 模型层: 两新列存在 + 默认值 + nullable=False
- API 创建: 默认值 / 显式传 source
- API 列表: 按 dispatch_type / source 可选过滤
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.workorder import WorkOrder

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
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


# ========== 模型层 ==========

def test_model_has_dispatch_type_and_source_columns():
    """WorkOrder 必须含 dispatch_type / source 两列。"""
    cols = [c.name for c in WorkOrder.__table__.columns]
    assert "dispatch_type" in cols
    assert "source" in cols


def test_model_column_defaults_and_nullable():
    """两列默认值 dispatch_type='assign' / source='manual'，且 nullable=False。"""
    dispatch_col = WorkOrder.__table__.columns["dispatch_type"]
    source_col = WorkOrder.__table__.columns["source"]
    assert dispatch_col.default.arg == "assign"
    assert source_col.default.arg == "manual"
    assert not dispatch_col.nullable
    assert not source_col.nullable


# ========== 创建工单 ==========

def test_create_defaults_source_manual_dispatch_assign():
    """不传 source 时，创建出的工单 source=manual / dispatch_type=assign。"""
    h = _auth_headers()
    wo = _create_wo(h)
    assert wo["source"] == "manual"
    assert wo["dispatch_type"] == "assign"


def test_create_with_source_alarm():
    h = _auth_headers()
    wo = _create_wo(h, source="alarm")
    assert wo["source"] == "alarm"


def test_create_with_source_inspection():
    h = _auth_headers()
    wo = _create_wo(h, source="inspection")
    assert wo["source"] == "inspection"


# ========== 列表过滤 ==========

def test_list_filter_by_source():
    import time
    h = _auth_headers()
    _create_wo(h, source="alarm")
    time.sleep(1.1)  # wo_id 秒级精度, 避免同秒主键冲突 (同 test_list_pagination 模式)
    _create_wo(h, source="manual")
    resp = client.get("/api/v1/work-orders?source=alarm", headers=h)
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["source"] == "alarm"


def test_list_filter_by_source_no_match():
    h = _auth_headers()
    _create_wo(h, source="manual")
    resp = client.get("/api/v1/work-orders?source=app", headers=h)
    assert resp.status_code == 200
    assert len(resp.json()["data"]["items"]) == 0


def test_list_filter_by_dispatch_type():
    h = _auth_headers()
    _create_wo(h)  # 默认 assign
    resp = client.get("/api/v1/work-orders?dispatch_type=assign", headers=h)
    assert resp.status_code == 200
    assert len(resp.json()["data"]["items"]) == 1
    resp2 = client.get("/api/v1/work-orders?dispatch_type=grab", headers=h)
    assert len(resp2.json()["data"]["items"]) == 0
