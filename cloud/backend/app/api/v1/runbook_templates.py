"""
Runbook 模板 CRUD API (spec maint-platform §2.6)

将原硬编码模板持久化到 DB, 支持列表(分页+筛选)/详情/创建/更新/删除。
执行匹配由 RunbookEngine 负责 (DB active 模板优先, fallback 内置)。
"""
import logging

from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import JSONResponse
from typing import Optional, List, Literal
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.core.database import get_db
from app.models.runbook import RunbookTemplateModel, TEMPLATE_STATUS_VALUES
from app.core.response import success_response, paginated_response, action_response
from pydantic import BaseModel
from app.middleware.permission import require_write_permission

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_write_permission("healing:manage"))])


# ─── Pydantic Schemas ───

class TemplateCreate(BaseModel):
    name: str
    category: Literal["inverter", "charger", "pcs", "bms", "ems", "ess", "general"] = "general"
    alarm_type: Optional[str] = None          # 缺省 = name
    description: Optional[str] = None
    steps: Optional[List[dict]] = None         # 透传存储
    status: Optional[Literal["active", "inactive"]] = None   # 缺省 active


class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[Literal["inverter", "charger", "pcs", "bms", "ems", "ess", "general"]] = None
    alarm_type: Optional[str] = None
    description: Optional[str] = None
    steps: Optional[List[dict]] = None
    status: Optional[Literal["active", "inactive"]] = None


# ─── 序列化助手 ───

def _step_summary(steps):
    """统计总/自动/人工步数"""
    steps = steps or []
    auto_n = sum(1 for s in steps if s.get("auto_execute"))
    return len(steps), auto_n, len(steps) - auto_n


def template_to_dict(t: RunbookTemplateModel, include_steps: bool = False) -> dict:
    """ORM → dict。列表不含 steps(精简), 详情含 steps。"""
    total, auto_n, manual_n = _step_summary(t.steps)
    d = {
        "id": t.id,
        "name": t.name,
        "category": t.category,
        "alarm_type": t.alarm_type,
        "description": t.description,
        "step_count": total,
        "auto_steps": auto_n,
        "manual_steps": manual_n,
        "status": t.status,
        "version": t.version,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }
    if include_steps:
        d["steps"] = t.steps or []
    return d


# ─── 端点 ───

@router.get("/templates", tags=["Runbook模板"])
def list_templates(
    category: Optional[str] = None,
    status: Optional[str] = None,
    keyword: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """获取 Runbook 模板列表 (分页 + category/status 筛选 + 关键词)"""
    try:
        query = db.query(RunbookTemplateModel)

        if category:
            query = query.filter(RunbookTemplateModel.category == category)
        if status:
            query = query.filter(RunbookTemplateModel.status == status)
        if keyword:
            kw = f"%{keyword}%"
            query = query.filter(or_(
                RunbookTemplateModel.name.ilike(kw),
                RunbookTemplateModel.alarm_type.ilike(kw),
            ))

        total = query.count()
        items = (
            query.order_by(RunbookTemplateModel.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return paginated_response([template_to_dict(t) for t in items], total, page, page_size)
    except HTTPException:
        raise
    except Exception:
        logger.exception("list_templates 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.get("/templates/{template_id}", tags=["Runbook模板"])
def get_template(template_id: int, db: Session = Depends(get_db)):
    """获取 Runbook 模板详情 (含完整 steps)"""
    try:
        t = db.query(RunbookTemplateModel).filter(RunbookTemplateModel.id == template_id).first()
        if not t:
            raise HTTPException(status_code=404, detail="模板不存在")
        return success_response(template_to_dict(t, include_steps=True))
    except HTTPException:
        raise
    except Exception:
        logger.exception("get_template 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.post("/templates", tags=["Runbook模板"])
def create_template(data: TemplateCreate, db: Session = Depends(get_db)):
    """创建 Runbook 模板"""
    try:
        status = data.status or "active"
        if status not in TEMPLATE_STATUS_VALUES:
            raise HTTPException(status_code=400, detail=f"无效的状态: {status}")

        if db.query(RunbookTemplateModel).filter(RunbookTemplateModel.name == data.name).first():
            raise HTTPException(status_code=400, detail=f"模板名 '{data.name}' 已存在")

        new = RunbookTemplateModel(
            name=data.name,
            category=data.category,
            alarm_type=data.alarm_type or data.name,
            description=data.description,
            steps=data.steps,
            status=status,
            version=1,
        )
        db.add(new)
        db.commit()
        db.refresh(new)
        return success_response(template_to_dict(new, include_steps=True), message="模板创建成功")
    except HTTPException:
        raise
    except Exception:
        logger.exception("create_template 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.put("/templates/{template_id}", tags=["Runbook模板"])
def update_template(template_id: int, data: TemplateUpdate, db: Session = Depends(get_db)):
    """更新 Runbook 模板 (字段实际变化时 version +1)"""
    try:
        t = db.query(RunbookTemplateModel).filter(RunbookTemplateModel.id == template_id).first()
        if not t:
            raise HTTPException(status_code=404, detail="模板不存在")

        update_data = data.model_dump(exclude_unset=True)

        if "status" in update_data and update_data["status"] is not None:
            if update_data["status"] not in TEMPLATE_STATUS_VALUES:
                raise HTTPException(status_code=400, detail=f"无效的状态: {update_data['status']}")

        # alarm_type 显式传 null 不清空 (保留原值)
        if update_data.get("alarm_type") is None:
            update_data.pop("alarm_type", None)

        # 重名检查 (改名时)
        if "name" in update_data and update_data["name"] != t.name:
            dup = db.query(RunbookTemplateModel).filter(RunbookTemplateModel.name == update_data["name"]).first()
            if dup:
                raise HTTPException(status_code=400, detail=f"模板名 '{update_data['name']}' 已存在")

        changed = False
        for key, value in update_data.items():
            if getattr(t, key) != value:
                setattr(t, key, value)
                changed = True
        if changed:
            t.version = (t.version or 1) + 1

        db.commit()
        db.refresh(t)
        return success_response(template_to_dict(t, include_steps=True), message="模板已更新")
    except HTTPException:
        raise
    except Exception:
        logger.exception("update_template 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.delete("/templates/{template_id}", tags=["Runbook模板"])
def delete_template(template_id: int, db: Session = Depends(get_db)):
    """删除 Runbook 模板"""
    try:
        t = db.query(RunbookTemplateModel).filter(RunbookTemplateModel.id == template_id).first()
        if not t:
            raise HTTPException(status_code=404, detail="模板不存在")
        db.delete(t)
        db.commit()
        return action_response(success=True, message=f"模板 {template_id} 已删除")
    except HTTPException:
        raise
    except Exception:
        logger.exception("delete_template 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})
