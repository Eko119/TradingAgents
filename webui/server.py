"""HTTP server for the TradingAgents Web Console.

Stdlib-only (``http.server``): a small JSON API plus three static files.
Single-user, localhost-by-default — there is intentionally no auth layer,
so binding a non-loopback interface requires an explicit flag and warns.

Endpoints
    GET  /                                  console (index.html)
    GET  /static/<app.css|app.js>           assets
    GET  /api/health                        liveness + version
    GET  /api/config                        effective config, key status (booleans only)
    GET  /api/results                       persisted analyses
    GET  /api/results/<ticker>/<date>       report sections + log tail
    GET  /api/results/<ticker>/<date>/export   combined markdown download
    GET  /api/memory                        decision log markdown
    GET  /api/runs                          runs started by this server
    GET  /api/runs/<id>                     one run + log tail
    POST /api/runs                          launch an analysis
"""

from __future__ import annotations

import argparse
import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.metadata import PackageNotFoundError, version as pkg_version
from pathlib import Path

from tradingagents.dataflows.utils import safe_ticker_component
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.llm_clients.api_key_env import PROVIDER_API_KEY_ENV

from webui.runner import REPORT_SECTIONS, STATUS_FILENAME
from webui.runs import RunError, RunManager, tail_file

import os
import re

logger = logging.getLogger(__name__)

_STATIC_DIR = Path(__file__).parent / "static"
_STATIC_FILES = {
    "app.css": "text/css; charset=utf-8",
    "app.js": "application/javascript; charset=utf-8",
}
_DATE_DIR_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MAX_BODY_BYTES = 64 * 1024

# Keys whose values are safe to show. Everything else in config stays
# server-side; secrets never live in DEFAULT_CONFIG, but an allowlist is
# cheaper to reason about than a denylist.
_CONFIG_DISPLAY_KEYS = (
    "llm_provider", "deep_think_llm", "quick_think_llm", "backend_url",
    "temperature", "max_debate_rounds", "max_risk_discuss_rounds",
    "checkpoint_enabled", "output_language", "results_dir",
    "memory_log_path", "data_vendors",
)


def _app_version() -> str:
    try:
        return pkg_version("tradingagents")
    except PackageNotFoundError:
        return "dev"


class ConsoleState:
    """Shared state handed to every request handler."""

    def __init__(self, config: dict | None = None, run_manager: RunManager | None = None):
        self.config = dict(config or DEFAULT_CONFIG)
        self.results_dir = Path(self.config["results_dir"])
        self.run_manager = run_manager or RunManager(self.results_dir)

    # ---- data assembly (kept on the state object so tests can call it directly)

    def config_payload(self) -> dict:
        cfg = {k: self.config.get(k) for k in _CONFIG_DISPLAY_KEYS}
        cfg["results_dir"] = str(cfg["results_dir"])
        providers = {}
        for provider, env_var in PROVIDER_API_KEY_ENV.items():
            providers[provider] = {
                "env_var": env_var,
                "key_set": bool(os.environ.get(env_var)) if env_var else None,
            }
        return {"config": cfg, "providers": providers, "version": _app_version()}

    def list_results(self) -> list[dict]:
        out: list[dict] = []
        root = self.results_dir
        if not root.is_dir():
            return out
        for ticker_dir in sorted(root.iterdir()):
            if not ticker_dir.is_dir():
                continue
            try:
                safe_ticker_component(ticker_dir.name)
            except ValueError:
                continue
            for date_dir in sorted(ticker_dir.iterdir(), reverse=True):
                if not date_dir.is_dir() or not _DATE_DIR_RE.fullmatch(date_dir.name):
                    continue
                sections = []
                reports = date_dir / "reports"
                if reports.is_dir():
                    sections = sorted(
                        p.stem for p in reports.glob("*.md") if p.is_file()
                    )
                status = {}
                status_path = date_dir / STATUS_FILENAME
                if status_path.is_file():
                    try:
                        status = json.loads(status_path.read_text(encoding="utf-8"))
                    except (OSError, ValueError):
                        status = {}
                if not sections and not status:
                    continue
                out.append({
                    "ticker": ticker_dir.name,
                    "date": date_dir.name,
                    "sections": sections,
                    "status": status.get("status"),
                    "decision": status.get("decision"),
                })
        return out

    def _run_dir(self, ticker: str, date: str) -> Path:
        """Resolve a results subdirectory from URL components, refusing traversal."""
        ticker = safe_ticker_component(ticker)
        if not _DATE_DIR_RE.fullmatch(date):
            raise ValueError(f"invalid date component: {date!r}")
        return self.results_dir / ticker / date

    def result_detail(self, ticker: str, date: str) -> dict | None:
        run_dir = self._run_dir(ticker, date)
        if not run_dir.is_dir():
            return None
        sections = {}
        reports = run_dir / "reports"
        if reports.is_dir():
            for name in REPORT_SECTIONS:
                path = reports / f"{name}.md"
                if path.is_file():
                    sections[name] = path.read_text(encoding="utf-8", errors="replace")
            # Pick up any sections written by other tools, ordered after the known set.
            for path in sorted(reports.glob("*.md")):
                if path.stem not in sections:
                    sections[path.stem] = path.read_text(encoding="utf-8", errors="replace")
        status = {}
        status_path = run_dir / STATUS_FILENAME
        if status_path.is_file():
            try:
                status = json.loads(status_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                status = {}
        log_tail = tail_file(run_dir / "message_tool.log") or tail_file(run_dir / "web_run.log")
        if not sections and not status:
            return None
        return {
            "ticker": ticker,
            "date": date,
            "sections": sections,
            "status": status,
            "log_tail": log_tail,
        }

    def export_markdown(self, ticker: str, date: str) -> str | None:
        detail = self.result_detail(ticker, date)
        if detail is None or not detail["sections"]:
            return None
        parts = [f"# TradingAgents analysis — {ticker} — {date}\n"]
        for name, body in detail["sections"].items():
            title = name.replace("_", " ").title()
            parts.append(f"\n## {title}\n\n{body.strip()}\n")
        return "\n".join(parts)

    def memory_markdown(self) -> str | None:
        path = Path(self.config["memory_log_path"])
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None


class ConsoleHandler(BaseHTTPRequestHandler):
    server_version = "TradingAgentsConsole/" + _app_version()

    # The ThreadingHTTPServer instance carries .state (ConsoleState).
    @property
    def state(self) -> ConsoleState:
        return self.server.state  # type: ignore[attr-defined]

    # ---- response helpers

    def _security_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; frame-ancestors 'none'",
        )

    def _send_json(self, payload, status: int = 200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self._security_headers()
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, message: str, status: int):
        self._send_json({"error": message}, status)

    def _send_file(self, path: Path, content_type: str, download_name: str | None = None):
        try:
            body = path.read_bytes()
        except OSError:
            self._send_error_json("not found", 404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if download_name:
            self.send_header("Content-Disposition", f'attachment; filename="{download_name}"')
        self._security_headers()
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):  # noqa: A002 — BaseHTTPRequestHandler signature
        logger.info("%s — %s", self.address_string(), format % args)

    # ---- routing

    def do_GET(self):  # noqa: N802
        path = self.path.split("?", 1)[0].rstrip("/") or "/"
        try:
            if path == "/":
                self._send_file(_STATIC_DIR / "index.html", "text/html; charset=utf-8")
            elif path.startswith("/static/"):
                name = path[len("/static/"):]
                if name in _STATIC_FILES:
                    self._send_file(_STATIC_DIR / name, _STATIC_FILES[name])
                else:
                    self._send_error_json("not found", 404)
            elif path == "/api/health":
                self._send_json({"status": "ok", "version": _app_version()})
            elif path == "/api/config":
                self._send_json(self.state.config_payload())
            elif path == "/api/results":
                self._send_json({"results": self.state.list_results()})
            elif path == "/api/memory":
                md = self.state.memory_markdown()
                self._send_json({"markdown": md})
            elif path == "/api/runs":
                self._send_json({"runs": self.state.run_manager.list()})
            elif path.startswith("/api/runs/"):
                run_id = path[len("/api/runs/"):]
                run = self.state.run_manager.describe(run_id)
                if run is None:
                    self._send_error_json("unknown run id", 404)
                else:
                    run["log_tail"] = self.state.run_manager.log_tail(run_id)
                    self._send_json(run)
            elif path.startswith("/api/results/"):
                parts = path[len("/api/results/"):].split("/")
                if len(parts) == 2:
                    detail = self.state.result_detail(parts[0], parts[1])
                    if detail is None:
                        self._send_error_json("no analysis found", 404)
                    else:
                        self._send_json(detail)
                elif len(parts) == 3 and parts[2] == "export":
                    md = self.state.export_markdown(parts[0], parts[1])
                    if md is None:
                        self._send_error_json("no analysis found", 404)
                    else:
                        body = md.encode("utf-8")
                        self.send_response(200)
                        self.send_header("Content-Type", "text/markdown; charset=utf-8")
                        self.send_header("Content-Length", str(len(body)))
                        self.send_header(
                            "Content-Disposition",
                            f'attachment; filename="{parts[0]}-{parts[1]}.md"',
                        )
                        self._security_headers()
                        self.end_headers()
                        self.wfile.write(body)
                else:
                    self._send_error_json("not found", 404)
            else:
                self._send_error_json("not found", 404)
        except ValueError as exc:
            self._send_error_json(str(exc), 400)
        except BrokenPipeError:
            pass
        except Exception:
            logger.exception("unhandled error serving GET %s", self.path)
            self._send_error_json("internal server error", 500)

    def do_POST(self):  # noqa: N802
        path = self.path.split("?", 1)[0].rstrip("/")
        try:
            if path != "/api/runs":
                self._send_error_json("not found", 404)
                return
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > _MAX_BODY_BYTES:
                self._send_error_json("request body required (max 64 KiB)", 400)
                return
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
            except (UnicodeDecodeError, ValueError):
                self._send_error_json("body must be valid JSON", 400)
                return
            if not isinstance(payload, dict):
                self._send_error_json("body must be a JSON object", 400)
                return

            provider = str(self.state.config.get("llm_provider", "")).lower()
            env_var = PROVIDER_API_KEY_ENV.get(provider)
            if env_var and not os.environ.get(env_var):
                self._send_error_json(
                    f"{env_var} is not set — configure it in .env before launching "
                    f"(provider: {provider})",
                    409,
                )
                return

            run = self.state.run_manager.start(
                payload.get("ticker", ""),
                payload.get("date", ""),
                payload.get("asset_type", "stock"),
            )
            self._send_json(run, 201)
        except RunError as exc:
            self._send_error_json(str(exc), 400)
        except BrokenPipeError:
            pass
        except Exception:
            logger.exception("unhandled error serving POST %s", self.path)
            self._send_error_json("internal server error", 500)


def make_server(host: str = "127.0.0.1", port: int = 8321,
                state: ConsoleState | None = None) -> ThreadingHTTPServer:
    httpd = ThreadingHTTPServer((host, port), ConsoleHandler)
    httpd.daemon_threads = True
    httpd.state = state or ConsoleState()  # type: ignore[attr-defined]
    return httpd


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="TradingAgents Web Console")
    parser.add_argument("--host", default="127.0.0.1",
                        help="bind address (default 127.0.0.1; the console has no auth)")
    parser.add_argument("--port", type=int, default=8321)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    if args.host not in ("127.0.0.1", "localhost"):
        logger.warning(
            "Binding %s exposes the console to the network WITHOUT authentication. "
            "Only do this behind a trusted reverse proxy.", args.host,
        )

    httpd = make_server(args.host, args.port)
    logger.info("TradingAgents Web Console on http://%s:%d", args.host, args.port)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("shutting down")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
