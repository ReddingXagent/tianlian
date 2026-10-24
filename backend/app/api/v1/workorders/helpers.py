"""工单 WS 广播 / 团队归属校验 / 评价序列化 辅助函数 — 从原 workorders.py 拆出 (卡 1ed83abf)。

对外符号由包 ``__init__`` 重导出。team scoping 逻辑 (任务卡 ed509541) 原样保留。
"""
import asyncio

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.api.deps import is_platform_admin
from app.models.station import Station
from app.models.user import User
from app.models.workorder import WorkOrder
from app.ws.routes import broadcast_workorder_to_all as broadcast_workorder


def _broadcast_wo(db: Session, event: str, wo_data: dict):
    """同步广播工单WS事件 (卡 434f741a: 按工单归属 team 作用域过滤)

    team_id 在调度前同步查好 (DB 查询不进协程); 工单无归属站点 → None,
    语义=只发平台 admin 连接 (见 ws_manager.broadcast_team_scoped)。
    保持原 ensure_future / run_until_complete 双路径结构, 仅换目标协程。
    """
    try:
        team_id = _workorder_team_id(db, wo_data.get("id"))
        payload = {"event": event, **wo_data}
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(broadcast_workorder(payload, team_id=team_id))
        else:
            loop.run_until_complete(broadcast_workorder(payload, team_id=team_id))
    except Exception:
        try:
            loop2 = asyncio.new_event_loop()
            loop2.run_until_complete(broadcast_workorder(payload, team_id=team_id))
            loop2.close()
        except Exception:
            pass  # WS广播不阻塞API


# ─── 团队归属校验（任务卡 ed509541）───
# workorder 经 station 间接归属 team（自身无 team_id 列）；
# admin/super_admin 平台级豁免；跨团队一律 404（不泄露存在）。


def _workorder_team_id(db: Session, workorder_id: str):
    """workorder → station.team_id（经 join）；工单/站点不存在或未挂站点 → None。"""
    row = (
        db.query(Station.team_id)
        .join(WorkOrder, WorkOrder.station_id == Station.id)
        .filter(WorkOrder.id == workorder_id)
        .first()
    )
    return row[0] if row else None


def _check_workorder_team(db: Session, workorder_id: str, user: User, msg: str = "工单不存在") -> None:
    """非 admin 校验 workorder 经 station 归属本 team；不存在/跨团队/未挂站点 → 404。"""
    if is_platform_admin(user):
        return
    tid = _workorder_team_id(db, workorder_id)
    if tid is None or user.team_id is None or tid != user.team_id:
        raise HTTPException(status_code=404, detail=msg)


def _serialize_rating(rec) -> dict:
    """序列化评价记录（含操作人追踪字段）。"""
    avg = round((rec.response_rating + rec.quality_rating + rec.attitude_rating) / 3, 2)
    return {
        "id": rec.id, "order_id": rec.order_id,
        "response_rating": rec.response_rating,
        "quality_rating": rec.quality_rating,
        "attitude_rating": rec.attitude_rating,
        "average_rating": avg,
        "comment": rec.comment,
        "user_id": rec.user_id,          # 评价人
        "verifier_id": rec.verifier_id,  # 验收人
        "created_at": rec.created_at.isoformat() if rec.created_at else None,
    }
