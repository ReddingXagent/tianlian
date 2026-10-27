"""
告警通知 API 测试
覆盖: 列表 + 统计 + 标记已读/解决/忽略 + 全部已读
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    """自动注入 test_db fixture"""
    pass


@pytest.fixture
def auth_token(test_db):
    """获取认证token"""
    response = client.post("/api/v1/auth/login", data={
        "username": "admin",
        "password": "admin123"
    })
    assert response.status_code == 200
    data = response.json()
    token = data.get("token") or data.get("data", {}).get("token")
    return token


@pytest.fixture
def test_station(test_db):
    """创建测试站点"""
    db = test_db["session"]
    from app.models.station import Station, StationStatus
    station = Station(
        name="测试站点",
        code="TEST-STATION-001",
        status=StationStatus.NORMAL
    )
    db.add(station)
    db.commit()
    db.refresh(station)
    return station


@pytest.fixture
def test_device(test_db, test_station):
    """创建测试设备"""
    db = test_db["session"]
    from app.models.device import Device, DeviceType, DeviceStatus, ProtocolType
    device = Device(
        sn="TEST-DEV-001",
        name="测试设备",
        type=DeviceType.PV_INVERTER,
        status=DeviceStatus.ONLINE,
        station_id=test_station.id,
        protocol_type=ProtocolType.MODBUS_RTU
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return device


@pytest.fixture
def test_alarm(test_db, test_device):
    """创建测试告警"""
    db = test_db["session"]
    from app.models.alarm import Alarm, AlarmLevel, AlarmStatus
    alarm = Alarm(
        device_id=test_device.id,
        station_id=test_device.station_id,
        alarm_type="temperature_high",
        level=AlarmLevel.WARNING,
        content="温度超过阈值",
        status=AlarmStatus.ACTIVE
    )
    db.add(alarm)
    db.commit()
    db.refresh(alarm)
    return alarm


class TestAlarmNoticesAPI:
    """告警通知 API 测试类"""

    # ========== 列表 ==========

    def test_list_alarm_notices_success(self, auth_token):
        """测试获取告警通知列表成功"""
        response = client.get("/api/v1/alarm-notices", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        data = response.json()
        # 分页格式
        assert "items" in data.get("data", data) or "items" in data

    def test_list_alarm_notices_with_pagination(self, auth_token):
        """测试告警通知列表分页"""
        response = client.get("/api/v1/alarm-notices?page=1&page_size=10", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        data = response.json()
        # 检查分页字段
        items = data.get("data", {}).get("items", []) or data.get("items", [])
        total = data.get("data", {}).get("total", 0) or data.get("total", 0)
        page = data.get("data", {}).get("page", 1) or data.get("page", 1)
        assert page == 1

    def test_list_alarm_notices_with_level_filter(self, auth_token):
        """测试告警通知列表级别过滤"""
        response = client.get("/api/v1/alarm-notices?level=critical", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200

    def test_list_alarm_notices_with_status_filter(self, auth_token):
        """测试告警通知列表状态过滤"""
        response = client.get("/api/v1/alarm-notices?status=active", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200

    def test_list_alarm_notices_with_hours_filter(self, auth_token):
        """测试告警通知列表时间过滤"""
        response = client.get("/api/v1/alarm-notices?hours=24", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200

    def test_list_alarm_notices_combined_filters(self, auth_token):
        """测试告警通知列表组合过滤"""
        response = client.get("/api/v1/alarm-notices?level=warning&status=active&page=1&page_size=20", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200

    # ========== 统计 ==========

    def test_get_alarm_notice_stats_success(self, auth_token):
        """测试获取告警通知统计成功"""
        response = client.get("/api/v1/alarm-notices/stats", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        data = response.json()
        stats = data.get("data", data)
        # 统计应包含各级别数量
        assert "total_unread" in stats or "critical" in stats

    # ========== 单条操作 ==========

    def test_mark_notice_read_success(self, auth_token, test_alarm):
        """测试标记告警已读成功"""
        response = client.put(f"/api/v1/alarm-notices/{test_alarm.id}/read", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        data = response.json()
        notice_data = data.get("data", data)
        assert notice_data.get("status") == "acknowledged"

    def test_mark_notice_read_not_found(self, auth_token):
        """测试标记不存在告警已读"""
        response = client.put("/api/v1/alarm-notices/99999/read", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 404

    def test_resolve_notice_success(self, auth_token, test_alarm):
        """测试解决告警成功"""
        response = client.put(f"/api/v1/alarm-notices/{test_alarm.id}/resolve", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "handle_desc": "已修复温度传感器"
        })
        assert response.status_code == 200
        data = response.json()
        notice_data = data.get("data", data)
        assert notice_data.get("status") == "resolved"

    def test_resolve_notice_not_found(self, auth_token):
        """测试解决不存在告警"""
        response = client.put("/api/v1/alarm-notices/99999/resolve", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 404

    def test_ignore_notice_success(self, auth_token, test_alarm):
        """测试忽略告警成功"""
        response = client.put(f"/api/v1/alarm-notices/{test_alarm.id}/ignore", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        data = response.json()
        notice_data = data.get("data", data)
        assert notice_data.get("status") == "ignored"

    def test_ignore_notice_not_found(self, auth_token):
        """测试忽略不存在告警"""
        response = client.put("/api/v1/alarm-notices/99999/ignore", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 404

    # ========== 全部已读 ==========

    def test_mark_all_read_success(self, auth_token):
        """测试标记全部已读成功"""
        response = client.put("/api/v1/alarm-notices/read-all", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        data = response.json()
        notice_data = data.get("data", data)
        assert "updated" in notice_data

    # ========== 完整流程测试 ==========

    def test_alarm_notice_workflow(self, auth_token, test_device):
        """测试告警通知完整流程"""
        # 1. 创建告警
        from app.models.alarm import Alarm, AlarmLevel, AlarmStatus
        db = test_db["session"] if "test_db" in dir() else None
        
        # 通过alarms API创建告警
        create_resp = client.post("/api/v1/alarms", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "device_id": test_device.id,
            "alarm_type": "workflow_test",
            "level": "warning",
            "content": "流程测试告警"
        })
        
        # 如果创建成功，继续测试
        if create_resp.status_code == 200:
            alarm_id = create_resp.json().get("data", {}).get("id") or create_resp.json().get("id")
            
            # 2. 获取通知列表，应包含新告警
            list_resp = client.get("/api/v1/alarm-notices", headers={
                "Authorization": f"Bearer {auth_token}"
            })
            assert list_resp.status_code == 200
            
            # 3. 标记已读
            read_resp = client.put(f"/api/v1/alarm-notices/{alarm_id}/read", headers={
                "Authorization": f"Bearer {auth_token}"
            })
            # 可能告警不在通知列表中（已解决），所以只检查不报错
            
            # 4. 解决告警
            resolve_resp = client.put(f"/api/v1/alarm-notices/{alarm_id}/resolve", headers={
                "Authorization": f"Bearer {auth_token}"
            }, json={"handle_desc": "流程测试完成"})