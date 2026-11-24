# Evaluation Method

## Purpose

Assess Tableau TWBX migration readiness without migrating an app or accessing a
cloud environment. Use the evaluation skill for this workflow; the migration
skill is a separate, explicitly authorized follow-on.

## Procedure

1. Obtain an owner-provided TWBX or an authorized Public download.
2. Run local evaluation with a frozen capability profile and new output folder.
3. Retain source/inventory/tool/guidance hashes and source-coordinate findings.
4. Review the seven historical blocker families and identify missing metadata.
5. Report a provisional recommendation and its limitations, not migration parity.
6. Keep source-bearing inputs and outputs private. Distribute first-party tooling only.

## Blocker Tests

| Family | Inspect | Required review beyond static inspection |
|---|---|---|
| Calculation semantics | LOD, aggregation and table-calculation formulas | Filter context and translated semantics |
| Visual dependencies | Worksheet grain, table-calculation metadata and sorts | Addressing, partitions, ties and totals |
| Parameters/interactions | Parameters, worksheet filters and actions | Effective state, scope, reset and navigation |
| Types | Source datatype metadata and optional local Hyper profiles | Nulls, duplicates, precision, dates and locale |
| Ambiguous logic | Inventory issues and captions/formulas | Source-owner business intent |
| Relationships | Logical/physical relationship and relation metadata | Keys, cardinality, filter direction and fan-out |
| Security | Identity-dependent formulas and declared requirements | Approved entitlements and private identity tests |

The Public catalog supplies LOD, Window Comparisons and Drill-Downs candidates.
Titles and detected features are not proof of edge-case or security coverage.
Tests needing intentional ambiguity, exact precision cases or entitlements
require owner-confirmed inputs; absence is an evidence gap, not infeasibility.

## Decision Boundaries

- Category 1 predicts supported agent-executed work with no required human migration
  steps or unknown capabilities. Agent coding/reasoning is not human intervention.
- Category 2 identifies a specific required human step. Native forecast metadata
  triggers the current manual forecast-output/model-details download path.
- Category 3 requires an explicit unsupported required behavior under an approved
  target constraint, alternatives reviewed, approver and reassessment condition.
- Unknown capability coverage remains undetermined, unless a known unsupported
  required behavior already establishes category 3. Missing access, missing
  evidence and malformed input do not establish infeasibility.
- A completed evaluation does not certify a migration or require migration trials.

## Reuse And Testing

Run the offline synthetic tests and a local assessment from the extracted ZIP.
Test natural-language skill prompts in a fresh compatible assistant session.
The owner-labeled calibration set expects seven category-1 workbooks and one
category-2 native-forecast workbook. These optional local inputs are not bundled;
set TABLEAU_BENCHMARK_DIR to run them. Feature-based synthetic tests cover category 3,
renaming, disabled forecasts and unknown functions. Calibration is not held-out
accuracy evidence. Broader claims need independent source/target evidence and
previously unseen cases; no migrations are required to run the evaluation tests.