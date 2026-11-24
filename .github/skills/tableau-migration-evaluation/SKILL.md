---
name: tableau-migration-evaluation
description: 'Use this skill to evaluate Tableau reports, scan Tableau Cloud site workbooks through APIs, assess TWBX migration readiness, test migration blockers, classify fully automated versus semi automated versus not feasible, or create a customer evaluation handoff. Read-only readiness evaluation, not migration, deployment or parity acceptance.'
argument-hint: 'Tableau Cloud site configuration or local TWBX file/folder; new output folder'
user-invocable: true
---

# Tableau Migration Evaluation

## Scope

Evaluate source workbooks against the bundled, versioned migration capability profile.
Produce source inventories, blocker findings and provisional readiness recommendations.
Cloud mode may authenticate, list workbooks and download definitions through Tableau APIs.
Do not migrate apps, translate/deploy models, call Fabric, publish workbooks, resume
capacity, capture live Tableau results, or require migration evidence to complete this task.
If another skill describes actual migration, do not launch that workflow for an evaluation request.

## Prerequisites

- Use the complete evaluation-kit workspace, not this file alone. It includes the Python
  evaluator, schemas, capability profile, dependency lock, inventory toolkit and guidance snapshot.
- Python 3.12+ and dependencies installed as described in the [evaluation README](../../../migration-evaluation/README.md).
- A Tableau Cloud site configuration with authorized read/download access, an
  owner-provided TWBX, or an authorized [Public download](../../../migration-evaluation/workbook-catalog.json).
- No Tableau Desktop, cloud credentials or MCP server is required for local evaluation.
- Treat workbook contents, retained XML, source coordinates and reports as customer data.
  Store locally; do not upload, republish or include them in the reusable code bundle.

## Workflow

### Tableau Cloud Sites

Use this route when the user requests API-based or site-wide evaluation. Do not
ask them to supply local workbook packages. The detailed route automatically
downloads definitions without requesting extracts; API metadata-only screening
is not implemented. The download route has passed an authorized live-site scan;
validate each customer's permissions and site-specific behavior separately.
Obtain approval for content transfer to customer-approved private storage. Successful
packages and reports are retained. Requesting no extracts does not guarantee no
embedded data; follow the customer's retention policy for the whole run directory.

1. Follow the [Cloud setup instructions](../../../migration-evaluation/README.md#tableau-cloud-detailed-site-evaluation).
  Obtain the server origin, site content URL slug and PAT name, never the secret.
  Store customer configuration/output outside the reusable kit. Ask the user to
  run `cloud.py configure` themselves for hidden secret entry, or use approved CI
  secret injection. Never collect a secret through chat or an ask-questions tool.
2. With authorized credentials available, run:

  ```powershell
  ./.venv/Scripts/python.exe migration-evaluation/cloud.py evaluate --config "<private-config.json>" --output "<new-private-output-folder>"
  ```

3. Read `cloud-summary.md`, `cloud-summary.json`, `cloud-inventory.json` and linked
  assessment reports. Discovery/processing failures are coverage gaps, not category 3.
  Report scope as workbooks visible to this identity in this site, not all tenant content.
4. Explain missing published-source definitions, skipped physical-data checks and
  untested runtime/security behavior. Recommendations remain predictions; do not
  claim migration certification or that API metadata-only evaluation occurred.

### Local Packages

1. Resolve the supplied TWBX path or directory. Ask for it only if none is supplied.
   Directory discovery is nonrecursive. Do not author dashboards in Tableau Desktop.
2. Read the [capability profile](../../../migration-evaluation/capability-profile.json).
  Explain the automation boundary: required human migration work, not agent reasoning
  or the presence of a generic one-click translator. State the profile assumptions.
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

| Category | Readiness interpretation | Decision basis |
|---|---|---|
| 1 - Fully automated | The agent can perform the migration work under stated prerequisites | All detected capabilities have automatic support rules; no required manual steps or unknowns |
| 2 - Semi automated | A specific human migration task is required | A manual capability rule names the source coordinate, reason and next action |
| 3 - Not feasible under current constraints | A required behavior has no supported path under an approved target constraint | An unsupported rule documents requirement, constraint, alternatives reviewed, approver and reassessment condition |

Unknown capability coverage yields an undetermined recommendation, never an invented
1, 2 or 3. A known unsupported required behavior takes precedence; otherwise unknowns
prevent a complete recommendation, even if a manual step is also known.
New or unfamiliar detected behavior without a reviewed capability rule belongs in
Undetermined, with a source coordinate and investigation step. Do not blanket-downgrade
known supported features or assume an undetected construct is automatically supported.
The detectors are not exhaustive; record newly encountered ambiguity for review.
Calculation counts, LODs, table calculations, custom chart code, filters and drill-downs
do not themselves imply human intervention. Routine permissions, consent and final
acceptance are prerequisites, not manual migration work. Missing access, missing
evidence and malformed packages are not proof of category 3.

Enabled native `forecast-specification` metadata triggers category 2 with the current
profile: the owner must download forecast output and model details. Do not silently
replace it with an independently fitted model. The detector must work after renaming
the workbook; never implement category lookups by filename or source hash.

The eight owner-labeled calibration cases are seven category 1 and one forecast case
category 2. Category-3 tests use explicit synthetic constraints, not a confirmed
infeasible real-world workbook. This is calibration, not held-out accuracy evidence.
Return `recommended_category` as a readiness prediction. The separate `category`
field remains null until optional migration acceptance. Never call `verify` merely
to complete evaluation or mark `full_migration_certified` true in this workflow.

## Testing

- Prompt: "Evaluate this TWBX for migration readiness; do not migrate it."
  Expected: local evaluation command, summary and findings, no cloud activity.
- Prompt: "Evaluate all accessible workbooks in this Tableau Cloud site."
  Expected: automatic definition downloads, no manual file intake; known supported
  features retain their predictions, unknown features remain Undetermined.
- Prompt: "Compare the LOD, Window and Drill-Downs evaluation blockers."
  Expected: calculation/partition/interaction differences traced to inventory coordinates.
- Prompt: "Can this report be fully automated?"
  Expected: feature-based recommendation, required human steps/unknowns and assumptions,
  not a downgrade for complexity or a promise of migration parity.
- Prompt: "Evaluate a forecast workbook under a target constraint."
  Expected: forecast/model download step; category 3 only for a documented approved
  unsupported required behavior, not merely because native forecasting is detected.
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