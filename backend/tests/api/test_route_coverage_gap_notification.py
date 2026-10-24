# 卡18885b82: 路由补盲 — 通知配置双前缀 9 端点
# /system-config/notification: templates/{id} GET/PUT/DELETE, rules/{id} PUT/DELETE
# /notification-configs: {id}/toggle PUT, templates/{id} GET/PUT/DELETE
from app.models.notification_config import NotificationConfig, NotificationTemplate

SC = "/api/v1/system-config/notification"
NC = "/api/v1/notification-configs"


def _seed_template(s, name="测试模板", is_system=False, code=None):
    t = NotificationTemplate(name=name, code=code or f"TPL_{abs(hash(name)) % 10**8}",
                             channel="email", event_type="alarm", content="内容 {var}",
                             is_system=is_system, enabled=True)
    s.add(t)
    s.commit()
    s.refresh(t)
    return t


def _seed_config(s, name="测试规则"):
    c = NotificationConfig(name=name, scope_type="tenant", enabled=True)
    s.add(c)
    s.commit()
    s.refresh(c)
    return c


# ─── /system-config/notification ───

def test_sc_template_get_update_delete(client):
    t = _seed_template(client._sesh, name="SC模板")
    r = client.get(f"{SC}/templates/{t.id}")
    assert r.status_code == 200
    assert r.json()["data"]["name"] == "SC模板"

    r = client.put(f"{SC}/templates/{t.id}", json={"name": "改名", "content": "新内容"})
    assert r.status_code == 200
    assert r.json()["data"]["name"] == "改名"

    assert client.get(f"{SC}/templates/99999").status_code == 404
    assert client.put(f"{SC}/templates/99999", json={"name": "x"}).status_code == 404

    r = client.delete(f"{SC}/templates/{t.id}")
    assert r.status_code == 200
    assert client.get(f"{SC}/templates/{t.id}").status_code == 404


def test_sc_template_system_immune(client):
    t = _seed_template(client._sesh, name="内置模板", is_system=True)
    assert client.put(f"{SC}/templates/{t.id}", json={"name": "x"}).status_code == 400
    assert client.delete(f"{SC}/templates/{t.id}").status_code == 400


def test_sc_rule_update_delete(client):
    c = _seed_config(client._sesh, name="SC规则")
    r = client.put(f"{SC}/rules/{c.id}",
                   json={"name": "新名", "channels": ["sms", "email"], "enabled": False})
    assert r.status_code == 200
    assert r.json()["data"]["name"] == "新名"
    assert client.put(f"{SC}/rules/99999", json={"name": "x"}).status_code == 404

    r = client.delete(f"{SC}/rules/{c.id}")
    assert r.status_code == 200
    assert client.delete(f"{SC}/rules/{c.id}").status_code == 404


# ─── /notification-configs ───

def test_nc_toggle(client):
    c = _seed_config(client._sesh, name="切换配置")
    r = client.put(f"{NC}/{c.id}/toggle")
    assert r.status_code == 200
    assert r.json()["data"]["enabled"] is False
    r = client.put(f"{NC}/{c.id}/toggle")
    assert r.json()["data"]["enabled"] is True
    assert client.put(f"{NC}/99999/toggle").status_code == 404


def test_nc_template_get_update_delete(client):
    t = _seed_template(client._sesh, name="NC模板")
    r = client.get(f"{NC}/templates/{t.id}")
    assert r.status_code == 200
    assert r.json()["data"]["name"] == "NC模板"

    r = client.put(f"{NC}/templates/{t.id}", json={"name": "NC改名", "enabled": False})
    assert r.status_code == 200
    assert r.json()["data"]["name"] == "NC改名"

    assert client.get(f"{NC}/templates/99999").status_code == 404
    assert client.put(f"{NC}/templates/99999", json={"name": "x"}).status_code == 404

    assert client.delete(f"{NC}/templates/{t.id}").status_code == 200
    assert client.get(f"{NC}/templates/{t.id}").status_code == 404
    assert client.delete(f"{NC}/templates/99999").status_code == 404
