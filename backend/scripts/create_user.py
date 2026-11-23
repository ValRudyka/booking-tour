"""Create a user with any role from the command line (staff accounts are not self-registered).

Usage (from backend/):
    python -m scripts.create_user --role admin --phone +380500000001 \
        --email admin@tour.local --password "S3cret-pass" --last-name Адмін --first-name Системний
"""
import argparse
import sys

from app.db import SessionLocal
from app.models.enums import UserRole
from app.schemas.auth import normalize_phone
from app.services.users import UserError, create_user


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a user")
    parser.add_argument("--role", choices=[r.value for r in UserRole], required=True)
    parser.add_argument("--phone", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--last-name", required=True)
    parser.add_argument("--first-name", required=True)
    args = parser.parse_args()
    if len(args.password) < 8:
        print("Password must be at least 8 characters", file=sys.stderr)
        return 1
    with SessionLocal() as db:
        try:
            user = create_user(db, phone=normalize_phone(args.phone), email=args.email,
                               password=args.password, last_name=args.last_name,
                               first_name=args.first_name, role=UserRole(args.role))
        except (UserError, ValueError) as error:
            print(f"Error: {getattr(error, 'message', error)}", file=sys.stderr)
            return 1
        db.commit()
        print(f"Created user id={user.id} role={user.role.value} phone={user.phone}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
