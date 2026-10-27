"""数据导出/备份 API 测试 (卡 922b2fba)

覆盖: 平台导出权限 / 租户过滤 / team 用户越权 403 / backup 元数据块 / 附件头。
"""
import json

from tests.conftest import _get_token
from tests._test_helpers import _fast_hash


def _seed_tenant_world(client):
    """造两个租户各自的数据: tenant A (team_a, 1站1设备1用户), tenant B (team_b, 1站1设备)."""
    from app.models.tenant import Tenant
    from app.models.user import Team, User, UserRole
    from app.models.station import Station, StationStatus
    from app.models.device import Device, DeviceType, DeviceStatus

    s = client._sesh
    tenant_a = Tenant(name="租户A", code="TEN_A")
    tenant_b = Tenant(name="租户B", code="TEN_B")
    s.add_all([tenant_a, tenant_b])
    s.commit()

    team_a = Team(name="团队A", code="TEN_A")
    team_b = Team(name="团队B", code="TEN_B")
    s.add_all([team_a, team_b])
    s.commit()

    sta_a = Station(name="A站", code="STAA", status=StationStatus.NORMAL, team_id=team_a.id, tenant_id=tenant_a.id)
    sta_b = Station(name="B站", code="STAB", status=StationStatus.NORMAL, team_id=team_b.id, tenant_id=tenant_b.id)
    s.add_all([sta_a, sta_b])
    s.commit()

    dev_a = Device(sn="SN-EXP-A", name="A设备", code="EXPA", type=DeviceType.CHARGER_DC,
                   status=DeviceStatus.ONLINE, station_id=sta_a.id, rated_power=60.0)
    dev_b = Device(sn="SN-EXP-B", name="B设备", code="EXPB", type=DeviceType.CHARGER_DC,
                   status=DeviceStatus.ONLINE, station_id=sta_b.id, rated_power=60.0)
    s.add_all([dev_a, dev_b])
    s.commit()

    if not s.query(User).filter(User.username == "a_engineer").first():
        s.add(User(username="a_engineer", password_hash=_fast_hash("eng123456"),
                   real_name="A工程师", role=UserRole.ENGINEER, status="active", team_id=team_a.id))
        s.commit()

    return {"tenant_a": tenant_a, "tenant_b": tenant_b, "team_a": team_a, "team_b": team_b}


def test_platform_export_admin_ok(client):
    _seed_tenant_world(client)
    r = client.get("/api/v1/admin-data/export", params={"scope": "platform", "mode": "export"})
    assert r.status_code == 200
    assert "attachment" in r.headers.get("content-disposition", "")
    assert "tianlian_export" in r.headers.get("content-disposition", "")
    body = r.json()
    data = body.get("data", body)
    # 关键业务表均在
    for table in ("stations", "devices", "users", "alarms", "work_orders"):
        assert table in data, f"缺少表 {table}"
    # 两租户数据都在 (平台全量)
    sns = [d.get("sn") for d in data["devices"]]
    assert "SN-EXP-A" in sns and "SN-EXP-B" in sns
    # 导出不得泄露密码哈希
    for u in data["users"]:
        assert "password_hash" not in u


def test_platform_export_team_user_403(client):
    _seed_tenant_world(client)
    token = _get_token(client, "a_engineer", "eng123456")
    r = client.get("/api/v1/admin-data/export",
                   params={"scope": "platform"},
                   headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


def test_tenant_export_filters_to_own_tenant(client):
    world = _seed_tenant_world(client)
    r = client.get("/api/v1/admin-data/export",
                   params={"scope": "tenant", "tenant_id": world["tenant_a"].id, "mode": "export"})
    assert r.status_code == 200
    data = r.json().get("data")
    sns = [d.get("sn") for d in data["devices"]]
    assert sns == ["SN-EXP-A"]
    station_codes = [s.get("code") for s in data["stations"]]
    assert station_codes == ["STAA"]
    usernames = [u.get("username") for u in data["users"]]
    assert "a_engineer" in usernames


def test_team_user_can_export_own_tenant_only(client):
    world = _seed_tenant_world(client)
    token = _get_token(client, "a_engineer", "eng123456")
    headers = {"Authorization": f"Bearer {token}"}
    # 本租户 → 200 且仅本租户数据
    r = client.get("/api/v1/admin-data/export",
                   params={"scope": "tenant", "tenant_id": world["tenant_a"].id},
                   headers=headers)
    assert r.status_code == 200
    assert [d.get("sn") for d in r.json()["data"]["devices"]] == ["SN-EXP-A"]
    # 他人租户 → 403
    r = client.get("/api/v1/admin-data/export",
                   params={"scope": "tenant", "tenant_id": world["tenant_b"].id},
                   headers=headers)
    assert r.status_code == 403


def test_tenant_scope_requires_tenant_id(client):
    r = client.get("/api/v1/admin-data/export", params={"scope": "tenant"})
    assert r.status_code == 400


def test_backup_mode_has_metadata(client):
    _seed_tenant_world(client)
    r = client.get("/api/v1/admin-data/export",
                   params={"scope": "platform", "mode": "backup"})
    assert r.status_code == 200
    body = r.json()
    meta = body.get("metadata")
    assert meta, "backup 模式缺 metadata 块"
    assert meta.get("generated_at")
    assert meta.get("version")
    schemas = meta.get("table_schemas")
    assert isinstance(schemas, dict) and "devices" in schemas
    assert "sn" in schemas["devices"]


def test_export_anonymous_401(anon_client):
    r = anon_client.get("/api/v1/admin-data/export", params={"scope": "platform"})
    assert r.status_code == 401


def test_backup_generated_at_is_tz_aware(client):
    """generated_at 须带 +08:00 偏移 (tz-aware), 不再是裸 naive 时间。"""
    from datetime import datetime
    _seed_tenant_world(client)
    r = client.get("/api/v1/admin-data/export",
                   params={"scope": "platform", "mode": "backup"})
    assert r.status_code == 200
    generated_at = r.json()["metadata"]["generated_at"]
    parsed = datetime.fromisoformat(generated_at)
    assert parsed.tzinfo is not None, f"generated_at 无时区标记: {generated_at}"
    assert parsed.utcoffset().total_seconds() == 8 * 3600


def test_export_filename_date_matches_biz_tz(client, monkeypatch):
    """文件名中日期须为 Asia/Shanghai 当日 (UTC 16:00 后不跳次日)。"""
    from datetime import datetime, timezone
    import app.api.v1.admin_data_ops as mod

    # 锚定 UTC 2026-10-10 17:00 → 上海已是 10-11, UTC 仍是 10-10 (切日边界)
    frozen = datetime(2026, 10, 10, 17, 0, 0, tzinfo=timezone.utc)

    class _FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is not None:
                return frozen.astimezone(tz)
            return frozen.replace(tzinfo=None)

    monkeypatch.setattr(mod, "datetime", _FrozenDateTime)
    _seed_tenant_world(client)
    r = client.get("/api/v1/admin-data/export", params={"scope": "platform"})
    assert r.status_code == 200
    disp = r.headers.get("content-disposition", "")
    assert "tianlian_export_platform_20261011" in disp, disp  # 上海日期, 非 UTC 的 20261010


# ---- 卡 e5008622: 导出行数上限防伪流式 OOM ----

def test_export_row_limit_exceeded(client, monkeypatch):
    """charging_orders 行数超上限 → 413 (卡 e5008622)。

    _build_payload 对 8 张表 .all() 前须先 .count() 预检; charging_orders 是
    最大增长表, mock 其 count() 返回 MAX+1 (模拟大表), 其余表走真实查询
    (行数远低于上限, 正常通过)。断言 GET /admin-data/export?scope=platform
    返回 413, detail 含表名/行数/上限值。
    """
    import app.api.v1.admin_data_ops as mod
    from app.models.charging_order import ChargingOrder

    _seed_tenant_world(client)
    limit = getattr(mod, "MAX_EXPORT_ROWS_PER_TABLE", 50000)
    over = limit + 1
    real_query = client._sesh.query

    class _OverLimitQuery:
        """charging_orders 替身: count 超限; all() 在 GREEN 后因先 raise 不会被触达。"""

        def __init__(self, real):
            self._real = real

        def count(self):
            return over

        def all(self):
            return []

        def filter(self, *a, **k):
            # platform scope filters=None, 不会触发; 兜底转发真实 query
            return self._real.filter(*a, **k)

    def _patched_query(*args, **kwargs):
        q = real_query(*args, **kwargs)
        model = args[0] if args else kwargs.get("model")
        return _OverLimitQuery(q) if model is ChargingOrder else q

    monkeypatch.setattr(client._sesh, "query", _patched_query)

    r = client.get("/api/v1/admin-data/export", params={"scope": "platform"})
    assert r.status_code == 413, r.text
    detail = r.json().get("detail", "")
    assert "charging_orders" in detail, detail
    assert str(over) in detail, detail
    assert str(limit) in detail, detail


def test_export_row_limit_not_triggered_for_small_tables(client):
    """回归: 正常小表导出不受行数上限误伤, 权限门/序列化/metadata 不变 (卡 e5008622)。"""
    _seed_tenant_world(client)
    r = client.get("/api/v1/admin-data/export",
                   params={"scope": "platform", "mode": "backup"})
    assert r.status_code == 200
    body = r.json()
    # 序列化未变: devices 仍在, password_hash 仍剥离
    data = body.get("data", body)
    assert "devices" in data
    for u in data["users"]:
        assert "password_hash" not in u
    # metadata 未变
    assert body.get("metadata", {}).get("version")
