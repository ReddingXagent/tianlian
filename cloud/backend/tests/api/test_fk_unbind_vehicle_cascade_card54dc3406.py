"""FK 级联补全：unbind_vehicle 裸删（卡 54dc3406）

enterprise_vehicles.unbind_vehicle 此前裸 db.delete(vehicle)，未调用
purge_enterprise_vehicle_children：车辆若有 v2g 计划/收益、维保、保险
（vehicle_id NOT NULL）→ 生产 PG IntegrityError 裸 500；SQLite FK OFF
下删除成功但留孤儿。弱引用（司机分配/告警规则/交易流水）应置空保留。

沿用 tests/api/test_fk_delete_engineer_cascade_card043f4ef0.py 双引擎范式：
- A 类：FK-ON 独立引擎下解绑不得裸 500；
- B 类：默认 sqlite（FK OFF）引擎下服务层级联不留孤儿。
admin 调用方 → assert_enterprise_team_access 豁免。
"""
import datetime
import uuid as _uuid

from tests.api.test_fk_delete_cascade import fk_env  # noqa: F401 复用 FK-ON 环境
from tests.api.test_fk_delete_cascade_x2 import _u


def _seed_vehicle_with_refs(s):
    """建企业 + 车辆 + 强/弱子引用，返回 (vehicle, 强引用ids, 弱引用objs)。"""
    from decimal import Decimal
    from app.models.enterprise import Enterprise
    from app.models.enterprise_transaction import (
        EnterpriseTransaction,
        TransactionType,
    )
    from app.models.enterprise_vehicle import EnterpriseVehicle
    from app.models.fleet_alert_rule import (
        AlertRuleType,
        FleetAlertRecord,
        FleetAlertRule,
    )
    from app.models.fleet_driver import DriverStatus, FleetDriver, LicenseType
    from app.models.fleet_v2g import FleetV2GPlan, FleetV2GRevenue, V2GPlanStatus
    from app.models.fleet_vehicle_profile import (
        FleetVehicleInsurance,
        FleetVehicleMaintenance,
        VehicleInsuranceType,
        VehicleMaintenanceType,
    )

    u = _u()
    ent = Enterprise(name=f"车企{u}", code=f"ENT{u.upper()}")
    s.add(ent)
    s.commit()
    s.refresh(ent)

    veh = EnterpriseVehicle(enterprise_id=ent.id, plate_number=f"沪A{u[:5].upper()}",
                            vin=f"VIN{u.upper()}")
    s.add(veh)
    s.commit()
    s.refresh(veh)

    # 强引用（vehicle_id NOT NULL）
    plan = FleetV2GPlan(enterprise_id=ent.id, vehicle_id=veh.id,
                        plan_date=datetime.date(2026, 8, 30),
                        status=V2GPlanStatus.SCHEDULED)
    rev = FleetV2GRevenue(enterprise_id=ent.id, vehicle_id=veh.id,
                          record_date=datetime.date(2026, 8, 30))
    maint = FleetVehicleMaintenance(vehicle_id=veh.id, type=VehicleMaintenanceType.REPAIR)
    ins = FleetVehicleInsurance(vehicle_id=veh.id, insurance_type=VehicleInsuranceType.COMPULSORY,
                                company="人保", policy_no=f"PO{u}",
                                start_date=datetime.datetime(2026, 1, 1),
                                end_date=datetime.datetime(2026, 12, 31),
                                premium=Decimal("3000.00"))
    s.add_all([plan, rev, maint, ins])

    # 弱引用（可空 → 置空保留）
    driver = FleetDriver(enterprise_id=ent.id, name="王师傅", phone="13800000000",
                         license_no=f"DL{u}", license_type=LicenseType.C1,
                         assigned_vehicle_id=veh.id, status=DriverStatus.ACTIVE)
    rule = FleetAlertRule(enterprise_id=ent.id, rule_type=AlertRuleType.LOW_BATTERY,
                          threshold={"soc_below": 20}, notify_channels=["im"],
                          enable=True)
    s.add(driver)
    s.add(rule)
    s.commit()
    s.refresh(rule)
    record = FleetAlertRecord(rule_id=rule.id, enterprise_id=ent.id,
                              vehicle_id=veh.id, plate_number=veh.plate_number,
                              alert_value="soc=15.0%")
    s.add(record)
    # FleetAlertRule 本体无 vehicle_id 列（记录表才有），弱引用挂 record 上
    tx = EnterpriseTransaction(enterprise_id=ent.id, vehicle_id=veh.id,
                               type=TransactionType.CONSUME,
                               amount=Decimal("50.00"),
                               balance_after=Decimal("950.00"))
    s.add(tx)
    s.commit()
    s.refresh(record)
    s.refresh(tx)
    s.refresh(driver)
    return veh, (plan.id, rev.id, maint.id, ins.id), (driver, record, tx)


class TestUnbindVehicleCascade:
    def test_fkon_no_500_children_disposed(self, fk_env):
        from app.models.enterprise_vehicle import EnterpriseVehicle
        from app.models.fleet_v2g import FleetV2GPlan, FleetV2GRevenue
        from app.models.fleet_vehicle_profile import (
            FleetVehicleInsurance,
            FleetVehicleMaintenance,
        )
        from app.models.fleet_driver import FleetDriver
        from app.models.fleet_alert_rule import FleetAlertRecord
        from app.models.enterprise_transaction import EnterpriseTransaction

        s = fk_env._fk_session()
        veh, strong_ids, (driver, record, tx) = _seed_vehicle_with_refs(s)
        plan_id, rev_id, maint_id, ins_id = strong_ids

        resp = fk_env.delete(
            f"/api/v1/enterprises/{veh.enterprise_id}/vehicles/{veh.id}"
        )
        assert resp.status_code != 500, f"裸500: {resp.status_code} {resp.text[:300]}"
        assert resp.status_code == 200, resp.text

        s.close()
        s = fk_env._fk_session()

        # NOT NULL 子表级联删
        assert s.query(FleetV2GPlan).filter(FleetV2GPlan.id == plan_id).count() == 0
        assert s.query(FleetV2GRevenue).filter(FleetV2GRevenue.id == rev_id).count() == 0
        assert s.query(FleetVehicleMaintenance).filter(
            FleetVehicleMaintenance.id == maint_id).count() == 0
        assert s.query(FleetVehicleInsurance).filter(
            FleetVehicleInsurance.id == ins_id).count() == 0
        # 弱引用置空保留
        d = s.query(FleetDriver).filter(FleetDriver.id == driver.id).one()
        assert d.assigned_vehicle_id is None
        r = s.query(FleetAlertRecord).filter(FleetAlertRecord.id == record.id).one()
        assert r.vehicle_id is None
        t = s.query(EnterpriseTransaction).filter(EnterpriseTransaction.id == tx.id).one()
        assert t.vehicle_id is None
        assert s.query(EnterpriseVehicle).filter(
            EnterpriseVehicle.id == veh.id).count() == 0

    def test_sqlite_no_orphans(self, client):
        from app.models.enterprise_vehicle import EnterpriseVehicle
        from app.models.fleet_v2g import FleetV2GPlan, FleetV2GRevenue
        from app.models.fleet_vehicle_profile import (
            FleetVehicleInsurance,
            FleetVehicleMaintenance,
        )
        from app.models.fleet_driver import FleetDriver
        from app.models.fleet_alert_rule import FleetAlertRecord
        from app.models.enterprise_transaction import EnterpriseTransaction

        s = client._sesh
        veh, strong_ids, (driver, record, tx) = _seed_vehicle_with_refs(s)
        plan_id, rev_id, maint_id, ins_id = strong_ids

        resp = client.delete(
            f"/api/v1/enterprises/{veh.enterprise_id}/vehicles/{veh.id}"
        )
        assert resp.status_code == 200, resp.text
        s.expire_all()
        assert s.query(FleetV2GPlan).count() == 0
        assert s.query(FleetV2GRevenue).count() == 0
        assert s.query(FleetVehicleMaintenance).count() == 0
        assert s.query(FleetVehicleInsurance).count() == 0
        assert s.query(FleetDriver).filter(FleetDriver.id == driver.id).one().assigned_vehicle_id is None
        assert s.query(FleetAlertRecord).filter(FleetAlertRecord.id == record.id).one().vehicle_id is None
        assert s.query(EnterpriseTransaction).filter(EnterpriseTransaction.id == tx.id).one().vehicle_id is None
        assert s.query(EnterpriseVehicle).filter(EnterpriseVehicle.id == veh.id).count() == 0
