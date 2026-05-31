"""Payment model extensions and SQLite migrations (legacy; use modules.db.bootstrap)."""

from sqlalchemy import inspect, text

from extensions import db


def migrate_payments_table() -> None:
    """Add new payment columns and migrate legacy data (SQLite-safe)."""
    inspector = inspect(db.engine)
    table = "stream_payments" if "stream_payments" in inspector.get_table_names() else "payments"
    if table not in inspector.get_table_names():
        return

    columns = {col["name"] for col in inspector.get_columns(table)}
    additions = {
        "customer_name": "VARCHAR(255)",
        "customer_email": "VARCHAR(255)",
        "method": "VARCHAR(50)",
        "provider_payment_id": "VARCHAR(255)",
        "reference_note": "VARCHAR(500)",
        "paid_at": "DATETIME",
    }

    for name, col_type in additions.items():
        if name not in columns:
            db.session.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {col_type}"))

    if "provider" in columns:
        db.session.execute(
            text(
                f"UPDATE {table} SET method = provider "
                "WHERE method IS NULL OR TRIM(method) = ''"
            )
        )
    if "approved_at" in columns:
        db.session.execute(
            text(f"UPDATE {table} SET paid_at = approved_at WHERE paid_at IS NULL")
        )
    db.session.execute(
        text(f"UPDATE {table} SET status = 'paid' WHERE status = 'approved'")
    )
    db.session.commit()
