"""
统一响应格式包装器

所有 API 响应必须使用以下统一格式：
{
    "code": 200,
    "message": "success",
    "data": <数据>,
    "timestamp": <UTC时间戳>
}

分页响应格式：
{
    "code": 200,
    "message": "success",
    "data": {
        "items": [...],
        "total": N,
        "page": 1,
        "page_size": 20
    },
    "timestamp": <UTC时间戳>
}
"""
from datetime import datetime, timezone
from typing import Any, List


def success_response(data: Any = None, message: str = "success") -> dict:
    """
    成功响应（单条记录或简单数据）
    
    Args:
        data: 返回的数据（可以是字典、列表、对象等）
        message: 提示消息
    
    Returns:
        统一格式的响应字典
    """
    return {
        "code": 200,
        "message": message,
        "data": data,
        "timestamp": int(datetime.now(timezone.utc).timestamp())
    }


def paginated_response(
    items: List[Any],
    total: int,
    page: int,
    page_size: int,
    message: str = "success"
) -> dict:
    """
    分页响应
    
    Args:
        items: 数据项列表
        total: 总记录数
        page: 当前页码
        page_size: 每页大小
        message: 提示消息
    
    Returns:
        统一格式的分页响应字典
    """
    return {
        "code": 200,
        "message": message,
        "data": {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size
        },
        "timestamp": int(datetime.now(timezone.utc).timestamp())
    }


def error_response(
    code: int,
    message: str,
    data: Any = None
) -> dict:
    """
    错误响应
    
    Args:
        code: 错误码（400, 404, 500等）
        message: 错误消息
        data: 可选的额外数据
    
    Returns:
        统一格式的错误响应字典
    """
    return {
        "code": code,
        "message": message,
        "data": data,
        "timestamp": int(datetime.now(timezone.utc).timestamp())
    }


def action_response(
    success: bool = True,
    message: str = "操作成功",
    data: Any = None
) -> dict:
    """
    操作响应（用于删除、更新状态等操作）
    
    Args:
        success: 操作是否成功
        message: 提示消息
        data: 可选的额外数据
    
    Returns:
        统一格式的操作响应字典
    """
    return {
        "code": 200 if success else 500,
        "message": message,
        "data": data,
        "timestamp": int(datetime.now(timezone.utc).timestamp())
    }