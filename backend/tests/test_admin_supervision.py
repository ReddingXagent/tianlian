"""
管理后台 - 市政监管对接 后端测试 (SPEC §2.5)

覆盖:
- 监管平台配置 CRUD + 取值校验
- 上报记录: 手动触发 / 列表筛选 / 重试
- 合规检查: 触发 / 列表筛选 / 详情
"""
from decimal import Decimal


class TestSupervisionConfig:
    """市政监管平台配置"""

    def test_create_config(self, client):
        resp = client.post("/api/v1/admin/supervision/configs", json={
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
        assert data["report_strategy"] == "realtime"
        assert data["auth_config"]["app_id"] == "SZ001"
        assert data["station_endpoints"]["order"] == "/order"

    def test_invalid_report_strategy(self, client):
        resp = client.post("/api/v1/admin/supervision/configs", json={
            "city": "X", "platform_url": "https://x",
            "report_strategy": "unknown",
        })
        assert resp.status_code == 422  # Literal 前置 (卡 6031add1)

    def test_list_and_filter(self, client):
        client.post("/api/v1/admin/supervision/configs", json={
            "city": "北京市", "platform_url": "https://bj",
        })
        client.post("/api/v1/admin/supervision/configs", json={
            "city": "上海市", "platform_url": "https://sh", "status": "inactive",
        })

        resp = client.get("/api/v1/admin/supervision/configs")
        assert resp.json()["data"]["total"] >= 2

        resp = client.get("/api/v1/admin/supervision/configs?city=上海市")
        items = resp.json()["data"]["items"]
        assert len(items) == 1 and items[0]["city"] == "上海市"

        resp = client.get("/api/v1/admin/supervision/configs?status=inactive")
        assert resp.json()["data"]["total"] == 1

    def test_get_update_delete(self, client):
        r = client.post("/api/v1/admin/supervision/configs", json={
            "city": "广州市", "platform_url": "https://gz",
        })
        cid = r.json()["data"]["id"]

        assert client.get(f"/api/v1/admin/supervision/configs/{cid}").status_code == 200

        resp = client.put(f"/api/v1/admin/supervision/configs/{cid}", json={
            "report_strategy": "realtime", "report_interval_seconds": 15,
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["report_strategy"] == "realtime"
        assert data["report_interval_seconds"] == 15

        assert client.delete(f"/api/v1/admin/supervision/configs/{cid}").status_code == 200
        assert client.get(f"/api/v1/admin/supervision/configs/{cid}").status_code == 404

    def test_config_404(self, client):
        assert client.get("/api/v1/admin/supervision/configs/99999").status_code == 404


class TestRegulatoryReport:
    """监管数据上报"""

    def _make_config(self, client, city="深圳市"):
        r = client.post("/api/v1/admin/supervision/configs", json={
            "city": city, "platform_url": "https://supervision",
        })
        return r.json()["data"]["id"], city

    def test_manual_report(self, client):
        cid, city = self._make_config(client)
        resp = client.post("/api/v1/admin/supervision/reports/manual", json={
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
        resp = client.post("/api/v1/admin/supervision/reports/manual", json={
            "config_id": cid, "report_type": "invalid",
        })
        assert resp.status_code == 422  # Literal 前置 (卡 6031add1)

    def test_manual_report_config_not_found(self, client):
        resp = client.post("/api/v1/admin/supervision/reports/manual", json={
            "config_id": 99999, "report_type": "heartbeat",
        })
        assert resp.status_code == 404

    def test_list_and_filter(self, client):
        cid, city = self._make_config(client, "北京市")
        client.post("/api/v1/admin/supervision/reports/manual", json={
            "config_id": cid, "report_type": "station",
        })
        client.post("/api/v1/admin/supervision/reports/manual", json={
            "config_id": cid, "report_type": "order",
        })

        resp = client.get("/api/v1/admin/supervision/reports?config_id=%d" % cid)
        assert resp.json()["data"]["total"] == 2

        resp = client.get("/api/v1/admin/supervision/reports?report_type=order")
        items = resp.json()["data"]["items"]
        assert all(i["report_type"] == "order" for i in items)

        resp = client.get("/api/v1/admin/supervision/reports?city=北京市")
        assert resp.json()["data"]["total"] == 2

    def test_retry_failed_report(self, client):
        cid, _ = self._make_config(client)
        # 直接造一条失败记录: 先 manual 成功再用 DB 改状态(走 API 无法造 failed,
        # 改用报告详情 + 重试已成功的应被拒绝)
        r = client.post("/api/v1/admin/supervision/reports/manual", json={
            "config_id": cid, "report_type": "heartbeat",
        })
        rid = r.json()["data"]["id"]

        # 已成功的不允许重试
        resp = client.post(f"/api/v1/admin/supervision/reports/{rid}/retry")
        assert resp.status_code == 400

        # 详情
        assert client.get(f"/api/v1/admin/supervision/reports/{rid}").status_code == 200
        assert client.get("/api/v1/admin/supervision/reports/99999").status_code == 404

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

        resp = client.post(f"/api/v1/admin/supervision/reports/{rid}/retry")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "success"
        assert data["retry_count"] == 2
        assert data["error_message"] is None


class TestComplianceCheck:
    """合规检查"""

    def _make_config(self, client, city="深圳市"):
        r = client.post("/api/v1/admin/supervision/configs", json={
            "city": city, "platform_url": "https://supervision",
        })
        return r.json()["data"]["id"], city

    def test_run_compliance(self, client):
        cid, city = self._make_config(client)
        resp = client.post("/api/v1/admin/supervision/compliance", json={
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
        resp = client.post("/api/v1/admin/supervision/compliance", json={
            "config_id": cid, "check_type": "unknown", "result": "pass",
        })
        assert resp.status_code == 422  # Literal 前置 (卡 6031add1)

    def test_run_config_not_found(self, client):
        resp = client.post("/api/v1/admin/supervision/compliance", json={
            "config_id": 99999, "check_type": "compliance", "result": "pass",
        })
        assert resp.status_code == 404

    def test_list_and_detail(self, client):
        cid, _ = self._make_config(client, "杭州市")
        client.post("/api/v1/admin/supervision/compliance", json={
            "config_id": cid, "check_type": "report_delay", "result": "fail", "score": 40,
        })
        client.post("/api/v1/admin/supervision/compliance", json={
            "config_id": cid, "check_type": "compliance", "result": "pass", "score": 98,
        })

        resp = client.get("/api/v1/admin/supervision/compliance?config_id=%d" % cid)
        assert resp.json()["data"]["total"] == 2

        resp = client.get("/api/v1/admin/supervision/compliance?result=fail")
        items = resp.json()["data"]["items"]
        assert all(i["result"] == "fail" for i in items)

        resp = client.get("/api/v1/admin/supervision/compliance?check_type=compliance")
        assert resp.json()["data"]["total"] == 1

        # 详情 + 404
        r = client.post("/api/v1/admin/supervision/compliance", json={
            "config_id": cid, "check_type": "data_integrity", "result": "pass",
        })
        ckid = r.json()["data"]["id"]
        assert client.get(f"/api/v1/admin/supervision/compliance/{ckid}").status_code == 200
        assert client.get("/api/v1/admin/supervision/compliance/99999").status_code == 404
