"""
运营-市政监管对接 API 测试 (SPEC §2.5)

覆盖端点前缀: /api/v1/operate/supervision
  - /configs     监管平台配置 CRUD (按运营团队隔离)
  - /reports     上报记录 查询/详情/手动触发/重试
  - /compliance  合规检查 查询/详情/触发

测试矩阵:
  ① 上报数据构造 (schema 默认值 / auth_config·station_endpoints·report_content
     JSON 序列化往返 / team_id 服务端强制 / 时间戳 isoformat)
  ② 状态流转 (retry: failed·pending → success; 已 success → 400; retry_count 自增;
     error_message 清空)
  ③ 过滤 + 分页边界 (city / status / report_type / check_type / result / config_id;
     page·page_size 422 边界; 空数据; 页越界)
  ④ 权限 scoping (router 级 operate:manage → viewer 403; team_scope 列表隔离;
     assert_team_access 单资源跨 team → 404; admin 豁免; 跨 team 与不存在均 404)

与 tests/api/test_ops_invoice.py / test_deps_team_scoping.py 同源 mock 风格:
client fixture 默认 admin (team_id=None, 平台级, team_scope=None); team 级用例经
_add_user + _login_token 注入 ENGINEER token, 直接 seed ORM 到 client._sesh (与
端点 get_db 共享同一测试库), 不依赖真实外网/真实生产 DB。

发现的业务缺陷见文件末尾 "已知缺陷清单" 注释, 只记录不修改。
"""
import bcrypt
import pytest
from datetime import datetime, timezone
from decimal import Decimal

from app.models.admin_supervision import (
    MunicipalSupervisionConfig,
    RegulatoryReport,
    ComplianceCheck,
)
from app.models.user import User, UserRole, Team


# ─── seed helpers ───

def _add_user(session, username, role, team_id=None, password="pw123456"):
    """创建并提交用户, 返回 ORM (供 team scoping 用例复用)。"""
    u = User(
        username=username,
        real_name=username,
        role=role,
        team_id=team_id,
        status="active",
        password_hash=bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode(),
    )
    session.add(u)
    session.commit()
    session.refresh(u)
    return u


def _login_token(client, username, password="pw123456"):
    r = client.post("/api/v1/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, f"登录失败 {username}: {r.text}"
    return r.json().get("data", {}).get("token") or r.json().get("token")


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _seed_config(session, team_id=0, city="测试市", status="active", **overrides):
    """直接 seed 一条监管配置。auth_config / station_endpoints 期望传 JSON 字符串。"""
    c = MunicipalSupervisionConfig(
        team_id=team_id,
        city=overrides.get("city", city),
        city_code=overrides.get("city_code"),
        platform_name=overrides.get("platform_name"),
        platform_type=overrides.get("platform_type", "generic"),
        protocol_type=overrides.get("protocol_type", "http_push"),
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


def _seed_report(session, team_id=0, config_id=1, status="success", **overrides):
    r = RegulatoryReport(
        team_id=team_id,
        config_id=config_id,
        city=overrides.get("city", "测试市"),
        report_type=overrides.get("report_type", "heartbeat"),
        report_content=overrides.get("report_content"),
        status=status,
        retry_count=overrides.get("retry_count", 0),
        error_message=overrides.get("error_message"),
        reported_at=overrides.get("reported_at", datetime.now(timezone.utc)),
    )
    session.add(r)
    session.commit()
    session.refresh(r)
    return r


def _seed_check(session, team_id=0, config_id=1, **overrides):
    cc = ComplianceCheck(
        team_id=team_id,
        config_id=config_id,
        city=overrides.get("city", "测试市"),
        check_type=overrides.get("check_type", "data_integrity"),
        result=overrides.get("result", "pass"),
        score=overrides.get("score", Decimal("0.00")),
        details=overrides.get("details"),
        checked_at=overrides.get("checked_at", datetime.now(timezone.utc)),
    )
    session.add(cc)
    session.commit()
    session.refresh(cc)
    return cc


BASE_CONFIG = {"city": "测试市", "platform_url": "https://gov.example.com/api"}


# ==================== 配置: 上报数据构造 + 创建校验 ====================

class TestSupervisionConfigCreate:
    """配置创建: 默认值 / JSON 字段序列化往返 / team_id 服务端强制 / 枚举校验。"""

    def test_create_config_applies_defaults(self, client):
        """最小 payload → schema 默认值 (platform_type=generic / protocol_type=http_push /
        report_strategy=scheduled / report_interval=60 / heartbeat=1 / status=active)"""
        r = client.post("/api/v1/operate/supervision/configs", json=BASE_CONFIG)
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["platform_type"] == "generic"
        assert d["protocol_type"] == "http_push"
        assert d["report_strategy"] == "scheduled"
        assert d["report_interval_seconds"] == 60
        assert d["heartbeat_enabled"] == 1
        assert d["status"] == "active"
        # 未传可选字段 → null
        assert d["auth_config"] is None
        assert d["station_endpoints"] is None
        assert d["city_code"] is None

    def test_create_config_admin_team_id_zero(self, client):
        """admin (team_id=None) 创建配置 → team_id 服务端补 0 (平台默认模板)。"""
        r = client.post("/api/v1/operate/supervision/configs", json=BASE_CONFIG)
        assert r.status_code == 200
        assert r.json()["data"]["team_id"] == 0

    def test_create_config_auth_config_roundtrip(self, client):
        """auth_config dict → 入库 JSON 字符串 → 响应还原 dict。"""
        payload = {**BASE_CONFIG, "auth_config": {"token": "abc", "refresh": "def"}}
        r = client.post("/api/v1/operate/supervision/configs", json=payload)
        assert r.status_code == 200
        assert r.json()["data"]["auth_config"] == {"token": "abc", "refresh": "def"}

    def test_create_config_station_endpoints_roundtrip(self, client):
        """station_endpoints 嵌套结构序列化往返。"""
        endpoints = {"station": "/api/station", "device": "/api/device", "order": "/api/order"}
        r = client.post("/api/v1/operate/supervision/configs",
                        json={**BASE_CONFIG, "station_endpoints": endpoints})
        assert r.status_code == 200
        assert r.json()["data"]["station_endpoints"] == endpoints

    def test_create_config_explicit_null_auth_config(self, client):
        """显式传 auth_config=null → 响应 null (非字符串 'null')。"""
        r = client.post("/api/v1/operate/supervision/configs",
                        json={**BASE_CONFIG, "auth_config": None})
        assert r.status_code == 200
        assert r.json()["data"]["auth_config"] is None

    @pytest.mark.parametrize("field", ["report_strategy", "status", "platform_type", "protocol_type"])
    def test_create_invalid_enum_rejected_400(self, client, field):
        """create 对四个枚举字段做服务端校验, 非法值 → 400 (非 422, schema 为 plain str)。"""
        r = client.post("/api/v1/operate/supervision/configs",
                        json={**BASE_CONFIG, field: "__bogus__"})
        assert r.status_code == 422, f"{field} 非法值应 422, 实际 {r.status_code}: {r.text}"

    @pytest.mark.parametrize("pt", ["yueyichong", "lianlian", "zhelichong", "generic", "other"])
    def test_create_valid_platform_types(self, client, pt):
        r = client.post("/api/v1/operate/supervision/configs",
                        json={**BASE_CONFIG, "platform_type": pt})
        assert r.status_code == 200
        assert r.json()["data"]["platform_type"] == pt

    @pytest.mark.parametrize("proto", ["http_push", "http_pull", "mqtt", "websocket"])
    def test_create_valid_protocol_types(self, client, proto):
        r = client.post("/api/v1/operate/supervision/configs",
                        json={**BASE_CONFIG, "protocol_type": proto})
        assert r.status_code == 200
        assert r.json()["data"]["protocol_type"] == proto

    @pytest.mark.parametrize("missing_field", ["city", "platform_url"])
    def test_create_missing_required_field_422(self, client, missing_field):
        """必填字段缺失 → pydantic 422。"""
        payload = {k: v for k, v in BASE_CONFIG.items() if k != missing_field}
        r = client.post("/api/v1/operate/supervision/configs", json=payload)
        assert r.status_code == 422


# ==================== 配置: 读 / 更新 / 删除 / 序列化 ====================

class TestSupervisionConfigReadWrite:
    """配置详情 / 列表 / 更新 / 删除 + 时间戳 isoformat 序列化。"""

    def test_get_config_detail_isoformat_timestamps(self, client):
        """created_at / updated_at 序列化为 isoformat 字符串。"""
        c = _seed_config(client._sesh)
        r = client.get(f"/api/v1/operate/supervision/configs/{c.id}")
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["id"] == c.id
        assert isinstance(d["created_at"], str)
        assert isinstance(d["updated_at"], str)
        # isoformat 可被 fromisoformat 还原 (往返无损)
        assert datetime.fromisoformat(d["created_at"]) == c.created_at

    def test_get_config_not_found_404(self, client):
        r = client.get("/api/v1/operate/supervision/configs/999999")
        assert r.status_code == 404
        assert "不存在" in r.json()["detail"]

    def test_list_configs_empty(self, client):
        """空库 → 200, items=[], total=0。"""
        r = client.get("/api/v1/operate/supervision/configs")
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["items"] == []
        assert d["total"] == 0

    def test_list_configs_pagination(self, client):
        for i in range(3):
            _seed_config(client._sesh, city=f"市{i}")
        r = client.get("/api/v1/operate/supervision/configs?page=1&page_size=2")
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["total"] == 3
        assert len(d["items"]) == 2
        assert d["page"] == 1
        assert d["page_size"] == 2

    def test_list_configs_page_beyond_range_empty(self, client):
        """页码越界 → 200 空列表 (非 404)。"""
        _seed_config(client._sesh)
        r = client.get("/api/v1/operate/supervision/configs?page=99")
        assert r.status_code == 200
        assert r.json()["data"]["items"] == []

    @pytest.mark.parametrize("page,page_size", [(0, 20), (1, 0), (1, 101), (1, 200)])
    def test_list_configs_invalid_pagination_422(self, client, page, page_size):
        """page<1 / page_size<1 / page_size>100 → 422。"""
        r = client.get(f"/api/v1/operate/supervision/configs?page={page}&page_size={page_size}")
        assert r.status_code == 422

    def test_list_configs_filter_by_city(self, client):
        _seed_config(client._sesh, city="广州市")
        _seed_config(client._sesh, city="深圳市")
        r = client.get("/api/v1/operate/supervision/configs?city=广州市")
        assert r.status_code == 200
        cities = {i["city"] for i in r.json()["data"]["items"]}
        assert cities == {"广州市"}

    def test_list_configs_filter_by_status(self, client):
        _seed_config(client._sesh, status="active", city="A")
        _seed_config(client._sesh, status="inactive", city="B")
        r = client.get("/api/v1/operate/supervision/configs?status=inactive")
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["status"] == "inactive"

    def test_list_configs_ordered_by_id_desc(self, client):
        """列表按 id 倒序 (最新优先)。"""
        c1 = _seed_config(client._sesh, city="旧")
        c2 = _seed_config(client._sesh, city="新")
        r = client.get("/api/v1/operate/supervision/configs")
        ids = [i["id"] for i in r.json()["data"]["items"]]
        assert ids == [c2.id, c1.id]

    def test_update_config_partial_keeps_others(self, client):
        """model_dump(exclude_unset=True) 仅改传入字段, 其余保持。"""
        c = _seed_config(client._sesh, city="原名", platform_url="https://old")
        r = client.put(f"/api/v1/operate/supervision/configs/{c.id}", json={"city": "新名"})
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["city"] == "新名"
        assert d["platform_url"] == "https://old"  # 未传 → 保持

    def test_update_config_auth_config_reserialized(self, client):
        """更新 auth_config → 重新 _dump 序列化, 响应还原 dict。"""
        c = _seed_config(client._sesh)
        r = client.put(f"/api/v1/operate/supervision/configs/{c.id}",
                       json={"auth_config": {"token": "new"}})
        assert r.status_code == 200
        assert r.json()["data"]["auth_config"] == {"token": "new"}

    def test_update_config_empty_body_noop(self, client):
        """空 body → 200, 字段全部保持。"""
        c = _seed_config(client._sesh, city="保持")
        r = client.put(f"/api/v1/operate/supervision/configs/{c.id}", json={})
        assert r.status_code == 200
        assert r.json()["data"]["city"] == "保持"

    def test_update_config_invalid_report_strategy_400(self, client):
        c = _seed_config(client._sesh)
        r = client.put(f"/api/v1/operate/supervision/configs/{c.id}",
                       json={"report_strategy": "__bad__"})
        assert r.status_code == 422  # Literal 前置 (卡 6031add1)

    def test_update_config_invalid_status_400(self, client):
        c = _seed_config(client._sesh)
        r = client.put(f"/api/v1/operate/supervision/configs/{c.id}",
                       json={"status": "__bad__"})
        assert r.status_code == 422  # Literal 前置 (卡 6031add1)

    def test_update_config_not_found_404(self, client):
        r = client.put("/api/v1/operate/supervision/configs/999999", json={"city": "x"})
        assert r.status_code == 404

    def test_delete_config(self, client):
        c = _seed_config(client._sesh)
        r = client.delete(f"/api/v1/operate/supervision/configs/{c.id}")
        assert r.status_code == 200
        assert r.json()["data"]["id"] == c.id
        # 删除后查不到
        assert client.get(f"/api/v1/operate/supervision/configs/{c.id}").status_code == 404

    def test_delete_config_not_found_404(self, client):
        assert client.delete("/api/v1/operate/supervision/configs/999999").status_code == 404


# ==================== 上报记录: 手动触发 + 状态流转 (retry) ====================

class TestSupervisionReportLifecycle:
    """手动上报构造 + retry 状态流转矩阵。"""

    def test_manual_report_creates_success(self, client):
        """手动触发 → 落库一条 status=success / retry_count=0 的记录。"""
        c = _seed_config(client._sesh)
        r = client.post("/api/v1/operate/supervision/reports/manual",
                        json={"config_id": c.id, "report_type": "heartbeat"})
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["config_id"] == c.id
        assert d["status"] == "success"
        assert d["retry_count"] == 0
        assert d["report_type"] == "heartbeat"
        # 城市从配置冗余带入
        assert d["city"] == c.city
        # reported_at 已置 (isoformat)
        assert d["reported_at"] is not None

    def test_manual_report_content_roundtrip(self, client):
        """report_content dict → JSON → 还原 dict。"""
        c = _seed_config(client._sesh)
        content = {"station": "S1", "devices": 12, "power_kw": 88.5}
        r = client.post("/api/v1/operate/supervision/reports/manual",
                        json={"config_id": c.id, "report_type": "station",
                              "report_content": content})
        assert r.status_code == 200
        assert r.json()["data"]["report_content"] == content

    def test_manual_report_default_report_type_heartbeat(self, client):
        c = _seed_config(client._sesh)
        r = client.post("/api/v1/operate/supervision/reports/manual", json={"config_id": c.id})
        assert r.status_code == 200
        assert r.json()["data"]["report_type"] == "heartbeat"

    @pytest.mark.parametrize("rt", ["station", "device", "order", "heartbeat"])
    def test_manual_report_valid_types(self, client, rt):
        c = _seed_config(client._sesh)
        r = client.post("/api/v1/operate/supervision/reports/manual",
                        json={"config_id": c.id, "report_type": rt})
        assert r.status_code == 200
        assert r.json()["data"]["report_type"] == rt

    def test_manual_report_invalid_type_400(self, client):
        c = _seed_config(client._sesh)
        r = client.post("/api/v1/operate/supervision/reports/manual",
                        json={"config_id": c.id, "report_type": "__bad__"})
        assert r.status_code == 422  # Literal 前置 (卡 6031add1)

    def test_manual_report_config_not_found_404(self, client):
        r = client.post("/api/v1/operate/supervision/reports/manual",
                        json={"config_id": 999999, "report_type": "heartbeat"})
        assert r.status_code == 404

    def test_get_report_detail(self, client):
        c = _seed_config(client._sesh)
        rep = _seed_report(client._sesh, config_id=c.id, status="failed",
                           error_message="timeout")
        r = client.get(f"/api/v1/operate/supervision/reports/{rep.id}")
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["status"] == "failed"
        assert d["error_message"] == "timeout"

    def test_get_report_not_found_404(self, client):
        assert client.get("/api/v1/operate/supervision/reports/999999").status_code == 404

    def test_retry_failed_to_success(self, client):
        """failed → retry → success, retry_count+1, error_message 清空。"""
        c = _seed_config(client._sesh)
        rep = _seed_report(client._sesh, config_id=c.id, status="failed",
                           retry_count=2, error_message="网络超时")
        r = client.post(f"/api/v1/operate/supervision/reports/{rep.id}/retry")
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["status"] == "success"
        assert d["retry_count"] == 3
        assert d["error_message"] is None

    def test_retry_pending_to_success(self, client):
        """pending (在途) → retry → success (端点仅拦 success, pending 可重试)。"""
        c = _seed_config(client._sesh)
        rep = _seed_report(client._sesh, config_id=c.id, status="pending", retry_count=0)
        r = client.post(f"/api/v1/operate/supervision/reports/{rep.id}/retry")
        assert r.status_code == 200
        assert r.json()["data"]["status"] == "success"
        assert r.json()["data"]["retry_count"] == 1

    def test_retry_already_success_400(self, client):
        """已 success 的上报无需重试 → 400。"""
        c = _seed_config(client._sesh)
        rep = _seed_report(client._sesh, config_id=c.id, status="success")
        r = client.post(f"/api/v1/operate/supervision/reports/{rep.id}/retry")
        assert r.status_code == 400
        assert "无需重试" in r.json()["detail"]

    def test_retry_not_found_404(self, client):
        r = client.post("/api/v1/operate/supervision/reports/999999/retry")
        assert r.status_code == 404

    def test_retry_persists_state(self, client):
        """retry 落库后再读详情, 状态/retry_count 已持久化。"""
        c = _seed_config(client._sesh)
        rep = _seed_report(client._sesh, config_id=c.id, status="failed", retry_count=1)
        client.post(f"/api/v1/operate/supervision/reports/{rep.id}/retry")
        d = client.get(f"/api/v1/operate/supervision/reports/{rep.id}").json()["data"]
        assert d["status"] == "success"
        assert d["retry_count"] == 2


class TestSupervisionReportFiltering:
    """上报记录列表过滤 + 分页 + 空数据。"""

    def test_list_reports_empty(self, client):
        r = client.get("/api/v1/operate/supervision/reports")
        assert r.status_code == 200
        assert r.json()["data"]["items"] == []

    def test_list_reports_filter_by_status(self, client):
        c = _seed_config(client._sesh)
        _seed_report(client._sesh, config_id=c.id, status="success")
        _seed_report(client._sesh, config_id=c.id, status="failed", error_message="e")
        r = client.get("/api/v1/operate/supervision/reports?status=failed")
        items = r.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["status"] == "failed"

    def test_list_reports_filter_by_report_type(self, client):
        c = _seed_config(client._sesh)
        _seed_report(client._sesh, config_id=c.id, report_type="order")
        _seed_report(client._sesh, config_id=c.id, report_type="heartbeat")
        r = client.get("/api/v1/operate/supervision/reports?report_type=order")
        items = r.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["report_type"] == "order"

    def test_list_reports_filter_by_config_id(self, client):
        c1 = _seed_config(client._sesh, city="A")
        c2 = _seed_config(client._sesh, city="B")
        _seed_report(client._sesh, config_id=c1.id)
        _seed_report(client._sesh, config_id=c2.id)
        r = client.get(f"/api/v1/operate/supervision/reports?config_id={c2.id}")
        items = r.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["config_id"] == c2.id

    def test_list_reports_filter_by_city(self, client):
        c = _seed_config(client._sesh, city="珠海市")
        _seed_report(client._sesh, config_id=c.id, city="珠海市")
        _seed_report(client._sesh, config_id=c.id, city="汕头市")
        r = client.get("/api/v1/operate/supervision/reports?city=珠海市")
        items = r.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["city"] == "珠海市"

    def test_list_reports_pagination(self, client):
        c = _seed_config(client._sesh)
        for _ in range(3):
            _seed_report(client._sesh, config_id=c.id)
        r = client.get("/api/v1/operate/supervision/reports?page=1&page_size=2")
        d = r.json()["data"]
        assert d["total"] == 3
        assert len(d["items"]) == 2


# ==================== 合规检查 ====================

class TestSupervisionCompliance:
    """合规检查: 触发构造 / 校验 / score Decimal / details 往返 / 查询。"""

    def test_run_compliance_creates_check(self, client):
        c = _seed_config(client._sesh)
        r = client.post("/api/v1/operate/supervision/compliance",
                        json={"config_id": c.id, "check_type": "data_integrity",
                              "result": "pass", "score": "95.50"})
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["config_id"] == c.id
        assert d["check_type"] == "data_integrity"
        assert d["result"] == "pass"
        assert d["score"] == 95.5
        assert d["city"] == c.city
        assert d["checked_at"] is not None

    def test_run_compliance_defaults(self, client):
        """最小 payload → check_type=data_integrity / result=pass / score=0.00。"""
        c = _seed_config(client._sesh)
        r = client.post("/api/v1/operate/supervision/compliance", json={"config_id": c.id})
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["check_type"] == "data_integrity"
        assert d["result"] == "pass"
        assert d["score"] == 0

    def test_run_compliance_details_roundtrip(self, client):
        c = _seed_config(client._sesh)
        details = {"missing": ["station_count"], "coverage": 0.92}
        r = client.post("/api/v1/operate/supervision/compliance",
                        json={"config_id": c.id, "details": details})
        assert r.status_code == 200
        assert r.json()["data"]["details"] == details

    def test_run_compliance_invalid_check_type_400(self, client):
        c = _seed_config(client._sesh)
        r = client.post("/api/v1/operate/supervision/compliance",
                        json={"config_id": c.id, "check_type": "__bad__"})
        assert r.status_code == 422  # Literal 前置 (卡 6031add1)

    def test_run_compliance_invalid_result_400(self, client):
        c = _seed_config(client._sesh)
        r = client.post("/api/v1/operate/supervision/compliance",
                        json={"config_id": c.id, "result": "__bad__"})
        assert r.status_code == 422  # Literal 前置 (卡 6031add1)

    @pytest.mark.parametrize("ct", ["data_integrity", "report_delay", "compliance"])
    def test_run_compliance_valid_check_types(self, client, ct):
        c = _seed_config(client._sesh)
        r = client.post("/api/v1/operate/supervision/compliance",
                        json={"config_id": c.id, "check_type": ct})
        assert r.status_code == 200
        assert r.json()["data"]["check_type"] == ct

    @pytest.mark.parametrize("res", ["pass", "warn", "fail"])
    def test_run_compliance_valid_results(self, client, res):
        c = _seed_config(client._sesh)
        r = client.post("/api/v1/operate/supervision/compliance",
                        json={"config_id": c.id, "result": res})
        assert r.status_code == 200
        assert r.json()["data"]["result"] == res

    def test_run_compliance_config_not_found_404(self, client):
        r = client.post("/api/v1/operate/supervision/compliance",
                        json={"config_id": 999999})
        assert r.status_code == 404

    def test_run_compliance_score_boundary_100(self, client):
        """合规得分上界 100.00 → 200, Numeric(5,2) 可容纳。"""
        c = _seed_config(client._sesh)
        r = client.post("/api/v1/operate/supervision/compliance",
                        json={"config_id": c.id, "score": "100.00"})
        assert r.status_code == 200
        assert r.json()["data"]["score"] == 100.0

    def test_get_compliance_detail(self, client):
        c = _seed_config(client._sesh)
        cc = _seed_check(client._sesh, config_id=c.id, result="warn", score=Decimal("60.50"))
        r = client.get(f"/api/v1/operate/supervision/compliance/{cc.id}")
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["result"] == "warn"
        assert d["score"] == 60.5

    def test_get_compliance_not_found_404(self, client):
        assert client.get("/api/v1/operate/supervision/compliance/999999").status_code == 404

    def test_list_compliance_filter_by_result(self, client):
        c = _seed_config(client._sesh)
        _seed_check(client._sesh, config_id=c.id, result="pass")
        _seed_check(client._sesh, config_id=c.id, result="fail")
        r = client.get("/api/v1/operate/supervision/compliance?result=fail")
        items = r.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["result"] == "fail"

    def test_list_compliance_filter_by_check_type(self, client):
        c = _seed_config(client._sesh)
        _seed_check(client._sesh, config_id=c.id, check_type="report_delay")
        _seed_check(client._sesh, config_id=c.id, check_type="compliance")
        r = client.get("/api/v1/operate/supervision/compliance?check_type=compliance")
        items = r.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["check_type"] == "compliance"

    def test_list_compliance_empty(self, client):
        r = client.get("/api/v1/operate/supervision/compliance")
        assert r.status_code == 200
        assert r.json()["data"]["items"] == []


# ==================== 鉴权: router 级 operate:manage ====================

class TestSupervisionPermissionGate:
    """router 级 require_permission('operate:manage') 覆盖全部端点 (含 GET);
    viewer 无该权限 → 403。engineer 持有 → 通过 (team scoping 见下)。"""

    @pytest.fixture
    def viewer_token(self, client):
        _add_user(client._sesh, "sup_viewer", UserRole.VIEWER)
        return _login_token(client, "sup_viewer")

    def test_viewer_list_configs_forbidden(self, client, viewer_token):
        r = client.get("/api/v1/operate/supervision/configs", headers=_auth(viewer_token))
        assert r.status_code == 403

    def test_viewer_create_config_forbidden(self, client, viewer_token):
        r = client.post("/api/v1/operate/supervision/configs",
                        json=BASE_CONFIG, headers=_auth(viewer_token))
        assert r.status_code == 403

    def test_viewer_get_config_forbidden(self, client, viewer_token):
        c = _seed_config(client._sesh)
        r = client.get(f"/api/v1/operate/supervision/configs/{c.id}",
                       headers=_auth(viewer_token))
        assert r.status_code == 403

    def test_viewer_list_reports_forbidden(self, client, viewer_token):
        r = client.get("/api/v1/operate/supervision/reports", headers=_auth(viewer_token))
        assert r.status_code == 403

    def test_viewer_manual_report_forbidden(self, client, viewer_token):
        c = _seed_config(client._sesh)
        r = client.post("/api/v1/operate/supervision/reports/manual",
                        json={"config_id": c.id}, headers=_auth(viewer_token))
        assert r.status_code == 403

    def test_viewer_run_compliance_forbidden(self, client, viewer_token):
        c = _seed_config(client._sesh)
        r = client.post("/api/v1/operate/supervision/compliance",
                        json={"config_id": c.id}, headers=_auth(viewer_token))
        assert r.status_code == 403

    def test_anonymous_unauthorized(self, anon_client):
        """无 token → 全局 enforce_auth 拦 401。"""
        r = anon_client.get("/api/v1/operate/supervision/configs")
        assert r.status_code == 401


# ==================== team scoping 矩阵 ====================

class TestSupervisionTeamScoping:
    """team_id 服务端隔离矩阵 (任务卡 708350b3):

      ① 同 team 放行
      ② 跨 team → 404 (不泄露资源存在)
      ③ admin 平台级豁免 (跨 team 仍可见)
      ④ 列表经 team_scope 过滤, 跨 team 记录不出现
      ⑤ 跨 team 与不存在均 404 (status_code 不可区分)
    """

    @pytest.fixture
    def two_teams(self, client):
        s = client._sesh
        ta = Team(name="监管团队A", code="SUPTA")
        tb = Team(name="监管团队B", code="SUPTB")
        s.add_all([ta, tb])
        s.commit()
        s.refresh(ta)
        s.refresh(tb)

        _add_user(s, "sup_eng_a", UserRole.ENGINEER, team_id=ta.id)
        _add_user(s, "sup_eng_b", UserRole.ENGINEER, team_id=tb.id)
        return {
            "ta": ta, "tb": tb,
            "eng_a_token": _login_token(client, "sup_eng_a"),
            "eng_b_token": _login_token(client, "sup_eng_b"),
        }

    # ── 列表隔离 (team_scope) ──

    def test_list_configs_team_user_sees_only_own_team(self, client, two_teams):
        _seed_config(client._sesh, team_id=two_teams["ta"].id, city="A市")
        _seed_config(client._sesh, team_id=two_teams["tb"].id, city="B市")
        r = client.get("/api/v1/operate/supervision/configs",
                       headers=_auth(two_teams["eng_a_token"]))
        assert r.status_code == 200
        cities = {i["city"] for i in r.json()["data"]["items"]}
        assert cities == {"A市"}  # 仅本 team

    def test_list_configs_admin_sees_all_teams(self, client, two_teams):
        _seed_config(client._sesh, team_id=two_teams["ta"].id, city="A市")
        _seed_config(client._sesh, team_id=two_teams["tb"].id, city="B市")
        r = client.get("/api/v1/operate/supervision/configs")  # admin 默认头
        assert r.status_code == 200
        cities = {i["city"] for i in r.json()["data"]["items"]}
        assert {"A市", "B市"} <= cities

    def test_list_reports_team_scoping(self, client, two_teams):
        c = _seed_config(client._sesh)
        _seed_report(client._sesh, team_id=two_teams["ta"].id, config_id=c.id, city="A")
        _seed_report(client._sesh, team_id=two_teams["tb"].id, config_id=c.id, city="B")
        r = client.get("/api/v1/operate/supervision/reports",
                       headers=_auth(two_teams["eng_a_token"]))
        cities = {i["city"] for i in r.json()["data"]["items"]}
        assert cities == {"A"}

    def test_list_compliance_team_scoping(self, client, two_teams):
        c = _seed_config(client._sesh)
        _seed_check(client._sesh, team_id=two_teams["ta"].id, config_id=c.id, city="A")
        _seed_check(client._sesh, team_id=two_teams["tb"].id, config_id=c.id, city="B")
        r = client.get("/api/v1/operate/supervision/compliance",
                       headers=_auth(two_teams["eng_a_token"]))
        cities = {i["city"] for i in r.json()["data"]["items"]}
        assert cities == {"A"}

    # ── 单资源 assert_team_access ──

    def test_get_config_same_team_ok(self, client, two_teams):
        c = _seed_config(client._sesh, team_id=two_teams["ta"].id)
        r = client.get(f"/api/v1/operate/supervision/configs/{c.id}",
                       headers=_auth(two_teams["eng_a_token"]))
        assert r.status_code == 200

    def test_get_config_cross_team_404(self, client, two_teams):
        c = _seed_config(client._sesh, team_id=two_teams["tb"].id)
        r = client.get(f"/api/v1/operate/supervision/configs/{c.id}",
                       headers=_auth(two_teams["eng_a_token"]))
        assert r.status_code == 404

    def test_get_config_admin_exempt_cross_team(self, client, two_teams):
        c = _seed_config(client._sesh, team_id=two_teams["tb"].id)
        r = client.get(f"/api/v1/operate/supervision/configs/{c.id}")  # admin
        assert r.status_code == 200

    def test_get_config_cross_team_and_not_found_both_404(self, client, two_teams):
        """跨 team 与不存在均 404 (status_code 不可区分 —— 安全语义)。

        注: 二者 detail 文案不同 (跨 team='资源不存在' / 不存在='监管平台配置不存在'),
        属轻度存在性信息泄露, 见已知缺陷清单 BUG-1。此处仅断言 status_code 一致。
        """
        c = _seed_config(client._sesh, team_id=two_teams["tb"].id)
        cross = client.get(f"/api/v1/operate/supervision/configs/{c.id}",
                           headers=_auth(two_teams["eng_a_token"]))
        missing = client.get("/api/v1/operate/supervision/configs/999999",
                             headers=_auth(two_teams["eng_a_token"]))
        assert cross.status_code == 404
        assert missing.status_code == 404

    def test_update_config_cross_team_404(self, client, two_teams):
        c = _seed_config(client._sesh, team_id=two_teams["tb"].id)
        r = client.put(f"/api/v1/operate/supervision/configs/{c.id}", json={"city": "x"},
                       headers=_auth(two_teams["eng_a_token"]))
        assert r.status_code == 404

    def test_delete_config_cross_team_404(self, client, two_teams):
        c = _seed_config(client._sesh, team_id=two_teams["tb"].id)
        r = client.delete(f"/api/v1/operate/supervision/configs/{c.id}",
                          headers=_auth(two_teams["eng_a_token"]))
        assert r.status_code == 404

    def test_manual_report_cross_team_config_404(self, client, two_teams):
        """手动上报引用他 team 配置 → assert_team_access 拦 404。"""
        c = _seed_config(client._sesh, team_id=two_teams["tb"].id)
        r = client.post("/api/v1/operate/supervision/reports/manual",
                        json={"config_id": c.id},
                        headers=_auth(two_teams["eng_a_token"]))
        assert r.status_code == 404

    def test_manual_report_same_team_assigns_user_team(self, client, two_teams):
        """team 级用户手动上报 → 新记录 team_id = 用户 team_id (服务端强制)。"""
        c = _seed_config(client._sesh, team_id=two_teams["ta"].id)
        r = client.post("/api/v1/operate/supervision/reports/manual",
                        json={"config_id": c.id},
                        headers=_auth(two_teams["eng_a_token"]))
        assert r.status_code == 200
        assert r.json()["data"]["team_id"] == two_teams["ta"].id

    def test_run_compliance_cross_team_config_404(self, client, two_teams):
        c = _seed_config(client._sesh, team_id=two_teams["tb"].id)
        r = client.post("/api/v1/operate/supervision/compliance",
                        json={"config_id": c.id},
                        headers=_auth(two_teams["eng_a_token"]))
        assert r.status_code == 404

    def test_get_report_cross_team_404(self, client, two_teams):
        c = _seed_config(client._sesh)
        rep = _seed_report(client._sesh, team_id=two_teams["tb"].id, config_id=c.id)
        r = client.get(f"/api/v1/operate/supervision/reports/{rep.id}",
                       headers=_auth(two_teams["eng_a_token"]))
        assert r.status_code == 404

    def test_retry_report_cross_team_404(self, client, two_teams):
        c = _seed_config(client._sesh)
        rep = _seed_report(client._sesh, team_id=two_teams["tb"].id, config_id=c.id,
                           status="failed")
        r = client.post(f"/api/v1/operate/supervision/reports/{rep.id}/retry",
                        headers=_auth(two_teams["eng_a_token"]))
        assert r.status_code == 404

    def test_get_compliance_cross_team_404(self, client, two_teams):
        c = _seed_config(client._sesh)
        cc = _seed_check(client._sesh, team_id=two_teams["tb"].id, config_id=c.id)
        r = client.get(f"/api/v1/operate/supervision/compliance/{cc.id}",
                       headers=_auth(two_teams["eng_a_token"]))
        assert r.status_code == 404

    def test_team_user_cannot_hijack_via_report_content(self, client, two_teams):
        """team 级用户即便持合法 token, 也无法为他 team 配置创建上报 (config 守卫先行)。"""
        c = _seed_config(client._sesh, team_id=two_teams["tb"].id)
        r = client.post("/api/v1/operate/supervision/reports/manual",
                        json={"config_id": c.id, "report_content": {"inject": True}},
                        headers=_auth(two_teams["eng_a_token"]))
        assert r.status_code == 404


# ============================================================================
# 已知缺陷清单 (只记录, 不修改业务源码)
# ----------------------------------------------------------------------------
# BUG-1 (轻度信息泄露): get/update/delete config + manual_report + run_compliance
#   采用两步校验 —— _get_config (404 "监管平台配置不存在") → assert_team_access
#   (404 "资源不存在")。跨 team 与资源不存在虽同为 404, 但 detail 文案不同,
#   攻击者可据此区分 "配置存在但属他 team" vs "配置不存在", 泄露他 team 是否
#   注册了某城市/平台监管对接。建议: 单资源校验对齐 assert_station_team_access
#   的单查询模式, 统一 detail (见 test_get_config_cross_team_and_not_found_both_404)。
#
# BUG-2 (校验缺口): update_config 仅校验 report_strategy / status 两个枚举,
#   create_config 校验的 platform_type / protocol_type 在更新路径未校验 ——
#   可经 PUT 写入非法枚举值 (如 platform_type='__bogus__')。建议 update 补齐。
#
# BUG-3 (校验缺口): ComplianceRunRequest.score 无 0-100 范围与 Numeric(5,2)
#   精度约束 (列上限 999.99)。score>999.99 在 PG 生产会 numeric field overflow
#   (500); score<0 / score>100 违反 "0-100" 业务语义被静默存入。
#   建议补 Field(ge=0, le=100, max_digits=5, decimal_places=2) (对齐 ops_invoice
#   卡 406b7e13f 的金额校验模式)。
#
# BUG-4 (功能缺口): list_configs / list_reports / list_compliance 均无时间窗口
#   过滤 (created_at / reported_at / checked_at 未暴露为 query 参数), 监管审计
#   场景无法按上报时间范围检索; 排序按 id 而非时间。建议补 start/end 日期过滤。
# ============================================================================
