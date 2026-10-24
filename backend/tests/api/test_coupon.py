#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
优惠券管理 API 测试
"""
import pytest
import uuid
from decimal import Decimal
from app.models.charging_order import ChargingOrder
from app.models.coupon import Coupon, CouponType, CouponStatus
from tests.api._helpers import coupon_window

# 发放窗口动态锚点（卡 73d52e60 窗口 enforcement 后，硬编码日期会随时间腐烂）
_WIN = coupon_window()


class TestCouponAPI:
    def test_create_coupon(self, client):
        payload = {
            "name": "API测试优惠券",
            "coupon_type": "fixed",
            "face_value": 15.0,
            "min_order_amount": 30.0,
            "max_discount_amount": 15.0,
            "applicable_user_types": "app,enterprise",
            "applicable_stations": "1,2",
            "total_stock": 200,
            "per_user_limit": 1,
            "valid_days": 30,
            "start_time": _WIN[0],
            "end_time": _WIN[1],
            "is_active": True,
            "description": "API测试描述",
        }
        r = client.post("/api/v1/operate/coupon", json=payload)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["id"] is not None
        assert data["name"] == "API测试优惠券"

    def test_list_coupons(self, client):
        # 先创建一个
        client.post("/api/v1/operate/coupon", json={
            "name": "列表测试券",
            "coupon_type": "percentage",
            "face_value": 0.9,
            "total_stock": 100,
            "start_time": _WIN[0],
            "end_time": _WIN[1],
        })
        r = client.get("/api/v1/operate/coupon")
        assert r.status_code == 200
        data = r.json()["data"]
        assert "items" in data
        assert len(data["items"]) >= 1

    def test_get_coupon_detail(self, client):
        create_r = client.post("/api/v1/operate/coupon", json={
            "name": "详情测试券",
            "coupon_type": "fixed",
            "face_value": 10.0,
            "total_stock": 50,
            "start_time": _WIN[0],
            "end_time": _WIN[1],
        })
        coupon_id = create_r.json()["data"]["id"]

        r = client.get(f"/api/v1/operate/coupon/{coupon_id}")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["id"] == coupon_id
        assert data["name"] == "详情测试券"

    def test_update_coupon(self, client):
        create_r = client.post("/api/v1/operate/coupon", json={
            "name": "待更新优惠券",
            "coupon_type": "fixed",
            "face_value": 5.0,
            "total_stock": 100,
            "start_time": _WIN[0],
            "end_time": _WIN[1],
        })
        coupon_id = create_r.json()["data"]["id"]

        r = client.put(f"/api/v1/operate/coupon/{coupon_id}", json={
            "name": "已更新优惠券",
            "face_value": 20.0,
        })
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["name"] == "已更新优惠券"

    def test_delete_coupon(self, client):
        create_r = client.post("/api/v1/operate/coupon", json={
            "name": "待删除优惠券",
            "coupon_type": "fixed",
            "face_value": 8.0,
            "total_stock": 50,
            "start_time": _WIN[0],
            "end_time": _WIN[1],
        })
        coupon_id = create_r.json()["data"]["id"]

        r = client.delete(f"/api/v1/operate/coupon/{coupon_id}")
        assert r.status_code == 200

        # 验证已删除
        r2 = client.get(f"/api/v1/operate/coupon/{coupon_id}")
        assert r2.status_code == 404

    def test_distribute_coupons(self, client):
        # per_user_limit=0(不限): 本测试验证 quantity 驱动的轮流分配, 卡 ea373b3a
        # enforce 后默认 limit=1 会把每人 10 张的分配判超限
        create_r = client.post("/api/v1/operate/coupon", json={
            "name": "发放测试券",
            "coupon_type": "fixed",
            "face_value": 10.0,
            "total_stock": 100,
            "per_user_limit": 0,
            "start_time": _WIN[0],
            "end_time": _WIN[1],
        })
        coupon_id = create_r.json()["data"]["id"]

        r = client.post("/api/v1/operate/coupon/distribute", json={
            "coupon_id": coupon_id,
            "quantity": 50,
            "user_type": "app",
            "user_ids": "1,2,3,4,5",
            "batch_name": "测试发放批次",
        })
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["batch_id"] is not None
        assert data["count"] == 50  # quantity=50, 轮流分配到5个用户
        assert len(data["codes"]) <= 10  # 只返回前10个券码

    def test_redeem_coupon(self, client):
        # 创建优惠券
        create_r = client.post("/api/v1/operate/coupon", json={
            "name": "核销测试券",
            "coupon_type": "fixed",
            "face_value": 10.0,
            "min_order_amount": 20.0,
            "total_stock": 100,
            "start_time": _WIN[0],
            "end_time": _WIN[1],
        })
        coupon_id = create_r.json()["data"]["id"]

        # 发放一张券
        dist_r = client.post("/api/v1/operate/coupon/distribute", json={
            "coupon_id": coupon_id,
            "quantity": 1,
            "user_type": "app",
            "user_ids": "999",
            "batch_name": "核销测试批次",
        })
        coupon_code = dist_r.json()["data"]["codes"][0]

        # 核销 (卡 5f7fa7ba: 须种 user_id=999 的真实订单, 券持有人即 999)
        order = ChargingOrder(
            order_no=f"TL{uuid.uuid4().hex[:14].upper()}",
            station_id=1, device_id=1, user_id=999,
        )
        client._sesh.add(order)
        client._sesh.commit()
        client._sesh.refresh(order)
        r = client.post("/api/v1/operate/coupon/redeem", json={
            "coupon_code": coupon_code,
            "order_id": order.id,
            "order_amount": 50.0,
        })
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["coupon_code"] == coupon_code
        assert data["discount_amount"] == 10.0

    def test_coupon_stats(self, client):
        r = client.get("/api/v1/operate/coupon/stats")
        assert r.status_code == 200
        data = r.json()["data"]
        assert "total_coupons" in data
        assert "total_stock" in data
        assert "total_used" in data

    def test_coupon_usages(self, client):
        r = client.get("/api/v1/operate/coupon/usages")
        assert r.status_code == 200
        data = r.json()["data"]
        assert "items" in data