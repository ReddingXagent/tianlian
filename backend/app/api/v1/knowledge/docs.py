"""知识库文档生成端点（拆分自原 knowledge.py）。

注：旧版列表兼容路由 ``GET ""``（list_articles_legacy）因集合根空 path 限制，
已内联至包 ``__init__``。
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import Optional
from pydantic import BaseModel
from sqlalchemy.orm import Session
from fastapi.responses import JSONResponse

from app.core.database import get_db
from app.api.v1.auth import get_current_user
from app.models.user import User
from app.models.knowledge import KnowledgeArticle
from app.services.audit_service import audit_service
from app.core.response import success_response

from ._shared import logger, _kb_team_clause, _ROUTER_DEPENDENCIES


router = APIRouter(dependencies=_ROUTER_DEPENDENCIES)


class DocGenerateRequest(BaseModel):
    doc_type: str  # document/manual/checklist
    device_type: Optional[str] = None
    fault_code: Optional[str] = None
    title: Optional[str] = None


# ========== 文档生成端点 ==========

@router.post("/generate-doc")
def generate_documentation(
    data: DocGenerateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """自动生成运维文档markdown"""
    try:
        from datetime import datetime, timezone

        # 生成文档内容
        title = data.title or f"运维手册 - {data.doc_type}"
        content_lines = [
            f"# {title}",
            "",
            f"**生成时间**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}",
            f"**文档类型**: {data.doc_type}",
            "",
            "---",
            ""
        ]

        if data.doc_type == "manual" and data.device_type:
            content_lines.extend([
                f"## 设备类型: {data.device_type}",
                "",
                "### 设备概述",
                "- 设备型号：待补充",
                "- 设备位置：待补充",
                "- 关联站点：待补充",
                "",
                "### 常见故障码",
                "| 故障码 | 描述 | 处理方案 |",
                "|--------|------|----------|",
                "| E001   | 通信故障 | 检查网络连接 |",
                "| E002   | 温度异常 | 检查散热系统 |",
                "",
                "### 维保步骤",
                "1. 定期检查设备状态",
                "2. 清洁设备外部",
                "3. 检查连接线路",
                "4. 记录运行参数",
                ""
            ])

        elif data.doc_type == "checklist":
            content_lines.extend([
                "## 检查清单",
                "",
                "### 日常巡检",
                "- [ ] 设备运行状态正常",
                "- [ ] 告警指示灯无异常",
                "- [ ] 温湿度在正常范围",
                "- [ ] 通信连接稳定",
                "",
                "### 定期维护",
                "- [ ] 设备清洁完成",
                "- [ ] 紧固件检查",
                "- [ ] 参数校准",
                "- [ ] 日志备份",
                ""
            ])

        elif data.fault_code:
            content_lines.extend([
                f"## 故障码: {data.fault_code}",
                "",
                "### 故障描述",
                "- 故障现象：待补充",
                "- 可能原因：待分析",
                "- 影响范围：待评估",
                "",
                "### 处理方案",
                "1. 初步诊断步骤",
                "2. 故障排查流程",
                "3. 修复操作步骤",
                "4. 验证测试步骤",
                ""
            ])

        else:
            # 从知识库相关文章提取
            _gd_clause = _kb_team_clause(KnowledgeArticle, current_user)
            _gd_q = db.query(KnowledgeArticle).filter(
                KnowledgeArticle.category == data.doc_type
            )
            if _gd_clause is not None:
                _gd_q = _gd_q.filter(_gd_clause)
            articles = _gd_q.limit(10).all()

            content_lines.extend([
                "## 相关知识库文章",
                ""
            ])
            for article in articles:
                content_lines.extend([
                    f"### {article.title}",
                    article.content[:200] + "...",
                    ""
                ])

        content_lines.extend([
            "---",
            "",
            "> **注意**: 此文档由系统自动生成，建议根据实际情况补充完善。",
            ""
        ])

        markdown_content = '\n'.join(content_lines)

        audit_service.log_crud(
            current_user.id,
            current_user.username,
            "generate",
            "doc",
            data.doc_type
        )

        return success_response({
            "title": title,
            "content": markdown_content,
            "format": "markdown",
            "generated_at": datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("generate_documentation 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})
