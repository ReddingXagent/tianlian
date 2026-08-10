"""Coverage boost for api/server.py remaining uncovered lines.

Covers:
- L341-350: run_api() function execution
- _format_uptime() all branches (days/hours/minutes present)
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.server import _format_uptime, run_api
from config import LocalAPIConfig


class TestFormatUptime:
    """Cover all branches of _format_uptime."""

    def test_seconds_only(self):
        assert _format_uptime(45) == "45s"

    def test_minutes_and_seconds(self):
        assert _format_uptime(125) == "2m 5s"

    def test_hours_minutes_seconds(self):
        assert _format_uptime(3725) == "1h 2m 5s"

    def test_days_hours_minutes_seconds(self):
        assert _format_uptime(90061) == "1d 1h 1m 1s"

    def test_zero_seconds(self):
        assert _format_uptime(0) == "0s"


class TestRunApi:
    """Cover run_api() execution path."""

    @pytest.mark.asyncio
    async def test_run_api_starts_server(self):
        """run_api should create uvicorn server and call serve()."""
        config = LocalAPIConfig(host="127.0.0.1", port=18899)

        mock_server = MagicMock()
        mock_server.serve = AsyncMock()

        with patch("uvicorn.Server", return_value=mock_server):
            with patch("uvicorn.Config") as mock_uv_config:
                app = MagicMock()
                await run_api(config, app)

        mock_server.serve.assert_awaited_once()
        mock_uv_config.assert_called_once()
