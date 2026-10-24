"""
巡检幂等缺陷修复测试 (卡 e68dc900)

覆盖:
1. _save_finding 去重: 同 team+source+related_id 未处理 finding 存在时跳过
   → 同异常连续两轮巡检只写一条
2. 储能SOC 检查用 per-device 最新值: SOC 恢复后不再产生新 finding
3. 充电功率检查用 per-device 最新值: 只报设备数, 不报遥测行数
4. task_acks_late 重投递场景 finding 写入幂等 (同任务重复执行)
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from tests.test_agent_memory import _make_device, _make_station, _make_team


def _battery_row(session, device_id, station_id, soc, minutes_ago=0):
    from app.models.telemetry_v2 import TelemetryBattery
    row = TelemetryBattery(
        device_id=device_id,
        station_id=station_id,
        battery_soc=soc,
        timestamp=datetime.now(timezone.utc) - timedelta(minutes=minutes_ago),
    )
    session.add(row)
    session.commit()
    return row


def _charger_row(session, device_id, station_id, power, minutes_ago=0):
    from app.models.telemetry_v2 import TelemetryCharger
    row = TelemetryCharger(
        device_id=device_id,
        station_id=station_id,
        charger_power=power,
        timestamp=datetime.now(timezone.utc) - timedelta(minutes=minutes_ago),
    )
    session.add(row)
    session.commit()
    return row


def _findings(session, team_id, source):
    from app.models.agent_memory import AgentMemory
    return (
        session.query(AgentMemory)
        .filter(
            AgentMemory.team_id == team_id,
            AgentMemory.source == source,
        )
        .all()
    )


class TestFindingsDedup:
    def test_same_anomaly_two_rounds_single_finding(self, test_db):
        """①同异常连续两轮巡检只写一条"""
        from app.models.device import DeviceStatus
        from app.tasks import agent_patrol

        session = test_db["session"]
        team = _make_team(session)
        st = _make_station(session, team.id)
        _make_device(
            session, st.id, sn="D-DEDUP",
            status=DeviceStatus.ONLINE,
            last_heartbeat=datetime.now(timezone.utc) - timedelta(minutes=30),
        )

        agent_patrol.patrol_maintenance.__wrapped__(team.id)
        agent_patrol.patrol_maintenance.__wrapped__(team.id)

        rows = _findings(session, team.id, "patrol:device_offline")
        assert len(rows) == 1

    def test_redelivery_idempotent(self, test_db):
        """④acks_late 重投递: 同任务重复执行不重复写 finding"""
        from app.models.device import DeviceStatus
        from app.tasks import agent_patrol

        session = test_db["session"]
        team = _make_team(session)
        st = _make_station(session, team.id)
        _make_device(
            session, st.id, sn="D-REDELIVER",
            status=DeviceStatus.ONLINE,
            last_heartbeat=datetime.now(timezone.utc) - timedelta(minutes=15),
        )

        for _ in range(3):
            agent_patrol.patrol_maintenance.__wrapped__(team.id)

        rows = _findings(session, team.id, "patrol:device_offline")
        assert len(rows) == 1

    def test_resolved_and_expired_finding_can_be_recreated(self, test_db):
        """已 resolved 且超出静默窗口的 finding 不再压制新发现"""
        from app.models.device import DeviceStatus
        from app.tasks import agent_patrol

        session = test_db["session"]
        team = _make_team(session)
        st = _make_station(session, team.id)
        _make_device(
            session, st.id, sn="D-RESOLVE",
            status=DeviceStatus.ONLINE,
            last_heartbeat=datetime.now(timezone.utc) - timedelta(minutes=20),
        )

        agent_patrol.patrol_maintenance.__wrapped__(team.id)
        rows = _findings(session, team.id, "patrol:device_offline")
        assert len(rows) == 1
        rows[0].status = "resolved"
        rows[0].created_at = datetime.now(timezone.utc) - timedelta(hours=2)
        session.commit()

        agent_patrol.patrol_maintenance.__wrapped__(team.id)
        assert len(_findings(session, team.id, "patrol:device_offline")) == 2

    def test_resolved_within_window_still_suppressed(self, test_db):
        """已 resolved 但仍在1h静默窗口内 → 继续压制 (防抖)"""
        from app.models.device import DeviceStatus
        from app.tasks import agent_patrol

        session = test_db["session"]
        team = _make_team(session)
        st = _make_station(session, team.id)
        _make_device(
            session, st.id, sn="D-RESOLVE-SOON",
            status=DeviceStatus.ONLINE,
            last_heartbeat=datetime.now(timezone.utc) - timedelta(minutes=20),
        )

        agent_patrol.patrol_maintenance.__wrapped__(team.id)
        rows = _findings(session, team.id, "patrol:device_offline")
        assert len(rows) == 1
        rows[0].status = "resolved"
        session.commit()

        agent_patrol.patrol_maintenance.__wrapped__(team.id)
        assert len(_findings(session, team.id, "patrol:device_offline")) == 1


class TestSocLatestValue:
    def test_soc_recovered_no_new_finding(self, test_db):
        """②SOC恢复后不再产生新 finding (per-device 最新值)"""
        from app.tasks import agent_patrol

        session = test_db["session"]
        team = _make_team(session)
        st = _make_station(session, team.id)
        dev = _make_device(session, st.id, sn="D-SOC-RECOVER")

        # 历史低SOC行 (旧) + 最新正常行
        _battery_row(session, dev.id, st.id, soc=5.0, minutes_ago=60)
        _battery_row(session, dev.id, st.id, soc=80.0, minutes_ago=1)

        agent_patrol.patrol_maintenance.__wrapped__(team.id)
        assert _findings(session, team.id, "patrol:battery_low_soc") == []

    def test_low_soc_reports_devices_not_rows(self, test_db):
        """③per-device 只报设备数: 同设备多条低SOC行也只一条 finding"""
        from app.tasks import agent_patrol

        session = test_db["session"]
        team = _make_team(session)
        st = _make_station(session, team.id)
        dev = _make_device(session, st.id, sn="D-SOC-LOW")

        _battery_row(session, dev.id, st.id, soc=5.0, minutes_ago=30)
        _battery_row(session, dev.id, st.id, soc=8.0, minutes_ago=1)

        result = agent_patrol.patrol_maintenance.__wrapped__(team.id)
        assert result["checks"]["battery_low_soc"] == 1
        assert len(_findings(session, team.id, "patrol:battery_low_soc")) == 1

    def test_soc_recovery_then_recheck_no_repeat(self, test_db):
        """低SOC→写一条→恢复→巡检不再写新 finding"""
        from app.tasks import agent_patrol

        session = test_db["session"]
        team = _make_team(session)
        st = _make_station(session, team.id)
        dev = _make_device(session, st.id, sn="D-SOC-CYCLE")

        _battery_row(session, dev.id, st.id, soc=4.0, minutes_ago=1)
        agent_patrol.patrol_maintenance.__wrapped__(team.id)
        assert len(_findings(session, team.id, "patrol:battery_low_soc")) == 1

        _battery_row(session, dev.id, st.id, soc=90.0, minutes_ago=0)
        agent_patrol.patrol_maintenance.__wrapped__(team.id)
        assert len(_findings(session, team.id, "patrol:battery_low_soc")) == 1


class TestChargerPowerLatestValue:
    def _seed_active_order(self, session, team, st, dev):
        from app.models.charging_order import ChargingOrder, OrderStatus
        order = ChargingOrder(
            order_no="PO-DEDUP-1",
            device_id=dev.id,
            station_id=st.id,
            order_status=OrderStatus.CHARGING,
        )
        session.add(order)
        session.commit()
        return order

    def test_zero_power_per_device_not_per_row(self, test_db):
        """③同设备多条零功率行只一条 finding"""
        from app.tasks import agent_patrol

        session = test_db["session"]
        team = _make_team(session)
        st = _make_station(session, team.id)
        dev = _make_device(session, st.id, sn="D-PWR-0")
        self._seed_active_order(session, team, st, dev)

        _charger_row(session, dev.id, st.id, power=0, minutes_ago=30)
        _charger_row(session, dev.id, st.id, power=0, minutes_ago=1)

        result = agent_patrol.patrol_maintenance.__wrapped__(team.id)
        assert result["checks"]["charger_zero_power"] == 1
        assert len(_findings(session, team.id, "patrol:charger_zero_power")) == 1

    def test_power_recovered_no_finding(self, test_db):
        """最新功率恢复为非0 → 不产生 finding"""
        from app.tasks import agent_patrol

        session = test_db["session"]
        team = _make_team(session)
        st = _make_station(session, team.id)
        dev = _make_device(session, st.id, sn="D-PWR-OK")
        self._seed_active_order(session, team, st, dev)

        _charger_row(session, dev.id, st.id, power=0, minutes_ago=30)
        _charger_row(session, dev.id, st.id, power=60.0, minutes_ago=1)

        result = agent_patrol.patrol_maintenance.__wrapped__(team.id)
        assert result["checks"]["charger_zero_power"] == 0
        assert _findings(session, team.id, "patrol:charger_zero_power") == []
