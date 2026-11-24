"""Complete orders whose trip has ended (the same job the server runs every hour).

Usage (from backend/):
    python -m scripts.complete_orders
    python -m scripts.complete_orders --order-id 42 --force   # dev only, see below

--order-id N --force is for manual testing (e.g. of reviews): it moves that one order from
«Документи готові» to «Завершено» now, ignoring the end date, as the System (change_status, so the
history row and the client's notification are written as usual). Other statuses are refused.
"""
import argparse
import sys

from app.services.errors import DomainError
from app.services.order_completion import run_completion_job, run_force_complete


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.complete_orders",
                                     description="Complete orders whose trip has ended.")
    parser.add_argument("--order-id", type=int, help="complete only this order (needs --force)")
    parser.add_argument("--force", action="store_true",
                        help="dev only: ignore the end date (order must be documents_ready)")
    args = parser.parse_args(argv)
    if args.force != (args.order_id is not None):
        parser.error("--order-id and --force are used together")

    if args.order_id is not None:
        try:
            order = run_force_complete(args.order_id)
        except DomainError as error:
            print(f"Refused: {error.message}", file=sys.stderr)
            return 1
        print(f"Order {order.number} completed (forced, end date ignored)")
        return 0

    count = run_completion_job()
    print(f"Completed orders (trip ended, documents ready): {count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
