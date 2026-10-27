"""
设备维护计划 GET 端点测试

覆盖: GET /api/v1/devices/{id}/maintenance-plan
- 有计划: PUT 写入后 GET 回读，字段与 PUT 写入完全对齐
- 无计划: 未设置的设备 GET 返回 200，日期字段 null（绝不 500）
- 部分更新: 只写 next_maintenance，GET 回读 last 仍为 null
- 设备不存在: 404，detail 风格与同文件其他端点一致
- 未认证: 401/403
"""
import pytest


def _get_token(client, username="admin", password="admin123"):
    """辅助：获取 admin 登录 token"""
    resp = client.post(
        "/api/v1/auth/login",
        data={"username": username, "password": password},
    )
    if resp.status_code != 200:
        return ""
    data = resp.json()
    return data.get("data", {}).get("token", "") or data.get("token", "")


def _auth(client):
    token = _get_token(client)
    assert token, "登录失败，无法获取 token"
    return {"Authorization": f"Bearer {token}"}


# ======================================================================
# 有计划 / 无计划 / 部分更新
# ======================================================================

def test_get_maintenance_plan_with_plan(client, seed_users, seed_devices):
    """PUT 写入维护计划后，GET 回读字段完全对齐。"""
    headers = _auth(client)
    dev_id = seed_devices["chg001"].id
    payload = {
        "maintenance_interval_days": 30,
        "last_maintenance": "2026-06-01",
        "next_maintenance": "2026-07-01",
    }
    put = client.put(
        f"/api/v1/devices/{dev_id}/maintenance-plan", json=payload, headers=headers
    )
    assert put.status_code == 200, put.text

    resp = client.get(f"/api/v1/devices/{dev_id}/maintenance-plan", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["device_id"] == dev_id
    assert data["maintenance_interval_days"] == 30
    assert data["last_maintenance"] == "2026-06-01"
    assert data["next_maintenance"] == "2026-07-01"


def test_get_maintenance_plan_empty(client, seed_users, seed_devices):
    """未设置维护计划的设备：GET 返回 200，日期字段 null，绝不 500。"""
    headers = _auth(client)
    dev_id = seed_devices["inv001"].id

    resp = client.get(f"/api/v1/devices/{dev_id}/maintenance-plan", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["device_id"] == dev_id
    assert data["last_maintenance"] is None
    assert data["next_maintenance"] is None
    assert data["maintenance_interval_days"] == 90  # 模型默认值


def test_get_maintenance_plan_partial_update(client, seed_users, seed_devices):
    """只更新 next_maintenance，GET 回读：next 有值，last 仍为 null。"""
    headers = _auth(client)
    dev_id = seed_devices["pcs001"].id
    client.put(
        f"/api/v1/devices/{dev_id}/maintenance-plan",
        json={"next_maintenance": "2026-09-01"},
        headers=headers,
    )

    resp = client.get(f"/api/v1/devices/{dev_id}/maintenance-plan", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["next_maintenance"] == "2026-09-01"
    assert data["last_maintenance"] is None


# ======================================================================
# 异常路径
# ======================================================================

def test_get_maintenance_plan_device_not_found(client, seed_users):
    """设备不存在返回 404，detail 与同文件其他端点风格一致。"""
    headers = _auth(client)
    resp = client.get("/api/v1/devices/999999/maintenance-plan", headers=headers)
    assert resp.status_code == 404
    assert resp.json()["detail"] == "设备不存在"


def test_get_maintenance_plan_unauthenticated(anon_client):
    """未认证访问返回 401/403。"""
    resp = anon_client.get("/api/v1/devices/1/maintenance-plan")
    assert resp.status_code in (401, 403)
