"""
备件库存管理测试 — maint-platform-spec §2.2

覆盖:
- CRUD: 创建 / 列表 / 详情 / 更新 / 删除
- 入库 inbound: available + total 同增
- 出库 outbound: available 减
- 库存不足校验: 出库超量 → 409
- 工单联动: spare-parts 申请命中库存则扣减 available; 不足 → 409; 未命中 → 放行(兼容)
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.models.spare_part import SparePartInventory

client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    pass


def _login():
    resp = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    data = resp.json()
    return data.get("token") or data.get("data", {}).get("token")


def _auth_headers():
    return {"Authorization": f"Bearer {_login()}"}


def _create_part(h, **overrides):
    """创建一条库存记录。初始 total_quantity == available_quantity。"""
    defaults = dict(part_name="IGBT模块", part_model="FF50R12",
                    total_quantity=10, warehouse="上海中心仓")
    defaults.update(overrides)
    resp = client.post("/api/v1/spare-parts", json=defaults, headers=h)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _create_wo(h, **overrides):
    defaults = dict(fault_desc="测试故障", type="repair", level="warning")
    defaults.update(overrides)
    resp = client.post("/api/v1/work-orders", json=defaults, headers=h)
    assert resp.status_code == 200
    return resp.json()["data"]


def _to_active(h, wo_id):
    client.post(f"/api/v1/work-orders/{wo_id}/accept", headers=h)
    client.post(f"/api/v1/work-orders/{wo_id}/start", headers=h)


# ========== CRUD ==========

def test_create_part():
    h = _auth_headers()
    data = _create_part(h, part_name="直流接触器", part_model="Schneider LC1D",
                        total_quantity=5, warehouse="北京仓")
    assert data["id"] > 0
    assert data["part_name"] == "直流接触器"
    assert data["part_model"] == "Schneider LC1D"
    # 初始: 累计入库量 == 可用量
    assert data["total_quantity"] == 5
    assert data["available_quantity"] == 5
    assert data["warehouse"] == "北京仓"


def test_create_part_default_quantities():
    """未传数量时默认 0。"""
    h = _auth_headers()
    resp = client.post("/api/v1/spare-parts",
                       json={"part_name": "熔断器"}, headers=h)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["total_quantity"] == 0
    assert data["available_quantity"] == 0


def test_list_parts_with_search():
    h = _auth_headers()
    _create_part(h, part_name="IGBT模块A", part_model="M1")
    _create_part(h, part_name="滤波电容B", part_model="M2")
    resp = client.get("/api/v1/spare-parts", params={"keyword": "IGBT"}, headers=h)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] >= 1
    assert all("IGBT" in p["part_name"] for p in data["items"])


def test_get_part_detail():
    h = _auth_headers()
    part = _create_part(h)
    resp = client.get(f"/api/v1/spare-parts/{part['id']}", headers=h)
    assert resp.status_code == 200
    assert resp.json()["data"]["id"] == part["id"]


def test_get_part_not_found():
    h = _auth_headers()
    resp = client.get("/api/v1/spare-parts/999999", headers=h)
    assert resp.status_code == 404


def test_update_part():
    h = _auth_headers()
    part = _create_part(h)
    resp = client.put(f"/api/v1/spare-parts/{part['id']}", json={
        "part_name": "IGBT模块-改", "warehouse": "深圳仓",
    }, headers=h)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["part_name"] == "IGBT模块-改"
    assert data["warehouse"] == "深圳仓"
    # 更新基本信息不得改动库存量
    assert data["available_quantity"] == 10
    assert data["total_quantity"] == 10


def test_delete_part():
    h = _auth_headers()
    part = _create_part(h)
    resp = client.delete(f"/api/v1/spare-parts/{part['id']}", headers=h)
    assert resp.status_code == 200
    # 删除后查询应 404
    resp = client.get(f"/api/v1/spare-parts/{part['id']}", headers=h)
    assert resp.status_code == 404


# ========== 入库 / 出库 ==========

def test_inbound_increases_both():
    h = _auth_headers()
    part = _create_part(h, total_quantity=10)
    resp = client.post(f"/api/v1/spare-parts/{part['id']}/inbound",
                       json={"quantity": 5, "note": "采购补货"}, headers=h)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["available_quantity"] == 15
    assert data["total_quantity"] == 15


def test_outbound_decreases_available_only():
    h = _auth_headers()
    part = _create_part(h, total_quantity=10)
    resp = client.post(f"/api/v1/spare-parts/{part['id']}/outbound",
                       json={"quantity": 4, "note": "领用"}, headers=h)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["available_quantity"] == 6
    # 累计入库量不变
    assert data["total_quantity"] == 10


def test_outbound_insufficient_stock():
    """出库量 > 可用量 → 409。"""
    h = _auth_headers()
    part = _create_part(h, total_quantity=3)
    resp = client.post(f"/api/v1/spare-parts/{part['id']}/outbound",
                       json={"quantity": 5}, headers=h)
    assert resp.status_code == 409
    # 库存未被改动
    detail = client.get(f"/api/v1/spare-parts/{part['id']}", headers=h).json()["data"]
    assert detail["available_quantity"] == 3


def test_inbound_invalid_quantity():
    """入库量必须 >= 1 → 422。"""
    h = _auth_headers()
    part = _create_part(h)
    resp = client.post(f"/api/v1/spare-parts/{part['id']}/inbound",
                       json={"quantity": 0}, headers=h)
    assert resp.status_code == 422


# ========== 工单联动扣减 ==========

def test_workorder_spare_parts_deducts_inventory():
    """工单申请备件命中库存 → 扣减 available，total 不变。"""
    h = _auth_headers()
    _create_part(h, part_name="IGBT模块", part_model="FF50R12", total_quantity=10)
    wo = _create_wo(h)
    _to_active(h, wo["id"])

    resp = client.post(f"/api/v1/work-orders/{wo['id']}/spare-parts", json={
        "part_name": "IGBT模块", "part_model": "FF50R12",
        "quantity": 2, "reason": "原模块烧毁",
    }, headers=h)
    assert resp.status_code == 200, resp.text

    # 库存被扣减
    listing = client.get("/api/v1/spare-parts", params={"keyword": "IGBT"}, headers=h).json()["data"]
    inv = listing["items"][0]
    assert inv["available_quantity"] == 8
    assert inv["total_quantity"] == 10


def test_workorder_spare_parts_insufficient_blocked():
    """工单申请量 > 库存可用量 → 409，库存不动。"""
    h = _auth_headers()
    _create_part(h, part_name="滤波电容", part_model="C-100", total_quantity=1)
    wo = _create_wo(h)
    _to_active(h, wo["id"])

    resp = client.post(f"/api/v1/work-orders/{wo['id']}/spare-parts", json={
        "part_name": "滤波电容", "part_model": "C-100",
        "quantity": 5, "reason": "批量更换",
    }, headers=h)
    assert resp.status_code == 409

    listing = client.get("/api/v1/spare-parts", params={"keyword": "滤波电容"}, headers=h).json()["data"]
    inv = listing["items"][0]
    assert inv["available_quantity"] == 1  # 未被扣减


def test_workorder_spare_parts_no_inventory_record_passes():
    """库存无此备件记录 → 放行记录申请(不阻断)，库存台账无变化。"""
    h = _auth_headers()
    wo = _create_wo(h)
    _to_active(h, wo["id"])

    resp = client.post(f"/api/v1/work-orders/{wo['id']}/spare-parts", json={
        "part_name": "全新未入库备件", "part_model": "X-1",
        "quantity": 3, "reason": "首次领用",
    }, headers=h)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["quantity"] == 3


# ========== 并发竞态回归 (卡 78bffa57) ==========
# SQLite 下 with_for_update() 为 no-op(已知), 并发正确性断言用
# 双连接交错互commit后 stale 快照必被刷新(检测串行化, 参照卡 0020305d):
# B 先读行固化 identity-map 陈旧快照(等价并发事务早先已读), A 完整跑通
# 路由并 commit, 再让 B 跑 —— 旧实现 B 基于陈旧快照计算(超扣/丢更新),
# 行锁+populate_existing 实现强制刷新快照基于最新值复查。

def _db_avail(test_db, part_id):
    s = test_db["session"]
    s.expire_all()
    p = s.query(SparePartInventory).filter(SparePartInventory.id == part_id).first()
    return p.available_quantity


def test_concurrent_outbound_no_oversell(test_db):
    """并发出库超扣: avail=10, A、B 各出 8, 第二笔必须 409, 终态 10-8=2。"""
    from fastapi import HTTPException
    from app.api.v1.spare_parts import StockMove, outbound
    s = test_db["session"]
    part = SparePartInventory(part_name="并发IGBT", part_model="R-CONC",
                              total_quantity=10, available_quantity=10)
    s.add(part)
    s.commit()
    SL = test_db["SessionLocal"]
    sa, sb = SL(), SL()

    # B 固化陈旧快照 available=10
    p_b = sb.query(SparePartInventory).filter(SparePartInventory.id == part.id).first()
    assert p_b.available_quantity == 10

    # A 完整出库 8 → DB=2
    outbound(part.id, StockMove(quantity=8), db=sa)
    sa.commit()

    # B 出库 8: 旧实现陈旧快照 10-8≥0 通过 → 超扣; 持锁复查基于 2<8 → 409
    with pytest.raises(HTTPException) as ei:
        outbound(part.id, StockMove(quantity=8), db=sb)
    assert ei.value.status_code == 409
    sb.rollback()

    final = _db_avail(test_db, part.id)
    assert final == 2, f"并发出库超扣: 期望 2, 实际 {final}"


def test_concurrent_inbound_no_lost_update(test_db):
    """并发入库丢更新: avail=10, A、B 各入 5, 终态应 20 而非 15。"""
    from app.api.v1.spare_parts import StockMove, inbound
    s = test_db["session"]
    part = SparePartInventory(part_name="并发电容", part_model="C-CONC",
                              total_quantity=10, available_quantity=10)
    s.add(part)
    s.commit()
    SL = test_db["SessionLocal"]
    sa, sb = SL(), SL()

    # B 固化陈旧快照 available=10
    p_b = sb.query(SparePartInventory).filter(SparePartInventory.id == part.id).first()
    assert p_b.available_quantity == 10

    # A 完整入库 5 → DB=15
    inbound(part.id, StockMove(quantity=5), db=sa)
    sa.commit()

    # B 入库 5: 旧实现陈旧快照 10+5=15(丢 A 的 5); 正确=20
    inbound(part.id, StockMove(quantity=5), db=sb)
    sb.commit()

    final = _db_avail(test_db, part.id)
    assert final == 20, f"并发入库丢更新: 期望 20, 实际 {final}"
    s2 = test_db["session"]
    s2.expire_all()
    p = s2.query(SparePartInventory).filter(SparePartInventory.id == part.id).first()
    assert p.total_quantity == 20


def test_outbound_uses_row_lock(test_db):
    """语义单测: 出库读取库存行必须经 with_for_update() 构造。"""
    from sqlalchemy import event
    from app.api.v1.spare_parts import StockMove, outbound
    s = test_db["session"]
    part = SparePartInventory(part_name="锁IGBT", part_model="R-LOCK",
                              total_quantity=5, available_quantity=5)
    s.add(part)
    s.commit()
    calls = {"for_update": 0}

    def _before_cursor_execute(conn, cursor, statement, parameters,
                               context, executemany):
        if "spare_parts_inventory" not in statement:
            return
        sel = getattr(context.compiled, "statement", None)
        if getattr(sel, "_for_update_arg", None) is not None:
            calls["for_update"] += 1

    engine = test_db["engine"]
    event.listen(engine, "before_cursor_execute", _before_cursor_execute)
    try:
        outbound(part.id, StockMove(quantity=1), db=s)
        s.commit()
    finally:
        event.remove(engine, "before_cursor_execute", _before_cursor_execute)
    assert calls["for_update"] >= 1, "出库余量读取必须经 with_for_update() 行锁"


def test_concurrent_workorder_deduct_no_oversell(test_db, monkeypatch):
    """工单联动扣减同竞态: avail=10, 两单各领 8, 第二笔 409, 终态 2。"""
    import app.api.v1  # noqa: F401  先加载 api.v1, 避免 deps 循环导入
    from fastapi import HTTPException
    from app.api.v1.workorders import routes_extensions as rext
    from app.models.user import User, UserRole
    from app.models.workorder import WorkOrder, WorkOrderStatus

    s = test_db["session"]
    part = SparePartInventory(part_name="联动IGBT", part_model="R-WO",
                              total_quantity=10, available_quantity=10)
    s.add(part)
    s.add_all([
        WorkOrder(id="WO_CONC_78BFFA57_1", fault_desc="并发测试",
                  status=WorkOrderStatus.PROCESSING),
        WorkOrder(id="WO_CONC_78BFFA57_2", fault_desc="并发测试",
                  status=WorkOrderStatus.PROCESSING),
    ])
    s.commit()
    monkeypatch.setattr(rext, "_check_workorder_team", lambda *a, **k: None)
    admin = User(id=0, username="admin", role=UserRole.ADMIN, status="active", team_id=None)
    SL = test_db["SessionLocal"]
    sa, sb = SL(), SL()
    payload = type("P", (), {"part_name": "联动IGBT", "part_model": "R-WO",
                             "quantity": 8, "reason": "r"})()

    # B 固化陈旧快照 available=10
    p_b = sb.query(SparePartInventory).filter(SparePartInventory.id == part.id).first()
    assert p_b.available_quantity == 10

    # A 单1 完整领用 8 → DB=2
    rext.spare_parts_workorder("WO_CONC_78BFFA57_1", payload, db=sa, user=admin)
    sa.commit()

    # B 单2 领 8: 旧实现陈旧快照 10-8≥0 → 超扣; 持锁复查 2<8 → 409
    with pytest.raises(HTTPException) as ei:
        rext.spare_parts_workorder("WO_CONC_78BFFA57_2", payload, db=sb, user=admin)
    assert ei.value.status_code == 409
    sb.rollback()

    final = _db_avail(test_db, part.id)
    assert final == 2, f"工单联动并发超扣: 期望 2, 实际 {final}"
