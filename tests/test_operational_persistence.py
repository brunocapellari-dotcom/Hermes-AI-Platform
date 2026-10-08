from pathlib import Path

from hermes.operational_persistence import SqlOperationalStore
from hermes.persistence import Database


def test_operational_store_schema(tmp_path: Path) -> None:
    db = Database(f"sqlite:///{tmp_path / 'operational.db'}")
    db.create_schema()
    store = SqlOperationalStore(db)
    assert store.status_counts()
    db.close()
