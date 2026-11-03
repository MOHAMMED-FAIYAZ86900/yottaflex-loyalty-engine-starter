import csv
import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

DB_PATH = Path("data/loyalty_phase4.db")
OUT_DIR = Path("exports")
OUT_DIR.mkdir(parents=True, exist_ok=True)

def columns(conn, table):
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}

def choose(existing, candidates, description):
    for name in candidates:
        if name in existing:
            return name
    raise RuntimeError(
        f"Could not identify {description}. Available columns: {sorted(existing)}"
    )

def write_csv(path, rows):
    if not rows:
        raise RuntimeError(f"No rows to write: {path}")

    # Build a union of all columns across all scenario records.
    fieldnames = list(dict.fromkeys(
        key for row in rows for key in row.keys()
    ))

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
            extrasaction="raise"
        )
        writer.writeheader()
        writer.writerows(rows)

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

try:
    # ---------------------------------------------------------
    # 1. Balance differs from ledger sum
    # ---------------------------------------------------------
    balance_row = conn.execute("""
        SELECT account_id, customer_id, SUM(points_delta) AS ledger_balance
        FROM points_transaction
        GROUP BY account_id, customer_id
        ORDER BY ledger_balance DESC
        LIMIT 1
    """).fetchone()

    if not balance_row:
        raise RuntimeError("No points transactions found.")

    ledger_balance = int(balance_row["ledger_balance"] or 0)
    reported_balance = ledger_balance + 100

    scenario_balance = {
        "scenario_id": "EC-001",
        "edge_case": "BALANCE_DIFFERS_FROM_LEDGER",
        "entity_type": "loyalty_account",
        "entity_id": balance_row["account_id"],
        "customer_id": balance_row["customer_id"],
        "ledger_balance_points": ledger_balance,
        "reported_balance_points": reported_balance,
        "injected_difference_points": reported_balance - ledger_balance,
        "source": "Phase 4 points_transaction ledger",
    }

    truth_balance = {
        "scenario_id": "EC-001",
        "expected_outcome": "FLAG_BALANCE_MISMATCH",
        "is_anomaly": True,
        "ground_truth_reason": (
            "Reported account balance differs from the sum of its "
            "points ledger transactions."
        ),
        "expected_difference_points": 100,
    }

    # ---------------------------------------------------------
    # 2. Redemption exceeds available points
    # Use a real rejected redemption as the source record.
    # ---------------------------------------------------------
    rejected = conn.execute("""
        SELECT redemption_id, account_id, requested_points, created_at,
               rejection_reason
        FROM redemption
        WHERE status = 'REJECTED'
        ORDER BY redemption_id
        LIMIT 1
    """).fetchone()

    if not rejected:
        raise RuntimeError("No rejected redemption found.")

    available_row = conn.execute("""
        SELECT COALESCE(SUM(points_delta), 0) AS balance
        FROM points_transaction
        WHERE account_id = ?
          AND created_at <= ?
    """, (rejected["account_id"], rejected["created_at"])).fetchone()

    available = int(available_row["balance"] or 0)
    requested = int(rejected["requested_points"])

    # Ensure the fixture is unambiguously an over-balance request.
    if requested <= available:
        requested = available + max(1, abs(requested - available) + 1)

    scenario_redemption = {
        "scenario_id": "EC-002",
        "edge_case": "REDEMPTION_EXCEEDS_AVAILABLE_POINTS",
        "entity_type": "redemption",
        "entity_id": rejected["redemption_id"],
        "account_id": rejected["account_id"],
        "available_points": available,
        "requested_points": requested,
        "shortfall_points": requested - available,
        "source_rejection_reason": rejected["rejection_reason"],
    }

    truth_redemption = {
        "scenario_id": "EC-002",
        "expected_outcome": "REJECT_REDEMPTION",
        "is_anomaly": True,
        "ground_truth_reason": (
            "The redemption request exceeds the available points balance. "
            "It must be rejected without creating a redemption points debit."
        ),
        "expected_shortfall_points": requested - available,
    }

    # ---------------------------------------------------------
    # 3. Returned order keeps all points
    # Source: a real return with a positive points reversal.
    # Fault injection: simulate zero points reversed.
    # ---------------------------------------------------------
    returned = conn.execute("""
        SELECT r.return_id, r.order_id, r.order_line_id,
               r.reversed_points, la.account_id, o.customer_id
        FROM return_event r
        JOIN orders o ON o.order_id = r.order_id
        JOIN loyalty_account la ON la.customer_id = o.customer_id
        WHERE r.reversed_points > 0
        ORDER BY r.return_id
        LIMIT 1
    """).fetchone()

    if not returned:
        raise RuntimeError("No returned order with reversed points found.")

    expected_reversal = int(returned["reversed_points"])

    scenario_return = {
        "scenario_id": "EC-003",
        "edge_case": "RETURNED_ORDER_KEEPS_ALL_POINTS",
        "entity_type": "return_event",
        "entity_id": returned["return_id"],
        "order_id": returned["order_id"],
        "order_line_id": returned["order_line_id"],
        "account_id": returned["account_id"],
        "customer_id": returned["customer_id"],
        "expected_reversed_points": expected_reversal,
        "simulated_actual_reversed_points": 0,
        "source": "Phase 4 return_event",
    }

    truth_return = {
        "scenario_id": "EC-003",
        "expected_outcome": "FLAG_MISSING_POINTS_REVERSAL",
        "is_anomaly": True,
        "ground_truth_reason": (
            "The returned order should reverse the points earned on the "
            "returned quantity. The injected faulty behavior reverses zero."
        ),
        "expected_reversed_points": expected_reversal,
    }

    # ---------------------------------------------------------
    # 4. Points expire twice
    # Source: an existing expiry record.
    # Fault injection: duplicate its account/lot expiry.
    # ---------------------------------------------------------
    expiry = conn.execute("""
        SELECT expiry_batch_id, account_id, lot_id,
               points_transaction_id, expired_points
        FROM expiry_batch
        ORDER BY expiry_batch_id
        LIMIT 1
    """).fetchone()

    if not expiry:
        raise RuntimeError("No expiry batch found.")

    scenario_expiry = {
        "scenario_id": "EC-004",
        "edge_case": "POINTS_EXPIRE_TWICE",
        "entity_type": "expiry_batch",
        "entity_id": expiry["expiry_batch_id"],
        "account_id": expiry["account_id"],
        "lot_id": expiry["lot_id"],
        "original_expiry_transaction_id": expiry["points_transaction_id"],
        "original_expired_points": int(expiry["expired_points"]),
        "simulated_duplicate_expiry": True,
    }

    truth_expiry = {
        "scenario_id": "EC-004",
        "expected_outcome": "REJECT_DUPLICATE_EXPIRY",
        "is_anomaly": True,
        "ground_truth_reason": (
            "The same account and points lot must not be expired more than "
            "once. The duplicate attempt must be idempotently rejected."
        ),
        "expected_unique_expiry_per_account_lot": True,
    }

    # ---------------------------------------------------------
    # 5. Tier uses gross rather than qualifying spend
    # Derive gross spend from order lines and qualifying spend
    # from the order records where available.
    # ---------------------------------------------------------
    order_cols = columns(conn, "orders")
    line_cols = columns(conn, "order_line")
    tier_cols = columns(conn, "tier")

    qualifying_col = choose(
        order_cols,
        ["qualifying_spend_cents", "qualifying_spend"],
        "qualifying spend column in orders",
    )

    threshold_col = choose(
        tier_cols,
        [
            "min_qualifying_spend_cents",
            "minimum_qualifying_spend_cents",
            "min_spend_cents",
            "threshold_cents",
            "min_spend",
        ],
        "tier threshold column",
    )

    order_customer_col = choose(
        order_cols, ["customer_id"], "customer ID in orders"
    )
    line_quantity_col = choose(
        line_cols, ["quantity"], "order-line quantity"
    )
    line_price_col = choose(
        line_cols, ["unit_price_cents", "unit_price"],
        "order-line unit price"
    )

    gross_by_customer = {}
    for row in conn.execute(f"""
        SELECT o.{order_customer_col} AS customer_id,
               SUM(ol.{line_quantity_col} * ol.{line_price_col}) AS gross
        FROM orders o
        JOIN order_line ol ON ol.order_id = o.order_id
        GROUP BY o.{order_customer_col}
    """):
        gross_by_customer[row["customer_id"]] = int(row["gross"] or 0)

    qualifying_by_customer = {}
    for row in conn.execute(f"""
        SELECT {order_customer_col} AS customer_id,
               SUM({qualifying_col}) AS qualifying
        FROM orders
        GROUP BY {order_customer_col}
    """):
        qualifying_by_customer[row["customer_id"]] = int(
            row["qualifying"] or 0
        )

    tiers = conn.execute(f"""
        SELECT * FROM tier ORDER BY {threshold_col}
    """).fetchall()

    tier_case = None

    # Find a real customer whose gross spend crosses a tier threshold
    # while qualifying spend remains below that same threshold.
    for tier in tiers:
        threshold = int(tier[threshold_col] or 0)
        if threshold <= 0:
            continue

        for customer_id, gross in gross_by_customer.items():
            qualifying = qualifying_by_customer.get(customer_id, 0)
            if gross >= threshold and qualifying < threshold:
                tier_case = {
                    "customer_id": customer_id,
                    "gross": gross,
                    "qualifying": qualifying,
                    "threshold": threshold,
                    "tier_name": str(tier["tier_name"])
                    if "tier_name" in tier.keys()
                    else str(tier["tier_id"]),
                    "injected": False,
                }
                break

        if tier_case:
            break

    # If the dataset has no natural example, create a transparent,
    # threshold-based synthetic fixture using a real customer ID.
    if not tier_case:
        first_customer = conn.execute("""
            SELECT customer_id FROM customer ORDER BY customer_id LIMIT 1
        """).fetchone()

        if not first_customer or not tiers:
            raise RuntimeError("Cannot construct tier edge case.")

        selected_tier = None
        for tier in tiers:
            threshold = int(tier[threshold_col] or 0)
            if threshold > 0:
                selected_tier = tier
                break

        if selected_tier is None:
            raise RuntimeError("No positive tier threshold found.")

        threshold = int(selected_tier[threshold_col])
        tier_case = {
            "customer_id": first_customer["customer_id"],
            "gross": threshold + 1,
            "qualifying": max(0, threshold - 1),
            "threshold": threshold,
            "tier_name": str(selected_tier["tier_name"])
            if "tier_name" in selected_tier.keys()
            else str(selected_tier["tier_id"]),
            "injected": True,
        }

    scenario_tier = {
        "scenario_id": "EC-005",
        "edge_case": "TIER_USES_GROSS_INSTEAD_OF_QUALIFYING_SPEND",
        "entity_type": "customer",
        "entity_id": tier_case["customer_id"],
        "customer_id": tier_case["customer_id"],
        "gross_spend_cents": tier_case["gross"],
        "qualifying_spend_cents": tier_case["qualifying"],
        "tier_threshold_cents": tier_case["threshold"],
        "tier_name_at_threshold": tier_case["tier_name"],
        "synthetic_threshold_fixture": tier_case["injected"],
    }

    truth_tier = {
        "scenario_id": "EC-005",
        "expected_outcome": "CALCULATE_TIER_FROM_QUALIFYING_SPEND",
        "is_anomaly": True,
        "ground_truth_reason": (
            "Tier qualification must use qualifying spend after discounts "
            "and refunds, not gross order value."
        ),
        "gross_based_threshold_reached": (
            tier_case["gross"] >= tier_case["threshold"]
        ),
        "qualifying_based_threshold_reached": (
            tier_case["qualifying"] >= tier_case["threshold"]
        ),
        "expected_tier_qualification": "QUALIFIES"
        if tier_case["qualifying"] >= tier_case["threshold"]
        else "DOES_NOT_QUALIFY",
    }

    scenarios = [
        scenario_balance,
        scenario_redemption,
        scenario_return,
        scenario_expiry,
        scenario_tier,
    ]

    ground_truth = [
        truth_balance,
        truth_redemption,
        truth_return,
        truth_expiry,
        truth_tier,
    ]

    write_csv(OUT_DIR / "edge_case_scenarios.csv", scenarios)
    write_csv(OUT_DIR / "edge_case_ground_truth.csv", ground_truth)

    with (OUT_DIR / "edge_case_ground_truth.json").open(
        "w", encoding="utf-8"
    ) as f:
        json.dump(ground_truth, f, indent=2, ensure_ascii=False)

    print("\nPHASE 5 EDGE-CASE FIXTURES CREATED")
    print("---------------------------------")
    print(f"Scenario records: {len(scenarios)}")
    print(f"Ground-truth records: {len(ground_truth)}")
    print(f"Database read only: {DB_PATH}")
    print(f"Scenario CSV: {OUT_DIR / 'edge_case_scenarios.csv'}")
    print(f"Ground-truth CSV: {OUT_DIR / 'edge_case_ground_truth.csv'}")
    print(f"Ground-truth JSON: {OUT_DIR / 'edge_case_ground_truth.json'}")
    print("\nEdge cases:")
    for item in scenarios:
        print(f"- {item['scenario_id']}: {item['edge_case']}")

finally:
    conn.close()
