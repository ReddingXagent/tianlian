"""
租户品牌解析服务 (工作卡 28546b66)

契约: backend/docs/contracts/user-client-contract.md §1 (场站响应 + branding)

职责:
- 解析场站 branding 对象: station.tenant_id → TenantBrand → 品牌字段；
  租户未配置 → 天链默认品牌 (source=default)。
- 所有返回字段非 null，端侧无需判空。
- 列表场景批量解析 (branding_map)，避免 N+1。

branding 对象两种形态:
- 全量 (详情): operator_name / logo_url / service_phone / theme_color + source
- 轻量 (列表): operator_name / theme_color + source (不含 logo_url/service_phone)
"""
import logging
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.models.tenant_brand import TenantBrand

logger = logging.getLogger(__name__)

# 天链默认品牌 (source=default 降级时使用)
# logo_url / service_phone 暂留空串 (非 null) —— 平台默认视觉资产就绪前由端侧以
# 默认主题色 + operator_name 兜底；端侧无需对任一字段判空。
DEFAULT_BRAND = {
    "operator_name": "天链",
    "logo_url": "",
    "service_phone": "",
    "theme_color": "#00A86B",
}

_FULL_FIELDS = ("operator_name", "logo_url", "service_phone", "theme_color")
_LIGHT_FIELDS = ("operator_name", "theme_color")  # 列表轻量版


def _pack(fields: dict, source: str, lightweight: bool) -> dict:
    keys = _LIGHT_FIELDS if lightweight else _FULL_FIELDS
    return {k: fields.get(k, DEFAULT_BRAND[k]) for k in keys} | {"source": source}


def _record_fields(b: TenantBrand) -> dict:
    return {
        "operator_name": b.operator_name,
        "logo_url": b.logo_url,
        "service_phone": b.service_phone,
        "theme_color": b.theme_color,
    }


def default_branding(lightweight: bool = False) -> dict:
    """天链默认品牌 (source=default)。"""
    return _pack(DEFAULT_BRAND, "default", lightweight)


def branding_for_tenant(db: Session, tenant_id: Optional[int], lightweight: bool = False) -> dict:
    """单租户品牌解析: 已配置 → source=tenant；未配置/tenant_id 为空 → source=default。

    DB 异常 → 记录日志并降级到默认品牌 (source=default)，端侧仍可正常渲染。
    """
    try:
        if tenant_id is not None:
            b = db.query(TenantBrand).filter(TenantBrand.tenant_id == tenant_id).first()
            if b is not None:
                return _pack(_record_fields(b), "tenant", lightweight)
        return default_branding(lightweight)
    except Exception:
        logger.exception("branding_for_tenant 查询异常 tenant_id=%s, 降级默认品牌", tenant_id)
        return default_branding(lightweight)


def branding_map(
    db: Session, tenant_ids: Iterable[Optional[int]], lightweight: bool = False
) -> dict:
    """批量品牌解析 (列表场景): 返回 {tenant_id: branding}，含 None 键 (降级 default)。

    一次查询取回本页所有已配置租户的品牌，避免逐站查询 (N+1)。

    DB 异常 → 记录日志并对每个 tenant_id 降级到默认品牌 (source=default)。
    """
    try:
        return _branding_map_impl(db, tenant_ids, lightweight)
    except Exception:
        logger.exception("branding_map 查询异常, 降级默认品牌")
        # 仍需返回与输入 tenant_ids 一一对应的映射 (含 None 键)
        seen = set()
        result: dict = {}
        for tid in tenant_ids:
            if tid in seen:
                continue
            seen.add(tid)
            result[tid] = default_branding(lightweight)
        return result


def _branding_map_impl(
    db: Session, tenant_ids: Iterable[Optional[int]], lightweight: bool = False
) -> dict:
    ids = {tid for tid in tenant_ids if tid is not None}
    records: dict[int, TenantBrand] = {}
    if ids:
        for b in db.query(TenantBrand).filter(TenantBrand.tenant_id.in_(ids)).all():
            records[b.tenant_id] = b

    result: dict = {}
    # 用集合去重 tenant_id (含 None)
    seen = set()
    for tid in tenant_ids:
        key = tid  # None 亦可作 dict key
        if key in seen:
            continue
        seen.add(key)
        b = records.get(tid) if tid is not None else None
        result[key] = (
            _pack(_record_fields(b), "tenant", lightweight) if b is not None
            else default_branding(lightweight)
        )
    return result
