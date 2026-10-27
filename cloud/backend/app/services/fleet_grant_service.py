"""
车队设备授权 scope 服务 (卡 a1468299)

提供充电启动链路的设备授权校验: 企业车在指定设备(桩)上充电是否被授权范围覆盖。

授权语义(与 EnterpriseDeviceGrant 表配合):
- 该企业无任何授权记录 → 放行(未配置=不限, 向后兼容, 保 baseline)
- 有授权记录 → 设备须被某条授权覆盖:
  · 整站授权(device_id IS NULL 且 station_id == device.station_id) → 该站所有桩放行
  · 桩级授权(device_id == device.id) → 仅该桩
  · 否则 → 拒绝(返回 False + reason)

仅企业车(有 enterprise)受约束; 个人/散客在调用方先跳过本函数。
"""
from __future__ import annotations

import logging
from typing import Tuple

from sqlalchemy.orm import Session

from app.models.device import Device
from app.models.enterprise_device_grant import EnterpriseDeviceGrant

logger = logging.getLogger(__name__)


def is_device_authorized(
    db: Session, enterprise_id: int, device: Device
) -> Tuple[bool, str]:
    """校验企业是否被授权在 device 上充电。

    Returns:
        (allowed, reason): allowed=True 时 reason 描述命中规则; False 时 reason 指明拒绝原因。

    DB 异常 → 记录日志并降级放行 (向后兼容, 保 baseline)。
    """
    try:
        grants = (
            db.query(EnterpriseDeviceGrant)
            .filter(EnterpriseDeviceGrant.enterprise_id == enterprise_id)
            .all()
        )
    except Exception:
        logger.exception(
            "is_device_authorized 查询异常 enterprise_id=%s device_id=%s, 降级放行",
            enterprise_id,
            getattr(device, "id", None),
        )
        return True, "设备授权校验异常, 降级放行"

    # 企业未配置任何设备授权 → 不限制(向后兼容)
    if not grants:
        return True, "企业未配置设备授权, 放行"

    station_id = device.station_id
    for g in grants:
        if g.device_id is None:
            # 整站授权: 覆盖该站所有桩
            if g.station_id == station_id:
                return True, f"整站授权 站点 {station_id}"
        else:
            # 桩级授权: 仅该桩
            if g.device_id == device.id:
                return True, f"桩级授权 设备 {device.id}"

    return (
        False,
        f"设备 {device.id}(站点 {station_id}) 不在企业 {enterprise_id} 的授权范围",
    )
