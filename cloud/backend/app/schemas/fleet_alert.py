"""
车队告警规则引擎 API 请求/响应模型 - SPEC §4.3

包含:
- FleetAlertRuleCreate: 创建规则请求体
- FleetAlertRuleUpdate: 更新规则请求体(全部可选)
- FleetAlertRuleResponse: 规则响应体
- FleetAlertRecordResponse: 告警记录响应体
"""
from datetime import datetime
from typing import Optional, List, Dict, Any

from pydantic import BaseModel, Field


class FleetAlertRuleCreate(BaseModel):
    """告警规则创建请求"""
    enterprise_id: int = Field(..., gt=0, description="企业ID")
    rule_type: str = Field(..., description="规则类型: low_battery/abnormal_charging/overtime_parking")
    threshold: Dict[str, Any] = Field(
        default_factory=dict,
        description="阈值配置, 如 low_battery:{soc_below:20}",
    )
    notify_channels: List[str] = Field(
        default_factory=list,
        description="通知渠道, 如 [im, sms]",
    )
    enable: bool = Field(default=True, description="是否启用")


class FleetAlertRuleUpdate(BaseModel):
    """告警规则更新请求(全部可选)"""
    rule_type: Optional[str] = Field(None, description="规则类型")
    threshold: Optional[Dict[str, Any]] = Field(None, description="阈值配置")
    notify_channels: Optional[List[str]] = Field(None, description="通知渠道")
    enable: Optional[bool] = Field(None, description="是否启用")


class FleetAlertTestPayload(BaseModel):
    """告警规则手动测试触发请求体 (卡 dfa3097f D2)

    替代裸 Dict[str, Any], 启用 Pydantic 校验, 杜绝非法 vehicle_id 类型穿透。
    """
    vehicle_id: Optional[int] = Field(None, gt=0, description="可选: 关联车辆ID, 必须属于规则所在企业")


class FleetAlertRuleResponse(BaseModel):
    """告警规则响应"""
    id: int
    enterprise_id: int
    rule_type: str
    threshold: Dict[str, Any]
    notify_channels: List[str]
    enable: bool
    created_at: Optional[datetime] = None


class FleetAlertRecordResponse(BaseModel):
    """告警记录响应"""
    id: int
    rule_id: int
    enterprise_id: int
    vehicle_id: Optional[int] = None
    plate_number: Optional[str] = None
    triggered_at: datetime
    alert_value: Optional[str] = None
    notified: bool
    status: str
