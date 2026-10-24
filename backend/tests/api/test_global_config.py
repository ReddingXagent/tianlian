"""系统配置 - 全局配置端点测试 (app/api/v1/system_config/global_config.py, 卡 7ebaa989)

global_config.py 是 system_config 模块中唯一零测试的端点:
- GET  /api/v1/system-config/global  读全局配置 (system 域, 默认值回退)
- PUT  /api/v1/system-config/global  更新全局配置 (exclude_none 部分更新 + 审计日志)

实现要点:
- DEFAULT_GLOBAL_CONFIG 兜底: 表中无记录 → 返回默认值
- _load_json_config 合并语义: 已存值 {**default, **data}, db 覆盖同名键
- PUT 用 data.dict(exclude_none=True), 未传字段不覆盖
- 两道鉴权: assert_config_domain_access("system") 在前, _check_admin_or_permission("system:config") 在后
  viewer (team_type 无 system 域) 在第一道即被 403 拦下

覆盖维度:
(a) GET: 默认值回退 / 已存值读取 / viewer 403
(b) PUT: 全量更新 / 部分更新 (exclude_none 不覆盖未传字段) / merge 后回读 / viewer 403 / 422 长度越界
(c) 审计日志: PUT 成功后 audit_logs 落一条 update / system_config 记录, 含 old_value/new_value

铁律: 仅加测试, 不改业务代码。
"""
import ast

from sqlalchemy import text

from app.api.v1.system_config.global_config import DEFAULT_GLOBAL_CONFIG


def _parse_audit_value(raw):
    """实现用 str(dict) 落库 (单引号 Python 字面量, 非 JSON), 用 literal_eval 还原。"""
    if not raw:
        return {}
    return ast.literal_eval(raw)

GLOBAL_URL = "/api/v1/system-config/global"


# ═══════════════════════════════════════════════════════════════
# helper: 切到 viewer1 视角
# ═══════════════════════════════════════════════════════════════

def _as_viewer(client, seed_users):
    """把 client 切到 viewer1 (team_type 无 system 域 → 403)。返回原 admin token 便于恢复。"""
    from tests.conftest import _get_token
    admin_token = client.headers.get("Authorization")
    tok = _get_token(client, "viewer1", "view123")
    client.headers["Authorization"] = f"Bearer {tok}"
    return admin_token


# ═══════════════════════════════════════════════════════════════
# 1. GET /global
# ═══════════════════════════════════════════════════════════════

class TestGetGlobalConfig:
    def test_default_when_empty(self, client):
        """表中无 global_config 记录 → 返回 DEFAULT_GLOBAL_CONFIG 兜底。"""
        r = client.get(GLOBAL_URL)
        assert r.status_code == 200
        assert r.json()["data"] == DEFAULT_GLOBAL_CONFIG

    def test_reads_stored_value(self, client):
        """已存配置 (经 merge default) 原样读回, db 覆盖同名键。"""
        client.put(GLOBAL_URL, json={
            "system_name": "自定义平台",
            "language": "en-US",
        })
        r = client.get(GLOBAL_URL)
        data = r.json()["data"]
        assert data["system_name"] == "自定义平台"
        assert data["language"] == "en-US"
        # 未改字段保留默认
        assert data["copyright"] == DEFAULT_GLOBAL_CONFIG["copyright"]
        assert data["logo_url"] == DEFAULT_GLOBAL_CONFIG["logo_url"]

    def test_default_matches_contract(self, client):
        """DEFAULT_GLOBAL_CONFIG 契约: 5 个固定键 + 固定值。"""
        assert set(DEFAULT_GLOBAL_CONFIG.keys()) == {
            "system_name", "logo_url", "copyright", "login_bg_url", "language",
        }
        assert DEFAULT_GLOBAL_CONFIG["system_name"] == "天链云平台"
        assert DEFAULT_GLOBAL_CONFIG["language"] == "zh-CN"


# ═══════════════════════════════════════════════════════════════
# 2. PUT /global
# ═══════════════════════════════════════════════════════════════

class TestUpdateGlobalConfig:
    def test_update_all_fields(self, client):
        """全量更新 → 返回值 = 新值, 默认键被覆盖。"""
        payload = {
            "system_name": "新平台",
            "logo_url": "https://cdn/logo.png",
            "copyright": "© 2026 天链",
            "login_bg_url": "https://cdn/bg.jpg",
            "language": "en-US",
        }
        r = client.put(GLOBAL_URL, json=payload)
        assert r.status_code == 200
        assert "全局配置已更新" in r.json()["message"]
        assert r.json()["data"] == payload

    def test_update_partial_preserves_untouched(self, client):
        """仅传 system_name, 其余字段不变 (exclude_none 不覆盖)。"""
        # 先写一个已知状态
        client.put(GLOBAL_URL, json={
            "system_name": "旧平台",
            "logo_url": "https://cdn/old.png",
            "language": "zh-CN",
        })
        # 只改 system_name
        r = client.put(GLOBAL_URL, json={"system_name": "新平台"})
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["system_name"] == "新平台"
        # 未传字段保留
        assert data["logo_url"] == "https://cdn/old.png"
        assert data["language"] == "zh-CN"
        assert data["copyright"] == DEFAULT_GLOBAL_CONFIG["copyright"]

    def test_update_empty_payload_keeps_default(self, client):
        """空 dict (全 None) → 不覆盖任何字段, 返回 DEFAULT。"""
        r = client.put(GLOBAL_URL, json={})
        assert r.status_code == 200
        assert r.json()["data"] == DEFAULT_GLOBAL_CONFIG

    def test_update_then_get_round_trip(self, client):
        """PUT 后 GET 持久化一致 (merge 语义)。"""
        client.put(GLOBAL_URL, json={"system_name": "回读平台", "language": "ja-JP"})
        data = client.get(GLOBAL_URL).json()["data"]
        assert data["system_name"] == "回读平台"
        assert data["language"] == "ja-JP"

    def test_update_validation_too_long(self, client):
        """system_name 超 max_length(100) → 422。"""
        r = client.put(GLOBAL_URL, json={"system_name": "x" * 101})
        assert r.status_code == 422


# ═══════════════════════════════════════════════════════════════
# 3. 权限校验 (viewer 403)
# ═══════════════════════════════════════════════════════════════

class TestGlobalConfigAuth:
    def test_viewer_get_denied(self, client, seed_users):
        """viewer team_type 无 system 域 → GET 403 (assert_config_domain_access)。"""
        _as_viewer(client, seed_users)
        r = client.get(GLOBAL_URL)
        assert r.status_code == 403
        assert "system" in r.json()["detail"]

    def test_viewer_put_denied(self, client, seed_users):
        """viewer → PUT 403 (在 _check_admin_or_permission 之前已被 domain 校验拦)。"""
        _as_viewer(client, seed_users)
        r = client.put(GLOBAL_URL, json={"system_name": "越权"})
        assert r.status_code == 403

    def test_anon_denied(self, anon_client):
        """匿名 (无 token) → GET 401。"""
        r = anon_client.get(GLOBAL_URL)
        assert r.status_code == 401


# ═══════════════════════════════════════════════════════════════
# 4. 审计日志
# ═══════════════════════════════════════════════════════════════

class TestGlobalConfigAudit:
    def _audit_rows(self, db):
        """用 client._sesh (测试 SessionLocal) 查 audit_logs。

        audit_service.log_crud 未传 db 时走模块级 SessionLocal (自管事务+COMMIT)。
        但 audit_service 在 import 时 ``from app.core.database import SessionLocal``
        把名字绑死成 import 时刻的全局 SessionLocal (指向 ./tianlian_v3.db), 而 conftest
        后续 ``db_module.SessionLocal = test_engine_maker`` 的赋值改的是 database 模块属性,
        无法回流到 audit_service 的局部名 → 审计误写到全局开发库。

        故测试需 monkeypatch ``audit_service.SessionLocal`` 到 conftest override 后的测试
        SessionLocal (app.core.database.SessionLocal), 使写入落到测试库, 再用 client._sesh 查。
        (坑: [[service-sessionlocal-import-binding-test-pitfall]])
        """
        return db.execute(
            text("SELECT action, module, target_desc, old_value, new_value "
                 "FROM audit_logs WHERE module = 'system_config' "
                 "ORDER BY id DESC")
        ).all()

    def _patch_audit_session(self, monkeypatch):
        """把 audit_service 的 SessionLocal 名字对齐到 conftest override 后的测试 sessionmaker。"""
        import app.services.audit_service as _as
        from app.core.database import SessionLocal as _test_sl
        monkeypatch.setattr(_as, "SessionLocal", _test_sl)

    def test_put_writes_audit_log(self, client, monkeypatch):
        """PUT 成功 → audit_logs 落一条 update/system_config, 含 old/new 值。"""
        self._patch_audit_session(monkeypatch)
        r = client.put(GLOBAL_URL, json={"system_name": "审计平台"})
        assert r.status_code == 200
        rows = self._audit_rows(client._sesh)
        assert len(rows) >= 1
        row = rows[0]
        assert row[0] == "update"          # action
        assert row[1] == "system_config"   # module
        assert "全局配置" in (row[2] or "")  # target_desc
        old = _parse_audit_value(row[3])
        new = _parse_audit_value(row[4])
        # old 是更新前 (默认值), new 含新值
        assert new.get("system_name") == "审计平台"
        assert old.get("system_name") == DEFAULT_GLOBAL_CONFIG["system_name"]

    def test_put_audit_records_diff(self, client, monkeypatch):
        """二次更新: old_value 反映上一次的状态, new_value 反映本次。"""
        self._patch_audit_session(monkeypatch)
        client.put(GLOBAL_URL, json={"system_name": "第一版"})
        client.put(GLOBAL_URL, json={"system_name": "第二版"})
        rows = self._audit_rows(client._sesh)
        latest = rows[0]
        new = _parse_audit_value(latest[4])
        old = _parse_audit_value(latest[3])
        assert new["system_name"] == "第二版"
        assert old["system_name"] == "第一版"

    def test_get_writes_no_audit(self, client, monkeypatch):
        """GET 只读, 不应落审计日志。"""
        self._patch_audit_session(monkeypatch)
        client.get(GLOBAL_URL)
        rows = self._audit_rows(client._sesh)
        assert len(rows) == 0
