"""工单 Pydantic Schema + 活跃/完成态常量 — 从原 workorders.py 拆出 (卡 1ed83abf)。

原文件内 ``WorkOrderTransfer`` / ``WorkOrderUrge`` 也归并到此, 统一 Schema 入口。
对外符号由包 ``__init__`` 重导出, import 路径不变。
"""
from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.models.workorder import WorkOrderStatus

# 卡 77a186b3：自由字符串收紧为 Literal，防止任意字符串污染状态机
WorkOrderTypeLiteral = Literal[
    "preventive", "emergency", "plan", "maintenance", "inspection", "upgrade", "repair"
]
WorkOrderStatusLiteral = Literal[
    "pending", "accepted", "processing", "pending_verify",
    "completed", "assigned", "in_progress", "resolved", "closed",
]


class WorkOrderCreate(BaseModel):
    fault_desc: str  # 故障描述
    type: WorkOrderTypeLiteral = "repair"
    level: str = "warning"
    station_id: Optional[int] = None
    device_id: Optional[int] = None
    source: str = "manual"  # 来源 manual/alarm/app/inspection (maint-spec §4)


class WorkOrderUpdate(BaseModel):
    fault_desc: Optional[str] = None
    level: Optional[str] = None
    status: Optional[WorkOrderStatusLiteral] = None
    assignee_id: Optional[int] = None
    solution: Optional[str] = None


class WorkOrderDispatch(BaseModel):
    auto: bool = True  # 是否自动派单


# 工单活跃态（可签到/支援/申请备件）与完成态（可评价）
_ACTIVE_STATUSES = [WorkOrderStatus.ACCEPTED, WorkOrderStatus.PROCESSING, WorkOrderStatus.PENDING_VERIFY]
_DONE_STATUSES = [WorkOrderStatus.COMPLETED, WorkOrderStatus.RESOLVED, WorkOrderStatus.CLOSED]


class WorkOrderCheckinSchema(BaseModel):
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    address: Optional[str] = None
    note: Optional[str] = None
    photo_url: Optional[str] = None


class WorkOrderSupportSchema(BaseModel):
    target_engineer_id: Optional[int] = None
    reason: str
    remote: bool = False


class WorkOrderSparePartSchema(BaseModel):
    part_name: str
    part_model: Optional[str] = None
    quantity: int = Field(1, ge=1)
    reason: str


class WorkOrderRateSchema(BaseModel):
    response_rating: int = Field(..., ge=1, le=5)   # 响应速度
    quality_rating: int = Field(..., ge=1, le=5)    # 维修质量
    attitude_rating: int = Field(..., ge=1, le=5)   # 服务态度
    comment: Optional[str] = None


class WorkOrderAcceptanceSchema(BaseModel):
    """站长一站式验收 — 评分+评语+通过/驳回"""
    response_rating: int = Field(..., ge=1, le=5)   # 响应速度
    quality_rating: int = Field(..., ge=1, le=5)    # 维修质量
    attitude_rating: int = Field(..., ge=1, le=5)   # 服务态度
    comment: Optional[str] = None
    reject: bool = False                            # True=驳回回退处理, False=通过验收


class WorkOrderTransfer(BaseModel):
    """转单请求"""
    target_engineer_id: int
    reason: str


class WorkOrderUrge(BaseModel):
    """催单请求"""
    message: Optional[str] = "请尽快处理"
