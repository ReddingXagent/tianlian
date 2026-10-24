from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

from app.models.settlement import SettlementStatus


class SettlementBillBase(BaseModel):
    enterprise_id: int = Field(..., description="企业ID")
    bill_period_start: datetime = Field(..., description="账期开始时间")
    bill_period_end: datetime = Field(..., description="账期结束时间")


class SettlementBillCreate(SettlementBillBase):
    pass


class SettlementBillResponse(SettlementBillBase):
    id: int
    total_orders: int
    total_energy_kwh: float
    total_charge_fee: float
    total_service_fee: float
    total_parking_fee: float
    total_discount: float
    total_amount: float
    total_paid: float
    balance: float
    status: SettlementStatus
    confirmed_at: Optional[datetime] = None
    paid_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True


class SettlementBillDetailResponse(BaseModel):
    id: int
    order_id: int
    vehicle_id: Optional[int] = None
    driver_id: Optional[int] = None
    charging_time: datetime
    energy_kwh: float
    fees: float
    created_at: datetime

    class Config:
        orm_mode = True


class SettlementBillConfirm(BaseModel):
    pass


class SettlementBillPay(BaseModel):
    pass


class SettlementInvoiceApply(BaseModel):
    # 发票申请可以扩展字段，如发票抬头、税号等，这里先保持简单
    invoice_title: str = Field(..., description="发票抬头")
    tax_number: str = Field(..., description="纳税人识别号")
    address: str = Field(..., description="注册地址")
    phone: str = Field(..., description="联系电话")
    bank_name: str = Field(..., description="开户银行")
    bank_account: str = Field(..., description="银行账户")