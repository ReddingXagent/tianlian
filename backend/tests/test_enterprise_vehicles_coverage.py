"""
企业车辆管理 API 补充覆盖测试 - Phase43 车队管理

补 app/api/v1/enterprise_vehicles.py 未覆盖分支:
- VIN 长度校验(422)
- _get_auto_confirm_config: 配置读取 / 非法JSON容错
- _evaluate_auto_confirm: 白名单 / 余额阈值 / 不匹配 / 关闭
- _sync_vin_whitelist_on_confirm: 无策略(全站) / 限站策略 / 已存在跳过
- 列表 approval_status 筛选
- 绑定自动确认(enabled+余额达标)
- confirm / reject / batch-confirm 端点全路径
- profile 各聚合段异常容错

源码零改动,仅新增测试。
"""
import json
from decimal import Decimal

import pytest
from sqlalchemy import text
from fastapi.testclient import TestClient


# ========== Fixtures (与既有 test_enterprise_vehicles*.py 一致,独立可运行) ==========

_counter = [0]


def _unique_code(prefix: str = "ENT_VC") -> str:
    _counter[0] += 1
    return f"{prefix}{_counter[0]}"


def _create_enterprise(test_db, name="测试车队企业", balance=10000.00):
    from app.models.enterprise import Enterprise
    db = test_db["session"]
    ent = Enterprise(name=name, code=_unique_code(), balance=balance)
    db.add(ent)
    db.commit()
    db.refresh(ent)
    return ent


@pytest.fixture
def enterprise_id(test_db):
    return _create_enterprise(test_db).id


@pytest.fixture
def client(test_db):
    from app.main import app
    from app.core.database import get_db
    app.dependency_overrides[get_db] = lambda: test_db["session"]
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _login(client):
    resp = client.post(
        "/api/v1/auth/login",
        data={"username": "admin", "password": "admin123"},
    )
    assert resp.status_code == 200
    data = resp.json()
    return data.get("token") or data.get("data", {}).get("token")


def _auth_headers(client):
    return {"Authorization": f"Bearer {_login(client)}"}


def _bind_vehicle(client, enterprise_id, **overrides):
    """绑定车辆辅助函数,默认成功"""
    payload = {
        "plate_number": "豫A99999",
        "vin": "LSJU26938VSCV0001",
    }
    payload.update(overrides)
    resp = client.post(
        f"/api/v1/enterprises/{enterprise_id}/vehicles",
        json=payload,
        headers=_auth_headers(client),
    )
    assert resp.status_code == 200, f"绑定车辆失败: {resp.text}"
    return resp.json()["data"]


def _set_fleet_auto_confirm(test_db, config: dict):
    """往 system_configs 写入合法 fleet_auto_confirm JSON 配置。"""
    s = test_db["session"]
    s.execute(
        text("INSERT INTO system_configs (config_key, config_value, type) VALUES (:k, :v, :t)"),
        {"k": "fleet_auto_confirm", "v": json.dumps(config), "t": "global"},
    )
    s.commit()


def _set_fleet_auto_confirm_raw(test_db, raw_value: str):
    """往 system_configs 写入任意 config_value(用于非法 JSON 容错测试)。"""
    s = test_db["session"]
    s.execute(
        text("INSERT INTO system_configs (config_key, config_value, type) VALUES (:k, :v, :t)"),
        {"k": "fleet_auto_confirm", "v": raw_value, "t": "global"},
    )
    s.commit()


# ========== VIN 校验 ==========

class TestVinValidation:
    def test_bind_invalid_vin_length(self, client, enterprise_id):
        """VIN 非17位 -> pydantic validator 抛 ValueError -> 422"""
        resp = client.post(
            f"/api/v1/enterprises/{enterprise_id}/vehicles",
            json={"plate_number": "豫V00001", "vin": "LSJU26938VS1"},  # 11位
            headers=_auth_headers(client),
        )
        assert resp.status_code == 422


# ========== 自动确认配置读取 ==========

class TestAutoConfirmConfig:
    def test_config_present_parses_json(self, test_db):
        """system_configs 有合法配置 -> 解析返回(覆盖 import json + json.loads)"""
        from app.api.v1.enterprise_vehicles import _get_auto_confirm_config
        _set_fleet_auto_confirm(test_db, {"enabled": True, "balance_threshold": 5000})
        cfg = _get_auto_confirm_config(test_db["session"])
        assert cfg["enabled"] is True
        assert cfg["balance_threshold"] == 5000

    def test_config_invalid_json_falls_back(self, test_db):
        """config_value 非法 JSON -> except -> 返回默认(覆盖 logger.warning 分支)"""
        from app.api.v1.enterprise_vehicles import _get_auto_confirm_config
        _set_fleet_auto_confirm_raw(test_db, "{not-json")
        cfg = _get_auto_confirm_config(test_db["session"])
        assert cfg == {"enabled": False, "balance_threshold": 0, "whitelist_enterprise_codes": []}

    def test_config_missing_falls_back(self, test_db):
        """无配置行 -> 返回默认"""
        from app.api.v1.enterprise_vehicles import _get_auto_confirm_config
        cfg = _get_auto_confirm_config(test_db["session"])
        assert cfg["enabled"] is False


# ========== 自动确认规则评估 ==========

class TestEvaluateAutoConfirm:
    def test_whitelist_match(self, test_db):
        """enabled + 企业编码在白名单 -> True"""
        from app.api.v1.enterprise_vehicles import _evaluate_auto_confirm
        ent = _create_enterprise(test_db, name="白名单企业")
        _set_fleet_auto_confirm(test_db, {
            "enabled": True,
            "whitelist_enterprise_codes": [ent.code, "OTHER"],
        })
        assert _evaluate_auto_confirm(test_db["session"], ent) is True

    def test_balance_threshold_match(self, test_db):
        """enabled + 余额>=阈值 -> True(白名单空,走余额规则)"""
        from app.api.v1.enterprise_vehicles import _evaluate_auto_confirm
        ent = _create_enterprise(test_db, name="余额充足企业", balance=10000.00)
        _set_fleet_auto_confirm(test_db, {
            "enabled": True,
            "balance_threshold": 5000,
        })
        assert _evaluate_auto_confirm(test_db["session"], ent) is True

    def test_no_match_returns_false(self, test_db):
        """enabled 但白名单/余额均不命中 -> False"""
        from app.api.v1.enterprise_vehicles import _evaluate_auto_confirm
        ent = _create_enterprise(test_db, name="不匹配企业", balance=100.00)
        _set_fleet_auto_confirm(test_db, {
            "enabled": True,
            "balance_threshold": 999999,
            "whitelist_enterprise_codes": ["NOT_THIS"],
        })
        assert _evaluate_auto_confirm(test_db["session"], ent) is False

    def test_disabled_returns_false(self, test_db):
        """规则关闭 -> 直接 False"""
        from app.api.v1.enterprise_vehicles import _evaluate_auto_confirm
        ent = _create_enterprise(test_db, name="规则关闭企业")
        _set_fleet_auto_confirm(test_db, {"enabled": False})
        assert _evaluate_auto_confirm(test_db["session"], ent) is False


# ========== VIN 白名单同步(helper) ==========

class TestSyncVinWhitelist:
    def _make_vehicle(self, test_db, ent, vin):
        from app.models.enterprise_vehicle import (
            EnterpriseVehicle, EnterpriseVehicleStatus, ApprovalStatus,
        )
        s = test_db["session"]
        veh = EnterpriseVehicle(
            enterprise_id=ent.id,
            plate_number="豫W" + vin[-5:],
            vin=vin,
            status=EnterpriseVehicleStatus.ACTIVE,
            approval_status=ApprovalStatus.PENDING,
        )
        s.add(veh)
        s.commit()
        s.refresh(veh)
        return veh

    def test_no_policy_adds_to_all_stations(self, test_db):
        """无充电策略 -> VIN 加入所有场站(覆盖 all_stations 分支 + 循环创建)"""
        from app.api.v1.enterprise_vehicles import _sync_vin_whitelist_on_confirm
        from app.models.station import Station, StationStatus
        from app.models.enterprise_vehicle import StationVinWhitelist
        s = test_db["session"]
        ent = _create_enterprise(test_db, name="无策略企业")
        s.add_all([
            Station(name="站A", code="STC_A", status=StationStatus.NORMAL),
            Station(name="站B", code="STC_B", status=StationStatus.NORMAL),
        ])
        s.commit()
        veh = self._make_vehicle(test_db, ent, "LSJU26938VSWL0001")

        _sync_vin_whitelist_on_confirm(s, veh)
        s.commit()

        rows = s.query(StationVinWhitelist).filter_by(vin=veh.vin).all()
        assert len(rows) == 2

    def test_policy_limits_to_allowed_stations(self, test_db):
        """有限站策略 -> 仅加入 allowed_station_ids(覆盖 policy 分支)"""
        from app.api.v1.enterprise_vehicles import _sync_vin_whitelist_on_confirm
        from app.models.station import Station, StationStatus
        from app.models.fleet_charging_policy import FleetChargingPolicy
        from app.models.enterprise_vehicle import StationVinWhitelist
        s = test_db["session"]
        ent = _create_enterprise(test_db, name="限站策略企业")
        st_keep = Station(name="保留站", code="STC_K", status=StationStatus.NORMAL)
        st_skip = Station(name="排除站", code="STC_S", status=StationStatus.NORMAL)
        s.add_all([st_keep, st_skip])
        s.commit()
        s.refresh(st_keep)
        s.refresh(st_skip)
        s.add(FleetChargingPolicy(
            enterprise_id=ent.id, enable=True,
            allowed_station_ids=[st_keep.id],
        ))
        s.commit()
        veh = self._make_vehicle(test_db, ent, "LSJU26938VSWL0002")

        _sync_vin_whitelist_on_confirm(s, veh)
        s.commit()

        rows = s.query(StationVinWhitelist).filter_by(vin=veh.vin).all()
        assert {r.station_id for r in rows} == {st_keep.id}

    def test_existing_record_not_duplicated(self, test_db):
        """同 VIN 已在白名单 -> 再次同步不重复创建(覆盖 if not existing False 分支)"""
        from app.api.v1.enterprise_vehicles import _sync_vin_whitelist_on_confirm
        from app.models.station import Station, StationStatus
        from app.models.enterprise_vehicle import StationVinWhitelist
        s = test_db["session"]
        ent = _create_enterprise(test_db, name="去重企业")
        s.add(Station(name="单站", code="STC_D", status=StationStatus.NORMAL))
        s.commit()
        veh = self._make_vehicle(test_db, ent, "LSJU26938VSWL0003")

        _sync_vin_whitelist_on_confirm(s, veh)
        s.commit()
        _sync_vin_whitelist_on_confirm(s, veh)
        s.commit()

        rows = s.query(StationVinWhitelist).filter_by(vin=veh.vin).all()
        assert len(rows) == 1


# ========== 列表 approval_status 筛选 ==========

class TestVehicleListFilter:
    def test_filter_by_approval_status(self, client, enterprise_id):
        """approval_status 筛选: confirmed/pending 各返回对应车辆"""
        v1 = _bind_vehicle(client, enterprise_id, plate_number="豫L00001", vin="LSJU26938VSLF0001")
        _bind_vehicle(client, enterprise_id, plate_number="豫L00002", vin="LSJU26938VSLF0002")
        # 先确认 v1
        r = client.post(
            f"/api/v1/enterprises/{enterprise_id}/vehicles/{v1['id']}/confirm",
            headers=_auth_headers(client),
        )
        assert r.status_code == 200

        resp = client.get(
            f"/api/v1/enterprises/{enterprise_id}/vehicles?approval_status=confirmed",
            headers=_auth_headers(client),
        )
        assert resp.status_code == 200
        items = resp.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["id"] == v1["id"]
        assert items[0]["approval_status"] == "confirmed"

        resp2 = client.get(
            f"/api/v1/enterprises/{enterprise_id}/vehicles?approval_status=pending",
            headers=_auth_headers(client),
        )
        assert len(resp2.json()["data"]["items"]) == 1


# ========== 绑定自动确认 ==========

class TestVehicleBindAutoConfirm:
    def test_bind_auto_confirmed_by_balance(self, client, test_db):
        """enabled + 余额达标 -> 绑定时自动确认(覆盖 auto-confirm 分支)"""
        ent = _create_enterprise(test_db, name="自动确认企业", balance=10000.00)
        _set_fleet_auto_confirm(test_db, {"enabled": True, "balance_threshold": 5000})

        data = _bind_vehicle(client, ent.id, plate_number="豫AC0001", vin="LSJU26938VSAC0001")
        assert data["approval_status"] == "confirmed"
        assert data["confirmed_by"] == "auto"
        assert data["confirmed_at"] is not None


# ========== 手动确认端点 ==========

class TestConfirmVehicle:
    def test_confirm_success(self, client, enterprise_id):
        """pending -> confirmed,confirmed_by=manual"""
        created = _bind_vehicle(client, enterprise_id, plate_number="豫C00001", vin="LSJU26938VSCM0001")
        resp = client.post(
            f"/api/v1/enterprises/{enterprise_id}/vehicles/{created['id']}/confirm",
            headers=_auth_headers(client),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["approval_status"] == "confirmed"
        assert data["confirmed_by"] == "manual"
        assert data["confirmed_at"] is not None

    def test_confirm_not_found(self, client, enterprise_id):
        """车辆不存在 -> 404"""
        resp = client.post(
            f"/api/v1/enterprises/{enterprise_id}/vehicles/99999/confirm",
            headers=_auth_headers(client),
        )
        assert resp.status_code == 404

    def test_confirm_already_confirmed(self, client, enterprise_id):
        """重复确认 -> 400"""
        created = _bind_vehicle(client, enterprise_id, plate_number="豫C00002", vin="LSJU26938VSCM0002")
        client.post(
            f"/api/v1/enterprises/{enterprise_id}/vehicles/{created['id']}/confirm",
            headers=_auth_headers(client),
        )
        resp = client.post(
            f"/api/v1/enterprises/{enterprise_id}/vehicles/{created['id']}/confirm",
            headers=_auth_headers(client),
        )
        assert resp.status_code == 400


# ========== 拒绝端点 ==========

class TestRejectVehicle:
    def test_reject_success(self, client, enterprise_id):
        """pending -> rejected,清空确认字段"""
        created = _bind_vehicle(client, enterprise_id, plate_number="豫R00001", vin="LSJU26938VSRE0001")
        resp = client.post(
            f"/api/v1/enterprises/{enterprise_id}/vehicles/{created['id']}/reject",
            json={"reason": "资料不全"},
            headers=_auth_headers(client),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["approval_status"] == "rejected"

    def test_reject_not_found(self, client, enterprise_id):
        """车辆不存在 -> 404"""
        resp = client.post(
            f"/api/v1/enterprises/{enterprise_id}/vehicles/99999/reject",
            json={},
            headers=_auth_headers(client),
        )
        assert resp.status_code == 404


# ========== 批量确认端点 ==========

class TestBatchConfirm:
    def test_batch_confirm_mixed(self, client, enterprise_id):
        """混合: 已确认跳过 + pending 确认(覆盖 skipped/confirmed 双分支)"""
        v1 = _bind_vehicle(client, enterprise_id, plate_number="豫B00001", vin="LSJU26938VSBC0001")
        v2 = _bind_vehicle(client, enterprise_id, plate_number="豫B00002", vin="LSJU26938VSBC0002")
        v3 = _bind_vehicle(client, enterprise_id, plate_number="豫B00003", vin="LSJU26938VSBC0003")
        # v1 先单独确认
        client.post(
            f"/api/v1/enterprises/{enterprise_id}/vehicles/{v1['id']}/confirm",
            headers=_auth_headers(client),
        )

        resp = client.post(
            f"/api/v1/enterprises/{enterprise_id}/vehicles/batch-confirm",
            json={"vehicle_ids": [v1["id"], v2["id"], v3["id"]]},
            headers=_auth_headers(client),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert set(data["confirmed_ids"]) == {v2["id"], v3["id"]}
        assert data["skipped_ids"] == [v1["id"]]
        assert data["total_requested"] == 3
        assert data["total_confirmed"] == 2

    def test_batch_confirm_empty_ids(self, client, enterprise_id):
        """vehicle_ids 空 -> 400"""
        resp = client.post(
            f"/api/v1/enterprises/{enterprise_id}/vehicles/batch-confirm",
            json={"vehicle_ids": []},
            headers=_auth_headers(client),
        )
        assert resp.status_code == 400

    def test_batch_confirm_not_found(self, client, enterprise_id):
        """vehicle_ids 均不存在 -> 404"""
        resp = client.post(
            f"/api/v1/enterprises/{enterprise_id}/vehicles/batch-confirm",
            json={"vehicle_ids": [99999]},
            headers=_auth_headers(client),
        )
        assert resp.status_code == 404


# ========== profile 各聚合段异常容错 ==========

class TestProfileErrorResilience:
    def test_each_segment_swallows_error(self, client, test_db, monkeypatch):
        """四段聚合任一 _xxx_to_dict 抛异常 -> 对应字段回退空,整体仍 200"""
        from datetime import date
        import app.api.v1.enterprise_vehicles as ev
        from app.models.charging_order import ChargingOrder, OrderStatus, OrderPaymentStatus
        from app.models.fleet_v2g import FleetV2GRevenue
        from app.models.carbon_emission import CarbonReductionRecord
        from app.models.enterprise_transaction import EnterpriseTransaction, TransactionType

        ent = _create_enterprise(test_db, name="容错企业")
        created = _bind_vehicle(client, ent.id, plate_number="豫E00001", vin="LSJU26938VSER0001")
        vid = created["id"]
        s = test_db["session"]

        # 各段都准备一条数据,使对应 _xxx_to_dict 被调用
        s.add(ChargingOrder(
            order_no="CO_ERR_1", station_id=1, device_id=1,
            plate_number="豫E00001", vehicle_id=vid,
            charged_kwh=Decimal("10"), total_amount=Decimal("20"),
            paid_amount=Decimal("20"),
            order_status=OrderStatus.COMPLETED,
            payment_status=OrderPaymentStatus.PAID,
        ))
        s.add(FleetV2GRevenue(
            enterprise_id=ent.id, vehicle_id=vid,
            record_date=date(2026, 7, 1),
            discharge_energy_kwh=Decimal("5"), total_revenue=Decimal("9"),
        ))
        s.add(CarbonReductionRecord(
            enterprise_id=ent.id, vehicle_id=vid,
            record_date=date(2026, 7, 1),
            charge_energy_kwh=Decimal("10"),
            carbon_reduction_kg=Decimal("2"),
        ))
        s.add(EnterpriseTransaction(
            enterprise_id=ent.id, vehicle_id=vid,
            type=TransactionType.CONSUME,
            amount=Decimal("20"), balance_after=Decimal("9980"),
        ))
        s.commit()

        def _boom(*a, **kw):
            raise RuntimeError("boom")
        monkeypatch.setattr(ev, "_charging_order_to_dict", _boom)
        monkeypatch.setattr(ev, "_v2g_revenue_to_dict", _boom)
        monkeypatch.setattr(ev, "_carbon_record_to_dict", _boom)
        monkeypatch.setattr(ev, "_transaction_to_dict", _boom)

        resp = client.get(
            f"/api/v1/enterprises/{ent.id}/vehicles/{vid}/profile",
            headers=_auth_headers(client),
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["charging_history"] == []
        assert data["v2g"] == {"records": [], "total_revenue": 0}
        assert data["carbon"] == []
        assert data["transactions"] == []
