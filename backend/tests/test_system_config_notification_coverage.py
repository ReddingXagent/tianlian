"""
系统配置 - 通知配置域 覆盖率补充测试
目标: app/api/v1/system_config/notification.py 64% → 100%

覆盖原未命中分支:
  - get_notification_switches 已存在配置分支 (115-122)
  - list_notification_templates 过滤分支 channel/event_type/enabled (235/237/239)
  - get_notification_template 详情 + 404 (272-276)
  - create_notification_template 重复 code 400 (303)
  - update_notification_template 全字段/404/系统模板拒改 (344-378)
  - delete_notification_template 成功/404/系统模板拒删 (391-411)
  - list_notification_rules 过滤分支 scope_type/scope_id/enabled (431/433/435)
  - update_notification_rule 全字段/404 (525-573)
  - delete_notification_rule 成功/404 (583-601)

client fixture 已注入 admin token，端点对 admin 直通(_check_admin_or_permission)。
源码零改动。
"""
from fastapi.testclient import TestClient

# client fixture 已带 admin Authorization 头；统一前缀
BASE = "/api/v1/system-config"


class TestNotificationSwitchesExistingConfig:
    """通知开关: 命中「配置已存在」分支 (115-122)。"""

    def test_get_switches_returns_stored_values_after_update(self, client: TestClient, seed_users):
        """先 PUT 写入开关 → 再 GET 应走 config 已存在分支并返回存储值，而非默认全 False。"""
        resp_put = client.put(f"{BASE}/notification/switches", json={
            "sms_on": True, "email_on": True, "app_push_on": True,
            "im_b_on": True, "im_on": True,
        })
        assert resp_put.status_code == 200

        resp = client.get(f"{BASE}/notification/switches")
        assert resp.status_code == 200
        sw = resp.json()["data"]
        # 全部为 True 才能证明走的是「已存在配置」分支，而非默认值分支
        assert sw["sms_on"] is True
        assert sw["email_on"] is True
        assert sw["app_push_on"] is True
        assert sw["im_b_on"] is True
        assert sw["im_on"] is True


class TestNotificationTemplates:
    """通知模板: 详情/过滤/重复/更新/删除全路径。"""

    def _create(self, client, code="tpl_a", channel="sms", event_type="evt_a",
                is_system=False, content="内容 {var}"):
        resp = client.post(f"{BASE}/notification/templates", json={
            "name": f"模板_{code}",
            "code": code,
            "channel": channel,
            "event_type": event_type,
            "subject": "主题",
            "content": content,
            "variables": [{"name": "var", "desc": "变量"}],
            "is_system": is_system,
        })
        assert resp.status_code in (200, 201), resp.text
        return resp.json()["data"]

    # ── 详情 (272-276) ──
    def test_get_template_detail_success(self, client, seed_users):
        d = self._create(client, code="tpl_detail")
        resp = client.get(f"{BASE}/notification/templates/{d['id']}")
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["id"] == d["id"]
        assert body["code"] == "tpl_detail"
        assert body["channel"] == "sms"
        assert body["content"] == "内容 {var}"
        assert body["variables"] == [{"name": "var", "desc": "变量"}]

    def test_get_template_not_found(self, client, seed_users):
        resp = client.get(f"{BASE}/notification/templates/99999")
        assert resp.status_code == 404
        assert "不存在" in resp.json()["detail"]

    # ── 重复 code (303) ──
    def test_create_template_duplicate_code(self, client, seed_users):
        self._create(client, code="dup_code")
        resp = client.post(f"{BASE}/notification/templates", json={
            "name": "重复模板", "code": "dup_code",
            "channel": "sms", "event_type": "evt", "content": "x",
        })
        assert resp.status_code == 400
        assert "已存在" in resp.json()["detail"]

    # ── 列表过滤 (235/237/239) ──
    def test_list_templates_filter_by_channel(self, client, seed_users):
        self._create(client, code="f_sms", channel="sms", event_type="filter_evt")
        self._create(client, code="f_email", channel="email", event_type="filter_evt")
        resp = client.get(f"{BASE}/notification/templates", params={"channel": "sms"})
        assert resp.status_code == 200
        codes = [i["code"] for i in resp.json()["data"]["items"]]
        assert "f_sms" in codes
        assert "f_email" not in codes

    def test_list_templates_filter_by_event_type(self, client, seed_users):
        self._create(client, code="e_a", channel="sms", event_type="evt_unique_a")
        self._create(client, code="e_b", channel="sms", event_type="evt_unique_b")
        resp = client.get(f"{BASE}/notification/templates", params={"event_type": "evt_unique_b"})
        codes = [i["code"] for i in resp.json()["data"]["items"]]
        assert codes == ["e_b"]

    def test_list_templates_filter_by_enabled(self, client, seed_users):
        # 新建模板默认 enabled=True，先禁用其中一个
        d = self._create(client, code="en_dis")
        client.put(f"{BASE}/notification/templates/{d['id']}", json={"enabled": False})
        resp = client.get(f"{BASE}/notification/templates", params={"enabled": False})
        assert resp.status_code == 200
        items = resp.json()["data"]["items"]
        assert all(i["enabled"] is False for i in items)
        assert any(i["code"] == "en_dis" for i in items)

    # ── 更新 (344-378) ──
    def test_update_template_success_all_fields(self, client, seed_users):
        d = self._create(client, code="upd_tpl")
        resp = client.put(f"{BASE}/notification/templates/{d['id']}", json={
            "name": "新名称", "subject": "新主题", "content": "新内容",
            "variables": [{"name": "x", "desc": "y"}], "enabled": False,
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["name"] == "新名称"
        # 回读确认字段全部落库
        body = client.get(f"{BASE}/notification/templates/{d['id']}").json()["data"]
        assert body["subject"] == "新主题"
        assert body["content"] == "新内容"
        assert body["enabled"] is False
        assert body["variables"] == [{"name": "x", "desc": "y"}]

    def test_update_template_not_found(self, client, seed_users):
        resp = client.put(f"{BASE}/notification/templates/99999", json={"name": "x"})
        assert resp.status_code == 404

    def test_update_system_template_rejected(self, client, seed_users):
        d = self._create(client, code="sys_upd", is_system=True)
        resp = client.put(f"{BASE}/notification/templates/{d['id']}", json={"name": "x"})
        assert resp.status_code == 400
        assert "不可修改" in resp.json()["detail"]

    # ── 删除 (391-411) ──
    def test_delete_template_success(self, client, seed_users):
        d = self._create(client, code="del_tpl")
        resp = client.delete(f"{BASE}/notification/templates/{d['id']}")
        assert resp.status_code == 200
        assert resp.json()["message"].endswith("已删除")
        # 二次获取应 404，证明确实删除
        assert client.get(f"{BASE}/notification/templates/{d['id']}").status_code == 404

    def test_delete_template_not_found(self, client, seed_users):
        resp = client.delete(f"{BASE}/notification/templates/99999")
        assert resp.status_code == 404

    def test_delete_system_template_rejected(self, client, seed_users):
        d = self._create(client, code="sys_del", is_system=True)
        resp = client.delete(f"{BASE}/notification/templates/{d['id']}")
        assert resp.status_code == 400
        assert "不可删除" in resp.json()["detail"]


class TestNotificationRules:
    """通知规则: 过滤/更新/删除全路径。"""

    def _create(self, client, name="rule_a", scope_type="tenant", scope_id=1,
                channels=("sms",), enabled=True, priority=0):
        resp = client.post(f"{BASE}/notification/rules", json={
            "name": name, "scope_type": scope_type, "scope_id": scope_id,
            "channels": list(channels),
            "receivers": ["u1"], "receiver_roles": ["admin"],
            "trigger_events": ["alarm_trigger"],
            "quiet_start": "22:00", "quiet_end": "08:00",
            "timezone": "Asia/Shanghai",
            "rate_limit_per_hour": 10, "rate_limit_per_day": 50,
            "enabled": enabled, "priority": priority,
        })
        assert resp.status_code in (200, 201), resp.text
        return resp.json()["data"]

    # ── 列表过滤 (431/433/435) ──
    def test_list_rules_filter_by_scope_type(self, client, seed_users):
        self._create(client, name="r_station", scope_type="station", scope_id=100, priority=1)
        self._create(client, name="r_tenant", scope_type="tenant", scope_id=1, priority=0)
        resp = client.get(f"{BASE}/notification/rules", params={"scope_type": "station"})
        names = [i["name"] for i in resp.json()["data"]["items"]]
        assert "r_station" in names
        assert "r_tenant" not in names

    def test_list_rules_filter_by_scope_id(self, client, seed_users):
        self._create(client, name="r_sid", scope_type="station", scope_id=777, priority=1)
        resp = client.get(f"{BASE}/notification/rules", params={"scope_id": 777})
        names = [i["name"] for i in resp.json()["data"]["items"]]
        assert names == ["r_sid"]

    def test_list_rules_filter_by_enabled(self, client, seed_users):
        self._create(client, name="r_off", enabled=False, priority=0)
        self._create(client, name="r_on", enabled=True, priority=1)
        resp = client.get(f"{BASE}/notification/rules", params={"enabled": False})
        assert resp.status_code == 200
        names = [i["name"] for i in resp.json()["data"]["items"]]
        assert "r_off" in names
        assert "r_on" not in names

    # ── 更新 (525-573) ──
    def test_update_rule_success_all_fields(self, client, seed_users):
        d = self._create(client, name="upd_rule", channels=("sms",))
        resp = client.put(f"{BASE}/notification/rules/{d['id']}", json={
            "name": "新规则名",
            "channels": ["email", "im_b"],   # 渠道重算：sms 关、email/im_b 开
            "receivers": ["u2"], "receiver_roles": ["engineer"],
            "trigger_events": ["workorder_dispatch"],
            "template_overrides": {"sms": "tpl_x"},
            "quiet_start": "23:00", "quiet_end": "07:00",
            "timezone": "UTC",
            "rate_limit_per_hour": 20, "rate_limit_per_day": 100,
            "enabled": False, "priority": 9,
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["name"] == "新规则名"

        # 回读验证全部字段落库 + 渠道开关按 channels 重算
        items = client.get(f"{BASE}/notification/rules").json()["data"]["items"]
        upd = next(i for i in items if i["id"] == d["id"])
        assert upd["sms_enabled"] is False
        assert upd["email_enabled"] is True
        assert upd["im_b_enabled"] is True
        assert upd["im_enabled"] is False
        assert upd["receivers"] == ["u2"]
        assert upd["receiver_roles"] == ["engineer"]
        assert upd["trigger_events"] == ["workorder_dispatch"]
        assert upd["template_overrides"] == {"sms": "tpl_x"}
        assert upd["quiet_start"] == "23:00"
        assert upd["quiet_end"] == "07:00"
        assert upd["timezone"] == "UTC"
        assert upd["rate_limit_per_hour"] == 20
        assert upd["rate_limit_per_day"] == 100
        assert upd["enabled"] is False
        assert upd["priority"] == 9

    def test_update_rule_partial_channels_only(self, client, seed_users):
        """只更新 channels，其他字段保持。"""
        d = self._create(client, name="part_rule", channels=("sms", "email"))
        resp = client.put(f"{BASE}/notification/rules/{d['id']}", json={"channels": ["app"]})
        assert resp.status_code == 200
        items = client.get(f"{BASE}/notification/rules").json()["data"]["items"]
        upd = next(i for i in items if i["id"] == d["id"])
        assert upd["app_push_enabled"] is True
        assert upd["sms_enabled"] is False
        assert upd["email_enabled"] is False
        # name 未传应保持原值
        assert upd["name"] == "part_rule"

    def test_update_rule_not_found(self, client, seed_users):
        resp = client.put(f"{BASE}/notification/rules/99999", json={"name": "x"})
        assert resp.status_code == 404
        assert "不存在" in resp.json()["detail"]

    # ── 删除 (583-601) ──
    def test_delete_rule_success(self, client, seed_users):
        d = self._create(client, name="del_rule")
        resp = client.delete(f"{BASE}/notification/rules/{d['id']}")
        assert resp.status_code == 200
        assert resp.json()["message"].endswith("已删除")
        # 列表中不再存在
        items = client.get(f"{BASE}/notification/rules").json()["data"]["items"]
        assert all(i["id"] != d["id"] for i in items)

    def test_delete_rule_not_found(self, client, seed_users):
        resp = client.delete(f"{BASE}/notification/rules/99999")
        assert resp.status_code == 404
        assert "不存在" in resp.json()["detail"]


# ─── quiet_start/quiet_end 校验（卡 6259ac0d）───

class TestQuietTimeValidation:
    def test_create_bad_format_422(self, client, seed_users):
        for bad in ("25:99", "abc", "0800"):
            r = client.post(f"{BASE}/notification/rules", json={
                "name": "rule-x", "scope_type": "tenant", "scope_id": 1,
                "quiet_start": bad, "quiet_end": "09:00",
            })
            assert r.status_code == 422, bad

    def test_create_unpaired_422(self, client, seed_users):
        r = client.post(f"{BASE}/notification/rules", json={
            "name": "rule-x", "scope_type": "tenant", "scope_id": 1, "quiet_start": "22:00",
        })
        assert r.status_code == 422

    def test_create_valid_pair_201(self, client, seed_users):
        r = client.post(f"{BASE}/notification/rules", json={
            "name": "rule-ok", "scope_type": "tenant", "scope_id": 1,
            "quiet_start": "22:00", "quiet_end": "07:00",
        })
        assert r.status_code == 201, r.text

    def test_update_bad_format_422(self, client, seed_users):
        d = client.post(f"{BASE}/notification/rules", json={
            "name": "rule-u", "scope_type": "tenant", "scope_id": 1,
            "quiet_start": "22:00", "quiet_end": "07:00",
        }).json()["data"]
        r = client.put(f"{BASE}/notification/rules/{d['id']}", json={"quiet_start": "25:99", "quiet_end": "09:00"})
        assert r.status_code == 422

    def test_update_unpaired_422(self, client, seed_users):
        d = client.post(f"{BASE}/notification/rules", json={
            "name": "rule-u2", "scope_type": "tenant", "scope_id": 1,
            "quiet_start": "22:00", "quiet_end": "07:00",
        }).json()["data"]
        r = client.put(f"{BASE}/notification/rules/{d['id']}", json={"quiet_start": "23:00"})
        assert r.status_code == 422
