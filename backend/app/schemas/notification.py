"""Notification API schemas"""
from pydantic import BaseModel, Field
from typing import Optional


class NotificationChannel(BaseModel):
    sms: bool = Field(True, description="是否开启短信")
    email: bool = Field(True, description="是否开启邮件")
    app: bool = Field(True, description="是否开启APP推送")
    im_b: bool = Field(True, description="是否开启企业IM-B")
    im: bool = Field(True, description="是否开启飞信")
    dashboard: bool = Field(False, description="是否开启客服端板")  # Not in original but may be useful


class NotificationConfigResponse(BaseModel):
    """单个通知配置响应"""
    id: int = Field(..., description="配置ID")
    target_type: str = Field(..., description="目标类型: user/station/global")
    target_id: int = Field(..., description="目标ID或0(全局)")
    sms_enabled: bool = Field(..., description="短信开关")
    email_enabled: bool = Field(..., description="邮件开关")
    app_enabled: bool = Field(..., description="APP推送开关")
    im_b_enabled: bool = Field(..., description="企业IM-B开关")
    im_enabled: bool = Field(..., description="IM开关")
    quiet_start: Optional[str] = Field(None, description="免打扰开始时间")
    quiet_end: Optional[str] = Field(None, description="免打扰结束时间")
    enabled: bool = Field(..., description="整体开关")
    
    class Config:
        allow_scrum = True  # Enable true for Field alias matching
        json_encoders = {
            str: str,
        }