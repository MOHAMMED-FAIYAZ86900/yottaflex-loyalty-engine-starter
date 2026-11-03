# Data Dictionary (initial schema)

All monetary values are integer paise (INR); timestamps/dates are ISO-8601 text. PK = primary key; FK = foreign key.

| Entity | Field | Type | Required | Key / validation |
|---|---|---|---|---|
| Customer | customer_id | TEXT | Yes | PK; `CUST-` plus six digits |
| Customer | full_name | TEXT | Yes | Synthetic display name |
| Customer | email | TEXT | Yes | Unique; `.test` domain |
| Customer | signup_date | DATE | Yes | ISO date |
| Customer | region | ENUM | Yes | NORTH/SOUTH/EAST/WEST |
| LoyaltyAccount | account_id | TEXT | Yes | PK; `LOY-<customer_id>` |
| LoyaltyAccount | customer_id | TEXT | Yes | FK, unique; 1:1 with Customer |
| LoyaltyAccount | tier_id | TEXT | Yes | FK to Tier |
| LoyaltyAccount | status | ENUM | Yes | ACTIVE/SUSPENDED/CLOSED |
| Tier | tier_id | TEXT | Yes | PK |
| Tier | tier_name | TEXT | Yes | Unique |
| Tier | min_qualifying_spend_cents | INTEGER | Yes | >= 0 |
| Tier | earning_rate_bps | INTEGER | Yes | >= 0; 100 bps = 1 point/INR |
| Rule | rule_id | TEXT | Yes | PK |
| Rule | rule_type | TEXT | Yes | EARN in initial version |
| Rule | points_per_currency_unit | INTEGER | Yes | >= 0 |
| Order | order_id | TEXT | Yes | PK; `ORD-2026-` + six digits |
| Order | customer_id | TEXT | Yes | FK to Customer |
| Order | gross_amount_cents | INTEGER | Yes | >= 0 |
| Order | discount_cents | INTEGER | Yes | >= 0 and <= gross |
| Order | qualifying_spend_cents | INTEGER | Yes | >= 0; net eligible spend |
| OrderLine | order_line_id | TEXT | Yes | PK |
| OrderLine | order_id | TEXT | Yes | FK to Order |
| OrderLine | quantity | INTEGER | Yes | > 0 |
| OrderLine | returned_quantity | INTEGER | Yes | 0..quantity |
| PointsTransaction | transaction_id | TEXT | Yes | PK; `PTS-2026-` + eight digits |
| PointsTransaction | account_id | TEXT | Yes | FK to LoyaltyAccount |
| PointsTransaction | customer_id | TEXT | Yes | FK to Customer |
| PointsTransaction | order_id | TEXT | No | FK to Order |
| PointsTransaction | reference_transaction_id | TEXT | No | FK to original transaction |
| PointsTransaction | transaction_type | ENUM | Yes | ACCRUAL/REDEMPTION/REVERSAL/EXPIRY/ADJUSTMENT |
| PointsTransaction | points_delta | INTEGER | Yes | Non-zero; positive earn, negative debit |
| PointsTransaction | lot_id | TEXT | No | Accrual lot identifier |
| PointsTransaction | expires_at | TIMESTAMP | No | Expiry timestamp |
| Reward | reward_id | TEXT | Yes | PK |
| Reward | points_cost | INTEGER | Yes | > 0 |
| Redemption | redemption_id | TEXT | Yes | PK; `RDM-2026-` + six digits |
| Redemption | status | ENUM | Yes | APPROVED/REJECTED |
| ExpiryBatch | expiry_batch_id | TEXT | Yes | PK; `EXP-2026-` + six digits |
| ExpiryBatch | lot_id | TEXT | Yes | Unique per account/lot |

This is the initial dictionary; extend it to include every SQL column, effective-date overlap rules, lifecycle transitions and all optionality before final submission.
