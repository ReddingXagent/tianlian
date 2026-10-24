"""8 路由文件异常处理加固测试 (卡 21f3989f)

覆盖 app/api/v1 下 8 个新增 try/except 的路由文件, 验证 DB 操作抛异常时
端点兜底返回 500 + 固定 detail (不裸抛 stack, 不泄露内部信息):

  points_api / discount / v2g / runbook_templates
  users_api / spare_parts / alarm_notices / report_mgmt

mock 策略 (参照 test_dashboard_large_screen.TestLargeScreenDBException, 卡 a6e2e562):
  - 鉴权链 (get_current_user / require_write_permission / require_permission) 全部
    用 Query.first() 查 user, 且不调用 Session.commit()。
  - 故写端点: patch Session.commit 抛 OperationalError → 鉴权通过、业务 commit 处炸。
  - 读端点: patch Query.all/count/scalar 抛 OperationalError (鉴权仅用 .first() 不受影响)。

断言: status_code == 500 且 resp.json()['detail'] == 固定文案。
"""
import logging

import pytest
from sqlalchemy.exc import OperationalError


def _boom(*args, **kwargs):
    raise OperationalError("SELECT 1", {}, Exception("db down"))


# ─── patch 工具 ──────────────────────────────────────────────────

def _patch_commit(monkeypatch):
    """让所有 Session.commit 抛异常 (鉴权链不 commit → 鉴权不受影响)。"""
    from sqlalchemy.orm import Session
    monkeypatch.setattr(Session, "commit", _boom)


def _patch_query_read(monkeypatch):
    """让 Query 读方法 (.all/.count/.scalar) 抛异常; .first 保留给鉴权链。"""
    from sqlalchemy.orm.query import Query
    monkeypatch.setattr(Query, "all", _boom)
    monkeypatch.setattr(Query, "count", _boom)
    monkeypatch.setattr(Query, "scalar", _boom)


_DETAIL = "服务器内部错误，请稍后重试"


# ════════════════════════════════════════════════════════════════
# points_api — /api/v1/operate/points
# ════════════════════════════════════════════════════════════════

class TestPointsApiException:
    """points_api: 写端点 (create rule) commit 抛异常 → 500。"""

    def test_create_rule_db_exception_500(self, client, monkeypatch):
        _patch_commit(monkeypatch)
        body = {"name": "boom", "rule_type": "charge", "points": 1}
        res = client.post("/api/v1/operate/points", json=body)
        assert res.status_code == 500, f"{res.status_code}: {res.text}"
        assert res.json()["detail"] == _DETAIL

    def test_list_rules_db_exception_500(self, client, monkeypatch):
        _patch_query_read(monkeypatch)
        res = client.get("/api/v1/operate/points")
        assert res.status_code == 500, f"{res.status_code}: {res.text}"
        assert res.json()["detail"] == _DETAIL


# ════════════════════════════════════════════════════════════════
# discount — /api/v1/operate/discount
# ════════════════════════════════════════════════════════════════

class TestDiscountApiException:
    """discount: 创建折扣 commit 抛异常 → 500。"""

    def test_create_discount_db_exception_500(self, client, monkeypatch):
        _patch_commit(monkeypatch)
        body = {
            "name": "boom", "discount_type": "percentage", "discount_rate": 0.1,
            "start_time": "2026-01-01T00:00:00", "end_time": "2026-12-31T00:00:00",
        }
        res = client.post("/api/v1/operate/discount", json=body)
        assert res.status_code == 500, f"{res.status_code}: {res.text}"
        assert res.json()["detail"] == _DETAIL


# ════════════════════════════════════════════════════════════════
# v2g — /api/v1/devices/{device_id}/v2g/dispatch
# ════════════════════════════════════════════════════════════════

class TestV2GApiException:
    """v2g: dispatch 端点 commit 抛异常 → 500 (admin 鉴权放行, seed V2G 设备)。"""

    @staticmethod
    def _seed_v2g_device(client):
        from app.models.device import Device, DeviceType, DeviceStatus
        from app.models.station import Station, StationStatus
        s = client._sesh
        st = Station(name="站点-V2G-BOOM", code="ST-V2G-BOOM",
                     address="测试地址", status=StationStatus.NORMAL)
        s.add(st)
        s.commit()
        s.refresh(st)
        dev = Device(
            sn="SN-V2G-BOOM", name="V2G桩BOOM", code="CODE-V2G-BOOM",
            type=DeviceType.V2G_CHARGER, status=DeviceStatus.ONLINE,
            rated_power=100.0, station_id=st.id,
        )
        s.add(dev)
        s.commit()
        s.refresh(dev)
        return dev.id

    def test_dispatch_db_exception_500(self, client, monkeypatch):
        did = self._seed_v2g_device(client)
        _patch_commit(monkeypatch)
        res = client.post(
            f"/api/v1/devices/{did}/v2g/dispatch",
            json={"dispatch_type": "charge", "target_power_kw": 10.0},
        )
        assert res.status_code == 500, f"{res.status_code}: {res.text}"
        assert res.json()["detail"] == _DETAIL


# ════════════════════════════════════════════════════════════════
# runbook_templates — /api/v1/runbooks/templates
# ════════════════════════════════════════════════════════════════

class TestRunbookTemplatesApiException:
    """runbook_templates: 创建模板 commit 抛异常 → 500。"""

    def test_create_template_db_exception_500(self, client, monkeypatch):
        _patch_commit(monkeypatch)
        body = {"name": "boom-tmpl", "category": "general"}
        res = client.post("/api/v1/runbooks/templates", json=body)
        assert res.status_code == 500, f"{res.status_code}: {res.text}"
        assert res.json()["detail"] == _DETAIL


# ════════════════════════════════════════════════════════════════
# users_api — /api/v1/operate/users
# ════════════════════════════════════════════════════════════════

class TestUsersApiException:
    """users_api: 用户列表读异常 → 500。"""

    def test_list_users_db_exception_500(self, client, monkeypatch):
        _patch_query_read(monkeypatch)
        res = client.get("/api/v1/operate/users")
        assert res.status_code == 500, f"{res.status_code}: {res.text}"
        assert res.json()["detail"] == _DETAIL


# ════════════════════════════════════════════════════════════════
# spare_parts — /api/v1/spare-parts
# ════════════════════════════════════════════════════════════════

class TestSparePartsApiException:
    """spare_parts: 登记备件 commit 抛异常 → 500。"""

    def test_create_part_db_exception_500(self, client, monkeypatch):
        _patch_commit(monkeypatch)
        body = {"part_name": "boom-part", "total_quantity": 1}
        res = client.post("/api/v1/spare-parts", json=body)
        assert res.status_code == 500, f"{res.status_code}: {res.text}"
        assert res.json()["detail"] == _DETAIL


# ════════════════════════════════════════════════════════════════
# alarm_notices — /api/v1/alarm-notices
# ════════════════════════════════════════════════════════════════

class TestAlarmNoticesApiException:
    """alarm_notices: 通知列表读异常 → 500。"""

    def test_list_notices_db_exception_500(self, client, monkeypatch):
        _patch_query_read(monkeypatch)
        res = client.get("/api/v1/alarm-notices")
        assert res.status_code == 500, f"{res.status_code}: {res.text}"
        assert res.json()["detail"] == _DETAIL


# ════════════════════════════════════════════════════════════════
# report_mgmt — /api/v1/report-mgmt (raw SQL)
# ════════════════════════════════════════════════════════════════

class TestReportMgmtApiException:
    """report_mgmt: raw SQL 端点。create_report 经 admin 归属校验后 commit 抛异常 → 500。

    注意: report_mgmt 鉴权 (get_current_user) 的 Query.first() 内部走 Session.execute,
    故不能 patch execute (会炸鉴权)。改 patch commit: 鉴权不 commit, insert execute
    正常, 仅 commit 炸 → 落入端点 try/except。
    """

    def test_create_report_db_exception_500(self, client, monkeypatch):
        _patch_commit(monkeypatch)
        body = {"title": "boom-report", "type": "月报"}
        res = client.post("/api/v1/report-mgmt", json=body)
        assert res.status_code == 500, f"{res.status_code}: {res.text}"
        assert res.json()["detail"] == _DETAIL


# ════════════════════════════════════════════════════════════════
# 日志记录: logger.exception 应在异常路径触发
# ════════════════════════════════════════════════════════════════

class TestExceptionLogged:
    """异常路径应经 logger.exception 记录 (抽样 points_api 验证)。"""

    def test_points_create_exception_logged(self, client, monkeypatch, caplog):
        _patch_commit(monkeypatch)
        with caplog.at_level(logging.ERROR, logger="app.api.v1.operate.points_api"):
            client.post("/api/v1/operate/points",
                        json={"name": "boom", "rule_type": "charge", "points": 1})
        assert any("create_points_rule 异常" in r.getMessage() for r in caplog.records)
