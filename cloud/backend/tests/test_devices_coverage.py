"""
devices.py 端点覆盖率补充测试（任务卡 113bd512）

补足 app/api/v1/devices.py 中未被现有测试覆盖的端点/分支：
- create / update / delete_device（admin 默认站逻辑 + 团队级 station_id 校验）
- calculate_health (POST /{id}/health) 与 get_device_health 无数据 404 分支
- get_health_history、get_device_efficiency
- V2G 充电桩模式切换控制（charge/discharge/standby + 非法 action 拒绝）
- 标准控制的服务失败(400)/异常(500) 返回路径（回归 error_response 参数顺序 bug）
- get_maintenance_due / run_maintenance_check（含非 admin team 过滤与异常 500）
- get / update device_config（默认配置、字段校验、时段校验）
- team scoping helper（_device_team_id / _check_device_team 非 admin 路径）
- list_devices station_id 过滤
"""
from datetime import datetime, timezone, timedelta, date

import pytest
from unittest.mock import patch, AsyncMock

from tests._test_helpers import _fast_hash  # 卡17354607: 复用进程级 bcrypt hash 缓存


def _token(client, username="admin", password="admin123"):
    """登录拿 token；失败直接 fail 暴露真实问题。"""
    r = client.post(
        "/api/v1/auth/login",
        data={"username": username, "password": password},
    )
    assert r.status_code == 200, f"login 失败: {r.status_code} {r.text}"
    return r.json()["data"]["token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


# ──────────────────────────────────────────────────────────────
# 团队级用户 fixture：建 team + 本/他队站点 + 本/他队设备 + ENGINEER 用户
# ──────────────────────────────────────────────────────────────
def _setup_team(client, code="TM"):
    """构造团队级用户场景，并把 client 认证头切到该 ENGINEER。"""
    from app.models.user import User, UserRole, Team
    from app.models.station import Station, StationStatus
    from app.models.device import Device, DeviceType, DeviceStatus

    s = client._sesh
    team = Team(name=f"团队{code}", code=f"T{code}")
    s.add(team)
    s.commit()
    s.refresh(team)

    st_own = Station(name="本队站", code=f"{code}O", status=StationStatus.NORMAL, team_id=team.id)
    # 他队站点：team_id 指向不存在团队（SQLite 默认不校验 FK）
    st_other = Station(name="他队站", code=f"{code}X", status=StationStatus.NORMAL, team_id=999_111)
    s.add_all([st_own, st_other])
    s.commit()
    s.refresh(st_own)
    s.refresh(st_other)

    dev_own = Device(
        sn=f"SN-{code}O", name="本队设备", code=f"{code}O",
        type=DeviceType.CHARGER_DC, status=DeviceStatus.ONLINE,
        station_id=st_own.id, rated_power=60.0,
    )
    dev_other = Device(
        sn=f"SN-{code}X", name="他队设备", code=f"{code}X",
        type=DeviceType.CHARGER_DC, status=DeviceStatus.ONLINE,
        station_id=st_other.id, rated_power=60.0,
    )
    s.add_all([dev_own, dev_other])
    s.commit()
    s.refresh(dev_own)
    s.refresh(dev_other)

    username = f"eng_{code}"
    s.add(User(
        username=username,
        password_hash=_fast_hash("eng123"),
        role=UserRole.ENGINEER,
        team_id=team.id,
        status="active",
    ))
    s.commit()

    token = _token(client, username, "eng123")
    client.headers["Authorization"] = f"Bearer {token}"  # 切到团队级用户
    return {
        "token": token,
        "team_id": team.id,
        "station_own": st_own,
        "station_other": st_other,
        "device_own": dev_own,
        "device_other": dev_other,
    }


def _admin(client):
    """把 client 认证头切回 admin。"""
    token = _token(client)
    client.headers["Authorization"] = f"Bearer {token}"
    return token


# ════════════════════════════════════════════════════════════
# create_device
# ════════════════════════════════════════════════════════════
class TestCreateDevice:
    def test_admin_create_with_station_id(self, client, seed_users, seed_stations):
        token = _token(client)
        sid = seed_stations["station_a"].id
        resp = client.post("/api/v1/devices", json={
            "sn": "SN-NEW1", "code": "NEW1", "name": "新设备1",
            "type": "charger_dc", "station_id": str(sid),
        }, headers=_auth(token))
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["station_id"] == sid

    def test_admin_create_creates_default_station(self, client, seed_users):
        """未传 station_id 且无 DEFAULT 站点 → 自动创建 DEFAULT 站点。"""
        token = _token(client)
        resp = client.post("/api/v1/devices", json={
            "sn": "SN-DEF", "code": "DEF", "name": "默认站设备", "type": "pv_inverter",
        }, headers=_auth(token))
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["station_id"] is not None

    def test_admin_create_uses_existing_default(self, client, seed_users):
        """DEFAULT 站点已存在 → 复用，不新建。"""
        from app.models.station import Station, StationStatus
        s = client._sesh
        s.add(Station(name="默认电站", code="DEFAULT", address="系统默认", status=StationStatus.NORMAL))
        s.commit()
        token = _token(client)
        resp = client.post("/api/v1/devices", json={
            "sn": "SN-DEF2", "code": "DEF2", "name": "默认站设备2", "type": "pv_inverter",
        }, headers=_auth(token))
        assert resp.status_code == 200, resp.text

    def test_non_admin_create_no_station_400(self, client, seed_users):
        info = _setup_team(client)
        resp = client.post("/api/v1/devices", json={
            "sn": "SN-X", "code": "X", "name": "X", "type": "charger_dc",
        }, headers=_auth(info["token"]))
        assert resp.status_code == 400, resp.text

    def test_non_admin_create_other_team_station_404(self, client, seed_users):
        info = _setup_team(client)
        resp = client.post("/api/v1/devices", json={
            "sn": "SN-Y", "code": "Y", "name": "Y", "type": "charger_dc",
            "station_id": str(info["station_other"].id),
        }, headers=_auth(info["token"]))
        assert resp.status_code == 404, resp.text

    def test_non_admin_create_own_team_ok(self, client, seed_users):
        info = _setup_team(client)
        resp = client.post("/api/v1/devices", json={
            "sn": "SN-Z", "code": "Z", "name": "Z", "type": "charger_dc",
            "station_id": str(info["station_own"].id),
        }, headers=_auth(info["token"]))
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["station_id"] == info["station_own"].id


# ════════════════════════════════════════════════════════════
# update_device
# ════════════════════════════════════════════════════════════
class TestUpdateDevice:
    def test_update_fields(self, client, seed_users, seed_devices):
        token = _token(client)
        dev = seed_devices["chg001"]
        resp = client.put(f"/api/v1/devices/{dev.id}", json={
            "name": "改名", "status": "offline", "rated_power": 99.0,
        }, headers=_auth(token))
        assert resp.status_code == 200, resp.text
        d = resp.json()["data"]
        assert d["name"] == "改名"
        assert d["status"] == "offline"
        assert d["rated_power"] == 99.0

    def test_update_nonexistent_404(self, client, seed_users):
        token = _token(client)
        resp = client.put("/api/v1/devices/99999", json={"name": "x"}, headers=_auth(token))
        assert resp.status_code == 404, resp.text


# ════════════════════════════════════════════════════════════
# delete_device
# ════════════════════════════════════════════════════════════
class TestDeleteDevice:
    def test_delete_ok(self, client, seed_users, seed_stations):
        from app.models.device import Device, DeviceType, DeviceStatus
        s = client._sesh
        dev = Device(
            sn="SN-DEL", name="删除设备", code="DEL", type=DeviceType.METER,
            status=DeviceStatus.ONLINE, station_id=seed_stations["station_a"].id,
        )
        s.add(dev); s.commit(); s.refresh(dev)
        token = _token(client)
        resp = client.delete(f"/api/v1/devices/{dev.id}", headers=_auth(token))
        assert resp.status_code == 200, resp.text

    def test_delete_nonexistent_404(self, client, seed_users):
        token = _token(client)
        resp = client.delete("/api/v1/devices/99999", headers=_auth(token))
        assert resp.status_code == 404, resp.text


# ════════════════════════════════════════════════════════════
# calculate_health (POST /{id}/health) + get_device_health 404 分支
# ════════════════════════════════════════════════════════════
class TestCalculateHealth:
    def test_calculate_health_ok(self, client, seed_users, seed_devices):
        token = _token(client)
        dev = seed_devices["chg001"]
        resp = client.post(f"/api/v1/devices/{dev.id}/health", json={}, headers=_auth(token))
        assert resp.status_code == 200, resp.text
        d = resp.json()["data"]
        assert "total_score" in d
        assert "dimension_scores" in d
        assert "alarm" in d

    def test_calculate_health_nonexistent_404(self, client, seed_users):
        token = _token(client)
        resp = client.post("/api/v1/devices/99999/health", json={}, headers=_auth(token))
        assert resp.status_code == 404, resp.text

    def test_get_health_404_when_no_health_info(self, client, seed_users, seed_devices):
        """设备存在但 health_service 无健康信息 → 404（覆盖 not health_info 分支）。"""
        token = _token(client)
        dev = seed_devices["chg001"]
        with patch("app.services.health.health_service.get_device_health", return_value=None):
            resp = client.get(f"/api/v1/devices/{dev.id}/health", headers=_auth(token))
        assert resp.status_code == 404, resp.text


# ════════════════════════════════════════════════════════════
# get_health_history
# ════════════════════════════════════════════════════════════
class TestHealthHistory:
    def test_history_empty(self, client, seed_users, seed_devices):
        token = _token(client)
        dev = seed_devices["chg001"]
        resp = client.get(f"/api/v1/devices/{dev.id}/health/history", headers=_auth(token))
        assert resp.status_code == 200, resp.text
        assert isinstance(resp.json()["data"], list)

    def test_history_with_records(self, client, seed_users, seed_devices):
        from app.models.device import DeviceHealthRecord
        token = _token(client)
        dev = seed_devices["chg001"]
        s = client._sesh
        s.add(DeviceHealthRecord(
            device_id=dev.id, electrical_safe_score=90, thermal_score=80,
            comm_score=70, power_quality_score=60, mechanical_score=50, total_score=70.0,
        ))
        s.commit()
        resp = client.get(f"/api/v1/devices/{dev.id}/health/history?days=7", headers=_auth(token))
        assert resp.status_code == 200, resp.text
        assert len(resp.json()["data"]) >= 1


# ════════════════════════════════════════════════════════════
# get_device_efficiency
# ════════════════════════════════════════════════════════════
class TestDeviceEfficiency:
    def test_efficiency_with_logs(self, client, seed_users, seed_devices):
        from app.models.device_efficiency_log import DeviceEfficiencyLog
        token = _token(client)
        dev = seed_devices["chg001"]
        s = client._sesh
        now = datetime.now(timezone.utc)
        samples = [("utilization", 70.0), ("charge", 92.5), ("generation", 88.0)]
        for i, (mt, val) in enumerate(samples):
            ts = now - timedelta(days=i)
            s.add(DeviceEfficiencyLog(
                device_id=dev.id, station_id=dev.station_id,
                metric_type=mt, metric_value=val, recorded_at=ts,
                log_date=ts.strftime("%Y-%m-%d"),
            ))
        dev.utilization_rate = 80.0
        dev.pv_pr_ratio = 0.85
        s.commit()
        resp = client.get(f"/api/v1/devices/{dev.id}/efficiency", headers=_auth(token))
        assert resp.status_code == 200, resp.text
        d = resp.json()["data"]
        assert d["utilization"]["current"] == 80.0
        assert d["charge_efficiency"]["current"] == 92.5
        assert d["generation_efficiency"]["pv_pr"] == 0.85
        # 趋势数组非空
        assert len(d["charge_efficiency"]["trend"]) >= 1

    def test_efficiency_nonexistent_404(self, client, seed_users):
        token = _token(client)
        resp = client.get("/api/v1/devices/99999/efficiency", headers=_auth(token))
        assert resp.status_code == 404, resp.text


# ════════════════════════════════════════════════════════════
# V2G 充电桩模式切换控制
# ════════════════════════════════════════════════════════════
class TestV2GControl:
    @pytest.fixture(autouse=True)
    def _v2g_device(self, client, seed_users, seed_stations):
        from app.models.device import Device, DeviceType, DeviceStatus
        s = client._sesh
        dev = Device(
            sn="SN-V2G", name="V2G桩", code="V2G1", type=DeviceType.V2G_CHARGER,
            status=DeviceStatus.ONLINE, station_id=seed_stations["station_a"].id, rated_power=50.0,
        )
        s.add(dev); s.commit(); s.refresh(dev)
        self.dev = dev
        self.token = _token(client)

    def test_v2g_charge_mode(self, client):
        resp = client.post(f"/api/v1/devices/{self.dev.id}/control", json={
            "action": "charge_mode", "value": 30,
        }, headers=_auth(self.token))
        assert resp.status_code == 200, resp.text
        d = resp.json()["data"]
        assert d["dispatch_type"] == "charge"
        assert d["target_power_kw"] == 30.0
        assert d["status"] == "pending"

    def test_v2g_discharge_defaults_zero(self, client):
        resp = client.post(f"/api/v1/devices/{self.dev.id}/control", json={
            "action": "discharge_mode",
        }, headers=_auth(self.token))
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["target_power_kw"] == 0.0

    def test_v2g_standby(self, client):
        resp = client.post(f"/api/v1/devices/{self.dev.id}/control", json={
            "action": "standby_mode",
        }, headers=_auth(self.token))
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["dispatch_type"] == "standby"

    def test_v2g_rejects_standard_action(self, client):
        resp = client.post(f"/api/v1/devices/{self.dev.id}/control", json={
            "action": "start",
        }, headers=_auth(self.token))
        assert resp.status_code == 400, resp.text

    def test_v2g_unknown_action(self, client):
        resp = client.post(f"/api/v1/devices/{self.dev.id}/control", json={
            "action": "boost_mode",
        }, headers=_auth(self.token))
        assert resp.status_code == 400, resp.text


# ════════════════════════════════════════════════════════════
# 标准控制：服务失败(400) / 异常(500) 返回路径
# 回归 error_response 参数顺序 bug（修前会抛 TypeError → 真实 500 无 body）
# ════════════════════════════════════════════════════════════
class TestControlFailurePaths:
    def test_control_service_failure_returns_body_400(self, client, seed_users, seed_devices):
        token = _token(client)
        dev = seed_devices["chg001"]
        with patch("app.api.v1.devices.DeviceControlService") as Mock:
            Mock.return_value.send_control = AsyncMock(
                return_value={"success": False, "error": "适配器故障"}
            )
            resp = client.post(f"/api/v1/devices/{dev.id}/control", json={
                "action": "start",
            }, headers=_auth(token))
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["code"] == 400
        assert "适配器故障" in body["message"]

    def test_control_exception_returns_body_500(self, client, seed_users, seed_devices):
        token = _token(client)
        dev = seed_devices["chg001"]
        with patch("app.api.v1.devices.DeviceControlService") as Mock:
            Mock.return_value.send_control = AsyncMock(side_effect=RuntimeError("boom"))
            resp = client.post(f"/api/v1/devices/{dev.id}/control", json={
                "action": "start",
            }, headers=_auth(token))
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["code"] == 500
        # 安全：异常原文(boom)不得泄露到响应体，须返回通用消息
        assert "boom" not in body["message"]
        assert body["message"] == "设备控制异常"

    def test_control_exception_inner_log_failure_still_returns_500(self, client, seed_users, seed_devices):
        """控制异常时，连「记录失败日志」本身也抛异常 → 兜底 handler 吞掉，端点仍返回 500。"""
        token = _token(client)
        dev = seed_devices["chg001"]
        with patch("app.api.v1.devices.DeviceControlService") as Mock, \
             patch("app.api.v1.devices.DeviceControlLog", side_effect=RuntimeError("log fail")):
            Mock.return_value.send_control = AsyncMock(side_effect=RuntimeError("boom"))
            resp = client.post(f"/api/v1/devices/{dev.id}/control", json={
                "action": "start",
            }, headers=_auth(token))
        assert resp.status_code == 200, resp.text
        assert resp.json()["code"] == 500


# ════════════════════════════════════════════════════════════
# maintenance-due / run-maintenance-check
# ════════════════════════════════════════════════════════════
class TestMaintenanceDue:
    def test_maintenance_due_admin(self, client, seed_users, seed_stations):
        from app.models.device import Device, DeviceType, DeviceStatus
        s = client._sesh
        s.add(Device(
            sn="SN-DUE", name="到期设备", code="DUE", type=DeviceType.CHARGER_DC,
            status=DeviceStatus.ONLINE, station_id=seed_stations["station_a"].id,
            next_maintenance=date.today() + timedelta(days=3),
        ))
        s.commit()
        token = _token(client)
        resp = client.get("/api/v1/devices/maintenance-due?days_ahead=30", headers=_auth(token))
        assert resp.status_code == 200, resp.text
        d = resp.json()["data"]
        assert "items" in d and "stats" in d

    def test_maintenance_due_non_admin_filtered(self, client, seed_users):
        info = _setup_team(client)
        s = client._sesh
        info["device_own"].next_maintenance = date.today() + timedelta(days=5)
        s.commit()
        resp = client.get("/api/v1/devices/maintenance-due?days_ahead=30", headers=_auth(info["token"]))
        assert resp.status_code == 200, resp.text
        ids = [it["device_id"] for it in resp.json()["data"]["items"]]
        assert info["device_own"].id in ids

    def test_maintenance_due_exception_500(self, client, seed_users):
        token = _token(client)
        with patch("app.api.v1.devices.maintenance_schedule_checker.get_upcoming_maintenance",
                   side_effect=RuntimeError("x")):
            resp = client.get("/api/v1/devices/maintenance-due", headers=_auth(token))
        assert resp.status_code == 500, resp.text


class TestRunMaintenanceCheck:
    def test_run_check_admin(self, client, seed_users, seed_stations):
        from app.models.device import Device, DeviceType, DeviceStatus
        s = client._sesh
        s.add(Device(
            sn="SN-CHK", name="检查设备", code="CHK", type=DeviceType.CHARGER_DC,
            status=DeviceStatus.ONLINE, station_id=seed_stations["station_a"].id,
            next_maintenance=date.today() - timedelta(days=1),
            maintenance_interval_days=30,
        ))
        s.commit()
        token = _token(client)
        resp = client.post("/api/v1/devices/run-maintenance-check", headers=_auth(token))
        assert resp.status_code == 200, resp.text

    def test_run_check_non_admin_filtered(self, client, seed_users):
        info = _setup_team(client)
        s = client._sesh
        info["device_own"].next_maintenance = date.today() - timedelta(days=1)
        info["device_own"].maintenance_interval_days = 30
        s.commit()
        resp = client.post("/api/v1/devices/run-maintenance-check", headers=_auth(info["token"]))
        assert resp.status_code == 200, resp.text

    def test_run_check_exception_500(self, client, seed_users):
        token = _token(client)
        with patch("app.api.v1.devices.maintenance_schedule_checker.check_maintenance_schedule",
                   side_effect=RuntimeError("x")):
            resp = client.post("/api/v1/devices/run-maintenance-check", headers=_auth(token))
        assert resp.status_code == 500, resp.text


# ════════════════════════════════════════════════════════════
# get_device_config
# ════════════════════════════════════════════════════════════
class TestGetDeviceConfig:
    def test_get_config_default(self, client, seed_users, seed_devices):
        token = _token(client)
        dev = seed_devices["chg001"]  # charger_dc, 无 config 行
        resp = client.get(f"/api/v1/devices/{dev.id}/config", headers=_auth(token))
        assert resp.status_code == 200, resp.text
        d = resp.json()["data"]
        assert d["voltage_limit"] == 420.0
        assert d["charge_mode"] == "smart"
        assert d["time_periods"] == []

    def test_get_config_existing(self, client, seed_users, seed_devices):
        from app.models.device_config import DeviceConfig, ChargeMode
        token = _token(client)
        dev = seed_devices["chg001"]
        s = client._sesh
        s.add(DeviceConfig(
            device_id=dev.id, voltage_limit=400.0, current_limit=50.0,
            max_power=55.0, charge_mode=ChargeMode.FAST, overload_protection=False,
        ))
        s.commit()
        resp = client.get(f"/api/v1/devices/{dev.id}/config", headers=_auth(token))
        assert resp.status_code == 200, resp.text
        d = resp.json()["data"]
        assert d["voltage_limit"] == 400.0
        assert d["charge_mode"] == "fast"

    def test_get_config_non_charger_400(self, client, seed_users, seed_devices):
        token = _token(client)
        dev = seed_devices["inv001"]  # pv_inverter
        resp = client.get(f"/api/v1/devices/{dev.id}/config", headers=_auth(token))
        assert resp.status_code == 400, resp.text

    def test_get_config_nonexistent_404(self, client, seed_users):
        token = _token(client)
        resp = client.get("/api/v1/devices/99999/config", headers=_auth(token))
        assert resp.status_code == 404, resp.text


# ════════════════════════════════════════════════════════════
# update_device_config
# ════════════════════════════════════════════════════════════
class TestUpdateDeviceConfig:
    def test_update_config_create_and_all_fields(self, client, seed_users, seed_devices):
        token = _token(client)
        dev = seed_devices["chg001"]
        resp = client.put(f"/api/v1/devices/{dev.id}/config", json={
            "voltage_limit": 430.0, "current_limit": 61.0, "max_power": 62.0,
            "charge_mode": "eco", "overload_protection": False,
            "time_periods": [{"start_time": "00:00", "end_time": "06:00", "power_limit": 30.0}],
        }, headers=_auth(token))
        assert resp.status_code == 200, resp.text
        d = resp.json()["data"]
        assert d["voltage_limit"] == 430.0
        assert d["charge_mode"] == "eco"
        assert len(d["time_periods"]) == 1

    def test_update_config_existing_row(self, client, seed_users, seed_devices):
        from app.models.device_config import DeviceConfig
        token = _token(client)
        dev = seed_devices["chg001"]
        s = client._sesh
        s.add(DeviceConfig(device_id=dev.id))
        s.commit()
        resp = client.put(f"/api/v1/devices/{dev.id}/config", json={
            "max_power": 70.0,
        }, headers=_auth(token))
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["max_power"] == 70.0

    def test_update_config_invalid_voltage(self, client, seed_users, seed_devices):
        token = _token(client)
        dev = seed_devices["chg001"]
        resp = client.put(f"/api/v1/devices/{dev.id}/config", json={
            "voltage_limit": 0,
        }, headers=_auth(token))
        assert resp.status_code == 400, resp.text

    def test_update_config_invalid_current(self, client, seed_users, seed_devices):
        token = _token(client)
        dev = seed_devices["chg001"]
        resp = client.put(f"/api/v1/devices/{dev.id}/config", json={
            "current_limit": -1,
        }, headers=_auth(token))
        assert resp.status_code == 400, resp.text

    def test_update_config_invalid_power(self, client, seed_users, seed_devices):
        token = _token(client)
        dev = seed_devices["chg001"]
        resp = client.put(f"/api/v1/devices/{dev.id}/config", json={
            "max_power": 0,
        }, headers=_auth(token))
        assert resp.status_code == 400, resp.text

    def test_update_config_invalid_charge_mode(self, client, seed_users, seed_devices):
        token = _token(client)
        dev = seed_devices["chg001"]
        resp = client.put(f"/api/v1/devices/{dev.id}/config", json={
            "charge_mode": "turbo",
        }, headers=_auth(token))
        assert resp.status_code == 400, resp.text

    def test_update_config_invalid_time_period_order(self, client, seed_users, seed_devices):
        token = _token(client)
        dev = seed_devices["chg001"]
        resp = client.put(f"/api/v1/devices/{dev.id}/config", json={
            "time_periods": [{"start_time": "06:00", "end_time": "00:00", "power_limit": 10.0}],
        }, headers=_auth(token))
        assert resp.status_code == 400, resp.text

    def test_update_config_invalid_time_period_power(self, client, seed_users, seed_devices):
        token = _token(client)
        dev = seed_devices["chg001"]
        resp = client.put(f"/api/v1/devices/{dev.id}/config", json={
            "time_periods": [{"start_time": "00:00", "end_time": "06:00", "power_limit": 0}],
        }, headers=_auth(token))
        assert resp.status_code == 400, resp.text

    def test_update_config_non_charger_400(self, client, seed_users, seed_devices):
        token = _token(client)
        dev = seed_devices["inv001"]
        resp = client.put(f"/api/v1/devices/{dev.id}/config", json={
            "max_power": 70.0,
        }, headers=_auth(token))
        assert resp.status_code == 400, resp.text

    def test_update_config_nonexistent_404(self, client, seed_users):
        token = _token(client)
        resp = client.put("/api/v1/devices/99999/config", json={"max_power": 70.0}, headers=_auth(token))
        assert resp.status_code == 404, resp.text


# ════════════════════════════════════════════════════════════
# team scoping helper + list station_id 过滤
# ════════════════════════════════════════════════════════════
class TestTeamScopingAndFilters:
    def test_non_admin_lists_only_own_team(self, client, seed_users):
        info = _setup_team(client)
        resp = client.get("/api/v1/devices", headers=_auth(info["token"]))
        assert resp.status_code == 200, resp.text
        ids = [it["id"] for it in resp.json()["data"]["items"]]
        assert info["device_own"].id in ids
        assert info["device_other"].id not in ids

    def test_non_admin_get_own_device_ok(self, client, seed_users):
        info = _setup_team(client)
        resp = client.get(f"/api/v1/devices/{info['device_own'].id}", headers=_auth(info["token"]))
        assert resp.status_code == 200, resp.text

    def test_non_admin_get_other_team_404(self, client, seed_users):
        info = _setup_team(client)
        resp = client.get(f"/api/v1/devices/{info['device_other'].id}", headers=_auth(info["token"]))
        assert resp.status_code == 404, resp.text

    def test_list_filter_by_station_id(self, client, seed_users, seed_stations, seed_devices):
        token = _token(client)
        sid = seed_stations["station_a"].id
        resp = client.get(f"/api/v1/devices?station_id={sid}", headers=_auth(token))
        assert resp.status_code == 200, resp.text
        for it in resp.json()["data"]["items"]:
            assert it["station_id"] == sid
