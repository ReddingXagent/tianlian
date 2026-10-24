"""优惠券核销并发竞态测试 — 卡 674bb77e

缺陷 (大圣已复核实锤): redeem_coupon 读出 CouponUsage 后检查 status != ACTIVE
再置 USED 提交, 整段无行锁/原子守卫。并发核销同一 coupon_code 双双通过检查
→ 双核销双抵扣 (两次 200, 两份 discount_amount)。

测试手法 (卡 d74344ed 独立连接同构, 拦截点不同): ORM 端点旧写法在 commit 时才
flush 脏对象, 故 d74344ed 拦 commit; 本修复的 CAS 是 eager UPDATE 语句, 若仍拦
commit, 独立连接写入时请求事务已持 SQLite 写锁 → database is locked (已实测
500, 非竞态语义)。改拦 Session.execute: 当 CAS UPDATE(coupon_usages) 即将执行
时 (请求会话尚未持写锁), 独立连接先把同券码置 used 提交, 模拟并发方先行落库;
随后本请求 UPDATE ... WHERE status='active' 匹配 0 行。确定性触发, 无 sleep/线程。

未修复代码上无 eager UPDATE, patch 不触发, 端点照常 200 → 本测试 RED。
"""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from sqlalchemy import text
from sqlalchemy import Update

from app.models.charging_order import ChargingOrder
from app.models.coupon import CouponStatus, CouponUsage


def _seed_order(session, *, user_id):
    """插一条最小 ChargingOrder, 返回订单 id (SQLite 测试库无 FK 强制)"""
    o = ChargingOrder(
        order_no=f"TL{uuid.uuid4().hex[:14].upper()}",
        station_id=1,
        device_id=1,
        user_id=user_id,
    )
    session.add(o)
    session.commit()
    session.refresh(o)
    return o.id


def _seed_usage(session, coupon_id, *, user_id=101,
                code="CPN-RACE-000001", expires_delta_days=30):
    """插一条持券人为 user_id 的 CouponUsage (对齐 test_coupon_redeem_order_guard)"""
    u = CouponUsage(
        coupon_id=coupon_id,
        user_id=user_id,
        user_type="app",
        coupon_code=code,
        status=CouponStatus.ACTIVE,
        expires_at=datetime.now(timezone.utc) + timedelta(days=expires_delta_days),
    )
    session.add(u)
    session.commit()
    return u


class TestRedeemConcurrentRace:
    """POST /coupon/redeem — 并发核销同一券码 (卡 674bb77e)"""

    def test_redeem_race_second_write_rejected(self, client):
        """并发竞态: 本请求读检后、CAS 落库前, 并发方已核销同券码 → 400 状态错误, 不双抵扣.

        模拟: patch Session.execute, 首条针对 coupon_usages 的 UPDATE 执行前,
        独立连接先 UPDATE 同券码为 used + 抢写并发方的 order_id/discount/used_at。
        修复后 CAS 的 WHERE status='active' 匹配 0 行 → 400。落库归属应为并发方
        (order_id=并发方订单), 本请求不得改写 discount_amount。
        """
        from tests.api._helpers import create_coupon
        cid = create_coupon(client, face_value=10.0, min_order_amount=0)
        code = "CPN-RACE-000001"
        _seed_usage(client._sesh, cid, user_id=101, code=code)
        oid_mine = _seed_order(client._sesh, user_id=101)
        oid_rival = _seed_order(client._sesh, user_id=101)

        session = client._sesh
        orig_execute = type(session).execute
        fired = {"on": True}

        def racing_execute(self, statement, *args, **kwargs):
            if (
                fired["on"]
                and isinstance(statement, Update)
                and statement.table.name == "coupon_usages"
            ):
                fired["on"] = False
                # SAEnum 按枚举 name 存储 ('USED'), DateTime 列为 naive 形态 ——
                # 裸 SQL 注入须与 ORM 写入形态一致, 否则端点 refresh 读回即炸
                naive_now = datetime.now(timezone.utc).replace(tzinfo=None)
                conn = self.get_bind().connect()
                try:
                    conn.execute(
                        text(
                            "UPDATE coupon_usages SET status='USED', order_id=:o,"
                            " discount_amount=1.11, used_at=:t"
                            " WHERE coupon_code=:c"
                        ),
                        {"o": oid_rival, "t": naive_now, "c": code},
                    )
                    conn.commit()
                finally:
                    conn.close()
            return orig_execute(self, statement, *args, **kwargs)

        with patch.object(type(session), "execute", racing_execute):
            r = client.post("/api/v1/operate/coupon/redeem", json={
                "coupon_code": code, "order_id": oid_mine, "order_amount": 100,
            })

        assert r.status_code == 400, r.text
        assert "优惠券状态" in r.json()["detail"], r.text
        assert "used" in r.json()["detail"], r.text
        # 落库归属为并发方: 本请求未覆盖 discount_amount/order_id/used_at
        session.expire_all()
        u = session.query(CouponUsage).filter(
            CouponUsage.coupon_code == code).first()
        assert u.status == CouponStatus.USED
        assert u.order_id == oid_rival
        assert float(u.discount_amount) == 1.11

    def test_redeem_race_first_write_still_wins(self, client):
        """无并发竞争时 CAS 正路径不受影响: 本请求自己的 UPDATE 落库, 200 核销成功."""
        from tests.api._helpers import create_coupon
        cid = create_coupon(client, face_value=10.0, min_order_amount=0)
        code = "CPN-RACE-000002"
        _seed_usage(client._sesh, cid, user_id=101, code=code)
        oid = _seed_order(client._sesh, user_id=101)

        r = client.post("/api/v1/operate/coupon/redeem", json={
            "coupon_code": code, "order_id": oid, "order_amount": 100,
        })
        assert r.status_code == 200, r.text
        assert r.json()["data"]["discount_amount"] == 10.0
        u = client._sesh.query(CouponUsage).filter(
            CouponUsage.coupon_code == code).first()
        assert u.status == CouponStatus.USED
        assert u.order_id == oid
