"""
优惠券管理 API 专属测试（补缺） — 工作卡 0044a439

既有覆盖盘点（本文件不重复，只补真实缺口）:
- tests/api/test_coupon_api.py        stats/usages/batches/distribute/redeem/update/delete 主路径 + viewer 403
- tests/api/test_coupon_window.py     发放窗口 enforcement + usages 过期派生 (卡 73d52e60)
- tests/api/test_coupon_leftovers.py  update 窗口校验 + per_user_limit + 统计派生 (卡 ea373b3a)
- tests/api/test_coupon_redeem_order_guard.py  redeem 订单归属 (卡 5f7fa7ba)
- tests/test_operate_coupon.py        CRUD/发放/核销/参数校验全链

本文件补:
1. 写端点权限矩阵 — 5 个写端点(create/distribute/redeem/update/delete) ×
   3 个非平台角色(viewer/operator/engineer) 全量 403（既有仅散测 viewer 3 端点）
2. team 隔离 — usages 按 user→team 过滤下的跨 team user_id 探测（读侧越权）；
   券本体/批次为平台级配置（coupon_api.py 内注释明示的设计决策），读端点
   对非 admin 开放属预期行为，本文件固化该语义而非测反
3. 核销状态机 — DISABLED / DB 已 EXPIRED（非懒检查路径）的拒绝与拒绝文案区分
4. stats 精确数值链 — 创建→发放→核销后的全字段精确断言（既有仅 >=）
5. usages 分页 — page/page_size 截断与页间不重叠（既有缺失）
6. 校验边界 — name 长度上下界 / face_value=0 与上限内大额 / update 侧数值校验
7. 窗口外发放 + per_user_limit 超限（任务卡要求本文件自包含，各 1 条代表性用例，
   全量见 test_coupon_window.py / test_coupon_leftovers.py）
"""
import uuid
from datetime import datetime, timedelta, timezone

from app.models.charging_order import ChargingOrder
from app.models.coupon import Coupon, CouponUsage, CouponStatus
from app.models.user import User, UserRole
from tests.api._helpers import COUPON_URL, coupon_window, create_coupon, login_as


# ── seeds ──

def _seed_order(session, user_id=101):
    """插一条最小 ChargingOrder（卡 5f7fa7ba 后 redeem 须真实订单），返回 id"""
    o = ChargingOrder(
        order_no=f"TL{uuid.uuid4().hex[:14].upper()}",
        station_id=1, device_id=1, user_id=user_id,
    )
    session.add(o)
    session.commit()
    session.refresh(o)
    return o.id


def _seed_usage(session, coupon_id, *, user_id=101, status=CouponStatus.ACTIVE,
                code="CPN-API-DEFAULT1", expires_delta_days=30):
    """直插一条 CouponUsage，user_id/expires 可指定（覆盖 DB 预置状态场景）"""
    u = CouponUsage(
        coupon_id=coupon_id, user_id=user_id, user_type="app",
        coupon_code=code, status=status,
        expires_at=datetime.now(timezone.utc) + timedelta(days=expires_delta_days),
    )
    session.add(u)
    session.commit()
    return u


def _distribute(client, coupon_id, quantity=1, user_ids="1", **extra):
    body = {"coupon_id": coupon_id, "quantity": quantity, "user_ids": user_ids}
    body.update(extra)
    return client.post(f"{COUPON_URL}/distribute", json=body)


def _redeem(client, code, order_id, order_amount=100.0):
    return client.post(f"{COUPON_URL}/redeem", json={
        "coupon_code": code, "order_id": order_id, "order_amount": order_amount,
    })


def _seed_user(session, username, role, team_id=None):
    """造一个指定角色/team 的用户并返回（绕开 seed_users 固定角色集）"""
    from tests._test_helpers import _fast_hash
    u = User(
        username=username, password_hash=_fast_hash("pass123"),
        role=role, status="active", team_id=team_id,
    )
    session.add(u)
    session.commit()
    session.refresh(u)
    return u


# ── 1. 写端点权限矩阵 ──

class TestWriteEndpointPermissionMatrix:
    """5 个写端点经 require_platform_admin 收紧，任何非平台角色 → 403。

    既有覆盖仅 viewer × (distribute/redeem/update) 三点；此处全矩阵补齐
    create/delete 及 operator/engineer 角色（防未来把依赖从某个端点上摘掉）。
    """

    NON_ADMIN_ROLES = [
        ("viewer1", "view123", UserRole.VIEWER),
        ("engineer1", "eng123", UserRole.ENGINEER),
    ]

    def test_create_forbidden_all_non_admin_roles(self, client, seed_users):
        payload = {
            "name": "越权创建券", "face_value": 10, "total_stock": 10,
            "start_time": coupon_window()[0], "end_time": coupon_window()[1],
        }
        for username, password, _role in self.NON_ADMIN_ROLES:
            login_as(client, username, password)
            r = client.post(COUPON_URL, json=payload)
            assert r.status_code == 403, f"{username} 创建应 403, 实际 {r.status_code}"
        # 切回 admin 可创建（对照组，证明 403 来自角色而非 payload）
        login_as(client, "admin", "admin123")
        assert client.post(COUPON_URL, json=payload).status_code == 200

    def test_delete_forbidden_for_viewer(self, client, seed_users):
        cid = create_coupon(client)
        login_as(client, "viewer1", "view123")
        r = client.delete(f"{COUPON_URL}/{cid}")
        assert r.status_code == 403
        # 券未被删
        assert client._sesh.query(Coupon).get(cid) is not None

    def test_operator_cannot_write_any_coupon_endpoint(self, client):
        """operator（运维操作员，持站控权限但非平台角色）对券写端点全 403"""
        op = _seed_user(client._sesh, "op_probe", UserRole.OPERATOR)
        cid = create_coupon(client)
        login_as(client, "op_probe", "pass123")
        assert client.post(COUPON_URL, json={
            "name": "x", "face_value": 1, "total_stock": 1,
            "start_time": coupon_window()[0], "end_time": coupon_window()[1],
        }).status_code == 403
        assert _distribute(client, cid).status_code == 403
        assert client.put(f"{COUPON_URL}/{cid}", json={"name": "x"}).status_code == 403
        assert client.delete(f"{COUPON_URL}/{cid}").status_code == 403
        # redeem 拒绝时不动 DB（无券可查，仅验 403 在鉴权层短路）
        assert _redeem(client, "CPN-NONE", order_id=1).status_code == 403


# ── 2. team 隔离 ──

class TestTeamIsolation:
    """usages 按领取用户归属过滤（卡 ab5c5f17）；券本体/批次为平台级配置。

    设计边界（既有决策，固化语义）: Coupon/CouponBatch 无 team 归属，list/detail/
    stats/batches 对非 admin 开放读；跨 team 数据隔离只作用于 usages 维度。
    """

    def test_usages_cross_team_user_id_probe_returns_empty(self, client, db_session, seed_users):
        """A team 用户以 user_id 参数探测 B team 用户领券记录 → 空（读侧越权）"""
        cid = create_coupon(client)
        eng = seed_users["engineer1"]
        viewer = seed_users["viewer1"]
        eng.team_id = 5
        viewer.team_id = 999
        db_session.commit()
        # 券发给 B team viewer
        _seed_usage(db_session, cid, user_id=viewer.id, code="CPN-XTEAM-PROBE")
        login_as(client, "engineer1", "eng123")

        r = client.get(f"{COUPON_URL}/usages", params={"user_id": viewer.id})
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["total"] == 0
        assert data["items"] == []
        codes = [i["coupon_code"] for i in data["items"]]
        assert "CPN-XTEAM-PROBE" not in codes

    def test_usages_own_team_records_visible(self, client, db_session, seed_users):
        """同 team 用户的领券记录正常可见（隔离不误伤）"""
        cid = create_coupon(client)
        eng = seed_users["engineer1"]
        viewer = seed_users["viewer1"]
        eng.team_id = 5
        viewer.team_id = 5
        db_session.commit()
        _seed_usage(db_session, cid, user_id=viewer.id, code="CPN-TEAM5-001")
        login_as(client, "engineer1", "eng123")
        r = client.get(f"{COUPON_URL}/usages")
        codes = [i["coupon_code"] for i in r.json()["data"]["items"]]
        assert "CPN-TEAM5-001" in codes

    def test_coupon_read_endpoints_platform_level_for_non_admin(self, client, seed_users):
        """券本体/批次/统计为平台级配置: 非 admin 读 200（既有设计，固化语义）"""
        cid = create_coupon(client, total_stock=10)
        assert _distribute(client, cid, quantity=1, user_ids="1").status_code == 200
        login_as(client, "viewer1", "view123")
        assert client.get(COUPON_URL).status_code == 200
        assert client.get(f"{COUPON_URL}/{cid}").status_code == 200
        assert client.get(f"{COUPON_URL}/stats").status_code == 200
        assert client.get(f"{COUPON_URL}/batches").status_code == 200


# ── 3. 核销状态机 ──

class TestRedeemStateMachine:
    """CouponUsage 状态机: 仅 ACTIVE 可核销；非 ACTIVE 一律 400 且文案带状态。

    与懒检查路径区分: DB 已是 EXPIRED（expires_at 未到）→ "状态" 文案；
    DB 是 ACTIVE 但 expires_at 已过 → 懒翻转为 EXPIRED + "过期" 文案
    （后者既有覆盖，见 test_operate_coupon.test_redeem_expired_coupon_flips_to_expired）。
    """

    def test_redeem_disabled_rejected(self, client):
        """DISABLED 券 → 400，状态不被改写"""
        cid = create_coupon(client, min_order_amount=0)
        _seed_usage(client._sesh, cid, code="CPN-DIS-000001", status=CouponStatus.DISABLED)
        oid = _seed_order(client._sesh)
        r = _redeem(client, "CPN-DIS-000001", oid)
        assert r.status_code == 400
        assert "disabled" in r.json()["detail"]
        u = client._sesh.query(CouponUsage).filter(
            CouponUsage.coupon_code == "CPN-DIS-000001").first()
        assert u.status == CouponStatus.DISABLED
        assert u.order_id is None

    def test_redeem_db_expired_but_not_past_expiry_rejected_as_state(self, client):
        """DB 已 EXPIRED 但 expires_at 未到（人工翻转/补偿场景）→ 400 状态拒绝，
        不走懒检查翻转分支（status != ACTIVE 先短路）"""
        cid = create_coupon(client, min_order_amount=0)
        _seed_usage(client._sesh, cid, code="CPN-DBEXP-00001",
                    status=CouponStatus.EXPIRED, expires_delta_days=30)
        oid = _seed_order(client._sesh)
        r = _redeem(client, "CPN-DBEXP-00001", oid)
        assert r.status_code == 400
        assert "expired" in r.json()["detail"]
        assert "过期" not in r.json()["detail"]  # 状态文案而非懒检查文案

    def test_usages_disabled_status_passthrough(self, client):
        """DISABLED 状态在 usages 列表原样显示（无派生改写）"""
        cid = create_coupon(client)
        _seed_usage(client._sesh, cid, code="CPN-DIS-LIST001", status=CouponStatus.DISABLED)
        items = client.get(f"{COUPON_URL}/usages").json()["data"]["items"]
        target = next(i for i in items if i["coupon_code"] == "CPN-DIS-LIST001")
        assert target["status"] == "disabled"


# ── 4. stats 精确数值链 ──

class TestStatsExactValues:
    """创建→发放→核销全链后 stats 各字段精确断言（既有测试仅 >= 断言）。

    前置: 模板 DB 的 coupons/coupon_usages 表为空（conftest 仅 seed RBAC+admin），
    故可精确断言。usage_rate = used/distributed*100 四舍五入 1 位: 1/3 → 33.3。
    """

    def test_stats_exact_after_full_lifecycle(self, client):
        # per_user_limit=0: 3 张分给 3 个用户，避开限领整批拒绝（与 stats 语义无关）
        cid = create_coupon(client, total_stock=100, face_value=15.0,
                            min_order_amount=0, per_user_limit=0)
        r = _distribute(client, cid, quantity=3, user_ids="101,102,103")
        assert r.status_code == 200
        code = r.json()["data"]["codes"][0]
        oid = _seed_order(client._sesh, user_id=101)
        assert _redeem(client, code, oid, order_amount=100.0).status_code == 200

        data = client.get(f"{COUPON_URL}/stats").json()["data"]
        assert data["total_coupons"] == 1
        assert data["total_stock"] == 100
        assert data["remaining_stock"] == 97
        assert data["total_distributed"] == 3
        assert data["total_used"] == 1
        assert data["usage_rate"] == 33.3
        assert data["total_discount_amount"] == 15.0

    def test_stats_usage_rate_zero_when_no_distribution(self, client):
        """只建券不发 → usage_rate=0（除零保护），total_discount=0.0"""
        create_coupon(client)
        data = client.get(f"{COUPON_URL}/stats").json()["data"]
        assert data["total_distributed"] == 0
        assert data["usage_rate"] == 0
        assert data["total_discount_amount"] == 0.0

    def test_stats_discount_only_counts_used(self, client):
        """discount_amount 仅统计 USED：未核销 ACTIVE 券不计入"""
        cid = create_coupon(client, face_value=10.0, min_order_amount=0)
        _seed_usage(client._sesh, cid, code="CPN-STAT-ACTIVE")  # ACTIVE 不计
        data = client.get(f"{COUPON_URL}/stats").json()["data"]
        assert data["total_distributed"] == 1
        assert data["total_used"] == 0
        assert data["total_discount_amount"] == 0.0


# ── 5. usages 分页 ──

class TestUsagesPagination:
    """page/page_size 截断与页间不重叠（既有缺失）"""

    def test_usages_page_size_truncates_and_pages_disjoint(self, client):
        cid = create_coupon(client)
        for i in range(3):
            _seed_usage(client._sesh, cid, code=f"CPN-PAGE-{i:04d}")
        page1 = client.get(f"{COUPON_URL}/usages", params={"page_size": 2}).json()["data"]
        assert page1["total"] == 3
        assert len(page1["items"]) == 2
        page2 = client.get(f"{COUPON_URL}/usages", params={"page_size": 2, "page": 2}).json()["data"]
        assert len(page2["items"]) == 1
        ids1 = {i["id"] for i in page1["items"]}
        ids2 = {i["id"] for i in page2["items"]}
        assert ids1.isdisjoint(ids2)
        assert ids1 | ids2 == {i.id for i in client._sesh.query(CouponUsage).all()}

    def test_usages_page_ge_1_validated(self, client):
        r = client.get(f"{COUPON_URL}/usages", params={"page": 0})
        assert r.status_code == 422

    def test_usages_page_size_upper_bound(self, client):
        r = client.get(f"{COUPON_URL}/usages", params={"page_size": 101})
        assert r.status_code == 422


# ── 6. 校验边界 ──

class TestValidationBoundaries:
    """入参边界: 既有测过 name 空串/负面额/负库存/非法类型/缺时间，此处补长度上界、
    零值合法、Numeric(10,2) 上限内大额、update 侧数值约束。"""

    def test_create_name_over_100_chars_rejected(self, client):
        r = client.post(COUPON_URL, json={
            "name": "长" * 101, "face_value": 10, "total_stock": 10,
            "start_time": coupon_window()[0], "end_time": coupon_window()[1],
        })
        assert r.status_code == 422

    def test_create_zero_face_value_accepted(self, client):
        """face_value=0 合法（免费权益类券/免服务费券语义）"""
        cid = create_coupon(client, face_value=0)
        obj = client._sesh.query(Coupon).get(cid)
        assert float(obj.face_value) == 0.0

    def test_create_face_value_within_numeric_precision(self, client):
        """99999999.99 = Numeric(10,2) 上限内，落库读回无损"""
        cid = create_coupon(client, face_value=99999999.99)
        obj = client._sesh.query(Coupon).get(cid)
        assert float(obj.face_value) == 99999999.99

    def test_update_negative_face_value_rejected(self, client):
        """CouponUpdate.face_value ge=0: update 侧负数 → 422（既有只测 create 侧）"""
        cid = create_coupon(client)
        r = client.put(f"{COUPON_URL}/{cid}", json={"face_value": -5})
        assert r.status_code == 422

    def test_update_negative_stock_rejected(self, client):
        cid = create_coupon(client)
        r = client.put(f"{COUPON_URL}/{cid}", json={"total_stock": -1})
        assert r.status_code == 422


# ── 7. 窗口/限领代表性用例（自包含；全量见 test_coupon_window / test_coupon_leftovers）──

class TestDistributeWindowAndLimitRepresentative:
    def test_distribute_outside_window_rejected(self, client):
        """窗口外（已结束）→ 400 且库存/记录零落库"""
        _, past_end = coupon_window(start=-20, end=-10)
        cid = create_coupon(client, start_time=coupon_window(start=-30, end=-20)[0],
                            end_time=past_end)
        r = _distribute(client, cid)
        assert r.status_code == 400
        assert client._sesh.query(CouponUsage).filter(CouponUsage.coupon_id == cid).count() == 0
        assert client._sesh.query(Coupon).get(cid).remaining_stock == 100

    def test_distribute_exceeding_per_user_limit_rejected(self, client):
        """limit=1 第二次领取 → 400 整批拒绝"""
        cid = create_coupon(client, per_user_limit=1)
        assert _distribute(client, cid, quantity=1, user_ids="77").status_code == 200
        r = _distribute(client, cid, quantity=1, user_ids="77")
        assert r.status_code == 400
        assert "限领" in r.json()["detail"]
        assert client._sesh.query(CouponUsage).filter(
            CouponUsage.coupon_id == cid).count() == 1


# ── 8. 探明的缺陷（修复验证用例，卡 0044a439）──

class TestDefectFixes:
    """缺陷1: list ?coupon_type=fixed 过滤失配 — Coupon.coupon_type 列为
    SAEnum(CouponType) 存 name(FIXED)，查询以裸 str value(fixed) 比较恒不命中
    （既有 test_coupon_api.test_list_coupons_filter_by_type_returns_200 docstring
    已记录只敢断 200）。修复: 比较前转 CouponType 成员。

    缺陷2: redeem order_amount 无符号约束 — 负订单金额在 FREE_CHARGE 券下
    discount=负数原样落库（负抵扣），PERCENTAGE 券同理。修复: ge=0。

    附: coupon_type 过滤曾疑为失配缺陷，实测（SQLAlchemy str-enum bind 按
    value 命中）精确过滤正常——旧注释"已知问题"过时，此处固化为精确断言。
    """

    def test_list_filter_by_coupon_type_value_hits(self, client):
        """?coupon_type=fixed（value 口径，与创建入参一致）→ 精确命中"""
        create_coupon(client, coupon_type="fixed", name="固定券A")
        create_coupon(client, coupon_type="percentage", face_value=0.5, name="折扣券B")
        data = client.get(f"{COUPON_URL}", params={"coupon_type": "fixed"}).json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["name"] == "固定券A"

    def test_redeem_negative_order_amount_rejected(self, client):
        """order_amount=-100 → 422，券不被核销（负抵扣禁止）"""
        cid = create_coupon(client, coupon_type="free_charge", face_value=0, min_order_amount=0)
        _seed_usage(client._sesh, cid, code="CPN-NEG-000001")
        oid = _seed_order(client._sesh)
        r = _redeem(client, "CPN-NEG-000001", oid, order_amount=-100.0)
        assert r.status_code == 422
        u = client._sesh.query(CouponUsage).filter(
            CouponUsage.coupon_code == "CPN-NEG-000001").first()
        assert u.status == CouponStatus.ACTIVE
        assert u.discount_amount is None or float(u.discount_amount) >= 0
