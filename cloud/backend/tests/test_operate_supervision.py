"""
运营平台 - 市政监管对接 后端测试 (迁移自 admin, SPEC §2.5)

覆盖:
- 监管平台配置 CRUD + 取值校验 (按运营团队隔离)
- 上报记录: 手动触发 / 列表筛选 / 重试
- 合规检查: 触发 / 列表筛选 / 详情
- 团队隔离: A团队看不到B团队配置；伪造 X-Team-Id 不得越权 (任务卡 708350b3)
"""
import bcrypt
import pytest
from decimal import Decimal


# ─── 越权测试脚手架 ───

@pytest.fixture
def team_pair(client):
    """两团队 + 两团队级用户(operator, 具 operate:manage) + token，用于 team_id 越权测试。"""
    from app.models.user import User, UserRole, Team
    s = client._sesh
    ta = Team(name="监管团队A", code="SUPTA")
    tb = Team(name="监管团队B", code="SUPTB")
    s.add_all([ta, tb])
    s.commit()
    s.refresh(ta)
    s.refresh(tb)

    pwd = "sup123456"
    ua = User(
        username="sup_eng_a", real_name="A工程师", role=UserRole.OPERATOR,
        team_id=ta.id, status="active",
        password_hash=bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode(),
    )
    ub = User(
        username="sup_eng_b", real_name="B工程师", role=UserRole.OPERATOR,
        team_id=tb.id, status="active",
        password_hash=bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode(),
    )
    s.add_all([ua, ub])
    s.commit()

    def _tok(username):
        r = client.post("/api/v1/auth/login", data={"username": username, "password": pwd})
        assert r.status_code == 200, f"登录失败 {username}: {r.text}"
        return r.json()["data"]["token"]

    return {
        "teams": {"a": ta, "b": tb},
        "tokens": {"a": _tok("sup_eng_a"), "b": _tok("sup_eng_b")},
    }


def _h(token):
    return {"Authorization": f"Bearer {token}"}


class TestOpsSupervisionConfig:
    """运营平台 - 市政监管平台配置"""

    def test_create_config(self, client):
        resp = client.post("/api/v1/operate/supervision/configs", json={
            "city": "深圳市",
            "platform_url": "https://supervision.sz.gov.cn/api",
            "auth_config": {"app_id": "SZ001", "app_secret": "SEC"},
            "report_strategy": "realtime",
            "report_interval_seconds": 30,
            "station_endpoints": {"station": "/station", "order": "/order"},
            "heartbeat_enabled": 1,
            "status": "active",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["city"] == "深圳市"
        assert data["team_id"] == 0
        assert data["report_strategy"] == "realtime"
        assert data["auth_config"]["app_id"] == "SZ001"
        assert data["station_endpoints"]["order"] == "/order"

    def test_create_config_with_platform_fields(self, client):
        resp = client.post("/api/v1/operate/supervision/configs", json={
            "city": "广州市",
            "city_code": "440100",
            "platform_name": "粤易充",
            "platform_type": "yueyichong",
            "protocol_type": "http_push",
            "platform_url": "https://guangzhou.yueyichong.com/api",
            "report_strategy": "scheduled",
            "status": "active",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["platform_name"] == "粤易充"
        assert data["platform_type"] == "yueyichong"
        assert data["protocol_type"] == "http_push"
        assert data["city_code"] == "440100"

    def test_invalid_report_strategy(self, client):
        resp = client.post("/api/v1/operate/supervision/configs", json={
            "city": "X", "platform_url": "https://x",
            "report_strategy": "unknown",
        })
        assert resp.status_code == 422  # Literal 前置 (卡 6031add1)

    def test_list_and_filter(self, client):
        client.post("/api/v1/operate/supervision/configs", json={
            "city": "北京市", "platform_url": "https://bj",
        })
        client.post("/api/v1/operate/supervision/configs", json={
            "city": "上海市", "platform_url": "https://sh", "status": "inactive",
        })

        resp = client.get("/api/v1/operate/supervision/configs")
        assert resp.json()["data"]["total"] >= 2

        resp = client.get("/api/v1/operate/supervision/configs?city=上海市")
        items = resp.json()["data"]["items"]
        assert len(items) == 1 and items[0]["city"] == "上海市"

        resp = client.get("/api/v1/operate/supervision/configs?status=inactive")
        assert resp.json()["data"]["total"] == 1

    def test_get_update_delete(self, client):
        r = client.post("/api/v1/operate/supervision/configs", json={
            "city": "广州市", "platform_url": "https://gz",
        })
        cid = r.json()["data"]["id"]

        assert client.get(f"/api/v1/operate/supervision/configs/{cid}").status_code == 200

        resp = client.put(f"/api/v1/operate/supervision/configs/{cid}", json={
            "report_strategy": "realtime", "report_interval_seconds": 15,
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["report_strategy"] == "realtime"
        assert data["report_interval_seconds"] == 15

        assert client.delete(f"/api/v1/operate/supervision/configs/{cid}").status_code == 200
        assert client.get(f"/api/v1/operate/supervision/configs/{cid}").status_code == 404

    def test_config_404(self, client):
        assert client.get("/api/v1/operate/supervision/configs/99999").status_code == 404


class TestOpsSupervisionTeamIsolation:
    """运营平台 - 市政监管团队隔离"""

    def test_team_isolation(self, client, team_pair):
        """团队级用户只看本 team 配置；伪造 X-Team-Id 不得越权。"""
        ta, tb = team_pair["teams"]["a"], team_pair["teams"]["b"]
        # A 用户创建（故意伪造 X-Team-Id=B，资源仍归属 A）
        r = client.post(
            "/api/v1/operate/supervision/configs",
            json={"city": "深圳市", "platform_url": "https://sz"},
            headers={**_h(team_pair["tokens"]["a"]), "X-Team-Id": str(tb.id)},
        )
        assert r.status_code == 200
        assert r.json()["data"]["team_id"] == ta.id  # 归属 A，伪造 header 被忽略
        # B 用户创建
        client.post(
            "/api/v1/operate/supervision/configs",
            json={"city": "北京市", "platform_url": "https://bj"},
            headers=_h(team_pair["tokens"]["b"]),
        )

        # A 故意带 X-Team-Id=B 查询，仍只看到本 team（深圳）
        resp = client.get(
            "/api/v1/operate/supervision/configs",
            headers={**_h(team_pair["tokens"]["a"]), "X-Team-Id": str(tb.id)},
        )
        items = resp.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["city"] == "深圳市"

        # B 只看到本 team（北京）
        resp = client.get(
            "/api/v1/operate/supervision/configs",
            headers=_h(team_pair["tokens"]["b"]),
        )
        items = resp.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["city"] == "北京市"

    def test_cross_team_get_returns_404(self, client, team_pair):
        """团队级用户读他队配置 → 404（不泄露存在）。"""
        r = client.post(
            "/api/v1/operate/supervision/configs",
            json={"city": "北京市", "platform_url": "https://bj"},
            headers=_h(team_pair["tokens"]["b"]),
        )
        cid = r.json()["data"]["id"]

        # A 读 B 的配置 → 404；伪造 X-Team-Id 也无效
        resp = client.get(
            f"/api/v1/operate/supervision/configs/{cid}",
            headers={**_h(team_pair["tokens"]["a"]), "X-Team-Id": str(team_pair['teams']['b'].id)},
        )
        assert resp.status_code == 404

    def test_admin_sees_all_teams(self, client, team_pair):
        """admin 平台级，跨团队可见全部。"""
        client.post(
            "/api/v1/operate/supervision/configs",
            json={"city": "深圳市", "platform_url": "https://sz"},
            headers=_h(team_pair["tokens"]["a"]),
        )
        client.post(
            "/api/v1/operate/supervision/configs",
            json={"city": "北京市", "platform_url": "https://bj"},
            headers=_h(team_pair["tokens"]["b"]),
        )
        # client 默认 admin token
        resp = client.get("/api/v1/operate/supervision/configs")
        cities = {it["city"] for it in resp.json()["data"]["items"]}
        assert {"深圳市", "北京市"}.issubset(cities)


class TestOpsRegulatoryReport:
    """运营平台 - 监管数据上报"""

    def _make_config(self, client, city="深圳市"):
        r = client.post("/api/v1/operate/supervision/configs", json={
            "city": city, "platform_url": "https://supervision",
        })
        return r.json()["data"]["id"], city

    def test_manual_report(self, client):
        cid, city = self._make_config(client)
        resp = client.post("/api/v1/operate/supervision/reports/manual", json={
            "config_id": cid, "report_type": "station",
            "report_content": {"station_id": "S1", "name": "测试站"},
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["report_type"] == "station"
        assert data["status"] == "success"
        assert data["city"] == city
        assert data["report_content"]["station_id"] == "S1"

    def test_manual_report_invalid_type(self, client):
        cid, _ = self._make_config(client)
        resp = client.post("/api/v1/operate/supervision/reports/manual", json={
            "config_id": cid, "report_type": "invalid",
        })
        assert resp.status_code == 422  # Literal 前置 (卡 6031add1)

    def test_manual_report_config_not_found(self, client):
        resp = client.post("/api/v1/operate/supervision/reports/manual", json={
            "config_id": 99999, "report_type": "heartbeat",
        })
        assert resp.status_code == 404

    def test_list_and_filter(self, client):
        cid, city = self._make_config(client, "北京市")
        client.post("/api/v1/operate/supervision/reports/manual", json={
            "config_id": cid, "report_type": "station",
        })
        client.post("/api/v1/operate/supervision/reports/manual", json={
            "config_id": cid, "report_type": "order",
        })

        resp = client.get("/api/v1/operate/supervision/reports?config_id=%d" % cid)
        assert resp.json()["data"]["total"] == 2

        resp = client.get("/api/v1/operate/supervision/reports?report_type=order")
        items = resp.json()["data"]["items"]
        assert all(i["report_type"] == "order" for i in items)

        resp = client.get("/api/v1/operate/supervision/reports?city=北京市")
        assert resp.json()["data"]["total"] == 2

    def test_retry_failed_report(self, client):
        cid, _ = self._make_config(client)
        r = client.post("/api/v1/operate/supervision/reports/manual", json={
            "config_id": cid, "report_type": "heartbeat",
        })
        rid = r.json()["data"]["id"]

        # 已成功的不允许重试
        resp = client.post(f"/api/v1/operate/supervision/reports/{rid}/retry")
        assert resp.status_code == 400

        # 详情
        assert client.get(f"/api/v1/operate/supervision/reports/{rid}").status_code == 200
        assert client.get("/api/v1/operate/supervision/reports/99999").status_code == 404

    def test_retry_success_via_db(self, client, db_session):
        """构造 failed 记录验证重试成功路径"""
        from app.models.admin_supervision import RegulatoryReport
        cid, _ = self._make_config(client)
        rec = RegulatoryReport(
            config_id=cid, city="深圳市", report_type="order",
            status="failed", retry_count=1, error_message="timeout",
        )
        db_session.add(rec)
        db_session.commit()
        db_session.refresh(rec)
        rid = rec.id

        resp = client.post(f"/api/v1/operate/supervision/reports/{rid}/retry")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "success"
        assert data["retry_count"] == 2
        assert data["error_message"] is None


class TestOpsComplianceCheck:
    """运营平台 - 合规检查"""

    def _make_config(self, client, city="深圳市"):
        r = client.post("/api/v1/operate/supervision/configs", json={
            "city": city, "platform_url": "https://supervision",
        })
        return r.json()["data"]["id"], city

    def test_run_compliance(self, client):
        cid, city = self._make_config(client)
        resp = client.post("/api/v1/operate/supervision/compliance", json={
            "config_id": cid, "check_type": "data_integrity",
            "result": "warn", "score": 85.5,
            "details": {"missing": 3, "total": 100},
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["check_type"] == "data_integrity"
        assert data["result"] == "warn"
        assert data["score"] == 85.5
        assert data["city"] == city
        assert data["details"]["missing"] == 3

    def test_run_invalid_check_type(self, client):
        cid, _ = self._make_config(client)
        resp = client.post("/api/v1/operate/supervision/compliance", json={
            "config_id": cid, "check_type": "unknown", "result": "pass",
        })
        assert resp.status_code == 422  # Literal 前置 (卡 6031add1)

    def test_run_config_not_found(self, client):
        resp = client.post("/api/v1/operate/supervision/compliance", json={
            "config_id": 99999, "check_type": "compliance", "result": "pass",
        })
        assert resp.status_code == 404

    def test_list_and_detail(self, client):
        cid, _ = self._make_config(client, "杭州市")
        client.post("/api/v1/operate/supervision/compliance", json={
            "config_id": cid, "check_type": "report_delay", "result": "fail", "score": 40,
        })
        client.post("/api/v1/operate/supervision/compliance", json={
            "config_id": cid, "check_type": "compliance", "result": "pass", "score": 98,
        })

        resp = client.get("/api/v1/operate/supervision/compliance?config_id=%d" % cid)
        assert resp.json()["data"]["total"] == 2

        resp = client.get("/api/v1/operate/supervision/compliance?result=fail")
        items = resp.json()["data"]["items"]
        assert all(i["result"] == "fail" for i in items)

        resp = client.get("/api/v1/operate/supervision/compliance?check_type=compliance")
        assert resp.json()["data"]["total"] == 1

        # 详情 + 404
        r = client.post("/api/v1/operate/supervision/compliance", json={
            "config_id": cid, "check_type": "data_integrity", "result": "pass",
        })
        ckid = r.json()["data"]["id"]
        assert client.get(f"/api/v1/operate/supervision/compliance/{ckid}").status_code == 200
        assert client.get("/api/v1/operate/supervision/compliance/99999").status_code == 404


# ─── 权限门 / 边界校验 / 异常保护 补全 (卡 76d1d4d1) ────────────────────────────
# 原 19 测试缺三类覆盖: (1) 整 router 挂 require_permission('operate:manage') 的
# 权限门契约; (2) report_interval_seconds / city 的边界校验; (3) 12 路由 handler
# 内部异常 → 500 不裸崩。下三组补全。

def _login(client, username, password):
    r = client.post("/api/v1/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, f"登录失败 {username}: {r.status_code} {r.text}"
    return r.json()["data"]["token"]


@pytest.fixture
def viewer_env(client, monkeypatch):
    """client + seed viewer(不持 operate:manage) + SessionLocal 指向测试库。

    require_permission 函数内 ``from app.core.database import SessionLocal`` 查 user,
    需 monkeypatch 指向测试库 (同源坑见 test_rbac_route_write_guard / conftest override)。
    """
    import bcrypt
    import app.core.database as db_module
    from app.models.user import User, UserRole
    from sqlalchemy.orm import sessionmaker

    s = client._sesh
    pwd = "view123"
    if not s.query(User).filter(User.username == "sup_viewer").first():
        s.add(User(
            username="sup_viewer",
            password_hash=bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode(),
            real_name="sup_viewer",
            role=UserRole.VIEWER,
            status="active",
        ))
    s.commit()
    monkeypatch.setattr(db_module, "SessionLocal", sessionmaker(bind=s.get_bind()))
    yield client


class TestOpsSupervisionPermissionGate:
    """权限门: 整个 router 挂 require_permission('operate:manage')。

    viewer 不持 operate:manage → 全端点 403; 匿名 (无 token) → 401。
    """

    # 代表性端点 (覆盖列表/详情 + 各 POST/PUT/DELETE)
    GATE_ENDPOINTS = [
        ("GET", "/api/v1/operate/supervision/configs", None),
        ("POST", "/api/v1/operate/supervision/configs",
         {"city": "测试市", "platform_url": "https://x"}),
        ("GET", "/api/v1/operate/supervision/configs/1", None),
        ("PUT", "/api/v1/operate/supervision/configs/1", {"report_strategy": "realtime"}),
        ("DELETE", "/api/v1/operate/supervision/configs/1", None),
        ("GET", "/api/v1/operate/supervision/reports", None),
        ("POST", "/api/v1/operate/supervision/reports/manual",
         {"config_id": 1, "report_type": "heartbeat"}),
        ("POST", "/api/v1/operate/supervision/reports/1/retry", None),
        ("GET", "/api/v1/operate/supervision/compliance", None),
        ("POST", "/api/v1/operate/supervision/compliance",
         {"config_id": 1, "check_type": "compliance", "result": "pass"}),
    ]

    def test_viewer_forbidden(self, viewer_env):
        """viewer 不持 operate:manage → 全端点 403 (router 级 dependency 收口)。"""
        token = _login(viewer_env, "sup_viewer", "view123")
        h = {"Authorization": f"Bearer {token}"}
        for method, path, body in self.GATE_ENDPOINTS:
            resp = viewer_env.request(method, path, json=body, headers=h)
            assert resp.status_code == 403, (
                f"viewer {method} {path} 应 403, 实际 {resp.status_code}\n{resp.text}"
            )

    def test_anon_denied(self, anon_client):
        """匿名 (无 token) → 401 (全局 enforce_auth)。"""
        cases = [
            ("GET", "/api/v1/operate/supervision/configs", None),
            ("POST", "/api/v1/operate/supervision/reports/manual",
             {"config_id": 1, "report_type": "heartbeat"}),
        ]
        for method, path, body in cases:
            resp = anon_client.request(method, path, json=body)
            assert resp.status_code == 401, (
                f"anon {method} {path} 应 401, 实际 {resp.status_code}"
            )


class TestOpsSupervisionBoundaryValidation:
    """边界校验 (卡 76d1d4d1): report_interval_seconds 范围 + city 空/超长。

    枚举类字段 (report_strategy/status/platform_type/protocol_type) 仍走 handler 内
    手动校验 → 400 (见 test_invalid_report_strategy); 数值/长度类走 Pydantic Field → 422。
    """

    def test_report_interval_zero_rejected(self, client):
        r = client.post("/api/v1/operate/supervision/configs", json={
            "city": "测试市", "platform_url": "https://x",
            "report_interval_seconds": 0,
        })
        assert r.status_code == 422

    def test_report_interval_negative_rejected(self, client):
        r = client.post("/api/v1/operate/supervision/configs", json={
            "city": "测试市", "platform_url": "https://x",
            "report_interval_seconds": -5,
        })
        assert r.status_code == 422

    def test_report_interval_too_large_rejected(self, client):
        r = client.post("/api/v1/operate/supervision/configs", json={
            "city": "测试市", "platform_url": "https://x",
            "report_interval_seconds": 100000,
        })
        assert r.status_code == 422

    def test_empty_city_rejected(self, client):
        r = client.post("/api/v1/operate/supervision/configs", json={
            "city": "", "platform_url": "https://x",
        })
        assert r.status_code == 422

    def test_oversize_city_rejected(self, client):
        r = client.post("/api/v1/operate/supervision/configs", json={
            "city": "市" * 101, "platform_url": "https://x",
        })
        assert r.status_code == 422

    def test_update_invalid_interval_rejected(self, client):
        cid = client.post("/api/v1/operate/supervision/configs", json={
            "city": "测试市", "platform_url": "https://x",
        }).json()["data"]["id"]
        r = client.put(f"/api/v1/operate/supervision/configs/{cid}", json={
            "report_interval_seconds": 0,
        })
        assert r.status_code == 422


def _boom(*args, **kwargs):
    raise RuntimeError("boom")


class TestOpsSupervisionExceptionSafety:
    """12 路由异常保护: handler 内部异常 → 500 (不裸崩)。

    monkeypatch 响应函数 (success_response/paginated_response) 抛 RuntimeError —— 每个
    handler 的最后一条语句都是返回这两个之一, 故该异常必落在 try 块内被兜底。
    """

    def test_all_handlers_return_500_on_internal_error(self, client, db_session, monkeypatch):
        import app.api.v1.operate.supervision as mod
        from app.models.admin_supervision import RegulatoryReport

        # 先 seed (admin token, 未 patch), 再 monkeypatch
        cid = client.post("/api/v1/operate/supervision/configs", json={
            "city": "异常市", "platform_url": "https://x",
        }).json()["data"]["id"]
        rid_s = client.post("/api/v1/operate/supervision/reports/manual", json={
            "config_id": cid, "report_type": "heartbeat",
        }).json()["data"]["id"]
        rec = RegulatoryReport(
            config_id=cid, city="异常市", report_type="order",
            status="failed", retry_count=1, error_message="boom",
        )
        db_session.add(rec)
        db_session.commit()
        db_session.refresh(rec)
        rid_f = rec.id
        ckid = client.post("/api/v1/operate/supervision/compliance", json={
            "config_id": cid, "check_type": "compliance", "result": "pass",
        }).json()["data"]["id"]

        monkeypatch.setattr(mod, "success_response", _boom)
        monkeypatch.setattr(mod, "paginated_response", _boom)

        # DELETE 放最后: 其 db.delete+commit 会真正删配置, 影响后续依赖 cid 的端点
        cases = [
            ("GET", "/api/v1/operate/supervision/configs", None),
            ("POST", "/api/v1/operate/supervision/configs",
             {"city": "新市", "platform_url": "https://y"}),
            ("GET", f"/api/v1/operate/supervision/configs/{cid}", None),
            ("PUT", f"/api/v1/operate/supervision/configs/{cid}",
             {"report_strategy": "realtime"}),
            ("GET", "/api/v1/operate/supervision/reports", None),
            ("GET", f"/api/v1/operate/supervision/reports/{rid_s}", None),
            ("POST", "/api/v1/operate/supervision/reports/manual",
             {"config_id": cid, "report_type": "heartbeat"}),
            ("POST", f"/api/v1/operate/supervision/reports/{rid_f}/retry", None),
            ("GET", "/api/v1/operate/supervision/compliance", None),
            ("GET", f"/api/v1/operate/supervision/compliance/{ckid}", None),
            ("POST", "/api/v1/operate/supervision/compliance",
             {"config_id": cid, "check_type": "compliance", "result": "pass"}),
            ("DELETE", f"/api/v1/operate/supervision/configs/{cid}", None),
        ]
        for method, path, body in cases:
            resp = client.request(method, path, json=body)
            assert resp.status_code == 500, (
                f"{method} {path} 应 500, 实际 {resp.status_code}\n{resp.text}"
            )
