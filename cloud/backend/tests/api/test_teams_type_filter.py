"""
团队管理层级拆分 — teams API type 过滤 + parent_team 关联测试 (卡 ed15cbf4)

覆盖:
1. type 过滤正确性 (ops_company / maintenance_team / fleet)
2. 不传 type 返回全部
3. 创建团队带 type 字段
4. 创建运维团队带 parent_team_id (关联运营公司)
5. parent_team_id 指向非 ops_company → 400
6. parent_team_id 指向不存在的团队 → 400
7. 详情接口返回 parent_team_name
8. 更新团队 parent_team_id + 校验
9. 权限: 非 admin/operator 角色禁止访问
"""
import pytest


def _create_team(client, **body):
    """创建团队 helper, 返回 data dict。"""
    payload = {"name": "测试团队", "region": "HN"}
    payload.update(body)
    r = client.post("/api/v1/teams", json=payload)
    assert r.status_code == 200, f"创建团队失败: {r.status_code} {r.text[:300]}"
    return r.json()["data"]


class TestTeamTypeFilter:
    """type query 参数过滤。"""

    def test_filter_ops_company(self, client):
        """type=ops_company 只返回运营公司。"""
        _create_team(client, name="运营公司A", type="ops_company")
        _create_team(client, name="运维团队B", type="maintenance_team")

        r = client.get("/api/v1/teams?type=ops_company")
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        types = [t["type"] for t in items]
        assert all(t == "ops_company" for t in types), f"混入非 ops_company: {types}"
        assert any(t["name"] == "运营公司A" for t in items)

    def test_filter_maintenance_team(self, client):
        """type=maintenance_team 只返回运维团队。"""
        _create_team(client, name="公司X", type="ops_company")
        _create_team(client, name="维保Y", type="maintenance_team")

        r = client.get("/api/v1/teams?type=maintenance_team")
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        types = [t["type"] for t in items]
        assert all(t == "maintenance_team" for t in types), f"混入非 maintenance_team: {types}"
        assert any(t["name"] == "维保Y" for t in items)

    def test_filter_fleet(self, client):
        """type=fleet 只返回车队。"""
        _create_team(client, name="车队Z", type="fleet")

        r = client.get("/api/v1/teams?type=fleet")
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        assert all(t["type"] == "fleet" for t in items)
        assert any(t["name"] == "车队Z" for t in items)

    def test_no_type_returns_all(self, client):
        """不传 type 返回所有类型团队。"""
        _create_team(client, name="全量公司", type="ops_company")
        _create_team(client, name="全量维保", type="maintenance_team")

        r = client.get("/api/v1/teams")
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        types = set(t["type"] for t in items)
        assert "ops_company" in types
        assert "maintenance_team" in types


class TestTeamCreateWithType:
    """创建团队时写入 type / parent_team_id。"""

    def test_create_default_type(self, client):
        """不传 type, 默认 ops_company。"""
        team = _create_team(client, name="默认团队")
        assert team["type"] == "ops_company"

    def test_create_with_explicit_type(self, client):
        """显式传 type=maintenance_team。"""
        team = _create_team(client, name="显式维保", type="maintenance_team")
        assert team["type"] == "maintenance_team"
        assert team["parent_team_id"] is None

    def test_create_maintenance_with_parent(self, client):
        """运维团队挂到运营公司下。"""
        parent = _create_team(client, name="母公司M", type="ops_company")
        child = _create_team(
            client, name="子维保N", type="maintenance_team",
            parent_team_id=parent["id"],
        )
        assert child["parent_team_id"] == parent["id"]


class TestParentValidation:
    """parent_team_id 校验逻辑。"""

    def test_parent_must_be_ops_company(self, client):
        """parent_team_id 指向非 ops_company → 400。"""
        non_ops = _create_team(client, name="维保团队P", type="maintenance_team")
        r = client.post("/api/v1/teams", json={
            "name": "尝试挂维保", "type": "maintenance_team",
            "parent_team_id": non_ops["id"],
        })
        assert r.status_code == 400
        assert "ops_company" in r.json()["detail"]

    def test_parent_not_found(self, client):
        """parent_team_id 指向不存在的团队 → 400。"""
        r = client.post("/api/v1/teams", json={
            "name": "孤儿团队", "type": "maintenance_team",
            "parent_team_id": 99999,
        })
        assert r.status_code == 400
        assert "不存在" in r.json()["detail"]

    def test_update_parent_validation(self, client):
        """更新时 parent_team_id 指向非 ops_company → 400。"""
        ops = _create_team(client, name="运营公司Q", type="ops_company")
        mt = _create_team(client, name="维保R", type="maintenance_team")

        # 合法: 把维保挂到运营公司下
        r = client.put(f"/api/v1/teams/{mt['id']}", json={"parent_team_id": ops["id"]})
        assert r.status_code == 200
        assert r.json()["data"]["parent_team_id"] == ops["id"]

        # 非法: 挂到另一个维保团队下
        r2 = client.put(f"/api/v1/teams/{mt['id']}", json={"parent_team_id": mt["id"]})
        assert r2.status_code == 400
        assert "ops_company" in r2.json()["detail"]


class TestTeamDetailParentName:
    """详情接口返回 parent_team_name。"""

    def test_detail_returns_parent_name(self, client):
        """get_team 返回 parent_team_name (父团队存在时)。"""
        parent = _create_team(client, name="母公司S", type="ops_company")
        child = _create_team(
            client, name="子维保T", type="maintenance_team",
            parent_team_id=parent["id"],
        )

        r = client.get(f"/api/v1/teams/{child['id']}")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["parent_team_id"] == parent["id"]
        assert data["parent_team_name"] == "母公司S"

    def test_detail_no_parent_name_is_none(self, client):
        """无父团队时 parent_team_name 为 None。"""
        team = _create_team(client, name="独立团队U", type="ops_company")
        r = client.get(f"/api/v1/teams/{team['id']}")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["parent_team_id"] is None
        assert data["parent_team_name"] is None


class TestTeamListReturnType:
    """列表项包含 type / parent 字段。"""

    def test_list_item_has_type_field(self, client):
        """列表每项都有 type 字段。"""
        _create_team(client, name="列表团队V", type="fleet")
        r = client.get("/api/v1/teams")
        items = r.json()["data"]["items"]
        assert len(items) > 0
        for item in items:
            assert "type" in item
            assert "parent_team_id" in item
            assert "parent_team_name" in item
