from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.models import GoodsReceipt, Invoice, InvoiceLineItem, PurchaseOrder, PurchaseOrderLine, Vendor
from scripts import seed_demo


@pytest.fixture
def sqlite_sessions(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)
    monkeypatch.setattr(seed_demo, "SessionLocal", sessions)
    monkeypatch.setattr(seed_demo, "get_settings", lambda: SimpleNamespace(app_env="development"))
    yield sessions
    engine.dispose()


def count(session, model):
    return session.scalar(select(func.count()).select_from(model))


def test_reseed_is_repeatable_and_preserves_non_demo_records(sqlite_sessions):
    with sqlite_sessions() as session:
        session.add(Vendor(
            id="external-vendor-keep", external_id="EXT-V-KEEP", name="Non-demo supplier"
        ))
        session.commit()

    first = seed_demo.reseed(seed=123, vendors=4, purchase_orders=12)
    with sqlite_sessions() as session:
        assert count(session, Vendor) == 5
        assert count(session, PurchaseOrder) == first["purchase_orders"]
        assert count(session, PurchaseOrderLine) == first["purchase_order_lines"]
        assert count(session, GoodsReceipt) == first["goods_receipts"]
        assert count(session, Invoice) == first["invoices"]
        assert count(session, InvoiceLineItem) == first["invoice_lines"]
        assert session.get(Vendor, "external-vendor-keep") is not None

    second = seed_demo.reseed(seed=123, vendors=4, purchase_orders=12)
    assert first == second
    with sqlite_sessions() as session:
        assert count(session, Vendor) == 5
        assert count(session, Invoice) == second["invoices"]
        assert session.get(Vendor, "external-vendor-keep") is not None


def test_seed_refuses_non_development_environment(monkeypatch):
    monkeypatch.setattr(seed_demo, "get_settings", lambda: SimpleNamespace(app_env="production"))
    with pytest.raises(RuntimeError, match="APP_ENV must be 'development'"):
        seed_demo.reseed()
