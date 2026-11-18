# Engineering workflow

## Source contract

Inventory each TWBX independently before selecting or writing an adapter.
Preserve embedded Hyper tables and TWB XML on temporary copies. Record source types, relationships,
unmatched keys, duplicate multiplicity and excluded members. A package can contain
multiple tables whose physical totals cannot safely be joined or added together.
Never assume a business identifier is unique or that a date exclusion is a cutoff.
Check for visualization scaffolding before defining the fact grain: repeated
layers can multiply every count. Where present, apply the source sheet's layer filter, then
preserve legitimate repeated business identifiers within that layer. Neither
counting every physical layer nor blindly deduplicating identifiers is safe.

For every used formula record:

| Field | Required information |
|---|---|
| Identity | Datasource, internal name, caption and worksheet override |
| Inputs | Dependencies, source types, null/zero handling, relationships |
| Grain | Source row/mark grouping, aggregation and totals behavior |
| Filters | Extract, datasource, context, worksheet and action order/scope |
| Parameters | Allowed values, saved default, effect and nondefault tests |
| Table calculation | Partition/addressing, sort, ties, restart and densification |
| Target | Owning table/measure/query/UI component and exact implementation |
| Evidence | Independent worksheet scenarios, precision and expected differences |

Calculation-definition counts do not equal required target measures: unused
groups, helpers, duplicate expressions and presentation fields need classification.
Unresolved dependencies or unsupported logic block the affected acceptance gate.

## Fabric physical data

Use the owning Fabric skills to choose Lakehouse, Warehouse or another approved
store based on the source, workload, refresh and model requirements.
Load source facts and deliberately generated support tables separately.
Retain source binary doubles unless an approved contract intentionally changes
them; never convert currency to fixed decimal just to remove numerical residuals.
Preserve dates/time zones, nulls, strings/leading zeros and source exclusions.
Prove relationships do not fan out facts. Record source/stage/remote row signatures.
Verify supported conversions for source-specific types such as geography.
Document any portable representation and compare representative values;
storage fidelity does not establish rendering parity. Never silently drop
unsupported fields.

Implement source ingestion and transformations with a reviewed adapter or Fabric
notebook/pipeline. Separate local preparation from actual remote loading and
verify the remote contents. Do not assume a staging command uploads data.

## Semantic-model translation

Read `semantic-model-authoring` and applicable modeling/DAX/Direct Lake guidance
before authoring. Prefer modeling MCP for supported inspection/authoring; disk
PBIP/TMDL deployment follows that skill's REST deployment rule. Discover IDs from
the selected tenant/workspace and inspect existing items before writes.
Never delete models to resolve naming collisions without explicit approval.

Critical equivalence checks:

- `COUNT`, `COUNTD`, row counts and DAX `COUNTA` are not interchangeable.
  Source conditional counts can yield zero where DAX on no rows yields BLANK.
  Do not blanket-coalesce charts whose explicit zero suppression is intentional.
- FIXED/INCLUDE/EXCLUDE must respect Tableau's filter order, not generic
  `ALL`/`ALLEXCEPT` substitutions.
- WINDOW calculations and INDEX depend on marks, nonempty dates, partition,
  addressing, sorting and restarts. Calendar-week grouping is not a safe proxy.
- An unweighted average of daily totals is not an average of fact rows.
- Prior-period cards may be prior-year-to-date while trends show an entire prior
  period. Differences may be ratios for one metric and absolute amounts for another.
- Source maximum dates can differ before/after exclusions and context filters.
  Keep the global snapshot label separate from a filtered calculation anchor.
- Verify rank ties, maxima labels, shares of total, totals and blank future marks,
  not just the largest KPI cards.

Capture deployed expressions and execute all used measures. A smoke query that
does not error proves executability, not correctness.
For Direct Lake, resolve actual storage locations and schema support before
binding partitions. Diagnose resource paths, schema and permissions separately;
an ambiguous table/access error is not proof of an authentication failure.

## Rayfin implementation

Read the generated app's capability router, app design, analytics, query-design,
visual-interactivity, app-validation and app-deployment guidance on demand.
No existing single Rayfin pack owns this end-to-end migration orchestration.
Use installed version-matched package docs, not remembered CLI flags.

For a semantic-model app, apply connectors, analytics and visuals packs serially
when needed; do not reapply already installed packs or overwrite preserved seeds.
Restore compatible pinned dependencies with project-scoped approved feeds or
proxies and a supported runtime. Verify actual restoration, not just scaffolder
exit status. Stop on unavailable packages; obtain approval for a compatible
release change rather than silently mixing package versions. Preserve project
configuration and locks; never change global registries or disable TLS.
Diagnose secure credential-store dependencies without enabling plaintext
fallback or changing shared global authentication.

Connector CLI output can be a preview despite a successful status. Inspect
truncation metadata and retrieve the complete result using the installed
version's documented output contract. Validate any recorded file path before
reading it. Reject previews at acceptance boundaries.
Read JSON/CSV explicitly as UTF-8 on Windows; the locale default can corrupt
international member names or fail partway through validation.

Keep business calculations in the reviewed backend/query layer. Query actual
factories with intersecting filters before using their result shapes. Match
worksheet-specific filter targets: overview navigation does not imply global
detail filtering. Implement source reference lines, max/rank labels, shares,
tooltips, number formats, sort order and navigation explicitly.
Geographic exports can flatten the endpoints of multiple line geometries into
separate rows. Compare source mark/line grain and endpoint structure before
declaring row-count differences. Keep exact source-double agreement separate
from generated-geography coordinate differences and from pixel-size/typography
acceptance; do not silently apply a tolerance or infer an internal projection.
Inspect visualization-library capabilities as well as the raw Vega-Lite spec.
Automatic scrolling, minimum-mark sizing, synthetic labels and baseline
transforms can change presentation despite correct query data. Use supported
capability settings and explicit container sizing where required, surface render
errors, and confirm the complete source domain in the deployed browser.
Spec compilation alone does not exercise visualization-library transformations.
Bind palette domains and filter option values to exact source members, not
invented descriptive shorthand. Keep display captions separate from query
member keys. Query parity alone does not establish correct presentation binding.

For positioned pie charts, explicitly partition and normalize slice angles by
the source dimensions. Do not assume implicit stacking partitions by the
intended mark grain. Verify the compiled grouping/angle domain as well as
the actual browser marks. Keep decorative background bands distinct from
business marks.
Inspect source size encodings, including fixed domain, minimum/maximum size and
clamping, before translating bubbles or animations. Automatic scaling can alter
meaning across filter/parameter states. Capture independent source renders for
discriminating states. Preserve source size values in live queries; implement
the display transfer function separately and retain any pixel calibration as
a presentation limitation, not calculation
parity. Match label colors/placement without inventing label values.

Check the configured test-discovery glob and observed test-file counts.
A zero-test exit code does not establish coverage.

A Fabric item can display stale Getting started/blank Live URL state even when
the server records an active deployment. Verify read-only server status and
refresh portal state before republishing or creating another item. Exercise
the actual hosted runtime separately. Embedded sign-in does not prove standalone
sign-in, session restoration or viewer permissions.
Discover each subcommand's supported output contract rather than assuming
root-level flags apply. Preserve machine-readable output with explicit encoding.
Consume the app's existing theme/auth contexts; do not introduce a second
controller whose state the root does not observe.

Preserve protected assets, authentication gates, delegated model permissions and
disabled password auth. Surface errors and stale identity explicitly. A missing
connector cannot be replaced with mock or previously cached success-shaped data.

## Deployment and reuse

Run the app's existing typecheck, build, lint, focused/full tests and applicable
visual validators serially where they share build outputs. Record partial
validator support honestly. Deploy to the resolved existing item only within the
approved scope, following installed CLI docs, then exercise the authenticated
external-browser route and real viewer permissions.

## Repeatable operation

Keep the reusable workflow separate from each report's implementation and run
evidence. Record the following in a nonsecret report manifest or runbook:

| Binding | Required information |
|---|---|
| Source | Package/version hashes, hosted identity, snapshot and refresh policy |
| Translation | Reviewed mappings, transformations and unsupported behavior |
| Target | Approved environment, resolved store/model/app identities |
| Scenarios | Required worksheet, parameter, filter and interaction coverage |
| Execution | Versioned dependencies, adapters, commands and pipeline order |
| Acceptance | Comparison contracts, evidence locations and release gates |

Parameterize source and target bindings; keep secrets in approved stores.
Inspect existing resources before writes and reuse only verified identities.
Make reruns detect collisions/drift rather than overwrite baselines or create
duplicate cloud items. Preserve distinct source, build, deployment and acceptance
run identifiers.

For scheduled operation, orchestrate ingestion, transformations, data checks,
model refresh and post-refresh query checks in dependency order. A refresh
failure or mismatch must stop downstream acceptance and surface an explicit
failure. Schema, calculation, dependency or interaction changes require impact
review and renewed affected-layer validation; a routine data refresh need not
redeploy unchanged application code. Promote only after the agreed gates pass.

Put app-specific commands, schemas, source members, expected counts, layout
coordinates and debugging history in that app's runbook/evidence, not this skill.
Reuse tooling only after verifying its input/output and authorization contracts.
