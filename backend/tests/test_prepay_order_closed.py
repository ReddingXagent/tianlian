"""卡 2c49e61f — prepay 订单终态守卫 ORDER_CLOSED (契约驱动)

契约 §2.1 (backend/docs/contracts/user-client-contract.md L81):
错误响应含 ORDER_CLOSED, 但实现中 CODE_ORDER_CLOSED (response.py:18) 全仓库
无任何触发点 —— 已取消订单发起 prepay 不会返回该错误码。本文件补齐该守卫。

终态集合选择说明 (docstring 留档, 见测试类注释):
OrderStatus = pending/charging/completed/cancelled/failed。
本系统为后付费模型: 充电 completed 后仍需 prepay 支付 (tests/test_wx_merchant_payment.py
全部用 COMPLETED 订单 seed 且 prepay 成功), 故 completed 不属于"不可支付终态";
守卫集合 = {cancelled, failed}。
"""
import pytest

from app.models.payment_order import PaymentOrder


def _seed_order_with_status(client, order_no, user_id, order_status):
    """建归属 user_id、指定 order_status 的 ChargingOrder (复用站+桩+单最小链路)。"""
    from app.models.station import Station, StationStatus
    from app.models.device import Device, DeviceType, DeviceStatus
    from app.models.charging_order import ChargingOrder

    s = client._sesh
    st = Station(
        name=f"站_{order_no}", code=f"ST_{order_no}", status=StationStatus.NORMAL,
    )
    s.add(st)
    s.commit()
    s.refresh(st)
    dev = Device(
        sn=f"SN_{order_no}", name="桩", code=f"CHG_{order_no}",
        type=DeviceType.CHARGER_DC, status=DeviceStatus.ONLINE,
        station_id=st.id, rated_power=120.0,
    )
    s.add(dev)
    s.commit()
    s.refresh(dev)
    order = ChargingOrder(
        order_no=order_no, station_id=st.id, device_id=dev.id,
        user_id=user_id, order_status=order_status,
    )
    s.add(order)
    s.commit()
    return order


def _current_user_id(client):
    from app.models.user import User
    return client._sesh.query(User).filter(User.username == "admin").one().id


def _prepay(client, order_no):
    return client.post(
        "/api/v1/business/payments/prepay",
        json={"order_id": order_no, "openid": "oC", "scene": "miniprogram"},
    )


class TestPrepayOrderClosed:
    """卡 2c49e61f — 已取消/失败订单 prepay → ORDER_CLOSED。

    终态语义留档: OrderStatus 含 completed/cancelled/failed 三种"生命周期终态",
    但 completed 不拦 —— 后付费模型下充电完成后仍需支付 (现有测试
    test_wx_merchant_payment.py::TestPrepayContract 全部以 COMPLETED 订单
    seed 且断言 prepay 成功)。不可支付终态集合 = {cancelled, failed}:
    取消订单无需付款, 失败订单不可付款, 二者再发起统一下单无业务意义。
    """

    def test_prepay_cancelled_order_returns_order_closed(self, client):
        """已取消订单 → HTTP 200 + code!=0 + message=ORDER_CLOSED, 不落 PaymentOrder。"""
        from app.models.charging_order import OrderStatus
        _seed_order_with_status(
            client, "ord_closed_1", _current_user_id(client), OrderStatus.CANCELLED
        )
        r = _prepay(client, "ord_closed_1")
        assert r.status_code == 200
        body = r.json()
        assert body["code"] != 0
        assert body["message"] == "ORDER_CLOSED"
        assert body["data"] is None
        # 守卫在 payment service 之前, 不应落 PaymentOrder
        assert (
            client._sesh.query(PaymentOrder)
            .filter_by(business_order_no="ord_closed_1")
            .first()
            is None
        )

    def test_prepay_failed_order_returns_order_closed(self, client):
        """失败订单 → 同样 ORDER_CLOSED。"""
        from app.models.charging_order import OrderStatus
        _seed_order_with_status(
            client, "ord_closed_2", _current_user_id(client), OrderStatus.FAILED
        )
        r = _prepay(client, "ord_closed_2")
        assert r.status_code == 200
        body = r.json()
        assert body["code"] != 0
        assert body["message"] == "ORDER_CLOSED"
        assert body["data"] is None

    def test_prepay_pending_order_succeeds(self, client):
        """对照: 正常订单 (pending) 可 prepay, code=0 五字段 (mock 统一下单)。"""
        from app.models.charging_order import OrderStatus
        _seed_order_with_status(
            client, "ord_open_ok", _current_user_id(client), OrderStatus.PENDING
        )
        r = _prepay(client, "ord_open_ok")
        assert r.status_code == 200
        data = r.json()
        assert data["code"] == 0
        assert set(data["data"].keys()) == {
            "timeStamp", "nonceStr", "package", "signType", "paySign"
        }
