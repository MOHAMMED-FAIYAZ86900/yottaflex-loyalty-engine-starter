
import sqlite3
from typing import Optional


class LoyaltyEngine:
    """
    Ledger-first loyalty engine.

    Account balances are calculated from points_transaction.
    Redemption allocations identify the accrual lots consumed.
    Returns append reversal transactions and return-event records.
    """

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.conn.row_factory = sqlite3.Row

    # ---------------------------------------------------------
    # BALANCE
    # ---------------------------------------------------------

    def balance(self, account_id: str, as_of: Optional[str] = None) -> int:
        sql = """
            SELECT COALESCE(SUM(points_delta), 0)
            FROM points_transaction
            WHERE account_id = ?
        """
        args = [account_id]

        if as_of:
            sql += " AND created_at <= ?"
            args.append(as_of)

        result = self.conn.execute(sql, args).fetchone()[0]
        return int(result)

    def _lot_balance(self, account_id, lot_id, as_of=None):
        """
        Remaining points in a lot after ledger debits and
        redemption allocations.
        """

        sql = """
            SELECT COALESCE(SUM(points_delta), 0)
            FROM points_transaction
            WHERE account_id = ?
              AND lot_id = ?
        """
        args = [account_id, lot_id]

        if as_of:
            sql += " AND created_at <= ?"
            args.append(as_of)

        ledger_balance = int(
            self.conn.execute(sql, args).fetchone()[0]
        )

        allocation_sql = """
            SELECT COALESCE(SUM(pa.points_allocated), 0)
            FROM points_allocation pa
            JOIN points_transaction pt
              ON pt.transaction_id = pa.transaction_id
            WHERE pt.account_id = ?
              AND pa.lot_id = ?
        """
        allocation_args = [account_id, lot_id]

        if as_of:
            allocation_sql += " AND pt.created_at <= ?"
            allocation_args.append(as_of)

        allocated = int(
            self.conn.execute(
                allocation_sql, allocation_args
            ).fetchone()[0]
        )

        return ledger_balance - allocated

    # ---------------------------------------------------------
    # ACCRUAL
    # ---------------------------------------------------------

    def accrue(
        self,
        account_id,
        customer_id,
        order_id,
        points,
        created_at,
        expires_at,
        tx_id,
        lot_id
    ):
        if points <= 0:
            raise ValueError("Accrual points must be positive")

        existing = self.conn.execute(
            """
            SELECT transaction_id
            FROM points_transaction
            WHERE idempotency_key = ?
            """,
            (f"accrual:{order_id}",)
        ).fetchone()

        if existing:
            raise ValueError("Order has already been accrued")

        self.conn.execute(
            """
            INSERT INTO points_transaction (
                transaction_id,
                account_id,
                customer_id,
                order_id,
                transaction_type,
                points_delta,
                lot_id,
                created_at,
                expires_at,
                idempotency_key,
                notes
            )
            VALUES (?, ?, ?, ?, 'ACCRUAL', ?, ?, ?, ?, ?, ?)
            """,
            (
                tx_id,
                account_id,
                customer_id,
                order_id,
                points,
                lot_id,
                created_at,
                expires_at,
                f"accrual:{order_id}",
                "Earned on qualifying net spend"
            )
        )

    # ---------------------------------------------------------
    # REDEMPTION
    # ---------------------------------------------------------

    def redeem(
        self,
        account_id,
        customer_id,
        reward_id,
        points,
        created_at,
        redemption_id,
        tx_id
    ):
        if points <= 0:
            raise ValueError("Redemption points must be positive")

        if self.conn.in_transaction:
            self.conn.commit()

        self.conn.execute("BEGIN IMMEDIATE")

        try:
            existing = self.conn.execute(
                """
                SELECT status, requested_points
                FROM redemption
                WHERE redemption_id = ?
                """,
                (redemption_id,)
            ).fetchone()

            if existing:
                self.conn.commit()
                return {
                    "status": existing["status"],
                    "requested_points": existing["requested_points"],
                    "duplicate": True
                }

            available = self.balance(account_id, created_at)

            if available < points:
                self.conn.execute(
                    """
                    INSERT INTO redemption (
                        redemption_id,
                        account_id,
                        reward_id,
                        points_transaction_id,
                        requested_points,
                        status,
                        created_at,
                        rejection_reason
                    )
                    VALUES (?, ?, ?, NULL, ?, 'REJECTED', ?, ?)
                    """,
                    (
                        redemption_id,
                        account_id,
                        reward_id,
                        points,
                        created_at,
                        "INSUFFICIENT_BALANCE"
                    )
                )

                self.conn.commit()

                return {
                    "status": "REJECTED",
                    "available_points": available,
                    "requested_points": points
                }

            lots = self.conn.execute(
                """
                SELECT
                    transaction_id,
                    lot_id,
                    created_at,
                    expires_at
                FROM points_transaction
                WHERE account_id = ?
                  AND transaction_type = 'ACCRUAL'
                  AND lot_id IS NOT NULL
                  AND created_at <= ?
                  AND (expires_at IS NULL OR expires_at > ?)
                ORDER BY created_at ASC, transaction_id ASC
                """,
                (account_id, created_at, created_at)
            ).fetchall()

            remaining = points
            allocations = []

            for lot in lots:
                lot_id = lot["lot_id"]

                lot_balance = self._lot_balance(
                    account_id,
                    lot_id,
                    created_at
                )

                if lot_balance <= 0:
                    continue

                allocated = min(remaining, lot_balance)

                allocations.append((lot_id, allocated))
                remaining -= allocated

                if remaining == 0:
                    break

            if remaining > 0:
                raise ValueError(
                    "Insufficient unexpired points in accrual lots"
                )

            self.conn.execute(
                """
                INSERT INTO points_transaction (
                    transaction_id,
                    account_id,
                    customer_id,
                    transaction_type,
                    points_delta,
                    created_at,
                    idempotency_key,
                    notes
                )
                VALUES (?, ?, ?, 'REDEMPTION', ?, ?, ?, ?)
                """,
                (
                    tx_id,
                    account_id,
                    customer_id,
                    -points,
                    created_at,
                    f"redemption:{redemption_id}",
                    "Reward redemption"
                )
            )

            for index, (lot_id, allocated) in enumerate(allocations):
                self.conn.execute(
                    """
                    INSERT INTO points_allocation (
                        allocation_id,
                        transaction_id,
                        lot_id,
                        points_allocated
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        f"ALLOC-{redemption_id}-{index + 1}",
                        tx_id,
                        lot_id,
                        allocated
                    )
                )

            self.conn.execute(
                """
                INSERT INTO redemption (
                    redemption_id,
                    account_id,
                    reward_id,
                    points_transaction_id,
                    requested_points,
                    status,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, 'APPROVED', ?)
                """,
                (
                    redemption_id,
                    account_id,
                    reward_id,
                    tx_id,
                    points,
                    created_at
                )
            )

            self.conn.commit()

            return {
                "status": "APPROVED",
                "available_points": available - points,
                "requested_points": points,
                "allocations": allocations
            }

        except Exception:
            self.conn.rollback()
            raise

    # ---------------------------------------------------------
    # ACCRUAL REVERSAL
    # ---------------------------------------------------------

    def reverse_accrual(
        self,
        original_tx_id,
        reversal_tx_id,
        created_at,
        reason="RETURN",
        points_to_reverse=None,
        idempotency_key=None,
        _within_transaction=False
    ):
        """
        Reverse all or part of an accrual.

        When called by return_order_line(), the caller owns
        the transaction. Otherwise this method manages its
        own transaction.
        """

        owns_transaction = not _within_transaction

        if owns_transaction:
            if self.conn.in_transaction:
                self.conn.commit()
            self.conn.execute("BEGIN IMMEDIATE")
        elif not self.conn.in_transaction:
            raise RuntimeError(
                "Expected an active transaction from the caller"
            )

        try:
            original = self.conn.execute(
                """
                SELECT
                    account_id,
                    customer_id,
                    order_id,
                    points_delta,
                    transaction_type,
                    lot_id
                FROM points_transaction
                WHERE transaction_id = ?
                """,
                (original_tx_id,)
            ).fetchone()

            if (
                not original
                or original["transaction_type"] != "ACCRUAL"
            ):
                raise ValueError(
                    "Reversal must reference an existing accrual"
                )

            account_id = original["account_id"]
            customer_id = original["customer_id"]
            order_id = original["order_id"]
            original_points = int(original["points_delta"])
            lot_id = original["lot_id"]

            already_reversed = self.conn.execute(
                """
                SELECT COALESCE(SUM(-points_delta), 0)
                FROM points_transaction
                WHERE reference_transaction_id = ?
                  AND transaction_type = 'REVERSAL'
                """,
                (original_tx_id,)
            ).fetchone()[0]

            already_reversed = int(already_reversed)
            unreversed = original_points - already_reversed

            if unreversed <= 0:
                raise ValueError("Accrual has already been reversed")

            if points_to_reverse is None:
                points_to_reverse = unreversed

            points_to_reverse = int(points_to_reverse)

            if points_to_reverse <= 0:
                raise ValueError("Reversal points must be positive")

            if points_to_reverse > unreversed:
                raise ValueError(
                    "Reversal exceeds the remaining accrual points"
                )

            available = (
                self._lot_balance(account_id, lot_id, created_at)
                if lot_id
                else self.balance(account_id, created_at)
            )

            if available < points_to_reverse:
                raise ValueError(
                    "Cannot reverse accrual: points have already been "
                    "consumed, redeemed or expired"
                )

            key = (
                idempotency_key
                or f"reversal:{original_tx_id}:{already_reversed + points_to_reverse}"
            )

            self.conn.execute(
                """
                INSERT INTO points_transaction (
                    transaction_id,
                    account_id,
                    customer_id,
                    order_id,
                    reference_transaction_id,
                    transaction_type,
                    points_delta,
                    lot_id,
                    created_at,
                    idempotency_key,
                    notes
                )
                VALUES (?, ?, ?, ?, ?, 'REVERSAL', ?, ?, ?, ?, ?)
                """,
                (
                    reversal_tx_id,
                    account_id,
                    customer_id,
                    order_id,
                    original_tx_id,
                    -points_to_reverse,
                    lot_id,
                    created_at,
                    key,
                    reason
                )
            )

            if owns_transaction:
                self.conn.commit()

            return {
                "status": "REVERSED",
                "reversed_points": points_to_reverse,
                "remaining_unreversed_points": (
                    unreversed - points_to_reverse
                )
            }

        except Exception:
            if owns_transaction:
                self.conn.rollback()
            raise

    # ---------------------------------------------------------
    # PARTIAL ORDER-LINE RETURN
    # ---------------------------------------------------------

    def return_order_line(
        self,
        order_id,
        order_line_id,
        quantity,
        return_id,
        reversal_tx_id,
        created_at,
        reason="CUSTOMER_RETURN"
    ):
        """
        Process a partial or full order-line return.

        - Prevents returning more than purchased quantity.
        - Calculates proportional discount and refund.
        - Calculates cumulative proportional points reversal.
        - Appends a return_event.
        - Updates order and order-line lifecycle state.
        - Performs all changes atomically.
        """

        if quantity <= 0:
            raise ValueError("Return quantity must be positive")

        if self.conn.in_transaction:
            self.conn.commit()

        self.conn.execute("BEGIN IMMEDIATE")

        try:
            duplicate = self.conn.execute(
                """
                SELECT return_id, refund_amount_cents, reversed_points
                FROM return_event
                WHERE return_id = ?
                """,
                (return_id,)
            ).fetchone()

            if duplicate:
                self.conn.commit()
                return {
                    "status": "DUPLICATE",
                    "return_id": duplicate["return_id"],
                    "refund_amount_cents": duplicate["refund_amount_cents"],
                    "reversed_points": duplicate["reversed_points"]
                }

            line = self.conn.execute(
                """
                SELECT
                    ol.order_line_id,
                    ol.order_id,
                    ol.quantity,
                    ol.unit_price_cents,
                    ol.returned_quantity,
                    o.customer_id,
                    o.gross_amount_cents,
                    o.discount_cents,
                    o.qualifying_spend_cents,
                    o.status
                FROM order_line ol
                JOIN orders o ON o.order_id = ol.order_id
                WHERE ol.order_line_id = ?
                  AND ol.order_id = ?
                """,
                (order_line_id, order_id)
            ).fetchone()

            if not line:
                raise ValueError(
                    "Order line does not belong to the specified order"
                )

            remaining_quantity = (
                line["quantity"] - line["returned_quantity"]
            )

            if quantity > remaining_quantity:
                raise ValueError(
                    "Return quantity exceeds the unreturned quantity"
                )

            if line["status"] in ("RETURNED", "CANCELLED"):
                raise ValueError(
                    "Order cannot accept additional returns"
                )

            accrual = self.conn.execute(
                """
                SELECT transaction_id, points_delta
                FROM points_transaction
                WHERE order_id = ?
                  AND transaction_type = 'ACCRUAL'
                ORDER BY created_at ASC
                LIMIT 1
                """,
                (order_id,)
            ).fetchone()

            if not accrual:
                raise ValueError(
                    "No accrual transaction exists for this order"
                )

            original_tx_id = accrual["transaction_id"]
            original_points = int(accrual["points_delta"])

            original_gross = int(line["gross_amount_cents"])
            original_discount = int(line["discount_cents"])
            original_qualifying = original_gross - original_discount

            if original_qualifying < 0:
                raise ValueError("Invalid original qualifying spend")

            unit_price = int(line["unit_price_cents"])
            incremental_gross = quantity * unit_price

            # Total gross value returned before this return.
            prior_return_gross = self.conn.execute(
                """
                SELECT COALESCE(
                    SUM(re.returned_quantity * ol.unit_price_cents),
                    0
                )
                FROM return_event re
                JOIN order_line ol
                  ON ol.order_line_id = re.order_line_id
                WHERE re.order_id = ?
                """,
                (order_id,)
            ).fetchone()[0]

            prior_return_gross = int(prior_return_gross)
            cumulative_return_gross = (
                prior_return_gross + incremental_gross
            )

            if cumulative_return_gross > original_gross:
                raise ValueError(
                    "Cumulative returned value exceeds order gross amount"
                )

            # Allocate discount proportionally across cumulative returns.
            prior_discount = (
                original_discount * prior_return_gross
            ) // original_gross if original_gross else 0

            cumulative_discount = (
                original_discount * cumulative_return_gross
            ) // original_gross if original_gross else 0

            incremental_discount = (
                cumulative_discount - prior_discount
            )

            refund_amount = (
                incremental_gross - incremental_discount
            )

            cumulative_net_return = (
                cumulative_return_gross - cumulative_discount
            )

            # Calculate the cumulative reversal target from the
            # ORIGINAL qualifying spend, not the already-updated order.
            if original_qualifying > 0:
                cumulative_target = (
                    original_points * cumulative_net_return
                ) // original_qualifying
            else:
                cumulative_target = original_points

            cumulative_target = min(
                original_points,
                cumulative_target
            )

            prior_reversed = self.conn.execute(
                """
                SELECT COALESCE(SUM(-points_delta), 0)
                FROM points_transaction
                WHERE reference_transaction_id = ?
                  AND transaction_type = 'REVERSAL'
                """,
                (original_tx_id,)
            ).fetchone()[0]

            prior_reversed = int(prior_reversed)

            points_to_reverse = max(
                0,
                cumulative_target - prior_reversed
            )

            if points_to_reverse > 0:
                if not reversal_tx_id:
                    raise ValueError(
                        "A reversal transaction ID is required"
                    )

                self.reverse_accrual(
                    original_tx_id=original_tx_id,
                    reversal_tx_id=reversal_tx_id,
                    created_at=created_at,
                    reason=reason,
                    points_to_reverse=points_to_reverse,
                    idempotency_key=f"return:{return_id}",
                    _within_transaction=True
                )

            new_returned_quantity = (
                line["returned_quantity"] + quantity
            )

            self.conn.execute(
                """
                UPDATE order_line
                SET returned_quantity = ?
                WHERE order_line_id = ?
                """,
                (
                    new_returned_quantity,
                    order_line_id
                )
            )

            all_lines_returned = self.conn.execute(
                """
                SELECT COUNT(*)
                FROM order_line
                WHERE order_id = ?
                  AND returned_quantity < quantity
                """,
                (order_id,)
            ).fetchone()[0] == 0

            new_status = (
                "RETURNED"
                if all_lines_returned
                else "PARTIALLY_RETURNED"
            )

            new_qualifying_spend = max(
                0,
                original_qualifying - cumulative_net_return
            )

            self.conn.execute(
                """
                UPDATE orders
                SET status = ?,
                    qualifying_spend_cents = ?
                WHERE order_id = ?
                """,
                (
                    new_status,
                    new_qualifying_spend,
                    order_id
                )
            )

            self.conn.execute(
                """
                INSERT INTO return_event (
                    return_id,
                    order_id,
                    order_line_id,
                    returned_quantity,
                    refund_amount_cents,
                    reversed_points,
                    reversal_transaction_id,
                    created_at,
                    reason
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    return_id,
                    order_id,
                    order_line_id,
                    quantity,
                    refund_amount,
                    points_to_reverse,
                    reversal_tx_id if points_to_reverse > 0 else None,
                    created_at,
                    reason
                )
            )

            self.conn.commit()

            return {
                "status": "RETURN_PROCESSED",
                "return_id": return_id,
                "order_id": order_id,
                "order_line_id": order_line_id,
                "returned_quantity": quantity,
                "refund_amount_cents": refund_amount,
                "reversed_points": points_to_reverse,
                "order_status": new_status,
                "qualifying_spend_cents": new_qualifying_spend
            }

        except Exception:
            self.conn.rollback()
            raise

    # ---------------------------------------------------------
    # LOT EXPIRATION
    # ---------------------------------------------------------

    def expire_lot(
        self,
        account_id,
        customer_id,
        lot_id,
        expiry_tx_id,
        executed_at
    ):
        if self.conn.in_transaction:
            self.conn.commit()

        self.conn.execute("BEGIN IMMEDIATE")

        try:
            already = self.conn.execute(
                """
                SELECT 1
                FROM expiry_batch
                WHERE account_id = ?
                  AND lot_id = ?
                """,
                (account_id, lot_id)
            ).fetchone()

            if already:
                self.conn.commit()
                return {
                    "status": "ALREADY_EXPIRED",
                    "expired_points": 0
                }

            accrual = self.conn.execute(
                """
                SELECT MIN(created_at), MAX(expires_at)
                FROM points_transaction
                WHERE account_id = ?
                  AND lot_id = ?
                  AND transaction_type = 'ACCRUAL'
                """,
                (account_id, lot_id)
            ).fetchone()

            if not accrual or not accrual[0]:
                raise ValueError("Unknown accrual lot")

            expires_at = accrual[1]

            if not expires_at:
                raise ValueError("Lot has no expiry date")

            if expires_at > executed_at:
                raise ValueError("Lot has not expired yet")

            amount = self._lot_balance(
                account_id,
                lot_id,
                executed_at
            )

            if amount <= 0:
                self.conn.commit()
                return {
                    "status": "NOTHING_TO_EXPIRE",
                    "expired_points": 0
                }

            self.conn.execute(
                """
                INSERT INTO points_transaction (
                    transaction_id,
                    account_id,
                    customer_id,
                    transaction_type,
                    points_delta,
                    lot_id,
                    created_at,
                    idempotency_key,
                    notes
                )
                VALUES (?, ?, ?, 'EXPIRY', ?, ?, ?, ?, ?)
                """,
                (
                    expiry_tx_id,
                    account_id,
                    customer_id,
                    -amount,
                    lot_id,
                    executed_at,
                    f"expiry:{account_id}:{lot_id}",
                    "Lot expiration"
                )
            )

            self.conn.execute(
                """
                INSERT INTO expiry_batch (
                    expiry_batch_id,
                    account_id,
                    lot_id,
                    points_transaction_id,
                    expired_points,
                    executed_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    expiry_tx_id.replace("PTS", "EXP"),
                    account_id,
                    lot_id,
                    expiry_tx_id,
                    amount,
                    executed_at
                )
            )

            self.conn.commit()

            return {
                "status": "EXPIRED",
                "expired_points": amount
            }

        except Exception:
            self.conn.rollback()
            raise
