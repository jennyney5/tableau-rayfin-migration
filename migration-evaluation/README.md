# Tableau Migration Evaluation Kit

Customer-operated, read-only assessment of Tableau TWBX files for the current
Tableau-to-Rayfin skill. No Tableau Desktop authoring is required for intake,
Public download, XML inventory, or local Hyper profiling.

## Evaluation Only

This is the default customer workflow. No apps or models need to be migrated.
No Tableau Desktop, Tableau credentials, Fabric workspace, deployment, or
migration-acceptance evidence is required to evaluate a local TWBX.

The reusable [tableau-migration-evaluation skill](../.github/skills/tableau-migration-evaluation/SKILL.md)
is included in the customer ZIP. Open the extracted bundle root in VS Code
and ask Copilot: "Evaluate the TWBX files in this folder for migration
readiness. Use tableau-migration-evaluation; do not migrate anything."
The skill also supports `/tableau-migration-evaluation` in compatible clients.
The full bundle is required; the skill file alone is not the evaluator.

After installing dependencies below, run on a file or a directory:

```powershell
.\.venv\Scripts\python.exe migration-evaluation/evaluator.py evaluate --input "Customer Workbook.twbx" --output migration-evaluation/runs/customer-evaluation-001
```

Directory discovery is nonrecursive. Outputs include `evaluation-summary.md`,
`evaluation-summary.json`, and linked inventories/detailed reports per workbook.
Exit 0 means local evaluation completed, not that migration was certified.
Exit 1 means partial processing; exit 2 means invalid input/command failure.
Every output directory must be new.

An evaluation can be complete even though per-workbook migration acceptance
remains `needs_evidence`. Do not run `prepare-evidence` or `verify` just to
test evaluation. Those commands address a separate, optional migration lifecycle.

The current profile is conservative: valid workbooks receive a provisional
category-2 recommendation with different blocker findings. It is not yet a
calibrated three-way classifier. It does not certify category 1 or infer
category 3 from complexity, missing access, or missing evidence.

## Start Here

Run commands from the repository or extracted handoff bundle root, not this
subfolder. Python 3.12+ and the generic toolkit dependencies are required. An
existing repository environment can be reused; a new customer environment uses:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.windows.lock
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
```

The lock file reflects the original Windows environment. Validate other
platforms/Python versions separately; keep approved TLS and package feeds.

Download and assess the three confirmed Public examples:

```powershell
.\.venv\Scripts\python.exe migration-evaluation/suite.py --public-only --download-public --profile --output migration-evaluation/runs/public-001
.\.venv\Scripts\python.exe migration-evaluation/evaluator.py evaluate --input migration-evaluation/runs/public-001/workbooks --output migration-evaluation/runs/public-evaluation-001
```

The public catalog contains three attributed Public candidates. Without
`--download-public`, place an authorized local copy at the catalog's private
input path, or supply your own catalog with `--catalog`. Missing local inputs
are recorded as failed acquisitions, not migrated workbooks. Every output
directory must be new; originals are never modified.

Assess a customer workbook locally:

```powershell
.\.venv\Scripts\python.exe migration-evaluation/evaluator.py assess --workbook "Customer Workbook.twbx" --output migration-evaluation/runs/customer-001
```

Exit codes for `assess` and `verify`: 0 = complete decision; 1 = needs evidence;
2 = invalid input/processing failure. For `suite`: 0 = local suite completed;
1 = partial acquisition/processing; 2 = invalid/processing failure. No exit code
from local assessment proves migration parity. Read `run-status.json` before
consuming output.

## What It Produces

- `evaluation-summary.md` and `evaluation-summary.json` with `evaluate`: completed/partial local evaluation, provisional recommendations and a seven-family blocker matrix with report links.
- `assessment.json` and `report.md`: provisional recommendation, worksheet list, seven blocker families, source coordinates, owners, remedies, closure checks and acceptance gates.
- `inventory.json`: retained Tableau definitions and dependencies, not an expression compiler.
- `scenario-plan.json` in suite runs: unapproved worksheet-state draft. Define actual values and add parameter/action/security/precision cases before capture.
- `physical-profile.json` with `--profile`: embedded Hyper statistics, not joined business totals.
- `catalog-results.json` and `coverage.md`: acquisition provenance, hashes, detected candidate coverage and remaining test gaps.

Reports contain formulas and source metadata. Protect them like source data.
Never place PATs, passwords or tokens in this folder.

No source-bearing benchmark reports are included in this public repository.
Run the commands above to generate your own local coverage and evaluation
reports. Detection is candidate coverage, not accepted migration equivalence.

## Category Rules

1. **Fully automated:** unavailable as a certified capability in this MVP. The current skill requires report-specific reviewed bindings and has no generic unattended translator. Future support requires a versioned capability change backed by held-out migration and clean-rerun evidence.
2. **Semi automated:** the current provisional recommendation; confirmed only after independent acceptance of required data, calculation, query, interaction/runtime and security evidence, and resolution of findings.
3. **Not migratable under current constraints:** requires a documented required behavior, attempted supported path, owner-approved blocking constraint and reassessment condition.

Missing evidence leaves `category: null`, status `needs_evidence`, and
`full_migration_certified: false`. A category-2 recommendation is not a promise
that all unknown features are feasible. A successful build/export/inventory is
not certification.

## Optional Migration Acceptance

This section is outside the evaluation-only workflow. Skip it when testing
readiness or handing off the evaluation skill.

Create an intentionally incomplete evidence declaration:

```powershell
.\.venv\Scripts\python.exe migration-evaluation/evaluator.py prepare-evidence --assessment migration-evaluation/runs/customer-001/assessment.json --output migration-evaluation/runs/customer-001/evidence.json
```

The template will fail validation until an authorized operator supplies real
evidence. Expand scenarios beyond the saved default. The independent reviewer
must approve the required worksheet/state/identity scope; record exact source
revision/snapshot and target IDs/deployment in the provenance artifact.

Perform the skill's migration and validation in an explicitly approved sandbox.
Capture independent Tableau worksheet results at matching grain/state, typed
physical rows including duplicates, actual deployed measures and app factories,
and observed authenticated browser/security behavior. Existing generic export
and comparison tooling is included in the handoff; their configurations and
comparison contracts remain workbook-specific.

The included PAT exporter targets Tableau Cloud/Server, **not Tableau Public**.
For Public, capture source crosstabs and effective action states in the browser,
or use an authorized, immutable private published copy for supported REST
automation. Do not assume the Public download endpoint provides the Cloud/Server
`allData` or PAT API. Publishing a copy requires rights and environment approval.

Each evidence reference is `{"file":"relative/path","sha256":"64 lowercase hex characters"}`.
Files must exist beneath the evidence declaration's directory. Obtain hashes
with `Get-FileHash -Algorithm SHA256` and lowercase the returned hash. Retain raw
results, complete comparisons/difference ledgers, identities, source/target
bindings, state metadata, precision/tolerance approvals, and reviewer acceptance.
Record workbook-specific human tasks and active minutes; do not invent results.

Every gate and scenario needs an artifact reference, even when its status is
unverified. An artifact can document an evidence gap; it does not make that gate
pass. Every finding needs a resolution declaration. Non-applicability must be
independently justified in its resolution artifact. No silent scope omissions.

```powershell
.\.venv\Scripts\python.exe migration-evaluation/evaluator.py verify --assessment migration-evaluation/runs/customer-001/assessment.json --evidence migration-evaluation/runs/customer-001/evidence.json --output migration-evaluation/runs/customer-reviewed-001
```

**`verify` checks schema, bindings, artifact integrity and declared acceptance. It
does not execute Tableau, Fabric or browser validation or independently prove
the contents of reviewer-supplied artifacts.** Any certified flag is explicitly
an operator-attested acceptance decision. Tool/guidance changes require a fresh
assessment. Treat source-schema/calculation/security/interaction changes as new
assessment scope, not routine refresh.

## Public Sources Without Desktop

[Tableau Public's FAQ](https://help.tableau.com/current/public/desktop/en-us/public_faq.htm)
confirms both browser authoring and author-controlled TWBX downloads. Use
Download > Tableau Workbook > Current. Search can be filtered to downloadable
or copyable vizzes. The kit downloads only explicitly cataloged public endpoints,
with HTTPS host restrictions, a 50 MB limit and bounded ZIP/XML validation; it
does not bypass disabled downloads or scrape authenticated sessions.

Confirmed sources:

- [LOD: FIXED, INCLUDE, EXCLUDE, by Ruben Martinez](https://public.tableau.com/views/MasteringTableau8_LOD1-FIXEDINCLUDEEXCLUDEexamples/Dashboard).
- [Window Comparisons, by Ruben Martinez](https://public.tableau.com/views/MasteringTableau17_Tablecalculations2-Windowcomparisons/Dashboard).
- [Drill-Downs, by Alfred Chan](https://public.tableau.com/views/AllDifferentTypesofDrill-DownsinTableau/Dashboard).

Downloading is not blanket permission to redistribute, republish, or commercially
reuse the author's work or underlying data. Review rights and retain attribution
before customer distribution or private republishing. The handoff ZIP excludes
third-party workbook data and generated source-bearing reports by default.

Public files cannot establish restricted multi-identity security equivalence.
Use an existing authorized private security workbook and test identities; browser
authoring in a private Tableau environment is an alternative when a fixture is
needed. Intentional ambiguity and precision edge cases also remain gaps until
confirmed or added in a permitted browser-authored copy. No Desktop requirement
is imposed, and no such copy has been published by this kit.

## Customer Handoff and Tests

```powershell
.\.venv\Scripts\python.exe -m pytest migration-evaluation/tests -q -p no:cacheprovider
.\.venv\Scripts\python.exe migration-evaluation/package.py --output migration-evaluation/dist/tableau-evaluation-skill-kit.zip
```

The ZIP includes first-party evaluator code, schemas, catalog, generic toolkit,
dependency manifests, the evaluation skill, migration guidance snapshot, original plan/blockers, and
these operator instructions. Extract it into a new folder, use the setup above,
and run the Public-only benchmark or a customer-provided TWBX. It excludes app
projects, credentials, run data and third-party workbooks. Its hash manifest
records the bundled files.

Onboarding acceptance: the customer runs `evaluate`, opens the summary and
traces a blocker to its source coordinates. No cloud connection or migration
is required. Test the skill prompts in a fresh Copilot session to check client
discovery. Confirmed migration cases are a separate scope requiring authorized
trials and independent evidence, not an evaluation prerequisite.