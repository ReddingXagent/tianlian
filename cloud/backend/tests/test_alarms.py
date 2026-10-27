"""
告警 API 测试
覆盖：告警 CRUD / 状态流转(ack/resolve/ignore) / 过滤查询 / 团队隔离 /
      级别分类 / 通知记录 / 规则 CRUD / 权限边界 / 统计。
"""
import pytest
from fastapi.testclient import TestClient


def _get_token(client, username="admin", password="admin123"):
    """获取认证 token；测试环境 login 应稳定可用，失败直接 fail 以暴露真实问题。"""
    resp = client.post("/api/v1/auth/login", data={
        "username": username,
        "password": password,
    })
    assert resp.status_code == 200, f"login 失败 status={resp.status_code} body={resp.text}"
    data = resp.json()
    token = (data.get("data", {}).get("token") or data.get("token")
             or data.get("data", {}).get("access_token") or data.get("access_token"))
    assert token, f"login 响应未含 token: {data}"
    return token


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def _create_alarm(client, token, device_id, **overrides):
    """通过 POST /alarms 创建告警，返回 data。"""
    payload = {
        "device_id": device_id,
        "alarm_type": "unit_test",
        "level": "warning",
        "content": "UT 触发告警",
    }
    payload.update(overrides)
    resp = client.post("/api/v1/alarms", json=payload, headers=_h(token))
    assert resp.status_code == 200, f"create_alarm 失败: {resp.status_code} {resp.text}"
    return resp.json()["data"]


# ═══════════════════════════════════════════════
# 团队隔离脚手架：两团队 + 站点 + 设备 + 告警 + 工程师 token
# ═══════════════════════════════════════════════

@pytest.fixture
def alarm_team_world(client):
    """构造两团队世界，供告警团队隔离测试。

    team_a / team_b 各持一个站点、一台设备、一条告警（station_id 已回填）；
    各配一名 ENGINEER 用户 + token。admin 由 client fixture 默认注入。
    """
    from app.models.user import User, UserRole, Team
    from app.models.station import Station, StationStatus
    from app.models.device import Device, DeviceType, DeviceStatus
    from app.models.alarm import Alarm, AlarmLevel, AlarmStatus
    import bcrypt

    s = client._sesh
    ta = Team(name="告警团队A", code="ALRMTA")
    tb = Team(name="告警团队B", code="ALRMTB")
    s.add_all([ta, tb])
    s.commit()
    s.refresh(ta)
    s.refresh(tb)

    sta_a = Station(name="告警站A", code="ALSTA", address="A", status=StationStatus.NORMAL, team_id=ta.id)
    sta_b = Station(name="告警站B", code="ALSTB", address="B", status=StationStatus.NORMAL, team_id=tb.id)
    s.add_all([sta_a, sta_b])
    s.commit()
    s.refresh(sta_a)
    s.refresh(sta_b)

    dev_a = Device(sn="AL-A-01", name="A设备", code="ALDEVA", type=DeviceType.PV_INVERTER,
                   status=DeviceStatus.ONLINE, station_id=sta_a.id, rated_power=10.0)
    dev_b = Device(sn="AL-B-01", name="B设备", code="ALDEV", type=DeviceType.PV_INVERTER,
                   status=DeviceStatus.ONLINE, station_id=sta_b.id, rated_power=10.0)
    s.add_all([dev_a, dev_b])
    s.commit()
    s.refresh(dev_a)
    s.refresh(dev_b)

    alarm_a = Alarm(device_id=dev_a.id, station_id=sta_a.id, alarm_type="over_temp",
                    level=AlarmLevel.WARNING, content="A团队告警", status=AlarmStatus.ACTIVE)
    alarm_b = Alarm(device_id=dev_b.id, station_id=sta_b.id, alarm_type="comm_fault",
                    level=AlarmLevel.CRITICAL, content="B团队告警", status=AlarmStatus.ACTIVE)
    s.add_all([alarm_a, alarm_b])
    s.commit()
    s.refresh(alarm_a)
    s.refresh(alarm_b)

    pwd = "alrm123456"
    eng_a = User(
        username="alarm_eng_a", real_name="A工程师", role=UserRole.ENGINEER,
        team_id=ta.id, status="active",
        password_hash=bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode(),
    )
    eng_b = User(
        username="alarm_eng_b", real_name="B工程师", role=UserRole.ENGINEER,
        team_id=tb.id, status="active",
        password_hash=bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode(),
    )
    s.add_all([eng_a, eng_b])
    s.commit()

    def _tok(username):
        r = client.post("/api/v1/auth/login", data={"username": username, "password": pwd})
        assert r.status_code == 200, f"登录失败 {username}: {r.text}"
        return r.json()["data"]["token"]

    return {
        "teams": {"a": ta, "b": tb},
        "stations": {"a": sta_a, "b": sta_b},
        "devices": {"a": dev_a, "b": dev_b},
        "alarms": {"a": alarm_a, "b": alarm_b},
        "tokens": {"a": _tok("alarm_eng_a"), "b": _tok("alarm_eng_b")},
    }


# ═══════════════════════════════════════════════
# 列表查询 + 过滤
# ═══════════════════════════════════════════════

class TestAlarmList:
    """告警列表查询测试"""

    def test_list_alarms_authenticated(self, client, seed_users, seed_devices, seed_alarms):
        """认证用户可以查看告警列表"""
        token = _get_token(client)
        response = client.get("/api/v1/alarms", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200, f"Failed: {response.text}"

    def test_list_alarms_unauthenticated(self, anon_client):
        """未认证用户无法查看告警"""
        response = anon_client.get("/api/v1/alarms")
        assert response.status_code in (401, 403)

    def test_filter_alarms_by_level(self, client, seed_users, seed_devices, seed_alarms):
        """按级别过滤告警 — 仅返回 critical 级"""
        token = _get_token(client)
        response = client.get("/api/v1/alarms?level=critical", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        items = response.json()["data"]["items"]
        assert items, "应至少有一条 critical 告警"
        assert all(it["level"] == "critical" for it in items)

    def test_filter_alarms_by_status(self, client, seed_users, seed_devices, seed_alarms):
        """按状态过滤告警 — 仅返回 active"""
        token = _get_token(client)
        response = client.get("/api/v1/alarms?status=active", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        items = response.json()["data"]["items"]
        assert items, "应至少有一条 active 告警"
        assert all(it["status"] == "active" for it in items)

    def test_filter_alarms_by_device(self, client, seed_users, seed_devices, seed_alarms):
        """按设备过滤告警 — 仅返回该设备告警"""
        token = _get_token(client)
        device_id = seed_devices["inv001"].id
        response = client.get(f"/api/v1/alarms?device_id={device_id}", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        items = response.json()["data"]["items"]
        assert items, "inv001 应有告警"
        assert all(it["device_id"] == device_id for it in items)

    def test_filter_alarms_by_station(self, client, seed_users, seed_devices, seed_alarms):
        """按站点过滤告警"""
        token = _get_token(client)
        station_id = seed_devices["inv001"].station_id
        response = client.get(f"/api/v1/alarms?station_id={station_id}", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        items = response.json()["data"]["items"]
        assert all(it["station_id"] == station_id for it in items)

    def test_filter_alarms_by_rule(self, client, seed_users, seed_devices, seed_alarms):
        """按 rule_id 过滤告警 — 无匹配返回空列表"""
        token = _get_token(client)
        response = client.get("/api/v1/alarms?rule_id=99999", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        assert response.json()["data"]["items"] == []

    def test_list_alarms_pagination(self, client, seed_users, seed_devices, seed_alarms):
        """分页结构 — page/page_size/total 字段齐全"""
        token = _get_token(client)
        response = client.get("/api/v1/alarms?page=1&page_size=2", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["page"] == 1
        assert data["page_size"] == 2
        assert len(data["items"]) <= 2


# ═══════════════════════════════════════════════
# 详情
# ═══════════════════════════════════════════════

class TestAlarmDetail:
    """告警详情测试"""

    def test_get_alarm_by_id(self, client, seed_users, seed_devices, seed_alarms):
        """获取单个告警详情"""
        token = _get_token(client)
        alarm_id = seed_alarms["over_temp"].id
        response = client.get(f"/api/v1/alarms/{alarm_id}", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["id"] == alarm_id
        assert data["alarm_type"] == "over_temp"

    def test_get_nonexistent_alarm(self, client, seed_users, seed_devices, seed_alarms):
        """查询不存在的告警 → 404"""
        token = _get_token(client)
        response = client.get("/api/v1/alarms/99999", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 404


# ═══════════════════════════════════════════════
# 状态流转：ack / resolve / ignore
# ═══════════════════════════════════════════════

class TestAlarmAcknowledge:
    """告警确认 / 解决 / 忽略 — 状态流转"""

    def test_acknowledge_alarm(self, client, seed_users, seed_devices, seed_alarms):
        """确认告警 — status→acknowledged, handled_at 回填"""
        token = _get_token(client)
        alarm_id = seed_alarms["over_temp"].id
        response = client.put(f"/api/v1/alarms/{alarm_id}/ack", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["status"] == "acknowledged"
        assert data["handled_at"] is not None

    def test_acknowledge_nonexistent_alarm(self, client, seed_users, seed_devices, seed_alarms):
        """确认不存在的告警 → 404"""
        token = _get_token(client)
        response = client.put("/api/v1/alarms/99999/ack", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 404

    def test_acknowledge_alarm_viewer_forbidden(self, client, seed_users, seed_devices, seed_alarms):
        """只读用户不能确认告警 — 缺 alarm:process → 403"""
        token = _get_token(client, "viewer1", "view123")
        alarm_id = seed_alarms["over_temp"].id
        response = client.put(f"/api/v1/alarms/{alarm_id}/ack", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 403

    def test_resolve_alarm(self, client, seed_users, seed_devices, seed_alarms):
        """解决告警 — status→resolved, cleared_at 回填"""
        token = _get_token(client)
        alarm_id = seed_alarms["over_temp"].id
        response = client.put(f"/api/v1/alarms/{alarm_id}/resolve", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["status"] == "resolved"
        assert data["cleared_at"] is not None

    def test_resolve_nonexistent_alarm(self, client, seed_users, seed_devices, seed_alarms):
        """解决不存在的告警 → 404"""
        token = _get_token(client)
        response = client.put("/api/v1/alarms/99999/resolve", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 404

    def test_resolve_alarm_viewer_forbidden(self, client, seed_users, seed_devices, seed_alarms):
        """只读用户不能解决告警 → 403"""
        token = _get_token(client, "viewer1", "view123")
        alarm_id = seed_alarms["over_temp"].id
        response = client.put(f"/api/v1/alarms/{alarm_id}/resolve", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 403

    def test_ignore_alarm(self, client, seed_users, seed_devices, seed_alarms):
        """忽略告警 — status→ignored"""
        token = _get_token(client)
        alarm_id = seed_alarms["comm_fault"].id
        response = client.put(f"/api/v1/alarms/{alarm_id}/ignore", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200, response.text
        assert response.json()["data"]["status"] == "ignored"


# ═══════════════════════════════════════════════
# 创建 / 删除 / 级别分类
# ═══════════════════════════════════════════════

class TestAlarmCreateDelete:
    """告警创建 / 删除 / 级别分类"""

    def test_create_alarm_success(self, client, seed_users, seed_devices):
        """创建告警 — 返回告警且可在列表查到"""
        token = _get_token(client)
        dev_id = seed_devices["inv001"].id
        data = _create_alarm(client, token, dev_id, content="UT新建告警", level="critical")
        assert data["id"] > 0
        assert data["status"] == "active"
        assert data["level"] == "critical"
        # 列表可查到
        resp = client.get(f"/api/v1/alarms?device_id={dev_id}", headers=_h(token))
        ids = [it["id"] for it in resp.json()["data"]["items"]]
        assert data["id"] in ids

    def test_create_alarm_inherits_station(self, client, seed_users, seed_devices):
        """创建告警 — station_id 由 device 自动回填"""
        token = _get_token(client)
        dev = seed_devices["inv001"]
        data = _create_alarm(client, token, dev.id)
        assert data["station_id"] == dev.station_id

    def test_create_alarm_level_classification(self, client, seed_users, seed_devices):
        """级别分类 — info / warning / critical 均可创建并原样返回"""
        token = _get_token(client)
        dev_id = seed_devices["inv001"].id
        for lvl in ("info", "warning", "critical", "fatal"):
            data = _create_alarm(client, token, dev_id, level=lvl, content=f"级别{lvl}")
            assert data["level"] == lvl, f"级别 {lvl} 未正确分类"

    def test_simulate_alarm(self, client, seed_users, seed_devices):
        """模拟告警 — POST /simulate 写入 DB"""
        token = _get_token(client)
        dev_id = seed_devices["inv001"].id
        resp = client.post("/api/v1/alarms/simulate", json={
            "device_id": str(dev_id), "alarm_type": "sim", "message": "模拟", "level": "warning",
        }, headers=_h(token))
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["device_id"] == dev_id
        assert data["content"] == "模拟"

    def test_delete_alarm(self, client, seed_users, seed_devices, seed_alarms):
        """删除告警 — 删除后 GET 404"""
        token = _get_token(client)
        alarm_id = seed_alarms["emergency"].id
        resp = client.delete(f"/api/v1/alarms/{alarm_id}", headers=_h(token))
        assert resp.status_code == 200, resp.text
        # 删除后查不到
        assert client.get(f"/api/v1/alarms/{alarm_id}", headers=_h(token)).status_code == 404

    def test_delete_nonexistent_alarm(self, client, seed_users, seed_devices, seed_alarms):
        """删除不存在告警 → 404"""
        token = _get_token(client)
        resp = client.delete("/api/v1/alarms/99999", headers=_h(token))
        assert resp.status_code == 404

    def test_delete_alarm_viewer_forbidden(self, client, seed_users, seed_devices, seed_alarms):
        """只读用户不能删除告警 — 缺 alarm:delete → 403"""
        token = _get_token(client, "viewer1", "view123")
        alarm_id = seed_alarms["over_temp"].id
        resp = client.delete(f"/api/v1/alarms/{alarm_id}", headers=_h(token))
        assert resp.status_code == 403

    def test_engineer_cannot_delete_alarm(self, client, seed_users, seed_devices, seed_alarms):
        """工程师无 alarm:delete 权限 → 403（仅 admin/super_admin 可删）"""
        token = _get_token(client, "engineer1", "eng123")
        alarm_id = seed_alarms["over_temp"].id
        resp = client.delete(f"/api/v1/alarms/{alarm_id}", headers=_h(token))
        assert resp.status_code == 403


# ═══════════════════════════════════════════════
# 通知记录
# ═══════════════════════════════════════════════

class TestAlarmNotifications:
    """告警通知发送记录"""

    def test_list_alarm_notifications_empty(self, client, seed_users, seed_devices, seed_alarms):
        """告警通知列表 — 无记录时返回空数组"""
        token = _get_token(client)
        alarm_id = seed_alarms["over_temp"].id
        resp = client.get(f"/api/v1/alarms/{alarm_id}/notifications", headers=_h(token))
        assert resp.status_code == 200
        assert isinstance(resp.json()["data"], list)

    def test_list_alarm_notifications_with_record(self, client, seed_users, seed_devices, seed_alarms):
        """告警通知列表 — 种子一条记录后可查"""
        from app.models.alarm_notification import AlarmNotification
        s = client._sesh
        alarm_id = seed_alarms["over_temp"].id
        s.add(AlarmNotification(
            alarm_id=alarm_id, channel="sms", recipient="13800000000",
            status="sent", result="ok",
        ))
        s.commit()

        token = _get_token(client)
        resp = client.get(f"/api/v1/alarms/{alarm_id}/notifications", headers=_h(token))
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["channel"] == "sms"
        assert data[0]["recipient"] == "13800000000"

    def test_list_notifications_nonexistent_alarm(self, client, seed_users, seed_devices, seed_alarms):
        """不存在告警的通知列表 → 404"""
        token = _get_token(client)
        resp = client.get("/api/v1/alarms/99999/notifications", headers=_h(token))
        assert resp.status_code == 404


# ═══════════════════════════════════════════════
# 统计
# ═══════════════════════════════════════════════

class TestAlarmStats:
    """告警统计测试"""

    def test_alarm_stats(self, client, seed_users, seed_devices, seed_alarms):
        """告警统计信息 — 结构完整"""
        token = _get_token(client)
        response = client.get("/api/v1/alarms/stats/summary", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        data = response.json()["data"]
        for key in ("by_status", "by_level", "today_total", "active", "total"):
            assert key in data, f"统计缺字段 {key}"
        # seed 至少 3 条
        assert data["total"] >= 3
        assert sum(data["by_status"].values()) >= 3
        assert sum(data["by_level"].values()) >= 3

    def test_alarm_stats_level_counts(self, client, seed_users, seed_devices, seed_alarms):
        """统计 — by_level 含 critical 计数（seed 有 2 条 critical）"""
        token = _get_token(client)
        resp = client.get("/api/v1/alarms/stats/summary", headers=_h(token))
        by_level = resp.json()["data"]["by_level"]
        assert by_level.get("critical", 0) >= 2

    def test_today_total_uses_biz_today(self, client, seed_devices, monkeypatch):
        """凌晨窗口业务日侧统一: today_total 按业务今天统计 (卡 48bc65fe)。

        Alarm.created_at 为 DB server_default func.now() (云端 UTC 容器=UTC),
        func.date(created_at) 取 UTC 日。本测试把一条告警 created_at 置为业务今天
        (func.date=业务今天), 断言 today_total 计入 —— 证明 date.today() 已切换为
        today_in_biz_tz(); 旧 date.today()=UTC 昨天 → func.date(业务今天)!=UTC 昨天 → 漏统计。

        已知局限 (本卡范围外, 仅统一业务日侧): 凌晨窗口上海 00:00-08:00 创建的告警
        created_at(UTC)=业务昨天, func.date 比较侧未转业务日 → today_count 仍会漏统计该窗口;
        彻底修复需 DB 层时区转换 (跨库兼容性)。
        """
        from datetime import datetime, date as _date
        from sqlalchemy import update
        from app.api.v1 import alarms as alarms_mod
        from app.models.alarm import Alarm, AlarmLevel, AlarmStatus

        biz_today = _date(2026, 8, 7)
        utc_today = _date(2026, 8, 6)
        s = client._sesh
        dev = seed_devices["inv001"]
        alarm = Alarm(
            device_id=dev.id, station_id=dev.station_id,
            alarm_type="tz_probe", level=AlarmLevel.WARNING,
            content="时区探针", status=AlarmStatus.ACTIVE,
        )
        s.add(alarm)
        s.commit()
        # created_at 置为业务今天 (func.date(created_at) = 业务今天)
        s.execute(update(Alarm).where(Alarm.id == alarm.id)
                  .values(created_at=datetime.combine(biz_today, datetime.min.time())))
        s.commit()

        monkeypatch.setattr(alarms_mod, "today_in_biz_tz", lambda: biz_today, raising=False)

        class _FrozenDate(_date):
            @classmethod
            def today(cls):
                return utc_today
        monkeypatch.setattr(alarms_mod, "date", _FrozenDate, raising=False)

        token = _get_token(client)
        r = client.get("/api/v1/alarms/stats/summary", headers=_h(token))
        assert r.status_code == 200, r.text
        assert r.json()["data"]["today_total"] >= 1


# ═══════════════════════════════════════════════
# 团队隔离
# ═══════════════════════════════════════════════

class TestAlarmTeamIsolation:
    """告警团队隔离（任务卡 ed509541）"""

    def test_non_admin_list_only_own_team(self, client, alarm_team_world):
        """团队级用户仅见本团队告警"""
        ta = alarm_team_world["teams"]["a"]
        h = _h(alarm_team_world["tokens"]["a"])
        resp = client.get("/api/v1/alarms", headers=h)
        assert resp.status_code == 200
        items = resp.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["id"] == alarm_team_world["alarms"]["a"].id
        assert items[0]["station_id"] == alarm_team_world["stations"]["a"].id

    def test_admin_sees_all_teams(self, client, alarm_team_world):
        """admin 跨团队可见全部告警"""
        # client 默认 admin token
        resp = client.get("/api/v1/alarms")
        assert resp.status_code == 200
        ids = {it["id"] for it in resp.json()["data"]["items"]}
        assert alarm_team_world["alarms"]["a"].id in ids
        assert alarm_team_world["alarms"]["b"].id in ids

    def test_non_admin_create_other_team_device_forbidden(self, client, alarm_team_world):
        """团队级用户为他人团队设备创建告警 → 404"""
        dev_b = alarm_team_world["devices"]["b"]
        h = _h(alarm_team_world["tokens"]["a"])
        resp = client.post("/api/v1/alarms", json={
            "device_id": dev_b.id, "alarm_type": "x", "level": "warning", "content": "越权",
        }, headers=h)
        assert resp.status_code == 404

    def test_non_admin_create_own_team_device_ok(self, client, alarm_team_world):
        """团队级用户为本团队设备创建告警 → 200"""
        dev_a = alarm_team_world["devices"]["a"]
        h = _h(alarm_team_world["tokens"]["a"])
        resp = client.post("/api/v1/alarms", json={
            "device_id": dev_a.id, "alarm_type": "x", "level": "warning", "content": "本队",
        }, headers=h)
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["station_id"] == alarm_team_world["stations"]["a"].id

    def test_non_admin_get_other_team_alarm_404(self, client, alarm_team_world):
        """团队A访问团队B告警详情 → 404"""
        alarm_b_id = alarm_team_world["alarms"]["b"].id
        h = _h(alarm_team_world["tokens"]["a"])
        assert client.get(f"/api/v1/alarms/{alarm_b_id}", headers=h).status_code == 404

    def test_non_admin_ack_other_team_alarm_404(self, client, alarm_team_world):
        """团队A确认团队B告警 → 404（不泄露存在）"""
        alarm_b_id = alarm_team_world["alarms"]["b"].id
        h = _h(alarm_team_world["tokens"]["a"])
        assert client.put(f"/api/v1/alarms/{alarm_b_id}/ack", headers=h).status_code == 404

    def test_non_admin_can_ack_own_team_alarm(self, client, alarm_team_world):
        """工程师可确认本团队告警 → acknowledged"""
        alarm_a_id = alarm_team_world["alarms"]["a"].id
        h = _h(alarm_team_world["tokens"]["a"])
        resp = client.put(f"/api/v1/alarms/{alarm_a_id}/ack", headers=h)
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["status"] == "acknowledged"


# ═══════════════════════════════════════════════
# 告警规则 CRUD
# ═══════════════════════════════════════════════

class TestAlarmRules:
    """告警规则 CRUD + 切换"""

    def _create(self, client, name="UT规则"):
        token = _get_token(client)
        resp = client.post("/api/v1/alarms/rules", json={
            "name": name, "metric": "temperature", "operator": ">", "threshold": 80.0,
            "level": "critical", "enabled": True,
        }, headers=_h(token))
        assert resp.status_code == 200, resp.text
        return resp.json()["data"], token

    def test_create_rule(self, client, seed_users):
        """创建规则 — 字段回写"""
        data, _ = self._create(client)
        assert data["id"] > 0
        assert data["metric"] == "temperature"
        assert data["operator"] == ">"
        assert data["level"] == "critical"
        assert data["enabled"] is True

    def test_list_and_get_rule(self, client, seed_users):
        """列表 + 详情"""
        created, token = self._create(client, name="列表规则")
        resp = client.get("/api/v1/alarms/rules", headers=_h(token))
        assert resp.status_code == 200
        ids = [r["id"] for r in resp.json()["data"]["items"]]
        assert created["id"] in ids

        resp = client.get(f"/api/v1/alarms/rules/{created['id']}", headers=_h(token))
        assert resp.status_code == 200
        assert resp.json()["data"]["name"] == "列表规则"

    def test_get_nonexistent_rule_404(self, client, seed_users):
        """获取不存在规则 → 404"""
        token = _get_token(client)
        assert client.get("/api/v1/alarms/rules/99999", headers=_h(token)).status_code == 404

    def test_update_rule(self, client, seed_users):
        """更新规则 — threshold/level 落库"""
        created, token = self._create(client)
        resp = client.put(f"/api/v1/alarms/rules/{created['id']}", json={
            "threshold": 95.5, "level": "fatal",
        }, headers=_h(token))
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["threshold"] == 95.5
        assert data["level"] == "fatal"

    def test_update_nonexistent_rule_404(self, client, seed_users):
        """更新不存在规则 → 404"""
        token = _get_token(client)
        resp = client.put("/api/v1/alarms/rules/99999", json={"threshold": 1.0}, headers=_h(token))
        assert resp.status_code == 404

    def test_toggle_rule(self, client, seed_users):
        """启用/禁用切换 — enabled 翻转"""
        created, token = self._create(client)
        # require_permission("alarm:process"); admin 通过
        resp = client.put(f"/api/v1/alarms/rules/{created['id']}/toggle", headers=_h(token))
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["enabled"] is False
        # 再切回
        resp = client.put(f"/api/v1/alarms/rules/{created['id']}/toggle", headers=_h(token))
        assert resp.json()["data"]["enabled"] is True

    def test_delete_rule(self, client, seed_users):
        """删除规则 — 删除后 GET 404"""
        created, token = self._create(client)
        resp = client.delete(f"/api/v1/alarms/rules/{created['id']}", headers=_h(token))
        assert resp.status_code == 200, resp.text
        assert client.get(f"/api/v1/alarms/rules/{created['id']}", headers=_h(token)).status_code == 404

    def test_delete_nonexistent_rule_404(self, client, seed_users):
        """删除不存在规则 → 404"""
        token = _get_token(client)
        assert client.delete("/api/v1/alarms/rules/99999", headers=_h(token)).status_code == 404

    def test_list_rules_filter_enabled(self, client, seed_users):
        """规则列表按 enabled 过滤"""
        data, token = self._create(client, name="过滤规则")
        # 禁用它
        client.put(f"/api/v1/alarms/rules/{data['id']}/toggle", headers=_h(token))
        resp = client.get("/api/v1/alarms/rules?enabled=false", headers=_h(token))
        assert resp.status_code == 200
        ids = [r["id"] for r in resp.json()["data"]["items"]]
        assert data["id"] in ids


# ========== 审计归属 (卡 3dd8954e) ==========

def _latest_audit(s, module, action, target_id):
    from app.models.audit_log import AuditLog
    return (s.query(AuditLog)
            .filter(AuditLog.module == module, AuditLog.action == action,
                    AuditLog.target_id == str(target_id))
            .order_by(AuditLog.id.desc()).first())


def test_alarm_rule_audit_attribution_card3dd8954e(client, seed_users):
    """规则 create/delete 审计归属真实操作用户 (卡 3dd8954e, 修 user_id=0 硬编码)"""
    import app.core.database as _dbmod
    from app.models.user import User
    s = _dbmod.SessionLocal()
    try:
        admin = s.query(User).filter(User.username == "admin").first()
        assert admin is not None and admin.id != 0
        token = _get_token(client)

        resp = client.post("/api/v1/alarms/rules", json={
            "name": "审计归属规则", "metric": "temperature", "operator": ">",
            "threshold": 80.0, "level": "critical", "enabled": True,
        }, headers=_h(token))
        assert resp.status_code == 200, resp.text
        rule_id = resp.json()["data"]["id"]

        log = _latest_audit(s, "alarms", "create", rule_id)
        assert log is not None, "规则创建应产生审计记录"
        assert log.user_id == admin.id, f"审计归属错误: user_id={log.user_id} 期望 {admin.id}"
        assert log.username == admin.username

        resp = client.delete(f"/api/v1/alarms/rules/{rule_id}", headers=_h(token))
        assert resp.status_code == 200
        log = _latest_audit(s, "alarms", "delete", rule_id)
        assert log is not None, "规则删除应产生审计记录"
        assert log.user_id == admin.id, f"审计归属错误: user_id={log.user_id} 期望 {admin.id}"
        assert log.username == admin.username
    finally:
        s.close()


# ========== 审计可达性 (卡 eb0e1afd) ==========

def test_delete_alarm_audit_persisted_card_eb0e1afd(client, seed_users, seed_devices):
    """删除告警审计落库 (卡 eb0e1afd, 修 delete_alarm return 后死代码)"""
    import app.core.database as _dbmod
    from app.models.user import User
    s = _dbmod.SessionLocal()
    try:
        admin = s.query(User).filter(User.username == "admin").first()
        assert admin is not None and admin.id != 0
        token = _get_token(client)

        data = _create_alarm(client, token, seed_devices["inv001"].id,
                             content="eb0e1afd审计删除告警")
        alarm_id = data["id"]

        resp = client.delete(f"/api/v1/alarms/{alarm_id}", headers=_h(token))
        assert resp.status_code == 200, resp.text

        log = _latest_audit(s, "alarms", "delete", alarm_id)
        assert log is not None, \
            f"删除告警审计未落库: alarm_id={alarm_id} (return后死代码, 敏感操作零审计)"
        assert log.user_id == admin.id, f"审计归属错误: user_id={log.user_id} 期望 {admin.id}"
        assert log.username == admin.username
        # desc 区分同 id 撞号的规则删除审计 (ec4508cf 教训: 各测试独立 DB 下 id 都从 1 起)
        assert log.target_desc and "删除告警" in log.target_desc, \
            f"审计记录撞号误匹配: target_desc={log.target_desc!r} 期望含 '删除告警'"
    finally:
        s.close()
