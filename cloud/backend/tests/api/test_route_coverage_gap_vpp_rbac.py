# 卡18885b82: 路由补盲 — /vpp/* 6 端点 + /rbac/* 4 端点
# vpp: dispatch/lp POST, optimize/status GET, auto-scheduler status/start/stop/config
# rbac: roles/{id} GET/PUT/DELETE, check/{permission_name} GET
import uuid

from app.models.rbac import RoleTable, PermissionTable
from app.services.vpp.auto_scheduler import get_vpp_auto_scheduler

VPP = "/api/v1/vpp"
RBAC = "/api/v1/rbac"


def _stop_scheduler():
    """模块级单例 scheduler 跨 test 残留 running 会污染, 收尾强停。"""
    import asyncio
    sched = get_vpp_auto_scheduler()
    if sched._running:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                sched._running = False
                if sched._task:
                    sched._task.cancel()
            else:
                loop.run_until_complete(sched.stop())
        except Exception:
            sched._running = False
            if sched._task:
                sched._task.cancel()


# ─── /vpp/auto-scheduler ───

def test_auto_scheduler_status_stop_config(client):
    r = client.get(f"{VPP}/auto-scheduler/status")
    assert r.status_code == 200
    assert "running" in r.json()["data"]

    # stop 先行 (幂等, 未启动直接 stop 不报错), 再验证 config
    r = client.post(f"{VPP}/auto-scheduler/stop")
    assert r.status_code == 200
    assert r.json()["data"]["running"] is False

    r = client.patch(f"{VPP}/auto-scheduler/config",
                     params={"economic_interval": 300, "peak_threshold": 500.0})
    assert r.status_code == 200
    sched = get_vpp_auto_scheduler()
    assert sched.economic_dispatch_interval_sec == 300
    assert sched.peak_threshold_kw == 500.0
    _stop_scheduler()


def test_auto_scheduler_start_then_stop(client):
    r = client.post(f"{VPP}/auto-scheduler/start")
    assert r.status_code == 200
    assert r.json()["data"]["running"] is True
    r = client.post(f"{VPP}/auto-scheduler/stop")
    assert r.status_code == 200
    assert r.json()["data"]["running"] is False
    _stop_scheduler()


def test_vpp_optimize_status(client):
    r = client.get(f"{VPP}/optimize/status")
    assert r.status_code == 200
    data = r.json()["data"]
    assert "lp_optimizer_available" in data
    assert "economic" in data["supported_modes"]


def test_vpp_lp_dispatch_ok_and_bad_mode(client):
    r = client.post(f"{VPP}/dispatch/lp",
                    json={"target_power_kw": 0, "duration_min": 15, "mode": "economic"})
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["mode"] == "economic"
    assert "plan_id" in data

    r = client.post(f"{VPP}/dispatch/lp", json={"mode": "bad_mode"})
    assert r.status_code == 400
    _stop_scheduler()


# ─── /rbac ───

def _seed_role(s, name, is_system=0):
    role = RoleTable(name=name, display_name=name, description="", is_system=is_system)
    s.add(role)
    s.commit()
    s.refresh(role)
    return role


def test_rbac_role_get_update_delete(client):
    s = client._sesh
    role = _seed_role(s, f"gaprole_{uuid.uuid4().hex[:8]}")
    r = client.get(f"{RBAC}/roles/{role.id}")
    assert r.status_code == 200
    assert r.json()["data"]["name"] == role.name

    r = client.put(f"{RBAC}/roles/{role.id}", json={"display_name": "改名角色"})
    assert r.status_code == 200
    assert r.json()["data"]["display_name"] == "改名角色"

    assert client.get(f"{RBAC}/roles/99999").status_code == 404
    assert client.put(f"{RBAC}/roles/99999", json={"display_name": "x"}).status_code == 404

    r = client.delete(f"{RBAC}/roles/{role.id}")
    assert r.status_code == 200
    assert client.get(f"{RBAC}/roles/{role.id}").status_code == 404
    assert client.delete(f"{RBAC}/roles/99999").status_code == 404


def test_rbac_role_delete_system_forbidden(client):
    s = client._sesh
    role = _seed_role(s, f"sysrole_{uuid.uuid4().hex[:8]}", is_system=1)
    assert client.delete(f"{RBAC}/roles/{role.id}").status_code == 400


def test_rbac_check_permission(client):
    r = client.get(f"{RBAC}/check/nonexistent:perm")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["permission"] == "nonexistent:perm"
    assert data["allowed"] is False
    # admin 直通, 任意真实权限应 allowed
    perm = s_perm = client._sesh.query(PermissionTable).first()
    if perm is not None:
        r = client.get(f"{RBAC}/check/{perm.name}")
        assert r.json()["data"]["allowed"] is True
