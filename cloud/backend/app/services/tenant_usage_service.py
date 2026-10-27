"""
租户用量聚合服务

实时计算租户当前资源用量。Station/Device/User 当前均无 tenant_id 字段
（多租户隔离尚未落地），通过 hasattr 容错：字段不存在则对应指标返回 0，
不抛异常；将来给模型补 tenant_id 后本函数自动生效，无需改动。
"""
from sqlalchemy.orm import Session


def compute_current_usage(db: Session, tenant_id: int) -> dict:
    """实时统计租户当前 站点/设备/用户 数量，模型无 tenant_id 字段时容错返回 0。"""
    from app.models.station import Station
    from app.models.device import Device
    from app.models.user import User

    return {
        "station_count": _count_by_tenant(db, Station, tenant_id),
        "device_count": _count_by_tenant(db, Device, tenant_id),
        "user_count": _count_by_tenant(db, User, tenant_id),
    }


def _count_by_tenant(db: Session, model, tenant_id: int) -> int:
    """统计 model 中归属 tenant_id 的记录数；无 tenant_id 字段或查询异常时返回 0。"""
    if not hasattr(model, "tenant_id"):
        return 0
    try:
        return db.query(model).filter(model.tenant_id == tenant_id).count()
    except Exception:
        return 0
