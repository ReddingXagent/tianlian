"""数据导出/备份 API (卡 922b2fba)

GET /admin-data/export?scope=platform|tenant&tenant_id=&mode=export|backup
- scope=platform: 仅平台管理员, 全平台关键业务表
- scope=tenant: 按租户过滤 (Tenant.code → Team.code → Station.team_id 关联链,
  参考 report_mgmt._team_station_clause 思路); team 用户仅可导本租户
- mode=backup 额外附 metadata 块 (generated_at/version/table_schemas)
- 响应为 JSON 附件流 (StreamingResponse + Content-Disposition)
"""
import json
import logging
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.deps import is_platform_admin
from app.api.v1.auth import get_current_user
from app.models.user import User, Team
from app.models.tenant import Tenant
from app.models.station import Station
from app.models.device import Device
from app.models.alarm import Alarm
from app.models.workorder import WorkOrder
from app.models.charging_order import ChargingOrder
from app.services.audit_service import audit_service

logger = logging.getLogger(__name__)

router = APIRouter()

EXPORT_VERSION = "1.0"

# 卡 e5008622: 单表导出行数上限 — .all() 全量 ORM 加载前 count() 预检, 超限拒绝 413 防伪流式 OOM
MAX_EXPORT_ROWS_PER_TABLE = 50000

# 导出时间戳/文件名切日统一用业务时区 (UTC 容器下 16:00 后日期不再跳次日)
_EXPORT_TZ = ZoneInfo("Asia/Shanghai")

# 导出的关键业务表 (顺序即输出顺序); users 导出剥离 password_hash 防泄露
_TABLES = [
    ("teams", Team),
    ("tenants", Tenant),
    ("stations", Station),
    ("devices", Device),
    ("users", User),
    ("alarms", Alarm),
    ("work_orders", WorkOrder),
    ("charging_orders", ChargingOrder),
]

_SENSITIVE_COLUMNS = {"password_hash"}


def _row_to_dict(obj) -> dict:
    """ORM 行 → JSON 可序列化 dict (datetime→isoformat, enum→value)。"""
    out = {}
    for col in sa_inspect(obj).mapper.column_attrs:
        if col.key in _SENSITIVE_COLUMNS:
            continue
        value = getattr(obj, col.key)
        if hasattr(value, "isoformat"):
            value = value.isoformat()
        elif hasattr(value, "value") and not isinstance(value, str):
            value = value.value
        out[col.key] = value
    return out


def _serialize(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "value") and not isinstance(value, str):
        return value.value
    return value


def _resolve_tenant_team_ids(db: Session, tenant: Tenant):
    """租户 → 团队 id 集合 (Tenant.code == Team.code 关联链, 与 tenant.py 同源)。"""
    return [t.id for t in db.query(Team.id).filter(Team.code == tenant.code).all()]


def _build_payload(db: Session, mode: str, label: str, filters: Optional[dict]) -> dict:
    data = {}
    for name, model in _TABLES:
        query = db.query(model)
        if filters and name in filters:
            query = filters[name](query)
        # 卡 e5008622: .all() 全量 ORM 加载前先 count() 预检, 超限拒绝防伪流式 OOM
        # (charging_orders 等大表无行数上限, 全量加载 = ORM对象图+dict+JSON 三份内存)
        count = query.count()
        if count > MAX_EXPORT_ROWS_PER_TABLE:
            raise HTTPException(
                status_code=413,
                detail=f"表 {name} 行数 {count} 超过导出上限 {MAX_EXPORT_ROWS_PER_TABLE}，"
                       f"请按租户/时间范围筛选后导出",
            )
        data[name] = [_row_to_dict(row) for row in query.all()]

    payload = {"scope_label": label, "data": data}
    if mode == "backup":
        payload["metadata"] = {
            "generated_at": datetime.now(_EXPORT_TZ).isoformat(),
            "version": EXPORT_VERSION,
            "table_schemas": {
                name: [c.key for c in sa_inspect(model).mapper.column_attrs
                       if c.key not in _SENSITIVE_COLUMNS]
                for name, model in _TABLES
            },
        }
    return payload


def _export(db: Session, current_user: User, scope: str, tenant_id: Optional[int], mode: str):
    admin = is_platform_admin(current_user)

    if scope == "platform":
        if not admin:
            raise HTTPException(status_code=403, detail="仅平台管理员可导出全平台数据")
        filters = None
        label = "平台"
    else:
        if tenant_id is None:
            raise HTTPException(status_code=400, detail="scope=tenant 必须指定 tenant_id")
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if not tenant:
            raise HTTPException(status_code=404, detail="租户不存在")
        team_ids = _resolve_tenant_team_ids(db, tenant)
        if not admin:
            # team 用户仅可导本租户 (自身 team 须在该租户团队集内)
            if current_user.team_id not in team_ids:
                raise HTTPException(status_code=403, detail="仅可导出本租户数据")
        # 非平台管理员导出时进一步收敛到本 team (租户可能映射多团队)
        scope_team_ids = team_ids if admin else [current_user.team_id]

        stations = db.query(Station.id).filter(
            (Station.tenant_id == tenant.id) | (Station.team_id.in_(scope_team_ids))
        ).all()
        station_ids = [s.id for s in stations]
        devices = db.query(Device.id).filter(Device.station_id.in_(station_ids)).all() if station_ids else []
        device_ids = [d.id for d in devices]

        filters = {
            "stations": lambda q: q.filter(
                (Station.tenant_id == tenant.id) | (Station.team_id.in_(scope_team_ids))),
            "devices": lambda q: q.filter(Device.station_id.in_(station_ids)) if station_ids else q.filter(Device.id == -1),
            "users": lambda q: q.filter(User.team_id.in_(scope_team_ids)),
            "alarms": lambda q: q.filter(Alarm.device_id.in_(device_ids)) if device_ids else q.filter(Alarm.id == -1),
            "work_orders": lambda q: q.filter(WorkOrder.station_id.in_(station_ids)) if station_ids else q.filter(WorkOrder.id == "-1"),
            "charging_orders": lambda q: q.filter(ChargingOrder.station_id.in_(station_ids)) if station_ids else q.filter(ChargingOrder.id == -1),
        }
        label = tenant.name or f"租户{tenant.id}"

    payload = _build_payload(db, mode, label, filters)
    try:
        audit_service.log_crud(
            user_id=current_user.id, username=current_user.username,
            action="export", module="admin_data_ops",
            target_desc=f"数据导出 scope={scope} mode={mode}",
        )
    except Exception:
        pass
    # 中文文件名走 RFC 5987 filename* (Starlette header 仅 latin-1, 中文裸写 500);
    # filename 为 ASCII 兜底 (老客户端)。
    from urllib.parse import quote
    date_str = datetime.now(_EXPORT_TZ).strftime("%Y%m%d")
    ascii_scope = "platform" if scope == "platform" else "tenant"
    filename = f"tianlian_export_{ascii_scope}_{date_str}.json"
    filename_star = f"tianlian_export_{label}_{date_str}.json"

    def _stream():
        yield json.dumps(payload, ensure_ascii=False, default=_serialize)

    return StreamingResponse(
        _stream(),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=\"{filename}\"; filename*=UTF-8''{quote(filename_star)}"},
    )


@router.get("/export")
def export_data(
    scope: str = Query("platform", pattern="^(platform|tenant)$"),
    tenant_id: Optional[int] = Query(None),
    mode: str = Query("export", pattern="^(export|backup)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """数据导出/备份 (JSON 附件流)。"""
    try:
        return _export(db, current_user, scope, tenant_id, mode)
    except HTTPException:
        raise
    except Exception:
        logger.exception("export_data 异常")
        raise HTTPException(status_code=500, detail="导出失败, 请稍后重试")
