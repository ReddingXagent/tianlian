"""运营平台 - 平台服务费配置 API (工作卡 280c85ee — 云端配套④ §4 预留)

契约: backend/docs/contracts/user-client-contract.md §4 (平台服务费预留, 暂不启用)
端点 (挂 /ops 前缀):
- GET    /ops/platform-fee        列表 (team scoping)
- POST   /ops/platform-fee        创建配置
- PUT    /ops/platform-fee/{id}   更新配置
- DELETE /ops/platform-fee/{id}   删除配置

本期仅落数据结构 + 管理端 CRUD, enabled 固定 false, 不接真实分账 (profitsharing)。
权限门: require_permission("operate:manage") + team scoping。
"""
import logging
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.v1.auth import get_current_user
from app.api.deps import team_scope, assert_team_access
from app.middleware.permission import require_permission
from app.models.user import User
from app.models.platform_fee_config import PlatformFeeConfig
from app.services.wx_pay import platform_fee as fee_svc
from app.services.wx_pay import response as rsp

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(require_permission("operate:manage"))])


class FeeConfigCreate(BaseModel):
    tenant_id: Optional[int] = None
    enabled: bool = False
    rate_bp: int = Field(0, ge=0, le=3000, description="费率基点, 上限 3000 (30%)")
    scope: Literal["all", "whitelist"] = "all"
    user_ids: Optional[list] = None
    note: Optional[str] = None


class FeeConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    rate_bp: Optional[int] = Field(None, ge=0, le=3000)
    scope: Optional[Literal["all", "whitelist"]] = None
    user_ids: Optional[list] = None
    note: Optional[str] = None


def _get_cfg(db: Session, cfg_id: int) -> Optional[PlatformFeeConfig]:
    return db.query(PlatformFeeConfig).filter(PlatformFeeConfig.id == cfg_id).first()


@router.get("/platform-fee", summary="平台服务费配置列表 (team scoping)")
def list_fee_configs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        q = db.query(PlatformFeeConfig)
        scope = team_scope(current_user)
        if scope is not None:
            q = q.filter(PlatformFeeConfig.team_id == scope)
        items = q.order_by(PlatformFeeConfig.id.desc()).all()
        return rsp.ok(
            {"items": [fee_svc.to_dict(c) for c in items], "total": len(items)}
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("list_fee_configs 异常")
        return JSONResponse(
            status_code=500, content={"detail": "服务器内部错误，请稍后重试"}
        )


@router.post("/platform-fee", status_code=201, summary="创建平台服务费配置")
def create_fee_config(
    body: FeeConfigCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        cfg = fee_svc.create_config(
            db,
            team_id=current_user.team_id,
            tenant_id=body.tenant_id,
            # 契约 §4: 本期 enabled 固定 false (端侧零感知, prepay 不体现抽佣),
            # 忽略请求体 enabled, 杜绝误启用平台服务费分账 (卡 05a0e2bb)。
            enabled=False,
            rate_bp=body.rate_bp,
            scope=body.scope,
            user_ids=body.user_ids,
            note=body.note,
        )
        return rsp.ok(fee_svc.to_dict(cfg))
    except fee_svc.InvalidFeeRate as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception:
        logger.exception("create_fee_config 异常")
        return JSONResponse(
            status_code=500, content={"detail": "服务器内部错误，请稍后重试"}
        )


@router.put("/platform-fee/{cfg_id}", summary="更新平台服务费配置 (team scoping)")
def update_fee_config(
    cfg_id: int,
    body: FeeConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        cfg = _get_cfg(db, cfg_id)
        if cfg is None:
            raise HTTPException(status_code=404, detail="配置不存在")
        assert_team_access(current_user, cfg.team_id)
        fields = body.model_dump(exclude_unset=True)
        cfg = fee_svc.update_config(db, cfg, **fields)
        return rsp.ok(fee_svc.to_dict(cfg))
    except fee_svc.InvalidFeeRate as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception:
        logger.exception("update_fee_config 异常")
        return JSONResponse(
            status_code=500, content={"detail": "服务器内部错误，请稍后重试"}
        )


@router.delete("/platform-fee/{cfg_id}", summary="删除平台服务费配置 (team scoping)")
def delete_fee_config(
    cfg_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        cfg = _get_cfg(db, cfg_id)
        if cfg is None:
            raise HTTPException(status_code=404, detail="配置不存在")
        assert_team_access(current_user, cfg.team_id)
        db.delete(cfg)
        db.commit()
        return rsp.ok({"deleted": cfg_id})
    except HTTPException:
        raise
    except Exception:
        logger.exception("delete_fee_config 异常")
        return JSONResponse(
            status_code=500, content={"detail": "服务器内部错误，请稍后重试"}
        )
