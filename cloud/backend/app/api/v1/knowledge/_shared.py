"""知识库 API 共享定义（拆分自原 knowledge.py）。

仅存放跨子模块复用的模块级对象：logger、team 过滤 helper、关键词高亮 helper、
以及 router 级鉴权依赖列表。端点本身按域拆分到同包各子模块。
"""
import logging
import re

from fastapi import Depends

from app.api.deps import is_platform_admin
from app.middleware.permission import require_write_permission


logger = logging.getLogger("app.api.v1.knowledge")


# 知识库写操作 router 级依赖（原 knowledge.py 顶层 router 的 dependencies）
_ROUTER_DEPENDENCIES = [Depends(require_write_permission("knowledge:manage"))]


def _kb_team_clause(model, user):
    """知识库 team 过滤子句：admin 全见(返回 None)；团队级 team_id in (0, user.team_id)。

    数据隔离语义同 chat 服务(ai_chat._team_scope)：team_id=0 为平台共享(全平台可见)，
    >0 为企业专属(仅本企业可见)。admin/super_admin 豁免见全部。
    """
    if is_platform_admin(user):
        return None
    return model.team_id.in_([0, user.team_id or 0])


def _kb_resource_denied(item, user) -> bool:
    """单条知识资源归属拒绝：admin 放行；团队级仅 team_id in (0, user.team_id) 可见。"""
    if is_platform_admin(user):
        return False
    return item.team_id not in (0, user.team_id or 0)


def highlight_text(text: str, keyword: str, max_len: int = 200) -> str:
    """
    在文本中高亮关键词，返回带 <mark> 标签的片段
    """
    if not text or not keyword:
        return text[:max_len] if text else ""

    # 转义正则特殊字符
    escaped_keyword = re.escape(keyword)
    # 查找关键词位置
    pattern = re.compile(escaped_keyword, re.IGNORECASE)
    match = pattern.search(text)
    if not match:
        return text[:max_len]

    # 计算片段范围：关键词前后各100字符
    start = max(0, match.start() - 100)
    end = min(len(text), match.end() + 100)
    snippet = text[start:end]

    # 高亮关键词
    highlighted = pattern.sub(f'<mark>{keyword}</mark>', snippet)

    # 添加省略号
    prefix = '...' if start > 0 else ''
    suffix = '...' if end < len(text) else ''

    return f'{prefix}{highlighted}{suffix}'
