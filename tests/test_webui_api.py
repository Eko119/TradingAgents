"""Web console API tests — real ThreadingHTTPServer on an ephemeral port.

Deterministic and offline: results live in a temp directory, run launches
are exercised only through validation paths or a stubbed subprocess.
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from unittest.mock import MagicMock, patch

import pytest

from webui.runner import write_status
from webui.runs import RunError, RunManager, validate_run_request
from webui.server import ConsoleState, make_server


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def results_tree(tmp_path):
    """A results dir with one completed analysis and one junk entry."""
    run = tmp_path / "results" / "NVDA" / "2026-05-01"
    (run / "reports").mkdir(parents=True)
    (run / "reports" / "market_report.md").write_text("# Market\n\n**Strong** uptrend.")
    (run / "reports" / "final_trade_decision.md").write_text("Decision: BUY")
    write_status(run, status="completed", decision="BUY")
    # Junk that the listing must skip.
    (tmp_path / "results" / "NVDA" / "not-a-date").mkdir()
    (tmp_path / "results" / ".hidden~dir").mkdir()
    return tmp_path / "results"


@pytest.fixture()
def console(results_tree, tmp_path):
    state = ConsoleState(config={
        "results_dir": str(results_tree),
        "memory_log_path": str(tmp_path / "memory.md"),
        "llm_provider": "openai",
    })
    server = make_server("127.0.0.1", 0, state=state)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    yield base, state
    server.shutdown()
    server.server_close()


def get(base, path):
    with urllib.request.urlopen(base + path, timeout=5) as resp:
        return resp.status, json.loads(resp.read())


def get_raw(base, path):
    with urllib.request.urlopen(base + path, timeout=5) as resp:
        return resp.status, resp.read(), dict(resp.headers)


def post(base, path, payload):
    req = urllib.request.Request(
        base + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        return resp.status, json.loads(resp.read())


def expect_http_error(fn, *args):
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        fn(*args)
    err = exc_info.value
    return err.code, json.loads(err.read())


# ---------------------------------------------------------------------------
# request validation (no server needed)
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestRunValidation:
    def test_normalizes_ticker(self):
        assert validate_run_request("nvda ", "2026-05-01", "stock")[0] == "NVDA"

    @pytest.mark.parametrize("ticker", ["../etc", "", "A/B", "." , ".."])
    def test_rejects_unsafe_tickers(self, ticker):
        with pytest.raises(RunError):
            validate_run_request(ticker, "2026-05-01", "stock")

    @pytest.mark.parametrize("date", ["2026-13-01", "2026-02-30", "yesterday", "2026/05/01"])
    def test_rejects_bad_dates(self, date):
        with pytest.raises(RunError):
            validate_run_request("NVDA", date, "stock")

    def test_rejects_bad_asset_type(self):
        with pytest.raises(RunError):
            validate_run_request("NVDA", "2026-05-01", "bond")


# ---------------------------------------------------------------------------
# HTTP surface
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestApi:
    def test_health(self, console):
        base, _ = console
        status, body = get(base, "/api/health")
        assert status == 200 and body["status"] == "ok"

    def test_index_served_with_security_headers(self, console):
        base, _ = console
        status, body, headers = get_raw(base, "/")
        assert status == 200 and b"TradingAgents" in body
        assert headers["X-Content-Type-Options"] == "nosniff"
        assert "default-src 'self'" in headers["Content-Security-Policy"]

    def test_results_listing_skips_junk(self, console):
        base, _ = console
        _, body = get(base, "/api/results")
        assert [(r["ticker"], r["date"]) for r in body["results"]] == [("NVDA", "2026-05-01")]
        assert body["results"][0]["decision"] == "BUY"

    def test_result_detail_and_export(self, console):
        base, _ = console
        _, body = get(base, "/api/results/NVDA/2026-05-01")
        assert "market_report" in body["sections"]
        assert body["status"]["status"] == "completed"
        status, raw, headers = get_raw(base, "/api/results/NVDA/2026-05-01/export")
        assert status == 200 and b"Market" in raw
        assert "attachment" in headers["Content-Disposition"]

    def test_unknown_result_404(self, console):
        base, _ = console
        code, body = expect_http_error(get, base, "/api/results/TSLA/2026-01-01")
        assert code == 404 and "error" in body

    def test_path_traversal_rejected(self, console):
        base, _ = console
        code, _ = expect_http_error(get, base, "/api/results/..%2f..%2fetc/2026-05-01")
        assert code in (400, 404)
        code, _ = expect_http_error(get, base, "/api/results/NVDA/..%2freports")
        assert code in (400, 404)

    def test_static_whitelist(self, console):
        base, _ = console
        status, _, _ = get_raw(base, "/static/app.css")
        assert status == 200
        code, _ = expect_http_error(get, base, "/static/../server.py")
        assert code == 404

    def test_config_never_exposes_key_values(self, console, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-supersecret-123")
        base, _ = console
        status, raw, _ = get_raw(base, "/api/config")
        assert status == 200
        assert b"sk-supersecret-123" not in raw
        body = json.loads(raw)
        assert body["providers"]["openai"]["key_set"] is True
        assert body["providers"]["ollama"]["key_set"] is None

    def test_memory_empty_state(self, console):
        base, _ = console
        _, body = get(base, "/api/memory")
        assert body["markdown"] is None


@pytest.mark.unit
class TestRunEndpoint:
    def test_post_rejects_bad_ticker(self, console):
        base, _ = console
        code, body = expect_http_error(post, base, "/api/runs", {"ticker": "../x", "date": "2026-05-01"})
        assert code == 400 and "ticker" in body["error"]

    def test_post_rejects_missing_body(self, console):
        base, _ = console
        req = urllib.request.Request(base + "/api/runs", data=b"", method="POST")
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req, timeout=5)
        assert e.value.code == 400

    def test_post_409_when_key_missing(self, console, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        base, _ = console
        code, body = expect_http_error(post, base, "/api/runs", {"ticker": "NVDA", "date": "2026-05-01"})
        assert code == 409 and "OPENAI_API_KEY" in body["error"]

    def test_post_starts_subprocess(self, console):
        base, state = console
        fake = MagicMock()
        fake.poll.return_value = None
        with patch("webui.runs.subprocess.Popen", return_value=fake) as popen:
            status, body = post(base, "/api/runs", {"ticker": "msft", "date": "2026-05-02"})
        assert status == 201
        assert body["ticker"] == "MSFT" and body["status"] in ("starting", "running")
        argv = popen.call_args.args[0]
        assert "-m" in argv and "webui.runner" in argv and "MSFT" in argv
        # Status is visible through GET while "running".
        _, run = get(base, f"/api/runs/{body['id']}")
        assert run["status"] in ("starting", "running")


# ---------------------------------------------------------------------------
# run manager semantics
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestRunManager:
    def _manager(self, tmp_path, poll=None):
        mgr = RunManager(tmp_path, max_concurrent=1)
        fake = MagicMock()
        fake.poll.return_value = poll
        return mgr, fake

    def test_concurrency_limit(self, tmp_path):
        mgr, fake = self._manager(tmp_path)
        with patch("webui.runs.subprocess.Popen", return_value=fake):
            mgr.start("NVDA", "2026-05-01")
            with pytest.raises(RunError, match="limit"):
                mgr.start("AAPL", "2026-05-01")

    def test_dead_runner_without_status_reports_failed(self, tmp_path):
        mgr, fake = self._manager(tmp_path, poll=137)
        with patch("webui.runs.subprocess.Popen", return_value=fake):
            run = mgr.start("NVDA", "2026-05-01")
        described = mgr.describe(run["id"])
        assert described["status"] == "failed"
        assert "exited with code 137" in described["error"]

    def test_status_file_drives_completion(self, tmp_path):
        mgr, fake = self._manager(tmp_path, poll=0)
        with patch("webui.runs.subprocess.Popen", return_value=fake):
            run = mgr.start("NVDA", "2026-05-01")
        write_status(tmp_path / "NVDA" / "2026-05-01",
                     status="completed", decision="HOLD", finished_at="x")
        described = mgr.describe(run["id"])
        assert described["status"] == "completed" and described["decision"] == "HOLD"
