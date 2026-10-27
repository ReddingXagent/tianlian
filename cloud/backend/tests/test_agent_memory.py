"""
天链智能体 P1 — 记忆表 + 巡检任务 + 记忆服务 测试

覆盖:
- AgentMemory / AgentConversation CRUD
- agent_memory_service: save_memory / save_conversation / search_memory /
  get_findings / update_finding_status / get_conversation_history
- agent_patrol: 三类巡检 (maintenance / operations / platform) 在 mock 数据下记录 finding
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest


# ---------------------------------------------------------------------------
# 辅助: 构造 Team / Station / Device 等基础数据
# ---------------------------------------------------------------------------
def _make_team(session, name="agent-test-team"):
    from app.models.user import Team
    team = Team(name=name)
    session.add(team)
    session.commit()
    return team


def _make_station(session, team_id, code="ST-AGENT", **overrides):
    from app.models.station import Station
    payload = dict(
        name="测试站",
        code=code,
        team_id=team_id,
    )
    payload.update(overrides)
    st = Station(**payload)
    session.add(st)
    session.commit()
    return st


def _make_device(session, station_id, sn="DEV-AGENT-1", **overrides):
    from app.models.device import Device, DeviceType
    payload = dict(
        sn=sn,
        name="测试桩",
        code=sn,
        type=DeviceType.CHARGER_DC,
        station_id=station_id,
    )
    payload.update(overrides)
    dev = Device(**payload)
    session.add(dev)
    session.commit()
    return dev


# ---------------------------------------------------------------------------
# 1. 模型 CRUD
# ---------------------------------------------------------------------------
class TestAgentMemoryModel:
    """AgentMemory / AgentConversation 基础落库"""

    def test_save_and_read_memory(self, test_db):
        from app.services import agent_memory_service as svc

        team = _make_team(test_db["session"])
        mem = svc.save_memory(
            team_id=team.id,
            board="maintenance",
            category="finding",
            title="3号桩离线",
            content="设备超过10分钟无心跳",
            severity="critical",
            source="patrol:device_offline",
            related_type="device",
            related_id="123",
        )
        assert mem.id is not None
        assert mem.team_id == team.id
        assert mem.board == "maintenance"
        assert mem.category == "finding"
        assert mem.status == "open"
        assert mem.severity == "critical"
        assert mem.importance == pytest.approx(0.5)

    def test_memory_metadata_default_empty(self, test_db):
        from app.services import agent_memory_service as svc

        team = _make_team(test_db["session"])
        mem = svc.save_memory(
            team_id=team.id,
            board="operations",
            category="learning",
            title="经验",
            content="谷段充电更经济",
        )
        # meta_info 默认空 dict ({}), 不是 None
        assert mem.meta_info == {}

    def test_save_and_read_conversation(self, test_db):
        from app.services import agent_memory_service as svc

        team = _make_team(test_db["session"])
        convo = svc.save_conversation(
            team_id=team.id,
            board="maintenance",
            role="user",
            content="3号桩怎么了?",
        )
        assert convo.id is not None
        assert convo.role == "user"
        assert convo.board == "maintenance"
        assert convo.created_at is not None


# ---------------------------------------------------------------------------
# 2. 服务层: 搜索 / 查询 / 状态流转
# ---------------------------------------------------------------------------
class TestAgentMemoryService:
    def test_search_memory_ilike_keyword(self, test_db):
        from app.services import agent_memory_service as svc

        team = _make_team(test_db["session"])
        svc.save_memory(team.id, "maintenance", "finding", "3号桩离线", "心跳超时")
        svc.save_memory(team.id, "maintenance", "finding", "储能SOC低", "电池电量不足")
        svc.save_memory(team.id, "operations", "finding", "订单异常", "金额超阈")

        results = svc.search_memory(team.id, "SOC", limit=10)
        assert len(results) == 1
        assert "SOC" in results[0].title

    def test_search_memory_team_isolation(self, test_db):
        """不同 team_id 互相不可见"""
        from app.services import agent_memory_service as svc

        t1 = _make_team(test_db["session"], name="t1")
        t2 = _make_team(test_db["session"], name="t2")
        svc.save_memory(t1.id, "maintenance", "finding", "离线", "心跳超时")
        svc.save_memory(t2.id, "maintenance", "finding", "离线", "心跳超时")

        assert len(svc.search_memory(t1.id, "离线")) == 1
        assert len(svc.search_memory(t2.id, "离线")) == 1

    def test_search_memory_board_filter(self, test_db):
        from app.services import agent_memory_service as svc

        team = _make_team(test_db["session"])
        svc.save_memory(team.id, "maintenance", "finding", "离线", "x")
        svc.save_memory(team.id, "operations", "finding", "离线", "y")

        maint = svc.search_memory(team.id, "离线", board="maintenance")
        ops = svc.search_memory(team.id, "离线", board="operations")
        assert len(maint) == 1
        assert len(ops) == 1
        assert maint[0].board == "maintenance"

    def test_get_findings_default_open(self, test_db):
        from app.services import agent_memory_service as svc

        team = _make_team(test_db["session"])
        m1 = svc.save_memory(team.id, "maintenance", "finding", "f1", "c1")
        svc.save_memory(team.id, "maintenance", "finding", "f2", "c2")
        # 第三条标记 resolved, 默认查询应排除
        m3 = svc.save_memory(team.id, "maintenance", "finding", "f3", "c3")
        svc.update_finding_status(m3.id, "resolved")

        findings = svc.get_findings(team.id, status="open")
        titles = {f.title for f in findings}
        assert "f3" not in titles
        assert "f1" in titles and "f2" in titles

    def test_update_finding_status(self, test_db):
        from app.services import agent_memory_service as svc

        team = _make_team(test_db["session"])
        m = svc.save_memory(team.id, "maintenance", "finding", "f", "c")
        assert m.status == "open"

        updated = svc.update_finding_status(m.id, "acknowledged")
        assert updated.status == "acknowledged"

    def test_get_conversation_history_order(self, test_db):
        """对话历史按时间倒序 (最近在前)"""
        from app.services import agent_memory_service as svc

        team = _make_team(test_db["session"])
        svc.save_conversation(team.id, "maintenance", "user", "第一条")
        svc.save_conversation(team.id, "maintenance", "assistant", "第二条")

        history = svc.get_conversation_history(team.id, "maintenance")
        assert len(history) == 2
        # 倒序: 第二条在前
        assert history[0].content == "第二条"


# ---------------------------------------------------------------------------
# 3. 巡检任务
# ---------------------------------------------------------------------------
class TestPatrolMaintenance:
    def test_device_offline_writes_finding(self, test_db):
        """设备心跳超过10分钟且状态非 offline → 记录 finding"""
        from app.models.device import DeviceStatus
        from app.services import agent_memory_service as svc
        from app.tasks import agent_patrol

        team = _make_team(test_db["session"])
        st = _make_station(test_db["session"], team.id)
        # 心跳11分钟前, 状态仍是 online (未同步为 offline)
        _make_device(
            test_db["session"], st.id, sn="D-OFF",
            status=DeviceStatus.ONLINE,
            last_heartbeat=datetime.now(timezone.utc) - timedelta(minutes=11),
        )

        result = agent_patrol.patrol_maintenance.__wrapped__(team.id)

        assert result["findings"] >= 1
        findings = svc.get_findings(team.id, board="maintenance")
        assert any("离线" in f.title or "offline" in (f.source or "") for f in findings)

    def test_online_device_no_finding(self, test_db):
        """正常在线设备不产生 finding"""
        from app.models.device import DeviceStatus
        from app.tasks import agent_patrol

        team = _make_team(test_db["session"])
        st = _make_station(test_db["session"], team.id)
        _make_device(
            test_db["session"], st.id, sn="D-OK",
            status=DeviceStatus.ONLINE,
            last_heartbeat=datetime.now(timezone.utc) - timedelta(minutes=1),
        )

        result = agent_patrol.patrol_maintenance.__wrapped__(team.id)
        assert result["findings"] == 0


class TestPatrolOperations:
    def test_low_balance_enterprise_finding(self, test_db):
        """企业余额 < 100 → 记录 finding"""
        from app.models.enterprise import Enterprise, EnterpriseStatus
        from app.services import agent_memory_service as svc
        from app.tasks import agent_patrol

        team = _make_team(test_db["session"])
        test_db["session"].add(Enterprise(
            name="低余额车队",
            code="ENT-LOW",
            balance=Decimal("50.00"),
            owner_team_id=team.id,
            status=EnterpriseStatus.ACTIVE,
        ))
        test_db["session"].commit()

        result = agent_patrol.patrol_operations.__wrapped__(team.id)
        assert result["findings"] >= 1
        findings = svc.get_findings(team.id, board="operations")
        assert any("余额" in f.title for f in findings)


class TestPatrolPlatform:
    def test_platform_health_all_mocked(self, test_db, monkeypatch):
        """平台巡检: API/磁盘/Celery 全 mock, 不应抛异常, 返回结构正确"""
        from app.tasks import agent_patrol

        # 平台巡检需要至少一个 team 写入 finding (board=admin)
        _make_team(test_db["session"])

        # mock requests.get (API 健康)
        import app.tasks.agent_patrol as ap

        class _FakeResp:
            status_code = 200
            def json(self):
                return {"status": "healthy"}

        monkeypatch.setattr(ap.requests, "get", lambda *a, **k: _FakeResp())

        # mock shutil.disk_usage
        monkeypatch.setattr(ap.shutil, "disk_usage", lambda _p: type("U", (), {"total": 100, "used": 50, "free": 50})())

        # mock celery inspect (无 active 任务)
        class _FakeInspect:
            def active(self):
                return {}
        class _FakeControl:
            def inspect(self):
                return _FakeInspect()

        # patrol_platform 不按租户, 但 finding 需要一个 team_id 落库
        result = agent_patrol.patrol_platform.__wrapped__()
        assert "findings" in result
        assert "checks" in result


# ---------------------------------------------------------------------------
# 4. *_all 遍历器
# ---------------------------------------------------------------------------
class TestPatrolAllDispatchers:
    def test_maintenance_all_iterates_teams(self, test_db, monkeypatch):
        """maintenance_all 遍历活跃 Team, 对每个调用单租户巡检"""
        from app.tasks import agent_patrol

        t1 = _make_team(test_db["session"], name="all-t1")
        t2 = _make_team(test_db["session"], name="all-t2")

        called = []

        def _fake_single(team_id):
            called.append(team_id)
            return {"findings": 0, "checks": {}}

        # maintenance_all 内部通过模块级 patrol_maintenance 单租户函数调用,
        # 直接 patch 该函数对象即可拦截, 无需走 celery worker。
        monkeypatch.setattr(agent_patrol, "_patrol_maintenance_single", _fake_single)

        result = agent_patrol.patrol_maintenance_all.__wrapped__()

        assert set(called) == {t1.id, t2.id}
        assert result["total_teams"] == 2
        assert result["total_findings"] == 0
