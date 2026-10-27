"""
管理后台-市政监管对接 API 测试 (app/api/v1/admin_supervision.py) — 补全 6 端点

覆盖端点 (前缀 /api/v1/admin/supervision, router 依赖 require_role("admin")):
  - GET    /configs/{config_id}              监管配置详情
  - PUT    /configs/{config_id}              更新监管配置
  - DELETE /configs/{config_id}              删除监管配置
  - GET    /reports/{report_id}              上报记录详情
  - POST   /reports/{report_id}/retry        重试失败上报
  - GET    /compliance/{check_id}            合规检查详情

注: 本路由为 admin 兼容入口 (require_role("admin")), 无 team scoping — admin 角色全豁免。
与 tests/api/test_supervision.py (operate 域, require_permission('operate:manage') + team 隔离)
是不同路由文件, schema 也不同 (admin 版 SupConfigCreate 无 platform_type/protocol_type,
仅校验 report_strategy/status)。

测试矩阵:
  ① happy path: 各端点正常读取/更新/删除/状态流转
  ② error path: 404 (资源不存在) / 400 (retry 已 success / 非法枚举)

风格同 test_supervision.py: client 默认 admin (require_role 豁免), 直接 seed ORM 到 client._sesh。

铁律: 仅加测试, 不改业务代码。
"""
from datetime import datetime, timezone
from decimal import Decimal

from app.models.admin_supervision import (
    MunicipalSupervisionConfig,
    RegulatoryReport,
    ComplianceCheck,
)


# ─── seed helpers ───

def _seed_config(session, city="测试市", status="active", **overrides):
    c = MunicipalSupervisionConfig(
        team_id=overrides.get("team_id", 0),
        city=overrides.get("city", city),
        platform_url=overrides.get("platform_url", "https://gov.example.com/api"),
        auth_config=overrides.get("auth_config"),
        report_strategy=overrides.get("report_strategy", "scheduled"),
        report_interval_seconds=overrides.get("report_interval_seconds", 60),
        station_endpoints=overrides.get("station_endpoints"),
        heartbeat_enabled=overrides.get("heartbeat_enabled", 1),
        status=status,
        remark=overrides.get("remark"),
    )
    session.add(c)
    session.commit()
    session.refresh(c)
    return c


def _seed_report(session, config_id=1, status="failed", **overrides):
    r = RegulatoryReport(
        team_id=overrides.get("team_id", 0),
        config_id=config_id,
        city=overrides.get("city", "测试市"),
        report_type=overrides.get("report_type", "heartbeat"),
        report_content=overrides.get("report_content"),
        status=status,
        retry_count=overrides.get("retry_count", 1),
        error_message=overrides.get("error_message", "网络超时"),
        reported_at=overrides.get("reported_at", datetime.now(timezone.utc)),
    )
    session.add(r)
    session.commit()
    session.refresh(r)
    return r


def _seed_check(session, config_id=1, **overrides):
    cc = ComplianceCheck(
        team_id=overrides.get("team_id", 0),
        config_id=config_id,
        city=overrides.get("city", "测试市"),
        check_type=overrides.get("check_type", "data_integrity"),
        result=overrides.get("result", "pass"),
        score=overrides.get("score", Decimal("88.50")),
        details=overrides.get("details"),
        checked_at=overrides.get("checked_at", datetime.now(timezone.utc)),
    )
    session.add(cc)
    session.commit()
    session.refresh(cc)
    return cc


BASE = "/api/v1/admin/supervision"


# ==================== 配置: 详情 / 更新 / 删除 ====================

class TestAdminSupervisionConfig:
    """GET/PUT/DELETE /configs/{config_id} — happy + 404 + 枚举校验。"""

    def test_get_config_detail(self, client):
        c = _seed_config(client._sesh, city="广州市")
        r = client.get(f"{BASE}/configs/{c.id}")
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["id"] == c.id
        assert d["city"] == "广州市"
        assert d["platform_url"] == "https://gov.example.com/api"
        # 时间戳序列化为 isoformat 字符串
        assert isinstance(d["created_at"], str)

    def test_get_config_not_found_404(self, client):
        r = client.get(f"{BASE}/configs/999999")
        assert r.status_code == 404
        assert "不存在" in r.json()["detail"]

    def test_update_config_partial(self, client):
        """model_dump(exclude_unset=True) 仅改传入字段, 其余保持。"""
        c = _seed_config(client._sesh, city="原名", platform_url="https://old")
        r = client.put(f"{BASE}/configs/{c.id}", json={"city": "新名"})
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["city"] == "新名"
        assert d["platform_url"] == "https://old"  # 未传 → 保持

    def test_update_config_auth_config_reserialized(self, client):
        """更新 auth_config → JSON 重序列化, 响应还原 dict。"""
        c = _seed_config(client._sesh)
        r = client.put(f"{BASE}/configs/{c.id}", json={"auth_config": {"token": "new"}})
        assert r.status_code == 200
        assert r.json()["data"]["auth_config"] == {"token": "new"}

    def test_update_config_invalid_status_400(self, client):
        c = _seed_config(client._sesh)
        r = client.put(f"{BASE}/configs/{c.id}", json={"status": "__bad__"})
        assert r.status_code == 422  # Literal 前置 (卡 6031add1)

    def test_update_config_invalid_report_strategy_400(self, client):
        c = _seed_config(client._sesh)
        r = client.put(f"{BASE}/configs/{c.id}", json={"report_strategy": "__bad__"})
        assert r.status_code == 422  # Literal 前置 (卡 6031add1)

    def test_update_config_not_found_404(self, client):
        r = client.put(f"{BASE}/configs/999999", json={"city": "x"})
        assert r.status_code == 404

    def test_delete_config(self, client):
        c = _seed_config(client._sesh, city="待删")
        r = client.delete(f"{BASE}/configs/{c.id}")
        assert r.status_code == 200, r.text
        assert r.json()["data"]["id"] == c.id
        # 删除后再查 → 404
        assert client.get(f"{BASE}/configs/{c.id}").status_code == 404

    def test_delete_config_not_found_404(self, client):
        r = client.delete(f"{BASE}/configs/999999")
        assert r.status_code == 404


# ==================== 上报记录: 详情 / 重试 ====================

class TestAdminSupervisionReport:
    """GET /reports/{report_id} + POST /reports/{report_id}/retry。"""

    def test_get_report_detail(self, client):
        c = _seed_config(client._sesh)
        rep = _seed_report(client._sesh, config_id=c.id, status="failed",
                           error_message="timeout")
        r = client.get(f"{BASE}/reports/{rep.id}")
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["status"] == "failed"
        assert d["error_message"] == "timeout"
        assert d["config_id"] == c.id

    def test_get_report_not_found_404(self, client):
        r = client.get(f"{BASE}/reports/999999")
        assert r.status_code == 404

    def test_retry_failed_to_success(self, client):
        """failed → retry → success, retry_count+1, error_message 清空。"""
        c = _seed_config(client._sesh)
        rep = _seed_report(client._sesh, config_id=c.id, status="failed",
                           retry_count=2, error_message="网络超时")
        r = client.post(f"{BASE}/reports/{rep.id}/retry")
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["status"] == "success"
        assert d["retry_count"] == 3
        assert d["error_message"] is None

    def test_retry_pending_to_success(self, client):
        """pending (在途) → retry → success (端点仅拦 success)。"""
        c = _seed_config(client._sesh)
        rep = _seed_report(client._sesh, config_id=c.id, status="pending", retry_count=0)
        r = client.post(f"{BASE}/reports/{rep.id}/retry")
        assert r.status_code == 200
        assert r.json()["data"]["status"] == "success"
        assert r.json()["data"]["retry_count"] == 1

    def test_retry_already_success_400(self, client):
        """已 success 的上报无需重试 → 400。"""
        c = _seed_config(client._sesh)
        rep = _seed_report(client._sesh, config_id=c.id, status="success")
        r = client.post(f"{BASE}/reports/{rep.id}/retry")
        assert r.status_code == 400
        assert "无需重试" in r.json()["detail"]

    def test_retry_not_found_404(self, client):
        r = client.post(f"{BASE}/reports/999999/retry")
        assert r.status_code == 404


# ==================== 合规检查: 详情 ====================

class TestAdminSupervisionCompliance:
    """GET /compliance/{check_id}。"""

    def test_get_compliance_detail(self, client):
        c = _seed_config(client._sesh)
        cc = _seed_check(client._sesh, config_id=c.id, result="warn",
                         score=Decimal("60.50"))
        r = client.get(f"{BASE}/compliance/{cc.id}")
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["id"] == cc.id
        assert d["result"] == "warn"
        assert d["score"] == 60.5
        assert d["check_type"] == "data_integrity"

    def test_get_compliance_not_found_404(self, client):
        r = client.get(f"{BASE}/compliance/999999")
        assert r.status_code == 404
