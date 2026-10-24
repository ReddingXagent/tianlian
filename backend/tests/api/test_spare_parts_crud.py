"""
备件库存管理 API 测试 (app/api/v1/spare_parts.py) — tests/api 目录补全 5 端点

覆盖端点 (前缀 /api/v1/spare-parts, router 依赖 get_current_user + require_write_permission("workorder:edit")):
  - GET    /{part_id}            备件详情 (get_part)
  - PUT    /{part_id}            更新备件基本信息 (update_part, 不改库存)
  - DELETE /{part_id}            删除备件 (delete_part)
  - POST   /{part_id}/inbound    入库 (available + total 同增)
  - POST   /{part_id}/outbound   出库 (仅减 available, 不足 409)

注: tests/test_spare_parts_inventory.py 已覆盖相同端点, 但用的是模块级 TestClient(app.main.app)
+ test_db fixture 的老模式; 本文件对齐 tests/api/ 目录规范 (conftest client fixture, 默认 admin
token 注入, 直接 seed 到 client._sesh), 与 test_supervision.py / test_order_fees_refund.py 同源。

测试矩阵:
  ① happy path: 详情 / 部分更新(不改库存) / 删除 / 入库双增 / 出库单减
  ② error path: 不存在 404 / 出库不足 409 / 入库非法数量 422

铁律: 仅加测试, 不改业务代码。
"""
from app.models.spare_part import SparePartInventory


BASE = "/api/v1/spare-parts"


# ─── seed helpers ───

def _create_part_via_api(client, **overrides):
    """经 API 创建一条库存记录 (初始 total == available), 返回 data。"""
    body = {
        "part_name": "IGBT模块",
        "part_model": "FF50R12",
        "total_quantity": 10,
        "warehouse": "上海中心仓",
    }
    body.update(overrides)
    r = client.post(BASE, json=body)
    assert r.status_code == 200, f"创建备件失败: {r.status_code} {r.text}"
    return r.json()["data"]


def _seed_part(session, part_name="滤波电容", part_model="C-100", total=5, warehouse="北京仓"):
    """直接 seed 一条库存记录 (用于 inbound/outbound/PUT/DELETE 前置)。"""
    p = SparePartInventory(
        part_name=part_name,
        part_model=part_model,
        total_quantity=total,
        available_quantity=total,
        warehouse=warehouse,
    )
    session.add(p)
    session.commit()
    session.refresh(p)
    return p


# ==================== get_part: GET /{part_id} ====================

class TestGetPart:
    def test_get_part_detail(self, client):
        p = _seed_part(client._sesh, part_name="接触器")
        r = client.get(f"{BASE}/{p.id}")
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["id"] == p.id
        assert d["part_name"] == "接触器"
        assert d["total_quantity"] == 5
        assert d["available_quantity"] == 5

    def test_get_part_not_found_404(self, client):
        r = client.get(f"{BASE}/999999")
        assert r.status_code == 404
        assert "不存在" in r.json()["detail"]


# ==================== update_part: PUT /{part_id} ====================

class TestUpdatePart:
    def test_update_part_partial(self, client):
        """更新基本信息; 未传字段保持。"""
        p = _seed_part(client._sesh, part_name="原名", warehouse="原仓")
        r = client.put(f"{BASE}/{p.id}", json={"part_name": "新名", "part_model": "X-1"})
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["part_name"] == "新名"
        assert d["part_model"] == "X-1"
        assert d["warehouse"] == "原仓"  # 未传 → 保持

    def test_update_part_does_not_change_stock(self, client):
        """PUT 不得改动库存量 (库存仅经 inbound/outbound 变动)。"""
        p = _seed_part(client._sesh, total=10)
        r = client.put(f"{BASE}/{p.id}", json={"part_name": "改名"})
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["total_quantity"] == 10
        assert d["available_quantity"] == 10

    def test_update_part_not_found_404(self, client):
        r = client.put(f"{BASE}/999999", json={"part_name": "x"})
        assert r.status_code == 404


# ==================== delete_part: DELETE /{part_id} ====================

class TestDeletePart:
    def test_delete_part(self, client):
        p = _seed_part(client._sesh)
        r = client.delete(f"{BASE}/{p.id}")
        assert r.status_code == 200, r.text
        # action_response 结构: {code: 200, message, data, timestamp}
        assert r.json()["code"] == 200
        assert r.json()["message"] == "备件已删除"
        # 删除后再查 → 404
        assert client.get(f"{BASE}/{p.id}").status_code == 404

    def test_delete_part_not_found_404(self, client):
        r = client.delete(f"{BASE}/999999")
        assert r.status_code == 404


# ==================== inbound: POST /{part_id}/inbound ====================

class TestInbound:
    def test_inbound_increases_both(self, client):
        """入库 — available 与 total 同增。"""
        p = _seed_part(client._sesh, total=10)
        r = client.post(f"{BASE}/{p.id}/inbound", json={"quantity": 5})
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["total_quantity"] == 15
        assert d["available_quantity"] == 15

    def test_inbound_not_found_404(self, client):
        r = client.post(f"{BASE}/999999/inbound", json={"quantity": 1})
        assert r.status_code == 404

    def test_inbound_invalid_quantity_422(self, client):
        """quantity <= 0 触发 pydantic ge=1 → 422。"""
        p = _seed_part(client._sesh)
        r = client.post(f"{BASE}/{p.id}/inbound", json={"quantity": 0})
        assert r.status_code == 422


# ==================== outbound: POST /{part_id}/outbound ====================

class TestOutbound:
    def test_outbound_decreases_available_only(self, client):
        """出库 — 仅减 available, total 不变。"""
        p = _seed_part(client._sesh, total=10)
        r = client.post(f"{BASE}/{p.id}/outbound", json={"quantity": 4})
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["available_quantity"] == 6
        assert d["total_quantity"] == 10  # total 不变

    def test_outbound_exact_available_ok(self, client):
        """出库量恰好等于可用量 → 200 (边界: 可用清零)。"""
        p = _seed_part(client._sesh, total=5)
        r = client.post(f"{BASE}/{p.id}/outbound", json={"quantity": 5})
        assert r.status_code == 200
        assert r.json()["data"]["available_quantity"] == 0

    def test_outbound_insufficient_409(self, client):
        """出库量超过可用量 → 409。"""
        p = _seed_part(client._sesh, total=3)
        r = client.post(f"{BASE}/{p.id}/outbound", json={"quantity": 8})
        assert r.status_code == 409
        assert "库存不足" in r.json()["detail"]

    def test_outbound_not_found_404(self, client):
        r = client.post(f"{BASE}/999999/outbound", json={"quantity": 1})
        assert r.status_code == 404

    def test_outbound_invalid_quantity_422(self, client):
        p = _seed_part(client._sesh)
        r = client.post(f"{BASE}/{p.id}/outbound", json={"quantity": 0})
        assert r.status_code == 422
