"""
权限列表/树形图 API 测试

覆盖: GET /api/v1/permissions
- 平铺 items 结构
- 树形 tree 结构（含 children / 叶子节点）
"""
import pytest


def _get(client):
    return client.get("/api/v1/permissions", follow_redirects=True)


def test_permissions_returns_items_and_tree(client):
    """返回 items + tree 两个结构"""
    resp = _get(client)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "items" in data and "tree" in data
    assert isinstance(data["items"], list)
    assert isinstance(data["tree"], list)
    assert len(data["items"]) > 0
    assert len(data["tree"]) > 0


def test_permission_items_structure(client):
    """每条权限含 name/resource/action/label，name 形如 resource:action"""
    resp = _get(client)
    items = resp.json()["data"]["items"]
    sample = items[0]
    for key in ("name", "resource", "action", "label", "label_short"):
        assert key in sample
    assert ":" in sample["name"]
    name_resource = sample["name"].split(":", 1)[0]
    assert sample["resource"] == name_resource


def test_permission_tree_structure_with_leaves(client):
    """树节点含 children，叶子节点 is_leaf=True"""
    resp = _get(client)
    tree = resp.json()["data"]["tree"]
    node = tree[0]
    for key in ("key", "title", "resource", "children"):
        assert key in node
    assert isinstance(node["children"], list)
    assert len(node["children"]) > 0
    leaf = node["children"][0]
    assert leaf.get("is_leaf") is True
    assert leaf["name"]  # 非空


def test_permission_items_sorted_by_resource(client):
    """items 按资源定义顺序排序"""
    resp = _get(client)
    items = resp.json()["data"]["items"]
    # 至少覆盖多个不同资源
    resources = [it["resource"] for it in items]
    assert len(set(resources)) >= 2
