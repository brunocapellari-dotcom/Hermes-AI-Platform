from __future__ import annotations

import argparse
import os
import sqlite3
from pathlib import Path


def _integrity_check(connection: sqlite3.Connection) -> None:
    row = connection.execute("PRAGMA integrity_check").fetchone()
    if row is None or row[0] != "ok":
        raise RuntimeError("SQLite integrity check failed")


def _secure_permissions(path: Path) -> None:
    if os.name != "nt":
        path.chmod(0o600)


def backup_sqlite(source: Path, destination: Path) -> Path:
    source = source.expanduser().resolve()
    destination = destination.expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if source == destination:
        raise ValueError("backup destination must differ from source")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(destination)

    source_uri = f"{source.as_uri()}?mode=ro"
    with sqlite3.connect(source_uri, uri=True) as source_db:
        _integrity_check(source_db)
        with sqlite3.connect(destination) as backup_db:
            source_db.backup(backup_db)
            _integrity_check(backup_db)
    _secure_permissions(destination)
    return destination


def restore_sqlite(backup: Path, destination: Path) -> Path:
    backup = backup.expanduser().resolve()
    destination = destination.expanduser().resolve()
    if not backup.is_file():
        raise FileNotFoundError(backup)
    if backup == destination:
        raise ValueError("restore destination must differ from backup")
    if destination.exists():
        raise FileExistsError(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    backup_uri = f"{backup.as_uri()}?mode=ro"
    with sqlite3.connect(backup_uri, uri=True) as backup_db:
        _integrity_check(backup_db)
        with sqlite3.connect(destination) as restored_db:
            backup_db.backup(restored_db)
            _integrity_check(restored_db)
    _secure_permissions(destination)
    return destination


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Hermes local SQLite backup/restore")
    subparsers = parser.add_subparsers(dest="command", required=True)

    backup = subparsers.add_parser("backup", help="Create a verified SQLite backup")
    backup.add_argument("source", type=Path)
    backup.add_argument("destination", type=Path)

    restore = subparsers.add_parser("restore", help="Restore into a new SQLite file")
    restore.add_argument("backup", type=Path)
    restore.add_argument("destination", type=Path)
    return parser


def main() -> None:
    args = _parser().parse_args()
    if args.command == "backup":
        result = backup_sqlite(args.source, args.destination)
    else:
        result = restore_sqlite(args.backup, args.destination)
    print(result)


if __name__ == "__main__":
    main()
