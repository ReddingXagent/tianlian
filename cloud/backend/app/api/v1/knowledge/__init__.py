"""知识库 API - 带鉴权版本（拆分为子路由包）。

原 ``app/api/v1/knowledge.py``（1021 行）按域拆分为同包子模块；本包 ``__init__``
按原文件端点声明顺序聚合各子模块 router，重建与原文件一致的 ``router``：
- 端点集合与注册顺序不变（旧版列表兼容路由 ``GET ""`` 因集合根空 path 限制，
  FastAPI 不允许以空 prefix ``include`` 含空 path 路由的子 router，故直接装饰在
  被 v1 带 ``prefix="/knowledge"`` 消费的本 router 上，位置仍为末尾，与原文件一致）。
- router 级鉴权依赖 ``require_write_permission("knowledge:manage")`` 由各子模块
  router 各自携带（FastAPI 不会把父 router 的 dependencies 传递给 include 进来的
  子路由），故 ``app.api.v1.knowledge.router`` 导入路径与行为保持向后兼容。

子模块：articles / categories / stats / faq / docs；共享定义见 ``_shared``。
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional
from sqlalchemy.orm import Session
from fastapi.responses import JSONResponse

from app.core.database import get_db
from app.api.v1.auth import get_current_user
from app.models.user import User
from app.models.knowledge import KnowledgeArticle
from app.core.response import paginated_response

from ._shared import logger, _kb_team_clause
from . import articles, categories, stats, faq, docs

# 按 knowledge.py 原端点声明顺序聚合：articles → categories → stats → faq → docs
router = APIRouter()
router.include_router(articles.router)
router.include_router(categories.router)
router.include_router(stats.router)
router.include_router(faq.router)
router.include_router(docs.router)


# 保持向后兼容的旧列表路由（集合根 GET ""，须直接定义在本 router 上——见模块 docstring）
@router.get("")
def list_articles_legacy(
    category: Optional[str] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取知识库列表（旧版兼容）"""
    try:
        query = db.query(KnowledgeArticle)
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
                "author_id": item.author_id
            })

        return paginated_response(items_dict, total, page, page_size)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("list_articles_legacy 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})
