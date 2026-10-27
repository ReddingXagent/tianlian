"""C端优惠券领取并发超领竞态测试 — 卡 6e698559

缺陷 (check-then-act, 与卡 674bb77e 同族): claim() 的 per_user_limit 检查
(统计 status=ACTIVE 的 CouponUsage 条数) 与随后的 insert 之间无原子性。
并发双击时两个请求都通过检查 → 同一用户领到超过 per_user_limit 张券
(营销资产超发)。库存维度已有 CAS 扣减防护, 限领维度没有。

测试手法 (卡 d74344ed / test_coupon_distribute_race 同构, 确定性触发,
无 sleep/线程): 拦截 claim 内首个 CouponUsage COUNT 查询, 在其命中 DB 前
用独立连接把「并发方已提交的 ACTIVE 领取记录」插入 —— 模拟并发请求先行
落库。此时本请求尚未持任何写锁, 独立连接可写; 之后的复检若在取得写锁后
重查, 必然看到该行 → 409, 不再 insert。

注意: 不能用 (coupon_id, user_id) 全局唯一约束修复 —— per_user_limit 语义
是「同时持有 ACTIVE ≤ N」, 券 USED/EXPIRED 后须允许再领。回归用例覆盖之。

修复契约:
- PG: with_for_update() 行锁串行化同券领取, check 与 act 同临界区
- SQLite: 锁 no-op, 由库存 CAS 取得 RESERVED 写锁后的二次复检兜底
- 终态不变式: 单用户 ACTIVE 条数 ≤ per_user_limit, 库存扣减数 == 成功条数
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

from sqlalchemy import text

from app.models.coupon import Coupon, CouponStatus, CouponType, CouponUsage
from app.models.end_user import EndUser

AUTH_URL = "/api/v1/business/auth/wx-login"
BASE = "/api/v1/coupons"


def _login(client, code):
    r = client.post(AUTH_URL, json={"code": code})
    assert r.status_code == 200, r.text
    return r.json()["data"]["token"]


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _end_user(client, code):
    openid = "mock_" + __import__("hashlib").sha1(code.encode()).hexdigest()[:16]
    return client._sesh.query(EndUser).filter(EndUser.wx_openid == openid).one()


def _seed_coupon(session, *, per_user_limit=1, total_stock=100):
    now = datetime.now(timezone.utc)
    c = Coupon(
        name="限领竞态券",
        coupon_type=CouponType.FIXED,
        face_value=Decimal("10"),
        min_order_amount=Decimal("0"),
        total_stock=total_stock,
        remaining_stock=total_stock,
        per_user_limit=per_user_limit,
        valid_days=30,
        start_time=now - timedelta(days=1),
        end_time=now + timedelta(days=30),
        is_active=True,
    )
    session.add(c)
    session.commit()
    session.refresh(c)
    return c


def _active_count(session, coupon_id, user_id):
    session.expire_all()
    return (
        session.query(CouponUsage)
        .filter(
            CouponUsage.coupon_id == coupon_id,
            CouponUsage.user_id == user_id,
            CouponUsage.status == CouponStatus.ACTIVE,
        )
        .count()
    )


class TestClaimPerUserLimitRace:
    """POST /coupons/claim — per_user_limit check-then-act 竞态"""

    def _rival_claims(self, client, coupon_id, user_id):
        """拦截首个 CouponUsage COUNT 查询, 命中 DB 前由独立连接插入并发方
        已提交的 ACTIVE 领取记录 (模拟并发请求先落库, 此时本请求无写锁)。"""
        session = client._sesh
        orig_query = type(session).query
        fired = {"on": True}

        def racing_query(self, *entities, **kw):
            if fired["on"] and entities and entities[0] is CouponUsage:
                fired["on"] = False
                conn = self.get_bind().connect()
                try:
                    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                    conn.execute(
                        text(
                            "INSERT INTO coupon_usages "
                            "(coupon_id, user_id, user_type, coupon_code, status, "
                            " expires_at, received_at, created_at) VALUES "
                            "(:c, :u, 'end_user', :code, 'ACTIVE', :exp, :now, :now)"
                        ),
                        {
                            "c": coupon_id,
                            "u": user_id,
                            "code": "CPN-RIVAL000001",
                            "exp": now,
                            "now": now,
                        },
                    )
                    conn.commit()
                finally:
                    conn.close()
            return orig_query(self, *entities, **kw)

        return patch.object(type(session), "query", racing_query)

    def test_claim_race_no_over_claim(self, client):
        """per_user_limit=1, 并发方已领 1 张: 本请求须 409 LIMIT_REACHED,
        不得再 insert → 终态 ACTIVE 条数仍为 1 (不超领)。"""
        c = _seed_coupon(client._sesh, per_user_limit=1, total_stock=10)
        token = _login(client, "cpn-race-1")
        eu = _end_user(client, "cpn-race-1")

        with self._rival_claims(client, c.id, eu.id):
            r = client.post(f"{BASE}/claim", json={"coupon_id": c.id},
                            headers=_headers(token))

        assert r.status_code == 409, r.text
        assert r.json()["detail"] == "COUPON_LIMIT_REACHED"
        assert _active_count(client._sesh, c.id, eu.id) == 1, "并发下不得超领"
        # 被拒请求不得扣库存: 10 - 0 (并发方插入未扣) = 10
        client._sesh.refresh(c)
        assert c.remaining_stock == 10, "409 拒绝后库存须回滚"

    def test_claim_race_stock_and_limit_consistent(self, client):
        """终态不变式: 库存扣减数 == 成功领取数。被 409 拒绝的请求不扣库存、
        零落库。per_user_limit=2 + 已成功领 1: 并发脚手架再插 1 张 ACTIVE 后,
        本次 claim 无论命中首检还是 CAS 后复检, 都须 409 且库存回滚。"""
        c = _seed_coupon(client._sesh, per_user_limit=2, total_stock=10)
        token = _login(client, "cpn-race-2")
        eu = _end_user(client, "cpn-race-2")

        # 第一次成功 (ACTIVE=1, 库存 10→9)
        r1 = client.post(f"{BASE}/claim", json={"coupon_id": c.id},
                         headers=_headers(token))
        assert r1.status_code == 200, r1.text
        # 第二次并发 (脚手架模拟并发方直插 1 张已提交 ACTIVE) → 409
        with self._rival_claims(client, c.id, eu.id):
            r2 = client.post(f"{BASE}/claim", json={"coupon_id": c.id},
                             headers=_headers(token))
        assert r2.status_code == 409
        assert r2.json()["detail"] == "COUPON_LIMIT_REACHED"
        client._sesh.refresh(c)
        # 库存只被成功的 r1 扣 1 次; r2 的 CAS 扣减须已回滚
        assert c.remaining_stock == 9
        # ACTIVE=2 = 首领 1 + 并发脚手架直插 1 (直插不走 API, 不受其限领约束)
        assert _active_count(client._sesh, c.id, eu.id) == 2
        # r2 自身零落库: API 产出的 ACTIVE 行 (排除脚手架码) 仅首领 1 张
        api_rows = (
            client._sesh.query(CouponUsage)
            .filter(
                CouponUsage.coupon_id == c.id,
                CouponUsage.user_id == eu.id,
                CouponUsage.status == CouponStatus.ACTIVE,
                CouponUsage.coupon_code != "CPN-RIVAL000001",
            )
            .count()
        )
        assert api_rows == 1, "被 409 拒绝的请求不得落库"

    def test_claim_sequential_limit_enforced(self, client):
        """顺序路径回归: per_user_limit=1, 二次 claim → 409 LIMIT_REACHED。"""
        c = _seed_coupon(client._sesh, per_user_limit=1, total_stock=10)
        token = _login(client, "cpn-race-seq")
        eu = _end_user(client, "cpn-race-seq")
        r1 = client.post(f"{BASE}/claim", json={"coupon_id": c.id},
                         headers=_headers(token))
        assert r1.status_code == 200
        r2 = client.post(f"{BASE}/claim", json={"coupon_id": c.id},
                         headers=_headers(token))
        assert r2.status_code == 409
        assert r2.json()["detail"] == "COUPON_LIMIT_REACHED"
        assert _active_count(client._sesh, c.id, eu.id) == 1

    def test_claim_after_expired_can_reclaim(self, client):
        """用完(EXPIRED)后可再领 — 证明修复未引入 (coupon_id,user_id) 全局
        唯一约束挡住「用完再领」(per_user_limit 语义 = 同时持有 ACTIVE ≤ N)。"""
        c = _seed_coupon(client._sesh, per_user_limit=1, total_stock=10)
        token = _login(client, "cpn-race-re")
        eu = _end_user(client, "cpn-race-re")
        r1 = client.post(f"{BASE}/claim", json={"coupon_id": c.id},
                         headers=_headers(token))
        assert r1.status_code == 200, r1.text

        # 首领的券过期
        usage = (
            client._sesh.query(CouponUsage)
            .filter(CouponUsage.coupon_id == c.id, CouponUsage.user_id == eu.id)
            .one()
        )
        usage.status = CouponStatus.EXPIRED
        client._sesh.commit()

        r2 = client.post(f"{BASE}/claim", json={"coupon_id": c.id},
                         headers=_headers(token))
        assert r2.status_code == 200, r2.text
        assert _active_count(client._sesh, c.id, eu.id) == 1
        client._sesh.refresh(c)
        assert c.remaining_stock == 8
