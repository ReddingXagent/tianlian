"""app/core/auth_throttle.py 网关鉴权依赖单元测试

补 tests/test_gateway_auth_throttle.py (helper 单测 + 端到端 perf) 未直接覆盖的
get_current_gateway_or_user 依赖函数各分支 + reset 行为。

分支:
  - 缺认证 (无 X-API-Key 无 token) → 401
  - token 分支 → 委托 get_current_user
  - X-API-Key 优先于 token (同时给两个走 gateway)
  - 空 X-API-Key 视同未提供
  - gateway cache_miss: 有效 active key → caller + 回填缓存 + 记 last_used
  - gateway cache_hit: 复用缓存, 免 DB SELECT, 节流放行才 UPDATE
  - 无效 key → 401 且不缓存
  - 安全关键: key 查询 filter status=='active' (杜绝 revoked/expired)
  - _reset_gateway_auth_caches 原地清空 (对象身份不变)
"""
import types
from datetime import datetime
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.core import auth_throttle
from app.core.auth_throttle import get_current_gateway_or_user


@pytest.fixture(autouse=True)
def _reset_caches():
    """每测试前后清空进程内节流/缓存状态, 隔离 _should_record_last_used 残留。"""
    auth_throttle._reset_gateway_auth_caches()
    yield
    auth_throttle._reset_gateway_auth_caches()


def _make_request():
    """造 request: state 为空 SimpleNamespace (无 mw_inner_start → warn_dispatch_slow 跳过)。"""
    req = types.SimpleNamespace()
    req.state = types.SimpleNamespace()  # 无 mw_inner_start 属性
    req.url = types.SimpleNamespace(path="/x")
    return req


def _make_db(first_result=None):
    """造 mock db: db.query(M).filter(...).first() → first_result; .update() 链可用。"""
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = first_result
    return db


# ────────────────────────────────────────────────────────────────────
# 缺认证 / 空 key
# ────────────────────────────────────────────────────────────────────
class TestMissingAuth:
    def test_no_key_no_token_raises_401(self):
        with pytest.raises(HTTPException) as ei:
            get_current_gateway_or_user(
                request=_make_request(), x_api_key=None, token=None, db=MagicMock())
        assert ei.value.status_code == 401

    def test_empty_api_key_falls_through_to_401(self):
        """空字符串 X-API-Key ('') falsy → 视同未提供 → 401。"""
        with pytest.raises(HTTPException) as ei:
            get_current_gateway_or_user(
                request=_make_request(), x_api_key="", token=None, db=MagicMock())
        assert ei.value.status_code == 401


# ────────────────────────────────────────────────────────────────────
# token 分支
# ────────────────────────────────────────────────────────────────────
class TestTokenBranch:
    def test_delegates_to_get_current_user(self, monkeypatch):
        import app.api.v1.auth as auth_mod
        fake_user = {"type": "user", "id": 1}
        mock_gcu = MagicMock(return_value=fake_user)
        monkeypatch.setattr(auth_mod, "get_current_user", mock_gcu)
        db = MagicMock()
        result = get_current_gateway_or_user(
            request=_make_request(), x_api_key=None, token="jwt", db=db)
        assert result == fake_user
        mock_gcu.assert_called_once_with(token="jwt", db=db)


# ────────────────────────────────────────────────────────────────────
# X-API-Key 优先于 token
# ────────────────────────────────────────────────────────────────────
class TestApiKeyPrecedence:
    def test_api_key_takes_precedence_over_token(self, monkeypatch):
        """同时给 X-API-Key 和 token → 走 gateway 分支, get_current_user 不被调。"""
        import app.api.v1.auth as auth_mod
        mock_gcu = MagicMock(return_value="SHOULD_NOT_BE_USED")
        monkeypatch.setattr(auth_mod, "get_current_user", mock_gcu)
        key = MagicMock(id=3, client_id=3, status="active", expires_at=None)
        db = _make_db(first_result=key)
        result = get_current_gateway_or_user(
            request=_make_request(), x_api_key="real", token="jwt", db=db)
        assert result["type"] == "gateway"
        mock_gcu.assert_not_called()


# ────────────────────────────────────────────────────────────────────
# gateway cache_miss
# ────────────────────────────────────────────────────────────────────
class TestGatewayCacheMiss:
    def test_valid_active_key_returns_caller_and_backfills_cache(self):
        key = MagicMock(id=42, client_id=7, status="active", expires_at=None)
        db = _make_db(first_result=key)
        result = get_current_gateway_or_user(
            request=_make_request(), x_api_key="valid-key", token=None, db=db)
        assert result == {"type": "gateway", "key_id": 42, "client_id": 7}
        assert auth_throttle._get_cached_gateway_caller("valid-key") == result

    def test_first_use_records_last_used_at(self):
        key = MagicMock(id=88, client_id=2, status="active", expires_at=None)
        db = _make_db(first_result=key)
        get_current_gateway_or_user(
            request=_make_request(), x_api_key="newkey", token=None, db=db)
        # 赋值前 MagicMock 自动属性非 datetime; 节流放行赋值后为 datetime
        assert isinstance(key.last_used_at, datetime)

    def test_invalid_key_raises_401_and_not_cached(self):
        db = _make_db(first_result=None)
        with pytest.raises(HTTPException) as ei:
            get_current_gateway_or_user(
                request=_make_request(), x_api_key="bad", token=None, db=db)
        assert ei.value.status_code == 401
        assert auth_throttle._get_cached_gateway_caller("bad") is None

    def test_query_filters_active_status(self):
        """安全关键: key 查询 filter 含 status=='active', 杜绝 revoked/expired key 鉴权。

        值 'active' 经参数化不在默认 str(SQL) 文本 (显示 :status_1 占位符), 用
        literal_binds 编译内联参数确认右值确为 'active'。
        """
        key = MagicMock(id=1, client_id=1, status="active", expires_at=None)
        db = _make_db(first_result=key)
        get_current_gateway_or_user(
            request=_make_request(), x_api_key="k", token=None, db=db)
        args = db.query.return_value.filter.call_args[0]
        found = False
        for arg in args:
            if "status" not in str(arg):
                continue
            compiled = str(arg.compile(compile_kwargs={"literal_binds": True}))
            if "active" in compiled:
                found = True
                break
        assert found, [str(a) for a in args]


# ────────────────────────────────────────────────────────────────────
# gateway cache_hit
# ────────────────────────────────────────────────────────────────────
class TestGatewayCacheHit:
    def test_cached_caller_skips_db_select(self):
        """缓存命中免 key SELECT (.first()); 节流放行时仍 UPDATE last_used (允许)。"""
        caller = {"type": "gateway", "key_id": 5, "client_id": 9}
        auth_throttle._set_cached_gateway_caller("cached-key", caller)
        db = MagicMock()
        result = get_current_gateway_or_user(
            request=_make_request(), x_api_key="cached-key", token=None, db=db)
        assert result == caller
        # 不查 key (无 SELECT .first()); UPDATE 是节流放行的独立写, 与 key 校验无关
        db.query.return_value.filter.return_value.first.assert_not_called()

    def test_cache_hit_throttles_last_used_update(self):
        """缓存命中: 首次节流放行 → UPDATE; 同 key_id 窗口内二次 → 跳过 UPDATE。"""
        caller = {"type": "gateway", "key_id": 11, "client_id": 1}
        auth_throttle._set_cached_gateway_caller("k", caller)
        db1 = _make_db()
        get_current_gateway_or_user(
            request=_make_request(), x_api_key="k", token=None, db=db1)
        db1.query.return_value.filter.return_value.update.assert_called_once()
        # 第二次同 key_id 节流窗口内 → 不 UPDATE
        db2 = _make_db()
        get_current_gateway_or_user(
            request=_make_request(), x_api_key="k", token=None, db=db2)
        db2.query.return_value.filter.return_value.update.assert_not_called()


# ────────────────────────────────────────────────────────────────────
# _reset_gateway_auth_caches
# ────────────────────────────────────────────────────────────────────
class TestResetCaches:
    def test_reset_clears_in_place_preserving_identity(self):
        """clear() 原地清空, dict 对象身份不变 (telemetry re-import 共享同一对象)。"""
        auth_throttle._last_used_recorded_at[999] = 1.0
        auth_throttle._set_cached_gateway_caller("x", {"type": "gateway"})
        lu_id = id(auth_throttle._last_used_recorded_at)
        cache_id = id(auth_throttle._gateway_caller_cache)
        auth_throttle._reset_gateway_auth_caches()
        assert 999 not in auth_throttle._last_used_recorded_at
        assert "x" not in auth_throttle._gateway_caller_cache
        assert id(auth_throttle._last_used_recorded_at) == lu_id
        assert id(auth_throttle._gateway_caller_cache) == cache_id
