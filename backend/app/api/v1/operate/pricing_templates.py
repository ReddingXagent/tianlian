"""费率模板 — 模板化定价 + 绑定站点/设备 + 下发/校验闭环 (2026-10-09 丁哥需求)

- pricing_templates 表: 模板(时段明细 periods JSON: name/start/end/price/serviceFee/kind)
- 绑定: device_id(精确) > station_id(站点) > is_default(平台默认)
- 下发: 按绑定设备经深圳巴士 0x16 计费模板推送(电价+服务费), 复用 SZBUS 证据链
- 校验: 桩端上行证据(0x02 ACK / 0x25 执行电价 / 0x06 版本)与模板比对 → 已更新/未更新
"""
import json
import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.core.database import get_db, engine
from app.api.v1.auth import get_current_user
from app.models.device import Device
from app.models.user import User
from app.core.response import success_response

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(get_current_user)])

_ENSURE_SQL = """
CREATE TABLE IF NOT EXISTS pricing_templates (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    kind VARCHAR(20) NOT NULL DEFAULT 'charging',
    periods JSONB NOT NULL DEFAULT '[]',
    station_id INT NULL,
    device_id INT NULL,
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    occupancy_fee NUMERIC(10,4) NULL,
    reservation_fee NUMERIC(10,4) NULL,
    occupancy_rule JSONB NULL,      -- 占桩费规则: free_minutes/unit/price/cap/busy_double
    updated_by VARCHAR(100),
    updated_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now()
)
"""


def _ensure_table():
    try:
        with engine.begin() as conn:
            conn.execute(text(_ENSURE_SQL))
    except Exception as e:
        logger.warning("pricing_templates 建表失败: %s", e)


class PeriodItem(BaseModel):
    name: str = ""
    start: str = "00:00"
    end: str = "23:59"
    price: float = 0.0        # 时段电价(充电费模板) / 电价(V2G模板)
    serviceFee: float = 0.0   # 时段服务费(充电费模板)
    kind: str = "buy"         # charging 模板忽略; v2g 模板 buy=购电 sell=放电
    period_type: str = "flat" # sharp尖峰/peak峰/flat平/valley谷/deep_valley深谷
    start_date: Optional[str] = None  # 尖峰生效起始日 YYYY-MM-DD(仅尖峰, 政策性电价)
    end_date: Optional[str] = None    # 尖峰生效截止日 YYYY-MM-DD(仅尖峰)


class TemplatePayload(BaseModel):
    name: str
    kind: str = "charging"    # charging | v2g
    periods: List[PeriodItem] = []
    station_id: Optional[int] = None
    device_id: Optional[int] = None
    is_default: bool = False
    occupancy_fee: Optional[float] = None
    occupancy_rule: Optional[dict] = None  # {free_minutes, unit: minute|hour, price, cap?, busy_double?}    # 占桩费(元), 启用即>0
    reservation_fee: Optional[float] = None  # 预约费(元), 启用即>0


def _row_to_dict(r) -> dict:
    periods = r.get("periods")
    if isinstance(periods, str):
        try:
            periods = json.loads(periods or "[]")
        except Exception:
            periods = []
    ua = r.get("updated_at")
    return {
        "id": r.get("id"), "name": r.get("name"), "kind": r.get("kind"),
        "periods": periods or [],
        "station_id": r.get("station_id"), "device_id": r.get("device_id"),
        "is_default": r.get("is_default"),
        "occupancy_fee": r.get("occupancy_fee"), "reservation_fee": r.get("reservation_fee"),
        "updated_by": r.get("updated_by"),
        "updated_at": ua.isoformat() if hasattr(ua, "isoformat") else ua,
    }


def _fetch_templates(db: Session, kind: Optional[str] = None, device_id: Optional[int] = None,
                     station_id: Optional[int] = None) -> list:
    sql = "SELECT * FROM pricing_templates WHERE 1=1"
    params: dict = {}
    if kind:
        sql += " AND kind = :kind"
        params["kind"] = kind
    if device_id:
        sql += " AND (device_id = :did OR station_id = :sid OR is_default)"
        params["did"] = device_id
        params["sid"] = station_id or 0
    sql += " ORDER BY id DESC"
    rows = db.execute(text(sql), params).mappings().all()
    return [dict(r) for r in rows]


@router.get("/list")
def list_templates(kind: Optional[str] = None,
                   device_id: Optional[int] = None,
                   station_id: Optional[int] = None,
                   db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    """模板列表; 传 device_id 时按绑定优先级返回(device > station > default)."""
    _ensure_table()
    rows = _fetch_templates(db, kind, device_id, station_id)
    return success_response({"items": [_row_to_dict(r) for r in rows]},
                            "费率模板列表")


@router.post("")
def create_template(body: TemplatePayload, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    _ensure_table()
    if body.is_default:
        db.execute(text("UPDATE pricing_templates SET is_default = FALSE WHERE kind = :k"),
                   {"k": body.kind})
    ins = db.execute(text(
        "INSERT INTO pricing_templates (name, kind, periods, station_id, device_id, is_default, occupancy_fee, reservation_fee, occupancy_rule, updated_by, updated_at) "
        "VALUES (:n, :k, CAST(:p AS JSONB), :st, :dv, :df, :oc, :rs, CAST(:ocr AS JSONB), :u, now()) RETURNING id"),
        {"n": body.name, "k": body.kind, "p": json.dumps([p.dict() for p in body.periods]),
         "st": body.station_id, "dv": body.device_id, "df": body.is_default,
         "oc": body.occupancy_fee, "ocr": json.dumps(body.occupancy_rule) if body.occupancy_rule else None, "rs": body.reservation_fee, "u": str(user.username)})
    new_id = ins.scalar()
    db.commit()
    return success_response({"id": new_id}, "模板已创建")


@router.put("/{template_id}")
def update_template(template_id: int, body: TemplatePayload,
                    db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    _ensure_table()
    row = db.execute(text("SELECT id FROM pricing_templates WHERE id=:i"), {"i": template_id}).first()
    if not row:
        raise HTTPException(status_code=404, detail="模板不存在")
    if body.is_default:
        db.execute(text("UPDATE pricing_templates SET is_default = FALSE WHERE kind=:k AND id<>:i"),
                   {"k": body.kind, "i": template_id})
    db.execute(text(
        "UPDATE pricing_templates SET name=:n, kind=:k, periods=CAST(:p AS JSONB), "
        "station_id=:st, device_id=:dv, is_default=:df, occupancy_fee=:oc, reservation_fee=:rs, "
        "occupancy_rule=CAST(:ocr AS JSONB), updated_by=:u, updated_at=now() WHERE id=:i"),
        {"n": body.name, "k": body.kind, "p": json.dumps([p.dict() for p in body.periods]),
         "st": body.station_id, "dv": body.device_id, "df": body.is_default,
         "oc": body.occupancy_fee, "ocr": json.dumps(body.occupancy_rule) if body.occupancy_rule else None,
         "rs": body.reservation_fee,
         "u": str(user.username), "i": template_id})
    db.commit()
    return success_response(None, "模板已保存")


@router.delete("/{template_id}")
def delete_template(template_id: int, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    db.execute(text("DELETE FROM pricing_templates WHERE id=:i"), {"i": template_id})
    db.commit()
    return success_response(None, "模板已删除")


# SZBUS 0x16 桩内费率槽位: 1尖/2峰/3平/4谷/5深谷 (2026-10-10 丁哥: 深谷时段下发映射)
_FEE_SLOT = {"sharp": 1, "peak": 2, "flat": 3, "valley": 4, "deep_valley": 5}


def _resolve_devices(db: Session, tpl: dict) -> list:
    """模板绑定的设备: 绑设备→该设备; 绑站点→站内全部充电桩.
    2026-10-09 丁哥: 无平台默认兜底 —— 未绑定站点/设备的模板不可运营(返回空)."""
    if tpl.get("device_id"):
        d = db.query(Device).filter(Device.id == tpl["device_id"]).first()
        return [d] if d else []
    if tpl.get("station_id"):
        return db.query(Device).filter(
            Device.station_id == tpl["station_id"],
            Device.type.in_(["v2g_charger", "charger_dc", "charger_ac"])).all()
    return []


@router.post("/{template_id}/dispatch")
async def dispatch_template(template_id: int, db: Session = Depends(get_db),
                            user: User = Depends(get_current_user)):
    """模板下发: 按绑定设备经 0x16 计费模板推送(时段电价+服务费)."""
    from app.gateway.szbus import _gateway, Cmd, SZBusFrame
    import struct as _s
    _ensure_table()
    row = db.execute(text("SELECT * FROM pricing_templates WHERE id=:i"), {"i": template_id}).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="模板不存在")
    tpl = dict(row)
    periods = tpl["periods"] if isinstance(tpl["periods"], list) else json.loads(tpl["periods"] or "[]")
    if not periods:
        raise HTTPException(status_code=400, detail="模板时段为空, 请先设置费率")
    # V2G 模板: 仅下发购电(buy)时段 —— 放电(sell)价协议无独立下发通道, 保留为平台策略
    if tpl.get("kind") == "v2g":
        periods = [p for p in periods if p.get("kind") != "sell"]
        if not periods:
            raise HTTPException(status_code=400, detail="V2G模板无购电时段可下发(放电价为平台策略)")

    if _gateway is None:
        raise HTTPException(status_code=409, detail="SZBUS 网关未运行")

    if not tpl.get("device_id") and not tpl.get("station_id"):
        raise HTTPException(status_code=400, detail="模板未绑定站点/设备 —— 每个站点必须定义价格才能运营, 请先绑定")
    devices = _resolve_devices(db, tpl)
    results = []
    seg = bytes([1]) + _s.pack("<I", int(datetime.now().timestamp()) % 100000) + bytes([len(periods)])
    for p in periods:
        hh, mm = str(p.get("start", "00:00")).split(":")[:2]
        hh2, mm2 = str(p.get("end", "23:59")).split(":")[:2]
        energy = int(float(p.get("price", 0)) * 10000)
        service = int(float(p.get("serviceFee", 0)) * 10000)
        fee_slot = _FEE_SLOT.get(p.get("period_type", "flat"), 3)
        seg += bytes([fee_slot, int(hh), int(mm), int(hh2), int(mm2)])
        seg += _s.pack("<ii", energy, service)

    from datetime import datetime as _dt
    for d in devices:
        session = _gateway._sessions.get(d.sn)
        if not session or not session.get("checked_in"):
            results.append({"device": d.sn, "name": d.name, "result": "离线(未签到), 跳过"})
            continue
        rec = _gateway._dispatch_records.setdefault(d.sn, {})
        rec["dispatch_time"] = datetime.now(timezone.utc)
        _gateway._seq = (_gateway._seq + 1) & 0xFFFF
        frame = SZBusFrame(_gateway._seq, session["version"], session["manufacturer"],
                           session["device_id"], Cmd.BILLING, seg)
        session["writer"].write(frame.encode())
        await session["writer"].drain()
        rec["billing_dispatched"] = True
        rec["billing_version"] = int(datetime.now().timestamp()) % 100000
        rec["billing_seg"] = seg
        rec["billing_prices"] = [float(p.get("price", 0)) + float(p.get("serviceFee", 0)) for p in periods]
        rec["billing_energy_prices"] = [float(p.get("price", 0)) for p in periods]
        rec["billing_service_fees"] = [float(p.get("serviceFee", 0)) for p in periods]
        results.append({"device": d.sn, "name": d.name, "result": "已下发(0x16 计费模板)"})
    return success_response({"results": results, "dispatched": len(devices)}, "费率模板下发完成")


@router.post("/{template_id}/verify")
def verify_template(template_id: int, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    """模板校验: 桩端上行证据(0x02 ACK/0x25 执行电价/0x06 版本) vs 模板费率."""
    from app.gateway.szbus import _gateway
    _ensure_table()
    row = db.execute(text("SELECT * FROM pricing_templates WHERE id=:i"), {"i": template_id}).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="模板不存在")
    tpl = dict(row)
    periods = tpl["periods"] if isinstance(tpl["periods"], list) else json.loads(tpl["periods"] or "[]")
    energy_prices = [float(p.get("price", 0)) for p in periods]
    totals = [float(p.get("price", 0)) + float(p.get("serviceFee", 0)) for p in periods]

    devices = _resolve_devices(db, tpl)
    items = []
    for d in devices:
        rec = (_gateway._dispatch_records.get(d.sn) if _gateway else None) or {}
        dt = rec.get("dispatch_time")
        bp = rec.get("pile_price_report")
        online = bool(_gateway and _gateway._sessions.get(d.sn, {}).get("checked_in"))
        if not online:
            items.append({"item": f"{d.name}({d.sn})", "expected": "-", "actual": "桩离线", "ok": False})
            continue
        if not dt:
            items.append({"item": f"{d.name}({d.sn})", "expected": "已下发", "actual": "无下发记录", "ok": False})
            continue
        if bp and bp.get("time") and bp["time"] >= dt and bp.get("price") is not None:
            matched = any(abs(bp["price"] - ep) < 0.0001 for ep in energy_prices)
            matched_total = any(abs((bp["price"] or 0) + (bp.get("service") or 0) - t) < 0.0001 for t in totals)
            ok = matched or matched_total
            items.append({"item": f"{d.name}({d.sn})", "expected": f"电价{energy_prices} 合计{totals}",
                          "actual": f"桩执行电价 {bp['price']} + 服务费 {bp.get('service', 0)}",
                          "ok": ok})
        else:
            items.append({"item": f"{d.name}({d.sn})", "expected": f"电价{energy_prices}",
                          "actual": "待确认: 桩充电时 0x25 上报执行电价后复核", "ok": None})
    updated = bool(items) and all(i["ok"] is not False for i in items)
    pending = any(i["ok"] is None for i in items)
    conclusion = ("桩端费率已更新" + ("（部分待桩端充电时确认）" if pending else "")) if updated else "桩端费率未更新"
    return success_response({"updated": updated, "items": items}, conclusion)
