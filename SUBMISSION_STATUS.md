\# YottaFlex Loyalty Engine — Submission Status



\## Dataset

\- Random seed: 20261022

\- Customers: 20,000

\- Loyalty accounts: 20,000

\- Orders: 100,000

\- Order lines: 249,665

\- Points transactions: 317,156

\- Points allocations: 120,208

\- Redemptions: 118,713

\- Expiry batches: 93,431

\- Account tier events: 31,291



\## Implemented

\- Relational loyalty data model

\- Deterministic synthetic data generation

\- Points accrual and ledger

\- FIFO redemption allocation

\- Points expiry

\- Accrual reversal

\- Partial returns in the engine

\- Idempotency for redemption, expiry and return requests

\- Database integrity and reconciliation validation

\- CSV, JSON and SQL export

\- Source manifest and SHA-256 checksums



\## Test results

\- 13 automated engine tests passed.

\- Full-scale database validation passed.

\- Foreign-key violations: 0.

\- Database integrity: OK.



\## Known limitations

\- Partial returns are covered by unit tests but are not yet populated

&#x20; in the generated full-scale dataset.

\- The current anomaly ground truth covers extreme order-value labels.

\- The five requested edge-case scenarios are not all implemented

&#x20; as separate, validated ground-truth cases.

\- Concurrent redemption behaviour requires additional stress testing.

\- Reproducibility checksums have been generated for exported tables;

&#x20; a second independent regeneration comparison is still required.



\## Reproduction

```powershell

python -m loyalty.cli --db data/rebuild.db --customers 20000 --orders 100000 --seed 20261022

python scripts/export\_dataset.py

python -m pytest -v


## 4. Final GitHub submission

First inspect what will be committed:

```powershell
git status --short
git check-ignore data/loyalty.db data/loyalty_rebuild.db