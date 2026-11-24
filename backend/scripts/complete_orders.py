"""Complete orders whose trip has ended (the same job the server runs every hour).

Usage (from backend/):
    python -m scripts.complete_orders
"""
import sys

from app.services.order_completion import run_completion_job


def main() -> int:
    count = run_completion_job()
    print(f"Completed orders (trip ended, documents ready): {count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
