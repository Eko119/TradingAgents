"""Regression test: Alpha Vantage HTTP requests must carry a timeout.

A requests call without ``timeout=`` blocks forever on a stalled
connection, hanging the whole analysis pipeline.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tradingagents.dataflows import alpha_vantage_common


@pytest.mark.unit
class TestAlphaVantageRequestTimeout:
    def test_make_api_request_passes_timeout(self):
        response = MagicMock()
        response.text = "timestamp,open\n2026-01-02,100\n"
        with patch.object(alpha_vantage_common.requests, "get", return_value=response) as mock_get:
            alpha_vantage_common._make_api_request("TIME_SERIES_DAILY", {"symbol": "NVDA"})
        assert mock_get.call_args.kwargs.get("timeout") == alpha_vantage_common.REQUEST_TIMEOUT_SECONDS

    def test_timeout_constant_is_bounded(self):
        assert 0 < alpha_vantage_common.REQUEST_TIMEOUT_SECONDS <= 120
