"""9 个路由文件异常处理加固测试 (卡 bc00d9f4)

覆盖 app/api/v1 下 8 个新增 try/except 的路由文件, 验证 DB 操作抛异常时
端点兜底返回 500 + 固定 detail (不裸抛 stack, 不泄露内部信息):

  admin_supervision                /api/v1/admin/supervision/...
  pricing_management/parking       /api/v1/pricing/mgmt/parking/...
  pricing_management/occupancy     /api/v1/pricing/mgmt/occupancy/...
  pricing_management/energy        /api/v1/pricing/mgmt/energy/...
  devices/maintenance_plan         /api/v1/devices/{id}/maintenance-...
  devices/health                   /api/v1/devices/{id}/health...
  system_config/audit              /api/v1/system-config/audit/...
  notification_rules               /api/v1/notification-rules/...

mock 策略 (参照 test_exception_hardening_8routes.py, 卡 21f3989f):
  - 鉴权链 (get_current_user / require_role / require_permission /
    require_write_permission) 全部用 Query.first() 查 user, 且不调用
    Session.commit(); admin/super_admin 在权限矩阵查询前旁路 return。
  - 故写端点: patch Session.commit 抛 OperationalError → 鉴权通过、业务 commit 处炸。
  - 读端点 (列表/分页/统计): patch Query.all/count/scalar 抛 OperationalError
    (鉴权仅用 .first() 不受影响)。

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
# admin_supervision — /api/v1/admin/supervision
# ════════════════════════════════════════════════════════════════

class TestAdminSupervisionApiException:
    """admin_supervision: 创建配置 commit 抛异常 → 500; 列表读异常 → 500。"""

    def test_create_config_db_exception_500(self, client, monkeypatch):
        _patch_commit(monkeypatch)
        body = {"city": "boom-city", "platform_url": "http://x"}
        res = client.post("/api/v1/admin/supervision/configs", json=body)
        assert res.status_code == 500, f"{res.status_code}: {res.text}"
        assert res.json()["detail"] == _DETAIL

    def test_list_configs_db_exception_500(self, client, monkeypatch):
        _patch_query_read(monkeypatch)
        res = client.get("/api/v1/admin/supervision/configs")
        assert res.status_code == 500, f"{res.status_code}: {res.text}"
        assert res.json()["detail"] == _DETAIL

    def test_manual_report_db_exception_500(self, client, monkeypatch):
        """手动上报: 先 seed config, 再 patch commit → 业务 commit 炸 500。"""
        from app.models.admin_supervision import MunicipalSupervisionConfig
        s = client._sesh
        cfg = MunicipalSupervisionConfig(
            city="boom-city", platform_url="http://x",
            report_strategy="scheduled", status="active",
        )
        s.add(cfg)
        s.commit()
        s.refresh(cfg)
        _patch_commit(monkeypatch)
        body = {"config_id": cfg.id, "report_type": "heartbeat"}
        res = client.post("/api/v1/admin/supervision/reports/manual", json=body)
        assert res.status_code == 500, f"{res.status_code}: {res.text}"
        assert res.json()["detail"] == _DETAIL


# ════════════════════════════════════════════════════════════════
# pricing_management/parking — /api/v1/pricing/mgmt/parking
# ════════════════════════════════════════════════════════════════

class TestParkingPriceApiException:
    """parking: 创建定价 commit 抛异常 → 500; 列表读异常 → 500。"""

    def test_create_parking_db_exception_500(self, client, monkeypatch):
        _patch_commit(monkeypatch)
        body = {
            "station_id": 1, "free_minutes": 15, "hourly_rate": 5.0,
            "enable_night_rate": False, "effective_date": "2026-01-01",
            "is_active": False,
        }
        res = client.post("/api/v1/pricing/mgmt/parking", json=body)
        assert res.status_code == 500, f"{res.status_code}: {res.text}"
        assert res.json()["detail"] == _DETAIL

    def test_list_parking_db_exception_500(self, client, monkeypatch):
        _patch_query_read(monkeypatch)
        res = client.get("/api/v1/pricing/mgmt/parking")
        assert res.status_code == 500, f"{res.status_code}: {res.text}"
        assert res.json()["detail"] == _DETAIL


# ════════════════════════════════════════════════════════════════
# pricing_management/occupancy — /api/v1/pricing/mgmt/occupancy
# ════════════════════════════════════════════════════════════════

class TestOccupancyFeeApiException:
    """occupancy: 创建定价 commit 抛异常 → 500。"""

    def test_create_occupancy_db_exception_500(self, client, monkeypatch):
        _patch_commit(monkeypatch)
        body = {
            "station_id": 1, "grace_minutes": 30, "rate_per_minute": 0.5,
            "effective_date": "2026-01-01", "is_active": False,
        }
        res = client.post("/api/v1/pricing/mgmt/occupancy", json=body)
        assert res.status_code == 500, f"{res.status_code}: {res.text}"
        assert res.json()["detail"] == _DETAIL


# ════════════════════════════════════════════════════════════════
# pricing_management/energy — /api/v1/pricing/mgmt/energy
# ════════════════════════════════════════════════════════════════

class TestEnergyPriceApiException:
    """energy: 创建定价 commit 抛异常 → 500。"""

    def test_create_energy_db_exception_500(self, client, monkeypatch):
        _patch_commit(monkeypatch)
        body = {
            "station_id": 1, "slot_id": 1, "price_per_kwh": 1.2,
            "effective_date": "2026-01-01", "is_active": False,
        }
        res = client.post("/api/v1/pricing/mgmt/energy", json=body)
        assert res.status_code == 500, f"{res.status_code}: {res.text}"
        assert res.json()["detail"] == _DETAIL


# ════════════════════════════════════════════════════════════════
# devices/maintenance_plan — /api/v1/devices/{id}/maintenance-plan
# ════════════════════════════════════════════════════════════════

class TestMaintenancePlanApiException:
    """maintenance_plan: seed 设备后更新计划 commit 抛异常 → 500。"""

    @staticmethod
    def _seed_device(client):
        from app.models.device import Device, DeviceType, DeviceStatus
        from app.models.station import Station, StationStatus
        s = client._sesh
        st = Station(name="站点-MP-BOOM", code="ST-MP-BOOM",
                     address="测试地址", status=StationStatus.NORMAL)
        s.add(st)
        s.commit()
        s.refresh(st)
        dev = Device(
            sn="SN-MP-BOOM", name="桩BOOM", code="CODE-MP-BOOM",
            type=DeviceType.CHARGER_AC, status=DeviceStatus.ONLINE,
            rated_power=7.0, station_id=st.id,
        )
        s.add(dev)
        s.commit()
        s.refresh(dev)
        return dev.id

    def test_update_maintenance_plan_db_exception_500(self, client, monkeypatch):
        did = self._seed_device(client)
        _patch_commit(monkeypatch)
        body = {"maintenance_interval_days": 30}
        res = client.put(f"/api/v1/devices/{did}/maintenance-plan", json=body)
        assert res.status_code == 500, f"{res.status_code}: {res.text}"
        assert res.json()["detail"] == _DETAIL


# ════════════════════════════════════════════════════════════════
# devices/health — /api/v1/devices/{id}/health
# ════════════════════════════════════════════════════════════════

class TestDeviceHealthApiException:
    """health: seed 设备后计算健康度 commit 抛异常 → 500。"""

    @staticmethod
    def _seed_device(client):
        from app.models.device import Device, DeviceType, DeviceStatus
        from app.models.station import Station, StationStatus
        s = client._sesh
        st = Station(name="站点-HLTH-BOOM", code="ST-HLTH-BOOM",
                     address="测试地址", status=StationStatus.NORMAL)
        s.add(st)
        s.commit()
        s.refresh(st)
        dev = Device(
            sn="SN-HLTH-BOOM", name="桩BOOM", code="CODE-HLTH-BOOM",
            type=DeviceType.CHARGER_AC, status=DeviceStatus.ONLINE,
            rated_power=7.0, station_id=st.id,
        )
        s.add(dev)
        s.commit()
        s.refresh(dev)
        return dev.id

    def test_calculate_health_db_exception_500(self, client, monkeypatch):
        did = self._seed_device(client)
        _patch_commit(monkeypatch)
        body = {"insulation_resistance": 10.0}
        res = client.post(f"/api/v1/devices/{did}/health", json=body)
        assert res.status_code == 500, f"{res.status_code}: {res.text}"
        assert res.json()["detail"] == _DETAIL


# ════════════════════════════════════════════════════════════════
# system_config/audit — /api/v1/system-config/audit
# ════════════════════════════════════════════════════════════════

class TestAuditApiException:
    """audit: 统计端点 (含 .all/.count/.group_by) 读异常 → 500;
    列表读异常 → 500。"""

    def test_audit_stats_db_exception_500(self, client, monkeypatch):
        _patch_query_read(monkeypatch)
        res = client.get("/api/v1/system-config/audit/logs/stats")
        assert res.status_code == 500, f"{res.status_code}: {res.text}"
        assert res.json()["detail"] == _DETAIL

    def test_audit_logs_list_db_exception_500(self, client, monkeypatch):
        _patch_query_read(monkeypatch)
        res = client.get("/api/v1/system-config/audit/logs")
        assert res.status_code == 500, f"{res.status_code}: {res.text}"
        assert res.json()["detail"] == _DETAIL


# ════════════════════════════════════════════════════════════════
# notification_rules — /api/v1/notification-rules
# ════════════════════════════════════════════════════════════════

class TestNotificationRulesApiException:
    """notification_rules: 创建规则 commit 抛异常 → 500; 列表读异常 → 500。"""

    def test_create_rule_db_exception_500(self, client, monkeypatch):
        _patch_commit(monkeypatch)
        body = {"name": "boom-rule", "level": "warning"}
        res = client.post("/api/v1/notification-rules", json=body)
        assert res.status_code == 500, f"{res.status_code}: {res.text}"
        assert res.json()["detail"] == _DETAIL

    def test_list_rules_db_exception_500(self, client, monkeypatch):
        _patch_query_read(monkeypatch)
        res = client.get("/api/v1/notification-rules")
        assert res.status_code == 500, f"{res.status_code}: {res.text}"
        assert res.json()["detail"] == _DETAIL


# ════════════════════════════════════════════════════════════════
# 日志记录: logger.exception 应在异常路径触发
# ════════════════════════════════════════════════════════════════

class TestExceptionLogged:
    """异常路径应经 logger.exception 记录 (抽样验证)。"""

    def test_admin_supervision_create_exception_logged(self, client, monkeypatch, caplog):
        _patch_commit(monkeypatch)
        with caplog.at_level(logging.ERROR, logger="app.api.v1.admin_supervision"):
            client.post(
                "/api/v1/admin/supervision/configs",
                json={"city": "boom-city", "platform_url": "http://x"},
            )
        assert any("create_config 异常" in r.getMessage() for r in caplog.records)

    def test_notification_rules_create_exception_logged(self, client, monkeypatch, caplog):
        _patch_commit(monkeypatch)
        with caplog.at_level(logging.ERROR, logger="app.api.v1.notification_rules"):
            client.post(
                "/api/v1/notification-rules",
                json={"name": "boom-rule", "level": "warning"},
            )
        assert any("create_rule 异常" in r.getMessage() for r in caplog.records)
