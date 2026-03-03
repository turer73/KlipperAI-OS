"""SQLite database layer tests."""
from __future__ import annotations
import sqlite3
import tempfile
from pathlib import Path


def test_tables_created():
    from packages.api.db.tables import TABLES_SQL
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name
    conn = sqlite3.connect(db_path)
    for sql in TABLES_SQL:
        conn.execute(sql)
    conn.commit()
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in cursor}
    assert "print_history" in tables
    assert "flowguard_events" in tables
    assert "config_changes" in tables
    conn.close()
    Path(db_path).unlink(missing_ok=True)


def test_database_connect_and_close():
    from packages.api.db.engine import Database
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name
    db = Database(db_path)
    db.connect()
    # Tables should be created automatically
    tables = db.fetchall("SELECT name FROM sqlite_master WHERE type='table'")
    table_names = {row["name"] for row in tables}
    assert "print_history" in table_names
    db.close()
    Path(db_path).unlink(missing_ok=True)


def test_database_insert_and_fetch():
    from packages.api.db.engine import Database
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name
    db = Database(db_path)
    db.connect()
    db.execute(
        "INSERT INTO print_history (filename, status) VALUES (?, ?)",
        ("test.gcode", "completed"),
    )
    db.commit()
    row = db.fetchone("SELECT * FROM print_history WHERE filename = ?", ("test.gcode",))
    assert row is not None
    assert row["filename"] == "test.gcode"
    assert row["status"] == "completed"
    db.close()
    Path(db_path).unlink(missing_ok=True)


def test_database_fetchall():
    from packages.api.db.engine import Database
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name
    db = Database(db_path)
    db.connect()
    for i in range(3):
        db.execute(
            "INSERT INTO print_history (filename, status) VALUES (?, ?)",
            (f"file{i}.gcode", "completed"),
        )
    db.commit()
    rows = db.fetchall("SELECT * FROM print_history")
    assert len(rows) == 3
    db.close()
    Path(db_path).unlink(missing_ok=True)


def test_database_fetchone_returns_none():
    from packages.api.db.engine import Database
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name
    db = Database(db_path)
    db.connect()
    row = db.fetchone("SELECT * FROM print_history WHERE id = ?", (9999,))
    assert row is None
    db.close()
    Path(db_path).unlink(missing_ok=True)
