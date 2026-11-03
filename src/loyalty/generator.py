
from __future__ import annotations

import csv
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from random import Random

SEED = 20261022
TIERS = [
    ("TIER-BRONZE", "Bronze", 0, 100),
    ("TIER-SILVER", "Silver", 500000, 125),
    ("TIER-GOLD", "Gold", 1500000, 150),
    ("TIER-PLATINUM", "Platinum", 3000000, 200),
]

INSERT_TX = """
INSERT INTO points_transaction
(transaction_id, account_id, customer_id, order_id,
 reference_transaction_id, transaction_type, points_delta,
 lot_id, created_at, expires_at, idempotency_key, notes)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def money_to_points(net_spend_cents, earning_rate_bps):
    if net_spend_cents < 0 or earning_rate_bps < 0:
        raise ValueError("Spend and rate cannot be negative")
    return (net_spend_cents * earning_rate_bps) // 10000


def _tier_for_spend(spend_cents):
    return [tier for tier in TIERS if spend_cents >= tier[2]][-1]


def _split_amount(total_cents, parts, rng):
    if parts == 1:
        return [total_cents]
    cuts = sorted(rng.sample(range(1, total_cents), parts - 1))
    bounds = [0] + cuts + [total_cents]
    return [bounds[i + 1] - bounds[i] for i in range(parts)]


def _insert(conn, sql, rows, batch_size=5000):
    for start in range(0, len(rows), batch_size):
        conn.executemany(sql, rows[start:start + batch_size])


def generate(
    conn,
    customers=20000,
    orders=100000,
    seed=SEED,
    anomaly_rate=0.01,
    return_rate=0.02,
    concurrent_accounts=100,
):
    """
    Deterministic synthetic loyalty lifecycle generator.

    Generates:
    - Customers, loyalty accounts, tiers, rules and rewards
    - Orders, order lines and accrual transactions
    - Tier progression events
    - Partial order returns and proportional point reversals
    - Approved and rejected redemption requests
    - Competing redemption requests for selected accounts
    - FIFO redemption allocations
    - Expiry transactions and expiry batches
    - Separate anomaly ground-truth CSV

    Run against a fresh database. Existing customer data is never deleted.
    """

    if customers < 1 or orders < 1:
        raise ValueError("Customers and orders must be positive")

    if not 0 <= anomaly_rate <= 0.25:
        raise ValueError("anomaly_rate must be between 0 and 0.25")

    if not 0 <= return_rate <= 0.25:
        raise ValueError("return_rate must be between 0 and 0.25")

    if concurrent_accounts < 0:
        raise ValueError("concurrent_accounts cannot be negative")

    if conn.execute("SELECT COUNT(*) FROM customer").fetchone()[0]:
        raise RuntimeError(
            "Database already contains customers. "
            "Use a fresh database path; existing data was not changed."
        )

    rng = Random(seed)
    base_date = date(2026, 1, 1)

    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("BEGIN")

    try:
        # --------------------------------------------------
        # MASTER DATA
        # --------------------------------------------------

        conn.executemany(
            "INSERT OR IGNORE INTO tier VALUES (?,?,?,?,?,?)",
            [
                (a, b, c, d, "2026-01-01", None)
                for a, b, c, d in TIERS
            ],
        )

        conn.execute(
            "INSERT OR IGNORE INTO rule VALUES (?,?,?,?,?,?,?)",
            (
                "RULE-BASE",
                "Base earn rule",
                "EARN",
                1,
                "2026-01-01",
                None,
                1,
            ),
        )

        conn.executemany(
            "INSERT OR IGNORE INTO reward VALUES (?,?,?,?)",
            [
                ("RWD-1000", "Voucher INR 100", 1000, 1),
                ("RWD-2500", "Voucher INR 250", 2500, 1),
                ("RWD-5000", "Voucher INR 500", 5000, 1),
            ],
        )

        customer_rows = []
        account_rows = []

        for n in range(1, customers + 1):
            cid = f"CUST-{n:06d}"
            signup = (
                base_date + timedelta(days=rng.randrange(30))
            ).isoformat()

            customer_rows.append((
                cid,
                f"Customer {n}",
                f"customer{n}@example.test",
                signup,
                rng.choice(["NORTH", "SOUTH", "EAST", "WEST"]),
                signup + "T09:00:00",
            ))

            account_rows.append((
                f"LOY-{cid}",
                cid,
                "TIER-BRONZE",
                signup + "T09:00:00",
                "ACTIVE",
            ))

        _insert(
            conn,
            "INSERT INTO customer VALUES (?,?,?,?,?,?)",
            customer_rows,
        )
        _insert(
            conn,
            "INSERT INTO loyalty_account VALUES (?,?,?,?,?)",
            account_rows,
        )

        # --------------------------------------------------
        # ORDERS AND ACCRUALS
        # --------------------------------------------------

        spend = [0] * (customers + 1)
        current_tier = ["TIER-BRONZE"] * (customers + 1)

        lots_by_account = defaultdict(list)
        accrual_by_order = {}

        order_rows = []
        line_rows = []
        accrual_rows = []
        event_rows = []
        injected_anomalies = []

        # Retain order information for return generation.
        return_candidates = []

        line_counter = 1
        event_counter = 1
        tx_counter = 1
        total_lines = 0

        for i in range(1, orders + 1):
            n = rng.randint(1, customers)
            cid = f"CUST-{n:06d}"
            aid = f"LOY-{cid}"
            oid = f"ORD-2026-{i:06d}"

            od = base_date + timedelta(
                days=30 + ((i - 1) * 300 // orders)
            )
            created = od.isoformat() + "T12:00:00"

            is_anomaly = rng.random() < anomaly_rate

            if is_anomaly:
                gross = rng.randint(500000, 1000000) * 100
                discount = rng.randint(
                    0, min(gross // 5, 50000)
                )

                injected_anomalies.append((
                    "ORDER",
                    oid,
                    cid,
                    "EXTREME_ORDER_VALUE",
                    1,
                    "Injected order gross is far above the normal generator range",
                ))
            else:
                gross = rng.randint(1000, 50000) * 100
                discount = rng.randint(
                    0, min(gross // 5, 5000)
                )

            net = gross - discount

            order_rows.append((
                oid,
                cid,
                od.isoformat(),
                "INR",
                gross,
                discount,
                "COMPLETED",
                net,
            ))

            line_count = rng.randint(1, 4)
            line_ids = []
            line_amounts = []

            for amount in _split_amount(gross, line_count, rng):
                line_id = f"LINE-{line_counter:08d}"

                line_rows.append((
                    line_id,
                    oid,
                    f"SKU-{rng.randint(1, 500):04d}",
                    1,
                    amount,
                    0,
                ))

                line_ids.append(line_id)
                line_amounts.append(amount)

                line_counter += 1

            total_lines += line_count

            spend[n] += net
            tier_id, _, _, rate = _tier_for_spend(spend[n])

            if tier_id != current_tier[n]:
                old_tier = current_tier[n]
                current_tier[n] = tier_id

                event_rows.append((
                    f"EVT-TIER-{event_counter:08d}",
                    aid,
                    "TIER_CHANGED",
                    old_tier,
                    tier_id,
                    created,
                    f"Qualifying spend reached {spend[n]} paise",
                ))
                event_counter += 1

            points = money_to_points(net, rate)

            if points <= 0:
                raise RuntimeError(
                    f"Unexpected zero accrual for order {oid}"
                )

            txid = f"PTS-2026-{tx_counter:08d}"
            tx_counter += 1

            lotid = f"LOT-{oid}"
            expires = (
                od + timedelta(days=365)
            ).isoformat() + "T23:59:59"

            accrual_rows.append((
                txid,
                aid,
                cid,
                oid,
                None,
                "ACCRUAL",
                points,
                lotid,
                created,
                expires,
                f"accrual:{oid}",
                "Earned on eligible net spend",
            ))

            accrual_by_order[oid] = {
                "transaction_id": txid,
                "points": points,
                "lot_id": lotid,
                "account_id": aid,
                "customer_id": cid,
                "net_spend": net,
            }

            lots_by_account[aid].append({
                "lot_id": lotid,
                "customer_id": cid,
                "accrual_tx_id": txid,
                "created_at": created,
                "expires_at": expires,
                "original": points,
                "remaining": points,
            })

            if rng.random() < return_rate:
                return_candidates.append({
                    "order_id": oid,
                    "customer_id": cid,
                    "account_id": aid,
                    "gross": gross,
                    "discount": discount,
                    "net": net,
                    "line_id": line_ids[0],
                    "line_amount": line_amounts[0],
                    "line_count": line_count,
                    "accrual": accrual_by_order[oid],
                })

        _insert(
            conn,
            "INSERT INTO orders VALUES (?,?,?,?,?,?,?,?)",
            order_rows,
        )
        _insert(
            conn,
            "INSERT INTO order_line VALUES (?,?,?,?,?,?)",
            line_rows,
        )
        _insert(conn, INSERT_TX, accrual_rows)

        if event_rows:
            _insert(
                conn,
                "INSERT INTO account_event VALUES (?,?,?,?,?,?,?)",
                event_rows,
            )

        # --------------------------------------------------
        # PARTIAL ORDER RETURNS
        # --------------------------------------------------

        return_rows = []
        return_reversal_rows = []
        return_count = 0
        return_refund_total = 0
        return_reversed_total = 0

        return_at = "2026-11-15T12:00:00"

        # One line is returned from a selected order.
        # Multi-line orders therefore become PARTIALLY_RETURNED.
        for candidate in return_candidates:
            gross = candidate["gross"]
            discount = candidate["discount"]
            line_amount = candidate["line_amount"]
            net = candidate["net"]

            discount_share = (
                discount * line_amount // gross
                if gross else 0
            )
            refund = line_amount - discount_share

            refund = min(refund, net)
            if refund <= 0:
                continue

            accrual = candidate["accrual"]

            reversed_points = min(
                accrual["points"],
                accrual["points"] * refund // net,
            )

            reversal_txid = None

            if reversed_points > 0:
                reversal_txid = f"PTS-2026-{tx_counter:08d}"
                tx_counter += 1

                return_reversal_rows.append((
                    reversal_txid,
                    candidate["account_id"],
                    candidate["customer_id"],
                    None,
                    accrual["transaction_id"],
                    "REVERSAL",
                    -reversed_points,
                    accrual["lot_id"],
                    return_at,
                    None,
                    f"return-reversal:{candidate['order_id']}",
                    "Proportional points reversal for returned order line",
                ))

                # Reduce the corresponding original accrual lot.
                lot = next(
                    x for x in lots_by_account[candidate["account_id"]]
                    if x["lot_id"] == accrual["lot_id"]
                )
                lot["remaining"] -= reversed_points

            return_id = f"RET-2026-{return_count + 1:08d}"

            return_rows.append((
                return_id,
                candidate["order_id"],
                candidate["line_id"],
                1,
                refund,
                reversed_points,
                reversal_txid,
                return_at,
                "Synthetic partial order return",
            ))

            new_qualifying = max(0, net - refund)

            conn.execute(
                """
                UPDATE order_line
                SET returned_quantity = 1
                WHERE order_line_id = ?
                """,
                (candidate["line_id"],),
            )

            new_status = (
                "RETURNED"
                if candidate["line_count"] == 1
                else "PARTIALLY_RETURNED"
            )

            conn.execute(
                """
                UPDATE orders
                SET status = ?, qualifying_spend_cents = ?
                WHERE order_id = ?
                """,
                (
                    new_status,
                    new_qualifying,
                    candidate["order_id"],
                ),
            )

            customer_number = int(
                candidate["customer_id"].split("-")[1]
            )
            spend[customer_number] -= refund

            return_count += 1
            return_refund_total += refund
            return_reversed_total += reversed_points

        _insert(conn, INSERT_TX, return_reversal_rows)

        _insert(
            conn,
            """
            INSERT INTO return_event
            (return_id, order_id, order_line_id, returned_quantity,
             refund_amount_cents, reversed_points,
             reversal_transaction_id, created_at, reason)
            VALUES (?,?,?,?,?,?,?,?,?)
            """,
            return_rows,
        )

        # --------------------------------------------------
        # RECONCILE FINAL ACCOUNT TIERS AFTER REFUNDS
        # --------------------------------------------------

        tier_downgrade_count = 0
        tier_event_at = "2026-11-20T12:00:00"

        for n in range(1, customers + 1):
            final_tier = _tier_for_spend(spend[n])[0]
            aid = f"LOY-CUST-{n:06d}"

            if final_tier != current_tier[n]:
                event_rows = [(
                    f"EVT-TIER-{event_counter:08d}",
                    aid,
                    "TIER_CHANGED",
                    current_tier[n],
                    final_tier,
                    tier_event_at,
                    f"Tier recalculated after returns; qualifying spend is {spend[n]} paise",
                )]

                _insert(
                    conn,
                    "INSERT INTO account_event VALUES (?,?,?,?,?,?,?)",
                    event_rows,
                )

                event_counter += 1
                tier_downgrade_count += 1

            conn.execute(
                "UPDATE loyalty_account SET tier_id=? WHERE account_id=?",
                (final_tier, aid),
            )

        # --------------------------------------------------
        # REDEMPTIONS
        # --------------------------------------------------

        redemption_rows = []
        redemption_tx_rows = []
        allocation_rows = []

        redemption_no = 0
        allocation_count = 0
        approved_count = 0
        rejected_count = 0
        concurrent_pair_count = 0

        redemption_at = "2026-12-15T12:00:00"

        def available_lots(account_id):
            return [
                lot for lot in lots_by_account[account_id]
                if lot["remaining"] > 0
                and lot["expires_at"] > redemption_at
            ]

        def available_balance(account_id):
            return sum(
                lot["remaining"]
                for lot in available_lots(account_id)
            )

        def choose_reward(points):
            if points <= 1000:
                return "RWD-1000"
            if points <= 2500:
                return "RWD-2500"
            return "RWD-5000"

        def process_redemption(account_id, requested, reason=None):
            nonlocal redemption_no
            nonlocal allocation_count
            nonlocal approved_count
            nonlocal rejected_count
            nonlocal tx_counter

            redemption_no += 1

            rid = f"RDM-2026-{redemption_no:08d}"
            customer_id = account_id.replace("LOY-", "")
            available = available_balance(account_id)

            if requested > available:
                redemption_rows.append((
                    rid,
                    account_id,
                    choose_reward(requested),
                    None,
                    requested,
                    "REJECTED",
                    redemption_at,
                    reason or "Insufficient available points",
                ))
                rejected_count += 1
                return "REJECTED"

            if requested <= 0:
                raise ValueError("Redemption request must be positive")

            txid = f"PTS-2026-{tx_counter:08d}"
            tx_counter += 1

            redemption_tx_rows.append((
                txid,
                account_id,
                customer_id,
                None,
                None,
                "REDEMPTION",
                -requested,
                None,
                redemption_at,
                None,
                f"redemption:{rid}",
                "Synthetic reward redemption",
            ))

            redemption_rows.append((
                rid,
                account_id,
                choose_reward(requested),
                txid,
                requested,
                "APPROVED",
                redemption_at,
                None,
            ))

            left = requested

            for lot in available_lots(account_id):
                if left == 0:
                    break

                take = min(left, lot["remaining"])

                if take > 0:
                    allocation_count += 1

                    allocation_rows.append((
                        f"ALLOC-{allocation_count:09d}",
                        txid,
                        lot["lot_id"],
                        take,
                    ))

                    lot["remaining"] -= take
                    left -= take

            if left != 0:
                raise RuntimeError(
                    f"FIFO allocation failed for {rid}"
                )

            approved_count += 1
            return "APPROVED"

        # Simulate competing requests for selected accounts.
        # Both requests are created at the same timestamp and
        # request the same pre-attempt balance. Only the first
        # can be approved; the second must be rejected.
        concurrent_limit = min(concurrent_accounts, customers)

        for n in range(1, concurrent_limit + 1):
            aid = f"LOY-CUST-{n:06d}"
            balance_before = available_balance(aid)

            if balance_before <= 0:
                continue

            process_redemption(aid, balance_before)

            process_redemption(
                aid,
                balance_before,
                "Competing request rejected after the other request consumed the available balance",
            )

            concurrent_pair_count += 1

        # Ordinary bounded FIFO redemption requests.
        for n in range(concurrent_limit + 1, customers + 1):
            aid = f"LOY-CUST-{n:06d}"

            for _ in range(6):
                available = available_balance(aid)

                if available <= 0:
                    break

                requested = min(
                    available,
                    rng.choice([100, 250, 500, 750, 1000, 1500, 2000]),
                )

                process_redemption(aid, requested)

        # One explicit insufficient-balance attempt per account.
        for n in range(1, customers + 1):
            aid = f"LOY-CUST-{n:06d}"
            remaining = available_balance(aid)

            process_redemption(
                aid,
                remaining + rng.choice([100, 250, 500]),
                "Insufficient available points",
            )

        _insert(conn, INSERT_TX, redemption_tx_rows)

        _insert(
            conn,
            """
            INSERT INTO redemption
            (redemption_id, account_id, reward_id, points_transaction_id,
             requested_points, status, created_at, rejection_reason)
            VALUES (?,?,?,?,?,?,?,?)
            """,
            redemption_rows,
        )

        _insert(
            conn,
            """
            INSERT INTO points_allocation
            (allocation_id, transaction_id, lot_id, points_allocated)
            VALUES (?,?,?,?)
            """,
            allocation_rows,
        )

        # --------------------------------------------------
        # EXPIRY
        # --------------------------------------------------

        expiry_tx_rows = []
        expiry_rows = []
        expiry_count = 0

        for aid, lots in lots_by_account.items():
            for lot in lots:
                amount = lot["remaining"]

                if amount <= 0:
                    continue

                txid = f"PTS-2026-{tx_counter:08d}"
                tx_counter += 1

                executed = lot["expires_at"]

                expiry_tx_rows.append((
                    txid,
                    aid,
                    lot["customer_id"],
                    None,
                    None,
                    "EXPIRY",
                    -amount,
                    lot["lot_id"],
                    executed,
                    None,
                    f"expiry:{aid}:{lot['lot_id']}",
                    "Synthetic points lot expiration",
                ))

                expiry_rows.append((
                    txid.replace("PTS", "EXP"),
                    aid,
                    lot["lot_id"],
                    txid,
                    amount,
                    executed,
                ))

                lot["remaining"] = 0
                expiry_count += 1

        _insert(conn, INSERT_TX, expiry_tx_rows)

        _insert(
            conn,
            """
            INSERT INTO expiry_batch
            (expiry_batch_id, account_id, lot_id,
             points_transaction_id, expired_points, executed_at)
            VALUES (?,?,?,?,?,?)
            """,
            expiry_rows,
        )

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    # ------------------------------------------------------
    # SEPARATE ANOMALY GROUND TRUTH
    # ------------------------------------------------------

    anomaly_path = Path("reports") / "anomaly_ground_truth.csv"
    anomaly_path.parent.mkdir(parents=True, exist_ok=True)

    with anomaly_path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:
        writer = csv.writer(handle)

        writer.writerow([
            "entity_type",
            "entity_id",
            "customer_id",
            "anomaly_type",
            "is_anomaly",
            "ground_truth_reason",
        ])

        writer.writerows(injected_anomalies)

    counts = conn.execute("""
        SELECT transaction_type, COUNT(*)
        FROM points_transaction
        GROUP BY transaction_type
    """).fetchall()

    tx_counts = {
        kind: count for kind, count in counts
    }

    return {
        "customers": customers,
        "orders": orders,
        "order_lines": total_lines,
        "transactions_by_type": tx_counts,
        "points_transactions_total": sum(tx_counts.values()),
        "return_events": return_count,
        "return_refund_total_cents": return_refund_total,
        "return_reversed_points": return_reversed_total,
        "approved_redemptions": approved_count,
        "rejected_redemptions": rejected_count,
        "concurrent_redemption_pairs": concurrent_pair_count,
        "expiry_transactions": expiry_count,
        "tier_change_events": event_counter - 1,
        "tier_downgrades_after_returns": tier_downgrade_count,
        "points_allocations": allocation_count,
        "anomaly_labels": len(injected_anomalies),
        "anomaly_ground_truth_file": str(anomaly_path),
        "seed": seed,
    }
