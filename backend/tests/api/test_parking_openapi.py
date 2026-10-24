"""停车场系统对接开放API测试（任务卡 309b4132）

覆盖：
- 鉴权 401：无 key / 错 key / 错 secret / 集成配置 inactive
- 鉴权 403：allow_query=False（有效凭证但禁止查询）
- 跨站点隔离：本站点凭证看不到他站点数据
- 3 端点正常路径：charge-status / discount-eligibility / discount-applied
- order_no 幂等：重复提交返回同一记录
- 金额校验：amount <= 0 → 422

开放API独立鉴权：X-App-Key + X-App-Secret header（hmac.compare_digest 常数时间比较），
station_id 取自凭证（凭证绑定站点），不走 user JWT，故走 anon_client（enforce_auth 白名单豁免 /open/parking）。
"""
import pytest


# ── 测试数据构造 ──
def _make_station(s, code, team_id=1):
    from app.models.station import Station, StationStatus
    st = Station(name=f"站{code}", code=code, status=StationStatus.NORMAL, team_id=team_id)
    s.add(st)
    s.commit()
    s.refresh(st)
    return st


def _make_integration(s, station_id, app_key="PK-A", app_secret="SK-A",
                      allow_query=True, is_active=True, mode="A"):
    from app.models.parking_integration import ParkingIntegrationConfig, IntegrationMode
    cfg = ParkingIntegrationConfig(
        station_id=station_id,
        provider_name="测试车场",
        app_key=app_key,
        app_secret=app_secret,
        integration_mode=IntegrationMode(mode) if hasattr(IntegrationMode, "value") else mode,
        allow_query=allow_query,
        is_active=is_active,
    )
    s.add(cfg)
    s.commit()
    s.refresh(cfg)
    return cfg


def _headers(app_key, app_secret):
    return {"X-App-Key": app_key, "X-App-Secret": app_secret}


def _seed_charge_order(s, station_id, plate, order_status="charging", device_id=1):
    from app.models.charging_order import ChargingOrder, OrderStatus, OrderPaymentStatus
    o = ChargingOrder(
        order_no=f"CO-{station_id}-{plate}",
        station_id=station_id,
        device_id=device_id,
        plate_number=plate,
        order_status=OrderStatus(order_status),
        payment_status=OrderPaymentStatus.UNPAID,
    )
    s.add(o)
    s.commit()
    s.refresh(o)
    return o


def _seed_discount_rule(s, station_id, dtype="free_minutes", free_minutes=120):
    from app.models.parking import ParkingDiscount
    from decimal import Decimal
    d = ParkingDiscount(
        station_id=station_id,
        discount_type=dtype,
        free_minutes=free_minutes,
        discount_percent=Decimal("0"),
        fixed_amount=Decimal("0"),
        is_active=True,
    )
    s.add(d)
    s.commit()
    s.refresh(d)
    return d


# ════════════════════════════════════════════════════════════
# 鉴权
# ════════════════════════════════════════════════════════════
class TestParkingOpenAuth:
    def test_no_credentials_401(self, anon_client, client):
        """无任何凭证 → 401"""
        _make_station(client._sesh, "STA")
        r = anon_client.get("/api/v1/open/parking/charge-status?plate=京A12345")
        assert r.status_code == 401

    def test_wrong_key_401(self, anon_client, client):
        """错 key → 401"""
        st = _make_station(client._sesh, "STB")
        _make_integration(client._sesh, st.id, app_key="PK-OK", app_secret="SK-OK")
        r = anon_client.get(
            "/api/v1/open/parking/charge-status?plate=京A12345",
            headers=_headers("PK-WRONG", "SK-OK"),
        )
        assert r.status_code == 401

    def test_wrong_secret_401(self, anon_client, client):
        """对 key 但错 secret → 401"""
        st = _make_station(client._sesh, "STC")
        _make_integration(client._sesh, st.id, app_key="PK-OK", app_secret="SK-OK")
        r = anon_client.get(
            "/api/v1/open/parking/charge-status?plate=京A12345",
            headers=_headers("PK-OK", "SK-WRONG"),
        )
        assert r.status_code == 401

    def test_inactive_integration_401(self, anon_client, client):
        """凭证正确但 is_active=False → 401"""
        st = _make_station(client._sesh, "STD")
        _make_integration(client._sesh, st.id, app_key="PK-I", app_secret="SK-I", is_active=False)
        r = anon_client.get(
            "/api/v1/open/parking/charge-status?plate=京A12345",
            headers=_headers("PK-I", "SK-I"),
        )
        assert r.status_code == 401


# ════════════════════════════════════════════════════════════
# 授权（有效凭证但功能关闭）
# ════════════════════════════════════════════════════════════
class TestParkingOpenAllowQuery:
    def test_allow_query_false_403(self, anon_client, client):
        """allow_query=False → 403（凭证有效但禁止查询）"""
        st = _make_station(client._sesh, "STE")
        _make_integration(client._sesh, st.id, app_key="PK-NQ", app_secret="SK-NQ", allow_query=False)
        r = anon_client.get(
            "/api/v1/open/parking/charge-status?plate=京A12345",
            headers=_headers("PK-NQ", "SK-NQ"),
        )
        assert r.status_code == 403


# ════════════════════════════════════════════════════════════
# 3 端点正常路径
# ════════════════════════════════════════════════════════════
class TestParkingOpenEndpoints:
    def test_charge_status(self, anon_client, client):
        """charge-status：本站点该车牌充电中"""
        st = _make_station(client._sesh, "STF")
        _make_integration(client._sesh, st.id, app_key="PK-CS", app_secret="SK-CS")
        _seed_charge_order(client._sesh, st.id, "京A11111", order_status="charging")
        r = anon_client.get(
            "/api/v1/open/parking/charge-status?plate=京A11111",
            headers=_headers("PK-CS", "SK-CS"),
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["plate_number"] == "京A11111"
        assert data["charging"] is True

    def test_charge_status_not_charging(self, anon_client, client):
        """车牌无充电记录 → charging=False"""
        st = _make_station(client._sesh, "STG")
        _make_integration(client._sesh, st.id, app_key="PK-CS2", app_secret="SK-CS2")
        r = anon_client.get(
            "/api/v1/open/parking/charge-status?plate=京A99999",
            headers=_headers("PK-CS2", "SK-CS2"),
        )
        assert r.status_code == 200
        assert r.json()["data"]["charging"] is False

    def test_discount_eligibility(self, anon_client, client):
        """discount-eligibility：返回本站点生效的 ParkingDiscount 规则"""
        st = _make_station(client._sesh, "STH")
        _make_integration(client._sesh, st.id, app_key="PK-DE", app_secret="SK-DE")
        _seed_discount_rule(client._sesh, st.id, dtype="free_minutes", free_minutes=90)
        r = anon_client.get(
            "/api/v1/open/parking/discount-eligibility?plate=京A22222",
            headers=_headers("PK-DE", "SK-DE"),
        )
        assert r.status_code == 200
        items = r.json()["data"]["rules"]
        assert any(i["discount_type"] == "free_minutes" and i["free_minutes"] == 90 for i in items)

    def test_discount_applied(self, anon_client, client):
        """discount-applied：减免留痕成功"""
        st = _make_station(client._sesh, "STI")
        _make_integration(client._sesh, st.id, app_key="PK-DA", app_secret="SK-DA")
        r = anon_client.post(
            "/api/v1/open/parking/discount-applied",
            headers=_headers("PK-DA", "SK-DA"),
            json={
                "plate_number": "京A33333",
                "order_no": "PKORDER-1",
                "amount": "12.50",
                "remark": "充电减免2小时停车费",
            },
        )
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["order_no"] == "PKORDER-1"
        assert data["station_id"] == st.id
        from app.models.parking_discount_applied import ParkingDiscountApplied
        rec = client._sesh.query(ParkingDiscountApplied).filter_by(order_no="PKORDER-1").first()
        assert rec is not None
        assert str(rec.amount) == "12.50"


# ════════════════════════════════════════════════════════════
# 幂等
# ════════════════════════════════════════════════════════════
class TestParkingOpenIdempotency:
    def test_discount_applied_idempotent(self, anon_client, client):
        """同一 order_no 重复提交 → 幂等，不重复入库"""
        st = _make_station(client._sesh, "STJ")
        _make_integration(client._sesh, st.id, app_key="PK-IDEM", app_secret="SK-IDEM")
        payload = {
            "plate_number": "京A44444",
            "order_no": "PKORDER-IDEM",
            "amount": "8.00",
            "remark": "首次",
        }
        r1 = anon_client.post(
            "/api/v1/open/parking/discount-applied",
            headers=_headers("PK-IDEM", "SK-IDEM"),
            json=payload,
        )
        assert r1.status_code == 200
        first_id = r1.json()["data"]["id"]

        # 第二次同 order_no
        payload["remark"] = "重复"
        r2 = anon_client.post(
            "/api/v1/open/parking/discount-applied",
            headers=_headers("PK-IDEM", "SK-IDEM"),
            json=payload,
        )
        assert r2.status_code == 200
        assert r2.json()["data"]["id"] == first_id  # 同一记录

        from app.models.parking_discount_applied import ParkingDiscountApplied
        count = client._sesh.query(ParkingDiscountApplied).filter_by(order_no="PKORDER-IDEM").count()
        assert count == 1


# ════════════════════════════════════════════════════════════
# 金额校验
# ════════════════════════════════════════════════════════════
class TestParkingOpenAmountValidation:
    def test_zero_amount_rejected(self, anon_client, client):
        """amount=0 → 422（减免金额必须为正）"""
        st = _make_station(client._sesh, "STK")
        _make_integration(client._sesh, st.id, app_key="PK-Z", app_secret="SK-Z")
        r = anon_client.post(
            "/api/v1/open/parking/discount-applied",
            headers=_headers("PK-Z", "SK-Z"),
            json={"plate_number": "京A55555", "order_no": "PKORDER-Z", "amount": "0"},
        )
        assert r.status_code == 422

    def test_negative_amount_rejected(self, anon_client, client):
        """amount<0 → 422"""
        st = _make_station(client._sesh, "STL")
        _make_integration(client._sesh, st.id, app_key="PK-N", app_secret="SK-N")
        r = anon_client.post(
            "/api/v1/open/parking/discount-applied",
            headers=_headers("PK-N", "SK-N"),
            json={"plate_number": "京A66666", "order_no": "PKORDER-N", "amount": "-5.00"},
        )
        assert r.status_code == 422


# ════════════════════════════════════════════════════════════
# 跨站点隔离
# ════════════════════════════════════════════════════════════
class TestParkingOpenStationIsolation:
    def test_cross_station_data_invisible(self, anon_client, client):
        """站点A凭证查站点B的车牌 → 查不到（返回 not charging）"""
        st_a = _make_station(client._sesh, "STA1")
        st_b = _make_station(client._sesh, "STB1")
        # 车牌挂在 B 站点充电
        _seed_charge_order(client._sesh, st_b.id, "京A77777", order_status="charging")
        # A 站点凭证
        _make_integration(client._sesh, st_a.id, app_key="PK-A1", app_secret="SK-A1")
        r = anon_client.get(
            "/api/v1/open/parking/charge-status?plate=京A77777",
            headers=_headers("PK-A1", "SK-A1"),
        )
        assert r.status_code == 200
        assert r.json()["data"]["charging"] is False  # A 站点看不到 B 的充电

    def test_cross_station_discount_rule_invisible(self, anon_client, client):
        """站点A凭证查不到站点B的折扣规则"""
        st_a = _make_station(client._sesh, "STA2")
        st_b = _make_station(client._sesh, "STB2")
        # 折扣规则挂在 B
        _seed_discount_rule(client._sesh, st_b.id, dtype="percentage", free_minutes=0)
        _make_integration(client._sesh, st_a.id, app_key="PK-A2", app_secret="SK-A2")
        r = anon_client.get(
            "/api/v1/open/parking/discount-eligibility?plate=京A88888",
            headers=_headers("PK-A2", "SK-A2"),
        )
        assert r.status_code == 200
        assert r.json()["data"]["rules"] == []  # A 站点无规则

    def test_applied_station_from_credential(self, anon_client, client):
        """discount-applied 的 station_id 取自凭证（绑定站点），非请求体"""
        st_a = _make_station(client._sesh, "STA3")
        _make_station(client._sesh, "STB3")
        _make_integration(client._sesh, st_a.id, app_key="PK-A3", app_secret="SK-A3")
        r = anon_client.post(
            "/api/v1/open/parking/discount-applied",
            headers=_headers("PK-A3", "SK-A3"),
            json={"plate_number": "京A99999", "order_no": "PKORDER-ISO", "amount": "3.00"},
        )
        assert r.status_code == 200
        assert r.json()["data"]["station_id"] == st_a.id
