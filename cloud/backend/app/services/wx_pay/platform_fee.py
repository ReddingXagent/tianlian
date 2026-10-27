"""平台服务费配置服务 (工作卡 280c85ee — 云端配套④ §4 预留)

本期仅落数据结构 + 管理端 CRUD, enabled 固定 false, 不接真实分账 (profitsharing)。
费率校验: rate_bp ∈ [0, 3000] (IM-B分账上限 30%)。
"""
from typing import Optional

from sqlalchemy.orm import Session

from app.models.platform_fee_config import PlatformFeeConfig, FeeScope


class InvalidFeeRate(Exception):
    """费率越界 (rate_bp 必须 ∈ [0, 3000])"""


def _validate_rate_bp(rate_bp: int) -> None:
    # NaN/None 经 Pydantic 层拦截; 此处兜底负数 / 超 30% 上限
    if rate_bp is None or rate_bp < 0 or rate_bp > 3000:
        raise InvalidFeeRate("rate_bp 必须 ∈ [0, 3000] (上限 30%)")


def create_config(
    db: Session,
    *,
    team_id: Optional[int],
    tenant_id: Optional[int] = None,
    enabled: bool = False,
    rate_bp: int = 0,
    scope: str = "all",
    user_ids: Optional[list] = None,
    note: Optional[str] = None,
) -> PlatformFeeConfig:
    """创建平台服务费配置 (管理端预留 CRUD)。"""
    _validate_rate_bp(rate_bp)
    cfg = PlatformFeeConfig(
        tenant_id=tenant_id,
        team_id=team_id,
        enabled=enabled,
        rate_bp=rate_bp,
        scope=FeeScope(scope),
        user_ids=user_ids,
        note=note,
    )
    db.add(cfg)
    db.commit()
    db.refresh(cfg)
    return cfg


def update_config(db: Session, cfg: PlatformFeeConfig, **fields) -> PlatformFeeConfig:
    """更新配置 (仅允许字段白名单)。"""
    allowed = {"enabled", "rate_bp", "scope", "user_ids", "note", "tenant_id"}
    for k, v in fields.items():
        if k not in allowed:
            continue
        if k == "rate_bp":
            _validate_rate_bp(v)
        if k == "scope":
            cfg.scope = FeeScope(v)
        else:
            setattr(cfg, k, v)
    db.commit()
    db.refresh(cfg)
    return cfg


def to_dict(cfg: PlatformFeeConfig) -> dict:
    return {
        "id": cfg.id,
        "tenant_id": cfg.tenant_id,
        "team_id": cfg.team_id,
        "enabled": cfg.enabled,
        "rate_bp": cfg.rate_bp,
        "scope": cfg.scope.value,
        "user_ids": cfg.user_ids or [],
        "note": cfg.note,
        "created_at": cfg.created_at.isoformat() if cfg.created_at else None,
        "updated_at": cfg.updated_at.isoformat() if cfg.updated_at else None,
    }
