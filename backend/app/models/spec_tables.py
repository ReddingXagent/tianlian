"""
SPEC §4 缺口补齐模型 - 运营管理平台 (ops-platform-spec.md)

本文件集中存放 ops-platform-spec.md §4「需新增的表」中尚未实现的表。
按 SPEC 分区组织: 用户类型 / 优惠管理 / 运营分析 / 订单与费用。

查重说明 (已存在近似表, 故未在本文件重建):
- invoices          -> app.models.ops_settlement.OpsInvoice (ops_invoices), 文档串引用 SPEC §2.5+§4, 字段超集
- coupon_claims     -> app.models.coupon.CouponUsage (coupon_usages), 覆盖领取+使用生命周期 (received_at/used_at/status)
- points_logs       -> app.models.points.PointsRecord (points_records), 文档串即「积分流水记录表」
- discount_prices   -> app.models.price_discount.PriceDiscount (price_discounts), 词序重命名+字段超集;
                       station_scope 由 DiscountGroup.station_ids 承载
"""
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import Column, Integer, String, Numeric, DateTime, Enum as SAEnum, Index, UniqueConstraint, event
import enum

from app.core.database import Base


# ═══════════════════════════════════════════════════════════════════
# 用户类型 (SPEC §4)
# ═══════════════════════════════════════════════════════════════════

class AppUser(Base):
    """APP 用户表 - 充电 APP 注册用户档案与累计统计"""
    __tablename__ = "app_users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True, comment="关联系统用户ID(users.id)")
    phone = Column(String(20), nullable=False, unique=True, index=True, comment="手机号")
    nickname = Column(String(100), nullable=True, comment="昵称")
    avatar = Column(String(500), nullable=True, comment="头像URL")
    balance = Column(Numeric(12, 2), default=Decimal("0.00"), comment="账户余额(元)")
    total_charge_kwh = Column(Numeric(12, 2), default=Decimal("0.00"), comment="累计充电量(kWh)")
    total_spent = Column(Numeric(12, 2), default=Decimal("0.00"), comment="累计消费(元)")
    level = Column(Integer, default=1, comment="用户等级")
    points = Column(Integer, default=0, comment="积分余额")
    status = Column(String(20), default="active", comment="状态 active/inactive")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")

    __table_args__ = (
        Index("idx_app_user_user_id", "user_id"),
        Index("idx_app_user_phone", "phone"),
        Index("idx_app_user_status", "status"),
    )


class CardUser(Base):
    """卡用户表 - 充电卡持卡人档案与余额"""
    __tablename__ = "card_users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    card_no = Column(String(50), nullable=False, unique=True, index=True, comment="卡号(唯一)")
    user_id = Column(Integer, nullable=True, index=True, comment="关联系统用户ID")
    holder_name = Column(String(100), nullable=True, comment="持卡人姓名")
    bind_phone = Column(String(20), nullable=True, index=True, comment="绑定手机号")
    balance = Column(Numeric(12, 2), default=Decimal("0.00"), comment="卡内余额(元)")
    status = Column(String(20), default="active", comment="状态 active/inactive/locked")
    issued_at = Column(DateTime, nullable=True, comment="发卡时间")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")

    __table_args__ = (
        Index("idx_card_user_card_no", "card_no"),
        Index("idx_card_user_user_id", "user_id"),
        Index("idx_card_user_phone", "bind_phone"),
    )


class VinUser(Base):
    """VIN 用户表 - 车辆识别码绑定的用户档案"""
    __tablename__ = "vin_users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    vin = Column(String(50), nullable=False, unique=True, index=True, comment="车辆识别码(VIN)")
    brand = Column(String(50), nullable=True, comment="品牌")
    model = Column(String(100), nullable=True, comment="车型")
    plate_number = Column(String(20), nullable=True, index=True, comment="车牌号")
    user_id = Column(Integer, nullable=True, index=True, comment="关联系统用户ID")
    bind_phone = Column(String(20), nullable=True, comment="绑定手机号")
    auto_pay_account = Column(String(100), nullable=True, comment="自动代扣账户")
    status = Column(String(20), default="active", comment="状态 active/inactive")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")

    __table_args__ = (
        Index("idx_vin_user_vin", "vin"),
        Index("idx_vin_user_user_id", "user_id"),
        Index("idx_vin_user_plate", "plate_number"),
    )


class InterconnectPlatform(Base):
    """互联互通平台表 - 第三方充电平台业务登记(联系人/分成/绑定)

    注: 平台「技术接入配置」(api_base_url/auth/sync) 见 app.models.admin_interconnect.InterconnectConfig;
        本表聚焦运营侧的业务登记信息。
    """
    __tablename__ = "interconnect_platforms"

    id = Column(Integer, primary_key=True, autoincrement=True)
    platform_name = Column(String(100), nullable=False, comment="平台名称")
    platform_code = Column(String(50), nullable=False, unique=True, index=True, comment="平台编码")
    api_key = Column(String(200), nullable=True, comment="对接API Key")
    contact = Column(String(100), nullable=True, comment="联系人")
    phone = Column(String(20), nullable=True, comment="联系电话")
    revenue_share_ratio = Column(Numeric(5, 4), default=Decimal("0.0000"), comment="我方分成比例(0.7000=70%)")
    bind_date = Column(DateTime, nullable=True, comment="绑定日期")
    status = Column(String(20), default="active", comment="状态 active/inactive")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")

    __table_args__ = (
        Index("idx_iplat_code", "platform_code"),
        Index("idx_iplat_status", "status"),
    )


class InterconnectUser(Base):
    """互联互通用户表 - 他平台导流过来的用户映射"""
    __tablename__ = "interconnect_users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    platform_id = Column(Integer, nullable=False, index=True, comment="关联互联互通平台ID")
    outer_user_id = Column(String(100), nullable=False, index=True, comment="外部平台用户标识")
    nickname = Column(String(100), nullable=True, comment="昵称")
    phone = Column(String(20), nullable=True, comment="手机号")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")

    __table_args__ = (
        Index("idx_iuser_platform", "platform_id"),
        Index("idx_iuser_outer", "outer_user_id"),
    )


class BillingCycle(str, enum.Enum):
    MONTHLY = "monthly"        # 月结
    QUARTERLY = "quarterly"    # 季结


class EnterpriseAccount(Base):
    """企业账户表 - 运营侧企业计费账户(信用代码/计费周期)

    注: 企业主数据(内部编码/信用额度) 见 app.models.enterprise.Enterprise;
        本表聚焦运营计费所需的企业账户视图。
    """
    __tablename__ = "enterprise_accounts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    enterprise_name = Column(String(200), nullable=False, comment="企业名称")
    credit_code = Column(String(50), nullable=True, index=True, comment="统一社会信用代码")
    contact_person = Column(String(100), nullable=True, comment="联系人")
    contact_phone = Column(String(20), nullable=True, comment="联系电话")
    balance = Column(Numeric(12, 2), default=Decimal("0.00"), comment="账户余额(元)")
    billing_cycle = Column(SAEnum(BillingCycle), default=BillingCycle.MONTHLY, comment="计费周期 monthly/quarterly")
    status = Column(String(20), default="active", comment="状态 active/inactive/suspended")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")

    __table_args__ = (
        Index("idx_eacct_credit_code", "credit_code"),
        Index("idx_eacct_status", "status"),
    )


class EnterpriseSubUser(Base):
    """企业子用户表 - 企业账户下的员工/部门子账号(含预算上限)"""
    __tablename__ = "enterprise_sub_users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    enterprise_id = Column(Integer, nullable=False, index=True, comment="关联企业账户ID")
    user_id = Column(Integer, nullable=False, index=True, comment="关联系统用户ID")
    department = Column(String(100), nullable=True, comment="部门")
    budget_limit = Column(Numeric(12, 2), default=Decimal("0.00"), comment="预算上限(元)")
    status = Column(String(20), default="active", comment="状态 active/inactive")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")

    __table_args__ = (
        Index("idx_esub_enterprise", "enterprise_id"),
        Index("idx_esub_user", "user_id"),
    )


# ═══════════════════════════════════════════════════════════════════
# 优惠管理 (SPEC §4)
# ═══════════════════════════════════════════════════════════════════

class CouponActivityStat(Base):
    """优惠券活动统计表 - 单个优惠券的领取/使用/抵扣汇总"""
    __tablename__ = "coupon_activity_stats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    coupon_id = Column(Integer, nullable=False, index=True, comment="关联优惠券ID")
    total_claimed = Column(Integer, default=0, comment="累计领取数")
    total_used = Column(Integer, default=0, comment="累计使用数")
    total_discount_amount = Column(Numeric(12, 2), default=Decimal("0.00"), comment="累计抵扣金额(元)")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")

    __table_args__ = (
        Index("idx_cas_coupon", "coupon_id"),
    )


# ═══════════════════════════════════════════════════════════════════
# 订单与费用 (SPEC §4)
# ═══════════════════════════════════════════════════════════════════

class OrderChargeCurve(Base):
    """订单充电曲线表 - 充电过程中按分钟记录的功率/电压/电流/SOC"""
    __tablename__ = "order_charge_curves"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(Integer, nullable=False, index=True, comment="关联订单ID(charging_orders.id)")
    record_time = Column(DateTime, nullable=False, comment="记录时间")
    current_power = Column(Numeric(10, 2), nullable=True, comment="当前功率(kW)")
    energy_this_minute = Column(Numeric(10, 4), default=Decimal("0.0000"), comment="本分钟电量(kWh)")
    voltage = Column(Numeric(10, 2), nullable=True, comment="电压(V)")
    current = Column(Numeric(10, 2), nullable=True, comment="电流(A)")
    soc = Column(Numeric(5, 2), nullable=True, comment="电池SOC(%)")

    __table_args__ = (
        Index("idx_occ_order", "order_id"),
        Index("idx_occ_order_time", "order_id", "record_time"),
    )


# ═══════════════════════════════════════════════════════════════════
# 运营分析 - 报表聚合 (SPEC §4)
# ═══════════════════════════════════════════════════════════════════

class RevenueDaily(Base):
    """营收日汇总表 - 按日期+用户类型+站点的营收聚合"""
    __tablename__ = "revenue_daily"

    id = Column(Integer, primary_key=True, autoincrement=True)
    record_date = Column(DateTime, nullable=False, index=True, comment="统计日期")
    user_type = Column(String(50), nullable=True, index=True, comment="用户类型 app/card/vin/interconnect/enterprise")
    station_id = Column(Integer, nullable=True, index=True, comment="站点ID")
    orders_count = Column(Integer, default=0, comment="订单数")
    energy_kwh = Column(Numeric(12, 2), default=Decimal("0.00"), comment="充电量(kWh)")
    charge_fee = Column(Numeric(12, 2), default=Decimal("0.00"), comment="电费(元)")
    service_fee = Column(Numeric(12, 2), default=Decimal("0.00"), comment="服务费(元)")
    parking_fee = Column(Numeric(12, 2), default=Decimal("0.00"), comment="停车费(元)")
    occupancy_fee = Column(Numeric(12, 2), default=Decimal("0.00"), comment="占桩费(元)")
    reservation_fee = Column(Numeric(12, 2), default=Decimal("0.00"), comment="预约费(元)")
    total_revenue = Column(Numeric(12, 2), default=Decimal("0.00"), comment="总营收(元)")
    paid_revenue = Column(Numeric(12, 2), default=Decimal("0.00"), comment="已收营收(元)")
    refund_amount = Column(Numeric(12, 2), default=Decimal("0.00"), comment="退款金额(元)")
    # 卡 9863018d: 唯一约束哨兵键。user_type 可 NULL (历史/无类型订单), PG unique
    # 视多个 NULL 为不同值不去重, 故落库前由 before_insert 事件把 user_type 映射
    # 为 user_type_key=COALESCE(user_type, ''), 约束建在非 NULL 列上。
    # station_id 虽建表 nullable=True, 但 ChargingOrder.station_id NOT NULL 且
    # build_revenue_daily 按 order.station_id 分组, 恒写非 NULL → 直接进唯一键。
    user_type_key = Column(String(50), nullable=False, default="", server_default="",
                           comment="用户类型哨兵键 (user_type, NULL='', 唯一约束载体)")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")

    __table_args__ = (
        # 卡 9863018d: 幂等键唯一约束 (record_date, station_id, user_type_key)
        UniqueConstraint("record_date", "station_id", "user_type_key", name="uq_rev_date_station_utype"),
        Index("idx_rev_date", "record_date"),
        Index("idx_rev_user_type", "user_type"),
        Index("idx_rev_station", "station_id"),
    )


@event.listens_for(RevenueDaily, "before_insert")
def _rd_sync_user_type_key(mapper, connection, target):
    """user_type → user_type_key 哨兵同步 (NULL=''), 保持唯一约束载体非 NULL。"""
    target.user_type_key = target.user_type if target.user_type is not None else ""


class StationDailyMetric(Base):
    """站点日运营指标表 - 单站点单日的运营关键指标"""
    __tablename__ = "station_daily_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    station_id = Column(Integer, nullable=False, index=True, comment="站点ID")
    record_date = Column(DateTime, nullable=False, index=True, comment="统计日期")
    active_users = Column(Integer, default=0, comment="活跃用户数")
    new_users = Column(Integer, default=0, comment="新增用户数")
    orders_count = Column(Integer, default=0, comment="订单数")
    energy_kwh = Column(Numeric(12, 2), default=Decimal("0.00"), comment="充电量(kWh)")
    revenue = Column(Numeric(12, 2), default=Decimal("0.00"), comment="营收(元)")
    utilization_rate = Column(Numeric(5, 2), default=Decimal("0.00"), comment="利用率(%)")
    avg_charge_duration = Column(Integer, default=0, comment="平均充电时长(分钟)")
    avg_wait_time = Column(Integer, default=0, comment="平均等待时长(分钟)")
    online_devices = Column(Integer, default=0, comment="在线设备数")
    idle_ratio = Column(Numeric(5, 2), default=Decimal("0.00"), comment="空闲率(%)")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")

    __table_args__ = (
        # 卡 9863018d: 幂等键唯一约束 (两列均 NOT NULL, 无 NULL 哨兵坑)
        UniqueConstraint("station_id", "record_date", name="uq_sdm_station_date"),
        Index("idx_sdm_station", "station_id"),
        Index("idx_sdm_date", "record_date"),
        Index("idx_sdm_station_date", "station_id", "record_date"),
    )
