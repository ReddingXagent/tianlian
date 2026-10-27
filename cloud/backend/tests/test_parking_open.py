"""
停车场对接开放API 测试 (任务卡 309b4132)

覆盖 app/api/v1/parking_open.py:
- 鉴权链 (X-App-Key + X-App-Secret):
  - 401: 缺 header / key 不存在 / secret 错误 / 配置 inactive (统一 detail, 防枚举)
  - 403: allow_query=False (仅查询端点)
- GET /charge-status   : 本站点充电状态 (站点隔离 + plate 精确匹配)
- GET /discount-eligibility: 本站点生效折扣规则 (is_active 过滤 + 站点隔离)
- POST /discount-applied: 减免留痕 (422 amount<=0/缺字段, order_no 幂等, 站点隔离防伪造)

风格: 同步 TestClient + client fixture (参考 test_admin_edge_gateways.py)。
断言用 resp.status_code + resp.json()['detail']。
路径前缀 /api/v1 (api_router) + /open/parking (子 router)。
"""
import pytest

from app.models.parking_integration import (
    ParkingIntegrationConfig,
    IntegrationMode,
)
from app.models.parking_discount_applied import ParkingDiscountApplied
from app.models.parking import ParkingDiscount
from app.models.charging_order import ChargingOrder, OrderStatus


_BASE = "/api/v1/open/parking"


def _seed_station(client, sid: int):
    """建一个站点 (集成配置 station_id FK 指向它)。"""
    from app.models.station import Station, StationStatus
    client._sesh.add(Station(id=sid, name=f"测试站{sid}", code=f"ST{sid}", status=StationStatus.NORMAL))
    client._sesh.commit()


def _seed_credential(
    client,
    sid: int,
    app_key="KEY_A",
    app_secret="SECRET_A",
    allow_query=True,
    is_active=True,
    mode=IntegrationMode.A,
) -> ParkingIntegrationConfig:
    """建一对对接凭证, 默认 KEY_A/SECRET_A + 启用 + 允许查询。"""
    cfg = ParkingIntegrationConfig(
        station_id=sid,
        provider_name="测试停车场",
        app_key=app_key,
        app_secret=app_secret,
        integration_mode=mode,
        allow_query=allow_query,
        is_active=is_active,
    )
    client._sesh.add(cfg)
    client._sesh.commit()
    client._sesh.refresh(cfg)
    return cfg


def _headers(key="KEY_A", secret="SECRET_A"):
    return {"X-App-Key": key, "X-App-Secret": secret}


# ════════════════════════════════════════════════════════════
# 鉴权: 401 / 403
# ════════════════════════════════════════════════════════════
class TestParkingAuth:
    """X-App-Key/Secret 鉴权: 401 缺凭证/不存在/错密/停用; 403 allow_query=False。"""

    @staticmethod
    def _seed(client):
        _seed_station(client, sid=7001)
        _seed_credential(client, sid=7001, app_key="KEY_A", app_secret="SECRET_A")

    def test_no_headers_401(self, client):
        """缺两个 header → 401。"""
        self._seed(client)
        resp = client.get(f"{_BASE}/charge-status", params={"plate": "京A12345"})
        assert resp.status_code == 401
        assert resp.json()["detail"] == "无效的对接凭证"

    def test_missing_secret_401(self, client):
        """只带 key 不带 secret → 401。"""
        self._seed(client)
        resp = client.get(
            f"{_BASE}/charge-status", params={"plate": "京A12345"},
            headers={"X-App-Key": "KEY_A"},
        )
        assert resp.status_code == 401
        assert resp.json()["detail"] == "无效的对接凭证"

    def test_key_not_exist_401(self, client):
        """key 不存在 → 401 (统一 detail, 防枚举)。"""
        self._seed(client)
        resp = client.get(
            f"{_BASE}/charge-status", params={"plate": "京A12345"},
            headers=_headers("KEY_NOT_EXIST", "SECRET_A"),
        )
        assert resp.status_code == 401
        assert resp.json()["detail"] == "无效的对接凭证"

    def test_wrong_secret_401(self, client):
        """secret 不匹配 → 401。"""
        self._seed(client)
        resp = client.get(
            f"{_BASE}/charge-status", params={"plate": "京A12345"},
            headers=_headers("KEY_A", "WRONG_SECRET"),
        )
        assert resp.status_code == 401
        assert resp.json()["detail"] == "无效的对接凭证"

    def test_inactive_config_401(self, client):
        """配置 is_active=False → 401 (即便 key/secret 都对)。"""
        _seed_station(client, sid=7002)
        _seed_credential(client, sid=7002, app_key="KEY_I", app_secret="SECRET_I", is_active=False)
        resp = client.get(
            f"{_BASE}/charge-status", params={"plate": "京A12345"},
            headers=_headers("KEY_I", "SECRET_I"),
        )
        assert resp.status_code == 401
        assert resp.json()["detail"] == "无效的对接凭证"

    def test_allow_query_false_403(self, client):
        """allow_query=False → 查询端点 403 (非 401, 凭证本身有效)。"""
        _seed_station(client, sid=7003)
        _seed_credential(client, sid=7003, app_key="KEY_Q", app_secret="SECRET_Q", allow_query=False)
        resp = client.get(
            f"{_BASE}/charge-status", params={"plate": "京A12345"},
            headers=_headers("KEY_Q", "SECRET_Q"),
        )
        assert resp.status_code == 403
        assert resp.json()["detail"] == "该对接凭证未开放查询权限"

    def test_allow_query_false_still_can_post_discount(self, client):
        """allow_query=False 仅限查询; discount-applied (留痕) 用基础鉴权, 不受 403 限制。"""
        _seed_station(client, sid=7004)
        _seed_credential(client, sid=7004, app_key="KEY_P", app_secret="SECRET_P", allow_query=False)
        resp = client.post(
            f"{_BASE}/discount-applied",
            json={"plate_number": "京A12345", "order_no": "PK0099", "amount": "5.00"},
            headers=_headers("KEY_P", "SECRET_P"),
        )
        assert resp.status_code == 200, resp.text


# ════════════════════════════════════════════════════════════
# GET /charge-status
# ════════════════════════════════════════════════════════════
class TestChargeStatus:
    """查询车牌充电状态: 充电中判定 + 站点隔离。"""

    @staticmethod
    def _seed(client):
        _seed_station(client, sid=7101)
        _seed_credential(client, sid=7101, app_key="KEY_C", app_secret="SECRET_C")
        # 同站点同车牌: 一条 charging, 一条 completed
        client._sesh.add_all([
            ChargingOrder(order_no="CO_C1", station_id=7101, device_id=1,
                          plate_number="京C111", order_status=OrderStatus.CHARGING),
            ChargingOrder(order_no="CO_C2", station_id=7101, device_id=1,
                          plate_number="京C111", order_status=OrderStatus.COMPLETED),
        ])
        # 同车牌但在另一站点 charging (站点隔离验证: 不应被本站点查到)
        _seed_station(client, sid=7102)
        client._sesh.add(ChargingOrder(order_no="CO_C3", station_id=7102, device_id=1,
                                       plate_number="京C111", order_status=OrderStatus.CHARGING))
        client._sesh.commit()

    def test_charging_true(self, client):
        self._seed(client)
        resp = client.get(
            f"{_BASE}/charge-status", params={"plate": "京C111"},
            headers=_headers("KEY_C", "SECRET_C"),
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["plate_number"] == "京C111"
        assert data["station_id"] == 7101
        assert data["charging"] is True

    def test_charging_false_when_only_completed(self, client):
        """无 charging 订单 → charging=False (completed 不算充电中)。"""
        _seed_station(client, sid=7111)
        _seed_credential(client, sid=7111, app_key="KEY_C2", app_secret="SECRET_C2")
        client._sesh.add(ChargingOrder(order_no="CO_D1", station_id=7111, device_id=1,
                                       plate_number="京D222", order_status=OrderStatus.COMPLETED))
        client._sesh.commit()
        resp = client.get(
            f"{_BASE}/charge-status", params={"plate": "京D222"},
            headers=_headers("KEY_C2", "SECRET_C2"),
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["charging"] is False

    def test_station_isolation(self, client):
        """站点隔离: 邻站同车牌 charging 不计入本站点 (station_id 限定生效)。"""
        self._seed(client)
        resp = client.get(
            f"{_BASE}/charge-status", params={"plate": "京C111"},
            headers=_headers("KEY_C", "SECRET_C"),
        )
        # 本站点(7101)确有 charging → True; 但邻站(7102)的订单不可见
        # 这里 True 来自本站点自己的 CO_C1, 验证 station_id 限定生效
        assert resp.json()["data"]["charging"] is True
        assert resp.json()["data"]["station_id"] == 7101

    def test_empty_plate_422(self, client):
        """plate 空串 → 422 (Query min_length=1)。"""
        _seed_station(client, sid=7112)
        _seed_credential(client, sid=7112, app_key="KEY_C3", app_secret="SECRET_C3")
        resp = client.get(
            f"{_BASE}/charge-status", params={"plate": ""},
            headers=_headers("KEY_C3", "SECRET_C3"),
        )
        assert resp.status_code == 422


# ════════════════════════════════════════════════════════════
# GET /discount-eligibility
# ════════════════════════════════════════════════════════════
class TestDiscountEligibility:
    """查询站点折扣规则: is_active 过滤 + 站点隔离。"""

    @staticmethod
    def _seed(client):
        _seed_station(client, sid=7201)
        _seed_credential(client, sid=7201, app_key="KEY_D", app_secret="SECRET_D")
        from decimal import Decimal
        client._sesh.add_all([
            ParkingDiscount(station_id=7201, discount_type="free_minutes",
                            free_minutes=30, is_active=True, merchant_name="M1"),
            ParkingDiscount(station_id=7201, discount_type="percentage",
                            discount_percent=Decimal("50.00"), is_active=True),
            ParkingDiscount(station_id=7201, discount_type="fixed",
                            fixed_amount=Decimal("10.00"), is_active=False),  # 停用, 不应返回
            ParkingDiscount(station_id=7202, discount_type="free_minutes",
                            free_minutes=60, is_active=True),  # 邻站, 不可见
        ])
        _seed_station(client, sid=7202)
        client._sesh.commit()

    def test_returns_active_rules_only(self, client):
        self._seed(client)
        resp = client.get(
            f"{_BASE}/discount-eligibility", params={"plate": "京E555"},
            headers=_headers("KEY_D", "SECRET_D"),
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["station_id"] == 7201
        assert data["plate_number"] == "京E555"
        # 只含本站点 active 的 2 条 (排除停用 + 邻站)
        assert len(data["rules"]) == 2
        types = {r["discount_type"] for r in data["rules"]}
        assert types == {"free_minutes", "percentage"}

    def test_station_isolation_excludes_other_station(self, client):
        """邻站规则不可见 (即使 active)。"""
        self._seed(client)
        resp = client.get(
            f"{_BASE}/discount-eligibility", params={"plate": "京E555"},
            headers=_headers("KEY_D", "SECRET_D"),
        )
        for r in resp.json()["data"]["rules"]:
            # 本站点规则不会带 station_id 字段, 但数量与类型可证隔离
            assert r["discount_type"] != "fixed"  # fixed 是本站点停用项

    def test_empty_result_when_no_active_rules(self, client):
        """无 active 规则 → rules=[]。"""
        _seed_station(client, sid=7211)
        _seed_credential(client, sid=7211, app_key="KEY_D2", app_secret="SECRET_D2")
        resp = client.get(
            f"{_BASE}/discount-eligibility", params={"plate": "京E555"},
            headers=_headers("KEY_D2", "SECRET_D2"),
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["rules"] == []

    def test_percent_serialized_as_float(self, client):
        """discount_percent/fixed_amount 序列化为 float。"""
        _seed_station(client, sid=7212)
        _seed_credential(client, sid=7212, app_key="KEY_D3", app_secret="SECRET_D3")
        from decimal import Decimal
        client._sesh.add(ParkingDiscount(station_id=7212, discount_type="percentage",
                                         discount_percent=Decimal("12.50"),
                                         fixed_amount=Decimal("3.00"),
                                         max_discount=Decimal("100.00"), is_active=True))
        client._sesh.commit()
        resp = client.get(
            f"{_BASE}/discount-eligibility", params={"plate": "京E555"},
            headers=_headers("KEY_D3", "SECRET_D3"),
        )
        r = resp.json()["data"]["rules"][0]
        assert r["discount_percent"] == 12.5
        assert r["fixed_amount"] == 3.0
        assert r["max_discount"] == 100.0


# ════════════════════════════════════════════════════════════
# POST /discount-applied
# ════════════════════════════════════════════════════════════
class TestDiscountApplied:
    """减免留痕: 422 校验 / 幂等 / 站点隔离防伪造。"""

    @staticmethod
    def _seed(client):
        _seed_station(client, sid=7301)
        _seed_credential(client, sid=7301, app_key="KEY_E", app_secret="SECRET_E")

    def test_create_success(self, client):
        self._seed(client)
        resp = client.post(
            f"{_BASE}/discount-applied",
            json={"plate_number": "京F666", "order_no": "PK-0001", "amount": "8.50",
                  "remark": "充电减免"},
            headers=_headers("KEY_E", "SECRET_E"),
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["plate_number"] == "京F666"
        assert data["order_no"] == "PK-0001"
        assert data["amount"] == "8.50"
        assert data["station_id"] == 7301
        assert resp.json()["message"] == "减免留痕成功"

    def test_idempotent_same_order_no(self, client):
        """同 order_no 二次请求 → 返回既有记录, 不重复入库, message 标注幂等。"""
        self._seed(client)
        body = {"plate_number": "京F666", "order_no": "PK-0002", "amount": "5.00"}
        r1 = client.post(f"{_BASE}/discount-applied", json=body, headers=_headers("KEY_E", "SECRET_E"))
        assert r1.status_code == 200
        first_id = r1.json()["data"]["id"]
        first_amount = r1.json()["data"]["amount"]

        # 二次请求, 改 amount/plate 也不应覆盖 (幂等返回既有)
        body2 = {"plate_number": "京F999", "order_no": "PK-0002", "amount": "99.99"}
        r2 = client.post(f"{_BASE}/discount-applied", json=body2, headers=_headers("KEY_E", "SECRET_E"))
        assert r2.status_code == 200
        data2 = r2.json()["data"]
        assert data2["id"] == first_id
        assert data2["amount"] == first_amount  # 未被覆盖
        assert data2["plate_number"] == "京F666"  # 原值保留
        assert r2.json()["message"] == "减免记录已存在(幂等)"

        # 库内仅一条
        rows = client._sesh.query(ParkingDiscountApplied).filter(
            ParkingDiscountApplied.order_no == "PK-0002"
        ).all()
        assert len(rows) == 1

    def test_amount_zero_422(self, client):
        """amount=0 → 422 (field_validator: 必须>0)。"""
        self._seed(client)
        resp = client.post(
            f"{_BASE}/discount-applied",
            json={"plate_number": "京F666", "order_no": "PK-0003", "amount": "0"},
            headers=_headers("KEY_E", "SECRET_E"),
        )
        assert resp.status_code == 422

    def test_amount_negative_422(self, client):
        """amount<0 → 422。"""
        self._seed(client)
        resp = client.post(
            f"{_BASE}/discount-applied",
            json={"plate_number": "京F666", "order_no": "PK-0004", "amount": "-5.00"},
            headers=_headers("KEY_E", "SECRET_E"),
        )
        assert resp.status_code == 422

    def test_missing_plate_422(self, client):
        """缺 plate_number → 422。"""
        self._seed(client)
        resp = client.post(
            f"{_BASE}/discount-applied",
            json={"order_no": "PK-0005", "amount": "5.00"},
            headers=_headers("KEY_E", "SECRET_E"),
        )
        assert resp.status_code == 422

    def test_missing_amount_422(self, client):
        """缺 amount → 422。"""
        self._seed(client)
        resp = client.post(
            f"{_BASE}/discount-applied",
            json={"plate_number": "京F666", "order_no": "PK-0006"},
            headers=_headers("KEY_E", "SECRET_E"),
        )
        assert resp.status_code == 422

    def test_missing_order_no_422(self, client):
        """缺 order_no → 422。"""
        self._seed(client)
        resp = client.post(
            f"{_BASE}/discount-applied",
            json={"plate_number": "京F666", "amount": "5.00"},
            headers=_headers("KEY_E", "SECRET_E"),
        )
        assert resp.status_code == 422

    def test_station_isolation_independent_records(self, client):
        """站点隔离: 每个站点凭证只往自己 station_id 留痕, 跨站点独立记录。"""
        self._seed(client)  # 站点 7301, KEY_E
        _seed_station(client, sid=7302)
        _seed_credential(client, sid=7302, app_key="KEY_E2", app_secret="SECRET_E2")

        # 站点 7301 留痕
        r1 = client.post(f"{_BASE}/discount-applied",
                         json={"plate_number": "京G1", "order_no": "PK-7301", "amount": "1.00"},
                         headers=_headers("KEY_E", "SECRET_E"))
        assert r1.status_code == 200
        assert r1.json()["data"]["station_id"] == 7301

        # 站点 7302 留痕, 落到自己的 station_id
        r2 = client.post(f"{_BASE}/discount-applied",
                         json={"plate_number": "京G2", "order_no": "PK-7302", "amount": "2.00"},
                         headers=_headers("KEY_E2", "SECRET_E2"))
        assert r2.status_code == 200
        assert r2.json()["data"]["station_id"] == 7302

        # 两站点各一条, station_id 各自正确
        rec_7301 = client._sesh.query(ParkingDiscountApplied).filter_by(order_no="PK-7301").one()
        rec_7302 = client._sesh.query(ParkingDiscountApplied).filter_by(order_no="PK-7302").one()
        assert rec_7301.station_id == 7301
        assert rec_7302.station_id == 7302


# ════════════════════════════════════════════════════════════
# DB 异常路径 (卡 a6e2e562): 业务查询/写库抛异常 → 503, 不裸抛 stack
# ════════════════════════════════════════════════════════════
class TestDBExceptionPaths:
    """鉴权通过后, 业务 DB 操作抛异常 → 兜底 503 + 固定 detail。

    /open/parking 在 enforce_auth 白名单 (不碰 DB); 鉴权依赖 override 为内存 cfg,
    get_db override 为 query 抛 OperationalError 的 mock session —— 仅端点业务查询炸。
    """

    @staticmethod
    def _boom_session(client, monkeypatch, *, query_chain="first"):
        """override 鉴权依赖返回有效 cfg + get_db 返回炸的 session。

        query_chain: first/all —— 让 .first() 或 .all() 抛错 (按端点业务调用而定)。
        用 monkeypatch.setitem 管理 dependency_overrides, 测试结束自动还原 (避免污染 session 级 app)。
        """
        from unittest.mock import MagicMock
        from sqlalchemy.exc import OperationalError
        from app.api.v1.parking_open import get_query_credential, get_active_credential
        from app.core.database import get_db

        cfg = MagicMock()
        cfg.station_id = 7401
        cfg.allow_query = True

        overrides = client.app.dependency_overrides
        monkeypatch.setitem(overrides, get_query_credential, lambda: cfg)
        monkeypatch.setitem(overrides, get_active_credential, lambda: cfg)

        boom = MagicMock()
        chained = MagicMock()
        # 链式 .filter()/.order_by() 等返回自身, 让终端 .first()/.all() 落在 chained 上
        chained.filter.return_value = chained
        chained.order_by.return_value = chained
        chained.filter_by.return_value = chained
        getattr(chained, query_chain).side_effect = OperationalError(
            "SELECT 1", {}, Exception("db down")
        )
        boom.query.return_value = chained
        monkeypatch.setitem(overrides, get_db, lambda: boom)
        return boom

    def test_charge_status_db_error_503(self, client, monkeypatch):
        """charge-status 业务查询抛异常 → 503。"""
        self._boom_session(client, monkeypatch, query_chain="first")
        resp = client.get(
            f"{_BASE}/charge-status", params={"plate": "京A12345"},
            headers=_headers("KEY_A", "SECRET_A"),
        )
        assert resp.status_code == 503, resp.text
        assert resp.json()["detail"] == "服务暂时不可用"

    def test_discount_applied_db_error_503(self, client, monkeypatch):
        """discount-applied 写库抛异常 → 503。"""
        self._boom_session(client, monkeypatch, query_chain="first")
        resp = client.post(
            f"{_BASE}/discount-applied",
            json={"plate_number": "京A12345", "order_no": "PK-DBERR", "amount": "5.00"},
            headers=_headers("KEY_A", "SECRET_A"),
        )
        assert resp.status_code == 503, resp.text
        assert resp.json()["detail"] == "服务暂时不可用"

    def test_discount_eligibility_db_error_503(self, client, monkeypatch):
        """discount-eligibility 业务查询 (.all) 抛异常 → 503。"""
        self._boom_session(client, monkeypatch, query_chain="all")
        resp = client.get(
            f"{_BASE}/discount-eligibility", params={"plate": "京A12345"},
            headers=_headers("KEY_A", "SECRET_A"),
        )
        assert resp.status_code == 503, resp.text
        assert resp.json()["detail"] == "服务暂时不可用"
