"""Test altyapısı.

Şema testleri bellek içi SQLite üzerinde çalışır. Yabancı anahtar zorlaması
SQLite'ta varsayılan olarak kapalıdır ve açılmazsa kısıtlar sessizce
uygulanmaz; bu yüzden her bağlantıda açıkça etkinleştirilir.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.models import Base


@pytest.fixture()
def engine():
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture()
def session(engine):
    with Session(engine) as session:
        yield session
