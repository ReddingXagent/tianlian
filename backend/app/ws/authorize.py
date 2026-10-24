"""
WebSocket 授权作用域层 (卡 e2ad0b7d — IDOR 旁路修复)

app/ws/auth.py 闭合了认证缺口 (你是谁), 但带路径参数的 /ws/v1/* 端点
(digital-twin station/device, fleet/queue, fleet/v2g) 认证通过后零授权:
任意团队用户可连任意 station_id/device_id/enterprise_id 获取他人团队
实时运营数据 —— HTTP 层同数据有 _check_station_team / _check_device_team
/ assert_enterprise_team_access 守卫, WS 是旁路面。

本模块提供 WS 层授权原语, 归属推导复用 HTTP 层同款逻辑 (勿另起炉灶):
  - station → team_id / device → station → team_id: digital_twin.py 的
    _station_team_id / _device_team_id 同模式
  - enterprise → owner_team_id: deps.assert_enterprise_team_access 同语义
  - admin/super_admin 平台级豁免: deps.is_platform_admin

与 HTTP 层差异: HTTP 守卫抛 HTTPException(404), WS 端点握手阶段无法转
HTTP 异常, 故本层返回 bool, 失败由本层 close(4003) —— 4001 是认证
拒绝码, 4003 区分「认证通过但越权」。资源不存在也统一 4003, 不泄露
存在性 (与 HTTP 404 惯例等价)。

DB 查询经 asyncio.to_thread + 独立 Session, 先例见 auth.py 的
_lookup_active_user_sync (避免阻塞事件循环, 卡67523030)。
"""
import asyncio
from typing import Optional

from fastapi import WebSocket

from app.api.deps import _PLATFORM_ADMIN_ROLES

# WebSocket 授权拒绝码 (应用自定义范围 4000-4999; 4001=未认证)
WS_SCOPE_DENIED_CODE = 4003
_DENY_REASON = "无权访问"


def _is_platform_admin_role(role) -> bool:
    """is_platform_admin (deps.py) 的 role 字符串变体 —— 授权层只持有
    authenticate_websocket 返回的 user dict (role 已剥 ORM), 复用同源
    平台角色常量, 避免两处硬编码漂移。"""
    return str(role).upper() in _PLATFORM_ADMIN_ROLES


def _lookup_user_team_sync(user_id: int) -> Optional[int]:
    """同步DB查询: 用户归属 team_id, 异常/不存在 → None。"""
    import app.core.database as db_module
    from app.models.user import User

    session = db_module.SessionLocal()
    try:
        row = session.query(User.team_id).filter(User.id == user_id).first()
        return row[0] if row else None
    except Exception:
        return None
    finally:
        session.close()


def _lookup_resource_team_sync(station_id: Optional[int] = None,
                               device_id: Optional[int] = None,
                               enterprise_id: Optional[int] = None):
    """同步DB查询: 资源归属 team_id, 查不到/异常 → None (fail-closed)。

    - station → team_id: digital_twin._station_team_id 同模式
    - device → station → team_id (经 join 单次查询): digital_twin._device_team_id 同模式
    - enterprise → owner_team_id: deps.assert_enterprise_team_access 同语义
    """
    import app.core.database as db_module
    from app.models.device import Device
    from app.models.enterprise import Enterprise
    from app.models.station import Station

    session = db_module.SessionLocal()
    try:
        if station_id is not None:
            row = session.query(Station.team_id).filter(Station.id == station_id).first()
            return row[0] if row else None
        if device_id is not None:
            row = (
                session.query(Station.team_id)
                .join(Device, Device.station_id == Station.id)
                .filter(Device.id == device_id)
                .first()
            )
            return row[0] if row else None
        if enterprise_id is not None:
            row = session.query(Enterprise.owner_team_id).filter(Enterprise.id == enterprise_id).first()
            return row[0] if row else None
        return None
    except Exception:
        return None
    finally:
        session.close()


def _user_team_matches(user: dict, resource_team_id: Optional[int]) -> bool:
    """deps._team_denied 的 bool 变体: 平台管理员豁免; 双方 team_id
    明确且相等才放行。资源不存在 (None) 同样拒绝, 不泄露存在性。"""
    if _is_platform_admin_role(user.get("role")):
        return True
    user_team = _lookup_user_team_sync(user.get("user_id"))
    return (
        resource_team_id is not None
        and user_team is not None
        and resource_team_id == user_team
    )


async def _authorize(websocket: WebSocket, user: dict, resource_team_id: Optional[int]) -> bool:
    """统一收口: 校验通过 → True; 否则 close(4003) 并返回 False。"""
    allowed = await asyncio.to_thread(_user_team_matches, user, resource_team_id)
    if not allowed:
        await websocket.close(code=WS_SCOPE_DENIED_CODE, reason=_DENY_REASON)
        return False
    return True


async def authorize_station(websocket: WebSocket, user: dict, station_id: int) -> bool:
    """站点归属授权 (HTTP 层 _check_station_team 的 WS 变体)。"""
    team_id = await asyncio.to_thread(_lookup_resource_team_sync, station_id=station_id)
    return await _authorize(websocket, user, team_id)


async def authorize_device(websocket: WebSocket, user: dict, device_id: int) -> bool:
    """设备归属授权 (HTTP 层 _check_device_team 的 WS 变体, 经 station 推导)。"""
    team_id = await asyncio.to_thread(_lookup_resource_team_sync, device_id=device_id)
    return await _authorize(websocket, user, team_id)


async def device_in_scope(user: dict, device_id: int) -> bool:
    """subscribe_device 消息级设备归属校验: 不通过由调用方发 error 消息并跳过
    订阅 (不断连, 与端点级 close 4003 策略区分)。"""
    team_id = await asyncio.to_thread(_lookup_resource_team_sync, device_id=device_id)
    return await asyncio.to_thread(_user_team_matches, user, team_id)


async def authorize_enterprise(websocket: WebSocket, user: dict, enterprise_id: int) -> bool:
    """企业归属授权 (HTTP 层 assert_enterprise_team_access 的 WS 变体,
    owner_team_id 必须匹配 user.team_id, admin 豁免)。"""
    team_id = await asyncio.to_thread(_lookup_resource_team_sync, enterprise_id=enterprise_id)
    return await _authorize(websocket, user, team_id)
