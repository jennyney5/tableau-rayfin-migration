# Tableau to Rayfin migration

An accuracy-first skill for recreating Tableau reports as Rayfin apps backed by
Microsoft Fabric, with independent validation of data, calculations and behavior.

## Choose Your Workflow

This repository contains two separate skills sharing versioned inventory tooling:

| Goal | Skill | Cloud access |
|---|---|---|
| Assess TWBX readiness and explain blockers | [tableau-migration-evaluation](.github/skills/tableau-migration-evaluation/SKILL.md) | Not required for local evaluation |
| Recreate a workbook and validate the result | [tableau-rayfin-migration](.github/skills/tableau-rayfin-migration/SKILL.md) | Explicit source/target authorization required |

Evaluation does not initiate migration, create apps/models, or require migration
acceptance evidence. The current evaluation profile provides conservative,
provisional semi-automated recommendations; it is not a calibrated three-way
classifier or a guarantee of feasibility.

After installing the helpers below, evaluate a private TWBX or directory:

```powershell
.\.venv\Scripts\python.exe migration-evaluation/evaluator.py evaluate --input "C:\private-input\Sample Workbook.twbx" --output migration-evaluation/runs/sample-001
```

Or ask Copilot: "Use tableau-migration-evaluation to assess these TWBX files.
Do not migrate anything." See the [evaluation README](migration-evaluation/README.md)
for Public example downloads, output interpretation and customer ZIP packaging.
Generated runs are ignored by Git but can still contain sensitive source metadata.

## What is included

- The reusable [migration skill](.github/skills/tableau-rayfin-migration/SKILL.md)
  and four on-demand reference guides.
- A separate evaluation skill, local evaluator, schemas, capability profile,
  seven-family blocker guidance, Public candidate catalog and customer ZIP builder.
- Generic Python helpers for TWBX inventory, Hyper profiling, authenticated
  Tableau worksheet exports and typed CSV reconciliation.
- Synthetic, offline tests and placeholder-only configuration templates.

No source reports, customer data, credentials, deployed apps, cloud resource
identities, discrepancy ledgers or migration evidence are included.

The skill guides the entire workflow: source discovery, independent references,
Fabric ingestion and semantic modeling, Rayfin implementation, deployment and
layered acceptance. The helpers do **not** automatically compile Tableau formulas,
stage arbitrary reports into Fabric or generate/deploy complete apps.
Report-specific adapters and acceptance scenarios must be reviewed separately.

## Use the skill

Use an assistant that supports repository skills under `.github/skills`, or copy
the entire `tableau-rayfin-migration` skill directory, including `references`,
into your assistant's supported skill location.

Example request:

> Use tableau-rayfin-migration to recreate this Tableau workbook as a Rayfin app
> backed by Fabric. Establish independent references, preserve calculations and
> filter scope, and report discrepancies before accepting the migration.

Fabric/modeling skills and version-matched Rayfin build/deployment guidance are
external prerequisites, not bundled dependencies. The skill requires explicit
authorization before cloud writes or publication of source data.

## Install the optional helpers

Python 3.12 or later is required. Tableau Hyper API must support the selected
platform. The pinned Windows environment uses Python 3.12:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.windows.lock
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
```

For another supported platform, create an appropriate environment and install
the declared dependencies with `python -m pip install -e ".[dev]"`.
The Windows lock is not a cross-platform lock.

## Inventory and profile a workbook

```powershell
.\.venv\Scripts\tableau-migration.exe audit `
  --input "C:\private-input\Sample Workbook.twbx" `
  --output "C:\private-evidence\sample-audit-001"
```

Use a new evidence directory for each run. Audit completion is **not** numerical
certification. Inventories contain source definitions; even aggregate profiles
can be sensitive. Keep inputs and generated outputs outside this public repo.

## Capture independent Tableau references

Copy `migration\tableau-export.sample.json` into a private working directory.
Replace its placeholders with the approved hosted workbook identity, original
package path/hash, PAT name and explicit scenarios. Relative source paths resolve
from the configuration file's directory. Never put a PAT secret into the file.

In your own interactive Windows terminal:

```powershell
.\.venv\Scripts\python.exe -m tableau_migration.tableau_export configure `
  --config "C:\private-config\tableau-export.json"
.\.venv\Scripts\python.exe -m tableau_migration.tableau_export capture `
  --config "C:\private-config\tableau-export.json" `
  --output "C:\private-evidence\sample-tableau-001"
```

The setup prompt stores the PAT in Windows Credential Manager. For CI or other
supported platforms, inject `TABLEAU_TOKEN_NAME` and `TABLEAU_TOKEN_SECRET` through
a protected secret store; never echo or commit them.

Capture uses approved Tableau Cloud/Server access, not Tableau Public. It does
not upload, refresh or publish workbooks, expose hidden views, or change
permissions. Missing sheets/states remain explicit gaps. Read the
[export guide](.github/skills/tableau-rayfin-migration/references/TABLEAU_EXPORTS.md)
for API-version, effective-state, export-precision and empty-result limitations.

## Compare independently captured results

Copy `migration\compare-contract.example.json` into private evidence storage.
Replace every placeholder with the actual hashes, source identity, state,
full-grain keys and column rules for two separately captured exports.

```powershell
.\.venv\Scripts\tableau-migration.exe compare `
  --contract "C:\private-evidence\contract.json" `
  --output "C:\private-evidence\comparison.json"
```

Comparison returns 0 for agreement, 1 for differences and 2 for invalid input or
processing errors. It covers only the declared worksheet/scenario. Exact rows
or query results do not prove browser interactions, viewer access or complete
migration parity. See the
[validation contract](.github/skills/tableau-rayfin-migration/references/VALIDATION_CONTRACT.md).

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

Tests generate synthetic workbooks/extracts or mock Tableau REST responses;
they require no Tableau/Fabric account and perform no cloud writes. Hyper
profiling tests start the locally installed Hyper runtime.

## Publication boundaries

App-specific implementations, identifiers and debugging histories belong in each
app's private project/runbook, not in this reusable skill. Do not commit TWB/TWBX,
Hyper, raw CSVs, exports, evidence, credentials or private configuration. Ignore
rules are a guardrail, not a substitute for reviewing the exact staged files.
