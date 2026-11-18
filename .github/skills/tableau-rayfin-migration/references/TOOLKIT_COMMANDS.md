# Toolkit commands

These commands are optional accelerators, not prerequisites for the workflow.
Use them only when the accompanying toolkit is installed. Locate its root using
`pyproject.toml` (project `tableau-rayfin-migration`) and
`tools\tableau-migration`; inspect command help and manifests before execution.
If absent, use equivalent approved tools and preserve the same evidence contract.
Run from the toolkit root using its project environment.
These are Windows PowerShell examples. On another platform, first validate that
the dependencies and Hyper runtime support it, then use its path conventions.

## Setup

Restore only when needed; do not reinstall a working environment.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.windows.lock
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
```

## Generic inventory

```powershell
.\.venv\Scripts\tableau-migration.exe audit `
  --input ".\Sample Workbook.twbx" --output migration\output\sample-audit-001
```

`inventory` extracts definitions only; `profile` queries Hyper physical-table
statistics only. Directory discovery is top-level, not recursive.
Inspect `run-status.json`; audit completion means processing, not parity.
Protect outputs like source data, including formulas and aggregate statistics.

## Generic independent references

```powershell
.\.venv\Scripts\python.exe -m tableau_migration.tableau_export configure `
  --config migration\tableau-export.sample.json
.\.venv\Scripts\python.exe -m tableau_migration.tableau_export capture `
  --config migration\tableau-export.sample.json `
  --output migration\output\sample-tableau-api-001
```

The config must already exist and every capture output directory must be new.
The setup prompt is interactive, hidden, and belongs in the user's terminal.
Capture is read-only. Missing/inaccessible source worksheets are coverage gaps.

## Generic typed comparison

Copy `migration\compare-contract.example.json` and replace all placeholders.
Declare both file hashes, source hash, identical worksheet/state, every column's
exact header/type and full-grain keys. Inspect the example schema instead of
inventing column aliases, null tokens or tolerances.

```powershell
.\.venv\Scripts\tableau-migration.exe compare `
  --contract migration\baselines\sample\contract.json `
  --output migration\output\sample-comparison.json
```

Counts/keys are exact; only explicitly approved non-key decimal measures may use
nonzero tolerances. An API CSV is not assumed to have manual crosstab headers.
The compare command does not create target results; query the actual deployed
backend at the reviewed grain/state and preserve those results independently.

## Report-specific implementation boundary

Inventory, reference capture and typed comparison can be shared. Data staging,
calculation translation, model creation, app query generation and acceptance
scenarios still require reviewed bindings for the current report.

Keep those implementations and their commands in the report's project/runbook,
not this skill. Inspect any existing adapter before reuse; a similar report name
does not establish compatible grain, formulas, inputs or target resources.
Never copy another app's IDs, schemas, member values or expected totals.

For each implementation, preserve a manifest linking source identity, scenario,
actual query factory, full query text, target identity, complete result and
comparison contract. Execute the app's real factories through its actual
connector, rather than validating a separately rewritten query. Reject truncated
previews and preserve exact encoding, row counts, status and provenance.

No generic staging, model-deployment or end-to-end migration command is implied.
Discover or implement the required steps explicitly. Keep local preparation and
read-only comparison separate from authorized cloud writes.

## Tests and app commands

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

Each generated Rayfin app owns its commands. Inspect its package manifests and
capability guidance for typechecking, builds, lint, tests and visual validation;
do not assume script names or test discovery patterns. Run from that app root,
using the installed CLI's supported Node version, and do not race commands
sharing build outputs. Verify that the intended tests actually ran.
No generic Rayfin deploy syntax is prescribed here: read the installed package
docs and generated deployment skill for the actual app/version/target.
