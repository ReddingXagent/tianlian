#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
折扣管理 API 测试
"""
import pytest
from decimal import Decimal
from app.models.price_discount import PriceDiscount, DiscountGroup, DiscountType


class TestDiscountAPI:
    def test_create_discount(self, client):
        payload = {
            "name": "测试折扣API",
            "discount_type": "percentage",
            "discount_rate": 0.85,
            "applicable_user_types": "app,card",
            "min_consumption": 10.0,
            "max_discount_amount": 20.0,
            "start_time": "2026-01-01T00:00:00",
            "end_time": "2026-12-31T23:59:59",
            "priority": 5,
            "is_active": True,
            "description": "API测试折扣",
        }
        r = client.post("/api/v1/operate/discount", json=payload)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["id"] is not None
        assert data["name"] == "测试折扣API"

    def test_list_discounts(self, client):
        # 先创建一个
        payload = {
            "name": "列表测试折扣",
            "discount_type": "fixed",
            "discount_rate": 5.0,
            "start_time": "2026-01-01T00:00:00",
            "end_time": "2026-12-31T23:59:59",
        }
        client.post("/api/v1/operate/discount", json=payload)

        r = client.get("/api/v1/operate/discount")
        assert r.status_code == 200
        data = r.json()["data"]
        assert "items" in data
        assert len(data["items"]) >= 1

    def test_get_discount_detail(self, client):
        payload = {
            "name": "详情测试折扣",
            "discount_type": "percentage",
            "discount_rate": 0.9,
            "start_time": "2026-01-01T00:00:00",
            "end_time": "2026-12-31T23:59:59",
        }
        create_r = client.post("/api/v1/operate/discount", json=payload)
        discount_id = create_r.json()["data"]["id"]

        r = client.get(f"/api/v1/operate/discount/{discount_id}")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["id"] == discount_id
        assert data["name"] == "详情测试折扣"

    def test_update_discount(self, client):
        payload = {
            "name": "待更新折扣",
            "discount_type": "fixed",
            "discount_rate": 3.0,
            "start_time": "2026-01-01T00:00:00",
            "end_time": "2026-12-31T23:59:59",
        }
        create_r = client.post("/api/v1/operate/discount", json=payload)
        discount_id = create_r.json()["data"]["id"]

        update_payload = {"name": "已更新折扣", "priority": 10}
        r = client.put(f"/api/v1/operate/discount/{discount_id}", json=update_payload)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["name"] == "已更新折扣"

    def test_delete_discount(self, client):
        payload = {
            "name": "待删除折扣",
            "discount_type": "percentage",
            "discount_rate": 0.95,
            "start_time": "2026-01-01T00:00:00",
            "end_time": "2026-12-31T23:59:59",
        }
        create_r = client.post("/api/v1/operate/discount", json=payload)
        discount_id = create_r.json()["data"]["id"]

        r = client.delete(f"/api/v1/operate/discount/{discount_id}")
        assert r.status_code == 200

        # 验证已删除
        r2 = client.get(f"/api/v1/operate/discount/{discount_id}")
        assert r2.status_code == 404

    def test_create_discount_group(self, client):
        # 先创建折扣
        discount_payload = {
            "name": "关联折扣",
            "discount_type": "percentage",
            "discount_rate": 0.88,
            "start_time": "2026-01-01T00:00:00",
            "end_time": "2026-12-31T23:59:59",
        }
        discount_r = client.post("/api/v1/operate/discount", json=discount_payload)
        discount_id = discount_r.json()["data"]["id"]

        group_payload = {
            "name": "VIP用户组",
            "discount_id": discount_id,
            "user_type": "enterprise",
            "user_ids": "100,101,102",
            "station_ids": "1,2",
            "priority": 20,
            "is_active": True,
        }
        r = client.post("/api/v1/operate/discount/group", json=group_payload)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["id"] is not None
        assert data["name"] == "VIP用户组"

    def test_list_discount_groups(self, client):
        r = client.get("/api/v1/operate/discount/groups")
        assert r.status_code == 200
        data = r.json()["data"]
        assert "items" in data

    def test_update_discount_group(self, client):
        # 先创建折扣和分组
        discount_r = client.post("/api/v1/operate/discount", json={
            "name": "分组关联折扣",
            "discount_type": "fixed",
            "discount_rate": 10.0,
            "start_time": "2026-01-01T00:00:00",
            "end_time": "2026-12-31T23:59:59",
        })
        discount_id = discount_r.json()["data"]["id"]

        group_r = client.post("/api/v1/operate/discount/group", json={
            "name": "原分组名",
            "discount_id": discount_id,
            "user_type": "app",
            "priority": 1,
            "is_active": True,
        })
        group_id = group_r.json()["data"]["id"]

        # 更新
        r = client.put(f"/api/v1/operate/discount/group/{group_id}", json={
            "name": "新分组名",
            "priority": 99,
        })
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["name"] == "新分组名"

    def test_delete_discount_group(self, client):
        discount_r = client.post("/api/v1/operate/discount", json={
            "name": "分组删除测试折扣",
            "discount_type": "percentage",
            "discount_rate": 0.9,
            "start_time": "2026-01-01T00:00:00",
            "end_time": "2026-12-31T23:59:59",
        })
        discount_id = discount_r.json()["data"]["id"]

        group_r = client.post("/api/v1/operate/discount/group", json={
            "name": "待删除分组",
            "discount_id": discount_id,
            "user_type": "card",
            "is_active": True,
        })
        group_id = group_r.json()["data"]["id"]

        r = client.delete(f"/api/v1/operate/discount/group/{group_id}")
        assert r.status_code == 200