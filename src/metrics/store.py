"""Lightweight SQLite metrics store for anonymization lifecycle events."""
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class MetricsStore:
    def __init__(self, database_url: str):
        self._lock = threading.Lock()
        self._path = self._database_path(database_url)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @staticmethod
    def _database_path(database_url: str) -> Path:
        prefix = "sqlite:///"
        if not database_url.startswith(prefix):
            raise ValueError("MetricsStore currently supports SQLite DATABASE_URL only.")
        return Path(database_url[len(prefix):])

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="milliseconds")

    @staticmethod
    def _elapsed(start: str | None, end: str | None) -> float | None:
        if not start or not end:
            return None
        started = datetime.fromisoformat(start)
        finished = datetime.fromisoformat(end)
        return max(0.0, (finished - started).total_seconds())

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS anonymization_runs (
                    id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    file_type TEXT NOT NULL,
                    uploaded_at TEXT NOT NULL,
                    analysis_completed_at TEXT,
                    preparation_started_at TEXT,
                    preparation_completed_at TEXT,
                    downloaded_at TEXT,
                    status TEXT NOT NULL DEFAULT 'started',
                    preparation_seconds REAL,
                    full_cycle_seconds REAL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_anonymization_runs_status
                ON anonymization_runs(status)
                """
            )
            columns = {
                row["name"]
                for row in connection.execute(
                    "PRAGMA table_info(anonymization_runs)"
                ).fetchall()
            }
            if "preparation_started_at" not in columns:
                connection.execute(
                    "ALTER TABLE anonymization_runs ADD COLUMN preparation_started_at TEXT"
                )
            connection.execute(
                """
                UPDATE anonymization_runs
                SET preparation_seconds = NULL,
                    full_cycle_seconds = NULL,
                    preparation_completed_at = NULL
                WHERE preparation_started_at IS NULL
                """
            )

    def start_run(self, filename: str) -> str:
        run_id = str(uuid.uuid4())
        uploaded_at = self._now()
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO anonymization_runs (id, filename, file_type, uploaded_at)
                VALUES (?, ?, ?, ?)
                """,
                (run_id, Path(filename).name, Path(filename).suffix.lower().lstrip("."), uploaded_at),
            )
        return run_id

    def mark_analysis_completed(self, run_id: str) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE anonymization_runs
                SET analysis_completed_at = ?, status = 'analyzed'
                WHERE id = ? AND status = 'started'
                """,
                (self._now(), run_id),
            )

    def mark_failed(self, run_id: str) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                "UPDATE anonymization_runs SET status = 'failed' WHERE id = ?",
                (run_id,),
            )

    def mark_preparation_started(self, run_id: str) -> None:
        started_at = self._now()
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE anonymization_runs
                SET preparation_started_at = ?, status = 'preparing'
                WHERE id = ? AND downloaded_at IS NULL
                """,
                (started_at, run_id),
            )

    def mark_prepared(self, run_id: str) -> None:
        """Compatibility method; preparation ends at download, not response creation."""
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE anonymization_runs
                SET status = 'prepared'
                WHERE id = ? AND downloaded_at IS NULL
                """,
                (run_id,),
            )

    def mark_downloaded(self, run_id: str) -> None:
        downloaded_at = self._now()
        with self._lock, self._connect() as connection:
            row = connection.execute(
                """
                SELECT analysis_completed_at, preparation_started_at
                FROM anonymization_runs
                WHERE id = ?
                """,
                (run_id,),
            ).fetchone()
            if not row:
                return
            connection.execute(
                """
                UPDATE anonymization_runs
                SET downloaded_at = ?,
                    preparation_completed_at = ?,
                    preparation_seconds = ?,
                    full_cycle_seconds = ?,
                    status = 'downloaded'
                WHERE id = ? AND downloaded_at IS NULL
                """,
                (
                    downloaded_at,
                    downloaded_at,
                    self._elapsed(row["preparation_started_at"], downloaded_at),
                    self._elapsed(row["analysis_completed_at"], downloaded_at),
                    run_id,
                ),
            )

    def summary(self) -> dict[str, Any]:
        with self._lock, self._connect() as connection:
            counts = connection.execute(
                """
                SELECT
                    COUNT(*) AS total_runs,
                    SUM(CASE WHEN status = 'downloaded' THEN 1 ELSE 0 END) AS downloaded_files,
                    AVG(CASE WHEN preparation_seconds IS NOT NULL THEN preparation_seconds END) AS avg_preparation_seconds,
                    AVG(CASE WHEN full_cycle_seconds IS NOT NULL THEN full_cycle_seconds END) AS avg_full_cycle_seconds
                FROM anonymization_runs
                """
            ).fetchone()
            latest = connection.execute(
                """
                SELECT filename, file_type, status, preparation_seconds, full_cycle_seconds,
                       uploaded_at, downloaded_at
                FROM anonymization_runs
                ORDER BY uploaded_at DESC
                LIMIT 10
                """
            ).fetchall()

        return {
            "total_runs": int(counts["total_runs"] or 0),
            "downloaded_files": int(counts["downloaded_files"] or 0),
            "avg_preparation_seconds": round(float(counts["avg_preparation_seconds"] or 0), 2),
            "avg_full_cycle_seconds": round(float(counts["avg_full_cycle_seconds"] or 0), 2),
            "latest": [dict(row) for row in latest],
        }
