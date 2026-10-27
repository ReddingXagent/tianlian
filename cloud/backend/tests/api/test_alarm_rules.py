#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""告警规则配置 API 测试 (app/api/v1/alarm_rules.py, 工作卡 65f59428)

覆盖 7 个端点 (前缀 /api/v1/alarm-rules):
- GET  /                    列表 (enabled / device_type 过滤 + 分页)
- GET  /{rule_id}           详情 (不存在 → 404)
- POST /                    创建 (无效 level → 500 由 AlarmLevel 枚举触发)
- PUT  /{rule_id}           更新 (exclude_none; level 转枚举; 不存在 → 404)
- DELETE /{rule_id}         删除 (不存在 → 404)
- PUT  /{rule_id}/toggle    启用/禁用翻转
- POST /{rule_id}/evaluate  手动评估 (规则不存在 → triggered=False)

覆盖维度:
(a) 正常路径: CRUD 字段正确 + 序列化 (level 转 value)
(b) 参数校验: 缺 name/metric/threshold → 422; 分页越界 → 422
(c) 边界: update 仅传部分字段 (exclude_none); toggle 双向翻转
(d) 404: 详情/更新/删除/翻转 不存在规则
(e) 过滤: enabled / device_type
(f) 权限门: 写端点 require_permission("alarm:process") —— viewer → 403, 匿名 → 401

铁律: 仅加测试, 不改业务代码。
"""
import pytest

from app.models.alarm import AlarmRule, AlarmLevel

from tests.api._helpers import login_as, login_admin

URL = "/api/v1/alarm-rules"


def _payload(**overrides):
    p = {
        "name": "高温告警",
        "metric": "battery_temperature",
        "operator": ">",
        "threshold": 60.0,
        "level": "warning",
        "duration": 0,
        "enabled": True,
    }
    p.update(overrides)
    return p


# ═══════════════════════════════════════════════════════════════
# 1. 列表 (过滤 + 分页)
# ═══════════════════════════════════════════════════════════════

class TestList:
    def test_list_empty(self, client):
        r = client.get(URL)
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["total"] == 0
        assert d["items"] == []

    def test_list_filter_by_enabled(self, client):
        s = client._sesh
        s.add_all([
            AlarmRule(name="规则A", metric="m1", threshold=1, enabled=True),
            AlarmRule(name="规则B", metric="m2", threshold=2, enabled=False),
        ])
        s.commit()
        r = client.get(URL, params={"enabled": False})
        d = r.json()["data"]
        assert d["total"] == 1
        assert d["items"][0]["name"] == "规则B"

    def test_list_filter_by_device_type(self, client):
        s = client._sesh
        s.add_all([
            AlarmRule(name="PV规则", metric="m", threshold=1, device_type="PV_INVERTER"),
            AlarmRule(name="PCS规则", metric="m", threshold=1, device_type="PCS"),
        ])
        s.commit()
        r = client.get(URL, params={"device_type": "PCS"})
        d = r.json()["data"]
        assert d["total"] == 1
        assert d["items"][0]["name"] == "PCS规则"

    def test_list_pagination(self, client):
        s = client._sesh
        for i in range(3):
            s.add(AlarmRule(name=f"R{i}", metric="m", threshold=i))
        s.commit()
        r = client.get(URL, params={"page": 1, "page_size": 2})
        d = r.json()["data"]
        assert d["total"] == 3
        assert len(d["items"]) == 2

    def test_list_invalid_page_422(self, client):
        r = client.get(URL, params={"page": 0})
        assert r.status_code == 422

    def test_list_invalid_page_size_422(self, client):
        r = client.get(URL, params={"page_size": 101})
        assert r.status_code == 422


# ═══════════════════════════════════════════════════════════════
# 2. 详情
# ═══════════════════════════════════════════════════════════════

class TestGet:
    def test_get_existing(self, client):
        s = client._sesh
        rule = AlarmRule(name="详情规则", metric="voltage", threshold=380, level=AlarmLevel.CRITICAL)
        s.add(rule)
        s.commit()
        s.refresh(rule)
        r = client.get(f"{URL}/{rule.id}")
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["id"] == rule.id
        assert d["name"] == "详情规则"
        assert d["metric"] == "voltage"
        assert d["threshold"] == 380.0
        assert d["level"] == "critical"  # 枚举转 value

    def test_get_not_found_404(self, client):
        r = client.get(f"{URL}/999999")
        assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════
# 3. 创建
# ═══════════════════════════════════════════════════════════════

class TestCreate:
    def test_create_success_defaults(self, client):
        r = client.post(URL, json=_payload(name="新建规则"))
        assert r.status_code == 200, r.text[:300]
        d = r.json()["data"]
        assert d["name"] == "新建规则"
        assert d["operator"] == ">"  # 默认值
        assert d["level"] == "warning"
        assert d["enabled"] is True

    def test_create_with_optional_fields(self, client):
        body = _payload(
            device_type="PCS",
            device_ids=[1, 2],
            station_ids=[10],
            notify_users=[5],
            alarm_template="{metric}={value}",
            silence_minutes=30,
            auto_create_workorder=True,
        )
        r = client.post(URL, json=body)
        assert r.status_code == 200, r.text[:300]
        d = r.json()["data"]
        assert d["device_type"] == "PCS"
        assert d["device_ids"] == [1, 2]
        assert d["silence_minutes"] == 30
        assert d["auto_create_workorder"] is True

    def test_create_missing_required_name_422(self, client):
        body = _payload()
        del body["name"]
        r = client.post(URL, json=body)
        assert r.status_code == 422

    def test_create_missing_required_threshold_422(self, client):
        body = _payload()
        del body["threshold"]
        r = client.post(URL, json=body)
        assert r.status_code == 422

    def test_create_invalid_level(self, client):
        """非法 level → 422。

        57380d119 (卡e4b484b8) 后 RuleCreate.level 收紧为
        Literal["info","warning","critical","fatal"], 非法值由 Pydantic 前置拦截,
        不再进入 create_rule 的 AlarmLevel(data.level) → 无 ValueError re-raise。
        """
        r = client.post(URL, json=_payload(level="bogus"))
        assert r.status_code == 422


# ═══════════════════════════════════════════════════════════════
# 4. 更新
# ═══════════════════════════════════════════════════════════════

class TestUpdate:
    def test_update_partial_fields(self, client):
        """仅传部分字段 (exclude_none) 不覆盖其余字段。"""
        s = client._sesh
        rule = AlarmRule(name="更新前", metric="m", threshold=10, operator=">")
        s.add(rule)
        s.commit()
        s.refresh(rule)
        r = client.put(f"{URL}/{rule.id}", json={"threshold": 99.0, "enabled": False})
        assert r.status_code == 200, r.text[:300]
        d = r.json()["data"]
        assert d["threshold"] == 99.0
        assert d["enabled"] is False
        assert d["name"] == "更新前"  # 未传, 保留
        assert d["operator"] == ">"   # 未传, 保留

    def test_update_level_to_enum(self, client):
        s = client._sesh
        rule = AlarmRule(name="升级", metric="m", threshold=1, level=AlarmLevel.WARNING)
        s.add(rule)
        s.commit()
        s.refresh(rule)
        r = client.put(f"{URL}/{rule.id}", json={"level": "critical"})
        assert r.status_code == 200
        assert r.json()["data"]["level"] == "critical"

    def test_update_not_found_404(self, client):
        r = client.put(f"{URL}/999999", json={"threshold": 1.0})
        assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════
# 5. 删除
# ═══════════════════════════════════════════════════════════════

class TestDelete:
    def test_delete_success(self, client):
        s = client._sesh
        rule = AlarmRule(name="待删", metric="m", threshold=1)
        s.add(rule)
        s.commit()
        s.refresh(rule)
        r = client.delete(f"{URL}/{rule.id}")
        assert r.status_code == 200
        assert client.get(f"{URL}/{rule.id}").status_code == 404

    def test_delete_not_found_404(self, client):
        r = client.delete(f"{URL}/999999")
        assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════
# 6. toggle
# ═══════════════════════════════════════════════════════════════

class TestToggle:
    def test_toggle_flips_enabled(self, client):
        s = client._sesh
        rule = AlarmRule(name="翻转", metric="m", threshold=1, enabled=True)
        s.add(rule)
        s.commit()
        s.refresh(rule)
        r1 = client.put(f"{URL}/{rule.id}/toggle")
        assert r1.status_code == 200
        assert r1.json()["data"]["enabled"] is False
        r2 = client.put(f"{URL}/{rule.id}/toggle")
        assert r2.json()["data"]["enabled"] is True

    def test_toggle_not_found_404(self, client):
        r = client.put(f"{URL}/999999/toggle")
        assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════
# 7. evaluate
# ═══════════════════════════════════════════════════════════════

class TestEvaluate:
    def test_evaluate_missing_rule_not_triggered(self, client):
        """规则不存在 → engine 返回 triggered=False, 端点 200。"""
        r = client.post(f"{URL}/999999/evaluate")
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["success"] is True
        assert d["triggered"] is False

    def test_evaluate_existing_rule_ok(self, client):
        """存在的规则 (无遥测数据) → 评估完成不报错, triggered=False。"""
        s = client._sesh
        rule = AlarmRule(name="评估规则", metric="m", threshold=1)
        s.add(rule)
        s.commit()
        s.refresh(rule)
        r = client.post(f"{URL}/{rule.id}/evaluate")
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["success"] is True
        assert d["rule_id"] == rule.id


# ═══════════════════════════════════════════════════════════════
# 8. 权限门 (写端点 require_permission("alarm:process"))
# ═══════════════════════════════════════════════════════════════

class TestPermissionGate:
    @pytest.fixture
    def viewer_token(self, client):
        """切到 viewer (无 alarm:process) 身份 (seed viewer1 若不存在)。"""
        import bcrypt
        from app.models.user import User, UserRole
        s = client._sesh
        if not s.query(User).filter(User.username == "viewer1").first():
            s.add(User(
                username="viewer1",
                password_hash=bcrypt.hashpw(b"view123", bcrypt.gensalt()).decode(),
                real_name="观察员", role=UserRole.VIEWER, status="active",
            ))
            s.commit()
        return login_as(client, "viewer1", "view123")

    def test_viewer_can_list(self, client, viewer_token):
        """读端点仅 router-level 认证, viewer 可读。"""
        r = client.get(URL)
        assert r.status_code == 200

    def test_viewer_create_403(self, client, viewer_token):
        r = client.post(URL, json=_payload())
        assert r.status_code == 403

    def test_viewer_update_403(self, client, viewer_token):
        r = client.put(f"{URL}/1", json={"threshold": 1.0})
        assert r.status_code == 403

    def test_viewer_delete_403(self, client, viewer_token):
        r = client.delete(f"{URL}/1")
        assert r.status_code == 403

    def test_viewer_toggle_403(self, client, viewer_token):
        r = client.put(f"{URL}/1/toggle")
        assert r.status_code == 403

    def test_anonymous_write_401(self, anon_client):
        r = anon_client.post(URL, json=_payload())
        assert r.status_code == 401


# ═══════════════════════════════════════════════════════════════
# 9. evaluate 端点加固 (卡 2779d516): 写权限 + 用户维度限频
# ═══════════════════════════════════════════════════════════════

class TestEvaluateHardening:
    @pytest.fixture
    def viewer_token(self, client):
        import bcrypt
        from app.models.user import User, UserRole
        s = client._sesh
        if not s.query(User).filter(User.username == "viewer1").first():
            s.add(User(
                username="viewer1",
                password_hash=bcrypt.hashpw(b"view123", bcrypt.gensalt()).decode(),
                real_name="观察员", role=UserRole.VIEWER, status="active",
            ))
            s.commit()
        return login_as(client, "viewer1", "view123")

    def test_viewer_evaluate_403(self, client, viewer_token):
        """evaluate 是写端点 (可触发告警/工单/短信): viewer → 403。"""
        s = client._sesh
        rule = AlarmRule(name="评估权限", metric="m", threshold=1)
        s.add(rule); s.commit(); s.refresh(rule)
        r = client.post(f"{URL}/{rule.id}/evaluate")
        assert r.status_code == 403

    def test_viewer_evaluate_403_dup_endpoint(self, client, viewer_token):
        """重复端点 /alarms/rules/{id}/evaluate 同样要求写权限。"""
        s = client._sesh
        rule = AlarmRule(name="评估权限2", metric="m", threshold=1)
        s.add(rule); s.commit(); s.refresh(rule)
        r = client.post(f"/api/v1/alarms/rules/{rule.id}/evaluate")
        assert r.status_code == 403

    def test_evaluate_rate_limited_429(self, client, monkeypatch):
        """evaluate 用户维度限频: 连续触发超限 → 429 (防 viewer 级刷告警风暴)。"""
        from slowapi.errors import RateLimitExceeded
        from slowapi import _rate_limit_exceeded_handler
        from app.core.rate_limit import limiter

        limiter.reset()
        monkeypatch.setattr(limiter, "enabled", True)
        client.app.state.limiter = limiter
        client.app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

        s = client._sesh
        rule = AlarmRule(name="限频规则", metric="m", threshold=1000.0)
        s.add(rule); s.commit(); s.refresh(rule)

        codes = [client.post(f"{URL}/{rule.id}/evaluate").status_code for _ in range(12)]
        assert 429 in codes, f"超限应有 429, 实际: {codes}"
        # 未超限的请求全部正常
        ok = [c for c in codes if c != 429]
        assert all(c == 200 for c in ok)
        limiter.reset()
