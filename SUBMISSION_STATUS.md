# YottaFlex Loyalty Engine — Final Submission Status

**Project:** YottaFlex Loyalty Engine  
**Dataset seed:** 20261022  
**Database:** SQLite  
**Schema:** 13 relational tables

## Final dataset

| Entity | Records |
|---|---:|
| Customers | 20,000 |
| Loyalty accounts | 20,000 |
| Tiers | 4 |
| Rules | 1 |
| Orders | 100,000 |
| Order lines | 250,319 |
| Points transactions | 317,987 |
| Points allocations | 120,265 |
| Rewards | 3 |
| Redemptions | 138,522 |
| Expiry batches | 97,486 |
| Account events | 31,484 |
| Return events | 2,079 |

## Implemented functionality

- Relational data model with primary keys, foreign keys and entity relationships.
- Deterministic synthetic dataset generation using a fixed seed.
- Loyalty points accrual and transaction ledger.
- FIFO points allocation and redemption.
- Rejected redemption handling for insufficient balances.
- Points expiry and duplicate-expiry protection.
- Full and partial return processing with proportional points reversal.
- Idempotency for redemption, expiry and return requests.
- Qualifying spend recalculation and tier progression.
- Explicit account and return history records.
- CSV, JSON and compressed SQL exports.
- Source manifest with SHA-256 hashes and export metadata.
- Separate ground-truth and edge-case outputs.

## Required edge cases

Five required scenarios are represented by deliberately constructed fixtures:

1. Account balance differs from ledger-derived balance.
2. Redemption exceeds available points.
3. Returned order retains all earned points.
4. Points are expired more than once.
5. Tier progression incorrectly uses gross rather than qualifying spend.

These are controlled test fixtures, not claims that every anomaly naturally occurs in the generated operational dataset.

## Validation and tests

- Automated engine tests: 13 passed in the last verified run.
- Full-scale database validation: passed in the last verified run.
- Foreign-key violations: 0.
- Database integrity: OK.
- Order-line amount mismatches: 0.
- Qualifying-spend mismatches: 0.
- Invalid reversal references: 0.
- Over-reversed accruals: 0.
- Redemption allocation mismatches: 0.
- Invalid allocation transactions: 0.
- Expiry batch mismatches: 0.
- Negative lot balances: 0.
- Duplicate expiry lots: 0.
- Redemption status mismatches: 0.
- Return quantity mismatches: 0.
- Return reversal mismatches: 0.

See `reports/validation.json` for the detailed validation report.

## Reproducibility

The generator uses seed `20261022`. Matching row counts were verified across two fresh generations for the selected tables. A complete row-by-row content checksum comparison between independent database generations has not been completed.

## Concurrency qualification

Redemption attempts are processed sequentially in the generated simulation. The engine uses SQLite transaction handling, but a fully parallel, multi-process concurrency stress test has not been established.

## Export publication

- CSV and JSON dataset exports are published where tracked in the repository.
- Compressed SQL export: `exports/dataset/loyalty_dataset.sql.gz`.
- Canonical export manifest: `exports/dataset/source_manifest.json`.
- Large uncompressed files may remain local-only.

## Known limitations

- The edge-case scenarios are deliberately injected fixtures.
- Full database content reproducibility has not been established.
- The simulated competing redemption requests are not a substitute for a true concurrent stress test.
- SQLite is used for this challenge; production deployment would require further database and concurrency testing.

## Test command

```powershell
python -m pytest -v