"""Final coverage push — cover the last uncovered lines of the core modules.

Targets (baseline: 696 tests, 98% total; ocpp_adapter 97%, main/db_migration 99%):

adapters/ocpp_adapter.py:
  * L541-544  ImportError fallback (_HAS_OCPP=False) when the `ocpp` package
              is not installed.
  * L901-905, L912-913, L917, L924, L931, L938, L945
              TianlianChargePoint @after handler bodies. In ocpp==2.1.0 the
              `_after_action` hook only fires for *incoming* CALLs (see
              ChargePoint._handle_call), but these are CP->CSMS actions the
              CSMS never sends, so they are unreachable over the wire. We
              capture the handlers at class-definition time (the class is
              re-defined on every _run_real_charger() call) and invoke them
              directly.
  * L1037-1038 pending heartbeat/meter task cancellation after asyncio.wait
              returns FIRST_COMPLETED.
  * L1041-1048 except ConnectionClosed body: reconnect path while running,
              plain return when stopped.

main.py:
  * L46   sys.path.insert when the project root is missing from sys.path.
  * L567  asyncio.run(main()) under `if __name__ == "__main__"`.

db_migration.py:
  * L271  main() under `if __name__ == "__main__"` (exit-0 and exit-1 paths).
"""

import asyncio
import builtins
import importlib.util
import runpy
import sqlite3
import sys
from pathlib import Path

import pytest

# Ensure tests/ dir on path for mock_csms_server import
sys.path.insert(0, str(Path(__file__).parent))

from mock_csms_server import MockCSMSServer

from adapters.ocpp_adapter import OCPPAdapter
from config import OCPPConfig

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


# ── ocpp_adapter: ImportError fallback (L541-544) ───────────────────────


class TestOCPPImportFallback:
    """Module must degrade gracefully when the `ocpp` package is absent."""

    def test_has_ocpp_false_when_package_missing(self, monkeypatch):
        real_import = builtins.__import__

        def blocking_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "ocpp" or name.startswith("ocpp."):
                raise ImportError(f"No module named {name!r} (blocked by test)")
            return real_import(name, globals, locals, fromlist, level)

        monkeypatch.setattr(builtins, "__import__", blocking_import)

        # Load a fresh copy of the module so the conditional import re-runs
        spec = importlib.util.spec_from_file_location(
            "_ocpp_adapter_without_pkg", _PROJECT_ROOT / "adapters" / "ocpp_adapter.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        assert module._HAS_OCPP is False
        assert module._ocpp_call is None
        assert module._ocpp_call_result is None


# ── ocpp_adapter: @after handler bodies (L901-945) ──────────────────────


class TestRealChargerAfterHandlers:
    """Capture TianlianChargePoint @after handlers and invoke them directly.

    Unreachable via the wire protocol in ocpp==2.1.0 (after-hooks only fire
    for incoming CALLs; BootNotification/Heartbeat/etc. are CP->CSMS only).
    """

    @pytest.mark.asyncio
    async def test_after_handlers_captured_and_invoked(self, monkeypatch):
        import ocpp.routing as ocpp_routing
        import websockets

        captured = {}
        real_after = ocpp_routing.after

        def capturing_after(action):
            decorator = real_after(action)

            def wrapper(fn):
                captured[fn.__name__] = fn
                return decorator(fn)

            return wrapper

        monkeypatch.setattr(ocpp_routing, "after", capturing_after)

        class FailingConnect:
            """Aborts _run_real_charger right after the class is defined."""

            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                raise ConnectionRefusedError("test: no CSMS available")

            async def __aexit__(self, *exc):
                return False

        monkeypatch.setattr(websockets, "connect", lambda *a, **k: FailingConnect())

        config = OCPPConfig(
            charger_id="AFTER-CP-001",
            ws_url="ws://127.0.0.1:19999",
            heartbeat_interval=1,
            meter_sample_interval=1,
            use_real_charger=True,
        )
        adapter = OCPPAdapter(config)
        adapter._running = False  # generic except path returns quietly

        await adapter._run_real_charger()

        # Class body executed -> all seven @after handlers captured
        assert set(captured) == {
            "after_boot_notification",
            "after_heartbeat",
            "after_meter_values",
            "after_status_notification",
            "after_start_transaction",
            "after_stop_transaction",
            "after_authorize",
        }

        # Invoke each handler body directly (`self` is unused in all bodies)
        await captured["after_boot_notification"](
            None, charge_point_vendor="TestVendor", charge_point_model="TestModel"
        )
        await captured["after_heartbeat"](None)
        await captured["after_meter_values"](None, connector_id=1, meter_value=[1, 2])
        await captured["after_status_notification"](
            None, connector_id=1, error_code="NoError", status="Available"
        )
        await captured["after_start_transaction"](
            None, connector_id=1, id_tag="TAG-1", meter_start=10
        )
        await captured["after_stop_transaction"](None, transaction_id=42, meter_stop=100)
        await captured["after_authorize"](None, id_tag="TAG-1")

        # boot/heartbeat handlers built protocol messages
        req_actions = [m.action for m in adapter.message_log if m.direction == "req"]
        assert "BootNotification" in req_actions
        assert "Heartbeat" in req_actions


# ── ocpp_adapter: asyncio.wait pending-cancel path (L1037-1038) ─────────


class TestMainLoopPendingCancel:
    """Stop flag ends the heartbeat loop -> asyncio.wait returns -> pending
    meter task gets cancelled (L1037-1038)."""

    @pytest.mark.asyncio
    async def test_stop_flag_cancels_pending_loop_task(self):
        server = MockCSMSServer(host="127.0.0.1", port=19882)
        await server.start()

        config = OCPPConfig(
            charger_id="PEND-CP-001",
            ws_url="ws://127.0.0.1:19882",
            heartbeat_interval=0.05,
            meter_sample_interval=5.0,  # long: still asleep when heartbeat exits
            use_real_charger=True,
        )
        adapter = OCPPAdapter(config)
        adapter._running = True
        task = asyncio.create_task(adapter._run_real_charger())

        try:
            # Wait for BootNotification to reach the CSMS (main loop entered)
            for _ in range(60):
                if server.boot_notifications:
                    break
                await asyncio.sleep(0.05)
            assert server.boot_notifications, "BootNotification not received within 3s"

            # Let both loops run a couple of cycles
            await asyncio.sleep(0.2)

            # Heartbeat loop wakes within ~50ms and breaks; asyncio.wait then
            # returns FIRST_COMPLETED and cancels the still-sleeping meter task.
            adapter._running = False
            await asyncio.wait_for(task, timeout=5.0)
        finally:
            if not task.done():
                task.cancel()
            import contextlib
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
            await server.stop()

        assert adapter._ws_connected is False


# ── ocpp_adapter: ConnectionClosed handler (L1041-1048) ─────────────────


def _fake_connect_factory(mode_by_attempt):
    """Build a replacement for websockets.connect.

    mode_by_attempt: {attempt_number: mode}
      - "closed_on_send": ws.send() raises ConnectionClosed (mid BootNotification)
      - "abort":          __aenter__ raises SystemExit — a BaseException that
                          bypasses every outer reconnect/fallback handler, so
                          the recursion stops deterministically after one hop.
    """
    import websockets
    from websockets.exceptions import ConnectionClosed

    attempts = {"n": 0}

    class FakeWS:
        def __init__(self, mode):
            self._mode = mode

        async def send(self, data):
            if self._mode == "closed_on_send":
                raise ConnectionClosed(None, None)

        async def recv(self):
            await asyncio.sleep(3600)

        async def close(self):
            pass

    class FakeConnect:
        def __init__(self, *args, **kwargs):
            attempts["n"] += 1
            self._mode = mode_by_attempt.get(attempts["n"], "abort")

        async def __aenter__(self):
            if self._mode == "abort":
                raise SystemExit(42)  # test stop marker, not an Exception
            return FakeWS(self._mode)

        async def __aexit__(self, *exc):
            return False

    return lambda *a, **k: FakeConnect(), websockets


class TestConnectionClosedHandler:
    """Cover the except websockets.exceptions.ConnectionClosed body."""

    @pytest.mark.asyncio
    async def test_connection_closed_schedules_reconnect(self, monkeypatch):
        factory, websockets_mod = _fake_connect_factory(
            {1: "closed_on_send", 2: "abort"}
        )
        monkeypatch.setattr(websockets_mod, "connect", factory)

        config = OCPPConfig(
            charger_id="CC-CP-001",
            ws_url="ws://fake-csms:9999",
            heartbeat_interval=0.01,
            meter_sample_interval=0.01,
            use_real_charger=True,
        )
        adapter = OCPPAdapter(config)
        adapter._running = True

        # Attempt 1: ConnectionClosed during BootNotification -> inner handler
        # logs, sleeps and recurs. Attempt 2 aborts with SystemExit, which no
        # reconnect handler catches, so it propagates straight out.
        with pytest.raises(SystemExit):
            await adapter._run_real_charger()
        assert adapter._ws_connected is False

    @pytest.mark.asyncio
    async def test_connection_closed_stopped_returns(self, monkeypatch):
        factory, websockets_mod = _fake_connect_factory({1: "closed_on_send"})
        monkeypatch.setattr(websockets_mod, "connect", factory)

        config = OCPPConfig(
            charger_id="CC-CP-002",
            ws_url="ws://fake-csms:9999",
            heartbeat_interval=0.01,
            meter_sample_interval=0.01,
            use_real_charger=True,
        )
        adapter = OCPPAdapter(config)
        adapter._running = False

        # Not running -> no reconnect, plain return
        result = await adapter._run_real_charger()
        assert result is None
        assert adapter._ws_connected is False


# ── main.py: sys.path insertion (L46) + __main__ block (L567) ───────────


class TestMainModuleEntry:
    def test_project_root_inserted_when_missing(self):
        root = str(_PROJECT_ROOT.resolve())
        saved_main = sys.modules.pop("main", None)
        saved_path = sys.path[:]
        # Drop every entry that resolves to the project root
        sys.path[:] = [
            p for p in sys.path
            if not p or str(Path(p).resolve()) != root
        ]
        try:
            # Load main.py by file path (the finder cannot see it anymore);
            # its module-level guard must re-insert the project root (L45-46).
            spec = importlib.util.spec_from_file_location(
                "main", _PROJECT_ROOT / "main.py"
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            assert any(p and str(Path(p).resolve()) == root for p in sys.path)
        finally:
            sys.path[:] = saved_path
            if saved_main is not None:
                sys.modules["main"] = saved_main

    def test_main_block_calls_asyncio_run(self, monkeypatch):
        captured = []

        def fake_run(coro, **kwargs):
            captured.append(coro)
            coro.close()  # avoid "never awaited" warnings

        monkeypatch.setattr(asyncio, "run", fake_run)
        runpy.run_path(str(_PROJECT_ROOT / "main.py"), run_name="__main__")

        assert len(captured) == 1
        assert captured[0].__name__ == "main"


# ── db_migration.py: __main__ block (L271) ──────────────────────────────


class TestDbMigrationMainBlock:
    def test_main_block_migration_success_exits_0(self, tmp_path, monkeypatch):
        # Old-schema DB: telemetry_cache without the newer columns
        db_file = tmp_path / "old_schema.db"
        conn = sqlite3.connect(str(db_file))
        conn.execute(
            "CREATE TABLE telemetry_cache ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "device_id TEXT NOT NULL, "
            "payload TEXT NOT NULL, "
            "created_at TEXT NOT NULL)"
        )
        conn.commit()
        conn.close()

        monkeypatch.setattr(sys, "argv", ["db_migration.py", str(db_file)])
        with pytest.raises(SystemExit) as exc_info:
            runpy.run_path(str(_PROJECT_ROOT / "db_migration.py"), run_name="__main__")
        assert exc_info.value.code == 0

        # Schema actually upgraded
        conn = sqlite3.connect(str(db_file))
        cols = {r[1] for r in conn.execute("PRAGMA table_info(telemetry_cache)")}
        tables = {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        conn.close()
        assert {"alarm_cache", "gateway_state"} <= tables
        assert {"cached_at", "retry_count", "synced", "cloud_synced", "priority"} <= cols

    def test_main_block_migration_failure_exits_1(self, tmp_path, monkeypatch):
        # A directory cannot be opened as a SQLite DB -> OperationalError
        bad_path = tmp_path / "not_a_db"
        bad_path.mkdir()

        monkeypatch.setattr(sys, "argv", ["db_migration.py", str(bad_path)])
        with pytest.raises(SystemExit) as exc_info:
            runpy.run_path(str(_PROJECT_ROOT / "db_migration.py"), run_name="__main__")
        assert exc_info.value.code == 1
