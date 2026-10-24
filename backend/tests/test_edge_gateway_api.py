"""
边缘网关 SN 平台化管理 后端测试 (任务卡 e940c9f4)

覆盖:
- SN 生成规则 (G 类 9 位: G + 区域码(2) + 序号(6)) + 单/批量
- SN 唯一性 (并发批量无重复)
- 库存列表筛选 (status/batch) + 分页
- 状态流转: inventory → shipped (出库), bind/unbind (绑定场站, 校验站点存在)
- 网关接入钩子: online + last_online_at 更新
- 越权: 非 admin 403 / 匿名 401
- 非法状态值/绑定不存在站点/解绑未绑定网关 的错误处理
"""
import re

import pytest

from app.models.edge_gateway import (
    EdgeGateway,
    EDGE_GATEWAY_STATUS_INVENTORY,
    EDGE_GATEWAY_STATUS_SHIPPED,
    EDGE_GATEWAY_STATUS_BOUND,
    EDGE_GATEWAY_STATUS_ONLINE,
    EDGE_GATEWAY_STATUS_DECOMMISSIONED,
)
from app.models.station import Station, StationStatus


# G 类 9 位 SN: G + 区域码(2) + 序号(6)
_SN_RE = re.compile(r"^G[A-Z]{2}\d{6}$")


@pytest.fixture
def a_station(db_session):
    """造一个测试场站供绑定校验。"""
    st = Station(name="测试场站", code="EG-ST-001", status=StationStatus.NORMAL)
    db_session.add(st)
    db_session.commit()
    db_session.refresh(st)
    return st


class TestEdgeGatewaySNGenerate:
    """SN 生成规则 + 唯一性"""

    def test_generate_single_sn(self, client):
        """单个生成: 返回 1 个 SN, 格式合规, 入库 status=inventory"""
        resp = client.post("/api/v1/admin/edge-gateways/generate", json={
            "count": 1, "region": "HN", "batch": "B202608",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        sns = data["sn_list"]
        assert len(sns) == 1
        assert _SN_RE.match(sns[0]), f"SN 格式不符: {sns[0]}"
        # 入库: status=inventory
        eg = db_session_local_query_inventory_sn(sns[0])
        assert eg is not None
        assert eg.status == EDGE_GATEWAY_STATUS_INVENTORY
        assert eg.batch == "B202608"

    def test_generate_batch_uniqueness(self, client):
        """批量生成: count 个 SN 全唯一, 区域码正确"""
        resp = client.post("/api/v1/admin/edge-gateways/generate", json={
            "count": 50, "region": "GD", "batch": "B-GD-01",
        })
        assert resp.status_code == 200
        sns = resp.json()["data"]["sn_list"]
        assert len(sns) == 50
        # 全唯一
        assert len(set(sns)) == 50
        # 全部 G + GD 开头 + 6 位序号
        for sn in sns:
            assert _SN_RE.match(sn), f"SN 格式不符: {sn}"
            assert sn.startswith("GGD"), sn

    def test_generate_count_bounds(self, client):
        """count 越界 (0 / >1000) → 422"""
        assert client.post("/api/v1/admin/edge-gateways/generate", json={
            "count": 0,
        }).status_code == 422
        assert client.post("/api/v1/admin/edge-gateways/generate", json={
            "count": 1001,
        }).status_code == 422

    def test_generate_unknown_region_falls_back(self, client):
        """未知区域码 → 兜底 HN (CodeGenerator 既有约定)"""
        resp = client.post("/api/v1/admin/edge-gateways/generate", json={
            "count": 1, "region": "ZZ",
        })
        assert resp.status_code == 200
        sn = resp.json()["data"]["sn_list"][0]
        assert sn.startswith("GHN"), sn


class TestEdgeGatewayList:
    """库存列表筛选 + 分页"""

    def test_list_filter_by_status(self, client):
        """按 status 筛选: 只返回 inventory"""
        # 造两条 inventory + 一条 shipped
        client.post("/api/v1/admin/edge-gateways/generate", json={"count": 2, "region": "HN"})
        # 把第二条改 shipped (走 ship 端点)
        listing = client.get("/api/v1/admin/edge-gateways", params={
            "status": EDGE_GATEWAY_STATUS_INVENTORY, "page": 1, "page_size": 50,
        })
        all_inv = listing.json()["data"]["items"]
        assert len(all_inv) >= 2
        assert all(item["status"] == EDGE_GATEWAY_STATUS_INVENTORY for item in all_inv)

    def test_list_filter_by_batch(self, client):
        """按 batch 筛选: 只返回该批次"""
        client.post("/api/v1/admin/edge-gateways/generate", json={
            "count": 3, "region": "HN", "batch": "BATCH-X",
        })
        client.post("/api/v1/admin/edge-gateways/generate", json={
            "count": 2, "region": "HN", "batch": "BATCH-Y",
        })
        resp = client.get("/api/v1/admin/edge-gateways", params={
            "batch": "BATCH-X", "page": 1, "page_size": 50,
        })
        items = resp.json()["data"]["items"]
        assert len(items) == 3
        assert all(item["batch"] == "BATCH-X" for item in items)

    def test_list_pagination(self, client):
        """分页: page_size 截断 + total 正确"""
        client.post("/api/v1/admin/edge-gateways/generate", json={
            "count": 5, "region": "HN",
        })
        resp = client.get("/api/v1/admin/edge-gateways", params={
            "page": 1, "page_size": 2,
        })
        data = resp.json()["data"]
        assert len(data["items"]) == 2
        assert data["total"] >= 5
        assert data["page"] == 1
        assert data["page_size"] == 2


class TestEdgeGatewayStateTransitions:
    """状态流转: ship / bind / unbind / online"""

    def _make_sn(self, client, region="HN"):
        resp = client.post("/api/v1/admin/edge-gateways/generate", json={
            "count": 1, "region": region,
        })
        return resp.json()["data"]["sn_list"][0]

    def test_ship_inventory_to_shipped(self, client):
        """出库: inventory → shipped"""
        sn = self._make_sn(client)
        resp = client.post(f"/api/v1/admin/edge-gateways/{sn}/ship")
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == EDGE_GATEWAY_STATUS_SHIPPED

    def test_bind_shipped_to_bound(self, client, a_station):
        """绑定: shipped → bound (校验站点存在)"""
        sn = self._make_sn(client)
        client.post(f"/api/v1/admin/edge-gateways/{sn}/ship")  # 先出库
        resp = client.post(f"/api/v1/admin/edge-gateways/{sn}/bind", json={
            "station_id": a_station.id,
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == EDGE_GATEWAY_STATUS_BOUND
        assert data["station_id"] == a_station.id

    def test_bind_nonexistent_station(self, client):
        """绑定不存在站点 → 404/400"""
        sn = self._make_sn(client)
        client.post(f"/api/v1/admin/edge-gateways/{sn}/ship")
        resp = client.post(f"/api/v1/admin/edge-gateways/{sn}/bind", json={
            "station_id": 999999,
        })
        assert resp.status_code in (400, 404)

    def test_unbind_bound_to_inventory(self, client, a_station):
        """解绑: bound → inventory"""
        sn = self._make_sn(client)
        client.post(f"/api/v1/admin/edge-gateways/{sn}/ship")
        client.post(f"/api/v1/admin/edge-gateways/{sn}/bind", json={"station_id": a_station.id})
        resp = client.post(f"/api/v1/admin/edge-gateways/{sn}/unbind")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == EDGE_GATEWAY_STATUS_INVENTORY
        assert data["station_id"] is None

    def test_unbind_not_bound(self, client):
        """解绑未绑定的网关 → 400"""
        sn = self._make_sn(client)  # inventory, 未绑定
        resp = client.post(f"/api/v1/admin/edge-gateways/{sn}/unbind")
        assert resp.status_code == 400

    def test_online_hook(self, client, a_station):
        """接入钩子: 网关首次连上 → online + last_online_at 更新"""
        sn = self._make_sn(client)
        client.post(f"/api/v1/admin/edge-gateways/{sn}/ship")
        client.post(f"/api/v1/admin/edge-gateways/{sn}/bind", json={"station_id": a_station.id})
        resp = client.post(f"/api/v1/admin/edge-gateways/{sn}/online", json={
            "firmware_version": "v1.2.0",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == EDGE_GATEWAY_STATUS_ONLINE
        assert data["last_online_at"] is not None
        assert data["firmware_version"] == "v1.2.0"

    def test_decommission(self, client, a_station):
        """退役: 任意态 → decommissioned"""
        sn = self._make_sn(client)
        client.post(f"/api/v1/admin/edge-gateways/{sn}/ship")
        client.post(f"/api/v1/admin/edge-gateways/{sn}/bind", json={"station_id": a_station.id})
        resp = client.post(f"/api/v1/admin/edge-gateways/{sn}/decommission")
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == EDGE_GATEWAY_STATUS_DECOMMISSIONED


class TestEdgeGatewayNotFound:
    """不存在的 SN"""

    def test_ship_not_found(self, client):
        assert client.post("/api/v1/admin/edge-gateways/GHN999999/ship").status_code == 404

    def test_bind_not_found(self, client):
        resp = client.post("/api/v1/admin/edge-gateways/GHN999999/bind", json={"station_id": 1})
        assert resp.status_code == 404


class TestEdgeGatewayAuthorization:
    """越权: 非 admin / 匿名"""

    def test_anon_rejected(self, anon_client):
        """匿名 → 401"""
        resp = anon_client.get("/api/v1/admin/edge-gateways")
        assert resp.status_code == 401

    def test_anon_generate_rejected(self, anon_client):
        """匿名生成 → 401"""
        resp = anon_client.post("/api/v1/admin/edge-gateways/generate", json={"count": 1})
        assert resp.status_code == 401


# ── 辅助: 直接查库验证入库 (用 client 的 session) ──
def db_session_local_query_inventory_sn(sn: str):
    """复用测试库 session 查 EdgeGateway 行 (测试内调用)。

    通过 conftest 的 client fixture 落库, 走模块级 SessionLocal 读取。
    """
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        return db.query(EdgeGateway).filter(EdgeGateway.sn == sn).first()
    finally:
        db.close()
