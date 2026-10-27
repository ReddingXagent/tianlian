"""
协议实例管理 API 测试

覆盖:
- /api/v1/protocol-instances        协议实例 CRUD + connect/disconnect
- /api/v1/parser-configs            解析器配置 CRUD
- /api/v1/connection-dashboard      连接状态仪表板

注: protocol_instances / parser_configs 两表仅在 Alembic 迁移
    (202606020200_add_protocol_instance_tables) 中定义, 未注册到 Base.metadata,
    故本文件用 autouse fixture 手动建表 (SQLite 版, JSONB→TEXT), 对齐迁移结构。
"""
import pytest
from sqlalchemy import text


@pytest.fixture(autouse=True)
def _ensure_protocol_tables(client):
    """建两张迁移表 (SQLite 版), 供 raw-SQL 路由读写。"""
    s = client._sesh
    s.execute(text("""
        CREATE TABLE IF NOT EXISTS protocol_instances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            protocol_type TEXT NOT NULL,
            gateway_id INTEGER,
            device_type TEXT,
            config TEXT,
            parser_schema TEXT,
            status TEXT NOT NULL DEFAULT 'stopped',
            connection_status TEXT NOT NULL DEFAULT 'disconnected',
            last_connected DATETIME,
            description TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """))
    s.execute(text("""
        CREATE TABLE IF NOT EXISTS parser_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            device_type TEXT NOT NULL,
            protocol TEXT NOT NULL,
            parser_schema TEXT,
            config TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            description TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """))
    s.commit()


def _auth(client):
    r = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['data']['token']}"}


def _auth_engineer(client):
    r = client.post("/api/v1/auth/login", data={"username": "engineer1", "password": "eng123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['data']['token']}"}


def _create_instance(client, headers, name="测试Modbus实例", protocol_type="modbus_rtu"):
    return client.post("/api/v1/protocol-instances", json={
        "name": name,
        "protocol_type": protocol_type,
        "config": {"host": "127.0.0.1", "port": 502},
        "description": "测试用例",
    }, headers=headers)


# ── 协议实例 ────────────────────────────────────────────────

def test_create_and_get_instance(client, seed_users):
    headers = _auth(client)
    cre = _create_instance(client, headers)
    assert cre.status_code == 200
    d = cre.json()["data"]
    assert d["id"] > 0
    assert d["name"] == "测试Modbus实例"

    detail = client.get(f"/api/v1/protocol-instances/{d['id']}", headers=headers)
    assert detail.status_code == 200
    info = detail.json()["data"]
    assert info["protocol_type"] == "modbus_rtu"
    # 迁移默认值
    assert info["status"] == "stopped"
    assert info["connection_status"] == "disconnected"
    # SQLite 下 config 以 JSON 字符串存储
    assert isinstance(info["config"], str)
    assert "host" in info["config"]


def test_list_with_filter(client, seed_users):
    headers = _auth(client)
    _create_instance(client, headers, name="Modbus-A", protocol_type="modbus_rtu")
    _create_instance(client, headers, name="MQTT-B", protocol_type="mqtt")

    # 全量
    all_resp = client.get("/api/v1/protocol-instances", headers=headers)
    assert all_resp.status_code == 200
    assert all_resp.json()["data"]["total"] == 2

    # 按协议筛选
    r = client.get("/api/v1/protocol-instances?protocol_type=mqtt", headers=headers)
    items = r.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["protocol_type"] == "mqtt"

    # 关键词搜索 (匹配 name)
    r2 = client.get("/api/v1/protocol-instances?keyword=Modbus", headers=headers)
    assert r2.json()["data"]["total"] == 1


def test_update_instance(client, seed_users):
    headers = _auth(client)
    d = _create_instance(client, headers).json()["data"]
    resp = client.put(f"/api/v1/protocol-instances/{d['id']}", json={
        "name": "更新后实例",
        "status": "running",
    }, headers=headers)
    assert resp.status_code == 200
    assert "更新成功" in resp.json()["message"]

    info = client.get(f"/api/v1/protocol-instances/{d['id']}", headers=headers).json()["data"]
    assert info["name"] == "更新后实例"
    assert info["status"] == "running"


def test_update_empty_returns_noop(client, seed_users):
    """空更新体 → 返回 '无需更新'"""
    headers = _auth(client)
    d = _create_instance(client, headers).json()["data"]
    resp = client.put(f"/api/v1/protocol-instances/{d['id']}", json={}, headers=headers)
    assert resp.status_code == 200
    assert "无需更新" in resp.json()["message"]


def test_connect_disconnect_flow(client, seed_users):
    headers = _auth(client)
    d = _create_instance(client, headers, name="连接测试").json()["data"]["id"]

    conn = client.post(f"/api/v1/protocol-instances/{d}/connect", headers=headers)
    assert conn.status_code == 200
    assert "已连接" in conn.json()["message"]
    info = client.get(f"/api/v1/protocol-instances/{d}", headers=headers).json()["data"]
    assert info["connection_status"] == "connected"
    assert info["status"] == "running"
    assert info["last_connected"] is not None

    disc = client.post(f"/api/v1/protocol-instances/{d}/disconnect", headers=headers)
    assert disc.status_code == 200
    info = client.get(f"/api/v1/protocol-instances/{d}", headers=headers).json()["data"]
    assert info["connection_status"] == "disconnected"
    assert info["status"] == "stopped"


def test_instance_404s(client, seed_users):
    headers = _auth(client)
    assert client.get("/api/v1/protocol-instances/999999", headers=headers).status_code == 404
    assert client.put("/api/v1/protocol-instances/999999", json={"name": "x"}, headers=headers).status_code == 404
    assert client.delete("/api/v1/protocol-instances/999999", headers=headers).status_code == 404
    assert client.post("/api/v1/protocol-instances/999999/connect", headers=headers).status_code == 404


def test_delete_instance(client, seed_users):
    headers = _auth(client)
    d = _create_instance(client, headers).json()["data"]["id"]
    resp = client.delete(f"/api/v1/protocol-instances/{d}", headers=headers)
    assert resp.status_code == 200
    assert "已删除" in resp.json()["message"]
    assert client.get(f"/api/v1/protocol-instances/{d}", headers=headers).status_code == 404


# ── 解析器配置 ──────────────────────────────────────────────

def test_parser_config_crud(client, seed_users):
    headers = _auth(client)
    cre = client.post("/api/v1/parser-configs", json={
        "name": "Modbus解析器",
        "device_type": "pv_inverter",
        "protocol": "modbus_rtu",
        "parser_schema": "schema_v1",
        "config": {"register": 4000},
    }, headers=headers)
    assert cre.status_code == 200
    pid = cre.json()["data"]["id"]
    assert pid > 0

    lst = client.get("/api/v1/parser-configs", headers=headers)
    assert lst.json()["data"]["total"] == 1
    assert lst.json()["data"]["items"][0]["name"] == "Modbus解析器"

    upd = client.put(f"/api/v1/parser-configs/{pid}", json={"status": "inactive"}, headers=headers)
    assert upd.status_code == 200

    dele = client.delete(f"/api/v1/parser-configs/{pid}", headers=headers)
    assert dele.status_code == 200
    assert client.get("/api/v1/parser-configs", headers=headers).json()["data"]["total"] == 0


def test_parser_config_404s(client, seed_users):
    headers = _auth(client)
    assert client.put("/api/v1/parser-configs/999999", json={"name": "x"}, headers=headers).status_code == 404
    assert client.delete("/api/v1/parser-configs/999999", headers=headers).status_code == 404


def test_parser_config_write_requires_platform_admin(client, seed_users):
    """parser_configs 是平台级共享模板：非 admin 写三端点须 403。"""
    admin = _auth(client)
    eng = _auth_engineer(client)

    # 非 admin 创建 → 403
    cre = client.post("/api/v1/parser-configs", json={
        "name": "越权解析器", "device_type": "pv_inverter", "protocol": "modbus_rtu",
    }, headers=eng)
    assert cre.status_code == 403

    # admin 建一条，供改/删断言
    pid = client.post("/api/v1/parser-configs", json={
        "name": "Admin解析器", "device_type": "pv_inverter", "protocol": "modbus_rtu",
    }, headers=admin).json()["data"]["id"]

    # 非 admin 更新 / 删除 → 403
    assert client.put(f"/api/v1/parser-configs/{pid}", json={"name": "x"}, headers=eng).status_code == 403
    assert client.delete(f"/api/v1/parser-configs/{pid}", headers=eng).status_code == 403

    # admin 正常写不回归
    assert client.put(f"/api/v1/parser-configs/{pid}", json={"status": "inactive"}, headers=admin).status_code == 200
    assert client.delete(f"/api/v1/parser-configs/{pid}", headers=admin).status_code == 200

    # 非 admin 删除不存在的也不应走到 404 分支（403 优先）
    assert client.delete("/api/v1/parser-configs/999999", headers=eng).status_code == 403


def test_parser_config_keyword_wildcard_escaped(client, seed_users):
    """keyword 中 % / _ 不应作 LIKE 通配符（防通配符枚举）。"""
    headers = _auth(client)
    client.post("/api/v1/parser-configs", json={
        "name": "AAA", "device_type": "pv_inverter", "protocol": "modbus_rtu",
    }, headers=headers)
    client.post("/api/v1/parser-configs", json={
        "name": "ABA", "device_type": "pv_inverter", "protocol": "modbus_rtu",
    }, headers=headers)
    # "A%A" 若 % 生效会命中 AAA/ABA；转义后应零命中
    r = client.get("/api/v1/parser-configs?keyword=A%A", headers=headers)
    assert r.json()["data"]["total"] == 0
    # "A_A" 若 _ 生效会命中 AAA/ABA（各含一个任意字符）
    r2 = client.get("/api/v1/parser-configs?keyword=A_A", headers=headers)
    assert r2.json()["data"]["total"] == 0
    # 正常子串仍命中
    r3 = client.get("/api/v1/parser-configs?keyword=AB", headers=headers)
    assert r3.json()["data"]["total"] == 1


def test_instance_keyword_wildcard_escaped(client, seed_users):
    headers = _auth(client)
    _create_instance(client, headers, name="AAA")
    _create_instance(client, headers, name="ABA")
    assert client.get("/api/v1/protocol-instances?keyword=A%A", headers=headers).json()["data"]["total"] == 0
    assert client.get("/api/v1/protocol-instances?keyword=A_A", headers=headers).json()["data"]["total"] == 0
    assert client.get("/api/v1/protocol-instances?keyword=AB", headers=headers).json()["data"]["total"] == 1


# ── 连接状态仪表板 ──────────────────────────────────────────

def test_connection_dashboard(client, seed_users):
    headers = _auth(client)
    # 建一个 connected 实例 + 一个解析器配置以丰富统计
    inst = _create_instance(client, headers, name="仪表板实例", protocol_type="modbus_rtu").json()["data"]
    client.post(f"/api/v1/protocol-instances/{inst['id']}/connect", headers=headers)
    client.post("/api/v1/parser-configs", json={
        "name": "P", "device_type": "dt", "protocol": "mqtt",
    }, headers=headers)

    resp = client.get("/api/v1/connection-dashboard", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    stats = data["stats"]
    assert stats["total"] >= 1
    assert stats["connected"] >= 1
    assert stats["running"] >= 1
    assert isinstance(stats["by_protocol"], dict)
    assert "modbus_rtu" in stats["by_protocol"]
    assert data["protocol_count"] >= 1
    assert data["parser_count"] >= 1
    assert isinstance(data["recent_connections"], list)
