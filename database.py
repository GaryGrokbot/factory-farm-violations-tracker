"""SQLite database schema and helpers for the violations tracker."""

import sqlite3
import os

DB_PATH = os.environ.get("DB_PATH", "violations.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS violations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            facility_name TEXT NOT NULL,
            location TEXT,
            state TEXT,
            county TEXT,
            latitude REAL,
            longitude REAL,
            violation_type TEXT,
            date TEXT,
            source TEXT NOT NULL,
            source_id TEXT,
            description TEXT,
            severity TEXT,
            penalty_amount REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(source, source_id)
        );

        CREATE INDEX IF NOT EXISTS idx_violations_source ON violations(source);
        CREATE INDEX IF NOT EXISTS idx_violations_state ON violations(state);
        CREATE INDEX IF NOT EXISTS idx_violations_date ON violations(date);
        CREATE INDEX IF NOT EXISTS idx_violations_severity ON violations(severity);
        CREATE INDEX IF NOT EXISTS idx_violations_type ON violations(violation_type);
    """)
    conn.commit()
    conn.close()


def upsert_violation(conn, **kwargs):
    """Insert or ignore a violation record."""
    conn.execute("""
        INSERT OR IGNORE INTO violations
            (facility_name, location, state, county, latitude, longitude,
             violation_type, date, source, source_id, description, severity, penalty_amount)
        VALUES
            (:facility_name, :location, :state, :county, :latitude, :longitude,
             :violation_type, :date, :source, :source_id, :description, :severity, :penalty_amount)
    """, kwargs)


if __name__ == "__main__":
    init_db()
    print(f"Database initialized at {DB_PATH}")
