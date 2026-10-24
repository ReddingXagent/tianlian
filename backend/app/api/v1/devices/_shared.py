"""设备管理 API 共享定义（拆分自原 devices.py）。

仅存放跨子模块复用的模块级对象：logger、设备 team 归属校验 helper、
以及 router 级鉴权依赖列表。端点本身拆分到同包各子模块，其中被单测 patch 的
端点（control_device / get_maintenance_due / run_maintenance_check）留在包
``__init__``，以保证 ``patch("app.api.v1.devices.X")`` 仍命中本命名空间。
"""
import logging

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import is_platform_admin
from app.api.v1.auth import get_current_user
from app.middleware.permission import require_write_permission
from app.models.device import Device
from app.models.station import Station
from app.models.user import User


logger = logging.getLogger("app.api.v1.devices")


# 设备 router 级依赖（原 devices.py 顶层 router 的 dependencies）
_ROUTER_DEPENDENCIES = [Depends(get_current_user), Depends(require_write_permission("device:edit"))]


# ─── 团队归属校验（任务卡 ed509541）───
# device 经 station 间接归属 team（device 自身无 team_id 列）；
# admin/super_admin 平台级豁免；跨团队一律 404（不泄露存在），
# 与 is_platform_admin / assert_station_team_access 同源。


def _device_team_id(db: Session, device_id: int):
    """device → station.team_id（经 join，单次查询）；device/station 不存在 → None。"""
    row = (
        db.query(Station.team_id)
        .join(Device, Device.station_id == Station.id)
        .filter(Device.id == device_id)
        .first()
    )
    return row[0] if row else None


def _check_device_team(db: Session, device_id: int, user: User, msg: str = "设备不存在") -> None:
    """非 admin 校验 device 经 station 归属本 team；不存在/跨团队 → 404。"""
    if is_platform_admin(user):
        return
    tid = _device_team_id(db, device_id)
    if tid is None or user.team_id is None or tid != user.team_id:
        raise HTTPException(status_code=404, detail=msg)


# ─── async 版 team 校验 (卡 3f5b3d6b) ───
# async 端点改用 AsyncSession 后, 同步 _device_team_id/_check_device_team
# 中的 db.query() 不兼容, 需 async 版本用 select() + await db.execute()。


async def _device_team_id_async(db: AsyncSession, device_id: int):
    """async 版 _device_team_id (卡 3f5b3d6b)。"""
    result = await db.execute(
        select(Station.team_id)
        .join(Device, Device.station_id == Station.id)
        .where(Device.id == device_id)
    )
    row = result.first()
    return row[0] if row else None


async def _check_device_team_async(db: AsyncSession, device_id: int, user: User, msg: str = "设备不存在") -> None:
    """async 版 _check_device_team (卡 3f5b3d6b)。"""
    if is_platform_admin(user):
        return
    tid = await _device_team_id_async(db, device_id)
    if tid is None or user.team_id is None or tid != user.team_id:
        raise HTTPException(status_code=404, detail=msg)


# ─── 运维分离架构 (卡 00d7d49a) ────────────────────────────────────────────
# 设备写端点 (控制) 改用 assert_maintenance_access, 在原 OPS_COMPANY 自运维语义之上
# 额外开放 MAINTENANCE_TEAM 委外运维通道 (持有 active grant 且 scope 允许 control)。


def _device_station_id(db: Session, device_id: int):
    """device → station_id (单次查询); device 不存在 → None。"""
    row = db.query(Device.station_id).filter(Device.id == device_id).first()
    return row[0] if row else None


def _check_device_maintenance_access(db: Session, device_id: int, user: User) -> None:
    """设备控制等写端点的运维访问校验 (卡 00d7d49a)。

    经 device→station→assert_maintenance_access(action="control") 判定:
      - admin 放行;
      - OPS_COMPANY 自运维 (station 归属本 team) 放行;
      - MAINTENANCE_TEAM 持有该站 active grant 且 scope 允许 control 放行;
      - 否则 → 404 (不泄露存在)。

    与 _check_device_team 向后兼容 (原自运维场景不变), 额外开放委外运维通道。
    assert_maintenance_access 延迟导入避免循环。
    """
    from app.api.deps import assert_maintenance_access

    station_id = _device_station_id(db, device_id)
    if station_id is None:
        raise HTTPException(status_code=404, detail="设备不存在")
    assert_maintenance_access(db, station_id, user, action="control")
