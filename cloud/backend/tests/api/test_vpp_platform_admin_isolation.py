# 审计 #2 越权高危回归: vpp.py 全模块 15 端点收紧 platform admin
# coordinator 为进程级全局单例(无 team 归属), operator 原可操作全平台 VPP。
# 断言: operator → 403 (先过 device:edit 再被 require_platform_admin 拦);
#       admin (默认 client) → 非 401/403 (业务断言放宽)。
import uuid

import bcrypt
import pytest

from app.models.user import User, UserRole
from app.services.vpp import get_vpp_coordinator

VPP = "/api/v1/vpp"

# 全部 15 端点 (method, path, json_body)
# 确定性 ID（uuid5）：模块级参数化 ID 必须跨进程一致，
# 否则 pytest-xdist 各 worker 收集到的参数化 ID 不同 → "Different tests were collected" 收集失败。
# （2026-10-01 规范并行全量 9.6s 即败的根因；uuid4 随机后缀已禁用）
STATION_ID = f"iso-st-{uuid.uuid5(uuid.NAMESPACE_URL, 'tianlian-test-vpp-iso-station').hex[:8]}"
VPP_ENDPOINTS = [
    ("GET", f"{VPP}/capacity", None),
    ("GET", f"{VPP}/stations", None),
    ("POST", f"{VPP}/stations", {"station_id": STATION_ID, "station_name": "隔离测试站"}),
    ("PUT", f"{VPP}/stations/{STATION_ID}", {"online": False}),
    ("DELETE", f"{VPP}/stations/{STATION_ID}", None),
    ("POST", f"{VPP}/resources", {
        "resource_id": f"{STATION_ID}-BAT", "resource_type": "battery", "station_id": STATION_ID,
    }),
    ("GET", f"{VPP}/resources", None),
    ("POST", f"{VPP}/dispatch", {"mode": "economic"}),
    ("GET", f"{VPP}/dispatch/history", None),
    ("GET", f"{VPP}/price", None),
    ("POST", f"{VPP}/dispatch/lp", {"target_power_kw": 0, "duration_min": 15, "mode": "economic"}),
    ("GET", f"{VPP}/optimize/status", None),
    ("POST", f"{VPP}/simulate?count=1", None),
    ("GET", f"{VPP}/auto-scheduler/status", None),
    ("POST", f"{VPP}/auto-scheduler/start", None),
    ("POST", f"{VPP}/auto-scheduler/stop", None),
    ("PATCH", f"{VPP}/auto-scheduler/config?economic_interval=300", None),
]


def _ensure_operator(client):
    s = client._sesh
    if not s.query(User).filter(User.username == "vpp_iso_operator").first():
        s.add(User(
            username="vpp_iso_operator",
            password_hash=bcrypt.hashpw(b"op123456", bcrypt.gensalt()).decode(),
            real_name="vpp隔离测试操作员",
            role=UserRole.OPERATOR,
            status="active",
        ))
        s.commit()
    r = client.post("/api/v1/auth/login",
                    data={"username": "vpp_iso_operator", "password": "op123456"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['data']['token']}"}


@pytest.fixture
def operator_headers(client):
    return _ensure_operator(client)


@pytest.mark.parametrize("method,path,body", VPP_ENDPOINTS)
def test_operator_forbidden_on_all_vpp_endpoints(client, operator_headers, method, path, body):
    resp = client.request(method, path, json=body, headers=operator_headers)
    assert resp.status_code == 403, (
        f"OPERATOR 访问 {method} {path} 应 403，实际 {resp.status_code}\n{resp.text}"
    )


@pytest.mark.parametrize("method,path,body", VPP_ENDPOINTS)
def test_admin_allowed_on_all_vpp_endpoints(client, method, path, body):
    # client fixture 默认注入 admin token；权限断言从严(非401/403)，业务断言放宽
    resp = client.request(method, path, json=body)
    assert resp.status_code not in (401, 403), (
        f"ADMIN 访问 {method} {path} 被拒: {resp.status_code}\n{resp.text}"
    )
    # simulate 会 clear_all 全局单例，收尾恢复模拟基线避免污染后续测试
    if path.endswith("/simulate"):
        get_vpp_coordinator().clear_all()
