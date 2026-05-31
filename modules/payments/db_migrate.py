"""Payment model extensions and SQLite migrations."""

from sqlalchemy import inspect, text

from extensions import db


def migrate_payments_table() -> None:
    """Add new payment columns and migrate legacy data (SQLite-safe)."""
    inspector = inspect(db.engine)
    if "payments" not in inspector.get_table_names():
        return

    columns = {col["name"] for col in inspector.get_columns("payments")}
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
            db.session.execute(text(f"ALTER TABLE payments ADD COLUMN {name} {col_type}"))

    if "provider" in columns:
        db.session.execute(
            text(
                "UPDATE payments SET method = provider "
                "WHERE method IS NULL OR TRIM(method) = ''"
            )
        )
    if "approved_at" in columns:
        db.session.execute(
            text("UPDATE payments SET paid_at = approved_at WHERE paid_at IS NULL")
        )
    db.session.execute(
        text("UPDATE payments SET status = 'paid' WHERE status = 'approved'")
    )
    db.session.commit()
