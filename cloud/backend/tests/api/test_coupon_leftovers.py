"""优惠券域遗留小项 — 卡 ea373b3a

三项独立缺口，每项一个测试类：
1. update 窗口校验: PUT /coupon/{id} 可改 start/end 造反向/永久窗口，须校验合并后窗口
2. per_user_limit enforce: distribute 完全未限制单用户领取次数
3. 过期统计派生: revenue/coupon-effectiveness 按 DB EXPIRED 统计，与响应层派生口径脱节

锚点相对 now 动态生成（卡 7b7a7444 教训）。
"""
from datetime import datetime, timedelta, timezone

from tests.api._helpers import COUPON_URL, coupon_window, create_coupon
from app.models.coupon import Coupon, CouponUsage, CouponStatus


def _distribute(client, coupon_id, quantity=1, user_ids="1", **extra):
    body = {"coupon_id": coupon_id, "quantity": quantity, "user_ids": user_ids}
    body.update(extra)
    return client.post(f"{COUPON_URL}/distribute", json=body)


# ───────────────────────── 1. update 窗口校验 ─────────────────────────

class TestUpdateWindowValidation:
    """PUT /coupon/{id}: 合并后的 (start_time, end_time) 必须合法。

    背景: update 纯 setattr 落库，可单改 end_time 早于存量 start_time，或单改
    start_time 晚于存量 end_time，得到反向窗口的"永久券"（发放侧 start/end 检查
    形同虚设: now < start 恒真且 now > end 恒假 → 双向都拦不住的奇点在于反向窗口
    下两个条件必有一个成立，但 2099 类超远窗口则完全放行）。
    """

    def test_update_end_before_existing_start_rejected(self, client):
        """只改 end_time 早于存量 start_time → 400，DB 不变。
        存量 start 固定 now+10d（update 不受 create 侧校验，可直接种出宽窗口），
        新 end=now+2d < start → 合并后反向。"""
        cid = create_coupon(client, start_time=coupon_window(start=10, end=20)[0])
        _, early_end = coupon_window(start=5, end=2)  # now+2d < now+10d
        r = client.put(f"{COUPON_URL}/{cid}", json={"end_time": early_end})
        assert r.status_code == 400
        # DB 未被改动: 存量 end_time 仍在窗口内(>= start)
        obj = client._sesh.query(Coupon).get(cid)
        assert _naive_utc(obj.end_time) >= _naive_utc(obj.start_time)

    def test_update_start_after_existing_end_rejected(self, client):
        """只改 start_time 晚于存量 end_time → 400"""
        cid = create_coupon(client)
        late_start, _ = coupon_window(start=60, end=90)  # > 存量 end(now+30d)
        r = client.put(f"{COUPON_URL}/{cid}", json={"start_time": late_start})
        assert r.status_code == 400

    def test_update_both_fields_reversed_rejected(self, client):
        """同请求内 start > end → 400"""
        start, _ = coupon_window(start=10, end=20)
        _, end = coupon_window(start=-20, end=-10)
        cid = create_coupon(client)
        r = client.put(f"{COUPON_URL}/{cid}", json={"start_time": start, "end_time": end})
        assert r.status_code == 400

    def test_update_valid_window_accepted(self, client):
        """合法窗口（含只改单边后仍有序）→ 200 且落库"""
        start, end = coupon_window(start=-1, end=60)
        cid = create_coupon(client)
        r = client.put(f"{COUPON_URL}/{cid}", json={"start_time": start, "end_time": end})
        assert r.status_code == 200
        obj = client._sesh.query(Coupon).get(cid)
        assert _naive_utc(obj.start_time) <= _naive_utc(obj.end_time)

    def test_update_equal_start_end_accepted(self, client):
        """start == end（零宽窗口）合法: 发放侧为闭区间，允许瞬时窗口"""
        t = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
        cid = create_coupon(client)
        r = client.put(f"{COUPON_URL}/{cid}", json={"start_time": t, "end_time": t})
        assert r.status_code == 200

    def test_update_non_time_fields_still_work(self, client):
        """不涉窗口字段的更新不受影响（回归保护）"""
        cid = create_coupon(client, face_value=10.0)
        r = client.put(f"{COUPON_URL}/{cid}", json={"face_value": 25.0})
        assert r.status_code == 200


def _naive_utc(dt):
    """读出的 naive DateTime 按 UTC 解释并去掉 tzinfo，供比较。"""
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


# ───────────────────────── 2. per_user_limit ─────────────────────────

class TestPerUserLimit:
    """distribute enforce per_user_limit: None/0 = 不限，否则单用户领取数不超限。"""

    def test_distribute_exceeding_per_user_limit_rejected(self, client):
        """limit=1 时同一用户领第 2 张 → 400，无落库"""
        cid = create_coupon(client, total_stock=100, per_user_limit=1)
        assert _distribute(client, cid, quantity=1, user_ids="7").status_code == 200
        r = _distribute(client, cid, quantity=1, user_ids="7")
        assert r.status_code == 400
        assert "限领" in r.json()["detail"] or "limit" in r.json()["detail"].lower()
        assert client._sesh.query(CouponUsage).filter(
            CouponUsage.coupon_id == cid, CouponUsage.user_id == 7).count() == 1

    def test_distribute_error_message_contains_limit_value(self, client):
        """错误信息须说明 limit 值（可读性要求）"""
        cid = create_coupon(client, total_stock=100, per_user_limit=2)
        _distribute(client, cid, quantity=2, user_ids="8")
        r = _distribute(client, cid, quantity=1, user_ids="8")
        assert r.status_code == 400
        assert "2" in r.json()["detail"]

    def test_distribute_batch_exceeding_limit_rejected(self, client):
        """单次请求即超限: limit=1, quantity=3 全发给同一人 → 400（合并判定）"""
        cid = create_coupon(client, total_stock=100, per_user_limit=1)
        r = _distribute(client, cid, quantity=3, user_ids="9")
        assert r.status_code == 400
        assert client._sesh.query(CouponUsage).filter(
            CouponUsage.coupon_id == cid, CouponUsage.user_id == 9).count() == 0

    def test_distribute_mixed_pool_partial_over_limit_rejected(self, client):
        """user_ids 池内部分用户超限 → 整批拒绝（原子性，不部分发放）"""
        cid = create_coupon(client, total_stock=100, per_user_limit=1)
        assert _distribute(client, cid, quantity=1, user_ids="10").status_code == 200
        # 11 未领过(可领), 10 已领 1(limit=1, 不可再领) → 整批 400
        r = _distribute(client, cid, quantity=2, user_ids="10,11")
        assert r.status_code == 400
        # 无新增
        assert client._sesh.query(CouponUsage).filter(CouponUsage.coupon_id == cid).count() == 1

    def test_distribute_no_limit_when_zero_or_none(self, client):
        """per_user_limit=0 → 不限；多用户多次发放全通过"""
        cid = create_coupon(client, total_stock=100, per_user_limit=0)
        assert _distribute(client, cid, quantity=2, user_ids="12").status_code == 200
        r = _distribute(client, cid, quantity=2, user_ids="12")
        assert r.status_code == 200
        assert client._sesh.query(CouponUsage).filter(
            CouponUsage.coupon_id == cid, CouponUsage.user_id == 12).count() == 4

    def test_distribute_default_user_zero_unlimited(self, client):
        """user_ids 缺省 → 发给 user_id=0，默认 limit=1 时第 2 次被拒"""
        cid = create_coupon(client, total_stock=100, per_user_limit=1)
        assert _distribute(client, cid, quantity=1, user_ids="0").status_code == 200
        r = _distribute(client, cid, quantity=1, user_ids="0")
        assert r.status_code == 400

    def test_distribute_within_limit_ok(self, client):
        """limit=2, 领 2 张（分两次）→ 均 200"""
        cid = create_coupon(client, total_stock=100, per_user_limit=2)
        assert _distribute(client, cid, quantity=1, user_ids="13").status_code == 200
        assert _distribute(client, cid, quantity=1, user_ids="13").status_code == 200
        assert client._sesh.query(CouponUsage).filter(
            CouponUsage.coupon_id == cid, CouponUsage.user_id == 13).count() == 2


# ───────────────────────── 3. 过期统计派生 ─────────────────────────

class TestCouponEffectivenessDerivedExpired:
    """revenue/coupon-effectiveness 的 expired/active 计数须做过期派生，
    与 /coupon/usages 响应层口径一致（卡 73d52e60）: DB ACTIVE 且
    _as_utc(expires_at) < now → expired；== now 不算过期（严格小于）。
    """

    def _seed(self, client, *, status, expires_at):
        cid = create_coupon(client)
        u = CouponUsage(
            coupon_id=cid, user_id=500 + (id(status) % 7),
            coupon_code=f"CPN-EA-{status.value}-{id(expires_at) % 99999}",
            status=status, expires_at=expires_at,
        )
        client._sesh.add(u)
        client._sesh.commit()
        return cid, u.coupon_code

    def test_active_but_expired_counted_as_expired(self, client):
        """DB ACTIVE 但 expires_at 已过 → 统计为 expired 而非 active"""
        cid, code = self._seed(
            client, status=CouponStatus.ACTIVE,
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
        row = self._row(client, cid)
        assert row["expired"] == 1
        assert row["active"] == 0

    def test_valid_active_stays_active(self, client):
        """DB ACTIVE 且未过期 → active（不误伤）"""
        cid, _ = self._seed(
            client, status=CouponStatus.ACTIVE,
            expires_at=datetime.now(timezone.utc) + timedelta(days=10),
        )
        row = self._row(client, cid)
        assert row["active"] == 1
        assert row["expired"] == 0

    def test_db_expired_status_respected(self, client):
        """DB 已是 EXPIRED（redeem 懒翻转）→ 统计 expired（原行为保持）"""
        cid, _ = self._seed(
            client, status=CouponStatus.EXPIRED,
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
        row = self._row(client, cid)
        assert row["expired"] == 1

    def test_naive_expired_at_interpreted_as_utc(self, client):
        """naive expires_at 按 UTC 解释（与响应层 _as_utc 一致）。
        naive now-1d(UTC) 落库后读出为 naive → 视为已过期。"""
        cid, _ = self._seed(
            client, status=CouponStatus.ACTIVE,
            expires_at=datetime.utcnow() - timedelta(days=1),
        )
        row = self._row(client, cid)
        assert row["expired"] == 1

    def _row(self, client, cid):
        data = client.get("/api/v1/operate/revenue/coupon-effectiveness").json()["data"]
        return next(c for c in data["coupons"] if c["coupon_id"] == cid)
