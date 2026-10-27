"""
API 依赖注入模块

提供常用的 FastAPI 依赖:
- get_current_user: 获取当前认证用户
- get_db: 数据库会话

Team scoping 辅助（任务卡 1f13817b — 第二层鉴权）:
角色授权（require_role）之后，团队级用户只能读写本 team 的资源；
admin/super_admin 为平台级，豁免 team 过滤。跨团队访问一律 404
（不泄露资源存在），与 require_role 对 ADMIN/SUPER_ADMIN 的放行语义一致。
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, Depends
from sqlalchemy.orm import Session

from app.api.v1.auth import get_current_user
from app.core.database import get_db
from app.models.station import Station
from app.models.user import Team, User

__all__ = [
    "get_current_user",
    "get_db",
    "is_platform_admin",
    "require_platform_admin",
    "assert_station_team_access",
    "team_scope",
    "assert_team_access",
    "resolve_team_filter",
    "assert_enterprise_team_access",
    "assert_alarm_team_access",
    "assert_device_team_access",
    "assert_device_team_access_async",
    "assert_vehicle_team_access",
    "assert_driver_team_access",
    "assert_order_team_access",
    "assert_maintenance_access",
    "resolve_team_type",
    "assert_config_domain_access",
]

# 平台级角色：跨团队可见，豁免 team scoping（与 auth.require_role 一致）
_PLATFORM_ADMIN_ROLES = ("ADMIN", "SUPER_ADMIN")


def is_platform_admin(user: User) -> bool:
    """admin/super_admin 为平台级角色，豁免 team scoping。

    与 auth.require_role 中 ``user_role.upper() in ("ADMIN", "SUPER_ADMIN")``
    的判断保持同源。
    """
    role = user.role.value if hasattr(user.role, "value") else user.role
    return str(role).upper() in _PLATFORM_ADMIN_ROLES


def require_platform_admin(user: User = Depends(get_current_user)) -> User:
    """平台基础设施端点鉴权依赖：非 admin/super_admin → 403（任务卡 55f8d345）。

    证书申请/续期经 certbot 在主机执行（``--nginx`` 动主机 nginx 配置）且
    消耗 Let's Encrypt 速率配额，属平台基础设施，全端点（读+写）一律收紧
    admin only。与 ``is_platform_admin`` / ``auth.require_role`` 同源——
    admin/super_admin 放行，其余一律 403。供 ssl_certificates 等模块复用。
    """
    if not is_platform_admin(user):
        raise HTTPException(status_code=403, detail="需要平台管理员权限")
    return user


def _team_denied(resource_team_id: Optional[int], user: User) -> bool:
    """资源 team 与用户 team 不匹配（含任一为 None）→ 应拒绝。

    admin 由调用方先豁免。None 不视作匹配，避免「无团队用户 ↔ 未分配站点」
    的越权模糊地带——双方都必须有明确的 team_id 且相等才放行。
    """
    return (
        resource_team_id is None
        or user.team_id is None
        or resource_team_id != user.team_id
    )


def assert_station_team_access(db: Session, station_id: int, user: User) -> Station:
    """校验站点归属：admin 豁免；团队级仅可访问本 team 站点。

    站点不存在或跨团队 → 404（不泄露存在）。命中时返回 Station ORM，
    供调用方复用，避免重复查询。
    """
    station = db.query(Station).filter(Station.id == station_id).first()
    if station is None or (not is_platform_admin(user) and _team_denied(station.team_id, user)):
        raise HTTPException(status_code=404, detail="站点不存在")
    return station


def team_scope(user: User) -> Optional[int]:
    """列表查询的 team 过滤值（任务卡 708350b3）。

    - admin/super_admin → None：平台级，不过滤，跨团队全可见；
    - 团队级角色 → user.team_id：仅本 team。

    与 is_platform_admin / require_role 同源。返回 None 时调用方应跳过
    team 过滤，否则按返回值过滤。
    """
    if is_platform_admin(user):
        return None
    return user.team_id


def resolve_team_filter(db: Session, user: User, team_id: Optional[int]) -> Optional[int]:
    """列表 API 可选 ``team_id`` 查询参数解析（卡 2285f54a）。

    供 stations/devices/work-orders 列表按团队维度过滤（Tenants TeamDataView
    运营数据 Tab）复用 teams 域校验语义：

    - ``None`` → 返回 None：不启用 team 维度过滤，调用方沿用既有
      caller-based scoping（行为零变化）；
    - admin 指定任意 team_id → 返回该值（团队不存在 → 404，与
      ``GET /teams/{team_id}/members`` 的 404 语义一致）；
    - 团队级用户指定本 team → 返回该值（与其默认 scoping 等价）；
    - 团队级用户指定他 team → 403：与 assert_* 的 404（被动探测不泄露
      存在）不同，这里是调用方显式指定目标团队，403 更利于前端提示
      权限不足而非误导性的「不存在」。
    """
    if team_id is None:
        return None
    if db.query(Team.id).filter(Team.id == team_id).first() is None:
        raise HTTPException(status_code=404, detail=f"团队 {team_id} 不存在")
    if not is_platform_admin(user) and team_id != user.team_id:
        raise HTTPException(status_code=403, detail="无权查看其他团队数据")
    return team_id


def assert_team_access(user: User, resource_team_id: Optional[int]) -> None:
    """单资源归属校验（任务卡 708350b3）：admin 豁免；团队级不匹配 → 404。

    用于按主键取到的非 station 资源（监管配置/开票平台/巡检计划/值班规则
    等）：复用 _team_denied 的「双方必须有明确 team_id 且相等」语义，
    不匹配一律 404，不泄露资源存在。
    """
    if not is_platform_admin(user) and _team_denied(resource_team_id, user):
        raise HTTPException(status_code=404, detail="资源不存在")


def assert_enterprise_team_access(db: Session, enterprise_id: int, user: User):
    """企业归属校验（任务卡 708350b3）：enterprise.owner_team_id 必须匹配
    user.team_id；admin 豁免。企业不存在或跨团队 → 404。返回 Enterprise ORM。

    fleet 模块按 enterprise_id 查询/写入前必须调用，杜绝攻击者传入他人
    enterprise_id 越权读写车队数据。Enterprise import 延迟到函数内，
    避免 deps 顶层循环导入。
    """
    from app.models.enterprise import Enterprise

    ent = db.query(Enterprise).filter(Enterprise.id == enterprise_id).first()
    if ent is None or (not is_platform_admin(user) and _team_denied(ent.owner_team_id, user)):
        raise HTTPException(status_code=404, detail="企业不存在")
    return ent


def assert_alarm_team_access(db: Session, alarm_id: int, user: User) -> None:
    """告警归属校验（任务卡 ed509541）：经 alarm.station_id→team，station_id 缺失时
    回退 device→station→team。admin 豁免；告警不存在或跨团队 → 404。

    Alarm 无 team_id 列，归属经其关联 station 间接判定。供 alarms.py /
    alarm_notices.py 的详情/写端点复用，避免两处重复实现。
    """
    from app.models.alarm import Alarm
    from app.models.device import Device

    a = db.query(Alarm.station_id, Alarm.device_id).filter(Alarm.id == alarm_id).first()
    if a is None:
        raise HTTPException(status_code=404, detail="告警不存在")
    if is_platform_admin(user):
        return
    team_id = None
    if a.station_id:
        team_id = db.query(Station.team_id).filter(Station.id == a.station_id).scalar()
    elif a.device_id:
        team_id = (
            db.query(Station.team_id)
            .join(Device, Device.station_id == Station.id)
            .filter(Device.id == a.device_id)
            .scalar()
        )
    if _team_denied(team_id, user):
        raise HTTPException(status_code=404, detail="告警不存在")


def assert_device_team_access(db: Session, device_id: int, user: User) -> None:
    """设备归属校验（任务卡 b640bdd9 — 三批）：device.station_id→team。admin 豁免；
    设备不存在或跨团队 → 404（不泄露存在）。

    Device 无 team_id 列，归属经其挂载站点间接判定。供 analytics/v2g/telemetry/
    efficiency 等按 device_id 查询或写入的端点复用，避免逐模块重复 device→station→team
    解析。
    """
    from app.models.device import Device

    d = db.query(Device.station_id).filter(Device.id == device_id).first()
    if d is None:
        raise HTTPException(status_code=404, detail="设备不存在")
    if is_platform_admin(user):
        return
    team_id = None
    if d.station_id:
        team_id = db.query(Station.team_id).filter(Station.id == d.station_id).scalar()
    if _team_denied(team_id, user):
        raise HTTPException(status_code=404, detail="设备不存在")


async def assert_device_team_access_async(db, device_id: int, user: User) -> None:
    """assert_device_team_access 的异步版（卡52f731ac）。

    语义与同步版完全一致（device.station_id→team, admin 豁免, 跨团队/不存在 → 404），
    供含真实 await、改用 AsyncSession 的端点（predictive_maintenance 等）复用。
    同步版保留：10+ 同步端点（v2g/telemetry/analytics/diagnosis...）仍在用。
    """
    from app.models.device import Device
    from sqlalchemy import select

    d = (await db.execute(select(Device.station_id).where(Device.id == device_id))).first()
    if d is None:
        raise HTTPException(status_code=404, detail="设备不存在")
    if is_platform_admin(user):
        return
    team_id = None
    if d.station_id:
        team_id = (await db.execute(select(Station.team_id).where(Station.id == d.station_id))).scalar()
    if _team_denied(team_id, user):
        raise HTTPException(status_code=404, detail="设备不存在")


def assert_vehicle_team_access(db: Session, vehicle_id: int, user: User) -> None:
    """车辆归属校验（任务卡 ab5c5f17 — 五批）：vehicle→enterprise→owner_team。
    admin 豁免；车辆不存在或跨团队 → 404（不泄露存在）。

    EnterpriseVehicle 无 team_id 列，归属经其挂载企业间接判定。供
    enterprise_vehicles / fleet_vehicle_profiles / carbon_emission 等按
    vehicle_id 查询或写入的端点复用，避免逐模块重复 vehicle→enterprise→team 解析。
    """
    from app.models.enterprise import Enterprise
    from app.models.enterprise_vehicle import EnterpriseVehicle

    v = (
        db.query(EnterpriseVehicle.enterprise_id)
        .filter(EnterpriseVehicle.id == vehicle_id)
        .first()
    )
    if v is None:
        raise HTTPException(status_code=404, detail="车辆不存在")
    if is_platform_admin(user):
        return
    team_id = (
        db.query(Enterprise.owner_team_id)
        .filter(Enterprise.id == v.enterprise_id)
        .scalar()
    )
    if _team_denied(team_id, user):
        raise HTTPException(status_code=404, detail="车辆不存在")


def assert_driver_team_access(db: Session, driver_id: int, user: User) -> None:
    """司机归属校验（任务卡 ab5c5f17 — 五批）：driver→enterprise→owner_team。
    admin 豁免；司机不存在或跨团队 → 404（不泄露存在）。

    FleetDriver 无 team_id 列，归属经其挂载企业间接判定。供 fleet_attendance
    等按 driver_id 查询或写入的端点复用。
    """
    from app.models.enterprise import Enterprise
    from app.models.fleet_driver import FleetDriver

    d = (
        db.query(FleetDriver.enterprise_id)
        .filter(FleetDriver.id == driver_id)
        .first()
    )
    if d is None:
        raise HTTPException(status_code=404, detail="司机不存在")
    if is_platform_admin(user):
        return
    team_id = (
        db.query(Enterprise.owner_team_id)
        .filter(Enterprise.id == d.enterprise_id)
        .scalar()
    )
    if _team_denied(team_id, user):
        raise HTTPException(status_code=404, detail="司机不存在")


def assert_order_team_access(db: Session, order_id: int, user: User) -> None:
    """充电订单归属校验（任务卡 ab5c5f17 — 五批下半）：order.station_id→team。
    admin 豁免；订单不存在或跨团队 → 404（不泄露存在）。

    ChargingOrder 无 team_id 列，归属经其挂载站点间接判定。供 operate/orders
    等按 order_id 查询详情/曲线/写操作的端点复用，与 charging_orders 模块的
    私有 ``_assert_order_team_access`` 同源（该模块已治理，此处提为公共 helper
    供 operate 域复用，避免重复实现 order→station→team 解析）。
    """
    from app.models.charging_order import ChargingOrder

    if is_platform_admin(user):
        return
    team_id = (
        db.query(Station.team_id)
        .join(ChargingOrder, ChargingOrder.station_id == Station.id)
        .filter(ChargingOrder.id == order_id)
        .scalar()
    )
    if _team_denied(team_id, user):
        raise HTTPException(status_code=404, detail="充电订单不存在")


# ─── 运维分离架构: 运维访问校验 (卡 00d7d49a) ──────────────────────────────────
# 运营公司 (OPS_COMPANY) 可两种模式运维自家场站:
#   ① 自运维 — 运营+运维同一团队 (Station.team_id == 运营公司 team_id)
#   ② 委外运维 — 经 StationMaintenanceGrant 把运维权授予第三方 MAINTENANCE_TEAM
# 本 helper 把「该用户能否对 station_id 做某 action」收口, 供设备监控/控制/告警/工单
# 等运维端点复用。越权/无授权/站点不存在 → 一律 404 (不泄露存在), 与 assert_*_team_access 同源。


def assert_maintenance_access(
    db: Session, station_id: int, user: User, action: str = "control"
) -> None:
    """运维访问校验: 当前用户能否对 station_id 执行 action。

    action ∈ {"monitor"(只读), "control"(写/控制)}。

    放行条件 (任一):
      - 平台管理员 (admin/super_admin);
      - 用户属 OPS_COMPANY 且该站归属本 team (自运维模式①);
      - 用户属 MAINTENANCE_TEAM 且持有该站 active grant, 且 scope 允许 action:
          · full → monitor + control
          · monitoring_only → 仅 monitor
          · maintenance_only → 仅 control

    站点不存在 / 无授权 / scope 不足 → 404 (不泄露存在)。

    Station / Team / StationMaintenanceGrant 延迟导入避免循环。
    """
    from app.models.station import Station
    from app.models.user import Team, TeamType
    from app.models.station_maintenance_grant import (
        StationMaintenanceGrant, GrantStatus, SCOPE_ALLOWED_ACTIONS,
    )

    station = db.query(Station).filter(Station.id == station_id).first()
    # 站点不存在 → 404 (不泄露存在)
    if station is None:
        raise HTTPException(status_code=404, detail="站点不存在")

    # 平台管理员放行
    if is_platform_admin(user):
        return

    user_team_id = user.team_id
    if user_team_id is None:
        raise HTTPException(status_code=404, detail="站点不存在")

    # 解析用户 team.type (显式查 DB, 避免异步上下文 lazy-load)
    team_type = db.query(Team.type).filter(Team.id == user_team_id).scalar()
    team_type_val = team_type.value if hasattr(team_type, "value") else team_type

    # 模式① 自运维: 运营公司对自己名下场站全权
    if team_type_val == TeamType.OPS_COMPANY.value and station.team_id == user_team_id:
        return

    # 模式② 委外运维: 运维团队须持有 active grant 且 scope 允许 action
    if team_type_val == TeamType.MAINTENANCE_TEAM.value:
        grant = (
            db.query(StationMaintenanceGrant)
            .filter(
                StationMaintenanceGrant.station_id == station_id,
                StationMaintenanceGrant.maintenance_team_id == user_team_id,
                StationMaintenanceGrant.status == GrantStatus.ACTIVE,
            )
            .first()
        )
        if grant is not None and not _grant_expired(grant):
            allowed = SCOPE_ALLOWED_ACTIONS.get(grant.scope, set())
            if action in allowed:
                return

    # 其余一律 404 (不泄露存在): 包括未授权的运维团队 / scope 不足 / 车队等其它 type
    raise HTTPException(status_code=404, detail="站点不存在")


def _grant_expired(grant) -> bool:
    """grant 是否已过期 (status=active 但 expires_at 早于当前 UTC 墙钟)。

    naive/aware 安全: expires_at aware → 转 UTC 再去 tz; naive → 原样;
    统一与 naive UTC 墙钟比较 (SQLite DateTime 存 naive)。expires_at 为空 →
    永不过期。不修改 grant.status (读路径不写 DB), 仅作访问判定。
    """
    exp = grant.expires_at
    if exp is None:
        return False
    exp_naive = exp.astimezone(timezone.utc).replace(tzinfo=None) if exp.tzinfo else exp
    return exp_naive < datetime.now(timezone.utc).replace(tzinfo=None)


# ─── 配置域 team.type 防线 (卡 cf614348) ──────────────────────────────────────
# 平台 → 运营公司 → 运维团队/车队 三层组织下, 不同 Team.type 可访问的配置域由
# scope_matrix 收口。本组 helper 把「当前用户 → team_type → 配置域白名单 → 放行/403」
# 收敛为可复用的请求处理层校验, 供 /system-config、/notification-configs 等 config
# 端点强制调用, 杜绝车队/运维团队越权读写运营公司级 (支付/发票/电价) 配置。


def resolve_team_type(db: Session, user: User) -> str:
    """解析配置访问主体键。

    - 平台管理员 (admin/super_admin) → ``"platform_admin"``;
    - 否则取 ``user.team.type`` (经 team_id 显式查 DB, 避免异步上下文 lazy-load);
    - 无 team / team 无 type → ``"unknown"`` (最小权限, 空白名单)。

    返回值用于查 CONFIG_SCOPE_MATRIX 等矩阵。
    """
    if is_platform_admin(user):
        return "platform_admin"
    if user.team_id is None:
        return "unknown"
    from app.models.user import Team

    t = db.query(Team.type).filter(Team.id == user.team_id).scalar()
    if t is None:
        return "unknown"
    return t.value if hasattr(t, "value") else str(t)


def assert_config_domain_access(db: Session, user: User, domain: str) -> None:
    """配置域访问校验: domain 不在当前用户 team_type 白名单内 → 403。

    平台管理员 (矩阵值 ``"*"``) 全放行。用于 config 类端点按 Team.type 强制收口。
    """
    from app.core.scope_matrix import get_team_config_scope

    scope = get_team_config_scope(resolve_team_type(db, user))
    if scope == "*" or domain in scope:
        return
    raise HTTPException(
        status_code=403,
        detail=f"配置域 {domain} 超出当前团队权限",
    )
