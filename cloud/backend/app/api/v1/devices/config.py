"""设备控制历史 + 设备配置 + 删除端点（拆分自原 devices.py）。"""
import time
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional, Any
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, get_async_db
from app.api.v1.auth import get_current_user
from app.models.device import Device, DeviceType
from app.models.device_control_log import DeviceControlLog
from app.models.user import User
from app.services.audit_service import audit_service
from app.core.response import success_response, paginated_response, action_response

from ._shared import logger, _check_device_team, _check_device_team_async, _ROUTER_DEPENDENCIES


router = APIRouter(dependencies=_ROUTER_DEPENDENCIES)


class TimePeriodConfig(BaseModel):
    """时段配置"""
    start_time: str  # 格式 HH:MM
    end_time: str    # 格式 HH:MM
    power_limit: float  # 功率限制 kW
    price_per_kwh: Optional[float] = None  # 电价 元/kWh


class DeviceConfigRequest(BaseModel):
    """设备配置请求"""
    voltage_limit: Optional[float] = None  # 电压上限 V
    current_limit: Optional[float] = None  # 电流上限 A
    max_power: Optional[float] = None      # 最大功率 kW
    charge_mode: Optional[str] = None      # 充电模式: fast/smart/eco
    overload_protection: Optional[bool] = None  # 过载保护
    time_periods: Optional[List[TimePeriodConfig]] = None  # 时段配置


@router.get("/{device_id}/control-history")
def get_device_control_history(
    device_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取设备控制历史记录（team scoping：跨团队 → 404）"""
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")
    _check_device_team(db, device_id, user)

    query = db.query(DeviceControlLog).filter(
        DeviceControlLog.device_id == device_id
    )
    total = query.count()
    records = query.order_by(DeviceControlLog.created_at.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()

    items = [record.to_dict() for record in records]
    return paginated_response(items, total, page, page_size)


@router.get("/{device_id}/config")
def get_device_config(device_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """获取设备配置参数（team scoping：跨团队 → 404）"""
    from app.models.device_config import DeviceConfig

    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")
    _check_device_team(db, device_id, user)

    # 只允许充电桩类型设备配置
    if device.type not in [DeviceType.CHARGER_DC, DeviceType.CHARGER_AC]:
        raise HTTPException(status_code=400, detail="仅支持充电桩设备配置")

    config = db.query(DeviceConfig).filter(DeviceConfig.device_id == device_id).first()
    if not config:
        # 返回默认配置
        return success_response({
            'device_id': device_id,
            'voltage_limit': 420.0,
            'current_limit': 60.0,
            'max_power': 60.0,
            'charge_mode': 'smart',
            'overload_protection': True,
            'time_periods': [],
            'created_at': None,
            'updated_at': None,
        })

    return success_response({
        'device_id': config.device_id,
        'voltage_limit': config.voltage_limit,
        'current_limit': config.current_limit,
        'max_power': config.max_power,
        'charge_mode': config.charge_mode.value,
        'overload_protection': config.overload_protection,
        'time_periods': config.time_periods or [],
        'created_at': config.created_at.isoformat() if config.created_at else None,
        'updated_at': config.updated_at.isoformat() if config.updated_at else None,
    })


@router.put("/{device_id}/config")
def update_device_config(
    device_id: int,
    data: DeviceConfigRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """批量更新充电桩配置参数（team scoping：跨团队 → 404）"""
    from app.models.device_config import DeviceConfig, ChargeMode

    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")
    _check_device_team(db, device_id, user)

    # 只允许充电桩类型设备配置
    if device.type not in [DeviceType.CHARGER_DC, DeviceType.CHARGER_AC]:
        raise HTTPException(status_code=400, detail="仅支持充电桩设备配置")

    config = db.query(DeviceConfig).filter(DeviceConfig.device_id == device_id).first()
    if not config:
        config = DeviceConfig(device_id=device_id)
        db.add(config)

    # 更新配置字段
    if data.voltage_limit is not None:
        if data.voltage_limit <= 0:
            raise HTTPException(status_code=400, detail="电压上限必须大于0")
        config.voltage_limit = data.voltage_limit
    if data.current_limit is not None:
        if data.current_limit <= 0:
            raise HTTPException(status_code=400, detail="电流上限必须大于0")
        config.current_limit = data.current_limit
    if data.max_power is not None:
        if data.max_power <= 0:
            raise HTTPException(status_code=400, detail="最大功率必须大于0")
        config.max_power = data.max_power
    if data.charge_mode is not None:
        try:
            config.charge_mode = ChargeMode(data.charge_mode)
        except ValueError:
            raise HTTPException(status_code=400, detail="充电模式必须是: fast, smart, eco")
    if data.overload_protection is not None:
        config.overload_protection = data.overload_protection
    if data.time_periods is not None:
        # 验证时段配置
        for period in data.time_periods:
            if period.start_time >= period.end_time:
                raise HTTPException(status_code=400, detail="时段起始时间必须早于结束时间")
            if period.power_limit <= 0:
                raise HTTPException(status_code=400, detail="时段功率限制必须大于0")
        config.time_periods = [p.dict() for p in data.time_periods]

    db.commit()
    db.refresh(config)

    audit_service.log_crud(user.id, user.username, "update", "device_configs", str(config.id))

    return success_response({
        'device_id': config.device_id,
        'voltage_limit': config.voltage_limit,
        'current_limit': config.current_limit,
        'max_power': config.max_power,
        'charge_mode': config.charge_mode.value,
        'overload_protection': config.overload_protection,
        'time_periods': config.time_periods or [],
        'created_at': config.created_at.isoformat() if config.created_at else None,
        'updated_at': config.updated_at.isoformat() if config.updated_at else None,
    }, "设备配置已更新")


@router.post("/{device_id}/config/dispatch")
async def dispatch_device_config(
    device_id: int,
    db: AsyncSession = Depends(get_async_db),
    user: User = Depends(get_current_user),
):
    """配置下发：将平台配置推送到设备（2026-10-09 丁哥需求）。

    深圳巴士(szbus)在线桩：
      - 0x12 工作参数（对时/保活/上报间隔）主动下发；
      - time_periods 转 0x16 计费模板（多时段电价）主动推送。
    其他协议/离线：返回 409/部分支持明细，不影响平台侧配置。
    """
    result = await db.execute(select(Device).where(Device.id == device_id))
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")
    await _check_device_team_async(db, device_id, user)

    from app.models.device_config import DeviceConfig
    cfg_result = await db.execute(select(DeviceConfig).where(DeviceConfig.device_id == device_id))
    config = cfg_result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=400, detail="请先保存参数配置再下发")

    items = []
    protocol = (device.protocol_type.value if device.protocol_type else "") or ""
    # 协议自适应兜底: 档案未配协议时, 若桩在 SZBUS 网关有已签到会话则按深圳巴士协议处理
    if not protocol:
        try:
            from app.gateway.szbus import _gateway as _gw_probe
            if _gw_probe is not None and _gw_probe._sessions.get(device.sn, {}).get("checked_in"):
                protocol = "szbus"
        except Exception:
            pass
    dispatched = False

    if str(protocol).lower() == "szbus":
        try:
            from app.gateway.szbus import _gateway, _device_now, Cmd, SZBusFrame, encode_cp56time2a
            import struct as _struct
            if _gateway is None:
                raise RuntimeError("SZBUS 网关未运行")
            sn = device.sn
            session = _gateway._sessions.get(sn)
            if not session or not session.get("checked_in"):
                raise RuntimeError("桩不在线（未签到）")

            # 下发回读证据链起点（2026-10-09 丁哥: 校验=读桩上传数据比对下发定值）
            rec = _gateway._dispatch_records.setdefault(sn, {})
            rec["dispatch_time"] = datetime.now(timezone.utc)

            # 1) 0x12 工作参数：对时 + 保活30s×3 + 上报30s
            wp_body = (encode_cp56time2a(_device_now())
                       + bytes([30, 3, 30]) + bytes([1, 1]) + b"\0" * 96)
            _gateway._seq = (_gateway._seq + 1) & 0xFFFF
            wp = SZBusFrame(_gateway._seq, session["version"], session["manufacturer"],
                            session["device_id"], Cmd.WORK_PARAM, wp_body)
            session["writer"].write(wp.encode())
            await session["writer"].drain()
            rec["wp_dispatched"] = True
            items.append({"name": "工作参数(对时/保活/上报间隔)", "action": "0x12 下发", "result": "ok"})

            # 2) time_periods → 0x16 计费模板（时段电价）
            periods = config.time_periods or []
            if periods:
                seg = bytes([1]) + _struct.pack("<I", int(time.time()) % 100000) + bytes([len(periods)])
                for p in periods:
                    try:
                        hh, mm = str(p.get("start_time", "00:00")).split(":")[:2]
                        hh2, mm2 = str(p.get("end_time", "23:59")).split(":")[:2]
                    except Exception:
                        raise HTTPException(status_code=400, detail=f"时段格式错误: {p}")
                    price = int(float(p.get("price_per_kwh") or 0) * 10000)
                    seg += bytes([3, int(hh), int(mm), int(hh2), int(mm2)])
                    seg += _struct.pack("<ii", price, price)  # 电价=服务费(桩侧计费)
                _gateway._seq = (_gateway._seq + 1) & 0xFFFF
                bl = SZBusFrame(_gateway._seq, session["version"], session["manufacturer"],
                                session["device_id"], Cmd.BILLING, seg)
                session["writer"].write(bl.encode())
                await session["writer"].drain()
                rec["billing_dispatched"] = True
                billing_version = int(time.time()) % 100000
                rec["billing_version"] = billing_version
                rec["billing_seg"] = seg
                rec["billing_prices"] = [float(p.get("price_per_kwh") or 0) for p in periods]
                items.append({"name": f"计费模板({len(periods)}时段电价)", "action": "0x16 下发", "result": "ok"})

            dispatched = True
        except HTTPException:
            raise
        except Exception as e:
            items.append({"name": "协议下发", "action": "szbus", "result": f"失败: {e}"})
    else:
        items.append({"name": "电压/电流/功率上限、充电模式",
                      "action": "平台侧策略生效",
                      "result": "ok（当前协议无下行映射，由平台调度执行)"})

    # 控制日志
    log = DeviceControlLog(device_id=device_id, action="config_dispatch",
                           params={"items": items}, result="success" if dispatched else "partial",
                           message="配置下发", operator=str(user.username), operator_id=user.id)
    db.add(log)
    await db.commit()

    audit_service.log_crud(user.id, user.username, "dispatch", "device_configs", str(device_id))
    return success_response({"device_id": device_id, "dispatched": dispatched, "items": items},
                            "配置已下发" if dispatched else "配置下发（部分支持）")


@router.post("/{device_id}/config/verify")
def verify_device_config(
    device_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """配置校验（2026-10-09 丁哥定义）：下发后读取桩上传的数据，
    比对是否与下发定值一致 → 一致「桩端定值已更新」/ 不一致「桩端定值未更新」。

    证据链（深圳巴士协议无配置回读命令, 采用桩端上行证据）:
      - 工作参数: 桩 0x02 ACK 逐项成功位（在下发之后收到）
      - 计费模板: 桩 0x25 充电信息上报的实际执行电价 == 下发时段电价
    """
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")
    _check_device_team(db, device_id, user)

    sn = device.sn
    rec = None
    try:
        from app.gateway.szbus import _gateway
        if _gateway is not None:
            rec = _gateway._dispatch_records.get(sn)
    except Exception:
        pass

    if not rec or "dispatch_time" not in rec:
        return success_response(
            {"device_id": device_id, "updated": False,
             "items": [{"item": "下发记录", "expected": "已下发", "actual": "无", "ok": False}]},
            "桩端定值未更新（尚未下发，请先点【下发】）")

    dt = rec["dispatch_time"]
    items = []

    # 1) 工作参数：桩 0x02 ACK（下发之后、逐项全部成功）
    if rec.get("wp_dispatched"):
        wp = rec.get("wp_ack")
        if wp and wp["time"] >= dt and wp["ok"]:
            items.append({"item": "工作参数(对时/保活/上报)", "expected": "桩端确认成功",
                          "actual": "桩已确认(0x02全成功)", "ok": True})
        elif wp and wp["time"] >= dt:
            items.append({"item": "工作参数(对时/保活/上报)", "expected": "桩端确认成功",
                          "actual": "桩应答含失败项{}".format(wp.get("detail")), "ok": False})
        else:
            items.append({"item": "工作参数(对时/保活/上报)", "expected": "桩端确认成功",
                          "actual": "桩未上报确认(0x02)", "ok": False})

    # 2) 计费模板：桩 0x25 上报的实际执行电价 vs 下发时段电价
    if rec.get("billing_dispatched"):
        prices = rec.get("billing_prices") or []
        bp = rec.get("pile_price_report")
        if bp and bp["time"] >= dt and bp.get("price") is not None:
            if any(abs(bp["price"] - p) < 0.0001 for p in prices):
                items.append({"item": "计费模板(时段电价)", "expected": "{} 元/度".format(prices),
                              "actual": "桩执行电价 {} 元/度 一致".format(bp["price"]), "ok": True})
            else:
                items.append({"item": "计费模板(时段电价)", "expected": "{} 元/度".format(prices),
                              "actual": "桩执行电价 {} 元/度 不一致".format(bp["price"]), "ok": False})
        elif rec.get("pile_billing_version") and rec.get("pile_billing_version") == rec.get("billing_version"):
            items.append({"item": "计费模板(时段电价)", "expected": "版本 {}".format(rec.get("billing_version")),
                          "actual": "桩已拉取新版模板(版本匹配)", "ok": True})
        else:
            items.append({"item": "计费模板(时段电价)", "expected": "{} 元/度".format(prices),
                          "actual": "待确认: 桩充电时0x25上报执行电价或主动拉取模板后复核", "ok": None})

    pending = any(i["ok"] is None for i in items)
    updated = bool(items) and all(i["ok"] is not False for i in items)
    if updated and pending:
        conclusion = "桩端定值已更新（部分项待桩端充电时确认）"
    elif updated:
        conclusion = "桩端定值已更新"
    else:
        conclusion = "桩端定值未更新"
    log = DeviceControlLog(device_id=device_id, action="config_verify",
                           params={"updated": updated, "items": items},
                           result="success" if updated else "mismatch",
                           message="桩端定值已更新" if updated else "桩端定值未更新",
                           operator=str(user.username), operator_id=user.id)
    db.add(log)
    db.commit()
    audit_service.log_crud(user.id, user.username, "verify", "device_configs", str(device_id))
    return success_response({"device_id": device_id, "updated": updated, "items": items},
                            conclusion)


@router.delete("/{device_id}")
def delete_device(device_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """删除设备（team scoping：跨团队 → 404）"""
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")
    _check_device_team(db, device_id, user)

    # 卡 ed537344: 服务层显式级联（子表无 ondelete, 裸 delete 在 PG 下 IntegrityError 500 / SQLite 下留孤儿）
    from app.services.fk_cascade import purge_device_children
    purge_device_children(db, device_id)

    db.delete(device)
    db.commit()
    audit_service.log_crud(user.id, user.username, "delete", "devices", str(device_id))
    return action_response(message="设备已删除")
