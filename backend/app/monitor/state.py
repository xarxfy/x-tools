"""Small JSON documents stored in the settings table."""

import copy

from sqlalchemy.orm.attributes import flag_modified

from app.core.db import session_scope
from app.models import Setting


def load(key: str, default=None):
    with session_scope() as db:
        row = db.get(Setting, key)
        return copy.deepcopy(row.value) if row is not None else default


def _store(db, row, key, value):
    if row is None:
        db.add(Setting(key=key, value=value))
    else:
        row.value = value
        flag_modified(row, "value")
    db.commit()


def save(key: str, value) -> None:
    with session_scope() as db:
        _store(db, db.get(Setting, key), key, value)


def update(key: str, fn, default=None):
    """Read-modify-write in one transaction."""
    with session_scope() as db:
        row = db.get(Setting, key)
        current = copy.deepcopy(row.value) if row is not None else copy.deepcopy(default if default is not None else {})
        value = fn(current)
        _store(db, row, key, value)
        return value
