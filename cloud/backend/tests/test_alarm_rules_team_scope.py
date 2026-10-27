#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
告警规则 CRUD + rule-logs team scope 隔离测试 — 卡 960406a8

修复前 alarm_rules.py 与 alarms.py /rules* 端点零 team 过滤零归属校验,
团队级用户(engineer 持 alarm:process)可读全平台规则/建全平台规则/
删改他队规则; /rule-logs 裸查询泄露跨团队触发日志。修复后:
- 读: 非 admin 可见平台级(空 station_ids) + 与本 team 站点有交集的规则;
- 写: 非 admin 禁平台级规则(空 station_ids → 403), 他队站点 → 404,
  目标规则站点须全部 ⊆ 本 team(平台级/他队规则 → 404);
- rule-logs: 非 admin 经 Station.team_id 过滤;
- admin 全量豁免。

范式参考 test_fleet_v2g_records_isolation.py。
"""
import bcrypt
import pytest


@pytest.fixture
def rule_scope_pair(client):
    """两团队 + 两 engineer(持 alarm:process) + 各团队一站点 + 三条规则(平台级/A队/B队) + 各队一条 rule-log。"""
    from app.models.user import User, UserRole, Team
    from app.models.station import Station, StationStatus
    from app.models.alarm import AlarmRule, AlarmLevel, AlarmRuleLog
    s = client._sesh

    out = {"teams": {}, "users": {}, "stations": {}, "rules": {}, "logs": {}, "tokens": {}}
    pwd = "rule_scope_960406a8"
    for key in ("a", "b"):
        t = Team(name=f"规则隔离团队{key.upper()}", code=f"RSCOPE{key.upper()}")
        s.add(t)
        s.commit()
        s.refresh(t)
        out["teams"][key] = t

        u = User(
            username=f"rule_scope_eng_{key}", real_name=f"{key}工程师",
            role=UserRole.ENGINEER, team_id=t.id, status="active",
            password_hash=bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode(),
        )
        s.add(u)
        s.commit()

        st = Station(
            name=f"规则隔离站{key.upper()}", code=f"STA_RSCOPE_{key.upper()}",
            address="隔离测试地址", status=StationStatus.NORMAL, team_id=t.id,
        )
        s.add(st)
        s.commit()
        s.refresh(st)
        out["stations"][key] = st

    # 平台级规则(空 station_ids) + 各队专属规则
    platform_rule = AlarmRule(
        name="平台级规则", metric="battery_temperature", operator=">",
        threshold=60.0, level=AlarmLevel.WARNING, station_ids=None,
    )
    rule_a = AlarmRule(
        name="A队规则", metric="grid_voltage_a", operator=">",
        threshold=260.0, level=AlarmLevel.CRITICAL,
        station_ids=[out["stations"]["a"].id],
    )
    rule_b = AlarmRule(
        name="B队规则", metric="soc", operator="<",
        threshold=20.0, level=AlarmLevel.WARNING,
        station_ids=[out["stations"]["b"].id],
    )
    s.add_all([platform_rule, rule_a, rule_b])
    s.commit()
    for r in (platform_rule, rule_a, rule_b):
        s.refresh(r)
    out["rules"] = {"platform": platform_rule, "a": rule_a, "b": rule_b}

    log_a = AlarmRuleLog(rule_id=rule_a.id, station_id=out["stations"]["a"].id,
                         metric="grid_voltage_a", triggered=True)
    log_b = AlarmRuleLog(rule_id=rule_b.id, station_id=out["stations"]["b"].id,
                         metric="soc", triggered=False)
    s.add_all([log_a, log_b])
    s.commit()
    out["logs"] = {"a": log_a, "b": log_b}

    def _tok(username):
        r = client.post("/api/v1/auth/login", data={"username": username, "password": pwd})
        assert r.status_code == 200, f"登录失败 {username}: {r.text}"
        return r.json()["data"]["token"]

    out["tokens"]["a"] = _tok("rule_scope_eng_a")
    out["tokens"]["b"] = _tok("rule_scope_eng_b")
    return out


class TestAlarmRulesTeamScope:
    # ── ① 列表读隔离（两个重复端点族） ──

    def test_team_a_list_hides_team_b_rules_both_routers(self, client, rule_scope_pair):
        """团队A用户在 /alarm-rules 与 /alarms/rules 均看不到仅指向B队站的规则"""
        h = {"Authorization": f"Bearer {rule_scope_pair['tokens']['a']}"}
        for path in ("/api/v1/alarm-rules", "/api/v1/alarms/rules"):
            r = client.get(f"{path}?page_size=100", headers=h)
            assert r.status_code == 200, f"{path}: {r.text}"
            ids = {it["id"] for it in r.json()["data"]["items"]}
            assert rule_scope_pair["rules"]["b"].id not in ids, path
            assert rule_scope_pair["rules"]["a"].id in ids, path
            assert rule_scope_pair["rules"]["platform"].id in ids, path

    def test_team_a_detail_of_team_b_rule_404(self, client, rule_scope_pair):
        """团队A用户读B队规则详情 → 404 不泄露存在"""
        h = {"Authorization": f"Bearer {rule_scope_pair['tokens']['a']}"}
        for path in ("/api/v1/alarm-rules", "/api/v1/alarms/rules"):
            r = client.get(f"{path}/{rule_scope_pair['rules']['b'].id}", headers=h)
            assert r.status_code == 404, f"{path}: {r.status_code}"

    # ── ② 平台级规则：可读不可写 ──

    def test_team_a_reads_platform_rule_but_write_404(self, client, rule_scope_pair):
        """团队A用户可读平台级规则详情; PUT/toggle/DELETE → 404"""
        h = {"Authorization": f"Bearer {rule_scope_pair['tokens']['a']}"}
        pid = rule_scope_pair["rules"]["platform"].id
        r = client.get(f"/api/v1/alarm-rules/{pid}", headers=h)
        assert r.status_code == 200 and r.json()["data"]["id"] == pid

        r = client.put(f"/api/v1/alarm-rules/{pid}", json={"threshold": 70.0}, headers=h)
        assert r.status_code == 404
        r = client.put(f"/api/v1/alarms/rules/{pid}", json={"threshold": 70.0}, headers=h)
        assert r.status_code == 404
        r = client.put(f"/api/v1/alarm-rules/{pid}/toggle", headers=h)
        assert r.status_code == 404
        r = client.delete(f"/api/v1/alarm-rules/{pid}", headers=h)
        assert r.status_code == 404
        r = client.delete(f"/api/v1/alarms/rules/{pid}", headers=h)
        assert r.status_code == 404

    # ── ③ 创建约束 ──

    def test_team_a_create_platform_rule_forbidden(self, client, rule_scope_pair):
        """团队A用户创建空 station_ids → 404（平台级规则保留给 admin, 与 RBAC 403 契约区分）"""
        h = {"Authorization": f"Bearer {rule_scope_pair['tokens']['a']}"}
        payload = {"name": "越权平台规则", "metric": "temperature", "operator": ">", "threshold": 50.0}
        for path in ("/api/v1/alarm-rules", "/api/v1/alarms/rules"):
            r = client.post(path, json=payload, headers=h)
            assert r.status_code == 404, f"{path}: {r.status_code} {r.text}"

    def test_team_a_create_with_foreign_station_404(self, client, rule_scope_pair):
        """团队A用户创建含B队 station_id → 404 不泄露存在"""
        h = {"Authorization": f"Bearer {rule_scope_pair['tokens']['a']}"}
        payload = {
            "name": "越权他队规则", "metric": "temperature", "operator": ">",
            "threshold": 50.0, "station_ids": [rule_scope_pair["stations"]["b"].id],
        }
        for path in ("/api/v1/alarm-rules", "/api/v1/alarms/rules"):
            r = client.post(path, json=payload, headers=h)
            assert r.status_code == 404, f"{path}: {r.status_code} {r.text}"

    def test_team_a_update_own_rule_to_foreign_station_404(self, client, rule_scope_pair):
        """团队A用户把本队规则改成B队站点 → 404"""
        h = {"Authorization": f"Bearer {rule_scope_pair['tokens']['a']}"}
        r = client.put(
            f"/api/v1/alarm-rules/{rule_scope_pair['rules']['a'].id}",
            json={"station_ids": [rule_scope_pair["stations"]["b"].id]}, headers=h,
        )
        assert r.status_code == 404

    # ── ④ admin 全量豁免 ──

    def test_admin_full_access_unrestricted(self, client, rule_scope_pair, seed_users):
        """admin 读全量规则(含B队)、建平台级规则、删改平台级规则均不受限"""
        from tests.conftest import _get_token
        token = _get_token(client)
        h = {"Authorization": f"Bearer {token}"}
        ids = set()
        for path in ("/api/v1/alarm-rules", "/api/v1/alarms/rules"):
            r = client.get(f"{path}?page_size=100", headers=h)
            assert r.status_code == 200
            ids |= {it["id"] for it in r.json()["data"]["items"]}
        for k in ("platform", "a", "b"):
            assert rule_scope_pair["rules"][k].id in ids

        r = client.post("/api/v1/alarm-rules", json={
            "name": "admin平台规则", "metric": "temperature", "operator": ">", "threshold": 99.0,
        }, headers=h)
        assert r.status_code == 200
        new_id = r.json()["data"]["id"]
        r = client.put(f"/api/v1/alarm-rules/{new_id}", json={"threshold": 100.0}, headers=h)
        assert r.status_code == 200
        r = client.delete(f"/api/v1/alarm-rules/{new_id}", headers=h)
        assert r.status_code == 200

    # ── ⑤ rule-logs 隔离 ──

    def test_rule_logs_filtered_by_team(self, client, rule_scope_pair):
        """非 admin 只返回本 team 站点的触发日志; admin 全量"""
        from tests.conftest import _get_token
        r = client.get(
            "/api/v1/alarms/rule-logs?page_size=100",
            headers={"Authorization": f"Bearer {rule_scope_pair['tokens']['a']}"},
        )
        assert r.status_code == 200, r.text
        station_ids = {it.get("station_id") for it in r.json()["data"]["items"]}
        assert station_ids == {rule_scope_pair["stations"]["a"].id}

        r = client.get(
            "/api/v1/alarms/rule-logs?page_size=100",
            headers={"Authorization": f"Bearer {_get_token(client)}"},
        )
        assert r.status_code == 200
        station_ids = {it.get("station_id") for it in r.json()["data"]["items"]}
        assert {rule_scope_pair["stations"]["a"].id, rule_scope_pair["stations"]["b"].id} <= station_ids
