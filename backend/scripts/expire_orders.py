"""Cancel orders whose seat hold ran out (the same job the server runs every minute).

Usage (from backend/):
    python -m scripts.expire_orders
"""
import sys

from app.services.order_expiry import run_expiry_job


def main() -> int:
    count = run_expiry_job()
    print(f"Cancelled orders with an expired seat hold: {count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
