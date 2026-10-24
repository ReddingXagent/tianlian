"""知识库 FAQ 端点（拆分自原 knowledge.py）。"""
from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional
from pydantic import BaseModel
from sqlalchemy import distinct
from sqlalchemy.orm import Session
from fastapi.responses import JSONResponse

from app.core.database import get_db
from app.api.v1.auth import get_current_user
from app.models.user import User
from app.models.knowledge import KnowledgeFAQ
from app.services.audit_service import audit_service
from app.core.response import success_response

from ._shared import logger, _kb_team_clause, _kb_resource_denied, _ROUTER_DEPENDENCIES


router = APIRouter(dependencies=_ROUTER_DEPENDENCIES)


class FAQItem(BaseModel):
    question: str
    answer: str
    category: str
    tags: Optional[List[str]] = None

class FAQBatchImport(BaseModel):
    faqs: List[FAQItem]

class FAQResponse(BaseModel):
    id: int
    question: str
    answer: str
    category: str
    tags: Optional[str] = None
    views: int = 0
    helpful_count: int = 0
    created_at: Optional[str] = None

    class Config:
        from_attributes = True


# ========== FAQ 端点 ==========

@router.get("/faq")
def list_faq(
    category: Optional[str] = None,
    q: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取FAQ列表（支持分类筛选和关键词搜索）"""
    try:
        query = db.query(KnowledgeFAQ)
        # team scoping（任务卡 1c19b59a）：非 admin 仅本企业 + 平台共享(team_id=0)。
        _clause = _kb_team_clause(KnowledgeFAQ, current_user)
        if _clause is not None:
            query = query.filter(_clause)
        if category:
            query = query.filter(KnowledgeFAQ.category == category)
        if q:
            query = query.filter(
                (KnowledgeFAQ.question.ilike(f"%{q}%")) |
                (KnowledgeFAQ.answer.ilike(f"%{q}%"))
            )

        items = query.order_by(KnowledgeFAQ.views.desc(), KnowledgeFAQ.created_at.desc()).all()

        return success_response([{
            "id": item.id,
            "question": item.question,
            "answer": item.answer,
            "category": item.category,
            "tags": item.tags,
            "views": item.views or 0,
            "helpful_count": item.helpful_count or 0,
            "created_at": str(item.created_at) if item.created_at else None
        } for item in items])
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("list_faq 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.post("/faq")
def create_faq(
    data: FAQItem,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """创建单个FAQ"""
    try:
        faq = KnowledgeFAQ(
            question=data.question,
            answer=data.answer,
            category=data.category,
            tags=','.join(data.tags) if data.tags else None,
            author_id=current_user.id,
            team_id=current_user.team_id or 0,
        )
        db.add(faq)
        db.commit()
        db.refresh(faq)

        audit_service.log_crud(
            current_user.id,
            current_user.username,
            "create",
            "faq",
            str(faq.id)
        )

        return success_response({
            "id": faq.id,
            "question": faq.question,
            "answer": faq.answer,
            "category": faq.category,
            "tags": faq.tags,
            "views": 0,
            "helpful_count": 0,
            "created_at": str(faq.created_at) if faq.created_at else None
        }, message="FAQ创建成功")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("create_faq 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.post("/faq/batch-import")
def batch_import_faq(
    data: FAQBatchImport,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """批量导入FAQ"""
    try:
        imported = []
        for item in data.faqs:
            faq = KnowledgeFAQ(
                question=item.question,
                answer=item.answer,
                category=item.category,
                tags=','.join(item.tags) if item.tags else None,
                author_id=current_user.id,
                team_id=current_user.team_id or 0,
            )
            db.add(faq)
            imported.append(faq)

        db.commit()

        audit_service.log_crud(
            current_user.id,
            current_user.username,
            "batch_import",
            "faq",
            f"count={len(imported)}"
        )

        return success_response({
            "imported_count": len(imported),
            "items": [{
                "id": f.id,
                "question": f.question,
                "category": f.category
            } for f in imported]
        }, message=f"成功导入{len(imported)}个FAQ")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("batch_import_faq 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.put("/faq/{faq_id}/helpful")
def mark_faq_helpful(
    faq_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """标记FAQ有帮助"""
    try:
        faq = db.query(KnowledgeFAQ).filter(KnowledgeFAQ.id == faq_id).first()
        if not faq or _kb_resource_denied(faq, current_user):
            raise HTTPException(status_code=404, detail="FAQ不存在")

        faq.helpful_count = (faq.helpful_count or 0) + 1
        db.commit()

        return success_response({"helpful_count": faq.helpful_count})
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("mark_faq_helpful 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.get("/faq/categories")
def list_faq_categories(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取FAQ分类列表"""
    try:
        categories = db.query(distinct(KnowledgeFAQ.category)).all()
        return success_response([c[0] for c in categories if c[0]])
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("list_faq_categories 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})
