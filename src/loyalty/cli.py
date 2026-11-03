
import argparse
import json
from pathlib import Path

from .db import connect
from .generator import generate
from .validate import validate


def main():
    parser = argparse.ArgumentParser(
        description="Generate and validate a synthetic loyalty ledger"
    )

    parser.add_argument(
        "--db",
        default="data/loyalty.db",
        help="SQLite database path",
    )
    parser.add_argument(
        "--customers",
        type=int,
        default=100,
        help="Number of customers to generate",
    )
    parser.add_argument(
        "--orders",
        type=int,
        default=500,
        help="Number of orders to generate",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=20261022,
        help="Deterministic random seed",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate the existing database without generating data",
    )

    args = parser.parse_args()

    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = connect(str(db_path))

    try:
        generation_result = None

        if not args.validate_only:
            generation_result = generate(
                conn,
                args.customers,
                args.orders,
                args.seed,
            )

        validation_result = validate(conn)

        output = {
            "database": str(db_path),
            "mode": "validation_only" if args.validate_only else "generation_and_validation",
            "generation": generation_result,
            "validation": validation_result,
        }

        reports_dir = Path("reports")
        reports_dir.mkdir(exist_ok=True)

        (reports_dir / "validation.json").write_text(
            json.dumps(output, indent=2),
            encoding="utf-8",
        )

        print(json.dumps(output, indent=2))

        if not validation_result["passed"]:
            raise SystemExit(1)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
