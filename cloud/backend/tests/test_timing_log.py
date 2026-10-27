"""请求级 timing 分段埋点单元测试 (卡 f78a8e44)

验证 emit_write_timing 输出的固定键与 warning/info 阈值, 供生产 journalctl
grep "total_ms" 抓慢请求突发窗。仅测纯函数行为, 不依赖 DB / 端点 fixture。
"""
import logging

from app.core.timing_log import emit_write_timing, SLOW_THRESHOLD_MS


def _joined(caplog) -> str:
    """合并所有日志记录的 message, 便于对固定键做子串断言"""
    return " ".join(rec.getMessage() for rec in caplog.records)


def test_emit_timing_info_when_fast_has_all_fixed_keys(caplog):
    """快请求(<阈值)走 info, 输出含全部固定键, key=value 紧凑格式可 grep"""
    caplog.set_level(logging.INFO, logger="app.core.timing_log")
    emit_write_timing(
        "telemetry/batch-report", 3,
        auth_ms=1.0, parse_ms=2.0, insert_ms=10.0, commit_ms=5.0,
        total_ms=18.0,
    )
    msgs = _joined(caplog)
    assert "write_request_timing" in msgs
    for key_val in (
        "endpoint=telemetry/batch-report",
        "batch_size=3",
        "total_ms=18.0",
        "auth_ms=1.0",
        "parse_ms=2.0",
        "insert_ms=10.0",
        "commit_ms=5.0",
    ):
        assert key_val in msgs, f"缺少固定键: {key_val}"
    # 快请求不得触发 warning
    assert all(r.levelno < logging.WARNING for r in caplog.records)


def test_emit_timing_warning_when_slow(caplog):
    """慢请求(>=阈值)走 warning, 仍含固定键"""
    caplog.set_level(logging.INFO, logger="app.core.timing_log")
    emit_write_timing(
        "pod/heartbeat", 1,
        auth_ms=0.0, parse_ms=5.0, insert_ms=2000.0, commit_ms=0.0,
        total_ms=2000.0,
    )
    msgs = _joined(caplog)
    assert "slow_write_request" in msgs
    assert "total_ms=2000.0" in msgs
    assert "insert_ms=2000.0" in msgs
    assert any(r.levelno >= logging.WARNING for r in caplog.records)


def test_slow_threshold_boundary_is_warning(caplog):
    """total_ms 恰等于阈值 → warning(>=, 边界含)"""
    caplog.set_level(logging.INFO, logger="app.core.timing_log")
    emit_write_timing(
        "telemetry/batch-report", 0,
        auth_ms=0.0, parse_ms=0.0, insert_ms=0.0, commit_ms=0.0,
        total_ms=SLOW_THRESHOLD_MS,
    )
    assert any(r.levelno >= logging.WARNING for r in caplog.records)
