# AI Prompt History and Usage Disclosure

**Project:** YottaFlex Loyalty Engine — Round 2 Coding Challenge  
**Candidate:** Mohammed Faiyaz  
**AI tool used:** ChatGPT  
**Document purpose:** Disclosure of AI assistance during project development.

---

## 1. AI Usage Disclosure

ChatGPT was used as an AI-assisted development and problem-solving tool during this challenge.

The assistance covered project planning, Python implementation, database design, loyalty business logic, synthetic dataset generation, validation, testing, edge-case construction, documentation, and submission preparation.

The candidate reviewed and executed the generated or modified code locally, investigated errors, ran tests, inspected validation output, and made implementation decisions.

AI assistance does not replace the candidate's responsibility for understanding, reviewing, and validating the submitted implementation.

**Important record-keeping note:** This document distinguishes an exact prompt recovered from the available conversation record from reconstructed descriptions of development work. Reconstructed descriptions are not represented as verbatim prompts.

## 2. Exact prompt recovered from the available conversation record

| Timestamp | AI tool | Exact prompt | Work area |
|---|---|---|---|
| 2026-11-01 | ChatGPT | Help me start the YottaFlex 72-hour loyalty ledger challenge from not started, using Python, targeting complete coverage; provide an execution plan and actual code. | Initial project planning and implementation |

This is the exact prompt currently recoverable from the retained project conversation record.

## 3. Additional AI-assisted development activities

The following entries summarize additional work performed with ChatGPT during development. They are reconstructed descriptions, not verbatim prompt transcripts.

| No. | Development area | Reconstructed description of the assistance requested | Files or components affected |
|---:|---|---|---|
| 1 | Database architecture | Assistance designing a relational loyalty database covering customer, account, tier, rule, order, order-line, reward, points transaction, redemption, allocation, expiry, return, and account-event entities. | `src/loyalty/db.py` |
| 2 | Loyalty business logic | Assistance implementing points accrual, balance calculation, redemption, insufficient-balance rejection, FIFO allocation, reversals, returns, and expiry. | `src/loyalty/engine.py` |
| 3 | Deterministic data generation | Assistance developing a reproducible generator for 20,000 customers and 100,000 orders using seed `20261022`, including transaction history and lifecycle events. | `src/loyalty/generator.py` |
| 4 | Return processing | Assistance implementing partial returns, proportional refunds, points reversals, returned quantities, order-status updates, and qualifying-spend recalculation. | `src/loyalty/engine.py`, `src/loyalty/generator.py` |
| 5 | Tier progression | Assistance implementing qualifying-spend-based tier calculations and recording tier changes, including downgrades following returns. | `src/loyalty/generator.py`, `account_event` |
| 6 | Data validation | Assistance developing integrity checks for primary keys, foreign keys, order arithmetic, qualifying spend, redemption allocations, reversals, expiry, and return consistency. | `src/loyalty/validate.py` |
| 7 | Automated testing | Assistance creating and debugging unit tests for accrual, redemption, FIFO allocation, expiry, reversals, partial returns, and idempotency. | `tests/test_engine.py` |
| 8 | Edge-case construction | Assistance creating the five required edge-case fixtures and their expected outcomes, separately from the operational dataset. | `scripts/generate_edge_cases.py`, `exports/edge_case_scenarios.csv`, `exports/edge_case_ground_truth.csv`, `exports/edge_case_ground_truth.json` |
| 9 | Ground-truth and anomaly labels | Assistance preparing anomaly labels and expected outcomes based on defined business rules. | `reports/anomaly_ground_truth.csv`, edge-case ground-truth exports |
| 10 | Dataset exports | Assistance implementing CSV, JSON, and SQL export generation and a source manifest. | `scripts/export_dataset.py`, `exports/dataset/` |
| 11 | Reproducibility | Assistance checking two fresh dataset generations using the same seed and comparing row counts. | Reproducibility verification databases and reports |
| 12 | GitHub publication | Assistance troubleshooting large Git objects, Git staging, ignored files, GitHub push failures, and repository synchronization. | `.gitignore`, Git repository |
| 13 | Project documentation | Assistance drafting setup instructions, project architecture, business logic documentation, validation details, and limitations. | `README.md` |
| 14 | Data dictionary | Assistance documenting the relational schema, fields, constraints, relationships, and lifecycle semantics. | `DATA_DICTIONARY.md` |
| 15 | Final repository review | Assistance reviewing public repository contents against the challenge requirements and identifying missing documentation and export deliverables. | Repository documentation and submission files |

## 4. Candidate review and validation

The following activities were performed during local development and verification:

- Reviewed and executed the Python implementation in a local virtual environment.
- Investigated implementation errors and modified code based on observed failures.
- Executed the automated test suite.
- Ran database integrity and business-rule validation.
- Inspected generated dataset counts and transaction distributions.
- Generated and inspected the five required edge-case fixtures.
- Compared row counts from two fresh generations using the same random seed.
- Exported the generated dataset into the supported formats.
- Published the project to a public GitHub repository.

The recorded test result for the completed engine test suite was 13 passing tests.

The generated Phase 4 dataset passed the reported database and business-rule validation checks.

## 5. Known implementation limitations

The following limitations are disclosed:

1. Competing redemption attempts in the generator are simulated sequentially at the same simulated timestamp. This is not a true simultaneous multi-threaded concurrency benchmark.
2. Reproducibility verification compared row counts across two fresh generations. A full database content checksum comparison was not completed.
3. The five required edge cases are deliberately constructed test fixtures and should not be interpreted as naturally occurring production anomalies.
4. The project uses SQLite and has not been benchmarked as a multi-instance production deployment.
5. Some large uncompressed exports and the SQL dump were retained locally rather than included in the public GitHub repository because of repository size constraints.

## 6. Prompt-history completeness statement

This document is a transparent AI usage disclosure based on the conversation information currently available.

Only the prompt listed in Section 2 is presented as an exact recovered prompt. The entries in Section 3 are summaries of the additional AI-assisted development activities and are explicitly not verbatim transcripts.

The document does not claim to contain every exact prompt submitted during the challenge. Any additional original prompts recovered from the candidate's chat history or other AI tools should be appended with their actual wording and timestamps.

No prompts have been invented or falsely represented as exact historical records.

---

**Candidate:** Mohammed Faiyaz  
**Project:** YottaFlex Loyalty Engine  
**AI assistance disclosure:** ChatGPT-assisted development with candidate review and local validation.