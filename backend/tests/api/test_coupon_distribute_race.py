"""优惠券发放库存并发竞态测试 — 卡 674bb77e (附带项)

缺陷 (与 redeem 同类 check-then-act): distribute_coupons 先读
`coupon.remaining_stock < quantity` 判库存, 后以 ORM 绝对值写回
`remaining_stock = 读到的值 - quantity`。并发两批发放同过读检查 → 后提交者
以旧值覆盖 → 丢更新: 库存只扣一份, 券却发出两份 (营销资产超发)。

测试手法 (卡 d74344ed 独立连接同构, 拦截点为 Session.flush): distribute 在
扣减前已 flush 批次 INSERT (此后会话持 SQLite RESERVED 写锁, 独立连接无法
再写), 故拦首次"有 pending CouponBatch 的 flush" —— 此时本会话尚未持写锁,
独立连接先把库存改到并发方提交后的值, 再走原 flush。确定性触发, 无 sleep/线程。

修复契约: 扣减改原子相对 CAS ——
    UPDATE coupons SET remaining_stock = remaining_stock - :q
    WHERE id=:id AND remaining_stock >= :q
rowcount==0 → rollback + 400 "库存不足，剩余 X 张" (沿用现有语义)。
相对扣减保证任意提交交错下终值正确, 不依赖拦截时序。
"""
from unittest.mock import patch

from app.models.coupon import Coupon, CouponBatch, CouponUsage

DIST_URL = "/api/v1/operate/coupon/distribute"


def _get_stock(session, cid):
    session.expire_all()
    return session.query(Coupon).filter(Coupon.id == cid).first().remaining_stock


class TestDistributeStockRace:
    """POST /coupon/distribute — 并发发放扣库存 (卡 674bb77e 附带项)"""

    def _rival_decrement(self, client, cid, rival_to):
        """构造 flush 拦截: 首次带 pending 批次的 flush 前, 独立连接把库存改成
        并发方提交后的值 rival_to (模拟并发方先行落库)。"""
        from sqlalchemy import text
        session = client._sesh
        orig_flush = type(session).flush
        fired = {"on": True}

        def racing_flush(self):
            if fired["on"] and any(isinstance(o, CouponBatch) for o in self.new):
                fired["on"] = False
                conn = self.get_bind().connect()
                try:
                    conn.execute(
                        text("UPDATE coupons SET remaining_stock=:v WHERE id=:c"),
                        {"v": rival_to, "c": cid},
                    )
                    conn.commit()
                finally:
                    conn.close()
            return orig_flush(self)

        return patch.object(type(session), "flush", racing_flush)

    def test_distribute_race_stock_lost_update(self, client):
        """并发双发各 10 张 (库存 100): 并发方先扣至 90, 本请求不应覆盖回 90.

        旧绝对值写回: 本请求以读到的 100 计算写 90 → 终值 90 (丢更新, 发出 20 张)。
        CAS 相对扣减: 终值 = 90 - 10 = 80, 与两批发放严格一致。
        """
        from tests.api._helpers import create_coupon
        cid = create_coupon(client, face_value=10.0, min_order_amount=0,
                            per_user_limit=0, total_stock=100)

        with self._rival_decrement(client, cid, rival_to=90):
            r = client.post(DIST_URL, json={
                "coupon_id": cid, "quantity": 10, "user_ids": "101",
            })

        assert r.status_code == 200, r.text
        assert r.json()["data"]["count"] == 10
        assert _get_stock(client._sesh, cid) == 80, "并发方已扣减后不得丢更新"

    def test_distribute_race_stock_exhausted_rejected(self, client):
        """并发方把库存扣到 5 (< quantity=10): 本请求 CAS 匹配 0 行 → 400 库存不足,
        批次/券码全部回滚, 不得超发。"""
        from tests.api._helpers import create_coupon
        cid = create_coupon(client, face_value=10.0, min_order_amount=0,
                            per_user_limit=0, total_stock=100)

        with self._rival_decrement(client, cid, rival_to=5):
            r = client.post(DIST_URL, json={
                "coupon_id": cid, "quantity": 10, "user_ids": "101",
            })

        assert r.status_code == 400, r.text
        assert "库存不足" in r.json()["detail"], r.text
        assert _get_stock(client._sesh, cid) == 5
        # 整批回滚: 未发出任何券码/批次
        assert client._sesh.query(CouponUsage).filter(
            CouponUsage.coupon_id == cid).count() == 0
        assert client._sesh.query(CouponBatch).filter(
            CouponBatch.coupon_id == cid).count() == 0

    def test_distribute_no_race_still_works(self, client):
        """无并发竞争正路径: 库存 100 发 10 → 90, 响应契约不变。"""
        from tests.api._helpers import create_coupon
        cid = create_coupon(client, face_value=10.0, min_order_amount=0,
                            per_user_limit=0, total_stock=100)

        r = client.post(DIST_URL, json={
            "coupon_id": cid, "quantity": 10, "user_ids": "101",
        })
        assert r.status_code == 200, r.text
        assert r.json()["data"]["count"] == 10
        assert len(r.json()["data"]["codes"]) == 10
        assert _get_stock(client._sesh, cid) == 90
