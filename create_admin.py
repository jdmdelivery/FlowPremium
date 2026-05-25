#!/usr/bin/env python3
"""Create default admin users in the database.

Usage:
    python create_admin.py
"""

from app import create_app
from extensions import db
from utils.seed_users import DEFAULT_USERS, ensure_default_users


def main() -> None:
    app = create_app()
    with app.app_context():
        import modules.streaming.models  # noqa: F401

        db.create_all()
        messages = ensure_default_users()

        print("Default users seed complete.\n")
        for line in messages:
            print(f"  • {line}")

        print("\nCredentials:")
        for spec in DEFAULT_USERS:
            role = "admin" if spec["is_admin"] else "user"
            print(
                f"  • {spec['username']} / {spec['email']} / "
                f"{spec['password']} ({role})"
            )


if __name__ == "__main__":
    main()
