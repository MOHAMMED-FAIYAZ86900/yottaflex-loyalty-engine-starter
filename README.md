# YottaFlex Loyalty Engine
### Deterministic Loyalty Data Generation, Transaction Processing and Validation

**Project:** YottaFlex Loyalty Engine — Round 2 Coding Challenge  
**Role:** Associate AI Forward Deployed Engineer  
**Language:** Python  
**Database:** SQLite  
**Test Framework:** pytest  
**Random Seed:** `20261022`  
**Dataset Scale:** 20,000 customers · 100,000 orders · 317,987 points transactions

---

## 1. Project Overview

The YottaFlex Loyalty Engine is a deterministic, database-backed loyalty transaction simulation and data-generation system.

It models a customer loyalty program from customer onboarding through order processing, points accrual, redemption, returns, reversals, expiry, and tier progression.

The system generates a relational dataset with explicit transaction history and referential integrity. It also implements business rules for calculating available points, processing redemptions, reversing points after returns, expiring unused points, and determining customer tiers using qualifying spend.

The project is designed to demonstrate:

- Relational database design and data integrity.
- Loyalty program business-rule implementation.
- Deterministic synthetic data generation.
- Transaction lifecycle management.
- Points accounting and lot-level tracking.
- Edge-case and anomaly scenario construction.
- Automated validation and testing.
- Dataset export and reproducibility.

The generated data is intended for downstream analytics, anomaly detection, business-rule evaluation, and data-quality testing.

## 2. Key Features

### 2.1 Customer and loyalty account management

- Generates 20,000 customer records.
- Creates a corresponding loyalty account for each customer.
- Maintains customer-to-account relationships.
- Tracks account lifecycle and tier-related events.
- Uses stable identifiers for generated records.

### 2.2 Order processing

- Generates 100,000 orders.
- Generates individual order-line records.
- Tracks order totals, quantities, unit prices, and returned quantities.
- Supports completed, partially returned, returned, and cancelled order statuses.
- Maintains order and order-line relationships.

### 2.3 Points accrual

- Calculates points based on eligible order value and the configured earning rule.
- Creates explicit accrual transactions.
- Associates points with their originating accrual lots.
- Maintains transaction history rather than relying only on a stored balance.

### 2.4 Points redemption

- Checks available points before approving a redemption.
- Rejects requests that exceed available points.
- Records approved and rejected redemption attempts.
- Uses FIFO allocation to consume available points from eligible lots.
- Uses database transactions to protect redemption operations.
- Supports idempotency for duplicate redemption requests.

### 2.5 Returns and points reversal

- Supports partial and full order-line returns.
- Calculates proportional refunds.
- Reverses points associated with returned quantities.
- Updates order status and qualifying spend.
- Records return events and their corresponding reversal transactions.
- Prevents repeated processing of the same return request.

### 2.6 Points expiry

- Tracks points at the accrual-lot level.
- Expires eligible remaining points.
- Records expiry transactions and expiry batches.
- Prevents duplicate expiry processing for the same lot.

### 2.7 Tier progression

The generated loyalty program uses four tiers:

| Tier | Qualifying Spend Threshold | Earning Rate |
|---|---:|---:|
| Bronze | ₹0 | 100 bps |
| Silver | ₹5,000 | 125 bps |
| Gold | ₹15,000 | 150 bps |
| Platinum | ₹30,000 | 200 bps |

Earning rates are represented in basis points (bps), where 100 bps = 1%.

Tier evaluation uses qualifying spend rather than gross historical order value. Returned amounts are deducted from qualifying spend.

Tier changes are retained as account events, including downgrades caused by returns.

---

## 3. Technology Stack

| Component | Technology |
|---|---|
| Programming language | Python 3 |
| Database | SQLite |
| Database interface | Python `sqlite3` |
| Automated testing | pytest |
| Data export | Python CSV and JSON modules |
| SQL export | SQLite SQL dump |
| Version control | Git |
| Repository hosting | GitHub |

The implementation uses SQLite for persistent relational storage and Python for business logic, deterministic generation, validation, and exports.

---

## 4. Project Structure

```text
yottaflex-loyalty-engine/
│
├── src/
│   └── loyalty/
│       ├── __init__.py
│       ├── db.py
│       ├── engine.py
│       ├── generator.py
│       ├── validate.py
│       └── cli.py
│
├── tests/
│   └── test_engine.py
│
├── scripts/
│   ├── export_dataset.py
│   └── generate_edge_cases.py
│
├── data/
│   └── loyalty_phase4.db
│
├── exports/
│   ├── dataset/
│   │   ├── customer.csv
│   │   ├── customer.json
│   │   ├── loyalty_account.csv
│   │   ├── loyalty_account.json
│   │   ├── orders.csv
│   │   ├── orders.json
│   │   ├── points_transaction.csv.gz
│   │   ├── source_manifest.json
│   │   └── ...
│   │
│   ├── edge_case_scenarios.csv
│   └── edge_case_ground_truth.csv
│
├── reports/
│   └── anomaly_ground_truth.csv
│
├── README.md
├── DATA_DICTIONARY.md
├── PROMPT_HISTORY.md
├── SUBMISSION_STATUS.md
└── .gitignore
```

**Note:** The exact contents of generated data and report directories depend on which generation and export scripts have been run. Large local exports may be excluded from the public GitHub repository.

---

## 5. Database Architecture

The system uses a relational schema with primary keys, foreign keys, and explicit relationships.

### 5.1 Core entities

| Entity | Purpose |
|---|---|
| `customer` | Stores customer master records. |
| `loyalty_account` | Stores customer loyalty account information. |
| `tier` | Defines loyalty tiers and earning thresholds. |
| `rule` | Stores configured loyalty business rules. |
| `orders` | Stores order-level information. |
| `order_line` | Stores individual items within an order. |
| `reward` | Stores available reward definitions. |
| `points_transaction` | Stores accrual, redemption, reversal, expiry, and adjustment transactions. |
| `points_allocation` | Links redemption transactions to the points lots consumed. |
| `redemption` | Stores approved and rejected redemption requests. |
| `expiry_batch` | Records points-lot expiry processing. |
| `account_event` | Stores account and tier lifecycle events. |
| `return_event` | Stores order-line return and reversal information. |

### 5.2 Relationships

The principal relationships are:

- One customer can have one loyalty account.
- One loyalty account can have many orders.
- One order can have multiple order lines.
- One loyalty account can have multiple points transactions.
- An accrual transaction can create a points lot.
- A redemption can consume points from multiple lots.
- A points allocation connects a redemption with the accrual lot consumed.
- An order line can have return events.
- Return events can reference the corresponding points reversal.
- Expiry batches identify the points lots processed for expiry.
- Account events preserve tier and account lifecycle history.

### 5.3 Primary and foreign key integrity

The database uses primary keys to identify records and foreign keys to preserve relationships.

SQLite foreign-key enforcement is enabled by the database connection layer.

The database also uses transaction handling for critical operations such as redemption and returns.

---

## 6. Identifier Formats

The system uses structured identifiers for important business entities.

| Entity | Identifier format | Example |
|---|---|---|
| Loyalty account | `LOY-<customer-id>` | `LOY-C000001` |
| Order | `ORD-2026-<sequence>` | `ORD-2026-000001` |
| Points transaction | `PTS-2026-<sequence>` | `PTS-2026-00000001` |
| Redemption | `RDM-2026-<sequence>` | `RDM-2026-000001` |
| Expiry batch | `EXP-2026-<sequence>` | `EXP-2026-000001` |

These identifiers make generated records easier to inspect and trace.

---

## 7. Business Logic

### 7.1 Points balance

The authoritative points balance is calculated from the transaction ledger.

Conceptually:

```text
Available Points =
    Accruals
  + Adjustments
  - Redemptions
  - Reversals
  - Expiries
```

The implementation also tracks remaining balances at the accrual-lot level so that redemption and expiry operations can identify which points are available.

### 7.2 Points accrual

When an eligible order is processed:

1. The order is associated with a loyalty account.
2. The eligible order value is calculated.
3. The applicable earning rate is obtained from the tier.
4. The points earned are calculated.
5. An accrual transaction is created.
6. The accrual is available for subsequent redemption or expiry.

### 7.3 Redemption

A redemption request follows this sequence:

1. Identify the loyalty account.
2. Calculate available points.
3. Compare the requested amount with the available balance.
4. Approve or reject the request.
5. Record the redemption request.
6. If approved, create the corresponding points transaction.
7. Allocate consumed points against eligible accrual lots.

The database transaction mechanism prevents an operation from partially updating the account when the operation fails.

### 7.4 Returns and reversals

For a returned order line:

1. Validate the order-line reference.
2. Validate the quantity being returned.
3. Calculate the proportional refund.
4. Calculate the points to reverse.
5. Record the return event.
6. Create a reversal transaction.
7. Update the returned quantity and order status.
8. Recalculate qualifying spend and tier eligibility.

Partial returns are supported. Repeated return requests are checked to prevent duplicate processing.

### 7.5 Expiry

Expiry is processed against individual accrual lots.

The engine:

1. Identifies eligible lots.
2. Calculates the remaining points in each lot.
3. Creates an expiry transaction for the remaining eligible balance.
4. Records an expiry batch.
5. Prevents the same lot from being expired twice.

### 7.6 Tier calculation

Tier eligibility is based on qualifying spend.

```text
Qualifying Spend =
    Eligible Completed Order Value
  - Returned Order Value
```

The tier is recalculated when qualifying spend changes. Account events preserve the resulting tier transitions.

---

## 8. Dataset Generation

### 8.1 Generation configuration

| Parameter | Value |
|---|---:|
| Random seed | `20261022` |
| Customers | 20,000 |
| Orders | 100,000 |
| Order lines | 250,319 |
| Points transactions | 317,987 |
| Redemption attempts | 138,522 |
| Return events | 2,079 |
| Expiry batches | 97,486 |
| Account events | 31,484 |
| Points allocations | 120,265 |

These are the verified counts from the generated Phase 4 dataset.

### 8.2 Deterministic generation

The generator uses a fixed seed:

```text
20261022
```

Using the same seed and the same generation configuration is intended to produce repeatable synthetic data.

A fresh database should be used for each full generation run because the generator refuses to run against a database that already contains customer records.

### 8.3 Generated transaction types

The generated points transaction types include:

- `ACCRUAL`
- `REDEMPTION`
- `REVERSAL`
- `EXPIRY`
- `ADJUSTMENT`

Each transaction is stored as an explicit record.

### 8.4 Returns and rejected redemption attempts

The dataset includes:

- Completed orders.
- Partial and full returns.
- Points reversals.
- Approved redemptions.
- Rejected redemption attempts.
- Points expiry.
- Tier changes after qualifying-spend recalculation.

The generation process also creates simulated competing redemption attempts. These are sequential attempts using the same simulated timestamp; they are not a benchmark of truly simultaneous multi-threaded database contention.

---

## 9. Installation and Setup

### 9.1 Prerequisites

Install the following:

- Python 3.10 or later.
- Git.
- Windows PowerShell, Command Prompt, or a compatible terminal.

The project was developed and tested with Python 3.13.14.

Check Python:

```powershell
python --version
```

Check Git:

```powershell
git --version
```

### 9.2 Clone the repository

```powershell
git clone https://github.com/MOHAMMED-FAIYAZ86900/yottaflex-loyalty-engine-starter.git
```

Navigate to the project directory:

```powershell
cd yottaflex-loyalty-engine-starter
```

If the repository contains an additional nested project directory, enter that directory before running the following commands.

### 9.3 Create a virtual environment

```powershell
python -m venv .venv
```

### 9.4 Activate the virtual environment

```powershell
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation because of the execution policy, use this command for the current terminal session:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Then activate again:

```powershell
.\.venv\Scripts\Activate.ps1
```


### 9.5 Install the project and development dependencies

Upgrade pip:

```powershell
python -m pip install --upgrade pip
```

Install the project in editable mode with development dependencies:

```powershell
python -m pip install -e ".[dev]"
```

This command installs:

- The YottaFlex Loyalty Engine Python package.
- The package dependencies declared in `pyproject.toml`.
- pytest for automated testing.
- The `loyalty` command-line entry point.

Editable installation means that changes to the source code under `src/` are available without reinstalling the project.

### 9.6 Verify the installation

Verify the installed package:

```powershell
python -m pip show yottaflex-loyalty-engine
```

Verify the CLI:

```powershell
loyalty --help
```

Verify pytest:

```powershell
python -m pytest --version
```

Run the automated test suite:

```powershell
python -m pytest -q
```

Expected test result:

```text
13 passed
```

If the `loyalty` command is not recognized, close and reopen the terminal, reactivate `.venv`, and retry.

## 10. Running the Application

Run all commands from the repository root with the virtual environment activated.

### 10.1 Generate the dataset

Use a fresh database path:

```powershell
python -m loyalty.cli --db data/loyalty_phase4.db --customers 20000 --orders 100000 --seed 20261022
```

The generator creates the database and generates the configured dataset.

**Important:** Do not run full generation against an already populated database. Choose a new database path or use a clean database.

### 10.2 Validate an existing database

```powershell
python -m loyalty.cli --db data/loyalty_phase4.db --validate-only
```

The validation process checks database integrity and business-rule consistency.

### 10.3 Run automated tests

```powershell
python -m pytest -v
```

For concise output:

```powershell
python -m pytest -q
```

---

## 11. Generating Edge-Case Scenarios

The project contains a separate script for creating the five required edge-case fixtures.

Run:

```powershell
python scripts/generate_edge_cases.py
```

The script produces scenario and ground-truth exports under `exports/`.

### Required edge cases

| ID | Scenario | Expected outcome |
|---|---|---|
| EC-001 | Balance differs from ledger sum | `FLAG_BALANCE_MISMATCH` |
| EC-002 | Redemption exceeds available points | `REJECT_REDEMPTION` |
| EC-003 | Returned order keeps all points | `FLAG_MISSING_POINTS_REVERSAL` |
| EC-004 | Points expire twice | `REJECT_DUPLICATE_EXPIRY` |
| EC-005 | Tier uses gross rather than qualifying spend | `CALCULATE_TIER_FROM_QUALIFYING_SPEND` |

### Edge-case outputs

- `exports/edge_case_scenarios.csv`
- `exports/edge_case_ground_truth.csv`
- `exports/edge_case_ground_truth.json`

These are deliberate test fixtures designed to verify specific business-rule failures. They are not claims that all five anomalies occurred naturally in the generated operational dataset.

---

## 12. Exporting the Dataset

Run:

```powershell
python scripts/export_dataset.py
```

The export process creates CSV and JSON representations of the relational tables, a SQL dump, and a source manifest.

The export directory is:

```text
exports/dataset/
```

### Export formats

| Format | Purpose |
|---|---|
| CSV | Tabular analysis and machine-learning workflows |
| JSON | Structured record interchange |
| SQL | Database reconstruction and inspection |
| JSON manifest | Dataset metadata and file checksums |

The large points transaction CSV is also available in compressed form:

```text
exports/dataset/points_transaction.csv.gz
```

The compressed file is suitable for storage and transfer when the uncompressed CSV is too large.

Some large uncompressed exports and the SQL dump are retained locally rather than published in GitHub because of repository size constraints.

---

## 13. Data Validation

The validation module checks structural and business-level consistency.

### 13.1 Database integrity

- SQLite database integrity.
- Foreign-key violations.
- Primary-key uniqueness.
- Valid entity relationships.

### 13.2 Transaction validation

- Transaction type validity.
- Redemption status consistency.
- Points allocation consistency.
- Reversal references.
- Over-reversal detection.
- Expiry batch consistency.
- Duplicate expiry prevention.
- Negative points-lot balance detection.

### 13.3 Order and return validation

- Order-line arithmetic.
- Returned quantity limits.
- Return-to-order references.
- Refund totals.
- Points reversal consistency.
- Qualifying-spend consistency.
- Excessive return detection.

### 13.4 Verified validation results

The generated Phase 4 database passed the following checks:

| Validation check | Result |
|---|---:|
| Foreign-key violations | 0 |
| Database integrity errors | 0 |
| Order-line arithmetic mismatches | 0 |
| Qualifying-spend mismatches | 0 |
| Invalid reversal references | 0 |
| Over-reversed accruals | 0 |
| Redemption allocation mismatches | 0 |
| Invalid allocations | 0 |
| Expiry batch mismatches | 0 |
| Negative lot balances | 0 |
| Duplicate expiry lots | 0 |
| Redemption status mismatches | 0 |
| Return quantity mismatches | 0 |
| Invalid return order references | 0 |
| Return reversal mismatches | 0 |
| Excessive return refunds | 0 |

These results apply to the verified generated database, not to every possible input or future database.

---

## 14. Automated Testing

The test suite covers the core loyalty engine operations.

The verified test suite contains 13 tests:

1. Accrual and balance calculation.
2. Reversal of accrued points.
3. Rejection of insufficient-balance redemption.
4. Approval of valid redemption.
5. FIFO points allocation.
6. Rejection of premature expiry.
7. Expiry of remaining lot balance.
8. Idempotent duplicate expiry.
9. Idempotent duplicate redemption.
10. Reversal rejection after redemption has consumed the points.
11. Proportional partial-return reversal.
12. Multiple partial returns and rounding.
13. Duplicate return prevention and excess-quantity rejection.

Run:

```powershell
python -m pytest -v
```

---

## 15. Reproducibility

The project uses a fixed random seed:

```text
20261022
```

Two fresh database generations were executed with the same configuration.

The following table counts matched across the two generated databases:

- Customer.
- Loyalty account.
- Orders.
- Order lines.
- Points transactions.
- Points allocations.
- Redemptions.
- Expiry batches.
- Account events.
- Return events.

The verified runs produced matching row counts.

**Reproducibility qualification:** The completed comparison verified row counts across the selected tables. A full row-by-row content checksum comparison between the two database files has not been completed. Export-file SHA-256 checksums are recorded in the source manifest where applicable.

---

## 16. Ground Truth and Anomaly Data

The project separates edge-case ground truth from the main operational dataset.

This separation helps prevent expected outcomes from being accidentally treated as ordinary input features.

### Ground-truth outputs

- `reports/anomaly_ground_truth.csv`
- `exports/edge_case_ground_truth.csv`
- `exports/edge_case_ground_truth.json`

The anomaly ground-truth file contains labels for the configured extreme order-value anomalies.

The edge-case ground-truth files contain expected outcomes for the five deliberate test fixtures.

Ground-truth labels should be used as evaluation targets, not as input features when training or evaluating an anomaly-detection model.

---

## 17. Data Dictionary

Refer to:

```text
DATA_DICTIONARY.md
```

The data dictionary describes the generated entities, fields, identifiers, relationships, and relevant data semantics.

It should be read together with the database schema and the source code.

---

## 18. Known Limitations and Assumptions

The following limitations are documented to distinguish implemented functionality from future enhancements.

1. **Concurrency testing:** The generator creates simulated competing redemption attempts sequentially at the same simulated timestamp. It does not currently perform a true simultaneous multi-threaded contention benchmark.

2. **Reproducibility verification:** Matching row counts were verified across two fresh generations. Full database content checksum equality has not been established.

3. **Edge-case fixtures:** The five required edge cases are deliberately constructed fixtures. They are not all naturally occurring anomalies from the operational dataset.

4. **Database deployment:** SQLite is used for this challenge implementation. A production deployment with multiple application instances and high transaction contention would require additional database and concurrency testing.

5. **Synthetic data:** Generated customer, order, and transaction records are synthetic and should not be interpreted as real customer activity.

6. **Operational scope:** The project focuses on the loyalty data engine and its validation. It is not a complete production loyalty platform with authentication, payment integration, or a customer-facing application.

---

## 19. Future Improvements

Potential extensions include:

- True concurrent redemption testing with multiple workers.
- PostgreSQL deployment and transaction isolation testing.
- REST API endpoints for customer, order, redemption, and account operations.
- Structured application logging and monitoring.
- Additional anomaly scenarios and evaluation metrics.
- Larger-scale performance benchmarking.
- Automated CI workflows.
- Database migration and versioning support.
- More extensive property-based and integration testing.

---

## 20. Repository

**GitHub:**  
https://github.com/MOHAMMED-FAIYAZ86900/yottaflex-loyalty-engine-starter

The repository contains the project implementation, tests, documentation, and selected dataset exports.

---


## 21. Quick Start

The following commands provide a clean installation and execution workflow using Windows PowerShell.

### Clone the repository

```powershell
git clone https://github.com/MOHAMMED-FAIYAZ86900/yottaflex-loyalty-engine-starter.git

cd yottaflex-loyalty-engine-starter
```

### Create and activate the virtual environment

```powershell
python -m venv .venv

.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

.\.venv\Scripts\Activate.ps1
```

### Install the project

```powershell
python -m pip install --upgrade pip

python -m pip install -e ".[dev]"
```

### Run automated tests

```powershell
python -m pytest -q
```

### Generate a fresh dataset

Use a new database filename to avoid overwriting an existing generated dataset:

```powershell
loyalty --db data/loyalty_fresh.db --customers 20000 --orders 100000 --seed 20261022
```

### Validate the generated dataset

```powershell
loyalty --db data/loyalty_fresh.db --validate-only
```

### Generate edge-case fixtures

```powershell
python scripts/generate_edge_cases.py
```

### Export the dataset

```powershell
python scripts/export_dataset.py
```

**Important:** Run all commands from the repository root with the virtual environment activated. Full dataset generation requires a fresh database because the generator does not permit generation against an already populated customer table.

## 22. Final Summary

The YottaFlex Loyalty Engine implements a deterministic synthetic loyalty dataset generator and a transaction-processing engine with explicit relational history.

It covers the primary loyalty lifecycle: customer accounts, orders, points accrual, redemption, returns, reversals, expiry, and tier progression.

The implementation includes automated tests, five required edge-case fixtures, validation checks, structured exports, and reproducibility checks.

The project is intended to demonstrate practical engineering ability in Python, relational data modeling, transaction processing, business-rule implementation, data quality, and synthetic dataset generation.

**Author:** Mohammed Faiyaz  
**Project:** YottaFlex Loyalty Engine — Round 2 Coding Challenge