"""
司机考勤/工时管理测试 - fleet-platform-spec §4.3

覆盖:
- 批量录入: 新建 / 重复 upsert / 司机不存在 404
- 查询: 按司机+月份(日期升序)
- 月度汇总: 总工时 / 各状态天数 / 出勤率 / rest 班次分离
- 修正: 更新字段 / 记录不存在 404 / 非法枚举 400
"""
from app.models.enterprise import Enterprise
from app.models.fleet_driver import FleetDriver, DriverStatus


# ─── Helpers ───

def _seed_driver(db_session, idx=0):
    """建企业+司机, 返回 driver_id。"""
    ent = Enterprise(name=f"考勤测试企业{idx}", code=f"ATT{idx}", balance=10000.0)
    db_session.add(ent)
    db_session.commit()
    db_session.refresh(ent)
    d = FleetDriver(
        enterprise_id=ent.id,
        name=f"司机{idx}",
        phone=f"1380000000{idx}",
        license_no=f"LIC-ATT-{idx}",
        status=DriverStatus.ACTIVE,
    )
    db_session.add(d)
    db_session.commit()
    db_session.refresh(d)
    return d.id


_BATCH = [
    {"date": "2026-07-01", "shift_type": "day", "hours": 8.0, "status": "normal"},
    {"date": "2026-07-02", "shift_type": "day", "hours": 8.0, "status": "late"},
    {"date": "2026-07-03", "shift_type": "day", "hours": 8.0, "status": "absent"},
    {"date": "2026-07-04", "shift_type": "rest", "hours": 0.0, "status": "normal"},
    {"date": "2026-07-05", "shift_type": "night", "hours": 8.0, "status": "normal"},
]


def _import_batch(client, driver_id, records=None, month="2026-07"):
    """发起一次批量录入, 返回 response。"""
    return client.post("/api/v1/fleet/attendance/batch", json={
        "driver_id": driver_id,
        "month": month,
        "records": records if records is not None else _BATCH,
    })


# ======================================================================
# 批量录入
# ======================================================================

def test_batch_import_create(client, db_session):
    """POST /batch 新建多条考勤, 返回 created 计数。"""
    driver_id = _seed_driver(db_session)
    resp = _import_batch(client, driver_id)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["created"] == 5
    assert data["updated"] == 0
    assert data["total"] == 5
    assert data["driver_id"] == driver_id


def test_batch_import_upsert(client, db_session):
    """相同 (driver_id, date) 重复录入走更新, 返回 updated 计数。"""
    driver_id = _seed_driver(db_session)
    _import_batch(client, driver_id)
    # 再次导入相同日期 -> 全部更新
    resp = _import_batch(client, driver_id, records=[
        {"date": "2026-07-01", "shift_type": "day", "hours": 10.0, "status": "normal"},
    ])
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["created"] == 0
    assert data["updated"] == 1

    # 校验值已更新
    listing = client.get(f"/api/v1/fleet/attendance?driver_id={driver_id}&month=2026-07").json()["data"]["items"]
    day1 = next(it for it in listing if it["date"] == "2026-07-01")
    assert day1["hours"] == 10.0


def test_batch_import_driver_not_found(client, db_session):
    """司机不存在时返回 404。"""
    resp = _import_batch(client, driver_id=999999)
    assert resp.status_code == 404


def test_batch_import_duplicate_date_in_same_batch(client, db_session):
    """回归(卡 0e7deb3d 批量预取): 同一次 batch 内出现重复 date,
    第一条新建、第二条更新同一条, 不产生重复行。
    原逐条实现靠 autoflush 命中; 批量预取后须循环内同步 existing_map 才等价。
    """
    driver_id = _seed_driver(db_session)
    resp = _import_batch(client, driver_id, records=[
        {"date": "2026-07-01", "shift_type": "day", "hours": 8.0, "status": "normal"},
        {"date": "2026-07-01", "shift_type": "night", "hours": 6.0, "status": "late"},
    ])
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["created"] == 1
    assert data["updated"] == 1

    listing = client.get(f"/api/v1/fleet/attendance?driver_id={driver_id}&month=2026-07").json()["data"]["items"]
    day1 = [it for it in listing if it["date"] == "2026-07-01"]
    assert len(day1) == 1            # 不产生重复行
    assert day1[0]["hours"] == 6.0   # 取最后一次更新值
    assert day1[0]["shift_type"] == "night"


# ======================================================================
# 查询
# ======================================================================

def test_list_attendance_by_driver_month(client, db_session):
    """GET / 按 driver_id+month 查询, 日期升序。"""
    driver_id = _seed_driver(db_session)
    _import_batch(client, driver_id)

    resp = client.get(f"/api/v1/fleet/attendance?driver_id={driver_id}&month=2026-07")
    assert resp.status_code == 200
    data = resp.json()["data"]["items"]
    assert len(data) == 5
    dates = [it["date"] for it in data]
    assert dates == sorted(dates)
    assert dates[0] == "2026-07-01"
    # 字段完整性
    first = data[0]
    assert first["shift_type"] == "day"
    assert first["hours"] == 8.0
    assert first["status"] == "normal"


def test_list_attendance_driver_not_found(client, db_session):
    """查询司机不存在返回 404。"""
    resp = client.get("/api/v1/fleet/attendance?driver_id=999999&month=2026-07")
    assert resp.status_code == 404


# ======================================================================
# 月度汇总
# ======================================================================

def test_summary_total_hours_and_rate(client, db_session):
    """GET /summary 汇总: 总工时 / 各状态天数 / 出勤率 / rest 分离。

    批次: normal×2, late×1, absent×1, rest×1
    应出勤 = normal+late+absent = 4; 实到 = normal+late = 3; rate = 0.75
    总工时 = 8*4 + 0 = 32.0 (rest 工时为0)
    """
    driver_id = _seed_driver(db_session)
    _import_batch(client, driver_id)

    resp = client.get(f"/api/v1/fleet/attendance/summary?driver_id={driver_id}&month=2026-07")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total_days"] == 5
    assert data["total_hours"] == 32.0
    assert data["normal_days"] == 2
    assert data["late_days"] == 1
    assert data["absent_days"] == 1
    assert data["rest_days"] == 1
    assert data["attendance_rate"] == 0.75


def test_summary_no_records(client, db_session):
    """无考勤记录时出勤率为 0.0, 不报错。"""
    driver_id = _seed_driver(db_session)
    resp = client.get(f"/api/v1/fleet/attendance/summary?driver_id={driver_id}&month=2026-08")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total_days"] == 0
    assert data["total_hours"] == 0.0
    assert data["attendance_rate"] == 0.0


# ======================================================================
# 修正
# ======================================================================

def test_update_attendance(client, db_session):
    """PUT /{id} 修正字段, 回显新值。"""
    driver_id = _seed_driver(db_session)
    _import_batch(client, driver_id)
    record_id = client.get(
        f"/api/v1/fleet/attendance?driver_id={driver_id}&month=2026-07"
    ).json()["data"]["items"][0]["id"]

    resp = client.put(f"/api/v1/fleet/attendance/{record_id}", json={
        "hours": 10.5,
        "status": "late",
        "remark": "晚到 30 分钟",
    })
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["hours"] == 10.5
    assert data["status"] == "late"
    assert data["remark"] == "晚到 30 分钟"


def test_update_attendance_not_found(client, db_session):
    """修正不存在的记录返回 404。"""
    resp = client.put("/api/v1/fleet/attendance/99999", json={"hours": 8.0})
    assert resp.status_code == 404


def test_update_attendance_invalid_status(client, db_session):
    """非法 status 值返回 400。"""
    driver_id = _seed_driver(db_session)
    _import_batch(client, driver_id)
    record_id = client.get(
        f"/api/v1/fleet/attendance?driver_id={driver_id}&month=2026-07"
    ).json()["data"]["items"][0]["id"]

    resp = client.put(f"/api/v1/fleet/attendance/{record_id}", json={"status": "sick"})
    assert resp.status_code == 422  # Literal 前置 (卡 6031add1)


# ======================================================================
# 异常路径加固 (卡 416f2bb4)
# ======================================================================

def test_batch_import_integrity_conflict(client, db_session, monkeypatch):
    """批量录入遇唯一约束冲突 → 409, 不冒泡 500 裸堆栈。"""
    from sqlalchemy.exc import IntegrityError

    driver_id = _seed_driver(db_session)

    real_commit = db_session.commit
    call_count = {"n": 0}

    def _boom():
        call_count["n"] += 1
        # 仅在数据写入的 commit 抛 IntegrityError（跳过 fixture 自身的 seed commit）
        if call_count["n"] >= 1:
            raise IntegrityError("simulated", {}, Exception("UNIQUE"))
        return real_commit()

    monkeypatch.setattr(db_session, "commit", _boom)

    resp = _import_batch(client, driver_id)
    assert resp.status_code == 409
