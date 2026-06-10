"""Run lifecycle management for the web console.

Launches headless analysis subprocesses (``python -m webui.runner``) and
tracks them. Ground truth is split deliberately:

- liveness comes from the child process handle (``poll()``),
- semantic state comes from the run's ``web_run.json`` written by the
  runner (atomic writes, so reads never see torn JSON).

A run that died without reaching a terminal status (OOM-kill, interpreter
crash) is reported as ``failed`` with the exit code, so nothing can sit in
``running`` forever.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from tradingagents.dataflows.utils import safe_ticker_component

from webui.runner import STATUS_FILENAME

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ASSET_TYPES = ("stock", "crypto")


class RunError(ValueError):
    """Raised for user-correctable run-launch problems (HTTP 400/409)."""


def validate_run_request(ticker: str, date: str, asset_type: str) -> tuple[str, str, str]:
    """Validate and normalize a run request; raise RunError with a user-facing message."""
    try:
        ticker = safe_ticker_component(str(ticker or "").strip().upper())
    except ValueError as exc:
        raise RunError(str(exc)) from exc
    date = str(date or "").strip()
    if not _DATE_RE.fullmatch(date):
        raise RunError(f"date must be YYYY-MM-DD, got {date!r}")
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError as exc:
        raise RunError(f"not a valid calendar date: {date}") from exc
    if asset_type not in _ASSET_TYPES:
        raise RunError(f"asset_type must be one of {_ASSET_TYPES}, got {asset_type!r}")
    return ticker, date, asset_type


class RunManager:
    """Thread-safe registry of analysis subprocesses started by this server."""

    def __init__(self, results_dir: str | Path, *, max_concurrent: int = 2, python: str | None = None):
        self.results_dir = Path(results_dir)
        self.max_concurrent = max_concurrent
        self.python = python or sys.executable
        self._lock = threading.Lock()
        self._runs: dict[str, dict] = {}

    # -- launching -----------------------------------------------------

    def start(self, ticker: str, date: str, asset_type: str = "stock") -> dict:
        ticker, date, asset_type = validate_run_request(ticker, date, asset_type)

        with self._lock:
            active = [r for r in self._runs.values() if self._proc_running(r)]
            if len(active) >= self.max_concurrent:
                raise RunError(
                    f"already running {len(active)} analyses (limit {self.max_concurrent}); "
                    "wait for one to finish"
                )
            for r in active:
                if r["ticker"] == ticker and r["date"] == date:
                    raise RunError(f"an analysis for {ticker} on {date} is already running")

            run_dir = self.results_dir / ticker / date
            run_dir.mkdir(parents=True, exist_ok=True)
            run_id = uuid.uuid4().hex[:12]
            log_path = run_dir / "web_run.log"
            log_file = open(log_path, "ab")
            try:
                proc = subprocess.Popen(
                    [
                        self.python, "-m", "webui.runner",
                        ticker, date,
                        "--asset-type", asset_type,
                        "--run-dir", str(run_dir),
                    ],
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    cwd=os.getcwd(),
                )
            finally:
                # The child inherited the descriptor; the parent's copy is
                # closed either way so a launch failure doesn't leak it.
                log_file.close()

            record = {
                "id": run_id,
                "ticker": ticker,
                "date": date,
                "asset_type": asset_type,
                "started_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "run_dir": str(run_dir),
                "proc": proc,
            }
            self._runs[run_id] = record

        # Outside the lock: describe() re-acquires it.
        return self.describe(run_id)

    # -- inspection ----------------------------------------------------

    def list(self) -> list[dict]:
        with self._lock:
            ids = list(self._runs)
        return [self.describe(i) for i in ids]

    def describe(self, run_id: str) -> dict | None:
        with self._lock:
            record = self._runs.get(run_id)
        if record is None:
            return None

        status_doc = self._read_status(Path(record["run_dir"]))
        proc = record["proc"]
        exit_code = proc.poll()

        status = status_doc.get("status", "starting")
        if exit_code is not None and status in ("starting", "running"):
            # Child is gone but never reached a terminal status.
            status = "failed" if exit_code != 0 else "completed"
            status_doc.setdefault("error", f"runner exited with code {exit_code} before reporting a result")

        return {
            "id": record["id"],
            "ticker": record["ticker"],
            "date": record["date"],
            "asset_type": record["asset_type"],
            "started_at": record["started_at"],
            "status": status,
            "finished_at": status_doc.get("finished_at"),
            "decision": status_doc.get("decision"),
            "error": status_doc.get("error") if status == "failed" else None,
            "exit_code": exit_code,
        }

    def log_tail(self, run_id: str, max_bytes: int = 16384) -> str | None:
        with self._lock:
            record = self._runs.get(run_id)
        if record is None:
            return None
        return tail_file(Path(record["run_dir"]) / "web_run.log", max_bytes)

    # -- helpers ---------------------------------------------------------

    @staticmethod
    def _proc_running(record: dict) -> bool:
        return record["proc"].poll() is None

    @staticmethod
    def _read_status(run_dir: Path) -> dict:
        path = run_dir / STATUS_FILENAME
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}


def tail_file(path: Path, max_bytes: int = 16384) -> str:
    """Return the trailing portion of a text file, tolerating absence."""
    try:
        size = path.stat().st_size
        with open(path, "rb") as f:
            if size > max_bytes:
                f.seek(size - max_bytes)
            data = f.read()
        return data.decode("utf-8", errors="replace")
    except OSError:
        return ""
