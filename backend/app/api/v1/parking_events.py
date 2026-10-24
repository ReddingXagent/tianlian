"""
占位事件接入端点 — 无人值守占位费自动化 (工作卡 f0db2036)

⚠️ 命名一致性(丁哥定调): 本端点路径用 parking(沿用既有命名避免破坏面), 但语义是
   「占位费」(占用充电车位的费用), 不是停车费。停车费归停车场/道闸系统, 平台不收。
   现有 parking pricing(ParkingPrice) 语义即站点占位费率, 复用其计费逻辑。

端点:
- POST /api/v1/parking/events        外部车牌识别系统上报单条占位事件(车牌+起止时间)
- POST /api/v1/parking/events/batch  批量上报

数据流: 外部识别系统最终数据 → ingest_parking_event(幂等建/更新事件)
        → exit_at 非空 → settle_occupancy_event(占位费计费联动)

鉴权: 复用 get_current_gateway_or_user(X-API-Key 网关设备态 / Bearer 用户态)。
- 网关态(外部 ALPR 系统): 仅校验站点存在
- 用户态: 叠加 team scoping(assert_station_team_access, 跨团队 → 404)

MQTT: 丁哥要求"复用 gateway 设备接入"。现 app/gateway/mqtt.py 为出站协议适配器抽象,
无 MQTT broker 订阅基础设施(全仓外部推送均走 HTTP POST)。本端点的处理逻辑已抽到
service.ingest_parking_event / settle_occupancy_event, 未来接 MQTT broker 后,
topic handler 直接调用这两个函数即可, 鉴权复用同一 GatewayApiKey 体系。
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional, Literal

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.tasks.tz_utils import to_aware_biz_tz
from app.core.response import success_response
from app.models.station import Station
from app.models.user import User
from app.api.deps import assert_station_team_access
from app.api.v1.telemetry import get_current_gateway_or_user
from app.services.occupancy_fee_service import (
    ingest_parking_event, settle_occupancy_event,
)

router = APIRouter()

logger = logging.getLogger(__name__)


class ParkingEventReport(BaseModel):
    """外部车牌识别系统上报的占位事件(最终数据: 车牌+起止时间)。"""
    plate_number: str = Field(..., min_length=1, max_length=20, description="车牌号")
    station_id: int = Field(..., description="站点ID")
    enter_at: datetime = Field(..., description="进场时间")
    exit_at: Optional[datetime] = Field(None, description="离场时间, 缺省=未离场")
    camera_id: Optional[str] = Field(None, max_length=64, description="识别设备标识(追溯用)")
    source: Literal["alpr", "charging_estimate"] = Field("alpr", description="来源: alpr(识别系统) / charging_estimate(推算)")


class ParkingEventBatch(BaseModel):
    """批量占位事件上报。"""
    events: List[ParkingEventReport] = Field(..., min_length=1, max_length=500)


def _check_station_access(db: Session, station_id: int, caller) -> None:
    """站点存在性 + team 归属校验。

    用户态(Bearer): assert_station_team_access — 站点不存在或跨团队 → 404(不泄露存在)。
    网关态(X-API-Key, 外部 ALPR 系统): 仅校验站点存在 → 不存在 404。
    """
    if isinstance(caller, User):
        # 内含站点存在 + team 归属校验, 失败均 404
        assert_station_team_access(db, station_id, caller)
        return
    # 网关态: 仅校验站点存在
    if not db.query(Station).filter(Station.id == station_id).first():
        raise HTTPException(status_code=404, detail="站点不存在")


def _event_to_dict(ev) -> dict:
    return {
        "id": ev.id,
        "plate_number": ev.plate_number,
        "station_id": ev.station_id,
        "enter_at": ev.enter_at.isoformat() if ev.enter_at else None,
        "exit_at": ev.exit_at.isoformat() if ev.exit_at else None,
        "source": ev.source.value if ev.source else None,
        "match_order_id": ev.match_order_id,
        "occupancy_minutes": ev.occupancy_minutes or 0,
        "fee_status": ev.fee_status.value if ev.fee_status else None,
        "fee_amount": float(ev.fee_amount) if ev.fee_amount is not None else 0.0,
    }


def _ingest_and_settle(db: Session, body: ParkingEventReport) -> dict:
    """ingest 事件; exit_at 非空触发占位费计费联动; 返回序列化 dict(未 commit, 调用方提交)。

    卡 5a18d1ee: enter_at/exit_at 落库统一 naive-UTC (与 charging_sessions 卡 f7422bbc
    同口径)。上报 aware/naive 混传: aware(任意 tz) 真换算 UTC; naive 先按业务时区
    表面解释(to_aware_biz_tz, 上游识别系统在国内, naive 即上海墙钟) 再转 UTC,
    不再直接落 body 原值 — 否则 naive 上海墙钟被下游当 UTC 解读, 整体错位 8h。
    """
    from datetime import timezone

    def _to_utc_naive(dt: Optional[datetime]) -> Optional[datetime]:
        if dt is None:
            return None
        return to_aware_biz_tz(dt).astimezone(timezone.utc).replace(tzinfo=None)

    event = ingest_parking_event(
        db,
        plate_number=body.plate_number,
        station_id=body.station_id,
        enter_at=_to_utc_naive(body.enter_at),
        exit_at=_to_utc_naive(body.exit_at),
        source=body.source,
    )
    # 占位费在离场时结算(丁哥: 识别系统发来起止时间)
    if event.exit_at is not None:
        settle_occupancy_event(db, event)
    db.flush()
    return _event_to_dict(event)


@router.post("/parking/events")
def report_parking_event(
    body: ParkingEventReport,
    db: Session = Depends(get_db),
    caller: User = Depends(get_current_gateway_or_user),
):
    """接收外部车牌识别系统单条占位事件 → 幂等建/更新事件 + 离场触发占位费计费。"""
    try:
        _check_station_access(db, body.station_id, caller)
        data = _ingest_and_settle(db, body)
        db.commit()
        return success_response(data)
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        logger.exception("report_parking_event 异常")
        raise HTTPException(status_code=500, detail="服务器内部错误，请稍后重试")


@router.post("/parking/events/batch")
def report_parking_events(
    body: ParkingEventBatch,
    db: Session = Depends(get_db),
    caller: User = Depends(get_current_gateway_or_user),
):
    """批量接收占位事件(单事务, 任一站点校验失败整体回滚)。"""
    try:
        # 预校验全部站点(任一不存在/越权 → 整批 4xx, 不部分落库)
        for ev in body.events:
            _check_station_access(db, ev.station_id, caller)
        results = [_ingest_and_settle(db, ev) for ev in body.events]
        db.commit()
        return success_response({"events": results, "count": len(results)})
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        logger.exception("report_parking_events 异常")
        raise HTTPException(status_code=500, detail="服务器内部错误，请稍后重试")
