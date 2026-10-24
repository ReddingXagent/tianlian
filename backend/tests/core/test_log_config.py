"""
app/core/log_config.py 日志链路测试补全 — 六维度覆盖

维度:
  1. _sanitize_log_message   — 敏感字段脱敏 / 普通消息不变 / 非 str 透传
  2. JsonFormatter           — 合法 JSON / 必备字段 / UTC 时间戳 / extra 透传 / 异常脱敏
  3. RequestIDFilter + ctx   — contextvars set/get + filter 注入 record + 默认 "-"
  4. log_slow_query          — >=100ms WARNING / >=1000ms ERROR (含等号) + extra
  5. generate_request_id     — 16 位小写 hex / 2000 次唯一
  6. get_log_level           — 5 级映射 / 非法回落 INFO / LOG_LEVEL 环境变量 (importlib.reload)

注意:
  - 实现用模块自有 _SENSITIVE_PATTERNS (正则脱敏成 ****), 不是 app.utils.sanitize
  - 无 get_client_ip getter, client_ip 只能经 RequestIDFilter 验证
  - contextvar 测试用 contextvars.Context().run() 隔离, 防止 set 泄漏到其它测试
  - 所有符号经 log_config.X 访问 (模块属性), 以承受末尾 reload 测试的身份变更
"""
import contextvars
import json
import logging
import os
from datetime import timedelta

import pytest

from app.core import log_config


# ────────────────────────────────────────────────────────────────────
# 维度 1: _sanitize_log_message
# ────────────────────────────────────────────────────────────────────
class TestSanitizeLogMessage:
    """敏感信息脱敏: 走模块自有 _SENSITIVE_PATTERNS 正则, 替换为 ****。"""

    def test_password_string_masked(self):
        result = log_config._sanitize_log_message("password=super-secret-123")
        assert "super-secret-123" not in result
        assert "****" in result

    def test_token_string_masked(self):
        result = log_config._sanitize_log_message("token=eyJhbGci.payload.sig")
        assert "eyJhbGci.payload.sig" not in result
        assert "****" in result

    def test_api_key_string_masked(self):
        result = log_config._sanitize_log_message("api_key=AKIAIOSFODNN7EXAMPLE")
        assert "AKIAIOSFODNN7EXAMPLE" not in result
        assert "****" in result

    def test_dict_sensitive_fields_masked(self):
        """dict 经 str() 格式化后进日志链路, 三个敏感字段明文必须全部消失。"""
        payload = {"password": "secret123", "api_key": "AKIA9999", "token": "tok-xyz"}
        formatted = str(payload)
        sanitized = log_config._sanitize_log_message(formatted)
        assert "secret123" not in sanitized
        assert "AKIA9999" not in sanitized
        assert "tok-xyz" not in sanitized
        assert "****" in sanitized

    def test_normal_message_unchanged(self):
        """无敏感模式的普通消息 (含中文/常规键值) 原样透传。"""
        msg = "订单创建成功 action=login result=success count=5 用户=alice"
        assert log_config._sanitize_log_message(msg) == msg

    def test_non_str_returned_as_is(self):
        """非 str 输入 (dict/int/None/float) 直接返回, 不做脱敏。"""
        payload = {"password": "leak-me"}
        # 同一对象, 内容不变 (非 str 不进正则链路)
        assert log_config._sanitize_log_message(payload) is payload
        assert log_config._sanitize_log_message(12345) == 12345
        assert log_config._sanitize_log_message(None) is None
        assert log_config._sanitize_log_message(3.14) == 3.14


# ────────────────────────────────────────────────────────────────────
# 维度 2: JsonFormatter
# ────────────────────────────────────────────────────────────────────
class TestJsonFormatter:
    """JSON 行格式化: 合法 JSON / 必备字段 / UTC / extra 透传 / 异常脱敏。"""

    @staticmethod
    def _make_record(msg="hello %s", args=("world",), exc_info=None, level=logging.INFO):
        return logging.LogRecord(
            name="app.test.module", level=level, pathname=__file__, lineno=10,
            msg=msg, args=args, exc_info=exc_info,
        )

    def test_output_valid_json_with_required_fields(self):
        record = self._make_record()
        out = json.loads(log_config.JsonFormatter().format(record))
        # 顶层必备字段齐备
        for key in ("timestamp", "level", "module", "message",
                    "request_id", "user_id", "client_ip"):
            assert key in out
        assert out["level"] == "INFO"
        assert out["module"] == "app.test.module"
        assert out["message"] == "hello world"
        # 无 context 时缺省 "-"
        assert out["request_id"] == "-"
        assert out["user_id"] == "-"

    def test_timestamp_is_utc(self):
        record = self._make_record()
        out = json.loads(log_config.JsonFormatter().format(record))
        ts = out["timestamp"]
        # ISO 字符串以 +00:00 结尾 (UTC)
        assert ts.endswith("+00:00")
        from datetime import datetime
        dt = datetime.fromisoformat(ts)
        assert dt.utcoffset() == timedelta(0)

    def test_extra_fields_passthrough(self):
        """extra 白名单字段 (path/method/status_code/duration_ms/query_time_ms) 透传。"""
        record = self._make_record()
        record.query_time_ms = 42.5
        record.status_code = 200
        record.duration_ms = 7
        record.path = "/api/v1/test"
        record.method = "GET"
        out = json.loads(log_config.JsonFormatter().format(record))
        assert out["query_time_ms"] == 42.5
        assert out["status_code"] == 200
        assert out["duration_ms"] == 7
        assert out["path"] == "/api/v1/test"
        assert out["method"] == "GET"

    def test_extra_absent_when_not_set(self):
        """record 未带 extra 白名单字段时, 输出 JSON 不含这些键。"""
        record = self._make_record()
        out = json.loads(log_config.JsonFormatter().format(record))
        for key in ("path", "method", "status_code", "duration_ms", "query_time_ms"):
            assert key not in out

    def test_exception_field_sanitized(self):
        """exc_info 写入 exception 字段, 且其中的敏感明文被脱敏。"""
        import sys
        try:
            raise ValueError("auth failed password=hunter2 token=tok-abc")
        except ValueError:
            record = self._make_record(
                msg="operation failed", args=None, exc_info=sys.exc_info(),
                level=logging.ERROR,
            )
        out = json.loads(log_config.JsonFormatter().format(record))
        assert "exception" in out
        assert "hunter2" not in out["exception"]
        assert "tok-abc" not in out["exception"]
        assert "****" in out["exception"]

    def test_message_sanitized_in_output(self):
        """formatter 对 message 字段也走脱敏。"""
        record = self._make_record(msg="login password=p@ss-123", args=None)
        out = json.loads(log_config.JsonFormatter().format(record))
        assert "p@ss-123" not in out["message"]
        assert "****" in out["message"]


# ────────────────────────────────────────────────────────────────────
# 维度 3: RequestIDFilter + contextvars
# ────────────────────────────────────────────────────────────────────
class TestRequestIDFilterContextvars:
    """contextvars set/get + RequestIDFilter 注入 record + 默认值。

    用 contextvars.Context().run() 隔离, 防 set 泄漏到其它测试。
    无 get_client_ip getter, client_ip 仅经 filter 验证。
    """

    @staticmethod
    def _make_record():
        return logging.LogRecord(
            name="app.test", level=logging.INFO, pathname=__file__, lineno=1,
            msg="msg", args=None, exc_info=None,
        )

    def test_defaults_when_unset(self):
        def body():
            assert log_config.get_request_id() == "-"
            assert log_config.get_user_id() == "-"
        contextvars.Context().run(body)

    def test_set_and_get_request_id(self):
        def body():
            log_config.set_request_id("rid-abc-123")
            assert log_config.get_request_id() == "rid-abc-123"
        contextvars.Context().run(body)

    def test_set_user_id_stringifies(self):
        def body():
            log_config.set_user_id(42)
            assert log_config.get_user_id() == "42"  # str() 强转
        contextvars.Context().run(body)

    def test_filter_injects_from_context(self):
        def body():
            log_config.set_request_id("rid-xyz")
            log_config.set_user_id(7)
            log_config.set_client_ip("10.0.0.5")
            record = self._make_record()
            assert log_config.RequestIDFilter().filter(record) is True
            assert record.request_id == "rid-xyz"
            assert record.user_id == "7"
            assert record.client_ip == "10.0.0.5"
        contextvars.Context().run(body)

    def test_filter_defaults_when_unset(self):
        def body():
            record = self._make_record()
            assert log_config.RequestIDFilter().filter(record) is True
            assert record.request_id == "-"
            assert record.user_id == "-"
            assert record.client_ip == "-"
        contextvars.Context().run(body)

    def test_filter_record_attr_precedence(self):
        """record 上已有的真值 request_id 优先于 contextvar。"""
        def body():
            log_config.set_request_id("from-ctx")
            record = self._make_record()
            record.request_id = "from-attr"
            log_config.RequestIDFilter().filter(record)
            assert record.request_id == "from-attr"
            # 不设 record 属性时回落到 contextvar
            record2 = self._make_record()
            log_config.RequestIDFilter().filter(record2)
            assert record2.request_id == "from-ctx"
        contextvars.Context().run(body)


# ────────────────────────────────────────────────────────────────────
# 维度 4: log_slow_query
# ────────────────────────────────────────────────────────────────────
class TestLogSlowQuery:
    """>=1000ms ERROR / >=100ms WARNING (含等号) / 否则 INFO, 带 query_time_ms extra。"""

    @staticmethod
    def _slow_records(caplog):
        """返回 app.db.slow_query logger 产出的 record 列表。"""
        return [r for r in caplog.records if r.name == "app.db.slow_query"]

    def test_warning_at_100ms_boundary(self, caplog):
        caplog.set_level(logging.DEBUG)
        log_config.log_slow_query("find_devices", 100.0, "ids=1,2,3")
        recs = self._slow_records(caplog)
        assert recs
        assert recs[-1].levelno == logging.WARNING

    def test_warning_mid_range(self, caplog):
        caplog.set_level(logging.DEBUG)
        log_config.log_slow_query("find_devices", 542.7, "ids=1,2,3")
        recs = self._slow_records(caplog)
        assert recs[-1].levelno == logging.WARNING

    def test_error_at_1000ms_boundary(self, caplog):
        caplog.set_level(logging.DEBUG)
        log_config.log_slow_query("agg_report", 1000.0, "range=30d")
        recs = self._slow_records(caplog)
        assert recs[-1].levelno == logging.ERROR

    def test_error_above_1000ms(self, caplog):
        caplog.set_level(logging.DEBUG)
        log_config.log_slow_query("agg_report", 2500.0, "range=30d")
        recs = self._slow_records(caplog)
        assert recs[-1].levelno == logging.ERROR

    def test_info_below_100ms(self, caplog):
        # 必须在 log_slow_query 之前 set_level: 否则 INFO(20) < root 默认 WARNING(30)
        # 被过滤 (WARNING/ERROR 因级别够高才侥幸通过)
        caplog.set_level(logging.DEBUG)
        log_config.log_slow_query("fast_q", 50.0, "ok")
        recs = self._slow_records(caplog)
        assert recs[-1].levelno == logging.INFO

    def test_query_time_ms_extra_attached(self, caplog):
        caplog.set_level(logging.DEBUG)
        log_config.log_slow_query("find_devices", 123.456, "ids=1")
        recs = self._slow_records(caplog)
        # extra 经 round(_, 2) 保留两位
        assert recs[-1].query_time_ms == 123.46

    def test_message_contains_query_name_and_info(self, caplog):
        caplog.set_level(logging.DEBUG)
        log_config.log_slow_query("find_devices", 150.0, "filter=status=active")
        recs = self._slow_records(caplog)
        rendered = recs[-1].getMessage()
        assert "find_devices" in rendered
        assert "filter=status=active" in rendered
        assert "150.0ms" in rendered


# ────────────────────────────────────────────────────────────────────
# 维度 5: generate_request_id
# ────────────────────────────────────────────────────────────────────
class TestGenerateRequestId:
    """16 位小写 hex, 2000 次唯一。"""

    def test_length_is_16(self):
        for _ in range(100):
            assert len(log_config.generate_request_id()) == 16

    def test_lowercase_hex(self):
        for _ in range(100):
            rid = log_config.generate_request_id()
            assert all(c in "0123456789abcdef" for c in rid)

    def test_uniqueness_2000(self):
        ids = {log_config.generate_request_id() for _ in range(2000)}
        assert len(ids) == 2000


# ────────────────────────────────────────────────────────────────────
# 维度 6a: get_log_level (5 级映射 + 非法回落)
# ────────────────────────────────────────────────────────────────────
class TestGetLogLevel:
    """get_log_level 读模块级 LOG_LEVEL 查 LOG_LEVEL_MAP; 非法键回落 INFO。

    monkeypatch.setattr 改 LOG_LEVEL, 测完自动还原, 不污染 reload 测试。
    """

    @pytest.mark.parametrize("name,expected", [
        ("DEBUG", logging.DEBUG),
        ("INFO", logging.INFO),
        ("WARNING", logging.WARNING),
        ("ERROR", logging.ERROR),
        ("CRITICAL", logging.CRITICAL),
    ])
    def test_level_mapping(self, monkeypatch, name, expected):
        monkeypatch.setattr(log_config, "LOG_LEVEL", name)
        assert log_config.get_log_level() == expected

    def test_invalid_falls_back_to_info(self, monkeypatch):
        monkeypatch.setattr(log_config, "LOG_LEVEL", "TOTALLY_UNKNOWN")
        assert log_config.get_log_level() == logging.INFO


# ────────────────────────────────────────────────────────────────────
# 维度 7: get_request_logger (no-op LoggerAdapter 契约)
# ────────────────────────────────────────────────────────────────────
class TestGetRequestLogger:
    """get_request_logger 返回 extra 为空的 LoggerAdapter, 本身不绑定链路字段。

    request_id/user_id/client_ip 的注入由 RequestIDFilter 经 contextvars 在
    handler 层完成 (见 setup_logging 的 addFilter), 而非由本 adapter 绑定。
    """

    def test_returns_logger_adapter(self):
        adapter = log_config.get_request_logger("app.test.rl")
        assert isinstance(adapter, logging.LoggerAdapter)

    def test_wraps_named_logger(self):
        adapter = log_config.get_request_logger("app.test.rl.named")
        assert adapter.logger.name == "app.test.rl.named"

    def test_adapter_extra_empty_no_binding(self):
        """adapter.extra 为空 dict: 证明其不在此层绑定 request_id/user_id。"""
        adapter = log_config.get_request_logger("app.test.rl.empty")
        assert adapter.extra == {}


# ────────────────────────────────────────────────────────────────────
# 维度 8: setup_logging 初始化日志 (level/production/dir 并入 message)
# ────────────────────────────────────────────────────────────────────
class TestSetupLoggingInitInfo:
    """setup_logging 初始化日志把 level/production/dir 并入 message 文本。

    原先三键走 extra, 不在 JsonFormatter 白名单 → 生产 JSON 日志静默丢弃;
    且 extra 键 "level" 与 JSON 顶层 level (record.levelname) 同名会错误覆盖。
    现并入 message (经 getMessage() 渲染), 两种 formatter 下均可见。
    setup_logging 会改写 root logger 全局状态, 测试须保存/还原 handlers+level。
    """

    @staticmethod
    def _capture_root_state():
        root = logging.getLogger()
        return root, root.handlers[:], root.level

    @staticmethod
    def _restore_root_state(saved):
        root, saved_handlers, saved_level = saved
        new_handlers = [h for h in root.handlers if h not in saved_handlers]
        root.handlers[:] = saved_handlers
        root.setLevel(saved_level)
        for h in new_handlers:
            try:
                h.close()
            except Exception:
                pass

    def test_init_context_merged_into_message(self, tmp_path, monkeypatch):
        """init 行的 message 渲染后含 level/production/dir, 且不再走 extra。"""
        app_name = "tianlian-v3-init-unit"
        monkeypatch.setattr(log_config, "LOG_LEVEL", "INFO")
        monkeypatch.delenv("DEBUG", raising=False)  # → is_production=False

        logger = logging.getLogger(app_name)
        captured: dict = {}

        def spy(msg, *args, **kwargs):
            captured["msg"] = msg
            captured["args"] = args
            captured["extra"] = kwargs.get("extra")

        monkeypatch.setattr(logger, "info", spy)
        saved = self._capture_root_state()
        try:
            log_config.setup_logging(app_name=app_name, log_dir=tmp_path)
        finally:
            self._restore_root_state(saved)

        rendered = captured["msg"] % captured["args"]
        assert "日志系统初始化完成" in rendered
        assert "level=INFO" in rendered
        assert "production=False" in rendered
        assert "dir=" in rendered
        assert str(tmp_path) in rendered
        # 不再依赖会被 JSON 白名单丢弃的 extra
        assert captured["extra"] is None

    def test_init_context_present_in_production_json(self, tmp_path, monkeypatch):
        """生产 JSON 模式下, 初始化上下文并入 message, 不被 extra 白名单丢弃。"""
        monkeypatch.setenv("DEBUG", "false")  # production 模式
        monkeypatch.setattr(log_config, "LOG_LEVEL", "INFO")
        app_name = "tianlian-v3-init-json"

        saved = self._capture_root_state()
        try:
            log_config.setup_logging(app_name=app_name, log_dir=tmp_path)
        finally:
            self._restore_root_state(saved)

        log_file = tmp_path / f"{app_name}.log"
        assert log_file.exists(), f"日志文件未生成: {log_file}"
        entries = []
        for line in log_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                entries.append(json.loads(line))
        init_entries = [
            e for e in entries
            if str(e.get("message", "")).startswith("日志系统初始化完成")
        ]
        assert init_entries, "未找到初始化日志行"
        msg = init_entries[-1]["message"]
        assert "level=INFO" in msg
        assert "production=True" in msg  # production 模式
        assert "dir=" in msg
        assert str(tmp_path) in msg


# ────────────────────────────────────────────────────────────────────
# 维度 6b: LOG_LEVEL 环境变量解析 (importlib.reload + try/finally 还原)
# 放文件末尾: reload 会改变模块内符号身份, 留在最后避免影响其它测试。
# ────────────────────────────────────────────────────────────────────
class TestGetLogLevelEnvReload:
    """LOG_LEVEL 在 import 时经 .upper() 求值为模块常量, 测环境变量须 reload。

    finally 中还原环境变量并再次 reload, 把模块恢复到测试前状态。
    """

    def test_env_var_uppercased_and_applied(self):
        import importlib
        original = os.environ.get("LOG_LEVEL")
        try:
            os.environ["LOG_LEVEL"] = "warning"  # 小写, 验证 import 期 .upper()
            importlib.reload(log_config)
            assert log_config.LOG_LEVEL == "WARNING"
            assert log_config.get_log_level() == logging.WARNING
        finally:
            if original is None:
                os.environ.pop("LOG_LEVEL", None)
            else:
                os.environ["LOG_LEVEL"] = original
            importlib.reload(log_config)

    def test_env_var_invalid_falls_back_to_info(self):
        import importlib
        original = os.environ.get("LOG_LEVEL")
        try:
            os.environ["LOG_LEVEL"] = "not-a-real-level"
            importlib.reload(log_config)
            # .upper() 后仍不在 LOG_LEVEL_MAP → get_log_level 回落 INFO
            assert log_config.LOG_LEVEL == "NOT-A-REAL-LEVEL"
            assert log_config.get_log_level() == logging.INFO
        finally:
            if original is None:
                os.environ.pop("LOG_LEVEL", None)
            else:
                os.environ["LOG_LEVEL"] = original
            importlib.reload(log_config)
