"""
车辆确认流 + VIN 充电授权白名单 测试

覆盖:
- 手动确认 confirm → confirmed + VIN 入白名单
- 拒绝 reject → rejected + VIN 移除白名单
- 批量确认 batch-confirm
- 自动确认规则触发（余额阈值 / 白名单企业编码）
- 白名单联动：confirm→VIN入场站白名单，reject→移除
- 解绑车辆 → VIN 白名单移除
- GET /stations/{sid}/vin-whitelist 查询
- VIN 17位校验
"""
import pytest
import json
from fastapi.testclient import TestClient


# ========== Fixtures ==========

_counter = [0]


def _unique_code(prefix: str = "ENT_V") -> str:
    _counter[0] += 1
    return f"{prefix}{_counter[0]}"


def _create_enterprise(test_db, name="测试车队企业", balance=10000.00, code=None):
    from app.models.enterprise import Enterprise
    db = test_db["session"]
    ent = Enterprise(name=name, code=code or _unique_code(), balance=balance)
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
    """绑定车辆辅助函数，默认成功"""
    payload = {
        "plate_number": "豫A99999",
        "vin": "LSJU26938VS100001",
    }
    payload.update(overrides)
    resp = client.post(
        f"/api/v1/enterprises/{enterprise_id}/vehicles",
        json=payload,
        headers=_auth_headers(client),
    )
    assert resp.status_code == 200, f"绑定车辆失败: {resp.text}"
    return resp.json()["data"]


def _seed_station(test_db, code="STA_VIN_01"):
    """创建测试场站"""
    from app.models.station import Station, StationStatus
    db = test_db["session"]
    st = Station(name="测试VIN场站", code=code, status=StationStatus.NORMAL)
    db.add(st)
    db.commit()
    db.refresh(st)
    return st


# ========== 手动确认 ==========

class TestManualConfirm:
    """手动确认车辆测试"""

    def test_confirm_success(self, client, enterprise_id, test_db):
        """确认 → confirmed + confirmed_at/confirmed_by"""
        v = _bind_vehicle(client, enterprise_id, vin="LSJU26938VS100011")
        assert v["approval_status"] == "pending"

        resp = client.post(
            f"/api/v1/enterprises/{enterprise_id}/vehicles/{v['id']}/confirm",
            headers=_auth_headers(client),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["approval_status"] == "confirmed"
        assert data["confirmed_at"] is not None
        assert data["confirmed_by"] == "manual"

    def test_confirm_already_confirmed(self, client, enterprise_id):
        """重复确认 → 400"""
        v = _bind_vehicle(client, enterprise_id, vin="LSJU26938VS100012")
        client.post(
            f"/api/v1/enterprises/{enterprise_id}/vehicles/{v['id']}/confirm",
            headers=_auth_headers(client),
        )
        resp = client.post(
            f"/api/v1/enterprises/{enterprise_id}/vehicles/{v['id']}/confirm",
            headers=_auth_headers(client),
        )
        assert resp.status_code == 400

    def test_confirm_not_found(self, client, enterprise_id):
        """车辆不存在 → 404"""
        resp = client.post(
            f"/api/v1/enterprises/{enterprise_id}/vehicles/99999/confirm",
            headers=_auth_headers(client),
        )
        assert resp.status_code == 404


# ========== 拒绝 ==========

class TestReject:
    """拒绝车辆测试"""

    def test_reject_success(self, client, enterprise_id):
        """拒绝 → rejected，可重新确认"""
        v = _bind_vehicle(client, enterprise_id, vin="LSJU26938VS100021")
        resp = client.post(
            f"/api/v1/enterprises/{enterprise_id}/vehicles/{v['id']}/reject",
            json={"reason": "信息不全"},
            headers=_auth_headers(client),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["approval_status"] == "rejected"
        assert data["confirmed_at"] is None

    def test_reject_then_reconfirm(self, client, enterprise_id):
        """拒绝后可以重新确认"""
        v = _bind_vehicle(client, enterprise_id, vin="LSJU26938VS100022")
        # 拒绝
        client.post(
            f"/api/v1/enterprises/{enterprise_id}/vehicles/{v['id']}/reject",
            headers=_auth_headers(client),
        )
        # 重新确认
        resp = client.post(
            f"/api/v1/enterprises/{enterprise_id}/vehicles/{v['id']}/confirm",
            headers=_auth_headers(client),
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["approval_status"] == "confirmed"


# ========== 批量确认 ==========

class TestBatchConfirm:
    """批量确认测试"""

    def test_batch_confirm_success(self, client, enterprise_id):
        """批量确认多辆车"""
        v1 = _bind_vehicle(client, enterprise_id, plate_number="豫B001", vin="LSJU26938VS100031")
        v2 = _bind_vehicle(client, enterprise_id, plate_number="豫B002", vin="LSJU26938VS100032")
        v3 = _bind_vehicle(client, enterprise_id, plate_number="豫B003", vin="LSJU26938VS100033")

        resp = client.post(
            f"/api/v1/enterprises/{enterprise_id}/vehicles/batch-confirm",
            json={"vehicle_ids": [v1["id"], v2["id"], v3["id"]]},
            headers=_auth_headers(client),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total_confirmed"] == 3
        assert len(data["confirmed_ids"]) == 3

    def test_batch_confirm_skip_already_confirmed(self, client, enterprise_id):
        """批量确认跳过已确认的"""
        v1 = _bind_vehicle(client, enterprise_id, plate_number="豫C001", vin="LSJU26938VS100041")
        v2 = _bind_vehicle(client, enterprise_id, plate_number="豫C002", vin="LSJU26938VS100042")
        # 先手动确认 v1
        client.post(
            f"/api/v1/enterprises/{enterprise_id}/vehicles/{v1['id']}/confirm",
            headers=_auth_headers(client),
        )
        # 批量确认含已确认的 v1
        resp = client.post(
            f"/api/v1/enterprises/{enterprise_id}/vehicles/batch-confirm",
            json={"vehicle_ids": [v1["id"], v2["id"]]},
            headers=_auth_headers(client),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total_confirmed"] == 1
        assert data["total_requested"] == 2
        assert len(data["skipped_ids"]) == 1

    def test_batch_confirm_empty_ids(self, client, enterprise_id):
        """空列表 → 400"""
        resp = client.post(
            f"/api/v1/enterprises/{enterprise_id}/vehicles/batch-confirm",
            json={"vehicle_ids": []},
            headers=_auth_headers(client),
        )
        assert resp.status_code == 400


# ========== 自动确认规则 ==========

class TestAutoConfirm:
    """自动确认规则测试"""

    def test_auto_confirm_by_balance(self, client, test_db):
        """余额>阈值自动确认"""
        # 创建高余额企业
        ent = _create_enterprise(test_db, name="富裕车队", balance=50000.00, code="RICH001")
        # 设置自动确认规则
        db = test_db["session"]
        from sqlalchemy import text
        db.execute(text(
            "INSERT INTO system_configs (config_key, config_value, type) "
            "VALUES ('fleet_auto_confirm', :val, 'fleet')"
        ), {"val": json.dumps({"enabled": True, "balance_threshold": 30000, "whitelist_enterprise_codes": []})})
        db.commit()

        v = _bind_vehicle(client, ent.id, vin="LSJU26938VS100051")
        assert v["approval_status"] == "confirmed"
        assert v["confirmed_by"] == "auto"

    def test_auto_confirm_by_enterprise_code(self, client, test_db):
        """白名单企业编码自动确认"""
        ent = _create_enterprise(test_db, name="白名单车队", balance=100.00, code="WL_ENT_01")
        db = test_db["session"]
        from sqlalchemy import text
        db.execute(text(
            "INSERT INTO system_configs (config_key, config_value, type) "
            "VALUES ('fleet_auto_confirm', :val, 'fleet')"
        ), {"val": json.dumps({"enabled": True, "balance_threshold": 999999, "whitelist_enterprise_codes": ["WL_ENT_01"]})})
        db.commit()

        v = _bind_vehicle(client, ent.id, vin="LSJU26938VS100061")
        assert v["approval_status"] == "confirmed"

    def test_auto_confirm_disabled(self, client, test_db):
        """关闭自动确认 → 保持 pending"""
        ent = _create_enterprise(test_db, name="普通车队", balance=50000.00, code="NORMAL001")
        db = test_db["session"]
        from sqlalchemy import text
        db.execute(text(
            "INSERT INTO system_configs (config_key, config_value, type) "
            "VALUES ('fleet_auto_confirm', :val, 'fleet')"
        ), {"val": json.dumps({"enabled": False, "balance_threshold": 0, "whitelist_enterprise_codes": []})})
        db.commit()

        v = _bind_vehicle(client, ent.id, vin="LSJU26938VS100071")
        assert v["approval_status"] == "pending"

    def test_auto_confirm_below_threshold(self, client, test_db):
        """余额不足阈值 → 不自动确认"""
        ent = _create_enterprise(test_db, name="穷车队", balance=100.00, code="POOR001")
        db = test_db["session"]
        from sqlalchemy import text
        db.execute(text(
            "INSERT INTO system_configs (config_key, config_value, type) "
            "VALUES ('fleet_auto_confirm', :val, 'fleet')"
        ), {"val": json.dumps({"enabled": True, "balance_threshold": 5000, "whitelist_enterprise_codes": []})})
        db.commit()

        v = _bind_vehicle(client, ent.id, vin="LSJU26938VS100081")
        assert v["approval_status"] == "pending"


# ========== VIN 白名单联动 ==========

class TestVinWhitelistSync:
    """VIN 白名单联动测试"""

    def test_confirm_adds_to_whitelist(self, client, enterprise_id, test_db):
        """确认车辆 → VIN 进入场站白名单"""
        _seed_station(test_db)
        v = _bind_vehicle(client, enterprise_id, vin="LSJU26938VS100091")

        # 确认前 → 白名单为空
        resp = client.get(
            "/api/v1/stations/1/vin-whitelist",
            headers=_auth_headers(client),
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["total"] == 0

        # 确认
        client.post(
            f"/api/v1/enterprises/{enterprise_id}/vehicles/{v['id']}/confirm",
            headers=_auth_headers(client),
        )

        # 确认后 → 白名单有该 VIN
        resp = client.get(
            "/api/v1/stations/1/vin-whitelist",
            headers=_auth_headers(client),
        )
        data = resp.json()["data"]
        assert data["total"] >= 1
        vins = [item["vin"] for item in data["items"]]
        assert "LSJU26938VS100091" in vins

    def test_reject_removes_from_whitelist(self, client, enterprise_id, test_db):
        """拒绝车辆 → VIN 从白名单移除"""
        _seed_station(test_db)
        v = _bind_vehicle(client, enterprise_id, vin="LSJU26938VS100101")

        # 先确认
        client.post(
            f"/api/v1/enterprises/{enterprise_id}/vehicles/{v['id']}/confirm",
            headers=_auth_headers(client),
        )

        # 确认在白名单
        resp = client.get(
            "/api/v1/stations/1/vin-whitelist",
            headers=_auth_headers(client),
        )
        vins = [item["vin"] for item in resp.json()["data"]["items"]]
        assert "LSJU26938VS100101" in vins

        # 拒绝
        client.post(
            f"/api/v1/enterprises/{enterprise_id}/vehicles/{v['id']}/reject",
            headers=_auth_headers(client),
        )

        # 不在白名单
        resp = client.get(
            "/api/v1/stations/1/vin-whitelist",
            headers=_auth_headers(client),
        )
        vins = [item["vin"] for item in resp.json()["data"]["items"]]
        assert "LSJU26938VS100101" not in vins

    def test_unbind_removes_whitelist(self, client, enterprise_id, test_db):
        """解绑车辆 → VIN 白名单移除"""
        _seed_station(test_db)
        v = _bind_vehicle(client, enterprise_id, vin="LSJU26938VS100111")

        # 确认
        client.post(
            f"/api/v1/enterprises/{enterprise_id}/vehicles/{v['id']}/confirm",
            headers=_auth_headers(client),
        )

        # 解绑
        client.delete(
            f"/api/v1/enterprises/{enterprise_id}/vehicles/{v['id']}",
            headers=_auth_headers(client),
        )

        # 白名单应不含该 VIN
        resp = client.get(
            "/api/v1/stations/1/vin-whitelist",
            headers=_auth_headers(client),
        )
        vins = [item["vin"] for item in resp.json()["data"]["items"]]
        assert "LSJU26938VS100111" not in vins


# ========== VIN 白名单查询端点 ==========

class TestVinWhitelistQuery:
    """VIN 白名单查询/管理端点测试"""

    def test_get_empty_whitelist(self, client, enterprise_id, test_db):
        """空白名单查询"""
        _seed_station(test_db)
        resp = client.get(
            "/api/v1/stations/1/vin-whitelist",
            headers=_auth_headers(client),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["items"] == []
        assert data["total"] == 0

    def test_manual_add_to_whitelist(self, client, enterprise_id, test_db):
        """手动添加 VIN 到白名单"""
        _seed_station(test_db)
        resp = client.post(
            "/api/v1/stations/1/vin-whitelist",
            json={"vin": "LSJU26938VS100121", "enterprise_id": enterprise_id},
            headers=_auth_headers(client),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["vin"] == "LSJU26938VS100121"
        assert data["source"] == "manual"

    def test_manual_add_duplicate(self, client, enterprise_id, test_db):
        """重复添加 → 400"""
        _seed_station(test_db)
        client.post(
            "/api/v1/stations/1/vin-whitelist",
            json={"vin": "LSJU26938VS100122", "enterprise_id": enterprise_id},
            headers=_auth_headers(client),
        )
        resp = client.post(
            "/api/v1/stations/1/vin-whitelist",
            json={"vin": "LSJU26938VS100122", "enterprise_id": enterprise_id},
            headers=_auth_headers(client),
        )
        assert resp.status_code == 400

    def test_remove_from_whitelist(self, client, enterprise_id, test_db):
        """移除 VIN"""
        _seed_station(test_db)
        # 先加
        client.post(
            "/api/v1/stations/1/vin-whitelist",
            json={"vin": "LSJU26938VS100131", "enterprise_id": enterprise_id},
            headers=_auth_headers(client),
        )
        # 删
        resp = client.delete(
            "/api/v1/stations/1/vin-whitelist/LSJU26938VS100131",
            headers=_auth_headers(client),
        )
        assert resp.status_code == 200

    def test_remove_nonexistent(self, client, test_db):
        """删除不存在的 VIN → 404"""
        _seed_station(test_db)
        resp = client.delete(
            "/api/v1/stations/1/vin-whitelist/NOTEXIST1234567890",
            headers=_auth_headers(client),
        )
        assert resp.status_code == 404


# ========== VIN 校验 ==========

class TestVinValidation:
    """VIN 码 17 位校验"""

    def test_short_vin_rejected(self, client, enterprise_id):
        """VIN < 17 位 → 422"""
        resp = client.post(
            f"/api/v1/enterprises/{enterprise_id}/vehicles",
            json={"plate_number": "豫V001", "vin": "SHORT123"},
            headers=_auth_headers(client),
        )
        assert resp.status_code == 422

    def test_long_vin_rejected(self, client, enterprise_id):
        """VIN > 17 位 → 422"""
        resp = client.post(
            f"/api/v1/enterprises/{enterprise_id}/vehicles",
            json={"plate_number": "豫V002", "vin": "LSJU26938VS100001EXTRA"},
            headers=_auth_headers(client),
        )
        assert resp.status_code == 422

    def test_exact_17_vin_accepted(self, client, enterprise_id):
        """VIN = 17 位 → 成功"""
        resp = client.post(
            f"/api/v1/enterprises/{enterprise_id}/vehicles",
            json={"plate_number": "豫V003", "vin": "LSJU26938VS100141"},
            headers=_auth_headers(client),
        )
        assert resp.status_code == 200


# ========== 列表筛选 ==========

class TestListWithApprovalFilter:
    """列表支持 approval_status 筛选"""

    def test_filter_by_approval_status(self, client, enterprise_id):
        """按确认状态筛选"""
        v1 = _bind_vehicle(client, enterprise_id, plate_number="豫F001", vin="LSJU26938VS100151")
        v2 = _bind_vehicle(client, enterprise_id, plate_number="豫F002", vin="LSJU26938VS100152")
        # 确认 v1
        client.post(
            f"/api/v1/enterprises/{enterprise_id}/vehicles/{v1['id']}/confirm",
            headers=_auth_headers(client),
        )

        # 筛选 pending
        resp = client.get(
            f"/api/v1/enterprises/{enterprise_id}/vehicles?approval_status=pending",
            headers=_auth_headers(client),
        )
        data = resp.json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["approval_status"] == "pending"

        # 筛选 confirmed
        resp = client.get(
            f"/api/v1/enterprises/{enterprise_id}/vehicles?approval_status=confirmed",
            headers=_auth_headers(client),
        )
        data = resp.json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["approval_status"] == "confirmed"
