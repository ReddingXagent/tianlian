#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IDOR 横向越权补防测试（卡 0ff95dca）

覆盖:
1. 巡检 Task 族端点团队作用域 — 详情/更新/删除/结果 跨团队 → 404、
   本团队 → 200、admin 全通；list_tasks 团队过滤；create_task station/plan 归属校验。
2. Webhook secret 打码 — GET 列表/详情只回打码值，POST 创建响应一次性回显原文。

Task 归属推导: task.station_id→Station.team_id，无 station 回退 plan→team。
"""
import bcrypt
import pytest

from app.models.user import User, UserRole, Team
from app.models.station import Station, StationStatus


# ─── 脚手架: 两团队 + 各自 station + engineer 用户 + admin ───

@pytest.fixture
def idor_env(client):
    """两团队（各挂一站）+ 两 engineer + token；seed 一条 B 团队计划。"""
    from app.models.inspection import InspectionPlan, PlanStatus, PlanCycle, PlanTarget
    s = client._sesh
    ta = Team(name="idor团队A", code="IDORTA")
    tb = Team(name="idor团队B", code="IDORTB")
    s.add_all([ta, tb])
    s.commit(); s.refresh(ta); s.refresh(tb)

    sta = Station(name="idor站A", code="IDOSTA", team_id=ta.id, status=StationStatus.NORMAL)
    stb = Station(name="idor站B", code="IDOSTB", team_id=tb.id, status=StationStatus.NORMAL)
    s.add_all([sta, stb])
    s.commit(); s.refresh(sta); s.refresh(stb)

    pwd = "idor123456"
    ua = User(username="idor_eng_a", real_name="A工程师", role=UserRole.ENGINEER,
              team_id=ta.id, status="active",
              password_hash=bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode())
    ub = User(username="idor_eng_b", real_name="B工程师", role=UserRole.ENGINEER,
              team_id=tb.id, status="active",
              password_hash=bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode())
    s.add_all([ua, ub])
    s.commit()

    # B 团队计划（经 API 建，服务端强制归属 B）
    r = client.post("/api/v1/inspection/plans", json={"name": "B计划"},
                    headers=_h(_login(client, "idor_eng_b", pwd)))
    assert r.status_code == 200, r.text
    plan_b = r.json()["data"]

    def _mk_task(headers, **payload):
        body = {"name": "UT任务", "total_items": 5}
        body.update(payload)
        r = client.post("/api/v1/inspection/tasks", json=body, headers=headers)
        assert r.status_code == 200, f"建任务失败: {r.status_code} {r.text}"
        return r.json()["data"]

    h_a = _h(_login(client, "idor_eng_a", pwd))
    h_b = _h(_login(client, "idor_eng_b", pwd))
    h_admin = {"Authorization": client.headers["Authorization"]}

    return {
        "teams": {"a": ta, "b": tb},
        "stations": {"a": sta, "b": stb},
        "plan_b": plan_b,
        "mk_task": _mk_task,
        "h": {"a": h_a, "b": h_b, "admin": h_admin},
    }


def _login(client, username, password):
    r = client.post("/api/v1/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["data"]["token"]


def _h(token):
    return {"Authorization": f"Bearer {token}"}


# ─── Task 族: 详情/更新/删除/结果 ───

class TestTaskCrossTeamDenied:
    """A 团队用户访问 B 团队任务 → 404（不泄露存在）"""

    def test_get_update_delete_404(self, client, idor_env):
        t = idor_env["mk_task"](idor_env["h"]["b"],
                                station_id=idor_env["stations"]["b"].id)
        ha = idor_env["h"]["a"]
        assert client.get(f"/api/v1/inspection/tasks/{t['id']}", headers=ha).status_code == 404
        assert client.put(f"/api/v1/inspection/tasks/{t['id']}",
                          json={"status": "in_progress"}, headers=ha).status_code == 404
        assert client.delete(f"/api/v1/inspection/tasks/{t['id']}", headers=ha).status_code == 404

    def test_results_404(self, client, idor_env):
        t = idor_env["mk_task"](idor_env["h"]["b"],
                                station_id=idor_env["stations"]["b"].id)
        ha = idor_env["h"]["a"]
        assert client.get(f"/api/v1/inspection/tasks/{t['id']}/results", headers=ha).status_code == 404
        r = client.post(f"/api/v1/inspection/tasks/{t['id']}/results",
                        json={"results": [{"item_name": "x"}]}, headers=ha)
        assert r.status_code == 404

    def test_plan_derived_task_404(self, client, idor_env):
        """无 station、挂 B 团队计划的任务，A 同样不可访问（plan→team 回退路径）"""
        t = idor_env["mk_task"](idor_env["h"]["b"], plan_id=idor_env["plan_b"]["id"])
        ha = idor_env["h"]["a"]
        assert client.get(f"/api/v1/inspection/tasks/{t['id']}", headers=ha).status_code == 404


class TestTaskSameTeamAllowed:
    """B 本人 + admin 全通"""

    def test_owner_ok(self, client, idor_env):
        t = idor_env["mk_task"](idor_env["h"]["b"],
                                station_id=idor_env["stations"]["b"].id)
        hb = idor_env["h"]["b"]
        assert client.get(f"/api/v1/inspection/tasks/{t['id']}", headers=hb).status_code == 200
        assert client.put(f"/api/v1/inspection/tasks/{t['id']}",
                          json={"completed_items": 1}, headers=hb).status_code == 200
        r = client.post(f"/api/v1/inspection/tasks/{t['id']}/results",
                        json={"results": [{"item_name": "温度", "item_value": "25"}]},
                        headers=hb)
        assert r.status_code == 200
        assert client.get(f"/api/v1/inspection/tasks/{t['id']}/results",
                          headers=hb).status_code == 200

    def test_admin_sees_all(self, client, idor_env):
        t = idor_env["mk_task"](idor_env["h"]["b"],
                                station_id=idor_env["stations"]["b"].id)
        hadmin = idor_env["h"]["admin"]
        assert client.get(f"/api/v1/inspection/tasks/{t['id']}", headers=hadmin).status_code == 200
        assert client.put(f"/api/v1/inspection/tasks/{t['id']}",
                          json={"completed_items": 2}, headers=hadmin).status_code == 200
        assert client.delete(f"/api/v1/inspection/tasks/{t['id']}",
                             headers=hadmin).status_code == 200


class TestTaskListScoping:
    """list_tasks 团队过滤 + admin 全见"""

    def test_list_isolated(self, client, idor_env):
        idor_env["mk_task"](idor_env["h"]["a"],
                            station_id=idor_env["stations"]["a"].id, name="A任务")
        idor_env["mk_task"](idor_env["h"]["b"],
                            station_id=idor_env["stations"]["b"].id, name="B任务")

        items_a = client.get("/api/v1/inspection/tasks",
                             headers=idor_env["h"]["a"]).json()["data"]["items"]
        assert [it["name"] for it in items_a] == ["A任务"]

        items_b = client.get("/api/v1/inspection/tasks",
                             headers=idor_env["h"]["b"]).json()["data"]["items"]
        assert [it["name"] for it in items_b] == ["B任务"]

        # admin 看全部
        total = client.get("/api/v1/inspection/tasks",
                           headers=idor_env["h"]["admin"]).json()["data"]["total"]
        assert total >= 2


class TestCreateTaskOwnership:
    """create_task 引用他 team station/plan → 404；station 不存在 → 404"""

    def test_cross_station_404(self, client, idor_env):
        r = client.post("/api/v1/inspection/tasks", json={
            "name": "越权任务", "station_id": idor_env["stations"]["b"].id,
        }, headers=idor_env["h"]["a"])
        assert r.status_code == 404

    def test_cross_plan_404(self, client, idor_env):
        r = client.post("/api/v1/inspection/tasks", json={
            "name": "越权计划任务", "plan_id": idor_env["plan_b"]["id"],
        }, headers=idor_env["h"]["a"])
        assert r.status_code == 404

    def test_nonexistent_station_404(self, client, idor_env):
        r = client.post("/api/v1/inspection/tasks", json={
            "name": "幽灵站任务", "station_id": 999999,
        }, headers=idor_env["h"]["a"])
        assert r.status_code == 404

    def test_own_station_200(self, client, idor_env):
        r = client.post("/api/v1/inspection/tasks", json={
            "name": "本站任务", "station_id": idor_env["stations"]["a"].id,
        }, headers=idor_env["h"]["a"])
        assert r.status_code == 200


# ─── Webhook secret 打码 ───

_WH_SECRET = "whsec-0ff95dca-plaintext"

def _create_webhook(client):
    r = client.post("/api/v1/webhooks", json={
        "name": "idor webhook", "url": "https://example.com/hook",
        "event_types": ["alert"], "secret": _WH_SECRET,
    })
    assert r.status_code == 200, r.text
    return r.json()["data"]


class TestWebhookSecretMasking:
    """GET 列表/详情只回打码值；创建响应一次性回显原文"""

    def test_create_returns_plaintext_once(self, client):
        d = _create_webhook(client)
        assert d["secret"] == _WH_SECRET

    def test_get_detail_masked(self, client):
        d = _create_webhook(client)
        r = client.get(f"/api/v1/webhooks/{d['id']}")
        assert r.status_code == 200
        sec = r.json()["data"]["secret"]
        assert sec != _WH_SECRET
        assert sec == "whs****text"  # 前3 + **** + 尾4

    def test_list_masked(self, client):
        _create_webhook(client)
        r = client.get("/api/v1/webhooks")
        assert r.status_code == 200
        for it in r.json()["data"]["items"]:
            assert it["secret"] != _WH_SECRET
            assert "****" in (it["secret"] or "")

    def test_short_secret_fully_masked(self, client):
        """≤8 字符 secret 全打码，不留任何原文片段"""
        r = client.post("/api/v1/webhooks", json={
            "name": "短secret", "url": "https://example.com/h2",
            "event_types": [], "secret": "abc",
        })
        assert r.status_code == 200
        wid = r.json()["data"]["id"]
        sec = client.get(f"/api/v1/webhooks/{wid}").json()["data"]["secret"]
        assert sec == "****"
