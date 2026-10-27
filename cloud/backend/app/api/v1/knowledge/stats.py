"""知识库统计摘要 + 全文搜索端点（拆分自原 knowledge.py）。"""
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional
from sqlalchemy import distinct, func
from sqlalchemy.orm import Session
from fastapi.responses import JSONResponse

from app.core.database import get_db
from app.api.v1.auth import get_current_user
from app.models.user import User
from app.models.knowledge import KnowledgeArticle, KnowledgeFAQ
from app.core.response import success_response, paginated_response

from ._shared import logger, _kb_team_clause, highlight_text, _ROUTER_DEPENDENCIES


router = APIRouter(dependencies=_ROUTER_DEPENDENCIES)


@router.get("/stats/summary")
def get_stats_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取知识库统计摘要（鉴权）"""
    try:
        _stat_clause = _kb_team_clause(KnowledgeArticle, current_user)

        def _scoped(q):
            return q.filter(_stat_clause) if _stat_clause is not None else q

        total = _scoped(db.query(KnowledgeArticle)).count()

        # 分类数量
        categories_count = _scoped(db.query(distinct(KnowledgeArticle.category))).count()

        # 总浏览量
        total_views_result = _scoped(db.query(func.sum(KnowledgeArticle.view_count))).scalar()
        total_views = total_views_result or 0

        # 最多文章的分类
        top_category = _scoped(db.query(
            KnowledgeArticle.category,
            func.count(KnowledgeArticle.id).label('count')
        )).group_by(KnowledgeArticle.category).order_by(func.count(KnowledgeArticle.id).desc()).first()

        return success_response({
            "total": total,
            "categories": categories_count,
            "total_views": int(total_views),
            "top_category": top_category[0] if top_category else None,
            "top_category_count": top_category[1] if top_category else 0
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("get_stats_summary 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.get("/search")
def search_knowledge(
    q: str = Query(..., description="搜索关键词"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    知识库全文搜索 - 搜索文章标题/内容和FAQ问题/答案
    返回：id, title, category, summary(高亮片段), author, updated_at
    支持分页
    """
    try:
        if not q or not q.strip():
            return paginated_response([], 0, page, page_size)

        keyword = q.strip()
        results = []

        # 搜索文章（join User 表获取 author 信息）
        _art_clause = _kb_team_clause(KnowledgeArticle, current_user)
        articles = db.query(
            KnowledgeArticle,
            User.username
        ).outerjoin(User, KnowledgeArticle.author_id == User.id).filter(
            (KnowledgeArticle.title.ilike(f"%{keyword}%")) |
            (KnowledgeArticle.content.ilike(f"%{keyword}%"))
        )
        if _art_clause is not None:
            articles = articles.filter(_art_clause)
        articles = articles.order_by(KnowledgeArticle.created_at.desc()).all()

        for article, author_name in articles:
            title_match = keyword.lower() in (article.title or '').lower()
            content_match = keyword.lower() in (article.content or '').lower()

            if title_match:
                summary = highlight_text(article.title, keyword, max_len=150)
            elif content_match:
                summary = highlight_text(article.content, keyword, max_len=200)
            else:
                summary = article.content[:200] if article.content else ""

            results.append({
                "id": article.id,
                "title": article.title,
                "category": article.category,
                "summary": summary,
                "author": author_name or "未知",
                "updated_at": article.updated_at.isoformat() if article.updated_at else None,
                "highlight": summary,  # 向后兼容
            })

        # 搜索FAQ（FAQ 无 author，用空值）
        _faq_clause = _kb_team_clause(KnowledgeFAQ, current_user)
        faqs = db.query(KnowledgeFAQ).filter(
            (KnowledgeFAQ.question.ilike(f"%{keyword}%")) |
            (KnowledgeFAQ.answer.ilike(f"%{keyword}%"))
        )
        if _faq_clause is not None:
            faqs = faqs.filter(_faq_clause)
        faqs = faqs.order_by(KnowledgeFAQ.created_at.desc()).all()

        for faq in faqs:
            question_match = keyword.lower() in (faq.question or '').lower()
            answer_match = keyword.lower() in (faq.answer or '').lower()

            if question_match:
                summary = highlight_text(faq.question, keyword, max_len=150)
            elif answer_match:
                summary = highlight_text(faq.answer, keyword, max_len=200)
            else:
                summary = faq.answer[:200] if faq.answer else ""

            results.append({
                "id": faq.id,
                "title": faq.question,
                "category": faq.category,
                "summary": summary,
                "author": None,
                "updated_at": faq.updated_at.isoformat() if faq.updated_at else None,
                "highlight": summary,  # 向后兼容
            })

        # 按时间排序
        results.sort(
            key=lambda x: x.get("updated_at") or "",
            reverse=True
        )

        total = len(results)
        start = (page - 1) * page_size
        end = start + page_size
        paginated_results = results[start:end]

        return paginated_response(paginated_results, total, page, page_size)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("search_knowledge 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})
