"""
运营平台 - 充电桩收费二维码生成与下载 — 工作卡 c7523ad8

功能:
- 按云快充协议 V1.6 规则生成桩编号（14 位纯数字）与枪号（16 位）
- 按枪粒度生成二维码图片（PNG）：单枪桩 1 张（尾缀 01），双枪桩 2 张（01/02）
- 单张下载 / 批量打包下载（ZIP）
- 二维码内容 = 16 位枪号

桩编号规则（云快充协议 V1.6 / 丁哥 01:00 提出）:
  6 位国标行政区划码 + 8 位桩序号 = 14 位纯数字
  示例: 320106 00019236 → 32010600019236

枪号规则:
  14 位桩编号 + 2 位枪号 = 16 位
  示例: 32010600019236 01 → 3201060001923601

桩序号取 device.id（确定性、全局唯一 → 站点内唯一），保证生成接口幂等。

团队隔离: 任务卡 708350b3 — team_id 取 current_user.team_id（服务端强制），
设备归属经 station.team_id 校验；admin/平台级豁免。
"""
import io
import os
import uuid
import zipfile
import logging
from typing import Optional, List

import qrcode
from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.response import success_response
from app.api.v1.auth import get_current_user
from app.middleware.permission import require_permission
from app.api.deps import team_scope, assert_station_team_access
from app.models.user import User
from app.models.device import Device, DeviceType
from app.models.device_qrcode import DeviceQRCode
from app.models.station import Station

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(require_permission("operate:manage"))])

# ========== 桩编号 / 枪号生成 ==========

# 国标行政区划码（6 位）- 可从系统配置读取，默认占位（南京鼓楼区）
DEFAULT_REGION_CODE = "320106"

# 充电桩设备类型
CHARGER_TYPES = [DeviceType.CHARGER_DC, DeviceType.CHARGER_AC, DeviceType.V2G_CHARGER]

# 枪号尾缀上限（2 位 → 单桩最多 99 把枪）
MAX_GUN_NO = 99


def generate_pile_code(region_code: Optional[str], pile_seq: int) -> str:
    """
    生成 14 位桩编号（云快充协议 V1.6 格式，纯数字）

    格式: 6 位国标行政区划码 + 8 位桩序号
    示例: 320106 00000001 → 32010600000001

    Args:
        region_code: 6 位国标行政区划码（None 用默认占位；短补 0、长截断）
        pile_seq: 桩序号（站点内唯一；取模 1e8）
    """
    region = (region_code or DEFAULT_REGION_CODE)[:6].ljust(6, "0")
    pile_part = str(pile_seq % 100000000).zfill(8)
    return f"{region}{pile_part}"


def generate_gun_code(pile_code: str, gun_no: int) -> str:
    """
    生成 16 位枪号 = 14 位桩编号 + 2 位枪号尾缀

    示例: 32010600000001 + 01 → 3201060000000101
    """
    gun_part = str(gun_no % 100).zfill(2)
    return f"{pile_code}{gun_part}"


def generate_qr_image(content: str, label: str = "") -> bytes:
    """
    生成二维码 PNG 图片

    Args:
        content: 二维码内容（16 位枪号）
        label: 图片下方标注文字（桩名/编号）
    """
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(content)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    if label:
        try:
            from PIL import Image, ImageDraw, ImageFont
            img = img.convert("RGB")
            w, h = img.size
            label_h = 30
            new_img = Image.new("RGB", (w, h + label_h), "white")
            new_img.paste(img, (0, 0))
            draw = ImageDraw.Draw(new_img)
            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
            except (IOError, OSError):
                font = ImageFont.load_default()
            bbox = draw.textbbox((0, 0), label, font=font)
            text_w = bbox[2] - bbox[0]
            x = (w - text_w) // 2
            draw.text((x, h + 5), label, fill="black", font=font)
            buf = io.BytesIO()
            new_img.save(buf, format="PNG")
            return buf.getvalue()
        except ImportError:
            pass  # PIL不可用时不加标注

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ========== Schemas ==========

class QRGenerateRequest(BaseModel):
    """生成二维码请求"""
    device_ids: List[int] = Field(..., min_length=1, max_length=100, description="充电桩设备ID列表")
    region_code: Optional[str] = Field(
        None,
        max_length=6,
        pattern=r"^\d{6}$",
        description="6 位国标行政区划码（不传则用系统默认 320106）",
    )


class QRGenerateResult(BaseModel):
    """单张二维码生成结果（按枪粒度）"""
    device_id: int
    device_name: str
    pile_code: str  # 14 位桩编号
    gun_no: int
    qr_code: str  # 16 位枪号
    qr_image_url: str


class QRDownloadRequest(BaseModel):
    """批量下载请求"""
    device_ids: List[int] = Field(..., min_length=1, max_length=200, description="充电桩设备ID列表")


# ========== Helpers ==========

def _resolve_gun_count(device: Device) -> int:
    """解析设备枪数：空值/非法 → 1，上限 MAX_GUN_NO。"""
    raw = device.gun_count or 1
    if raw < 1:
        return 1
    return min(raw, MAX_GUN_NO)


def _get_or_create_qrcode(db: Session, device: Device, gun_no: int, gun_code: str) -> DeviceQRCode:
    """获取或创建某枪的二维码记录（按 device_id + gun_no 唯一）。"""
    record = db.query(DeviceQRCode).filter(
        DeviceQRCode.device_id == device.id,
        DeviceQRCode.gun_no == gun_no,
    ).first()

    if record:
        # 幂等覆盖（旧 20 位记录 / 上次生成的码 → 更新为当前 16 位枪号）
        if record.qr_code != gun_code:
            record.qr_code = gun_code
        record.is_active = True
        return record

    record = DeviceQRCode(
        device_id=device.id,
        gun_no=gun_no,
        qr_code=gun_code,
        is_active=True,
    )
    db.add(record)
    db.flush()
    return record


def _deactivate_extra_guns(db: Session, device: Device, active_gun_count: int) -> None:
    """枪数缩减时，将多余枪行（gun_no > 当前枪数）置失效（旧码失效可接受）。"""
    db.query(DeviceQRCode).filter(
        DeviceQRCode.device_id == device.id,
        DeviceQRCode.gun_no > active_gun_count,
    ).update({DeviceQRCode.is_active: False}, synchronize_session=False)


def _pile_code_of(qr_code: Optional[str]) -> Optional[str]:
    """从 16 位枪号取 14 位桩编号（非 16 位数字则原样返回）。"""
    if not qr_code:
        return None
    if len(qr_code) >= 16 and qr_code.isdigit():
        return qr_code[:14]
    return qr_code


# ========== API 端点 ==========

@router.post("/charger-qrcode/generate", response_model=None)
def generate_charger_qrcodes(
    req: QRGenerateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    批量生成充电桩收费二维码（按枪粒度展开）

    - 按 device.gun_count 展开为每枪一张二维码（单枪 01，双枪 01/02）
    - 桩编号 14 位纯数字；枪号 16 位
    - 幂等：同设备重复生成覆盖旧码、不新增行

    权限: 需登录，按团队隔离
    """
    region_code = req.region_code or os.getenv("REGION_CODE", DEFAULT_REGION_CODE)

    results = []
    errors = []

    for device_id in req.device_ids:
        device = db.query(Device).filter(Device.id == device_id).first()
        if not device:
            errors.append({"device_id": device_id, "error": "设备不存在"})
            continue

        # 验证是充电桩类型
        if device.type not in CHARGER_TYPES:
            errors.append({"device_id": device_id, "error": f"非充电桩设备(类型:{device.type.value})"})
            continue

        # 团队隔离：经 station 校验归属（admin 豁免，跨队 → 记错跳过）
        try:
            assert_station_team_access(db, device.station_id, current_user)
        except HTTPException:
            errors.append({"device_id": device_id, "error": "无权操作其他团队的设备"})
            continue

        # 14 位桩编号（pile_seq = device.id，确定性、站点内唯一）
        pile_code = generate_pile_code(region_code, device.id)
        gun_count = _resolve_gun_count(device)

        # 枪数缩减时失效多余枪行
        _deactivate_extra_guns(db, device, gun_count)

        for gun_no in range(1, gun_count + 1):
            gun_code = generate_gun_code(pile_code, gun_no)

            # 创建/覆盖二维码记录
            qr_record = _get_or_create_qrcode(db, device, gun_no, gun_code)

            # 生成二维码图片
            label = f"{device.name or ''} {gun_code}"
            img_bytes = generate_qr_image(gun_code, label.strip())

            # 存储图片
            upload_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
                "uploads", "qrcodes",
            )
            os.makedirs(upload_dir, exist_ok=True)
            filename = f"qr_{gun_code}_{uuid.uuid4().hex[:8]}.png"
            filepath = os.path.join(upload_dir, filename)
            with open(filepath, "wb") as f:
                f.write(img_bytes)

            qr_record.qr_image_path = filepath
            qr_record.print_count = (qr_record.print_count or 0) + 1

            results.append({
                "device_id": device.id,
                "device_name": device.name or "",
                "pile_code": pile_code,
                "gun_no": gun_no,
                "qr_code": gun_code,
                "qr_image_url": f"/api/v1/ops/charger-qrcode/download/{device.id}?gun_no={gun_no}",
            })

    db.commit()

    return success_response({
        "generated": results,
        "errors": errors,
        "total": len(results),
        "failed": len(errors),
    }, message=f"成功生成{len(results)}张二维码")


@router.get("/charger-qrcode/download/{device_id}")
def download_single_qrcode(
    device_id: int,
    gun_no: Optional[int] = Query(None, ge=1, le=MAX_GUN_NO, description="枪号（不传取首枪）"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """下载单张充电桩二维码（PNG）。多枪桩可用 gun_no 指定枪。"""
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")
    # 团队隔离：经 station 校验归属（admin 豁免，跨队 → 404）
    assert_station_team_access(db, device.station_id, current_user)

    qry = db.query(DeviceQRCode).filter(
        DeviceQRCode.device_id == device_id,
        DeviceQRCode.is_active == True,
    )
    if gun_no is not None:
        qry = qry.filter(DeviceQRCode.gun_no == gun_no)
    qr_record = qry.order_by(DeviceQRCode.gun_no).first()

    if not qr_record:
        raise HTTPException(status_code=404, detail="该设备尚未生成二维码，请先调用生成接口")

    # 如果有存储的图片文件，直接返回
    if qr_record.qr_image_path and os.path.exists(qr_record.qr_image_path):
        with open(qr_record.qr_image_path, "rb") as f:
            img_bytes = f.read()
    else:
        # 重新生成
        label = f"{device.name or ''} {qr_record.qr_code}"
        img_bytes = generate_qr_image(qr_record.qr_code, label.strip())

    return StreamingResponse(
        io.BytesIO(img_bytes),
        media_type="image/png",
        headers={
            "Content-Disposition": f'attachment; filename="qr_{qr_record.qr_code}.png"'
        }
    )


@router.post("/charger-qrcode/batch-download")
def batch_download_qrcodes(
    req: QRDownloadRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """批量下载充电桩二维码（ZIP 打包，按枪展开 — 双枪桩内含 2 张）"""
    zip_buffer = io.BytesIO()

    count = 0
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for device_id in req.device_ids:
            device = db.query(Device).filter(Device.id == device_id).first()
            if not device or device.type not in CHARGER_TYPES:
                continue

            # 团队隔离：跨队 device 跳过（admin 豁免）
            try:
                assert_station_team_access(db, device.station_id, current_user)
            except HTTPException:
                continue

            # 按枪展开全部有效二维码
            qr_records = db.query(DeviceQRCode).filter(
                DeviceQRCode.device_id == device_id,
                DeviceQRCode.is_active == True,
            ).order_by(DeviceQRCode.gun_no).all()

            for qr_record in qr_records:
                # 获取或生成图片
                if qr_record.qr_image_path and os.path.exists(qr_record.qr_image_path):
                    with open(qr_record.qr_image_path, "rb") as f:
                        img_bytes = f.read()
                else:
                    label = f"{device.name or ''} {qr_record.qr_code}"
                    img_bytes = generate_qr_image(qr_record.qr_code, label.strip())

                # 文件名: 枪号.png
                filename = f"{qr_record.qr_code}.png"
                zf.writestr(filename, img_bytes)
                count += 1

    if count == 0:
        raise HTTPException(status_code=404, detail="没有可下载的二维码，请先生成")

    zip_buffer.seek(0)
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="charger_qrcodes.zip"'
        }
    )


@router.get("/charger-qrcode/list", response_model=None)
def list_charger_qrcodes(
    station_id: Optional[int] = Query(None, description="按站点筛选"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """查询充电桩二维码列表（按枪粒度返回行）。分页以设备为单位，行按枪展开。"""
    # 查询充电桩设备
    query = db.query(Device).filter(Device.type.in_(CHARGER_TYPES))
    # 团队隔离：经 station.team_id 过滤（admin 豁免，看全部）
    scope = team_scope(current_user)
    if scope is not None:
        query = query.join(Station, Station.id == Device.station_id).filter(Station.team_id == scope)
    if station_id:
        query = query.filter(Device.station_id == station_id)

    total = query.count()
    devices = query.offset((page - 1) * page_size).limit(page_size).all()

    # ── 卡 11f7d020: 批量预取 QRCode/Station, 消除 N+1 ──
    device_ids = [d.id for d in devices]
    qr_map: dict = {}
    if device_ids:
        for rec in (
            db.query(DeviceQRCode)
            .filter(
                DeviceQRCode.device_id.in_(device_ids),
                DeviceQRCode.is_active == True,
            )
            .order_by(DeviceQRCode.gun_no)
            .all()
        ):
            qr_map.setdefault(rec.device_id, []).append(rec)
    station_map = {}
    station_ids = {d.station_id for d in devices if d.station_id}
    if station_ids:
        for st in db.query(Station).filter(Station.id.in_(station_ids)).all():
            station_map[st.id] = st

    items = []
    for device in devices:
        qr_records = qr_map.get(device.id, [])

        station = station_map.get(device.station_id) if device.station_id else None

        if not qr_records:
            items.append({
                "device_id": device.id,
                "device_name": device.name or "",
                "device_code": device.code or "",
                "device_type": device.type.value,
                "station_name": station.name if station else "",
                "gun_no": None,
                "pile_code": None,
                "qr_code": None,
                "has_qrcode": False,
                "is_active": False,
                "print_count": 0,
                "scan_count": 0,
                "created_at": None,
            })
            continue

        for rec in qr_records:
            items.append({
                "device_id": device.id,
                "device_name": device.name or "",
                "device_code": device.code or "",
                "device_type": device.type.value,
                "station_name": station.name if station else "",
                "gun_no": rec.gun_no,
                "pile_code": _pile_code_of(rec.qr_code),
                "qr_code": rec.qr_code,
                "has_qrcode": True,
                "is_active": rec.is_active,
                "print_count": rec.print_count if rec.print_count else 0,
                "scan_count": rec.scan_count if rec.scan_count else 0,
                "created_at": str(rec.created_at) if rec.created_at else None,
            })

    return success_response({
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    })
