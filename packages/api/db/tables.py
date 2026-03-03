"""SQLite tablo tanimlari."""
from __future__ import annotations

TABLES_SQL = [
    """CREATE TABLE IF NOT EXISTS print_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT NOT NULL,
        started_at TEXT NOT NULL DEFAULT (datetime('now')),
        ended_at TEXT,
        duration_seconds INTEGER DEFAULT 0,
        status TEXT DEFAULT 'started',
        filament_used_mm REAL DEFAULT 0,
        layers_total INTEGER DEFAULT 0,
        layers_printed INTEGER DEFAULT 0,
        notes TEXT DEFAULT ''
    )""",
    """CREATE TABLE IF NOT EXISTS flowguard_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL DEFAULT (datetime('now')),
        verdict TEXT NOT NULL,
        layer INTEGER DEFAULT 0,
        z_height REAL DEFAULT 0,
        filament_ok INTEGER DEFAULT 1,
        heater_duty REAL DEFAULT 0,
        tmc_sg INTEGER DEFAULT 0,
        ai_class TEXT DEFAULT 'normal',
        action_taken TEXT DEFAULT ''
    )""",
    """CREATE TABLE IF NOT EXISTS config_changes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL DEFAULT (datetime('now')),
        section TEXT NOT NULL,
        key TEXT NOT NULL,
        old_value TEXT,
        new_value TEXT,
        changed_by TEXT DEFAULT 'api'
    )""",
]
