"""企业整删漏删维保/保险（FK 级联同族残扫，卡 06158913 派生）

purge_enterprise_children 企业整删路径的 veh_ids 循环此前只清
FleetV2GPlan/FleetV2GRevenue，漏了 FleetVehicleMaintenance/
FleetVehicleInsurance（vehicle_id NOT NULL 无 ondelete）：
生产 PG IntegrityError 裸 500；SQLite FK OFF 留孤儿。
单车路径 purge_enterprise_vehicle_children 本就正确，此处只补企业路径。

沿用 test_fk_delete_cascade_x2 双引擎范式 + client fixture。
"""
import datetime
import uuid as _uuid
from decimal import Decimal

from tests.api.test_fk_delete_cascade import fk_env  # noqa: F401 复用 FK-ON 环境
from tests.api.test_fk_delete_cascade_x2 import _u


def _seed_vehicle_with_profile_refs(s):
    """建企业 + 车辆 + 维保/保险强引用，返回 (ent, veh, maint_id, ins_id)。"""
    from app.models.enterprise import Enterprise
    from app.models.enterprise_vehicle import EnterpriseVehicle
    from app.models.fleet_vehicle_profile import (
        FleetVehicleInsurance,
        FleetVehicleMaintenance,
        VehicleInsuranceType,
        VehicleMaintenanceType,
    )

    ent = Enterprise(name=f"维保FK企业{_u()}", code=f"MF{_u().upper()}")
    s.add(ent)
    s.commit()
    s.refresh(ent)

    veh = EnterpriseVehicle(enterprise_id=ent.id, plate_number=f"沪B{_u()[:5]}",
                            vin=f"VINV{_u()}{_u()}")
    s.add(veh)
    s.commit()
    s.refresh(veh)

    maint = FleetVehicleMaintenance(vehicle_id=veh.id,
                                    type=VehicleMaintenanceType.REPAIR)
    ins = FleetVehicleInsurance(
        vehicle_id=veh.id, insurance_type=VehicleInsuranceType.COMPULSORY,
        company="人保", policy_no=f"PO{_u()}",
        start_date=datetime.datetime(2026, 1, 1),
        end_date=datetime.datetime(2026, 12, 31),
        premium=Decimal("3000.00"))
    s.add_all([maint, ins])
    s.commit()
    s.refresh(maint)
    s.refresh(ins)
    return ent, veh, maint.id, ins.id


class TestEnterprisePurgeMaintenanceCascade:
    def test_fkon_no_500_children_disposed(self, fk_env):
        """FK-ON 引擎下整删带维保/保险的企业不得裸 500，子行清理。"""
        from app.models.enterprise_vehicle import EnterpriseVehicle
        from app.models.fleet_vehicle_profile import (
            FleetVehicleInsurance,
            FleetVehicleMaintenance,
        )

        s = fk_env._fk_session()
        ent, veh, maint_id, ins_id = _seed_vehicle_with_profile_refs(s)

        resp = fk_env.delete(f"/api/v1/enterprises/{ent.id}")
        assert resp.status_code != 500, f"裸500: {resp.status_code} {resp.text[:300]}"
        assert resp.status_code == 200, resp.text

        s.close()
        s = fk_env._fk_session()
        assert s.query(FleetVehicleMaintenance).filter(
            FleetVehicleMaintenance.id == maint_id).count() == 0
        assert s.query(FleetVehicleInsurance).filter(
            FleetVehicleInsurance.id == ins_id).count() == 0
        assert s.query(EnterpriseVehicle).filter(
            EnterpriseVehicle.id == veh.id).count() == 0

    def test_sqlite_no_orphans(self, client):
        """SQLite（FK OFF）整删 → 维保/保险不留孤儿行。"""
        from app.models.enterprise_vehicle import EnterpriseVehicle
        from app.models.fleet_vehicle_profile import (
            FleetVehicleInsurance,
            FleetVehicleMaintenance,
        )

        s = client._sesh
        ent, veh, maint_id, ins_id = _seed_vehicle_with_profile_refs(s)
        veh_id = veh.id

        resp = client.delete(f"/api/v1/enterprises/{ent.id}")
        assert resp.status_code == 200, resp.text
        s.expire_all()
        assert s.query(FleetVehicleMaintenance).filter(
            FleetVehicleMaintenance.id == maint_id).count() == 0
        assert s.query(FleetVehicleInsurance).filter(
            FleetVehicleInsurance.id == ins_id).count() == 0
        assert s.query(EnterpriseVehicle).filter(
            EnterpriseVehicle.id == veh_id).count() == 0

    def test_sqlite_bare_enterprise_still_ok(self, client):
        """无维保/保险的企业整删不受影响（回归）。"""
        from app.models.enterprise import Enterprise

        s = client._sesh
        ent = Enterprise(name=f"裸企{_u()}", code=f"BE{_u().upper()}")
        s.add(ent)
        s.commit()
        s.refresh(ent)

        resp = client.delete(f"/api/v1/enterprises/{ent.id}")
        assert resp.status_code == 200, resp.text
