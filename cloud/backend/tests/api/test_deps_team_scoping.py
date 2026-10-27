"""
app/api/deps.py 团队归属守卫单元测试 — 第二层鉴权核心（夜班补测）。

deps.py 是 team scoping 第二层鉴权的公共 helper 层。历史覆盖全部经端点级
间接（test_team_scoping / test_ops_settlement / test_revenue_stats 等），
零文件直接 import deps —— 本文件补齐「函数级」直测，固化每个守卫的契约矩阵：

  ① 同 team 放行
  ② 跨 team → 404（不泄露资源存在；区别于 403）
  ③ admin/super_admin 平台级豁免（跨 team 仍可见）
  ④ 资源不存在 → 404，与跨 team 的 404 不可区分（同 status_code + detail）
  ⑤ None 穿透 fail-closed：资源/用户 team_id 任一为 None 即拒绝
"""
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

# 先触发 app.api.v1 包完整初始化，化解 deps↔v1 循环导入：
# deps 顶层 `from app.api.v1.auth import get_current_user` 会触发 v1/__init__，
# 其中 charging_queue 又 `from app.api.deps import is_platform_admin` —— 若 deps 是
# 首个被导入的 app 模块，is_platform_admin 尚未定义即 ImportError。先 import v1
# 让 deps 在 v1.__init__ 上下文里被首次加载，auth 子模块可独立解析，循环解开。
import app.api.v1  # noqa: F401

from app.api.deps import (
    _team_denied,
    assert_alarm_team_access,
    assert_device_team_access,
    assert_device_team_access_async,
    assert_driver_team_access,
    assert_enterprise_team_access,
    assert_order_team_access,
    assert_station_team_access,
    assert_team_access,
    assert_vehicle_team_access,
    is_platform_admin,
    require_platform_admin,
    team_scope,
)
from app.models.user import User, UserRole


# ─── helpers ───

def _make_user(s, *, role, team_id=None, username=None):
    u = User(
        username=username or f"u_{role.value}_{uuid.uuid4().hex[:8]}",
        real_name=username or "tester",
        role=role,
        team_id=team_id,
        status="active",
        password_hash="x",
    )
    s.add(u)
    s.commit()
    s.refresh(u)
    return u


def _expect_404(fn):
    with pytest.raises(HTTPException) as exc:
        fn()
    assert exc.value.status_code == 404, f"期望 404，实际 {exc.value.status_code}"
    return exc.value


def _expect_403(fn):
    with pytest.raises(HTTPException) as exc:
        fn()
    assert exc.value.status_code == 403, f"期望 403，实际 {exc.value.status_code}"
    return exc.value


# ─── 全量脚手架：两团队 + 多角色用户 + 各域资源（分属两团队 + None 团队）───

@pytest.fixture
def world(client):
    from app.models.alarm import Alarm, AlarmLevel, AlarmStatus
    from app.models.charging_order import ChargingOrder
    from app.models.device import Device, DeviceStatus, DeviceType
    from app.models.enterprise import Enterprise
    from app.models.enterprise_vehicle import EnterpriseVehicle
    from app.models.fleet_driver import FleetDriver
    from app.models.station import Station, StationStatus
    from app.models.user import Team

    s = client._sesh
    h = uuid.uuid4().hex[:8]

    ta = Team(name=f"TA{h}", code=f"TA{h}")
    tb = Team(name=f"TB{h}", code=f"TB{h}")
    s.add_all([ta, tb]); s.commit(); s.refresh(ta); s.refresh(tb)

    sta = Station(name=f"SA{h}", code=f"SA{h}", team_id=ta.id, status=StationStatus.NORMAL)
    stb = Station(name=f"SB{h}", code=f"SB{h}", team_id=tb.id, status=StationStatus.NORMAL)
    stn = Station(name=f"SN{h}", code=f"SN{h}", team_id=None, status=StationStatus.NORMAL)
    s.add_all([sta, stb, stn]); s.commit()
    for x in (sta, stb, stn):
        s.refresh(x)

    dev_a = Device(sn=f"DA{h}", name="da", code=f"DA{h}", type=DeviceType.PV_INVERTER,
                   status=DeviceStatus.ONLINE, station_id=sta.id)
    dev_b = Device(sn=f"DB{h}", name="db", code=f"DB{h}", type=DeviceType.PV_INVERTER,
                   status=DeviceStatus.ONLINE, station_id=stb.id)
    s.add_all([dev_a, dev_b]); s.commit(); s.refresh(dev_a); s.refresh(dev_b)

    ent_a = Enterprise(name=f"EA{h}", code=f"EA{h}", owner_team_id=ta.id)
    ent_b = Enterprise(name=f"EB{h}", code=f"EB{h}", owner_team_id=tb.id)
    ent_n = Enterprise(name=f"EN{h}", code=f"EN{h}", owner_team_id=None)
    s.add_all([ent_a, ent_b, ent_n]); s.commit()
    for x in (ent_a, ent_b, ent_n):
        s.refresh(x)

    veh_a = EnterpriseVehicle(enterprise_id=ent_a.id, plate_number=f"PA{h}", vin=f"VIN{h}A")
    veh_b = EnterpriseVehicle(enterprise_id=ent_b.id, plate_number=f"PB{h}", vin=f"VIN{h}B")
    veh_n = EnterpriseVehicle(enterprise_id=ent_n.id, plate_number=f"PN{h}", vin=f"VIN{h}N")
    s.add_all([veh_a, veh_b, veh_n]); s.commit()
    for x in (veh_a, veh_b, veh_n):
        s.refresh(x)

    drv_a = FleetDriver(enterprise_id=ent_a.id, name=f"dA{h}", phone="13800000001", license_no=f"LA{h}")
    drv_b = FleetDriver(enterprise_id=ent_b.id, name=f"dB{h}", phone="13800000002", license_no=f"LB{h}")
    drv_n = FleetDriver(enterprise_id=ent_n.id, name=f"dN{h}", phone="13800000003", license_no=f"LN{h}")
    s.add_all([drv_a, drv_b, drv_n]); s.commit()
    for x in (drv_a, drv_b, drv_n):
        s.refresh(x)

    alarm_a = Alarm(device_id=dev_a.id, station_id=sta.id, alarm_type="over_temp",
                    level=AlarmLevel.WARNING, content="a", status=AlarmStatus.ACTIVE)
    alarm_b = Alarm(device_id=dev_b.id, station_id=stb.id, alarm_type="comm",
                    level=AlarmLevel.WARNING, content="b", status=AlarmStatus.ACTIVE)
    # station_id=None → 走 device→station→team 回退分支
    alarm_devonly = Alarm(device_id=dev_a.id, station_id=None, alarm_type="x",
                          level=AlarmLevel.WARNING, content="do", status=AlarmStatus.ACTIVE)
    s.add_all([alarm_a, alarm_b, alarm_devonly]); s.commit()
    for x in (alarm_a, alarm_b, alarm_devonly):
        s.refresh(x)

    order_a = ChargingOrder(order_no=f"OA{h}", station_id=sta.id, device_id=dev_a.id)
    order_b = ChargingOrder(order_no=f"OB{h}", station_id=stb.id, device_id=dev_b.id)
    s.add_all([order_a, order_b]); s.commit(); s.refresh(order_a); s.refresh(order_b)

    # conftest 已 seed admin(role=ADMIN, team_id=None)
    admin = s.query(User).filter(User.username == "admin").first()
    super_admin = _make_user(s, role=UserRole.SUPER_ADMIN, team_id=None, username=f"sa_{h}")
    eng_a = _make_user(s, role=UserRole.ENGINEER, team_id=ta.id, username=f"ea_{h}")
    eng_b = _make_user(s, role=UserRole.ENGINEER, team_id=tb.id, username=f"eb_{h}")

    return SimpleNamespace(
        s=s, ta=ta, tb=tb,
        sta=sta, stb=stb, stn=stn,
        dev_a=dev_a, dev_b=dev_b,
        ent_a=ent_a, ent_b=ent_b, ent_n=ent_n,
        veh_a=veh_a, veh_b=veh_b, veh_n=veh_n,
        drv_a=drv_a, drv_b=drv_b, drv_n=drv_n,
        alarm_a=alarm_a, alarm_b=alarm_b, alarm_devonly=alarm_devonly,
        order_a=order_a, order_b=order_b,
        admin=admin, super_admin=super_admin, eng_a=eng_a, eng_b=eng_b,
    )


# ─── is_platform_admin / require_platform_admin / team_scope ───

@pytest.mark.parametrize("role,expected", [
    (UserRole.ADMIN, True),
    (UserRole.SUPER_ADMIN, True),
    (UserRole.ENGINEER, False),
    (UserRole.OPERATOR, False),
    (UserRole.VIEWER, False),
    (UserRole.DISPATCHER, False),
    (UserRole.STATION_MASTER, False),
    (UserRole.AUDITOR, False),
])
def test_is_platform_admin_role_matrix(role, expected):
    u = User(username=f"x{uuid.uuid4().hex[:6]}", real_name="x",
             role=role, status="active", password_hash="x")
    assert is_platform_admin(u) is expected


def test_is_platform_admin_plain_string_role_case_insensitive():
    """role 无 .value（纯字符串）走 hasattr 分支；大小写不敏感。"""
    class _U:
        def __init__(self, r):
            self.role = r
    assert is_platform_admin(_U("admin")) is True
    assert is_platform_admin(_U("SUPER_ADMIN")) is True
    assert is_platform_admin(_U("Engineer")) is False


def test_require_platform_admin_admin_passes(world):
    assert require_platform_admin(world.admin).id == world.admin.id


def test_require_platform_admin_super_admin_passes(world):
    assert require_platform_admin(world.super_admin).id == world.super_admin.id


def test_require_platform_admin_team_level_forbidden_403(world):
    _expect_403(lambda: require_platform_admin(world.eng_a))


def test_require_platform_admin_is_403_not_404(world):
    """非平台 admin 命中 require_platform_admin 是 403（鉴权），不是 404（资源不存在）。"""
    err = _expect_403(lambda: require_platform_admin(world.eng_b))
    assert "管理员" in err.detail


def test_team_scope_platform_admin_returns_none(world):
    assert team_scope(world.admin) is None
    assert team_scope(world.super_admin) is None


def test_team_scope_team_level_returns_team_id(world):
    assert team_scope(world.eng_a) == world.ta.id
    assert team_scope(world.eng_b) == world.tb.id


# ─── _team_denied：None 穿透 fail-closed（核心安全语义）───

def _u(team_id):
    return SimpleNamespace(team_id=team_id)


def test_team_denied_match_passes():
    assert _team_denied(5, _u(5)) is False


def test_team_denied_mismatch_denied():
    assert _team_denied(6, _u(5)) is True


def test_team_denied_resource_none_denied():
    """资源 team_id 为 None → 拒绝（即使用户有明确 team）。"""
    assert _team_denied(None, _u(5)) is True


def test_team_denied_user_none_denied():
    """用户 team_id 为 None → 拒绝（即使资源有明确 team）。"""
    assert _team_denied(5, _u(None)) is True


def test_team_denied_both_none_denied():
    assert _team_denied(None, _u(None)) is True


# ─── assert_team_access：裸 resource_team_id 单资源校验 ───

def test_team_access_same_team_passes(world):
    assert assert_team_access(world.eng_a, world.ta.id) is None


def test_team_access_cross_team_404(world):
    _expect_404(lambda: assert_team_access(world.eng_a, world.tb.id))


def test_team_access_admin_exempt_cross_team(world):
    assert assert_team_access(world.admin, world.tb.id) is None
    assert assert_team_access(world.super_admin, world.tb.id) is None


def test_team_access_resource_none_404(world):
    _expect_404(lambda: assert_team_access(world.eng_a, None))


def test_team_access_user_none_team_404(world):
    """team 级用户但 team_id=None（脏数据）→ fail-closed 404。"""
    eng_no_team = _make_user(world.s, role=UserRole.ENGINEER, team_id=None,
                             username=f"enone_{uuid.uuid4().hex[:6]}")
    _expect_404(lambda: assert_team_access(eng_no_team, world.ta.id))


# ─── assert_station_team_access ───

def test_station_same_team_returns_orm(world):
    st = assert_station_team_access(world.s, world.sta.id, world.eng_a)
    assert st.id == world.sta.id


def test_station_cross_team_404(world):
    _expect_404(lambda: assert_station_team_access(world.s, world.stb.id, world.eng_a))


def test_station_admin_exempt_cross_team(world):
    st = assert_station_team_access(world.s, world.stb.id, world.admin)
    assert st.id == world.stb.id
    st2 = assert_station_team_access(world.s, world.sta.id, world.super_admin)
    assert st2.id == world.sta.id


def test_station_team_user_none_team_station_404(world):
    """station.team_id=None + team 级用户 → 404（None 不视作匹配）。"""
    _expect_404(lambda: assert_station_team_access(world.s, world.stn.id, world.eng_a))


def test_station_admin_none_team_exempt(world):
    st = assert_station_team_access(world.s, world.stn.id, world.admin)
    assert st.id == world.stn.id


def test_station_not_found_404(world):
    _expect_404(lambda: assert_station_team_access(world.s, 999_999, world.eng_a))


def test_station_admin_not_found_still_404(world):
    """admin 也要求资源存在（存在性检查先于 team 豁免）。"""
    _expect_404(lambda: assert_station_team_access(world.s, 999_999, world.admin))


def test_station_cross_team_and_not_found_indistinguishable(world):
    """跨 team 与不存在返回同 status_code + detail，不泄露资源存在性。"""
    e_cross = _expect_404(lambda: assert_station_team_access(world.s, world.stb.id, world.eng_a))
    e_none = _expect_404(lambda: assert_station_team_access(world.s, 999_999, world.eng_a))
    assert e_cross.detail == e_none.detail


# ─── assert_enterprise_team_access ───

def test_enterprise_same_team_returns_orm(world):
    e = assert_enterprise_team_access(world.s, world.ent_a.id, world.eng_a)
    assert e.id == world.ent_a.id


def test_enterprise_cross_team_404(world):
    _expect_404(lambda: assert_enterprise_team_access(world.s, world.ent_b.id, world.eng_a))


def test_enterprise_admin_exempt(world):
    e = assert_enterprise_team_access(world.s, world.ent_b.id, world.admin)
    assert e.id == world.ent_b.id


def test_enterprise_owner_none_team_user_404(world):
    _expect_404(lambda: assert_enterprise_team_access(world.s, world.ent_n.id, world.eng_a))


def test_enterprise_admin_owner_none_exempt(world):
    e = assert_enterprise_team_access(world.s, world.ent_n.id, world.admin)
    assert e.id == world.ent_n.id


def test_enterprise_not_found_404(world):
    _expect_404(lambda: assert_enterprise_team_access(world.s, 999_999, world.eng_a))


def test_enterprise_admin_not_found_still_404(world):
    _expect_404(lambda: assert_enterprise_team_access(world.s, 999_999, world.admin))


# ─── assert_alarm_team_access：station 主路径 + device 回退 ───

def test_alarm_station_path_same_team(world):
    assert assert_alarm_team_access(world.s, world.alarm_a.id, world.eng_a) is None


def test_alarm_station_path_cross_team_404(world):
    _expect_404(lambda: assert_alarm_team_access(world.s, world.alarm_a.id, world.eng_b))


def test_alarm_device_fallback_same_team(world):
    """alarm.station_id=None → 回退 device→station→team（dev_a 挂 team_a）。"""
    assert assert_alarm_team_access(world.s, world.alarm_devonly.id, world.eng_a) is None


def test_alarm_device_fallback_cross_team_404(world):
    _expect_404(lambda: assert_alarm_team_access(world.s, world.alarm_devonly.id, world.eng_b))


def test_alarm_admin_exempt(world):
    assert assert_alarm_team_access(world.s, world.alarm_b.id, world.admin) is None


def test_alarm_not_found_404(world):
    _expect_404(lambda: assert_alarm_team_access(world.s, 999_999, world.eng_a))


def test_alarm_admin_not_found_still_404(world):
    _expect_404(lambda: assert_alarm_team_access(world.s, 999_999, world.admin))


# ─── assert_device_team_access ───

def test_device_same_team_passes(world):
    assert assert_device_team_access(world.s, world.dev_a.id, world.eng_a) is None


def test_device_cross_team_404(world):
    _expect_404(lambda: assert_device_team_access(world.s, world.dev_b.id, world.eng_a))


def test_device_admin_exempt(world):
    assert assert_device_team_access(world.s, world.dev_b.id, world.admin) is None


def test_device_not_found_404(world):
    _expect_404(lambda: assert_device_team_access(world.s, 999_999, world.eng_a))


def test_device_admin_not_found_still_404(world):
    _expect_404(lambda: assert_device_team_access(world.s, 999_999, world.admin))


# ─── assert_device_team_access_async（语义与同步版一致）───

async def test_device_async_same_team_passes(world):
    from app.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        await assert_device_team_access_async(db, world.dev_a.id, world.eng_a)


async def test_device_async_cross_team_404(world):
    from app.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        with pytest.raises(HTTPException) as exc:
            await assert_device_team_access_async(db, world.dev_b.id, world.eng_a)
        assert exc.value.status_code == 404


async def test_device_async_admin_exempt(world):
    from app.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        await assert_device_team_access_async(db, world.dev_b.id, world.admin)


async def test_device_async_not_found_404(world):
    from app.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        with pytest.raises(HTTPException) as exc:
            await assert_device_team_access_async(db, 999_999, world.eng_a)
        assert exc.value.status_code == 404


# ─── assert_vehicle_team_access（vehicle→enterprise→owner_team）───

def test_vehicle_same_team_passes(world):
    assert assert_vehicle_team_access(world.s, world.veh_a.id, world.eng_a) is None


def test_vehicle_cross_team_404(world):
    _expect_404(lambda: assert_vehicle_team_access(world.s, world.veh_b.id, world.eng_a))


def test_vehicle_admin_exempt(world):
    assert assert_vehicle_team_access(world.s, world.veh_b.id, world.admin) is None


def test_vehicle_owner_none_team_404(world):
    """veh_n→ent_n(owner_team_id None) → team 级用户 404。"""
    _expect_404(lambda: assert_vehicle_team_access(world.s, world.veh_n.id, world.eng_a))


def test_vehicle_admin_owner_none_exempt(world):
    assert assert_vehicle_team_access(world.s, world.veh_n.id, world.admin) is None


def test_vehicle_not_found_404(world):
    _expect_404(lambda: assert_vehicle_team_access(world.s, 999_999, world.eng_a))


def test_vehicle_admin_not_found_still_404(world):
    _expect_404(lambda: assert_vehicle_team_access(world.s, 999_999, world.admin))


# ─── assert_driver_team_access（driver→enterprise→owner_team）───

def test_driver_same_team_passes(world):
    assert assert_driver_team_access(world.s, world.drv_a.id, world.eng_a) is None


def test_driver_cross_team_404(world):
    _expect_404(lambda: assert_driver_team_access(world.s, world.drv_b.id, world.eng_a))


def test_driver_admin_exempt(world):
    assert assert_driver_team_access(world.s, world.drv_b.id, world.admin) is None


def test_driver_owner_none_team_404(world):
    """drv_n→ent_n(owner_team_id None) → team 级用户 404。"""
    _expect_404(lambda: assert_driver_team_access(world.s, world.drv_n.id, world.eng_a))


def test_driver_admin_owner_none_exempt(world):
    assert assert_driver_team_access(world.s, world.drv_n.id, world.admin) is None


def test_driver_not_found_404(world):
    _expect_404(lambda: assert_driver_team_access(world.s, 999_999, world.eng_a))


def test_driver_admin_not_found_still_404(world):
    _expect_404(lambda: assert_driver_team_access(world.s, 999_999, world.admin))


# ─── assert_order_team_access（order.station_id→team）───

def test_order_same_team_passes(world):
    assert assert_order_team_access(world.s, world.order_a.id, world.eng_a) is None


def test_order_cross_team_404(world):
    _expect_404(lambda: assert_order_team_access(world.s, world.order_a.id, world.eng_b))


def test_order_admin_exempt(world):
    assert assert_order_team_access(world.s, world.order_b.id, world.admin) is None


def test_order_team_level_not_found_404(world):
    _expect_404(lambda: assert_order_team_access(world.s, 999_999, world.eng_a))


def test_order_admin_skips_existence_known_inconsistency(world):
    """已知契约差异（非安全缺陷）：assert_order_team_access 在 deps.py:274 对
    is_platform_admin 早期 return，不校验订单存在性 —— 与其余 8 个守卫
    （station/enterprise/alarm/device/vehicle/driver 均先查存在性，admin 不存在也 404）
    不一致。admin 为平台级本就全可见，最终结果（调用方后续查询仍会 404）等价，
    此处固化当前行为，提示后续可对齐。
    """
    assert assert_order_team_access(world.s, 999_999, world.admin) is None
