
from pathlib import Path
import sqlite3


SCHEMA = """

-- =====================================================
-- 1. CUSTOMER
-- =====================================================

CREATE TABLE IF NOT EXISTS customer (
    customer_id TEXT PRIMARY KEY,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    signup_date TEXT NOT NULL,
    region TEXT NOT NULL
        CHECK(region IN ('NORTH', 'SOUTH', 'EAST', 'WEST')),
    created_at TEXT NOT NULL
);


-- =====================================================
-- 2. TIER
-- =====================================================

CREATE TABLE IF NOT EXISTS tier (
    tier_id TEXT PRIMARY KEY,
    tier_name TEXT NOT NULL UNIQUE,
    min_qualifying_spend_cents INTEGER NOT NULL
        CHECK(min_qualifying_spend_cents >= 0),
    earning_rate_bps INTEGER NOT NULL
        CHECK(earning_rate_bps >= 0),
    effective_from TEXT NOT NULL,
    effective_to TEXT,

    CHECK(
        effective_to IS NULL
        OR effective_to >= effective_from
    )
);


-- =====================================================
-- 3. RULE
-- =====================================================

CREATE TABLE IF NOT EXISTS rule (
    rule_id TEXT PRIMARY KEY,
    rule_name TEXT NOT NULL,
    rule_type TEXT NOT NULL
        CHECK(rule_type IN (
            'EARN',
            'REDEEM',
            'EXPIRY',
            'REVERSAL'
        )),
    points_per_currency_unit INTEGER NOT NULL
        CHECK(points_per_currency_unit >= 0),
    effective_from TEXT NOT NULL,
    effective_to TEXT,
    is_active INTEGER NOT NULL
        CHECK(is_active IN (0, 1)),

    CHECK(
        effective_to IS NULL
        OR effective_to >= effective_from
    )
);


-- =====================================================
-- 4. LOYALTY ACCOUNT
-- =====================================================

CREATE TABLE IF NOT EXISTS loyalty_account (
    account_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL UNIQUE,
    tier_id TEXT NOT NULL,
    opened_at TEXT NOT NULL,
    status TEXT NOT NULL
        CHECK(status IN (
            'ACTIVE',
            'SUSPENDED',
            'CLOSED'
        )),

    FOREIGN KEY(customer_id)
        REFERENCES customer(customer_id),

    FOREIGN KEY(tier_id)
        REFERENCES tier(tier_id)
);


-- =====================================================
-- 5. ORDER
-- =====================================================

CREATE TABLE IF NOT EXISTS orders (
    order_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    order_date TEXT NOT NULL,
    currency TEXT NOT NULL DEFAULT 'INR'
        CHECK(currency = 'INR'),
    gross_amount_cents INTEGER NOT NULL
        CHECK(gross_amount_cents >= 0),
    discount_cents INTEGER NOT NULL
        CHECK(discount_cents >= 0),
    status TEXT NOT NULL
        CHECK(status IN (
            'COMPLETED',
            'PARTIALLY_RETURNED',
            'RETURNED',
            'CANCELLED'
        )),
    qualifying_spend_cents INTEGER NOT NULL
        CHECK(qualifying_spend_cents >= 0),

    FOREIGN KEY(customer_id)
        REFERENCES customer(customer_id),

    CHECK(discount_cents <= gross_amount_cents),
    CHECK(qualifying_spend_cents <= gross_amount_cents)
);


-- =====================================================
-- 6. ORDER LINE
-- =====================================================

CREATE TABLE IF NOT EXISTS order_line (
    order_line_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL,
    sku TEXT NOT NULL,
    quantity INTEGER NOT NULL
        CHECK(quantity > 0),
    unit_price_cents INTEGER NOT NULL
        CHECK(unit_price_cents >= 0),
    returned_quantity INTEGER NOT NULL DEFAULT 0
        CHECK(
            returned_quantity >= 0
            AND returned_quantity <= quantity
        ),

    FOREIGN KEY(order_id)
        REFERENCES orders(order_id)
);


-- =====================================================
-- 7. REWARD
-- =====================================================

CREATE TABLE IF NOT EXISTS reward (
    reward_id TEXT PRIMARY KEY,
    reward_name TEXT NOT NULL,
    points_cost INTEGER NOT NULL
        CHECK(points_cost > 0),
    is_active INTEGER NOT NULL
        CHECK(is_active IN (0, 1))
);


-- =====================================================
-- 8. POINTS TRANSACTION
-- =====================================================

CREATE TABLE IF NOT EXISTS points_transaction (
    transaction_id TEXT PRIMARY KEY,

    account_id TEXT NOT NULL,
    customer_id TEXT NOT NULL,

    order_id TEXT,

    reference_transaction_id TEXT,

    transaction_type TEXT NOT NULL
        CHECK(transaction_type IN (
            'ACCRUAL',
            'REDEMPTION',
            'REVERSAL',
            'EXPIRY',
            'ADJUSTMENT'
        )),

    points_delta INTEGER NOT NULL
        CHECK(points_delta <> 0),

    lot_id TEXT,

    created_at TEXT NOT NULL,
    expires_at TEXT,

    idempotency_key TEXT NOT NULL UNIQUE,

    notes TEXT,

    FOREIGN KEY(account_id)
        REFERENCES loyalty_account(account_id),

    FOREIGN KEY(customer_id)
        REFERENCES customer(customer_id),

    FOREIGN KEY(order_id)
        REFERENCES orders(order_id),

    FOREIGN KEY(reference_transaction_id)
        REFERENCES points_transaction(transaction_id),

    CHECK(
        expires_at IS NULL
        OR expires_at >= created_at
    )
);

-- =====================================================
-- POINTS ALLOCATION
-- Tracks which accrual lots fund each redemption.
-- =====================================================

CREATE TABLE IF NOT EXISTS points_allocation (
    allocation_id TEXT PRIMARY KEY,
    transaction_id TEXT NOT NULL,
    lot_id TEXT NOT NULL,
    points_allocated INTEGER NOT NULL CHECK (points_allocated > 0),

    FOREIGN KEY (transaction_id)
        REFERENCES points_transaction(transaction_id)
);

CREATE INDEX IF NOT EXISTS idx_points_allocation_lot
ON points_allocation(lot_id);

-- =====================================================
-- 9. REDEMPTION
-- =====================================================

CREATE TABLE IF NOT EXISTS redemption (
    redemption_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    reward_id TEXT NOT NULL,
    points_transaction_id TEXT UNIQUE,
    requested_points INTEGER NOT NULL CHECK (requested_points > 0),
    status TEXT NOT NULL CHECK (status IN ('APPROVED', 'REJECTED')),
    created_at TEXT NOT NULL,
    rejection_reason TEXT,

    FOREIGN KEY (account_id)
        REFERENCES loyalty_account(account_id),

    FOREIGN KEY (reward_id)
        REFERENCES reward(reward_id),

    FOREIGN KEY (points_transaction_id)
        REFERENCES points_transaction(transaction_id),

    CHECK (
        (status = 'APPROVED'
            AND points_transaction_id IS NOT NULL
            AND rejection_reason IS NULL)
        OR
        (status = 'REJECTED'
            AND points_transaction_id IS NULL
            AND rejection_reason IS NOT NULL)
    )
);

-- =====================================================
-- 10. EXPIRY BATCH
-- =====================================================

CREATE TABLE IF NOT EXISTS expiry_batch (
    expiry_batch_id TEXT PRIMARY KEY,

    account_id TEXT NOT NULL,

    lot_id TEXT NOT NULL,

    points_transaction_id TEXT NOT NULL UNIQUE,

    expired_points INTEGER NOT NULL
        CHECK(expired_points > 0),

    executed_at TEXT NOT NULL,

    FOREIGN KEY(account_id)
        REFERENCES loyalty_account(account_id),

    FOREIGN KEY(points_transaction_id)
        REFERENCES points_transaction(transaction_id),

    UNIQUE(account_id, lot_id)
);


-- =====================================================
-- 11. ACCOUNT EVENT HISTORY
-- =====================================================

CREATE TABLE IF NOT EXISTS account_event (
    event_id TEXT PRIMARY KEY,

    account_id TEXT NOT NULL,

    event_type TEXT NOT NULL
        CHECK(event_type IN (
            'TIER_CHANGED',
            'STATUS_CHANGED',
            'ACCOUNT_OPENED',
            'ACCOUNT_CLOSED'
        )),

    old_value TEXT,

    new_value TEXT,

    event_at TEXT NOT NULL,

    reason TEXT NOT NULL,

    FOREIGN KEY(account_id)
        REFERENCES loyalty_account(account_id)
);

-- =====================================================
-- 12. RETURN EVENT HISTORY
-- Append-only record of partial and full order returns.
-- =====================================================

CREATE TABLE IF NOT EXISTS return_event (
    return_id TEXT PRIMARY KEY,

    order_id TEXT NOT NULL,
    order_line_id TEXT NOT NULL,

    returned_quantity INTEGER NOT NULL
        CHECK(returned_quantity > 0),

    refund_amount_cents INTEGER NOT NULL
        CHECK(refund_amount_cents >= 0),

    reversed_points INTEGER NOT NULL
        CHECK(reversed_points >= 0),

    reversal_transaction_id TEXT UNIQUE,

    created_at TEXT NOT NULL,
    reason TEXT NOT NULL,

    FOREIGN KEY(order_id)
        REFERENCES orders(order_id),

    FOREIGN KEY(order_line_id)
        REFERENCES order_line(order_line_id),

    FOREIGN KEY(reversal_transaction_id)
        REFERENCES points_transaction(transaction_id)
);

CREATE INDEX IF NOT EXISTS idx_return_order
ON return_event(order_id);

CREATE INDEX IF NOT EXISTS idx_return_line
ON return_event(order_line_id);

-- =====================================================
-- INDEXES FOR PERFORMANCE
-- =====================================================

CREATE INDEX IF NOT EXISTS idx_customer_email
ON customer(email);


CREATE INDEX IF NOT EXISTS idx_orders_customer
ON orders(customer_id);


CREATE INDEX IF NOT EXISTS idx_orders_date
ON orders(order_date);


CREATE INDEX IF NOT EXISTS idx_order_line_order
ON order_line(order_id);


CREATE INDEX IF NOT EXISTS idx_account_customer
ON loyalty_account(customer_id);


CREATE INDEX IF NOT EXISTS idx_account_tier
ON loyalty_account(tier_id);


CREATE INDEX IF NOT EXISTS idx_points_account
ON points_transaction(account_id);


CREATE INDEX IF NOT EXISTS idx_points_customer
ON points_transaction(customer_id);


CREATE INDEX IF NOT EXISTS idx_points_order
ON points_transaction(order_id);


CREATE INDEX IF NOT EXISTS idx_points_type
ON points_transaction(transaction_type);


CREATE INDEX IF NOT EXISTS idx_points_reference
ON points_transaction(reference_transaction_id);


CREATE INDEX IF NOT EXISTS idx_points_lot_expiry
ON points_transaction(account_id, lot_id, expires_at);


CREATE INDEX IF NOT EXISTS idx_redemption_account
ON redemption(account_id);


CREATE INDEX IF NOT EXISTS idx_expiry_account
ON expiry_batch(account_id);


CREATE INDEX IF NOT EXISTS idx_account_event_account
ON account_event(account_id, event_at);

"""


# =========================================================
# DATABASE CONNECTION
# =========================================================

def connect(path="data/loyalty.db"):

    database_path = Path(path)

    database_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    conn = sqlite3.connect(
        str(database_path),
        timeout=30.0
    )

    conn.execute("PRAGMA foreign_keys = ON")

    conn.execute("PRAGMA busy_timeout = 30000")

    conn.execute("PRAGMA journal_mode = WAL")

    conn.execute("PRAGMA synchronous = NORMAL")

    conn.executescript(SCHEMA)

    return conn


# =========================================================
# DATABASE INTEGRITY CHECK
# =========================================================

def check_database_integrity(conn):

    foreign_key_errors = conn.execute(
        "PRAGMA foreign_key_check"
    ).fetchall()

    integrity_result = conn.execute(
        "PRAGMA integrity_check"
    ).fetchone()[0]

    return {
        "integrity_check": integrity_result,
        "foreign_key_violations": len(foreign_key_errors),
        "foreign_key_errors": foreign_key_errors,
        "passed": (
            integrity_result == "ok"
            and len(foreign_key_errors) == 0
        )
    }


# =========================================================
# DATABASE TABLE INFORMATION
# =========================================================

def get_table_counts(conn):

    tables = [
        "customer",
        "loyalty_account",
        "tier",
        "rule",
        "orders",
        "order_line",
        "points_transaction",
        "reward",
        "redemption",
        "expiry_batch",
        "account_event"
    ]

    counts = {}

    for table in tables:

        result = conn.execute(
            f"SELECT COUNT(*) FROM {table}"
        ).fetchone()

        counts[table] = result[0]

    return counts
