"""父表删除外键级联审计（卡 ed537344）

双形态缺陷背景：
- 生产 PostgreSQL 强制 FK，device/station 删除时若子表(告警/工单/维保/AI诊断/
  数字孪生/计费定价/停车等)存在引用行且无 ondelete/服务层级联 → IntegrityError
  裸 500（A 类缺陷）；
- 开发 SQLite 默认 FK OFF，删除直接成功 → 留下孤儿子行，诊断列表/定价查询/
  收藏解析等 join/引用路径数据腐化（B 类缺陷）。

修复策略（服务层显式级联，同一事务，不动 alembic）：
- delete device:
  - 级联删除：qr码 / 配置 / AI诊断 / 维保 / 数字孪生 / 聚合统计
  - 置空引用：告警(device_id)、工单(device_id) —— 历史记录保留
  - (遥测/分析/健康等已由 ORM cascade="all, delete-orphan" 关系覆盖)
- delete station:
  - 先级联删除站下 devices（复用同一策略）
  - 级联删除：数字孪生场景 / 计费定价5表 / 停车3表 / 收藏 / 聚合统计
  - 置空引用：告警/工单/维保/值班规则/AI诊断 的 station_id
  - (energy_strategy 4表为可空弱引用 → 置空)

测试用独立 PRAGMA foreign_keys=ON 引擎（SQLite 默认关 FK，须显式开才能复现
生产约束），模式取自 tests/test_workorders.py::test_create_fk_violation_returns_4xx。
"""
import os as _os
import uuid as _uuid

import pytest


# ────────────────────────────────────────────────────────────
# 公共构造：FK-ON 引擎 + app override
# ────────────────────────────────────────────────────────────

def _fk_engine():
    from sqlalchemy import create_engine, event

    db_path = f"/tmp/tianlian_fkdel_{_uuid.uuid4().hex}.db"
    eng = create_engine(
        f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
    )

    @event.listens_for(eng, "connect")
    def _enable_fk(dbapi_connection, record):
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    return eng, db_path


@pytest.fixture()
def fk_env(client):
    """FK-ON 独立引擎 + get_db override + admin token。

    依赖 client fixture 是为了让 require_permission 内的 SessionLocal 也指向
    测试库（复用 conftest 的 override 链）—— 但请求级 session 用本引擎的
    sessionmaker 逐请求新建（独立事务，避免 TestClient 长事务与端点 commit
    互相纠缠）。后端 sqlite 未开 FK 时（B 形态），用每请求新 session 强制
    让本引擎的 FK 约束在 commit 时生效。
    """
    from app.core.database import Base, get_db
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import BigInteger as SA_BigInteger
    from sqlalchemy.ext.compiler import compiles
    # 与 conftest._schema_template_db 相同: BigInteger PK 在 SQLite 须编译为
    # INTEGER 才有 rowid 自增语义
    @compiles(SA_BigInteger, "sqlite")
    def _compile_bigint_sqlite(element, compiler, **kw):
        return "INTEGER"
    import app.models  # noqa: F401 注册全部模型
    from app.api.v1.auth import get_current_user  # noqa: F401
    from tests._test_helpers import _fast_hash
    from app.models.user import User, UserRole
    from app.api.v1 import api_router
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    eng, db_path = _fk_engine()
    Base.metadata.create_all(bind=eng)
    FKSession = sessionmaker(bind=eng, expire_on_commit=False)
    s = FKSession()
    s.add(User(
        username="admin",
        password_hash=_fast_hash("admin123"),
        role=UserRole.ADMIN,
        status="active",
    ))
    s.commit()

    # require_permission 走模块级 SessionLocal
    import app.core.database as db_module
    _orig_sl = db_module.SessionLocal
    db_module.SessionLocal = FKSession

    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: FKSession()

    class _C(TestClient):
        pass

    try:
        with TestClient(app) as c:
            r = c.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
            assert r.status_code == 200, r.text
            token = r.json()["data"]["token"]
            c.headers["Authorization"] = f"Bearer {token}"
            c._fk_session = FKSession
            yield c
    finally:
        db_module.SessionLocal = _orig_sl
        s.close()
        eng.dispose()
        if _os.path.exists(db_path):
            _os.unlink(db_path)


def _team_id(s):
    from app.models.user import Team
    t = Team(name=f"团队FKDEL{_uuid.uuid4().hex[:6]}", code=f"FK{_uuid.uuid4().hex[:4].upper()}")
    s.add(t)
    s.commit()
    s.refresh(t)
    return t.id


def _seed_station_with_device(s, with_children=False):
    from app.models.station import Station, StationStatus
    from app.models.device import Device, DeviceType, DeviceStatus

    st = Station(name="级联站", code="FKDEL", status=StationStatus.NORMAL)
    s.add(st)
    s.commit()
    s.refresh(st)
    dev = Device(
        sn="SN-FKDEL-1", name="级联桩", code="FKDEL1",
        type=DeviceType.CHARGER_DC, status=DeviceStatus.ONLINE,
        station_id=st.id,
    )
    s.add(dev)
    s.commit()
    s.refresh(dev)
    return st, dev


def _seed_device_children(s, dev, st):
    """给设备挂上各类子行：NOT NULL 级联组 + nullable 置空组 + ORM 关系组。"""
    from datetime import date
    from app.models.device_qrcode import DeviceQRCode
    from app.models.device_config import DeviceConfig
    from app.models.ai_diagnosis import AIDiagnosisRecord
    from app.models.maintenance_record import MaintenanceRecord
    from app.models.digital_twin import DigitalTwinModel, DigitalTwinDataPoint, ThreeDModelType
    from app.models.pre_aggregation import DeviceDailyStats
    from app.models.alarm import Alarm, AlarmLevel, AlarmStatus
    from app.models.workorder import WorkOrder

    s.add(DeviceQRCode(device_id=dev.id, gun_no=1, qr_code="FKDEL00000001"))
    s.add(DeviceConfig(device_id=dev.id))
    s.add(AIDiagnosisRecord(device_id=dev.id, station_id=st.id))
    s.add(MaintenanceRecord(device_id=dev.id, station_id=st.id, title="维保"))
    s.add(DigitalTwinModel(device_id=dev.id, model_type=ThreeDModelType.CHARGER_DC))
    s.add(DigitalTwinDataPoint(device_id=dev.id, param_key="voltage", display_name="电压"))
    s.add(DeviceDailyStats(device_id=dev.id, station_id=st.id, date=date(2026, 8, 27)))
    s.add(Alarm(device_id=dev.id, station_id=st.id, level=AlarmLevel.WARNING,
                status=AlarmStatus.ACTIVE))
    s.add(WorkOrder(id="WO-FKDEL-1", device_id=dev.id, station_id=st.id))
    s.commit()


def _seed_station_children(s, st, team_id=None):
    """给站点挂上 NOT NULL station 子行（不含 device，device 单独驱动）。"""
    from datetime import date, datetime, timezone
    from decimal import Decimal
    from app.models.digital_twin import DigitalTwinScene
    from app.models.pricing_v2 import EnergyPrice, ServiceFeePrice, ParkingPrice, \
        OccupancyFeePrice, ReservationFeePrice, TimeSlotDefinition, UserType, FeeType, PeriodType, \
        ReservationPolicy
    from app.models.parking_event import OccupancyEvent
    from app.models.parking_integration import ParkingIntegrationConfig
    from app.models.parking_discount_applied import ParkingDiscountApplied
    from app.models.end_user import EndUser
    from app.models.end_user_favorite import EndUserFavorite
    from app.models.pre_aggregation import StationHourlyStats
    from app.models.on_call import OnCallRule

    from datetime import time as dtime
    slot = TimeSlotDefinition(name="峰段", period_type=PeriodType.PEAK,
                              start_time=dtime(8, 0), end_time=dtime(12, 0))
    eu = EndUser(wx_openid=f"openid-{st.id}")
    s.add(slot); s.add(eu)
    s.commit(); s.refresh(slot); s.refresh(eu)

    s.add(DigitalTwinScene(station_id=st.id, name="s", scene_config={}))
    s.add(EnergyPrice(station_id=st.id, slot_id=slot.id,
                      price_per_kwh=Decimal("1.0"), effective_date=date(2026, 1, 1)))
    s.add(ServiceFeePrice(station_id=st.id, user_type=UserType.APP,
                          fee_type=FeeType.PERCENT, fee_value=Decimal("0.1"),
                          effective_date=date(2026, 1, 1)))
    s.add(ParkingPrice(station_id=st.id, effective_date=date(2026, 1, 1)))
    s.add(OccupancyFeePrice(station_id=st.id, effective_date=date(2026, 1, 1)))
    s.add(ReservationFeePrice(station_id=st.id, effective_date=date(2026, 1, 1),
                              reservation_policy=ReservationPolicy.FLAT))
    s.add(OccupancyEvent(station_id=st.id, plate_number="沪A00001",
                         enter_at=datetime(2026, 8, 27, 10, 0, tzinfo=timezone.utc)))
    s.add(ParkingIntegrationConfig(station_id=st.id, app_key=f"ak-{st.id}",
                                   app_secret="sk"))
    s.add(ParkingDiscountApplied(station_id=st.id, plate_number="沪A00001",
                                 order_no=f"PO-{st.id}", amount=Decimal("1.00")))
    s.add(EndUserFavorite(end_user_id=eu.id, station_id=st.id))
    s.add(StationHourlyStats(station_id=st.id, hour=datetime(2026, 8, 27, 10, 0)))
    if team_id is not None:
        s.add(OnCallRule(name="值班", station_id=st.id, team_id=team_id,
                         rotation_order=[]))
    s.commit()


# ────────────────────────────────────────────────────────────
# A 类：FK-ON 下父删除不得 500
# ────────────────────────────────────────────────────────────

class TestDeleteDeviceWithChildren:
    def test_delete_device_no_500_and_children_disposed(self, fk_env):
        from app.models.device_qrcode import DeviceQRCode
        from app.models.device_config import DeviceConfig
        from app.models.ai_diagnosis import AIDiagnosisRecord
        from app.models.maintenance_record import MaintenanceRecord
        from app.models.digital_twin import DigitalTwinModel, DigitalTwinDataPoint
        from app.models.pre_aggregation import DeviceDailyStats
        from app.models.alarm import Alarm
        from app.models.workorder import WorkOrder

        s = fk_env._fk_session()
        st, dev = _seed_station_with_device(s)
        _seed_device_children(s, dev, st)

        resp = fk_env.delete(f"/api/v1/devices/{dev.id}")
        assert resp.status_code != 500, \
            f"删除有子行引用的设备触发裸500: {resp.status_code} {resp.text[:300]}"
        assert resp.status_code == 200, resp.text

        # 级联删除组：随设备消失
        assert s.query(DeviceQRCode).count() == 0
        assert s.query(DeviceConfig).count() == 0
        assert s.query(AIDiagnosisRecord).count() == 0
        assert s.query(MaintenanceRecord).filter(
            MaintenanceRecord.device_id == dev.id).count() == 0
        assert s.query(DigitalTwinModel).count() == 0
        assert s.query(DigitalTwinDataPoint).count() == 0
        assert s.query(DeviceDailyStats).count() == 0
        # 告警 device_id NOT NULL → 随设备删除（策略：不可置空即级联）
        assert s.query(Alarm).count() == 0
        # 工单 device_id 可空 → 行保留、置空
        wo = s.query(WorkOrder).one()
        assert wo.device_id is None

    def test_delete_device_no_children_ok(self, fk_env):
        s = fk_env._fk_session()
        st, dev = _seed_station_with_device(s)
        resp = fk_env.delete(f"/api/v1/devices/{dev.id}")
        assert resp.status_code == 200, resp.text


class TestDeleteStationWithChildren:
    def test_delete_station_no_500_and_children_disposed(self, fk_env):
        from app.models.station import Station
        from app.models.device import Device
        from app.models.digital_twin import DigitalTwinScene
        from app.models.pricing_v2 import EnergyPrice
        from app.models.parking_event import OccupancyEvent
        from app.models.end_user_favorite import EndUserFavorite
        from app.models.pre_aggregation import StationHourlyStats, DeviceDailyStats
        from app.models.alarm import Alarm
        from app.models.workorder import WorkOrder
        from app.models.on_call import OnCallRule
        from app.models.maintenance_record import MaintenanceRecord

        s = fk_env._fk_session()
        st, dev = _seed_station_with_device(s)
        _seed_device_children(s, dev, st)
        _seed_station_children(s, st)
        s.add(OnCallRule(name="值班", station_id=st.id, team_id=_team_id(s),
                         rotation_order=[]))
        s.commit()

        resp = fk_env.delete(f"/api/v1/stations/{st.id}")
        assert resp.status_code != 500, \
            f"删除有子行引用的站点触发裸500: {resp.status_code} {resp.text[:300]}"
        assert resp.status_code == 200, resp.text

        assert s.query(Station).filter(Station.id == st.id).count() == 0
        assert s.query(Device).filter(Device.station_id == st.id).count() == 0
        # NOT NULL 级联组全部随站点消失
        assert s.query(DigitalTwinScene).count() == 0
        assert s.query(EnergyPrice).count() == 0
        assert s.query(OccupancyEvent).count() == 0
        assert s.query(EndUserFavorite).count() == 0
        assert s.query(StationHourlyStats).count() == 0
        assert s.query(DeviceDailyStats).count() == 0
        # nullable 引用组：行保留、station_id 置空（告警已随设备级联删除）
        wo = s.query(WorkOrder).one()
        assert wo.station_id is None
        # 维保已随设备级联删除（device_id NOT NULL）
        assert s.query(MaintenanceRecord).count() == 0
        assert s.query(OnCallRule).one().station_id is None

    def test_delete_station_bare_ok(self, fk_env):
        from app.models.station import Station
        s = fk_env._fk_session()
        st = Station(name="空站", code="FKEMPTY")
        s.add(st); s.commit(); s.refresh(st)
        resp = fk_env.delete(f"/api/v1/stations/{st.id}")
        assert resp.status_code == 200, resp.text


# ────────────────────────────────────────────────────────────
# B 类：后端 sqlite（FK OFF）下的孤儿防护
# ────────────────────────────────────────────────────────────

def test_delete_device_sqlite_no_orphans(client):
    """默认测试引擎（FK OFF，B 形态）：服务层级联仍须清掉子行，不留孤儿。"""
    from app.models.station import Station, StationStatus
    from app.models.device import Device, DeviceType, DeviceStatus
    from app.models.device_qrcode import DeviceQRCode
    from app.models.ai_diagnosis import AIDiagnosisRecord
    from app.models.alarm import Alarm, AlarmLevel, AlarmStatus
    from app.models.workorder import WorkOrder

    s = client._sesh
    st = Station(name="孤儿站", code="ORPH", status=StationStatus.NORMAL)
    s.add(st); s.commit(); s.refresh(st)
    dev = Device(sn="SN-ORPH-1", name="孤儿桩", code="ORPH1",
                 type=DeviceType.CHARGER_DC, status=DeviceStatus.ONLINE,
                 station_id=st.id)
    s.add(dev); s.commit(); s.refresh(dev)
    _seed_device_children(s, dev, st)

    resp = client.delete(f"/api/v1/devices/{dev.id}")
    assert resp.status_code == 200, resp.text
    s.expire_all()
    # 无孤儿：级联组清零
    assert s.query(DeviceQRCode).count() == 0
    assert s.query(AIDiagnosisRecord).count() == 0
    # 告警 NOT NULL → 级联删除；工单可空 → 保留置空
    assert s.query(Alarm).count() == 0
    assert s.query(WorkOrder).one().device_id is None


def test_delete_station_sqlite_no_orphans(client):
    from app.models.station import Station, StationStatus
    from app.models.device import Device, DeviceType, DeviceStatus
    from app.models.pricing_v2 import EnergyPrice
    from app.models.end_user_favorite import EndUserFavorite
    from app.models.alarm import Alarm, AlarmLevel, AlarmStatus
    from app.models.on_call import OnCallRule

    s = client._sesh
    st = Station(name="孤儿站2", code="ORPH2", status=StationStatus.NORMAL)
    s.add(st); s.commit(); s.refresh(st)
    dev = Device(sn="SN-ORPH-2", name="孤儿桩2", code="ORPH2",
                 type=DeviceType.CHARGER_DC, status=DeviceStatus.ONLINE,
                 station_id=st.id)
    s.add(dev); s.commit(); s.refresh(dev)
    _seed_device_children(s, dev, st)
    _seed_station_children(s, st, team_id=_team_id(s))
    s.commit()

    resp = client.delete(f"/api/v1/stations/{st.id}")
    assert resp.status_code == 200, resp.text
    s.expire_all()
    assert s.query(Station).filter(Station.id == st.id).count() == 0
    assert s.query(Device).filter(Device.station_id == st.id).count() == 0
    assert s.query(EnergyPrice).count() == 0
    assert s.query(EndUserFavorite).count() == 0
    assert s.query(Alarm).count() == 0  # 告警 device_id NOT NULL → 随设备级联删除
    assert s.query(OnCallRule).one().station_id is None
