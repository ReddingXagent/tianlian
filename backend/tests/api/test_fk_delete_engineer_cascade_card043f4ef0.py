"""FK 删除级联补全：delete_engineer 裸删（卡 043f4ef0）

engineers.py 的 delete_engineer 此前裸 db.delete(user)，未调用
purge_user_children：工程师若有 on_call_shifts / on_call_logs（user_id
NOT NULL）或 api_keys → 生产 PG IntegrityError 裸 500；SQLite FK OFF
下删除成功但留孤儿。

沿用 tests/api/test_fk_delete_cascade_x2.py 双引擎范式：
- A 类：FK-ON 独立引擎下删除不得裸 500；
- B 类：默认 sqlite（FK OFF）引擎下服务层级联不留孤儿。
admin 调用方 → assert_team_access 豁免，team_id 无碍。
"""
import datetime
import uuid as _uuid

from tests.api.test_fk_delete_cascade import fk_env  # noqa: F401 复用 FK-ON 环境
from tests.api.test_fk_delete_cascade_x2 import _u


def _seed_engineer_with_refs(s):
    """建带 on_call 班次/日志 + apikey + 可空引用的工程师，返回 (user, team, alarm, order)。"""
    from app.models.user import User, UserRole, Team
    from app.models.api_key import ApiKey
    from app.models.on_call import OnCallRule, OnCallShift, OnCallLog
    from app.models.alarm import Alarm, AlarmLevel, AlarmStatus
    from app.models.workorder import WorkOrder

    team = Team(name=f"工团{_u()}", code=f"E{_u().upper()}")
    s.add(team); s.commit(); s.refresh(team)

    u = User(username=f"eng{_u()}", password_hash="x", role=UserRole.ENGINEER,
             status="active", team_id=team.id, real_name="张工")
    s.add(u); s.commit(); s.refresh(u)

    s.add(ApiKey(name=f"ak{_u()}", key_hash="h" * 32, key_prefix="h", user_id=u.id))

    rule = OnCallRule(name="轮值", team_id=team.id, rotation_order=[u.id])
    s.add(rule); s.commit(); s.refresh(rule)
    shift = OnCallShift(rule_id=rule.id, user_id=u.id,
                        start_time=datetime.datetime(2026, 8, 27, 9, 0),
                        end_time=datetime.datetime(2026, 8, 27, 18, 0))
    s.add(shift); s.commit(); s.refresh(shift)
    s.add(OnCallLog(shift_id=shift.id, user_id=u.id, content="交接"))

    from app.models.station import Station, StationStatus
    from app.models.device import Device, DeviceType, DeviceStatus
    st = Station(name="工程师站", code=f"EG{_u().upper()}", status=StationStatus.NORMAL)
    s.add(st); s.commit(); s.refresh(st)
    dev = Device(sn=f"SN-EG-{_u()}", name="工程师桩", code=f"EG{_u().upper()}",
                 type=DeviceType.CHARGER_DC, status=DeviceStatus.ONLINE,
                 station_id=st.id)
    s.add(dev); s.commit(); s.refresh(dev)
    alm = Alarm(device_id=dev.id, station_id=st.id, level=AlarmLevel.WARNING,
                status=AlarmStatus.ACTIVE, handler_id=u.id)
    s.add(alm)
    wo = WorkOrder(id=f"WO-ENG-{_u()}", assignee_id=u.id)
    s.add(wo)
    s.commit()
    return u, team, alm, wo


class TestDeleteEngineer:
    def test_fkon_no_500_children_disposed(self, fk_env):
        from app.models.user import User
        from app.models.api_key import ApiKey
        from app.models.on_call import OnCallShift, OnCallLog
        from app.models.alarm import Alarm
        from app.models.workorder import WorkOrder

        s = fk_env._fk_session()
        u, team, alm, wo = _seed_engineer_with_refs(s)

        resp = fk_env.delete(f"/api/v1/engineers/{u.id}")
        assert resp.status_code != 500, f"裸500: {resp.status_code} {resp.text[:300]}"
        assert resp.status_code == 200, resp.text

        s.close()
        s = fk_env._fk_session()

        # NOT NULL 子表级联删
        assert s.query(ApiKey).count() == 0
        assert s.query(OnCallShift).count() == 0
        assert s.query(OnCallLog).count() == 0
        # 可空历史引用置空保留
        assert s.query(Alarm).filter(Alarm.id == alm.id).one().handler_id is None
        assert s.query(WorkOrder).filter(WorkOrder.id == wo.id).one().assignee_id is None
        assert s.query(User).filter(User.id == u.id).count() == 0

    def test_sqlite_no_orphans(self, client):
        from app.models.user import User
        from app.models.api_key import ApiKey
        from app.models.on_call import OnCallShift
        from app.models.workorder import WorkOrder

        s = client._sesh
        u, team, alm, wo = _seed_engineer_with_refs(s)

        resp = client.delete(f"/api/v1/engineers/{u.id}")
        assert resp.status_code == 200, resp.text
        s.expire_all()
        assert s.query(ApiKey).count() == 0
        assert s.query(OnCallShift).count() == 0
        assert s.query(WorkOrder).filter(WorkOrder.id == wo.id).one().assignee_id is None
        assert s.query(User).filter(User.id == u.id).count() == 0
