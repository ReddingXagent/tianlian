"""知识库分类端点（拆分自原 knowledge.py）。"""
from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy import distinct
from sqlalchemy.orm import Session
from fastapi.responses import JSONResponse

from app.core.database import get_db
from app.api.v1.auth import get_current_user
from app.models.user import User
from app.models.knowledge import KnowledgeArticle, KnowledgeCategory
from app.services.audit_service import audit_service
from app.core.response import success_response, action_response

from ._shared import logger, _ROUTER_DEPENDENCIES


router = APIRouter(dependencies=_ROUTER_DEPENDENCIES)


@router.get("/categories")
def list_categories(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取分类列表 - 返回完整分类对象"""
    try:
        categories = db.query(KnowledgeCategory).order_by(KnowledgeCategory.sort_order.asc(), KnowledgeCategory.id.asc()).all()
        return success_response([{
            "id": c.id,
            "name": c.name,
            "icon": c.icon or "",
            "sort_order": c.sort_order or 0,
            "description": c.description or "",
            "article_count": db.query(KnowledgeArticle).filter(KnowledgeArticle.category == c.name).count(),
            "created_at": str(c.created_at) if c.created_at else None,
        } for c in categories])
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("list_categories 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.post("/categories")
def create_category(
    name: str = Query(..., description="分类名称"),
    icon: str = Query("", description="图标"),
    sort_order: int = Query(0, description="排序"),
    description: str = Query("", description="描述"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """创建分类"""
    try:
        existing = db.query(KnowledgeCategory).filter(KnowledgeCategory.name == name).first()
        if existing:
            raise HTTPException(status_code=400, detail=f"分类 '{name}' 已存在")

        cat = KnowledgeCategory(
            name=name,
            icon=icon,
            sort_order=sort_order,
            description=description
        )
        db.add(cat)
        db.commit()
        db.refresh(cat)

        audit_service.log_crud(
            current_user.id, current_user.username, "create", "knowledge_category", str(cat.id)
        )

        return success_response({
            "id": cat.id,
            "name": cat.name,
            "icon": cat.icon or "",
            "sort_order": cat.sort_order or 0,
            "description": cat.description or "",
            "created_at": str(cat.created_at) if cat.created_at else None,
        }, message="分类创建成功")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("create_category 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.put("/categories/{category_id}")
def update_category(
    category_id: int,
    name: str = Query(None, description="分类名称"),
    icon: str = Query(None, description="图标"),
    sort_order: int = Query(None, description="排序"),
    description: str = Query(None, description="描述"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """更新分类"""
    try:
        cat = db.query(KnowledgeCategory).filter(KnowledgeCategory.id == category_id).first()
        if not cat:
            raise HTTPException(status_code=404, detail="分类不存在")

        if name is not None:
            existing = db.query(KnowledgeCategory).filter(
                KnowledgeCategory.name == name, KnowledgeCategory.id != category_id
            ).first()
            if existing:
                raise HTTPException(status_code=400, detail=f"分类 '{name}' 已存在")
            cat.name = name
        if icon is not None:
            cat.icon = icon
        if sort_order is not None:
            cat.sort_order = sort_order
        if description is not None:
            cat.description = description

        db.commit()
        db.refresh(cat)

        audit_service.log_crud(
            current_user.id, current_user.username, "update", "knowledge_category", str(category_id)
        )

        return success_response({
            "id": cat.id,
            "name": cat.name,
            "icon": cat.icon or "",
            "sort_order": cat.sort_order or 0,
            "description": cat.description or "",
            "created_at": str(cat.created_at) if cat.created_at else None,
            "updated_at": str(cat.updated_at) if cat.updated_at else None,
        }, message="分类更新成功")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("update_category 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.delete("/categories/{category_id}")
def delete_category(
    category_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """删除分类"""
    try:
        cat = db.query(KnowledgeCategory).filter(KnowledgeCategory.id == category_id).first()
        if not cat:
            raise HTTPException(status_code=404, detail="分类不存在")

        # 检查是否有文章使用此分类
        article_count = db.query(KnowledgeArticle).filter(KnowledgeArticle.category == cat.name).count()
        if article_count > 0:
            raise HTTPException(status_code=400, detail=f"分类 '{cat.name}' 下有 {article_count} 篇文章，无法删除")

        db.delete(cat)
        db.commit()

        audit_service.log_crud(
            current_user.id, current_user.username, "delete", "knowledge_category", str(category_id)
        )

        return action_response(success=True, message=f"分类 '{cat.name}' 已删除")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("delete_category 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


# 保持向后兼容的旧路由
@router.get("/categories/list")
def list_categories_legacy(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取分类列表（旧版兼容）"""
    try:
        categories = db.query(distinct(KnowledgeArticle.category)).all()
        cats_from_db = db.query(KnowledgeCategory).order_by(KnowledgeCategory.sort_order.asc()).all()
        cat_names = [c[0] for c in categories if c[0]]
        cat_objs = [{
            "id": c.id, "name": c.name, "icon": c.icon or "",
            "sort_order": c.sort_order or 0, "description": c.description or ""
        } for c in cats_from_db]
        return success_response({"categories": cat_names, "items": cat_objs})
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("list_categories_legacy 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})
