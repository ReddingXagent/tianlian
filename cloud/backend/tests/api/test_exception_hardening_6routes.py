"""6 个路由文件异常处理加固测试 (卡 b4f5d41f)

覆盖 app/api/v1 下 6 个新增 try/except 的路由文件, 验证业务异常时端点兜底
返回 500 + 固定 detail (不裸抛 stack, 不泄露内部信息):

  fleet_overview            /api/v1/fleet/overview, /api/v1/fleet/balance-warning
  parking_events            /api/v1/parking/events, /api/v1/parking/events/batch
  enterprise_transactions   /api/v1/enterprises/{id}/transactions
  operate/overview          /api/v1/operate/overview
  permissions               /api/v1/permissions
  monitor                   /api/v1/monitor/realtime

mock 策略 (参照 test_exception_hardening_9routes.py, 卡 bc00d9f4):
  - 鉴权链 (get_current_user / require_write_permission) 全部用 Query.first()
    查 user/权限, 且不调用 Session.commit(); admin 在权限矩阵查询前旁路 return。
  - 故写端点: patch Session.commit 抛 OperationalError → 鉴权通过、业务 commit 处炸。
  - 读端点 (列表/统计): patch Query 读方法 (.all/.count/.scalar) 抛 OperationalError
    (鉴权仅用 .first() 不受影响)。
  - 不查 DB 的端点 (permissions/monitor): patch 模块内被调函数 (无 DB 路径),
    让其抛 ValueError → except 兜底。

断言: status_code == 500 且 resp.json()['detail'] == 固定文案。
"""
import logging

import pytest
from sqlalchemy.exc import OperationalError


_DETAIL = "服务器内部错误，请稍后重试"


def _boom(*args, **kwargs):
    raise OperationalError("SELECT 1", {}, Exception("db down"))


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


def _seed_enterprise(client):
    """seed 一个企业供 fleet/enterprise_transactions 端点使用, 返回 id。"""
    from app.models.enterprise import Enterprise
    s = client._sesh
    ent = Enterprise(name="车队-BOOM", code="ENT-BOOM", balance=1000, credit_limit=500)
    s.add(ent)
    s.commit()
    s.refresh(ent)
    return ent.id


def _seed_station(client):
    """seed 一个站点供 parking_events 端点使用, 返回 id。"""
    from app.models.station import Station, StationStatus
    s = client._sesh
    st = Station(name="站点-PK-BOOM", code="ST-PK-BOOM",
                 address="测试地址", status=StationStatus.NORMAL)
    s.add(st)
    s.commit()
    s.refresh(st)
    return st.id


# ════════════════════════════════════════════════════════════════
# fleet_overview — /api/v1/fleet
# ════════════════════════════════════════════════════════════════

class TestFleetOverviewApiException:
    """fleet_overview: 概览读异常 → 500; 低余额清单读异常 → 500。"""

    def test_overview_db_exception_500(self, client, monkeypatch):
        eid = _seed_enterprise(client)
        _patch_query_read(monkeypatch)
        res = client.get("/api/v1/fleet/overview", params={"enterprise_id": eid})
        assert res.status_code == 500, f"{res.status_code}: {res.text}"
        assert res.json()["detail"] == _DETAIL

    def test_balance_warning_db_exception_500(self, client, monkeypatch):
        _patch_query_read(monkeypatch)
        res = client.get("/api/v1/fleet/balance-warning")
        assert res.status_code == 500, f"{res.status_code}: {res.text}"
        assert res.json()["detail"] == _DETAIL


# ════════════════════════════════════════════════════════════════
# parking_events — /api/v1/parking/events
# ════════════════════════════════════════════════════════════════

class TestParkingEventsApiException:
    """parking_events: 单条/批量上报 commit 抛异常 → 500。"""

    def test_report_event_db_exception_500(self, client, monkeypatch):
        sid = _seed_station(client)
        _patch_commit(monkeypatch)
        body = {
            "plate_number": "京A12345", "station_id": sid,
            "enter_at": "2026-08-12T10:00:00",
        }
        res = client.post("/api/v1/parking/events", json=body)
        assert res.status_code == 500, f"{res.status_code}: {res.text}"
        assert res.json()["detail"] == _DETAIL

    def test_report_events_batch_db_exception_500(self, client, monkeypatch):
        sid = _seed_station(client)
        _patch_commit(monkeypatch)
        body = {"events": [{
            "plate_number": "京A12345", "station_id": sid,
            "enter_at": "2026-08-12T10:00:00",
        }]}
        res = client.post("/api/v1/parking/events/batch", json=body)
        assert res.status_code == 500, f"{res.status_code}: {res.text}"
        assert res.json()["detail"] == _DETAIL


# ════════════════════════════════════════════════════════════════
# enterprise_transactions — /api/v1/enterprises/{id}/transactions
# ════════════════════════════════════════════════════════════════

class TestEnterpriseTransactionsApiException:
    """enterprise_transactions: 列表读异常 → 500; 创建交易 commit 异常 → 500。"""

    def test_list_transactions_db_exception_500(self, client, monkeypatch):
        eid = _seed_enterprise(client)
        _patch_query_read(monkeypatch)
        res = client.get(f"/api/v1/enterprises/{eid}/transactions")
        assert res.status_code == 500, f"{res.status_code}: {res.text}"
        assert res.json()["detail"] == _DETAIL

    def test_create_transaction_db_exception_500(self, client, monkeypatch):
        eid = _seed_enterprise(client)
        _patch_commit(monkeypatch)
        body = {"type": "recharge", "amount": 100.0}
        res = client.post(f"/api/v1/enterprises/{eid}/transactions", json=body)
        assert res.status_code == 500, f"{res.status_code}: {res.text}"
        assert res.json()["detail"] == _DETAIL


# ════════════════════════════════════════════════════════════════
# operate/overview — /api/v1/operate/overview
# ════════════════════════════════════════════════════════════════

class TestOperateOverviewApiException:
    """operate/overview: 多统计查询读异常 → 500。"""

    def test_overview_db_exception_500(self, client, monkeypatch):
        _patch_query_read(monkeypatch)
        res = client.get("/api/v1/operate/overview")
        assert res.status_code == 500, f"{res.status_code}: {res.text}"
        assert res.json()["detail"] == _DETAIL


# ════════════════════════════════════════════════════════════════
# permissions — /api/v1/permissions (不查 DB, patch 模块内函数)
# ════════════════════════════════════════════════════════════════

class TestPermissionsApiException:
    """permissions: 纯枚举遍历无 DB; patch _build_items 抛异常 → 500。"""

    def test_list_permissions_exception_500(self, client, monkeypatch):
        def _raise(*a, **kw):
            raise RuntimeError("build items boom")
        monkeypatch.setattr("app.api.v1.permissions._build_items", _raise)
        res = client.get("/api/v1/permissions")
        assert res.status_code == 500, f"{res.status_code}: {res.text}"
        assert res.json()["detail"] == _DETAIL


# ════════════════════════════════════════════════════════════════
# monitor — /api/v1/monitor/realtime (patch datetime 注入异常)
# ════════════════════════════════════════════════════════════════

class TestMonitorApiException:
    """monitor: realtime 已接真实 Telemetry 聚合 (e8e4331cb), 旧 random.uniform
    注入点随假数据一起移除。改 patch 模块级 datetime 抛异常 → 500, 验证加固
    except 分支仍有效。
    """

    def test_realtime_exception_500(self, client, monkeypatch):
        def _boom(*a, **kw):
            raise RuntimeError("datetime boom")
        monkeypatch.setattr("app.api.v1.monitor.datetime", _boom)
        res = client.get("/api/v1/monitor/realtime")
        assert res.status_code == 500, f"{res.status_code}: {res.text}"
        assert res.json()["detail"] == _DETAIL

    def test_history_ok_200(self, client):
        """history 纯静态, 无可注入异常点, 仅确认加固后正常路径不破坏。"""
        res = client.get("/api/v1/monitor/history")
        assert res.status_code == 200, f"{res.status_code}: {res.text}"


# ════════════════════════════════════════════════════════════════
# 日志记录: logger.exception 应在异常路径触发 (抽样)
# ════════════════════════════════════════════════════════════════

class TestExceptionLogged6:
    """异常路径应经 logger.exception 记录 (抽样验证)。"""

    def test_fleet_overview_exception_logged(self, client, monkeypatch, caplog):
        eid = _seed_enterprise(client)
        _patch_query_read(monkeypatch)
        with caplog.at_level(logging.ERROR, logger="app.api.v1.fleet_overview"):
            client.get("/api/v1/fleet/overview", params={"enterprise_id": eid})
        assert any("fleet_overview 异常" in r.getMessage() for r in caplog.records)

    def test_operate_overview_exception_logged(self, client, monkeypatch, caplog):
        _patch_query_read(monkeypatch)
        with caplog.at_level(logging.ERROR, logger="app.api.v1.operate.overview"):
            client.get("/api/v1/operate/overview")
        assert any("operate_overview 异常" in r.getMessage() for r in caplog.records)
