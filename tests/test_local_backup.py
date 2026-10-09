import sqlite3
from pathlib import Path

import pytest

from hermes.local_backup import backup_sqlite, restore_sqlite


def create_database(path: Path) -> None:
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
        db.execute("INSERT INTO items(value) VALUES (?)", ("alpha",))
        db.commit()


def read_values(path: Path) -> list[str]:
    with sqlite3.connect(path) as db:
        rows = db.execute("SELECT value FROM items ORDER BY id").fetchall()
        return [str(row[0]) for row in rows]


def test_backup_and_restore_roundtrip(tmp_path: Path) -> None:
    source = tmp_path / "hermes.db"
    backup = tmp_path / "backups" / "hermes-backup.db"
    restored = tmp_path / "restored.db"
    create_database(source)

    assert backup_sqlite(source, backup) == backup.resolve()
    assert restore_sqlite(backup, restored) == restored.resolve()
    assert read_values(restored) == ["alpha"]


def test_backup_refuses_overwrite(tmp_path: Path) -> None:
    source = tmp_path / "source.db"
    destination = tmp_path / "backup.db"
    create_database(source)
    destination.write_bytes(b"existing")

    with pytest.raises(FileExistsError):
        backup_sqlite(source, destination)


def test_restore_refuses_overwrite(tmp_path: Path) -> None:
    source = tmp_path / "source.db"
    backup = tmp_path / "backup.db"
    destination = tmp_path / "target.db"
    create_database(source)
    backup_sqlite(source, backup)
    destination.write_bytes(b"existing")

    with pytest.raises(FileExistsError):
        restore_sqlite(backup, destination)


def test_backup_rejects_non_sqlite_source(tmp_path: Path) -> None:
    source = tmp_path / "not-sqlite.db"
    destination = tmp_path / "backup.db"
    source.write_text("not a sqlite database", encoding="utf-8")

    with pytest.raises(sqlite3.DatabaseError):
        backup_sqlite(source, destination)
