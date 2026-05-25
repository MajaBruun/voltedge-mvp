"""
Database-lag — SQLite via Python stdlib.

Designvalg: SQLite bruges lokalt og i CI; i produktion erstattes DB_PATH
med en Azure SQL-connection string uden kodeændringer (env-variabel).

Tabeller svarer til ER-diagrammet i rapportens afsnit 6.1:
  charging_sessions  → ChargingSession aggregate
  session_events     → Domain events (uforanderlig audit log)
"""

import os
import sqlite3
from contextlib import contextmanager
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.getenv("DB_PATH", "voltedge.db")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row      # giver dict-lignende adgang til rækker
    conn.execute("PRAGMA journal_mode=WAL")  # bedre concurrent read-performance
    return conn


@contextmanager
def db():
    """Context manager der lukker forbindelsen automatisk."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Opret tabeller hvis de ikke eksisterer (idempotent)."""
    with db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS charging_sessions (
                session_id    TEXT PRIMARY KEY,
                charger_id    TEXT NOT NULL,
                customer_id   TEXT NOT NULL,
                started_at    TEXT NOT NULL,
                ended_at      TEXT,
                status        TEXT NOT NULL DEFAULT 'active',
                energy_kwh    REAL,
                amount        REAL,
                load_signal   TEXT
            );

            CREATE TABLE IF NOT EXISTS session_events (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id    TEXT NOT NULL,
                event_type    TEXT NOT NULL,
                payload       TEXT NOT NULL,
                created_at    TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (session_id) REFERENCES charging_sessions(session_id)
            );
        """)
