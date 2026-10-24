"""
管理后台 - 边缘网关 SN 平台台账 后端测试 (任务卡 e940c9f4)

覆盖:
- SN 生成规则 (G 类 9 位: G + 区域码2 + 序号6) + 格式校验
- 单个/批量生成 + 唯一性 (并发序列自增不撞号)
- 库存列表筛选 (status/batch/keyword) + 分页
- 状态流转: inventory → shipped → bound → online → decommissioned
- bind 校验站点存在 (404) + unbind 回到 inventory
- 非法状态值 400 / 网关不存在 404
- 越权: 非 admin (anon_client) → 401/403
"""
import re

from app.models.edge_gateway import (
    EdgeGateway,
    EDGE_GATEWAY_STATUS_INVENTORY,
    EDGE_GATEWAY_STATUS_SHIPPED,
    EDGE_GATEWAY_STATUS_BOUND,
    EDGE_GATEWAY_STATUS_ONLINE,
    EDGE_GATEWAY_STATUS_DECOMMISSIONED,
)
from app.models.station import Station, StationStatus


# G 类 9 位: G + 大写区域码(2 或 3) + 6 位数字序号
# 区域码有 2 位(HN/GD) 也有 3 位(HUN/SNH), 故 SN 长度 = 1 + len(region) + 6
def _sn_pattern(region: str = "HN") -> re.Pattern:
    return re.compile(rf"^G{region}\d{{6}}$")


class TestEdgeGatewaySNGenerate:
    """SN 生成: 规则 / 单个 / 批量 / 唯一性"""

    def test_generate_single_sn_format(self, client):
        """单个生成 → G + 区域码 + 6位序号, status=inventory。"""
        resp = client.post("/api/v1/admin/edge-gateways/generate", json={
            "count": 1, "region": "HN", "batch": "B1",
        })
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["count"] == 1
        sn = data["sn_list"][0]
        assert _sn_pattern("HN").match(sn), f"SN 格式不符: {sn}"

    def test_generate_batch_count_and_unique(self, client):
        """批量生成数量正确且 SN 全部唯一。"""
        resp = client.post("/api/v1/admin/edge-gateways/generate", json={
            "count": 5, "region": "GD", "batch": "B2026",
        })
        assert resp.status_code == 200, resp.text
        sns = resp.json()["data"]["sn_list"]
        assert len(sns) == 5
        # 全部唯一
        assert len(set(sns)) == 5
        # 全部符合 GD 区域格式
        for sn in sns:
            assert _sn_pattern("GD").match(sn), f"SN 格式不符: {sn}"

    def test_generate_records_inventory_status(self, client):
        """生成的 SN 入库即 status=inventory。"""
        resp = client.post("/api/v1/admin/edge-gateways/generate", json={"count": 2, "region": "HN"})
        sns = resp.json()["data"]["sn_list"]
        rows = client._sesh.query(EdgeGateway).filter(EdgeGateway.sn.in_(sns)).all()
        assert len(rows) == 2
        for r in rows:
            assert r.status == EDGE_GATEWAY_STATUS_INVENTORY
            assert r.station_id is None

    def test_generate_seq_incremental(self, client):
        """同区域连续生成 → 序号单调递增 (序列自增正确, 不撞号)。"""
        r1 = client.post("/api/v1/admin/edge-gateways/generate", json={"count": 1, "region": "JS"})
        r2 = client.post("/api/v1/admin/edge-gateways/generate", json={"count": 1, "region": "JS"})
        sn1 = r1.json()["data"]["sn_list"][0]
        sn2 = r2.json()["data"]["sn_list"][0]
        seq1 = int(sn1[-6:])
        seq2 = int(sn2[-6:])
        assert seq2 == seq1 + 1, f"序号未递增: {seq1} → {seq2}"

    def test_generate_invalid_count(self, client):
        """数量越界 → 422 (Pydantic Field ge/le)。"""
        resp = client.post("/api/v1/admin/edge-gateways/generate", json={"count": 0})
        assert resp.status_code == 422
        resp = client.post("/api/v1/admin/edge-gateways/generate", json={"count": 1001})
        assert resp.status_code == 422


class TestEdgeGatewayList:
    """库存列表: 筛选 + 分页"""

    @staticmethod
    def _seed(client, n_inventory=3, n_shipped=2):
        client.post("/api/v1/admin/edge-gateways/generate", json={"count": n_inventory, "region": "HN", "batch": "INV"})
        # 生成并流转到 shipped
        r = client.post("/api/v1/admin/edge-gateways/generate", json={"count": n_shipped, "region": "GD", "batch": "SHP"})
        for sn in r.json()["data"]["sn_list"]:
            client.post(f"/api/v1/admin/edge-gateways/{sn}/ship")

    def test_list_filter_by_status(self, client):
        self._seed(client, n_inventory=3, n_shipped=2)
        resp = client.get("/api/v1/admin/edge-gateways?status=shipped")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] >= 2
        for it in data["items"]:
            assert it["status"] == "shipped"

    def test_list_filter_by_batch(self, client):
        self._seed(client)
        resp = client.get("/api/v1/admin/edge-gateways?batch=INV")
        assert resp.status_code == 200
        for it in resp.json()["data"]["items"]:
            assert it["batch"] == "INV"

    def test_list_keyword_search(self, client):
        client.post("/api/v1/admin/edge-gateways/generate", json={"count": 1, "region": "GD"})
        resp = client.get("/api/v1/admin/edge-gateways?keyword=GHN")
        # keyword 按 SN 模糊: GHN 前缀应只命中 HN 区域
        for it in resp.json()["data"]["items"]:
            assert it["sn"].startswith("GHN")

    def test_list_pagination(self, client):
        client.post("/api/v1/admin/edge-gateways/generate", json={"count": 10, "region": "HN"})
        resp = client.get("/api/v1/admin/edge-gateways?page=1&page_size=3")
        data = resp.json()["data"]
        assert len(data["items"]) <= 3
        assert data["page"] == 1
        assert data["page_size"] == 3

    def test_list_invalid_status(self, client):
        resp = client.get("/api/v1/admin/edge-gateways?status=unknown_state")
        assert resp.status_code == 400


class TestEdgeGatewayStatusFlow:
    """状态流转: ship / bind / unbind / online / decommission"""

    @staticmethod
    def _make_sn(client) -> str:
        r = client.post("/api/v1/admin/edge-gateways/generate", json={"count": 1, "region": "HN"})
        return r.json()["data"]["sn_list"][0]

    @staticmethod
    def _make_station(client, sid: int = 5001):
        client._sesh.add(Station(id=sid, name="绑定测试站", code=f"BIND{sid}", status=StationStatus.NORMAL))
        client._sesh.commit()

    def test_ship_flow(self, client):
        sn = self._make_sn(client)
        resp = client.post(f"/api/v1/admin/edge-gateways/{sn}/ship")
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "shipped"

    def test_bind_sets_station_and_status(self, client):
        sn = self._make_sn(client)
        self._make_station(client, sid=5002)
        resp = client.post(f"/api/v1/admin/edge-gateways/{sn}/bind", json={"station_id": 5002})
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["status"] == "bound"
        assert data["station_id"] == 5002

    def test_bind_nonexistent_station_404(self, client):
        sn = self._make_sn(client)
        resp = client.post(f"/api/v1/admin/edge-gateways/{sn}/bind", json={"station_id": 999999})
        assert resp.status_code == 404

    def test_unbind_back_to_inventory(self, client):
        sn = self._make_sn(client)
        self._make_station(client, sid=5003)
        client.post(f"/api/v1/admin/edge-gateways/{sn}/bind", json={"station_id": 5003})
        resp = client.post(f"/api/v1/admin/edge-gateways/{sn}/unbind")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "inventory"
        assert data["station_id"] is None

    def test_unbind_unbound_400(self, client):
        """未绑定的网关解绑 → 400。"""
        sn = self._make_sn(client)
        resp = client.post(f"/api/v1/admin/edge-gateways/{sn}/unbind")
        assert resp.status_code == 400

    def test_online_hook_updates_last_online(self, client):
        sn = self._make_sn(client)
        resp = client.post(f"/api/v1/admin/edge-gateways/{sn}/online", json={"firmware_version": "v1.2.0"})
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["status"] == "online"
        assert data["last_online_at"] is not None
        assert data["firmware_version"] == "v1.2.0"

    def test_decommission_is_terminal(self, client):
        sn = self._make_sn(client)
        resp = client.post(f"/api/v1/admin/edge-gateways/{sn}/decommission")
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "decommissioned"

    def test_decommissioned_rejects_ship(self, client):
        """退役网关不可出库 → 400。"""
        sn = self._make_sn(client)
        client.post(f"/api/v1/admin/edge-gateways/{sn}/decommission")
        resp = client.post(f"/api/v1/admin/edge-gateways/{sn}/ship")
        assert resp.status_code == 400

    def test_full_lifecycle(self, client):
        """完整生命周期: inventory → shipped → bound → online → decommissioned。"""
        sn = self._make_sn(client)
        self._make_station(client, sid=5004)

        assert client.post(f"/api/v1/admin/edge-gateways/{sn}/ship").json()["data"]["status"] == "shipped"
        assert client.post(f"/api/v1/admin/edge-gateways/{sn}/bind", json={"station_id": 5004}).json()["data"]["status"] == "bound"
        assert client.post(f"/api/v1/admin/edge-gateways/{sn}/online").json()["data"]["status"] == "online"
        assert client.post(f"/api/v1/admin/edge-gateways/{sn}/decommission").json()["data"]["status"] == "decommissioned"


class TestEdgeGatewayNotFound:
    """不存在的 SN → 404"""

    def test_ship_404(self, client):
        assert client.post("/api/v1/admin/edge-gateways/GHN999999/ship").status_code == 404

    def test_bind_404(self, client):
        assert client.post("/api/v1/admin/edge-gateways/GHN999999/bind", json={"station_id": 1}).status_code == 404


class TestEdgeGatewayAuthorization:
    """越权: 非 admin 不可访问 (require_platform_admin)。"""

    def test_anonymous_rejected(self, anon_client):
        """匿名访问 → 401 (全局 enforce_auth 先拦)。"""
        resp = anon_client.get("/api/v1/admin/edge-gateways")
        assert resp.status_code in (401, 403)

    def test_anonymous_generate_rejected(self, anon_client):
        resp = anon_client.post("/api/v1/admin/edge-gateways/generate", json={"count": 1})
        assert resp.status_code in (401, 403)
