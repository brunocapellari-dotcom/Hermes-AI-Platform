from pathlib import Path

from sqlalchemy import text

from hermes.persistence import Database


def test_file_sqlite_enables_integrity_and_concurrency_pragmas(tmp_path: Path) -> None:
    db = Database(f"sqlite:///{tmp_path / 'runtime.db'}")
    try:
        with db.engine.connect() as connection:
            foreign_keys = connection.execute(text("PRAGMA foreign_keys")).scalar_one()
            busy_timeout = connection.execute(text("PRAGMA busy_timeout")).scalar_one()
            journal_mode = connection.execute(text("PRAGMA journal_mode")).scalar_one()
            synchronous = connection.execute(text("PRAGMA synchronous")).scalar_one()

        assert foreign_keys == 1
        assert busy_timeout == 30_000
        assert str(journal_mode).casefold() == "wal"
        assert synchronous in {1, 2}
    finally:
        db.close()
