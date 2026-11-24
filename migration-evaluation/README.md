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

The versioned profile classifies required human intervention, not complexity.
Agent reasoning, report-specific coding and validation do not downgrade a report.
Recommendations are feature-based predictions, not guarantees of migration parity.
Unknown capabilities remain undetermined rather than being forced into a category.

## Start Here

### Tableau Cloud: Detailed Site Evaluation

The Cloud route lists accessible site workbooks through the REST API, downloads
definitions with `include_extract=False`, and runs the existing detailed classifier
locally. No manual TWBX intake or Tableau Desktop is needed. Metadata-only screening
is not implemented. The download-based route has passed an authorized live-site
scan and offline mocked tests. Validate permissions and behavior on each customer site.

Use [cloud-config.example.json](cloud-config.example.json) to create a private config
outside this repository, for example `C:\TableauPrivate\cloud-config.json`. Supply
the HTTPS server origin, site content URL slug (not display name), and PAT name.
Never put the secret in JSON, chat, source control or command-line arguments.
The identity must be authorized to list/download the intended workbooks.

Run `configure` yourself in an interactive Windows terminal for hidden secret entry
and storage in Windows Credential Manager, then evaluate:

```powershell
.\.venv\Scripts\python.exe migration-evaluation/cloud.py configure --config C:\TableauPrivate\cloud-config.json
.\.venv\Scripts\python.exe migration-evaluation/cloud.py evaluate --config C:\TableauPrivate\cloud-config.json --output C:\TableauPrivate\runs\cloud-001
```

For CI, inject both `TABLEAU_TOKEN_NAME` and `TABLEAU_TOKEN_SECRET` through a secret
manager. The name must match configuration. Secrets and raw server error messages
are not printed; failed workbook records contain stage and exception type.
Exit 0 means evaluation completed, 1 means partial discovery/processing, and 2 means
setup/authentication/command failure. Every output directory must be new.

Outputs include `cloud-inventory.json`, `cloud-summary.json`, `cloud-summary.md`,
downloaded definitions and per-workbook detailed reports. Plain TWB responses are
packaged locally. Downloads are limited to 50 MiB each; ZIP safety checks also apply.
Temporary downloads are removed after individual failures.
Successful packages and assessment artifacts are retained, not automatically deleted.
`include_extract=False` is a request to omit extracts, not a guarantee that returned
packages contain no embedded data or sensitive content. Obtain approval for content
transfer and use customer-approved storage before running the scan. After review,
retain or delete the entire private run directory according to customer policy.

- Scope is one site and content visible to the authenticated identity. Inaccessible
	workbooks cannot be counted. Repeat for other sites or with authorized broader access.
- All pages are discovered before assessment. Inconsistent totals/duplicate IDs fail
	discovery. This is not an atomic snapshot; definitions can change after discovery.
- Download/processing failures remain unclassified, not category 3; other workbooks
	continue after individual failures.
- Published data-source definitions may not be embedded and are not downloaded
	separately. Review missing-source coverage before relying on readiness predictions.
- No extracts are requested, and no physical profiling, live results, runtime,
	effective-security or numerical-parity validation is performed.
- Definitions, assets and reports are sensitive customer material. Use approved
	private storage/access controls and retention; never add output to the public kit.

Known detected capabilities retain their profile-based category. A detected feature
without a reviewed rule remains Undetermined with its source coordinate and next
action. Detectors are not an exhaustive Tableau schema or a generic translator:
review novel workbook behavior and missing dependencies rather than assuming that
an absent finding proves support. These are readiness predictions, not guarantees.

Customer acceptance checklist:

1. Confirm the site, authorized identity, download permission and private retention policy.
2. Confirm discovery completed and compare the visible workbook count with Tableau.
3. Inspect any failed downloads/assessments and every Undetermined result; never
   reinterpret an access failure as category 3 or silently omit it from the handoff.
4. Review linked per-workbook reasons, source coordinates, manual tasks and limitations.
5. Keep customer configs, credentials and run artifacts out of any code/skill handoff.

### Local Setup

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

1. **Fully automated:** detected behavior has supported agent-executed paths, with no required manual migration steps or unknown capabilities. Agent-specific implementation, LOD/table calculations, relationships, custom visuals and interaction complexity do not themselves downgrade the report.
2. **Semi automated:** a specific human migration task is necessary. Enabled native Tableau forecasting currently requires a manual download of forecast output, intervals and model details; automatic ingestion follows that step.
3. **Not migratable under current constraints:** a required behavior has no supported path under an explicitly approved constraint. The profile rule must document the requirement, constraint, alternatives reviewed, approver and reassessment condition. Complexity, missing access and malformed input are not category 3.

`recommended_category` is 1, 2, 3 or null (undetermined). An unsupported required
behavior takes precedence; otherwise unknown capability coverage prevents a complete
recommendation, even if a manual step is already known. Reports include capability
decisions, source coordinates, required human steps, unknowns and assumptions.
The seven blocker families remain diagnostics and validation tasks, not score thresholds.

Routine consent, credentials and final acceptance are prerequisites, not manual
migration work. Embedded data or authorized source access and target permissions
are assumed; this local command does not test live access. Nonstandard functions,
external analytics, extensions and uncovered analytical models require capability
review rather than an automatic success claim. Static detection is not exhaustive.

Modify a copy of the capability profile and pass `--profile <file>` to either
`evaluate` or `assess`. Rules use `automatic`, `manual`, `unsupported` or `unknown`.
Every rule needs `reason` and `next_action`. An `unsupported` rule additionally
requires `requirement`, `constraint`, `supported_path_review`,
`constraint_approved_by` and `reassessment_condition`. Do not invent approvals.
For example, required live external analytics may be category 3 if approved target
policy prohibits that service and local rewriting/materialization cannot satisfy
the live-service requirement. Without that constraint review it stays undetermined.

Calibration matches eight owner-labeled reports: seven fully automated and the
native-forecast case semi automated. The classifier uses source metadata, not report
names or hashes. Category-3 coverage is synthetic constraint testing; no held-out
real-world category-3 accuracy or universal migration success is established.

Evaluation leaves `category: null`, status `needs_evidence`, and
`full_migration_certified: false` because migration acceptance is separate.
A completed evaluation and a successful build/export/inventory are not certification.
Optional `verify` distinguishes observed zero-intervention acceptance (1), accepted
human-assisted work (2), and owner-approved conflicts (3); its evidence remains attested.

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

To include the eight original owner-labeled calibration workbooks, set
`$env:TABLEAU_BENCHMARK_DIR` to the directory containing authorized local copies
before running pytest. Without it those eight tests skip; synthetic three-way,
renaming, disabled-forecast, unknown-function and comment/string tests still run.
Workbook inputs and generated reports are never included in the reusable bundle.

Onboarding acceptance: the customer runs `evaluate`, opens the summary and
traces a blocker to its source coordinates. No cloud connection or migration
is required. Test the skill prompts in a fresh Copilot session to check client
discovery. Confirmed migration cases are a separate scope requiring authorized
trials and independent evidence, not an evaluation prerequisite.