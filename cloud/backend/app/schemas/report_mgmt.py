"""
报告管理 API 请求模型

任务卡 7011daeb：将 report_mgmt.py 路由的 `data: dict` 替换为 Pydantic BaseModel，
提供类型校验与 OpenAPI 字段文档。

字段全部 Optional（默认 None）以复刻原 dict 语义：
- create 端点用 model_dump()，未传字段为 None（与原 data.get(k)=None 一致，
  SQL 全字段 INSERT 写 NULL）。
- update 端点用 model_dump(exclude_unset=True)，仅更新客户端实际传入字段，
  复刻原 `if k in data` 行为。
"""
from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class ReportCreateRequest(BaseModel):
    """创建报告请求"""
    title: Optional[str] = Field(None, description="报告标题")
    type: Optional[str] = Field(None, description="报告类型（如 月报/周报/日报）")
    station_id: Optional[int] = Field(None, description="关联站点ID")
    author: Optional[str] = Field(None, description="作者")
    status: Optional[str] = Field(None, description="状态（draft/published）")
    content: Optional[str] = Field(None, description="报告内容")
    summary: Optional[str] = Field(None, description="摘要")
    period_start: Optional[date] = Field(None, description="统计周期开始")
    period_end: Optional[date] = Field(None, description="统计周期结束")


class ReportUpdateRequest(BaseModel):
    """更新报告请求（所有字段可选，仅更新传入字段）"""
    title: Optional[str] = Field(None, description="报告标题")
    type: Optional[str] = Field(None, description="报告类型")
    station_id: Optional[int] = Field(None, description="关联站点ID")
    author: Optional[str] = Field(None, description="作者")
    status: Optional[str] = Field(None, description="状态")
    content: Optional[str] = Field(None, description="报告内容")
    summary: Optional[str] = Field(None, description="摘要")
    period_start: Optional[date] = Field(None, description="统计周期开始")
    period_end: Optional[date] = Field(None, description="统计周期结束")
