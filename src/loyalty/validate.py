
def validate(conn):
    checks = {}

    # 1. Referential integrity
    checks["foreign_key_violations"] = len(
        conn.execute("PRAGMA foreign_key_check").fetchall()
    )

    # 2. SQLite database integrity
    checks["database_integrity"] = conn.execute(
        "PRAGMA integrity_check"
    ).fetchone()[0]

    # 3. Order line totals must equal order gross amount
    checks["order_line_amount_mismatches"] = conn.execute("""
        SELECT COUNT(*)
        FROM orders o
        LEFT JOIN (
            SELECT order_id,
                   SUM(quantity * unit_price_cents) AS line_total
            FROM order_line
            GROUP BY order_id
        ) l ON l.order_id = o.order_id
        WHERE COALESCE(l.line_total, 0) <> o.gross_amount_cents
    """).fetchone()[0]

    # 4. Qualifying spend must equal gross less discount and refunds
    checks["qualifying_spend_mismatches"] = conn.execute("""
        SELECT COUNT(*)
        FROM orders o
        LEFT JOIN (
            SELECT order_id, SUM(refund_amount_cents) AS refunded
            FROM return_event
            GROUP BY order_id
        ) r ON r.order_id = o.order_id
        WHERE o.qualifying_spend_cents <>
              o.gross_amount_cents
              - o.discount_cents
              - COALESCE(r.refunded, 0)
    """).fetchone()[0]

    # 5. Reversals must reference an accrual and use the same account/lot
    checks["invalid_reversal_references"] = conn.execute("""
        SELECT COUNT(*)
        FROM points_transaction r
        LEFT JOIN points_transaction a
          ON a.transaction_id = r.reference_transaction_id
        WHERE r.transaction_type = 'REVERSAL'
          AND (
              a.transaction_id IS NULL
              OR a.transaction_type <> 'ACCRUAL'
              OR r.account_id <> a.account_id
              OR r.lot_id <> a.lot_id
              OR r.points_delta >= 0
          )
    """).fetchone()[0]

    # 6. Cumulative reversals cannot exceed original accrual
    checks["over_reversed_accruals"] = conn.execute("""
        SELECT COUNT(*)
        FROM points_transaction a
        JOIN (
            SELECT reference_transaction_id,
                   SUM(-points_delta) AS reversed_points
            FROM points_transaction
            WHERE transaction_type = 'REVERSAL'
            GROUP BY reference_transaction_id
        ) r ON r.reference_transaction_id = a.transaction_id
        WHERE a.transaction_type = 'ACCRUAL'
          AND r.reversed_points > a.points_delta
    """).fetchone()[0]

    # 7. Every redemption must reconcile to its FIFO allocations
    checks["redemption_allocation_mismatches"] = conn.execute("""
        SELECT COUNT(*)
        FROM points_transaction p
        LEFT JOIN (
            SELECT transaction_id,
                   SUM(points_allocated) AS allocated
            FROM points_allocation
            GROUP BY transaction_id
        ) a ON a.transaction_id = p.transaction_id
        WHERE p.transaction_type = 'REDEMPTION'
          AND COALESCE(a.allocated, 0) <> -p.points_delta
    """).fetchone()[0]

    # 8. Allocation rows must belong to redemption transactions
    checks["invalid_allocation_transactions"] = conn.execute("""
        SELECT COUNT(*)
        FROM points_allocation a
        LEFT JOIN points_transaction p
          ON p.transaction_id = a.transaction_id
        WHERE p.transaction_id IS NULL
           OR p.transaction_type <> 'REDEMPTION'
           OR a.points_allocated <= 0
    """).fetchone()[0]

    # 9. Expiry batch must match its expiry ledger transaction
    checks["expiry_batch_mismatches"] = conn.execute("""
        SELECT COUNT(*)
        FROM expiry_batch e
        LEFT JOIN points_transaction p
          ON p.transaction_id = e.points_transaction_id
        WHERE p.transaction_id IS NULL
           OR p.transaction_type <> 'EXPIRY'
           OR p.account_id <> e.account_id
           OR p.lot_id <> e.lot_id
           OR -p.points_delta <> e.expired_points
    """).fetchone()[0]

    # 10. A points lot cannot have a negative remaining balance
    checks["negative_lot_balances"] = conn.execute("""
        SELECT COUNT(*)
        FROM (
            SELECT
                p.account_id,
                p.lot_id,
                SUM(p.points_delta) -
                COALESCE((
                    SELECT SUM(a.points_allocated)
                    FROM points_allocation a
                    JOIN points_transaction r
                      ON r.transaction_id = a.transaction_id
                    WHERE r.account_id = p.account_id
                      AND a.lot_id = p.lot_id
                ), 0) AS remaining
            FROM points_transaction p
            WHERE p.lot_id IS NOT NULL
            GROUP BY p.account_id, p.lot_id
            HAVING remaining < 0
        )
    """).fetchone()[0]

    # 11. A lot may only be expired once
    checks["duplicate_expiry_lots"] = conn.execute("""
        SELECT COUNT(*)
        FROM (
            SELECT account_id, lot_id
            FROM expiry_batch
            GROUP BY account_id, lot_id
            HAVING COUNT(*) > 1
        )
    """).fetchone()[0]

    # 12. Redemption records must match their ledger state
    checks["redemption_status_mismatches"] = conn.execute("""
        SELECT COUNT(*)
        FROM redemption r
        LEFT JOIN points_transaction p
          ON p.transaction_id = r.points_transaction_id
        WHERE
            (r.status = 'APPROVED' AND (
                p.transaction_id IS NULL
                OR p.transaction_type <> 'REDEMPTION'
                OR p.points_delta <> -r.requested_points
            ))
            OR
            (r.status = 'REJECTED' AND
                r.points_transaction_id IS NOT NULL)
    """).fetchone()[0]

    # 13. Returned quantity cannot exceed purchased quantity
    checks["return_quantity_mismatches"] = conn.execute("""
        SELECT COUNT(*)
        FROM order_line l
        LEFT JOIN (
            SELECT order_line_id,
                   SUM(returned_quantity) AS event_quantity
            FROM return_event
            GROUP BY order_line_id
        ) r ON r.order_line_id = l.order_line_id
        WHERE l.returned_quantity < 0
           OR l.returned_quantity > l.quantity
           OR l.returned_quantity <> COALESCE(r.event_quantity, 0)
    """).fetchone()[0]

    # 14. Return events must reference the correct order line
    checks["invalid_return_order_references"] = conn.execute("""
        SELECT COUNT(*)
        FROM return_event r
        LEFT JOIN order_line l
          ON l.order_line_id = r.order_line_id
        WHERE l.order_line_id IS NULL
           OR l.order_id <> r.order_id
           OR r.returned_quantity <= 0
           OR r.refund_amount_cents < 0
           OR r.reversed_points < 0
    """).fetchone()[0]

    # 15. Return event reversal references must reconcile
    checks["return_reversal_mismatches"] = conn.execute("""
        SELECT COUNT(*)
        FROM return_event r
        LEFT JOIN points_transaction p
          ON p.transaction_id = r.reversal_transaction_id
        WHERE
            (
                r.reversed_points = 0
                AND r.reversal_transaction_id IS NOT NULL
            )
            OR
            (
                r.reversed_points > 0
                AND (
                    p.transaction_id IS NULL
                    OR p.transaction_type <> 'REVERSAL'
                    OR -p.points_delta <> r.reversed_points
                )
            )
    """).fetchone()[0]

    # 16. Return refunds cannot exceed the original line value
    checks["excessive_return_refunds"] = conn.execute("""
        SELECT COUNT(*)
        FROM (
            SELECT
                l.order_line_id,
                l.quantity * l.unit_price_cents AS line_value,
                COALESCE(SUM(r.refund_amount_cents), 0) AS refunded
            FROM order_line l
            LEFT JOIN return_event r
              ON r.order_line_id = l.order_line_id
            GROUP BY l.order_line_id
            HAVING refunded > line_value
        )
    """).fetchone()[0]

    # 17. Report row counts
    tables = [
        "customer",
        "loyalty_account",
        "tier",
        "rule",
        "orders",
        "order_line",
        "points_transaction",
        "points_allocation",
        "reward",
        "redemption",
        "expiry_batch",
        "account_event",
        "return_event",
    ]

    checks["row_counts"] = {}

    for table in tables:
        checks["row_counts"][table] = conn.execute(
            f"SELECT COUNT(*) FROM {table}"
        ).fetchone()[0]

    # 18. Consolidated result
    zero_checks = [
        "foreign_key_violations",
        "order_line_amount_mismatches",
        "qualifying_spend_mismatches",
        "invalid_reversal_references",
        "over_reversed_accruals",
        "redemption_allocation_mismatches",
        "invalid_allocation_transactions",
        "expiry_batch_mismatches",
        "negative_lot_balances",
        "duplicate_expiry_lots",
        "redemption_status_mismatches",
        "return_quantity_mismatches",
        "invalid_return_order_references",
        "return_reversal_mismatches",
        "excessive_return_refunds",
    ]

    checks["passed"] = (
        checks["database_integrity"] == "ok"
        and all(checks[name] == 0 for name in zero_checks)
    )

    return checks
