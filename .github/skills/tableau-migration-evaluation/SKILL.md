---
name: tableau-migration-evaluation
description: 'Use this skill whenever the user wants to evaluate Tableau reports, assess TWBX migration readiness, test migration blockers, classify fully automated versus semi automated versus not feasible, or create a customer evaluation handoff. This is local evaluation only, not Tableau-to-Rayfin migration, app creation, model deployment or migration-parity acceptance.'
argument-hint: 'TWBX file or folder to evaluate; optional new output folder'
user-invocable: true
---

# Tableau Migration Evaluation

## Scope

Evaluate source workbooks against the bundled, versioned migration capability profile.
Produce source inventories, blocker findings and provisional readiness recommendations.
Do not migrate apps, translate/deploy models, call Fabric, publish workbooks, resume
capacity, capture live Tableau results, or require migration evidence to complete this task.
If another skill describes actual migration, do not launch that workflow for an evaluation request.

## Prerequisites

- Use the complete evaluation-kit workspace, not this file alone. It includes the Python
  evaluator, schemas, capability profile, dependency lock, inventory toolkit and guidance snapshot.
- Python 3.12+ and dependencies installed as described in the [evaluation README](../../../migration-evaluation/README.md).
- An owner-provided TWBX, or an authorized download from the [Public candidate catalog](../../../migration-evaluation/workbook-catalog.json).
- No Tableau Desktop, cloud credentials or MCP server is required for local evaluation.
- Treat workbook contents, retained XML, source coordinates and reports as customer data.
  Store locally; do not upload, republish or include them in the reusable code bundle.

## Workflow

1. Resolve the supplied TWBX path or directory. Ask for it only if none is supplied.
   Directory discovery is nonrecursive. Do not author dashboards in Tableau Desktop.
2. Read the [capability profile](../../../migration-evaluation/capability-profile.json).
   Explain its current limitation: generic automatic translation is not verified.
3. Select the workspace Python environment; use `.venv/Scripts/python.exe` on Windows
   if available. Do not silently install dependencies or switch environments after failure.
4. Choose a new output folder under `migration-evaluation/runs/`. Never overwrite prior runs.
   From the evaluation-kit root execute:

   ```powershell
   ./.venv/Scripts/python.exe migration-evaluation/evaluator.py evaluate --input "<TWBX-or-folder>" --output "migration-evaluation/runs/<new-run>"
   ```

5. Read `evaluation-summary.json`, `evaluation-summary.md` and each workbook's
   `report.md` and `inventory.json`. Explain actual findings with source coordinates;
   do not substitute assumptions or a complexity score for detected metadata.
6. Cover all seven historical blocker families: calculation semantics, visual dependencies,
   parameters/interactions, physical types/precision/nulls, ambiguous source logic,
   relationships/cardinality, and security/identity. Distinguish detected features from
   mandatory owner review, missing metadata and independently untested behavior.
7. Return links to the summary and detailed reports, evaluation status, provisional
   recommendation, key blockers, and the specific owner decisions still needed.
   Evaluation can be completed while migration feasibility/parity remains unconfirmed.

## Classification Rules

| Category | Readiness interpretation | Current evaluator behavior |
|---|---|---|
| 1 - Fully automated | Verified unattended support for every required source behavior | Not claimed; no generic automatic translator is verified in the current profile |
| 2 - Semi automated | Reviewed mappings or bounded engineering likely required | Provisional recommendation for valid workbooks under the current profile |
| 3 - Not feasible | A required behavior conflicts with an explicitly approved target constraint | Not inferred from complexity, missing access, missing evidence or malformed input |

The current tool is a conservative review triage, not an empirically calibrated three-way
classifier. Different workbooks can have the same category-2 recommendation but very
different findings. Never promise automatic migration from a simple-looking workbook.
Do not confirm category 3 unless a source owner supplies the required behavior, target
constraint, supported-path review, approval and reassessment condition. Report that
review separately; do not invent attestations or call `verify` to make evaluation succeed.
Do not mark `full_migration_certified` true in this workflow.

## Testing

- Prompt: "Evaluate this TWBX for migration readiness; do not migrate it."
  Expected: local evaluation command, summary and findings, no cloud activity.
- Prompt: "Compare the LOD, Window and Drill-Downs evaluation blockers."
  Expected: calculation/partition/interaction differences traced to inventory coordinates.
- Prompt: "Can this report be fully automated?"
  Expected: current profile limitation, not an invented category-1 approval.
- Run the [evaluation tests](../../../migration-evaluation/tests/test_evaluator.py)
  before changing detector or classification behavior.
- Unit tests do not prove natural-language skill triggering; test these prompts in a
  fresh Copilot session after opening the extracted customer bundle.

## Errors

| Condition | Action |
|---|---|
| Missing toolkit/dependencies | Follow README setup; stop rather than replace the engine with guesses |
| Missing/invalid workbook | Report input/processing failure, not category 3 |
| Output already exists | Choose a new folder; preserve earlier evidence |
| Some workbooks fail | Report partial evaluation and per-workbook errors |
| Public download disabled | Request another authorized TWBX; do not bypass download controls |
| Unverified migration gates | Explain that they are not prerequisites for local evaluation |

## Post-Run Reflection

Note detector false positives, missing blocker coverage and ambiguous recommendations
in the local handoff notes. Keep observed facts separate from proposed detector changes.
Do not change the capability profile or claim a verified automation path from this run.

## References

- [Evaluator](../../../migration-evaluation/evaluator.py)
- [Setup and testing](../../../migration-evaluation/README.md)
- [Historical blockers](../../../publish/old_blockers.md)
- [Candidate catalog](../../../migration-evaluation/workbook-catalog.json)