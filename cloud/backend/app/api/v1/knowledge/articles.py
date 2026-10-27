"""知识库文章端点（拆分自原 knowledge.py）。"""
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from fastapi.responses import JSONResponse

from app.core.database import get_db
from app.api.v1.auth import get_current_user
from app.models.user import User
from app.models.knowledge import KnowledgeArticle
from app.services.audit_service import audit_service
from app.core.response import success_response, paginated_response, action_response

from ._shared import logger, _kb_team_clause, _kb_resource_denied, _ROUTER_DEPENDENCIES


router = APIRouter(dependencies=_ROUTER_DEPENDENCIES)


class ArticleCreate(BaseModel):
    title: str
    content: str
    category: str = Field("general", max_length=50)
    tags: Optional[str] = None


class ArticleUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[str] = None
    published: Optional[bool] = None


class ArticleResponse(BaseModel):
    id: int
    title: str
    content: str
    category: str
    tags: Optional[str] = None
    view_count: int = 0
    published: bool = False
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    author_id: Optional[int] = None

    class Config:
        from_attributes = True


@router.get("/articles")
def list_articles(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取知识库文章列表（分页 + 鉴权）"""
    try:
        query = db.query(KnowledgeArticle)
        # team scoping（任务卡 1c19b59a）：非 admin 仅本企业 + 平台共享(team_id=0)。
        _clause = _kb_team_clause(KnowledgeArticle, current_user)
        if _clause is not None:
            query = query.filter(_clause)
        if category:
            query = query.filter(KnowledgeArticle.category == category)
        if search:
            query = query.filter(
                (KnowledgeArticle.title.ilike(f"%{search}%")) |
                (KnowledgeArticle.content.ilike(f"%{search}%"))
            )

        total = query.count()
        items = query.order_by(KnowledgeArticle.created_at.desc()).offset((page-1)*page_size).limit(page_size).all()

        items_dict = []
        for item in items:
            items_dict.append({
                "id": item.id,
                "title": item.title,
                "content": item.content,
                "category": item.category,
                "tags": item.tags,
                "view_count": item.view_count or 0,
                "published": item.published or False,
                "created_at": str(item.created_at) if item.created_at else None,
                "updated_at": str(item.updated_at) if item.updated_at else None,
                "author_id": item.author_id
            })

        return paginated_response(items_dict, total, page, page_size)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("list_articles 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.get("/articles/{article_id}")
def get_article(
    article_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取文章详情（鉴权）"""
    try:
        article = db.query(KnowledgeArticle).filter(KnowledgeArticle.id == article_id).first()
        if not article or _kb_resource_denied(article, current_user):
            raise HTTPException(status_code=404, detail="文章不存在")

        # 增加浏览次数
        article.view_count = (article.view_count or 0) + 1
        db.commit()

        return success_response({
            "id": article.id,
            "title": article.title,
            "content": article.content,
            "category": article.category,
            "tags": article.tags,
            "view_count": article.view_count,
            "published": article.published or False,
            "created_at": str(article.created_at) if article.created_at else None,
            "updated_at": str(article.updated_at) if article.updated_at else None,
            "author_id": article.author_id
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("get_article 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.post("/articles")
def create_article(
    data: ArticleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """创建文章（鉴权）"""
    try:
        article = KnowledgeArticle(
            title=data.title,
            content=data.content,
            category=data.category,
            tags=data.tags,
            author_id=current_user.id,
            published=True,
            team_id=current_user.team_id or 0,
        )
        db.add(article)
        db.commit()
        db.refresh(article)

        audit_service.log_crud(
            current_user.id,
            current_user.username,
            "create",
            "knowledge",
            str(article.id)
        )

        return success_response({
            "id": article.id,
            "title": article.title,
            "content": article.content,
            "category": article.category,
            "tags": article.tags,
            "view_count": article.view_count or 0,
            "published": article.published or False,
            "created_at": str(article.created_at) if article.created_at else None,
            "author_id": article.author_id
        }, message="文章创建成功")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("create_article 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.put("/articles/{article_id}")
def update_article(
    article_id: int,
    data: ArticleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """更新文章（鉴权）"""
    try:
        article = db.query(KnowledgeArticle).filter(KnowledgeArticle.id == article_id).first()
        if not article or _kb_resource_denied(article, current_user):
            raise HTTPException(status_code=404, detail="文章不存在")

        if data.title is not None:
            article.title = data.title
        if data.content is not None:
            article.content = data.content
        if data.category is not None:
            article.category = data.category
        if data.tags is not None:
            article.tags = data.tags
        if data.published is not None:
            article.published = data.published

        db.commit()
        db.refresh(article)

        audit_service.log_crud(
            current_user.id,
            current_user.username,
            "update",
            "knowledge",
            str(article_id)
        )

        return success_response({
            "id": article.id,
            "title": article.title,
            "content": article.content,
            "category": article.category,
            "tags": article.tags,
            "view_count": article.view_count or 0,
            "published": article.published or False,
            "updated_at": str(article.updated_at) if article.updated_at else None,
            "author_id": article.author_id
        }, message="文章更新成功")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("update_article 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.delete("/articles/{article_id}")
def delete_article(
    article_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """删除文章（鉴权）"""
    try:
        article = db.query(KnowledgeArticle).filter(KnowledgeArticle.id == article_id).first()
        if not article or _kb_resource_denied(article, current_user):
            raise HTTPException(status_code=404, detail="文章不存在")

        db.delete(article)
        db.commit()

        audit_service.log_crud(
            current_user.id,
            current_user.username,
            "delete",
            "knowledge",
            str(article_id)
        )

        return action_response(success=True, message="文章已删除")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("delete_article 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})
