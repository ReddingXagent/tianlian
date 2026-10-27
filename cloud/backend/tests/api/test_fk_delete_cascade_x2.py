"""FK 删除级联补全（卡 21205721 维度X-2弹）

work-orders / teams / tenants / users / enterprises 5 端点延续 X-1 弹
（卡 ed537344, bc2c2cb4f）的双引擎测试模式：
- A 类：FK-ON 独立引擎下父删除不得裸 500（复现生产 PG 约束）；
- B 类：默认 sqlite（FK OFF）引擎下服务层级联不留孤儿。

处置原则与 fk_cascade.py 一致：NOT NULL 子表 → 级联删；可空历史引用 →
置空保留；交易/流水/账本类绝不级联删 —— enterprises 端点存在账本数据
（交易/充值/账单/开票/资金账户/余额非零）时直接 409 拒绝删除。
"""
import datetime
import uuid as _uuid

import pytest

from tests.api.test_fk_delete_cascade import fk_env  # noqa: F401 复用 FK-ON 环境


def _u():
    return _uuid.uuid4().hex[:8]


# ────────────────────────────────────────────────────────────
# 1. DELETE /api/v1/work-orders/{id}
# ────────────────────────────────────────────────────────────

def _seed_workorder_with_children(s):
    from app.models.station import Station, StationStatus
    from app.models.device import Device, DeviceType, DeviceStatus
    from app.models.workorder import (
        WorkOrder, WorkOrderCheckin, WorkOrderSupportRequest,
        WorkOrderSparePart, WorkOrderRating,
    )
    from app.models.alarm import Alarm, AlarmLevel, AlarmStatus

    st = Station(name="工单站", code=f"WO{_u().upper()}", status=StationStatus.NORMAL)
    s.add(st); s.commit(); s.refresh(st)
    dev = Device(sn=f"SN-WO-{_u()}", name="工单桩", code=f"WO{_u().upper()}",
                 type=DeviceType.CHARGER_DC, status=DeviceStatus.ONLINE,
                 station_id=st.id)
    s.add(dev); s.commit(); s.refresh(dev)
    wo = WorkOrder(id=f"WO-FKX2-{_u()}", station_id=st.id)
    s.add(wo); s.commit(); s.refresh(wo)
    s.add(WorkOrderCheckin(order_id=wo.id, latitude=1.0, longitude=1.0))
    s.add(WorkOrderSupportRequest(order_id=wo.id, reason="需要支援"))
    s.add(WorkOrderSparePart(order_id=wo.id, part_name="枪线"))
    s.add(WorkOrderRating(order_id=wo.id, response_rating=5, quality_rating=5,
                          attitude_rating=5))
    s.add(Alarm(device_id=dev.id, station_id=st.id, level=AlarmLevel.WARNING,
                status=AlarmStatus.ACTIVE, workorder_id=wo.id))
    s.commit()
    return wo


class TestDeleteWorkOrder:
    def test_fkon_no_500_children_disposed(self, fk_env):
        from app.models.workorder import (
            WorkOrderCheckin, WorkOrderSupportRequest, WorkOrderSparePart,
            WorkOrderRating,
        )
        from app.models.alarm import Alarm

        s = fk_env._fk_session()
        wo = _seed_workorder_with_children(s)

        resp = fk_env.delete(f"/api/v1/work-orders/{wo.id}")
        assert resp.status_code != 500, f"裸500: {resp.status_code} {resp.text[:300]}"
        assert resp.status_code == 200, resp.text

        # 4 子表 order_id NOT NULL → 级联删除
        assert s.query(WorkOrderCheckin).count() == 0
        assert s.query(WorkOrderSupportRequest).count() == 0
        assert s.query(WorkOrderSparePart).count() == 0
        assert s.query(WorkOrderRating).count() == 0
        # 告警 workorder_id 可空 → 保留置空
        assert s.query(Alarm).one().workorder_id is None

    def test_sqlite_no_orphans(self, client):
        from app.models.workorder import (
            WorkOrderCheckin, WorkOrderSparePart, WorkOrderRating,
        )
        from app.models.alarm import Alarm, AlarmLevel, AlarmStatus

        s = client._sesh
        wo = _seed_workorder_with_children(s)

        resp = client.delete(f"/api/v1/work-orders/{wo.id}")
        assert resp.status_code == 200, resp.text
        s.expire_all()
        assert s.query(WorkOrderCheckin).count() == 0
        assert s.query(WorkOrderSparePart).count() == 0
        assert s.query(WorkOrderRating).count() == 0
        assert s.query(Alarm).one().workorder_id is None


# ────────────────────────────────────────────────────────────
# 2. DELETE /api/v1/teams/{id}
# ────────────────────────────────────────────────────────────

def _seed_team_with_children(s):
    from app.models.user import Team, User, UserRole
    from app.models.station import Station, StationStatus
    from app.models.enterprise import Enterprise, EnterpriseStatus
    from app.models.on_call import OnCallRule
    from app.models.agent_memory import AgentMemory, AgentConversation
    from app.models.station_maintenance_grant import (
        StationMaintenanceGrant, GrantScope,
    )
    from decimal import Decimal
    from app.models.energy_strategy import (
        EnergyPriceTemplate, EnergyPriceSpot,
    )
    from app.models.channel_config import ChannelConfig
    from app.models.notification import Notification
    from app.models.merchant import Merchant, MerchantType
    from app.models.platform_fee_config import PlatformFeeConfig
    from app.models.system_config import SystemConfig
    from app.models.notification_config import NotificationConfig
    from app.models.invoice_request import (
        InvoiceRequest, InvoiceTitleType,
    )
    from app.models.tenant_brand import TenantBrand
    from app.models.tenant import Tenant
    from app.models.inspection import InspectionPlan, PlanCycle

    team = Team(name=f"团队X2{_u()}", code=f"T{_u().upper()}")
    s.add(team); s.commit(); s.refresh(team)

    user = User(username=f"u{_u()}", password_hash="x", role=UserRole.ENGINEER,
                status="active", team_id=team.id)
    st = Station(name="团队站", code=f"TS{_u().upper()}",
                 status=StationStatus.NORMAL, team_id=team.id)
    ent = Enterprise(name=f"企{_u()}", code=f"E{_u().upper()}",
                     status=EnterpriseStatus.ACTIVE, owner_team_id=team.id)
    s.add_all([user, st, ent]); s.commit(); s.refresh(user); s.refresh(st); s.refresh(ent)

    # NOT NULL 级联组
    s.add(OnCallRule(name="轮值", team_id=team.id, rotation_order=[user.id]))
    s.add(AgentMemory(team_id=team.id, board="maintenance",
                      category="finding", title="t", content="c"))
    s.add(AgentConversation(team_id=team.id, board="maintenance", role="user",
                            content="hi"))
    s.add(StationMaintenanceGrant(station_id=st.id, maintenance_team_id=team.id,
                                  granted_by_team_id=team.id, scope=GrantScope.FULL))

    # 可空弱引用置空组
    tpl = EnergyPriceTemplate(province="湖南", version=1,
                              effective_from=datetime.date(2026, 1, 1))
    s.add(tpl); s.commit(); s.refresh(tpl)
    s.add(EnergyPriceSpot(team_id=team.id, price_date=datetime.date(2026, 8, 27), node_index=1))
    s.add(ChannelConfig(team_id=team.id, channel="im", config={}))
    s.add(Notification(team_id=team.id, title="t", recipient_id="r1"))
    tenant = Tenant(name=f"租户{_u()}", code=f"TN{_u().upper()}")
    s.add(tenant); s.commit(); s.refresh(tenant)
    s.add(Merchant(business_code=f"APL_{_u()}", merchant_type=MerchantType.ENTERPRISE,
                   merchant_name=f"商户{_u()}", team_id=team.id, tenant_id=tenant.id))
    s.add(PlatformFeeConfig(team_id=team.id, tenant_id=tenant.id))
    s.add(SystemConfig(config_key=f"sys{_u()}", config_value={"v": 1}, team_id=team.id))
    s.add(NotificationConfig(name="通知配置", team_id=team.id))
    s.add(InvoiceRequest(order_ids="[]", title_type=InvoiceTitleType.PERSONAL,
                         title_name=f"抬头{_u()}", team_id=team.id))
    s.add(TenantBrand(team_id=team.id, tenant_id=tenant.id, operator_name="op"))
    s.add(InspectionPlan(name=f"巡检计划{_u()}", cycle=PlanCycle.WEEKLY,
                         team_id=team.id))
    s.commit()
    return team, user, st, ent


class TestDeleteTeam:
    def test_fkon_no_500_children_disposed(self, fk_env):
        from app.models.user import User, Team
        from app.models.station import Station
        from app.models.enterprise import Enterprise
        from app.models.on_call import OnCallRule
        from app.models.agent_memory import AgentMemory, AgentConversation
        from app.models.station_maintenance_grant import StationMaintenanceGrant
        from app.models.energy_strategy import EnergyPriceSpot
        from app.models.channel_config import ChannelConfig
        from app.models.notification import Notification
        from app.models.inspection import InspectionPlan

        s = fk_env._fk_session()
        team, user, st, ent = _seed_team_with_children(s)

        resp = fk_env.delete(f"/api/v1/teams/{team.id}")
        assert resp.status_code != 500, f"裸500: {resp.status_code} {resp.text[:300]}"
        assert resp.status_code == 200, resp.text

        # seeding session 持 identity map 旧值 → 换新 session 断言
        s.close()
        s = fk_env._fk_session()

        # NOT NULL 级联组清零
        assert s.query(OnCallRule).count() == 0
        assert s.query(AgentMemory).count() == 0
        assert s.query(AgentConversation).count() == 0
        assert s.query(StationMaintenanceGrant).filter(
            StationMaintenanceGrant.maintenance_team_id == team.id).count() == 0
        assert s.query(StationMaintenanceGrant).filter(
            StationMaintenanceGrant.granted_by_team_id == team.id).count() == 0
        # 可空弱引用置空，历史保留
        assert s.query(User).filter(User.id == user.id).one().team_id is None
        assert s.query(Station).filter(Station.id == st.id).one().team_id is None
        assert s.query(Enterprise).filter(Enterprise.id == ent.id).one().owner_team_id is None
        assert s.query(EnergyPriceSpot).one().team_id is None
        assert s.query(ChannelConfig).one().team_id is None
        assert s.query(Notification).one().team_id is None
        assert s.query(InspectionPlan).one().team_id is None
        assert s.query(Team).filter(Team.id == team.id).count() == 0

    def test_sqlite_no_orphans(self, client):
        from app.models.on_call import OnCallRule
        from app.models.agent_memory import AgentMemory
        from app.models.user import User

        s = client._sesh
        team, user, st, ent = _seed_team_with_children(s)

        resp = client.delete(f"/api/v1/teams/{team.id}")
        assert resp.status_code == 200, resp.text
        s.expire_all()
        assert s.query(OnCallRule).count() == 0
        assert s.query(AgentMemory).count() == 0
        assert s.query(User).filter(User.id == user.id).one().team_id is None


# ────────────────────────────────────────────────────────────
# 3. DELETE /api/v1/tenants/{id}
# ────────────────────────────────────────────────────────────

def _seed_tenant_with_children(s):
    from app.models.tenant import Tenant, TenantConfig, TenantAuditLog
    from app.models.tenant_usage import TenantUsage
    from app.models.tenant_brand import TenantBrand
    from app.models.station import Station, StationStatus
    from app.models.vehicle import Vehicle
    from app.models.api_key import ApiKey, ClientCertificate
    from app.models.merchant import Merchant, MerchantType

    t = Tenant(name=f"租户X2{_u()}", code=f"TN{_u().upper()}")
    s.add(t); s.commit(); s.refresh(t)

    st = Station(name="租户站", code=f"NT{_u().upper()}",
                 status=StationStatus.NORMAL, tenant_id=t.id)
    s.add(st); s.commit(); s.refresh(st)

    # NOT NULL 级联组
    s.add(TenantConfig(tenant_id=t.id, config_key="theme", config_value="dark"))
    s.add(TenantAuditLog(tenant_id=t.id, action="create", resource_type="tenant"))
    s.add(TenantUsage(tenant_id=t.id, record_date=datetime.date(2026, 8, 27)))
    s.add(TenantBrand(tenant_id=t.id, operator_name="op"))

    # 可空置空组
    s.add(Vehicle(plate_number=f"沪B{_u()[:5]}", vin=f"VINT{_u()}{_u()}", tenant_id=t.id))
    s.add(ApiKey(name=f"ak{_u()}", key_hash="h" * 32, key_prefix="h", tenant_id=t.id))
    s.add(ClientCertificate(
        cert_serial=f"s{_u()}", cert_fingerprint=f"f{_u()}",
        cert_subject="subj", cert_issuer="iss", cert_pem="pem", name="cc",
        valid_from=datetime.datetime(2026, 1, 1),
        valid_until=datetime.datetime(2027, 1, 1), tenant_id=t.id))
    s.add(Merchant(business_code=f"APL{_u()}", merchant_type=MerchantType.ENTERPRISE, merchant_name=f"商户{_u()}", tenant_id=t.id))
    s.commit()
    return t, st


class TestDeleteTenant:
    def test_fkon_no_500_children_disposed(self, fk_env):
        from app.models.tenant import TenantAuditLog, TenantConfig
        from app.models.tenant_usage import TenantUsage
        from app.models.tenant_brand import TenantBrand
        from app.models.station import Station
        from app.models.vehicle import Vehicle
        from app.models.api_key import ApiKey, ClientCertificate
        from app.models.merchant import Merchant

        s = fk_env._fk_session()
        t, st = _seed_tenant_with_children(s)

        resp = fk_env.delete(f"/api/v1/tenants/{t.id}")
        assert resp.status_code != 500, f"裸500: {resp.status_code} {resp.text[:300]}"
        assert resp.status_code == 200, resp.text

        # seeding session 持 identity map 旧值 → 换新 session 断言
        s.close()
        s = fk_env._fk_session()

        # NOT NULL 级联组清零
        assert s.query(TenantConfig).count() == 0
        assert s.query(TenantAuditLog).count() == 0
        assert s.query(TenantUsage).count() == 0
        assert s.query(TenantBrand).count() == 0
        # 可空弱引用置空，历史保留
        assert s.query(Station).filter(Station.id == st.id).one().tenant_id is None
        assert s.query(Vehicle).one().tenant_id is None
        assert s.query(ApiKey).one().tenant_id is None
        assert s.query(ClientCertificate).one().tenant_id is None
        assert s.query(Merchant).one().tenant_id is None

    def test_sqlite_no_orphans(self, client):
        from app.models.tenant import TenantConfig
        from app.models.tenant_usage import TenantUsage
        from app.models.station import Station

        s = client._sesh
        t, st = _seed_tenant_with_children(s)

        resp = client.delete(f"/api/v1/tenants/{t.id}")
        assert resp.status_code == 200, resp.text
        s.expire_all()
        assert s.query(TenantConfig).count() == 0
        assert s.query(TenantUsage).count() == 0
        assert s.query(Station).filter(Station.id == st.id).one().tenant_id is None


# ────────────────────────────────────────────────────────────
# 4. DELETE /api/v1/users/{id}
# ────────────────────────────────────────────────────────────

def _seed_user_with_refs(s):
    from app.models.user import User, UserRole, Team
    from app.models.workorder import (
        WorkOrder, WorkOrderLog, WorkOrderCheckin, WorkOrderSupportRequest,
        WorkOrderSparePart, WorkOrderRating,
    )
    from app.models.maintenance_record import MaintenanceRecord
    from app.models.alarm import Alarm, AlarmLevel, AlarmStatus
    from app.models.station import Station, StationStatus
    from app.models.vehicle import Vehicle
    from app.models.api_key import ApiKey
    from app.models.knowledge import KnowledgeArticle, KnowledgeCategory, KnowledgeFAQ
    from app.models.on_call import OnCallRule, OnCallShift, OnCallLog
    from app.models.api_gateway import (
        ApiClient, OAuthAuthorizationCode, RateLimitRule, ThirdPartyIntegration,
    )
    from app.models.tenant import Tenant, TenantAuditLog
    from app.models.agent_memory import AgentConversation
    from app.models.user import Team as _Team

    team = _Team(name=f"用户团{_u()}", code=f"U{_u().upper()}")
    s.add(team); s.commit(); s.refresh(team)

    u = User(username=f"usr{_u()}", password_hash="x", role=UserRole.ENGINEER,
             status="active", team_id=team.id)
    s.add(u); s.commit(); s.refresh(u)
    # Team.leader_id 指向被删用户（自引用组用户→团队）
    team.leader_id = u.id
    sub_team = Team(name=f"子团{_u()}", code=f"S{_u().upper()}", parent_team_id=team.id)
    s.add(sub_team)

    st = Station(name="用户站", code=f"US{_u().upper()}", status=StationStatus.NORMAL)
    s.add(st); s.commit(); s.refresh(st)
    from app.models.device import Device, DeviceType, DeviceStatus
    dev = Device(sn=f"SN-U-{_u()}", name="用户桩", code=f"UD{_u().upper()}",
                 type=DeviceType.CHARGER_DC, status=DeviceStatus.ONLINE,
                 station_id=st.id)
    s.add(dev); s.commit(); s.refresh(dev)
    mr = MaintenanceRecord(device_id=dev.id, title="维保", engineer_id=u.id)
    s.add(mr)
    s.add(Alarm(device_id=dev.id, station_id=st.id, level=AlarmLevel.WARNING,
                status=AlarmStatus.ACTIVE, handler_id=u.id))
    s.add(Station(name="运营站", code=f"OP{_u().upper()}",
                  status=StationStatus.NORMAL, operator_id=u.id))
    s.add(Vehicle(plate_number=f"沪C{_u()[:5]}", vin=f"VINU{_u()}{_u()}", driver_id=u.id))

    wo = WorkOrder(id=f"WO-U-{_u()}", station_id=st.id, assignee_id=u.id,
                   creator_id=u.id, verifier_id=u.id)
    s.add(wo); s.commit(); s.refresh(wo)
    s.add(WorkOrderLog(order_id=wo.id, user_id=u.id))
    s.add(WorkOrderCheckin(order_id=wo.id, user_id=u.id))
    s.add(WorkOrderSupportRequest(order_id=wo.id, reason="r", user_id=u.id,
                                  target_engineer_id=u.id))
    s.add(WorkOrderSparePart(order_id=wo.id, part_name="p", user_id=u.id))
    s.add(WorkOrderRating(order_id=wo.id, response_rating=5, quality_rating=5,
                          attitude_rating=5, user_id=u.id, verifier_id=u.id))

    s.add(ApiKey(name=f"ak{_u()}", key_hash="h" * 32, key_prefix="h", user_id=u.id))
    cat = KnowledgeCategory(name=f"cat{_u()}")
    s.add(cat); s.commit(); s.refresh(cat)
    s.add(KnowledgeArticle(title="t", category_id=cat.id, content="c", author_id=u.id))
    s.add(KnowledgeFAQ(question="q", answer="a", author_id=u.id))

    rule = OnCallRule(name="轮值", team_id=team.id, rotation_order=[u.id])
    s.add(rule); s.commit(); s.refresh(rule)
    shift = OnCallShift(rule_id=rule.id, user_id=u.id,
                        start_time=datetime.datetime(2026, 8, 27, 9, 0),
                        end_time=datetime.datetime(2026, 8, 27, 18, 0))
    s.add(shift); s.commit(); s.refresh(shift)
    s.add(OnCallLog(shift_id=shift.id, user_id=u.id, content="交接"))

    cli = ApiClient(client_id=f"cid{_u()}", client_secret_hash="h" * 16, name="c",
                    created_by=u.id)
    s.add(cli); s.commit(); s.refresh(cli)
    from app.models.api_gateway import GatewayApiKey
    s.add(GatewayApiKey(key_id=f"gk{_u()}", client_id=cli.id, name="k",
                        api_key=f"ak{_u()}", created_by=u.id))
    s.add(OAuthAuthorizationCode(code=f"oc{_u()}", client_id=cli.id,
                                 expires_at=datetime.datetime(2026, 12, 31),
                                 user_id=u.id))
    s.add(RateLimitRule(client_id=cli.id, created_by=u.id))
    s.add(ThirdPartyIntegration(name="i", provider="im_b", created_by=u.id))

    t = Tenant(name=f"租户U{_u()}", code=f"UT{_u().upper()}")
    s.add(t); s.commit(); s.refresh(t)
    s.add(TenantAuditLog(tenant_id=t.id, user_id=u.id, action="create",
                         resource_type="tenant"))
    s.add(AgentConversation(team_id=team.id, board="operations", role="user",
                            content="hi", user_id=u.id))
    s.commit()
    return u, wo, st


class TestDeleteUser:
    def test_fkon_no_500_children_disposed(self, fk_env):
        from app.models.user import User, Team
        from app.models.workorder import WorkOrder, WorkOrderLog, WorkOrderSupportRequest
        from app.models.maintenance_record import MaintenanceRecord
        from app.models.alarm import Alarm
        from app.models.station import Station
        from app.models.vehicle import Vehicle
        from app.models.api_key import ApiKey
        from app.models.knowledge import KnowledgeArticle, KnowledgeFAQ
        from app.models.on_call import OnCallShift, OnCallLog
        from app.models.api_gateway import (
            ApiClient, GatewayApiKey, OAuthAuthorizationCode, RateLimitRule,
            ThirdPartyIntegration,
        )
        from app.models.tenant import TenantAuditLog
        from app.models.agent_memory import AgentConversation

        s = fk_env._fk_session()
        u, wo, st = _seed_user_with_refs(s)

        resp = fk_env.delete(f"/api/v1/users/{u.id}")
        assert resp.status_code != 500, f"裸500: {resp.status_code} {resp.text[:300]}"
        assert resp.status_code == 200, resp.text

        # seeding session 持 identity map 旧值 → 换新 session 断言
        s.close()
        s = fk_env._fk_session()

        # NOT NULL/凭证 级联组清零
        assert s.query(ApiKey).count() == 0
        assert s.query(OnCallShift).count() == 0
        assert s.query(OnCallLog).count() == 0
        # 可空历史引用置空，记录保留
        w = s.query(WorkOrder).one()
        assert (w.assignee_id, w.creator_id, w.verifier_id) == (None, None, None)
        assert s.query(WorkOrderLog).one().user_id is None
        assert s.query(MaintenanceRecord).one().engineer_id is None
        assert s.query(Alarm).one().handler_id is None
        ops = s.query(Station).filter(Station.id == st.id).one()
        assert ops.operator_id is None
        assert s.query(Vehicle).one().driver_id is None
        assert s.query(KnowledgeArticle).one().author_id is None
        assert s.query(KnowledgeFAQ).one().author_id is None
        assert s.query(WorkOrderSupportRequest).one().target_engineer_id is None
        assert s.query(ApiClient).one().created_by is None
        assert s.query(GatewayApiKey).one().created_by is None
        assert s.query(OAuthAuthorizationCode).one().user_id is None
        assert s.query(RateLimitRule).one().created_by is None
        assert s.query(ThirdPartyIntegration).one().created_by is None
        assert s.query(TenantAuditLog).one().user_id is None
        assert s.query(AgentConversation).one().user_id is None
        # Team.leader_id / parent_team_id 置空
        # Team.leader_id 置空（parent_team_id 指向的是保留的团队, 不在处置范围）
        assert all(t.leader_id is None for t in s.query(Team).all())

    def test_sqlite_no_orphans(self, client):
        from app.models.api_key import ApiKey
        from app.models.workorder import WorkOrder
        from app.models.on_call import OnCallShift

        s = client._sesh
        u, wo, st = _seed_user_with_refs(s)

        resp = client.delete(f"/api/v1/users/{u.id}")
        assert resp.status_code == 200, resp.text
        s.expire_all()
        assert s.query(ApiKey).count() == 0
        assert s.query(OnCallShift).count() == 0
        assert s.query(WorkOrder).one().assignee_id is None


# ────────────────────────────────────────────────────────────
# 5. DELETE /api/v1/enterprises/{id}
# ────────────────────────────────────────────────────────────

def _seed_enterprise(s, with_ledger=False, with_fleet=False):
    from app.models.enterprise import Enterprise, EnterpriseStatus
    from decimal import Decimal

    ent = Enterprise(name=f"企X2{_u()}", code=f"EX{_u().upper()}",
                     status=EnterpriseStatus.ACTIVE)
    if with_ledger:
        ent.balance = Decimal("100.00")
    s.add(ent); s.commit(); s.refresh(ent)

    if with_fleet:
        from app.models.fleet_charging_policy import FleetChargingPolicy
        from app.models.fleet_alert_rule import FleetAlertRule, AlertRuleType
        from app.models.enterprise_vehicle import (
            EnterpriseVehicle, StationVinWhitelist,
        )
        s.add(FleetChargingPolicy(enterprise_id=ent.id))
        s.add(FleetAlertRule(enterprise_id=ent.id, rule_type=AlertRuleType.LOW_BATTERY))
        veh = EnterpriseVehicle(enterprise_id=ent.id, plate_number=f"沪D{_u()[:5]}",
                                vin=f"VIN{_u()}{_u()}")
        s.add(veh)
        s.add(StationVinWhitelist(station_id=1, vin=f"VINV{_u()}",
                                  enterprise_id=ent.id, source="manual"))
        s.commit()
    return ent


def _ledger_row(s, ent, kind):
    from decimal import Decimal
    if kind == "txn":
        from app.models.enterprise_transaction import (
            EnterpriseTransaction, TransactionType,
        )
        s.add(EnterpriseTransaction(enterprise_id=ent.id,
                                    type=TransactionType.RECHARGE,
                                    amount=Decimal("1.00"),
                                    balance_after=Decimal("1.00")))
    elif kind == "recharge":
        from app.models.enterprise_recharge import RechargeApplication
        s.add(RechargeApplication(enterprise_id=ent.id, amount=Decimal("1.00")))
    elif kind == "bill":
        from app.models.settlement.bill import FleetSettlementBill
        s.add(FleetSettlementBill(bill_no=f"BL{_u()}", enterprise_id=ent.id,
                                  bill_period="2026-08"))
    elif kind == "invoice":
        from app.models.settlement.invoice import FleetInvoiceRequest
        s.add(FleetInvoiceRequest(enterprise_id=ent.id, amount=Decimal("1.00"),
                                  title="抬头"))
    elif kind == "fund_pool":
        from app.models.fund_pool import FundPool
        s.add(FundPool(enterprise_id=ent.id, account_name="a",
                       account_type="运营账户"))
    elif kind == "carbon":
        from app.models.carbon_emission import CarbonReductionSummary
        from app.models.fleet_carbon_certificate import FleetCarbonCertificate
        summ = CarbonReductionSummary(enterprise_id=ent.id, report_year=2026,
                                      report_month=8)
        s.add(summ); s.commit(); s.refresh(summ)
        s.add(FleetCarbonCertificate(enterprise_id=ent.id, summary_id=summ.id,
                                     certificate_no=f"CRT{_u()}"))


class TestDeleteEnterprise:
    def test_fkon_with_ledger_rejected_409(self, fk_env):
        """账本完整性优先：存在任何账本数据 → 拒绝删除，不做级联。"""
        s = fk_env._fk_session()
        ent = _seed_enterprise(s, with_ledger=True)
        for kind in ("txn", "recharge", "bill", "invoice", "fund_pool", "carbon"):
            _ledger_row(s, ent, kind)
        s.commit()

        resp = fk_env.delete(f"/api/v1/enterprises/{ent.id}")
        assert resp.status_code == 409, \
            f"有账本数据的企业删除应 409, 实际 {resp.status_code} {resp.text[:300]}"

    def test_fkon_with_balance_only_rejected_409(self, fk_env):
        s = fk_env._fk_session()
        ent = _seed_enterprise(s, with_ledger=True)
        resp = fk_env.delete(f"/api/v1/enterprises/{ent.id}")
        assert resp.status_code == 409, resp.text

    def test_fkon_clean_enterprise_fleet_children_deleted(self, fk_env):
        from app.models.fleet_charging_policy import FleetChargingPolicy
        from app.models.fleet_alert_rule import FleetAlertRule
        from app.models.enterprise_vehicle import (
            EnterpriseVehicle, StationVinWhitelist,
        )

        s = fk_env._fk_session()
        ent = _seed_enterprise(s, with_fleet=True)

        resp = fk_env.delete(f"/api/v1/enterprises/{ent.id}")
        assert resp.status_code != 500, f"裸500: {resp.status_code} {resp.text[:300]}"
        assert resp.status_code == 200, resp.text

        assert s.query(FleetChargingPolicy).count() == 0
        assert s.query(FleetAlertRule).count() == 0
        assert s.query(EnterpriseVehicle).count() == 0
        assert s.query(StationVinWhitelist).count() == 0

    def test_fkon_bare_enterprise_ok(self, fk_env):
        s = fk_env._fk_session()
        ent = _seed_enterprise(s)
        resp = fk_env.delete(f"/api/v1/enterprises/{ent.id}")
        assert resp.status_code == 200, resp.text

    def test_sqlite_no_orphans(self, client):
        from app.models.fleet_charging_policy import FleetChargingPolicy
        from app.models.enterprise_vehicle import (
            EnterpriseVehicle, StationVinWhitelist,
        )

        s = client._sesh
        ent = _seed_enterprise(s, with_fleet=True)
        resp = client.delete(f"/api/v1/enterprises/{ent.id}")
        assert resp.status_code == 200, resp.text
        s.expire_all()
        assert s.query(FleetChargingPolicy).count() == 0
        assert s.query(EnterpriseVehicle).count() == 0
        assert s.query(StationVinWhitelist).count() == 0
