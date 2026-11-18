# Validation contract and acceptance

## Independent layers

| Layer | Required comparison | What it does not prove |
|---|---|---|
| Source inventory | Source definitions, dependencies and grain reviewed | Formula equivalence |
| Physical data | Source -> stage -> actual store -> live model, typed duplicate-preserving bags | Aggregated calculations |
| Native-source diagnostics | Hyper SQL aggregates using reviewed source semantics vs target | Tableau/VizQL workbook evaluation |
| Worksheet outputs | Tableau-generated references vs actual deployed results at identical state/grain | Other worksheets/states or interactions |
| App queries | Actual query factories/connectors vs expected model results | Browser filter propagation/rendering |
| Runtime | Authenticated controls, labels, navigation, loading/errors, viewer and reload | Unobserved devices/states |

Use immutable hashes, source coordinates, exact query text, target item IDs,
timestamps and completion status at every layer. Comparing two copies of the
same translated formula is not independent validation.

## Scenario matrix

Enumerate each used worksheet/metric across:

- Saved defaults and all supported parameter values.
- Each filter, relevant intersections and source-specific filter scope.
- Navigation/filter actions, drill up/down, reset and back navigation.
- Empty results, null vs zero, missing prior periods and chart suppression.
- Date boundaries, partial periods, source anchors and prior-period rules.
- LOD context, nonempty daily marks, window partitions, INDEX restarts and ties.
- Totals/subtotals, maximum labels, shares, tooltips and display formatting.

Capture overview and detail scopes independently. If Tableau navigation does not
forward a filter, the source-equivalent detail case must remain unfiltered.
Verify changed-state outputs actually differ when the selected scenario should
change them; storing a requested parameter is not evidence that Tableau used it.

## Numeric comparisons

Preserve duplicate multiplicity, types, dates, source double bits, null/blank and
zero distinctions at the physical layer. Never compare facts as a deduplicated
set. Generated support tables need generated expected values, not fictitious
claims that they physically existed in Tableau.

At the measure layer, use explicit full-grain keys and declared column types.
Counts, quantities and keys are exact. Parse decimals as Decimal. Empty strings
are not implicit nulls. Reject duplicate/null keys, unexpected empty results,
nonfinite values, schema drift and mismatched state/hash metadata.
Treat a verified, explicitly allowed headerless-empty Tableau worksheet part as
evidence of zero returned marks, not evidence of its absent column schema.
Compare it only to an independently justified empty scenario; retain the
headerless indicator and exact source bytes. Include a positive multi-select
probe so filter serialization cannot silently turn valid alternatives into an
empty intersection.

Report separately:

1. Exact numeric/semantic differences.
2. Agreement only at the source's exported/display resolution.
3. Differences within an explicitly approved measure-specific tolerance.
4. Missing/unsupported/unverified evidence.

Never approve tolerance implicitly because values agree at cents or four
decimals. For final-digit residuals, trace contributing source records, compare
source and target stored bits, execute native-source sums and inspect export
resolution. Native Hyper SQL agreement narrows causes but does not reveal
Tableau's pre-export binary values or prove a particular VizQL aggregation plan.

## Difference ledger

Every discrepancy needs workbook hash, worksheet, scenario, measure, full-grain
key, source file and 1-based row/column where applicable, expected and actual
values, signed delta, applicable precision/tolerance, and contributing-record
references. Classify the cause and confidence:

- Changed/missing/duplicated source records or incorrect relationships.
- Exclusions, date/parameter anchors or filter scope/order.
- Aggregation/count/blank/LOD/window/rank semantics.
- Serialization/export-resolution or cross-engine aggregation residual.
- Presentation omission/formatting or unobserved runtime behavior.
- Unresolved; identify the discriminating evidence still required.

An unproven cause must be labelled a hypothesis. Produce complete CSV/JSON
ledgers rather than only examples or summary counts.

## Release status

Maintain distinct capture, comparison and release statuses. Export/audit/report
generation success is not parity. Persist incomplete status before work and leave
failed/interrupted evidence unusable for acceptance.

Do not set `full_migration_certified: true` or promote to another environment
unless every required scenario/measure/runtime gate has independent accepted
evidence, source identity is established, and the owner has accepted intentional
differences and approved promotion. A partial viewer/browser check stays partial.
Authentication failures never authorize disabling protection or bypassing ACLs.
Keep static visual coverage separate from runtime coverage. If a validator
cannot resolve a computed spec, record that gap. Use a documented preview route
only where supported and authorized for browser checks; it is not a schema pass.
Record the actual deployment checked, visible full category domains, all
runtime-built charts exercised, settled loading, render diagnostics, and any
unobserved console/viewer/session paths.
Exercise repeated transitions at the full source mark count. Correct counts and
one successful screenshot do not prove responsiveness. Record browser stalls,
recovery and memory indicators without attributing them to the application or
automation until isolated. Do not silently sample/drop marks to pass runtime
acceptance, and do not close unrelated tabs or terminate shared browser processes.

Inspect each validator's documented status and coverage, not just its exit code.
A successful report-generation command may still contain differences or require
review. The optional toolkit compare command returns 0 for pass, 1 for
differences and 2 for invalid/processing errors.
