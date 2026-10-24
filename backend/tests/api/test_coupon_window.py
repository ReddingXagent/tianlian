"""优惠券发放窗口 / 过期语义测试 — 卡 73d52e60

缺口1: distribute 只查 is_active+remaining_stock, 无 start_time≤now≤end_time 窗口校验
       → 窗口外/未开始的券可照常发放（营销资产在非计划时段流出）
缺口2: /coupon/usages 列表不过滤不派生 expires_at, 过期券(DB status=ACTIVE)显示 active

锚点全部相对 now 动态生成（卡 7b7a7444 日期腐烂教训），不用硬编码日期。
"""
from datetime import datetime, timedelta, timezone

from tests.api._helpers import COUPON_URL, coupon_window, create_coupon
from app.models.coupon import Coupon, CouponUsage, CouponStatus


def _distribute(client, coupon_id, quantity=1, user_ids="1"):
    return client.post(f"{COUPON_URL}/distribute", json={
        "coupon_id": coupon_id, "quantity": quantity,
        "user_ids": user_ids, "batch_name": "窗口测试发放",
    })


class TestDistributeWindow:
    """发放路径窗口 enforcement: now 必须落在 [start_time, end_time] 内"""

    def test_distribute_before_window_rejected(self, client):
        """未开始发放的券 → 400"""
        start, end = coupon_window(start=10, end=20)
        cid = create_coupon(client, start_time=start, end_time=end)
        r = _distribute(client, cid)
        assert r.status_code == 400
        assert "未开始" in r.json()["detail"]
        # 无批次落库、库存未扣
        assert client._sesh.query(CouponUsage).filter(CouponUsage.coupon_id == cid).count() == 0
        assert client._sesh.query(Coupon).get(cid).remaining_stock == 100

    def test_distribute_after_window_rejected(self, client):
        """已结束发放的券 → 400"""
        start, end = coupon_window(start=-20, end=-10)
        cid = create_coupon(client, start_time=start, end_time=end)
        r = _distribute(client, cid)
        assert r.status_code == 400
        assert "已结束" in r.json()["detail"]
        assert client._sesh.query(CouponUsage).filter(CouponUsage.coupon_id == cid).count() == 0

    def test_distribute_in_window_ok(self, client):
        """窗口内 → 正常发放"""
        cid = create_coupon(client)  # 默认 now±30 天
        r = _distribute(client, cid, quantity=2, user_ids="1,2")
        assert r.status_code == 200
        assert r.json()["data"]["count"] == 2

    def test_distribute_window_boundary_inclusive(self, client):
        """start_time 恰为现在(秒级) → 视为窗口内（闭区间语义）"""
        start = datetime.now(timezone.utc).isoformat()
        _, end = coupon_window(end=5)
        cid = create_coupon(client, start_time=start, end_time=end)
        r = _distribute(client, cid)
        assert r.status_code == 200

    def test_distribute_expired_but_active_still_blocked(self, client):
        """is_active=True 但窗口已过 → 仍被窗口拦截（is_active 与窗口独立）"""
        start, end = coupon_window(start=-30, end=-1)
        cid = create_coupon(client, is_active=True, start_time=start, end_time=end)
        r = _distribute(client, cid)
        assert r.status_code == 400
        assert "已结束" in r.json()["detail"]


class TestUsagesDerivedStatus:
    """/coupon/usages 响应层过期派生: ACTIVE 且 expires_at<now → 显示 expired

    设计取舍（二选一，选响应层派生）: 不在 GET 路径做批量 UPDATE——读端点带写
    会与并行核销竞态(把 USED 判成 EXPIRED 覆盖)，且污染只读语义。DB 状态仅在
    核销/redeem 懒翻转（既有行为）。
    """

    def test_expired_usage_shows_expired_in_list(self, client):
        """DB status=ACTIVE 但 expires_at 已过 → 列表显示 expired"""
        cid = create_coupon(client)
        u = CouponUsage(
            coupon_id=cid, user_id=1, coupon_code="CPN-DER-EXPIRED",
            status=CouponStatus.ACTIVE,
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
        client._sesh.add(u)
        client._sesh.commit()

        items = client.get(f"{COUPON_URL}/usages").json()["data"]["items"]
        target = next(i for i in items if i["coupon_code"] == "CPN-DER-EXPIRED")
        assert target["status"] == "expired"
        # 响应派生, DB 不被改写
        db_u = client._sesh.query(CouponUsage).filter(
            CouponUsage.coupon_code == "CPN-DER-EXPIRED").first()
        assert db_u.status == CouponStatus.ACTIVE

    def test_valid_usage_stays_active_in_list(self, client):
        cid = create_coupon(client)
        u = CouponUsage(
            coupon_id=cid, user_id=2, coupon_code="CPN-DER-VALID",
            status=CouponStatus.ACTIVE,
            expires_at=datetime.now(timezone.utc) + timedelta(days=10),
        )
        client._sesh.add(u)
        client._sesh.commit()

        items = client.get(f"{COUPON_URL}/usages").json()["data"]["items"]
        target = next(i for i in items if i["coupon_code"] == "CPN-DER-VALID")
        assert target["status"] == "active"

    def test_derived_status_respects_status_filter(self, client):
        """派生后过滤 status=expired 须能命中派生过期的记录"""
        cid = create_coupon(client)
        client._sesh.add(CouponUsage(
            coupon_id=cid, user_id=3, coupon_code="CPN-DER-FILT",
            status=CouponStatus.ACTIVE,
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        ))
        client._sesh.commit()

        r = client.get(f"{COUPON_URL}/usages", params={"status": "expired"})
        codes = [i["coupon_code"] for i in r.json()["data"]["items"]]
        assert "CPN-DER-FILT" in codes
