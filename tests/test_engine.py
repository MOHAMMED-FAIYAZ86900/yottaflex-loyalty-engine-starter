
import pytest

from loyalty.db import connect
from loyalty.engine import LoyaltyEngine


def setup_account(tmp_path):
    c = connect(tmp_path / "t.db")

    c.execute(
        "INSERT INTO customer VALUES (?,?,?,?,?,?)",
        (
            "CUST-000001",
            "A",
            "a@test.test",
            "2026-01-01",
            "WEST",
            "2026-01-01T00:00:00"
        )
    )

    c.execute(
        "INSERT INTO tier VALUES (?,?,?,?,?,?)",
        ("TIER-BRONZE", "Bronze", 0, 100, "2026-01-01", None)
    )

    c.execute(
        "INSERT INTO loyalty_account VALUES (?,?,?,?,?)",
        (
            "LOY-CUST-000001",
            "CUST-000001",
            "TIER-BRONZE",
            "2026-01-01",
            "ACTIVE"
        )
    )

    c.execute(
        "INSERT INTO reward VALUES (?,?,?,?)",
        ("RWD-1000", "Voucher", 1000, 1)
    )

    c.execute(
        "INSERT INTO orders VALUES (?,?,?,?,?,?,?,?)",
        (
            "ORD-2026-000001",
            "CUST-000001",
            "2026-01-01",
            "INR",
            150000,
            0,
            "COMPLETED",
            150000
        )
    )

    c.commit()
    return c


def add_accrual(engine, points, tx_id, lot_id, expires_at):
    engine.accrue(
        "LOY-CUST-000001",
        "CUST-000001",
        "ORD-2026-000001",
        points,
        "2026-01-01T12:00:00",
        expires_at,
        tx_id,
        lot_id
    )


# 1. Original accrual and reversal test
def test_accrual_balance_and_reversal(tmp_path):
    c = setup_account(tmp_path)
    e = LoyaltyEngine(c)

    add_accrual(
        e, 500, "PTS-2026-00000001",
        "LOT-1", "2027-01-01T00:00:00"
    )

    assert e.balance("LOY-CUST-000001") == 500

    e.reverse_accrual(
        "PTS-2026-00000001",
        "PTS-2026-00000002",
        "2026-01-02T12:00:00"
    )

    assert e.balance("LOY-CUST-000001") == 0


# 2. Original insufficient-balance test
def test_redeem_rejects_insufficient_balance(tmp_path):
    c = setup_account(tmp_path)
    e = LoyaltyEngine(c)

    result = e.redeem(
        "LOY-CUST-000001",
        "CUST-000001",
        "RWD-1000",
        1000,
        "2026-01-01T12:00:00",
        "RDM-2026-000001",
        "PTS-2026-00000001"
    )

    assert result["status"] == "REJECTED"
    assert e.balance("LOY-CUST-000001") == 0


# 3. Original approved-redemption test
def test_redeem_approved(tmp_path):
    c = setup_account(tmp_path)
    e = LoyaltyEngine(c)

    add_accrual(
        e, 1500, "PTS-2026-00000001",
        "LOT-1", "2027-01-01T00:00:00"
    )

    result = e.redeem(
        "LOY-CUST-000001",
        "CUST-000001",
        "RWD-1000",
        1000,
        "2026-01-02T12:00:00",
        "RDM-2026-000001",
        "PTS-2026-00000002"
    )

    assert result["status"] == "APPROVED"
    assert e.balance("LOY-CUST-000001") == 500


# 4. FIFO allocation across multiple accrual lots
def test_redemption_allocates_points_fifo(tmp_path):
    c = setup_account(tmp_path)
    e = LoyaltyEngine(c)

    add_accrual(
        e, 600, "PTS-2026-00000001",
        "LOT-1", "2027-01-01T00:00:00"
    )

    # Use a distinct order ID for the second accrual.
    e.conn.execute(
        "INSERT INTO orders VALUES (?,?,?,?,?,?,?,?)",
        (
            "ORD-2026-000002",
            "CUST-000001",
            "2026-01-02",
            "INR",
            150000,
            0,
            "COMPLETED",
            150000
        )
    )

    e.accrue(
        "LOY-CUST-000001",
        "CUST-000001",
        "ORD-2026-000002",
        700,
        "2026-01-02T12:00:00",
        "2027-01-01T00:00:00",
        "PTS-2026-00000002",
        "LOT-2"
    )

    result = e.redeem(
        "LOY-CUST-000001",
        "CUST-000001",
        "RWD-1000",
        800,
        "2026-01-03T12:00:00",
        "RDM-2026-000001",
        "PTS-2026-00000003"
    )

    assert result["status"] == "APPROVED"
    assert result["allocations"] == [("LOT-1", 600), ("LOT-2", 200)]

    assert e._lot_balance("LOY-CUST-000001", "LOT-1") == 0
    assert e._lot_balance("LOY-CUST-000001", "LOT-2") == 500
    assert e.balance("LOY-CUST-000001") == 500


# 5. Do not expire a lot before its expiry date
def test_expiration_rejected_before_expiry(tmp_path):
    c = setup_account(tmp_path)
    e = LoyaltyEngine(c)

    add_accrual(
        e, 1000, "PTS-2026-00000001",
        "LOT-1", "2026-01-10T00:00:00"
    )

    with pytest.raises(ValueError, match="not expired"):
        e.expire_lot(
            "LOY-CUST-000001",
            "CUST-000001",
            "LOT-1",
            "PTS-2026-00000002",
            "2026-01-09T00:00:00"
        )

    assert e.balance("LOY-CUST-000001") == 1000


# 6. Expire only the unredeemed remainder
def test_expiration_expires_remaining_lot_balance(tmp_path):
    c = setup_account(tmp_path)
    e = LoyaltyEngine(c)

    add_accrual(
        e, 1000, "PTS-2026-00000001",
        "LOT-1", "2026-01-10T00:00:00"
    )

    e.redeem(
        "LOY-CUST-000001",
        "CUST-000001",
        "RWD-1000",
        300,
        "2026-01-02T12:00:00",
        "RDM-2026-000001",
        "PTS-2026-00000002"
    )

    result = e.expire_lot(
        "LOY-CUST-000001",
        "CUST-000001",
        "LOT-1",
        "PTS-2026-00000003",
        "2026-01-11T00:00:00"
    )

    assert result["status"] == "EXPIRED"
    assert result["expired_points"] == 700
    assert e.balance("LOY-CUST-000001") == 0


# 7. Prevent a second expiration of the same lot
def test_duplicate_expiration_is_idempotent(tmp_path):
    c = setup_account(tmp_path)
    e = LoyaltyEngine(c)

    add_accrual(
        e, 1000, "PTS-2026-00000001",
        "LOT-1", "2026-01-10T00:00:00"
    )

    first = e.expire_lot(
        "LOY-CUST-000001",
        "CUST-000001",
        "LOT-1",
        "PTS-2026-00000002",
        "2026-01-11T00:00:00"
    )

    second = e.expire_lot(
        "LOY-CUST-000001",
        "CUST-000001",
        "LOT-1",
        "PTS-2026-00000003",
        "2026-01-12T00:00:00"
    )

    assert first["status"] == "EXPIRED"
    assert second["status"] == "ALREADY_EXPIRED"
    assert e.balance("LOY-CUST-000001") == 0


# 8. Duplicate redemption request must not deduct points twice
def test_duplicate_redemption_request(tmp_path):
    c = setup_account(tmp_path)
    e = LoyaltyEngine(c)

    add_accrual(
        e, 1000, "PTS-2026-00000001",
        "LOT-1", "2027-01-01T00:00:00"
    )

    first = e.redeem(
        "LOY-CUST-000001",
        "CUST-000001",
        "RWD-1000",
        500,
        "2026-01-02T12:00:00",
        "RDM-2026-000001",
        "PTS-2026-00000002"
    )

    second = e.redeem(
        "LOY-CUST-000001",
        "CUST-000001",
        "RWD-1000",
        500,
        "2026-01-02T12:00:00",
        "RDM-2026-000001",
        "PTS-2026-00000003"
    )

    assert first["status"] == "APPROVED"
    assert second["status"] == "APPROVED"
    assert second["duplicate"] is True
    assert e.balance("LOY-CUST-000001") == 500


# 9. Do not reverse an accrual after points have been consumed
def test_reversal_rejected_after_redemption(tmp_path):
    c = setup_account(tmp_path)
    e = LoyaltyEngine(c)

    add_accrual(
        e, 1000, "PTS-2026-00000001",
        "LOT-1", "2027-01-01T00:00:00"
    )

    e.redeem(
        "LOY-CUST-000001",
        "CUST-000001",
        "RWD-1000",
        300,
        "2026-01-02T12:00:00",
        "RDM-2026-000001",
        "PTS-2026-00000002"
    )

    with pytest.raises(ValueError, match="already been consumed"):
        e.reverse_accrual(
            "PTS-2026-00000001",
            "PTS-2026-00000003",
            "2026-01-03T12:00:00"
        )

    assert e.balance("LOY-CUST-000001") == 700


# 10. Partial return reverses proportional points
def test_partial_return_reverses_proportional_points(tmp_path):
    c = setup_account(tmp_path)
    e = LoyaltyEngine(c)

    c.execute(
        """
        INSERT INTO order_line (
            order_line_id, order_id, sku, quantity, unit_price_cents
        ) VALUES (?, ?, ?, ?, ?)
        """,
        ("LINE-001", "ORD-2026-000001", "SKU-001", 3, 50000)
    )
    c.commit()

    add_accrual(
        e, 500, "PTS-2026-00000001",
        "LOT-1", "2027-01-01T00:00:00"
    )

    result = e.return_order_line(
        order_id="ORD-2026-000001",
        order_line_id="LINE-001",
        quantity=1,
        return_id="RET-001",
        reversal_tx_id="PTS-2026-00000002",
        created_at="2026-02-01T12:00:00"
    )

    assert result["status"] == "RETURN_PROCESSED"
    assert result["refund_amount_cents"] == 50000
    assert result["reversed_points"] == 166
    assert e.balance("LOY-CUST-000001") == 334

    returned = c.execute(
        """
        SELECT returned_quantity
        FROM order_line
        WHERE order_line_id = 'LINE-001'
        """
    ).fetchone()[0]

    assert returned == 1

    reversal = c.execute(
        """
        SELECT points_delta, reference_transaction_id
        FROM points_transaction
        WHERE transaction_id = 'PTS-2026-00000002'
        """
    ).fetchone()

    assert reversal["points_delta"] == -166
    assert reversal["reference_transaction_id"] == "PTS-2026-00000001"

    c.close()


# 11. Multiple partial returns must reverse exactly the original points
def test_multiple_partial_returns_reverse_exact_points(tmp_path):
    c = setup_account(tmp_path)
    e = LoyaltyEngine(c)

    c.execute(
        """
        INSERT INTO order_line (
            order_line_id, order_id, sku, quantity, unit_price_cents
        ) VALUES (?, ?, ?, ?, ?)
        """,
        ("LINE-001", "ORD-2026-000001", "SKU-001", 3, 50000)
    )
    c.commit()

    add_accrual(
        e, 500, "PTS-2026-00000001",
        "LOT-1", "2027-01-01T00:00:00"
    )

    first = e.return_order_line(
        "ORD-2026-000001", "LINE-001", 1,
        "RET-001", "PTS-2026-00000002",
        "2026-02-01T12:00:00"
    )

    second = e.return_order_line(
        "ORD-2026-000001", "LINE-001", 1,
        "RET-002", "PTS-2026-00000003",
        "2026-02-02T12:00:00"
    )

    third = e.return_order_line(
        "ORD-2026-000001", "LINE-001", 1,
        "RET-003", "PTS-2026-00000004",
        "2026-02-03T12:00:00"
    )

    assert first["reversed_points"] == 166
    assert second["reversed_points"] == 167
    assert third["reversed_points"] == 167

    assert e.balance("LOY-CUST-000001") == 0
    assert third["order_status"] == "RETURNED"

    total_reversed = c.execute(
        """
        SELECT COALESCE(SUM(-points_delta), 0)
        FROM points_transaction
        WHERE transaction_type = 'REVERSAL'
        """
    ).fetchone()[0]

    assert total_reversed == 500

    total_refund = c.execute(
        """
        SELECT SUM(refund_amount_cents)
        FROM return_event
        """
    ).fetchone()[0]

    assert total_refund == 150000

    c.close()


# 12. Duplicate return ID must not process the return twice
def test_duplicate_return_is_idempotent(tmp_path):
    c = setup_account(tmp_path)
    e = LoyaltyEngine(c)

    c.execute(
        """
        INSERT INTO order_line (
            order_line_id, order_id, sku, quantity, unit_price_cents
        ) VALUES (?, ?, ?, ?, ?)
        """,
        ("LINE-001", "ORD-2026-000001", "SKU-001", 3, 50000)
    )
    c.commit()

    add_accrual(
        e, 500, "PTS-2026-00000001",
        "LOT-1", "2027-01-01T00:00:00"
    )

    first = e.return_order_line(
        "ORD-2026-000001", "LINE-001", 1,
        "RET-001", "PTS-2026-00000002",
        "2026-02-01T12:00:00"
    )

    second = e.return_order_line(
        "ORD-2026-000001", "LINE-001", 1,
        "RET-001", "PTS-2026-00000003",
        "2026-02-01T12:00:00"
    )

    assert first["status"] == "RETURN_PROCESSED"
    assert second["status"] == "DUPLICATE"
    assert e.balance("LOY-CUST-000001") == 334

    count = c.execute(
        "SELECT COUNT(*) FROM return_event"
    ).fetchone()[0]

    assert count == 1

    c.close()


# 13. Reject return quantity greater than purchased quantity
def test_return_rejects_excess_quantity(tmp_path):
    c = setup_account(tmp_path)
    e = LoyaltyEngine(c)

    c.execute(
        """
        INSERT INTO order_line (
            order_line_id, order_id, sku, quantity, unit_price_cents
        ) VALUES (?, ?, ?, ?, ?)
        """,
        ("LINE-001", "ORD-2026-000001", "SKU-001", 2, 75000)
    )
    c.commit()

    add_accrual(
        e, 500, "PTS-2026-00000001",
        "LOT-1", "2027-01-01T00:00:00"
    )

    with pytest.raises(ValueError, match="exceeds"):
        e.return_order_line(
            "ORD-2026-000001", "LINE-001", 3,
            "RET-001", "PTS-2026-00000002",
            "2026-02-01T12:00:00"
        )

    assert e.balance("LOY-CUST-000001") == 500

    count = c.execute(
        "SELECT COUNT(*) FROM return_event"
    ).fetchone()[0]

    assert count == 0

    c.close()
