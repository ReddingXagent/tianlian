"""父表删除外键级联服务（卡 ed537344）

背景：app/models 187 个 ForeignKey 仅 20 个带 ondelete。device/station 删除端点
此前直接 db.delete()，存在双形态缺陷：
- A（生产 PG，FK 强制）：alarms.device_id 等 NOT NULL 子引用使 ORM 在 flush 时
  先 UPDATE 子表置 NULL → 直接 IntegrityError 裸 500（已用独立引擎复现）；
- B（开发 SQLite，FK OFF）：删除成功但留下孤儿子行，诊断列表/定价查询/收藏
  解析等 join/引用路径数据腐化。

策略（同一事务、服务层显式处置，不动 alembic）：
- delete device：
  - 级联删除：device_qrcodes / device_configs / ai_diagnosis_records /
    maintenance_records / digital_twin_models / digital_twin_data_points /
    device_daily_stats（遥测/分析/健康等已由 ORM cascade 关系覆盖）
  - 置空引用：alarms.device_id 不可空 → 告警随设备删除；work_orders.device_id
    可空 → 置空保留历史工单
- delete station：
  - 先逐台处置站下 devices（复用 device 策略）
  - 级联删除：digital_twin_scenes / 计费定价5表 / 停车3表 / end_user_favorites /
    station_hourly_stats
  - 置空引用：work_orders / maintenance_records / on_call_rules /
    ai_diagnosis_records / energy 弱引用表的 station_id
"""
from __future__ import annotations

import logging

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# 卡 4e202c2b: purge_* 全文件原本零异常处理，DB 异常裸抛 500 泄漏 stmt/表名/
# 驱动报文。此处统一转译（rollback 后抛 HTTPException，detail 只含资源名）：
# - IntegrityError → 409（外键/唯一冲突，语义上多为并发关联写入）
# - OperationalError → 503（数据库暂不可用：锁/断连/超时）
# - 其余 → 500（通用文案，不泄漏内部细节）
# 原子性说明：purge_* 与随后的 db.delete/commit 同处调用方的一个事务，
# 中途无任何 commit —— 任一步失败即整体不落库，单事务已足够，
# 不需要额外 begin_nested savepoint（卡 4e202c2b 结论，经既有
# test_fk_delete_cascade*.py 双引擎全绿验证）。
_RESOURCE_NAMES: dict[str, str] = {}


def _purge_guard(resource: str):
    """装饰 purge_* 函数：统一 rollback + 异常转译（卡 4e202c2b）。"""

    def _wrap(fn):
        _RESOURCE_NAMES[fn.__name__] = resource

        def _call(db: Session, *args, **kwargs):
            try:
                return fn(db, *args, **kwargs)
            except HTTPException:
                db.rollback()
                raise
            except IntegrityError:
                db.rollback()
                logger.warning("级联处置%s失败: 完整性冲突", resource)
                raise HTTPException(
                    status_code=409,
                    detail=f"{resource}存在并发关联数据变更，删除冲突，请重试",
                )
            except OperationalError:
                db.rollback()
                logger.error("级联处置%s失败: 数据库暂不可用", resource)
                raise HTTPException(
                    status_code=503,
                    detail="数据库暂时不可用，请稍后重试",
                )
            except Exception:
                db.rollback()
                logger.exception("级联处置%s失败: 未预期异常", resource)
                raise HTTPException(
                    status_code=500,
                    detail=f"删除{resource}时发生内部错误",
                )

        _call.__name__ = fn.__name__
        return _call

    return _wrap

from app.models.ai_diagnosis import AIDiagnosisRecord
from app.models.alarm import Alarm
from app.models.device import Device
from app.models.device_config import DeviceConfig
from app.models.device_qrcode import DeviceQRCode
from app.models.device_efficiency_log import DeviceEfficiencyLog  # noqa: F401 (ORM 关系已覆盖, 注明)
from app.models.digital_twin import DigitalTwinDataPoint, DigitalTwinModel, DigitalTwinScene
from app.models.end_user_favorite import EndUserFavorite
from app.models.maintenance_record import MaintenanceRecord
from app.models.on_call import OnCallRule
from app.models.parking_discount_applied import ParkingDiscountApplied
from app.models.parking_event import OccupancyEvent
from app.models.parking_integration import ParkingIntegrationConfig
from app.models.pricing_v2 import (
    EnergyPrice,
    OccupancyFeePrice,
    ParkingPrice,
    ReservationFeePrice,
    ServiceFeePrice,
)
from app.models.pre_aggregation import DeviceDailyStats, StationHourlyStats
from app.models.workorder import (
    WorkOrder,
    WorkOrderCheckin,
    WorkOrderRating,
    WorkOrderSparePart,
    WorkOrderSupportRequest,
)


@_purge_guard("设备")
def purge_device_children(db: Session, device_id: int) -> None:
    """删除设备前处置全部子引用（同一事务内调用，调用方负责 commit）。"""
    # 级联删除：随设备消失的子行
    for model in (
        DeviceQRCode,
        DeviceConfig,
        AIDiagnosisRecord,
        MaintenanceRecord,
        DigitalTwinModel,
        DigitalTwinDataPoint,
        DeviceDailyStats,
    ):
        db.query(model).filter(model.device_id == device_id).delete(synchronize_session=False)

    # 告警 device_id NOT NULL：无法置空 → 随设备删除
    db.query(Alarm).filter(Alarm.device_id == device_id).delete(synchronize_session=False)

    # 历史工单保留：device_id 可空 → 置空
    db.query(WorkOrder).filter(WorkOrder.device_id == device_id).update(
        {WorkOrder.device_id: None}, synchronize_session=False
    )


@_purge_guard("站点")
def purge_station_children(db: Session, station_id: int) -> None:
    """删除站点前处置全部子引用（同一事务内调用，调用方负责 commit）。"""
    # 先处置站下设备（设备策略完整复用）
    device_ids = [
        row[0] for row in db.query(Device.id).filter(Device.station_id == station_id).all()
    ]
    for did in device_ids:
        purge_device_children(db, did)
    db.query(Device).filter(Device.station_id == station_id).delete(synchronize_session=False)

    # 级联删除：随站点消失的子行
    for model in (
        DigitalTwinScene,
        EnergyPrice,
        ServiceFeePrice,
        ParkingPrice,
        OccupancyFeePrice,
        ReservationFeePrice,
        OccupancyEvent,
        ParkingIntegrationConfig,
        ParkingDiscountApplied,
        EndUserFavorite,
        StationHourlyStats,
    ):
        db.query(model).filter(model.station_id == station_id).delete(synchronize_session=False)

    # 保留历史：station_id 可空 → 置空
    for model in (WorkOrder, MaintenanceRecord, OnCallRule, AIDiagnosisRecord):
        db.query(model).filter(model.station_id == station_id).update(
            {model.station_id: None}, synchronize_session=False
        )


# ────────────────────────────────────────────────────────────
# 以下为卡 21205721 维度X-2弹新增（workorder/team/tenant/user/enterprise）
# ────────────────────────────────────────────────────────────


@_purge_guard("工单")
def purge_workorder_children(db: Session, workorder_id: str) -> None:
    """删除工单前处置子引用（卡 21205721）。

    logs 已由 ORM cascade 关系覆盖；checkin/support/spare_part/rating 的
    order_id 均 NOT NULL → 随工单级联删除；alarm.workorder_id 可空 → 置空
    保留告警历史。
    """
    for model in (WorkOrderCheckin, WorkOrderSupportRequest, WorkOrderSparePart,
                  WorkOrderRating):
        db.query(model).filter(model.order_id == workorder_id).delete(
            synchronize_session=False
        )
    db.query(Alarm).filter(Alarm.workorder_id == workorder_id).update(
        {Alarm.workorder_id: None}, synchronize_session=False
    )


@_purge_guard("团队")
def purge_team_children(db: Session, team_id: int) -> None:
    """删除团队前处置子引用（卡 21205721）。

    - 级联删除（team_id NOT NULL / 强归属）：on_call_rules、agent_memory、
      agent_conversation、station_maintenance_grants（列声明 ondelete=CASCADE
      但 SQLite 不建约束，服务层兜底）
    - 置空保留（可空弱引用）：users.team_id、stations.team_id、
      enterprises.owner_team_id、energy_strategy 4表、channel_config、
      notification、notification_config、inspection_plans、merchant、
      platform_fee_config、system_config、invoice_request、tenant_brand
      （NotificationLog 无 team_id 列，天然无引用，勿加）
    - on_call_rules 级联前先清 on_call_shifts/on_call_logs（其 FK 指向 rules
      且 shifts.user_id NOT NULL 无法对团队置空）
    """
    from app.models.agent_memory import AgentConversation, AgentMemory
    from app.models.channel_config import ChannelConfig
    from app.models.energy_strategy import (
        EnergyDispatchPlan,
        EnergyFlowLog,
        EnergyPriceSpot,
        EnergyPriceTemplate,
        StationEnergyStrategy,
    )
    from app.models.enterprise import Enterprise
    from app.models.invoice_request import InvoiceRequest
    from app.models.merchant import Merchant
    from app.models.notification import Notification
    from app.models.inspection import InspectionPlan
    from app.models.notification_config import NotificationConfig
    from app.models.on_call import OnCallLog, OnCallRule, OnCallShift
    from app.models.platform_fee_config import PlatformFeeConfig
    from app.models.station import Station
    from app.models.station_maintenance_grant import StationMaintenanceGrant
    from app.models.system_config import SystemConfig
    from app.models.tenant_brand import TenantBrand
    from app.models.user import Team, User

    # on_call 链：logs → shifts → rules（shifts/logs 的 user FK 指向团队成员，
    # 团队删除时随规则一并消失）
    rule_ids = [
        row[0] for row in db.query(OnCallRule.id).filter(
            OnCallRule.team_id == team_id).all()
    ]
    if rule_ids:
        shift_ids = [
            row[0] for row in db.query(OnCallShift.id).filter(
                OnCallShift.rule_id.in_(rule_ids)).all()
        ]
        if shift_ids:
            db.query(OnCallLog).filter(OnCallLog.shift_id.in_(shift_ids)).delete(
                synchronize_session=False
            )
        db.query(OnCallShift).filter(OnCallShift.rule_id.in_(rule_ids)).delete(
            synchronize_session=False
        )
    db.query(OnCallRule).filter(OnCallRule.team_id == team_id).delete(
        synchronize_session=False
    )

    # 级联删除：团队强归属数据
    for model in (AgentMemory, AgentConversation, StationEnergyStrategy):
        db.query(model).filter(model.team_id == team_id).delete(
            synchronize_session=False
        )
    db.query(StationMaintenanceGrant).filter(
        (StationMaintenanceGrant.maintenance_team_id == team_id)
        | (StationMaintenanceGrant.granted_by_team_id == team_id)
    ).delete(synchronize_session=False)
    # energy_price_periods.template_id → templates.team_id 可空置空，但其
    # 行随模板保留即可；此处只置空 team 弱引用
    db.query(EnergyPriceTemplate).filter(
        EnergyPriceTemplate.team_id == team_id
    ).update({EnergyPriceTemplate.team_id: None}, synchronize_session=False)

    # 置空保留：可空弱引用（含 inspection_plans.team_id, 列声明 SET NULL 但
    # SQLite 不建约束，服务层兜底；Enterprise 列名为 owner_team_id）
    for model in (User, Station, EnergyPriceSpot,
                  EnergyDispatchPlan, EnergyFlowLog, ChannelConfig, Notification,
                  NotificationConfig, InspectionPlan, Merchant,
                  PlatformFeeConfig, SystemConfig, InvoiceRequest, TenantBrand):
        db.query(model).filter(model.team_id == team_id).update(
            {model.team_id: None}, synchronize_session=False
        )
    db.query(Enterprise).filter(Enterprise.owner_team_id == team_id).update(
        {Enterprise.owner_team_id: None}, synchronize_session=False
    )
    db.query(Team).filter(Team.parent_team_id == team_id).update(
        {Team.parent_team_id: None}, synchronize_session=False
    )


@_purge_guard("租户")
def purge_tenant_children(db: Session, tenant_id: int) -> None:
    """删除租户前处置子引用（卡 21205721）。

    - 级联删除（tenant_id NOT NULL）：tenant_configs、tenant_audit_logs、
      tenant_usage、tenant_brand
    - 置空保留（可空弱引用）：stations、vehicles、api_keys、
      client_certificates、merchants、platform_fee_config
    """
    from app.models.api_key import ApiKey, ClientCertificate
    from app.models.merchant import Merchant
    from app.models.platform_fee_config import PlatformFeeConfig
    from app.models.station import Station
    from app.models.tenant import TenantAuditLog, TenantConfig
    from app.models.tenant_brand import TenantBrand
    from app.models.tenant_usage import TenantUsage
    from app.models.vehicle import Vehicle

    for model in (TenantConfig, TenantAuditLog, TenantUsage, TenantBrand):
        db.query(model).filter(model.tenant_id == tenant_id).delete(
            synchronize_session=False
        )
    for model in (Station, Vehicle, ApiKey, ClientCertificate, Merchant,
                  PlatformFeeConfig):
        db.query(model).filter(model.tenant_id == tenant_id).update(
            {model.tenant_id: None}, synchronize_session=False
        )


@_purge_guard("用户")
def purge_user_children(db: Session, user_id: int) -> None:
    """删除用户前处置引用（卡 21205721，24 处 reverse FK）。

    - 级联删除：api_keys（凭证, usage_logs 由 ORM cascade 覆盖）、
      on_call_shifts / on_call_logs（user_id NOT NULL）
    - 置空保留（历史记录）：工单 9 FK（assignee/creator/verifier + log/checkin/
      support/spare_part/rating 的 user_id）、maintenance_records.engineer_id、
      alarms.handler_id、stations.operator_id、vehicles.driver_id、
      knowledge author×2、api_gateway 4 处、tenant_audit_logs.user_id、
      agent_conversation.user_id、teams.leader_id（自引用, 队长指向用户）
    """
    from app.models.agent_memory import AgentConversation
    from app.models.alarm import Alarm
    from app.models.api_gateway import (
        ApiClient,
        ApiEndpoint,
        GatewayApiKey,
        OAuthAuthorizationCode,
        RateLimitRule,
        ThirdPartyIntegration,
    )
    from app.models.api_key import ApiKey
    from app.models.knowledge import KnowledgeArticle, KnowledgeFAQ
    from app.models.maintenance_record import MaintenanceRecord
    from app.models.on_call import OnCallLog, OnCallShift
    from app.models.station import Station
    from app.models.tenant import TenantAuditLog
    from app.models.user import Team, User
    from app.models.vehicle import Vehicle
    from app.models.workorder import (
        WorkOrder,
        WorkOrderCheckin,
        WorkOrderLog,
        WorkOrderRating,
        WorkOrderSparePart,
        WorkOrderSupportRequest,
    )

    # 凭证级联：api_keys（含 usage_logs ORM cascade）
    db.query(ApiKey).filter(ApiKey.user_id == user_id).delete(
        synchronize_session=False
    )
    # 值班班次/日志（user_id NOT NULL）随用户删除；logs.shift_id 指向 shifts
    # 且无 ondelete → 先删挂在目标 shifts 上的 logs 再删 shifts
    shift_ids = [
        row[0] for row in db.query(OnCallShift.id).filter(
            OnCallShift.user_id == user_id).all()
    ]
    if shift_ids:
        db.query(OnCallLog).filter(OnCallLog.shift_id.in_(shift_ids)).delete(
            synchronize_session=False
        )
        db.query(OnCallShift).filter(
            OnCallShift.id.in_(shift_ids)
        ).delete(synchronize_session=False)
    db.query(OnCallLog).filter(OnCallLog.user_id == user_id).delete(
        synchronize_session=False
    )

    # 置空保留：全部可空历史引用（28 处 reverse FK 中非级联的 22 处，
    # 逐列显式声明，列名非 user_id 的用别名清单，防 hasattr 静默漏判）
    nullable_refs = (
        (WorkOrder, "assignee_id"), (WorkOrder, "creator_id"),
        (WorkOrder, "verifier_id"),
        (WorkOrderLog, "user_id"), (WorkOrderCheckin, "user_id"),
        (WorkOrderSupportRequest, "user_id"),
        (WorkOrderSupportRequest, "target_engineer_id"),
        (WorkOrderSparePart, "user_id"), (WorkOrderRating, "user_id"),
        (WorkOrderRating, "verifier_id"),
        (MaintenanceRecord, "engineer_id"), (Alarm, "handler_id"),
        (Station, "operator_id"), (Vehicle, "driver_id"),
        (KnowledgeArticle, "author_id"), (KnowledgeFAQ, "author_id"),
        (ApiClient, "created_by"), (GatewayApiKey, "created_by"),
        (ApiEndpoint, "registered_by"), (RateLimitRule, "created_by"),
        (ThirdPartyIntegration, "created_by"),
        (OAuthAuthorizationCode, "user_id"),
        (TenantAuditLog, "user_id"), (AgentConversation, "user_id"),
        (Team, "leader_id"),
    )
    for model, col in nullable_refs:
        db.query(model).filter(getattr(model, col) == user_id).update(
            {getattr(model, col): None}, synchronize_session=False
        )
    # on_call_shifts.backup_user_id 可空 → 置空（shift 本身可能因值班人而删,
    # 但该用户作为备份的他人班次保留）
    db.query(OnCallShift).filter(
        OnCallShift.backup_user_id == user_id
    ).update({OnCallShift.backup_user_id: None}, synchronize_session=False)


@_purge_guard("企业车辆")
def purge_enterprise_vehicle_children(db: Session, vehicle_id: int) -> None:
    """删除/解绑企业车辆前处置子引用（卡 54dc3406，单车辆路径）。

    purge_enterprise_children 已处理企业级整删（按 veh_ids 批量），但
    unbind_vehicle 单车解绑此前裸 db.delete：
    - 生产 PG（FK 强制）：FleetV2GPlan/FleetV2GRevenue/
      FleetVehicleMaintenance/FleetVehicleInsurance 的 vehicle_id NOT NULL
      → flush 置 NULL → IntegrityError 裸 500
    - 开发 SQLite（FK OFF）：留孤儿子行污染 join/引用路径

    - 级联删除（vehicle_id NOT NULL）：v2g 计划/收益、维保、保险
    - 置空保留（可空弱引用）：FleetDriver.assigned_vehicle_id、
      FleetAlertRecord.vehicle_id（FleetAlertRule 表本身无 vehicle_id 列，
      车辆维度挂 record 上）、EnterpriseTransaction.vehicle_id
    """
    from app.models.enterprise_transaction import EnterpriseTransaction
    from app.models.fleet_alert_rule import FleetAlertRecord
    from app.models.fleet_driver import FleetDriver
    from app.models.fleet_v2g import FleetV2GPlan, FleetV2GRevenue
    from app.models.fleet_vehicle_profile import (
        FleetVehicleInsurance,
        FleetVehicleMaintenance,
    )

    for model in (FleetV2GPlan, FleetV2GRevenue,
                  FleetVehicleMaintenance, FleetVehicleInsurance):
        db.query(model).filter(model.vehicle_id == vehicle_id).delete(
            synchronize_session=False
        )

    db.query(FleetDriver).filter(
        FleetDriver.assigned_vehicle_id == vehicle_id
    ).update({FleetDriver.assigned_vehicle_id: None}, synchronize_session=False)
    db.query(FleetAlertRecord).filter(
        FleetAlertRecord.vehicle_id == vehicle_id
    ).update({FleetAlertRecord.vehicle_id: None}, synchronize_session=False)
    db.query(EnterpriseTransaction).filter(
        EnterpriseTransaction.vehicle_id == vehicle_id
    ).update({EnterpriseTransaction.vehicle_id: None}, synchronize_session=False)


@_purge_guard("司机")
def purge_driver_children(db: Session, driver_id: int) -> None:
    """删除司机前处置子引用（卡 97a891bc 同族）：
    - 考勤 FleetDriverAttendance.driver_id NOT NULL 且无 ondelete，需显式删除。
    - 账户 fleet_driver_accounts/流水 fleet_driver_transactions 由 ORM
      relationship cascade="all, delete-orphan" 覆盖（delete_driver 单删路径），
      此处不重复处理；账本完整性守卫在调用方（非零余额/有流水拒删）已兜底。
    """
    from app.models.fleet_driver_attendance import FleetDriverAttendance
    db.query(FleetDriverAttendance).filter(
        FleetDriverAttendance.driver_id == driver_id
    ).delete(synchronize_session=False)


def enterprise_has_ledger_data(db: Session, ent) -> bool:
    """企业是否持有账本类数据（卡 21205721：账本完整性优先，有则禁删）。

    覆盖：非零余额/信用额度、交易流水、充值申请、结算账单、开票申请、
    资金账户（fund_pools）、碳核证/交易记录。
    """
    from app.models.enterprise_recharge import RechargeApplication
    from app.models.enterprise_transaction import EnterpriseTransaction
    from app.models.fleet_carbon_certificate import FleetCarbonCertificate
    from app.models.fund_pool import FundPool
    from app.models.settlement.bill import FleetSettlementBill
    from app.models.settlement.invoice import FleetInvoiceRequest

    if (ent.balance or 0) != 0 or (ent.credit_limit or 0) != 0:
        return True
    checks = (
        EnterpriseTransaction.enterprise_id,
        RechargeApplication.enterprise_id,
        FleetSettlementBill.enterprise_id,
        FleetInvoiceRequest.enterprise_id,
        FleetCarbonCertificate.enterprise_id,
        FundPool.enterprise_id,
    )
    for col in checks:
        if db.query(db.query(col).filter(col == ent.id).exists()).scalar():
            return True
    return False


@_purge_guard("企业")
def purge_enterprise_children(db: Session, enterprise_id: int) -> None:
    """删除企业前处置子引用（卡 21205721，仅无账本数据时被调用）。

    - 级联删除（enterprise_id NOT NULL 配置/资产类）：fleet_charging_policy、
      fleet_alert_rules/records、station_vin_whitelist、enterprise_vehicles
      （连带 v2g 计划/收益，vehicle_id NOT NULL）、fleet_drivers（账户/流水
      ORM cascade）、enterprise_device_grants、企业-场站绑定表；碳核证/账本
      类不在此处——有则已被 409 守卫拦下
    - 弱引用：fund_pools.enterprise_id 可空 → 置空（正常不会走到，防御兜底）
    """
    from app.models.enterprise import enterprise_stations
    from app.models.enterprise_device_grant import EnterpriseDeviceGrant
    from app.models.enterprise_vehicle import EnterpriseVehicle, StationVinWhitelist
    from app.models.fleet_alert_rule import FleetAlertRecord, FleetAlertRule
    from app.models.fleet_charging_policy import FleetChargingPolicy
    from app.models.fleet_driver import FleetDriver
    from app.models.fleet_v2g import FleetV2GPlan, FleetV2GRevenue
    from app.models.fleet_vehicle_profile import (
        FleetVehicleInsurance,
        FleetVehicleMaintenance,
    )
    from app.models.fund_pool import FundPool

    veh_ids = [
        row[0] for row in db.query(EnterpriseVehicle.id).filter(
            EnterpriseVehicle.enterprise_id == enterprise_id).all()
    ]
    if veh_ids:
        for model in (FleetV2GPlan, FleetV2GRevenue,
                      FleetVehicleMaintenance, FleetVehicleInsurance):
            db.query(model).filter(model.vehicle_id.in_(veh_ids)).delete(
                synchronize_session=False
            )
        db.query(EnterpriseVehicle).filter(
            EnterpriseVehicle.id.in_(veh_ids)
        ).delete(synchronize_session=False)

    # 司机考勤 driver_id NOT NULL 且无 ondelete，bulk delete 不触发 ORM
    # cascade → 先批量清理（卡 97a891bc 同族）
    driver_ids = [
        row[0] for row in db.query(FleetDriver.id).filter(
            FleetDriver.enterprise_id == enterprise_id).all()
    ]
    if driver_ids:
        from app.models.fleet_driver_attendance import FleetDriverAttendance
        db.query(FleetDriverAttendance).filter(
            FleetDriverAttendance.driver_id.in_(driver_ids)
        ).delete(synchronize_session=False)

    for model in (FleetChargingPolicy, FleetAlertRule, FleetAlertRecord,
                  FleetDriver, EnterpriseDeviceGrant, StationVinWhitelist):
        db.query(model).filter(model.enterprise_id == enterprise_id).delete(
            synchronize_session=False
        )
    db.execute(
        enterprise_stations.delete().where(
            enterprise_stations.c.enterprise_id == enterprise_id
        )
    )
    db.query(FundPool).filter(FundPool.enterprise_id == enterprise_id).update(
        {FundPool.enterprise_id: None}, synchronize_session=False
    )
