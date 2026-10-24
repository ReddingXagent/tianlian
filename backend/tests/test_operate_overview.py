"""
运营概览 API 测试

覆盖 GET /api/v1/operate/overview:
- 空库返回零值且字段齐全
- 站点/设备/订单计数与累计营收/电量/时长聚合正确
- 使用率为合法数值
"""
from datetime import datetime, timezone
from decimal import Decimal

from app.models.station import Station, StationStatus
from app.models.device import Device, DeviceType, DeviceStatus
from app.models.charging_order import (
    ChargingOrder, OrderStatus, OrderPaymentStatus, PaymentMethod, UserType,
)


def _seed_overview(session):
    """1 站点 + 2 设备(1 online) + 1 已完成已支付订单"""
    st = Station(name="概览站", code="OVR001", address="北京", status=StationStatus.NORMAL)
    session.add(st)
    session.flush()

    session.add(Device(sn="OVR-SN-1", name="桩#1", code="OVRD1",
                       type=DeviceType.CHARGER_DC, status=DeviceStatus.ONLINE,
                       station_id=st.id, rated_power=120.0))
    session.add(Device(sn="OVR-SN-2", name="桩#2", code="OVRD2",
                       type=DeviceType.CHARGER_DC, status=DeviceStatus.OFFLINE,
                       station_id=st.id, rated_power=120.0))

    session.add(ChargingOrder(
        order_no="OVR001", station_id=st.id, device_id=1, user_id=101,
        user_type=UserType.APP, charged_kwh=Decimal("50.00"),
        electricity_fee=Decimal("60.00"), service_fee=Decimal("40.00"),
        total_amount=Decimal("100.00"), paid_amount=Decimal("100.00"),
        payment_status=OrderPaymentStatus.PAID, order_status=OrderStatus.COMPLETED,
        payment_method=PaymentMethod.WECHAT, duration_minutes=60,
        created_at=datetime.now(timezone.utc),
    ))
    session.commit()
    return st


class TestOperateOverview:
    """运营概览卡片聚合"""

    def test_overview_empty(self, client):
        """空库: 计数归零, 字段齐全"""
        data = client.get("/api/v1/operate/overview").json()["data"]
        assert data["station_count"] == 0
        assert data["device_count"] == 0
        assert data["total_orders"] == 0
        assert data["total_revenue"] == 0
        assert data["total_kwh"] == 0
        # 关键字段都存在
        for key in ["usage_rate", "total_hours", "today_revenue",
                    "yesterday_revenue", "revenue_mom_change"]:
            assert key in data

    def test_overview_aggregates(self, client):
        """有数据: 站点/设备/订单/营收/电量/时长聚合正确"""
        _seed_overview(client._sesh)
        data = client.get("/api/v1/operate/overview").json()["data"]

        assert data["station_count"] == 1
        assert data["device_count"] == 2
        # 1 笔已完成已支付订单
        assert data["total_orders"] == 1
        assert data["total_revenue"] == 100.0
        assert data["total_kwh"] == 50.0
        assert data["total_hours"] == 1.0  # 60 分钟
        # 今日营收(订单创建于今天)
        assert data["today_revenue"] == 100.0

    def test_overview_usage_rate_valid(self, client):
        """使用率为 [0,100] 区间内的数值"""
        _seed_overview(client._sesh)
        data = client.get("/api/v1/operate/overview").json()["data"]
        usage = data["usage_rate"]
        assert isinstance(usage, (int, float))
        assert 0 <= usage <= 100
