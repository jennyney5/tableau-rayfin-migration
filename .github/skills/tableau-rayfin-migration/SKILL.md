---
name: tableau-rayfin-migration
description: >-
  Recreate Tableau workbooks as Rayfin dashboards backed by Microsoft Fabric,
  preserving source data, calculations, worksheet filter scope and interactions.
  Use this skill whenever the user asks to migrate Tableau to Rayfin or Fabric,
  automate Tableau worksheet exports, validate Tableau-to-Power-BI parity, or
  repeat a TWBX migration, even if they do not name this skill. Not for unrelated
  Power BI report authoring or business questions over existing models.
---

# Accuracy-first Tableau to Rayfin migration

Orchestrate source extraction, independent Tableau reference capture, Fabric
data/model reconstruction, Rayfin dashboards and evidence-backed acceptance.
This is a reusable workflow, not an app runbook, a Tableau expression compiler
or a guarantee of unattended migration. Discover each report's schema and
behavior; never inherit another migration's IDs, formulas, filters or totals.

## Prerequisites

- Original TWBX packages, authorization to inspect them, and a selected target.
  Distinguish a Rayfin web app with semantic-model backend from native PBIR.
- Approved extraction, build and comparison tooling. If the accompanying toolkit
  is available, use its generic inventory/export/comparison commands; otherwise
  implement equivalent reviewed steps. Do not assume local helpers exist.
  Restore dependencies from the selected tools' manifests.
- Tableau Cloud/Server workbook URL and view/export access. PAT credentials
  belong in the Windows vault or CI secret store, never in chat or tracked files.
- For cloud writes, an explicitly approved Fabric tenant/workspace/capacity,
  resolved item identities and appropriate permissions. Existing approval for
  one migration does not authorize other workbooks, Test/Prod, spend or ACL changes.
- Load `fabric-cli` and `semantic-model-authoring` when using their services;
  load the app's generated Rayfin capability/deployment/validation guidance.
  Discover applicable MCP tools first. Use connected modeling MCP preferentially
  for model inspection/authoring; follow the model skill's deployment exception.

## Workflow

1. **Establish scope and provenance.** Reuse confirmed choices. Ask only for
   missing source URL/package, target type, approved write boundary and required
   acceptance scenarios. Hash immutable originals. Keep every run's evidence
   separate; never replace the independent source with reconstructed results.
2. **Inventory before translation.** Run the generic audit from
   [Toolkit commands](references/TOOLKIT_COMMANDS.md) when available, or equivalent
   extraction tools. Review formulas, source columns/types, parameters,
   worksheet overrides, context filters, relationships,
   actions and layouts. Flag unresolved dependencies and unsupported constructs.
   Do not infer missing measures by subtracting formula and target-measure counts.
3. **Capture Tableau's own outputs.** Follow
   [Tableau reference exports](references/TABLEAU_EXPORTS.md). Enumerate source
   worksheets and capture each required state using the Cloud/Server API.
   On REST 3.30+, use explicitly named `allData` multipart worksheet parts,
   including sheets not listed as standalone views. On older versions, use
   exposed individual worksheets. Record missing/error parts, unsupported
   actions and rounded exports as gaps. First-sheet dashboard CSV is not enough.
4. **Create a reviewed translation contract.** For every used calculation and
   worksheet, map source dependencies, grain, filtering, parameter/date behavior,
   LOD/table-calculation addressing, target expression and independent test.
   Use [Engineering workflow](references/ENGINEERING_WORKFLOW.md).
   Stop on ambiguity instead of fabricating equivalent behavior.
5. **Recreate and verify physical data.** Stage exact retained rows and support
   tables without unreviewed joins, exclusions or quantization. Compare source,
   stage, actual Fabric store and live model with duplicate multiplicity, types, nulls,
   dates and binary doubles retained. Choose the Fabric store from source and
   refresh requirements, not from a previous app. Physical row agreement is not
   measure parity.
6. **Build the semantic model.** Apply the owning model/Fabric skills, preserve
   source count/blank/date/filter semantics, then deploy once to the approved
   target using its documented path. Inspect existing identities before writes;
   never delete/recreate duplicates automatically. Validate deployed expressions
   and query actual measures, not just local formula copies.
7. **Build the Rayfin dashboard.** Read the generated capability router and
   installed version-matched docs. Apply required packs serially. Bind verified
   live query shapes; implement source worksheet-specific filter/action scope,
   navigation, tooltips, reference lines, labels, formatting and date semantics.
   Preserve protected assets, delegated authorization and visible failure states.
   No mock or stale values may masquerade as live business data.
8. **Validate before publication.** Use
   [Validation contract](references/VALIDATION_CONTRACT.md): physical data,
   native-source diagnostics, independent worksheet results, deployed measures,
   actual app query factories, and local UI/error-state checks where supported.
   Complete deployed browser and viewer acceptance in step 9.
   Test empty results, ties, date boundaries and changed parameter/filter states.
   Keep exact, display-resolution and approved-tolerance results separate.
9. **Deploy and exercise the real app.** Publish only to the approved Fabric
   item/environment using version-matched deployment guidance. Verify server
   deployment status, live data connectivity, authenticated browser behavior,
   filters/actions, rendering, responsiveness, reload and representative viewer
   access. Capture evidence against the exact deployed version; build success
   alone does not establish a working app.
10. **Publish an honest decision and handoff.** Deliver an evidence index,
   full difference ledger with causes and exact source coordinates, coverage/unsupported-state
   matrix, and release decision. A command completing is not parity. Block
   certification/promotion on missing required evidence, substantive differences
   or unresolved scope. Do not silently remediate/deploy during a comparison-only
   request; implement fixes only within the user's authorized scope.
   Include rerun inputs, source/target bindings, refresh dependencies and the
   commands or pipeline used. Separate routine refresh checks from source-schema,
   calculation or UI changes that require retranslation and renewed acceptance.
   See [Engineering workflow](references/ENGINEERING_WORKFLOW.md).

## Error handling

| Condition | Required response |
|---|---|
| PAT unavailable or creation disabled | Ask the user to enable PATs/create their own token, then run the hidden setup prompt. Never request the secret in chat. |
| Tableau 401/403 or restricted export | Stop; report authentication/permission blocker. Do not bypass it with browser cookies or another identity. |
| Hidden sheet or dashboard-only result | Try supported 3.30+ `allData` named worksheet parts. If unavailable, record coverage gaps and request approval for exposure/capture. No guessed view IDs or first-sheet substitution. |
| Header/grain/precision drift | Preserve raw output; review an explicit mapping/contract. Never round/drop/aggregate fields to force agreement. |
| Headerless empty allData part | Accept only the verified named/status/MIME/length envelope and explicit empty scenario. Record missing schema; never synthesize zero rows or accept an error body. |
| Wrong Fabric tenant or ambiguous identity | Resolve the intended target without silently changing shared global authentication. Ask if unresolved. |
| Package restore fails | Inspect project-scoped feed/version configuration and approved proxy; retain TLS and pinned versions. |
| CLI result is truncated | Read the verified full output file or request complete output. A successful preview is not a completed comparison. |
| Portal appears undeployed | Verify actual server deployment status and refresh stale portal state before recreating or republishing an item. Prove the hosted runtime separately. |
| Unsupported formula, Delta feature or state | Fail closed at that layer, record evidence and the exact missing capability. |
| User interrupts browser activity | Yield, preserve partial status, and leave unobserved checks unverified. |

## Output format

Report the outcome first, with links to reusable artifacts. Every numeric claim
must identify its source/state and evidence resolution.

| Layer | Result | Evidence | Unresolved scope |
|---|---|---|---|
| Physical rows | pass / fail / blocked | row/hash ledger | exact sources/columns |
| Worksheet calculations | pass / fail / partial | Tableau + target comparison | missing states/precision |
| Dashboard interactions | pass / fail / unverified | observed runtime evidence | actions/viewer coverage |

Set `full_migration_certified: false` until every approved acceptance gate passes.
Never describe a report-specific adapter as a reusable compiler.

## Representative requests

- "Recreate this TWBX in Rayfin using Fabric": execute steps 1-10, obtaining
  approval before cloud writes; deliver an app/model plus bounded acceptance.
- "Automate Tableau exports": execute steps 1-3 and export-specific checks only;
  report actual exported/expected worksheet-state counts and gaps.
- "Explain Tableau/Fabric differences": capture permitted read-only evidence,
  run steps 4/5/8/10 as applicable, and leave the deployed implementation unchanged.

## Post-Run Reflection

Apply the skill-author shared **core section 5: Post-Run Reflection / Continuous
Improvement** protocol when available. This standalone workspace skill does not
depend on that plugin being installed: check for missing scenarios, source routing,
calculation/null gotchas, export limitations, tool friction and misleading output.
Record only verified, reusable findings in this skill's references when authorized;
keep app-specific commands, schemas, member values, workarounds, credentials,
source data, account details and run status outside the skill, in the app's
runbook or protected run evidence. Generalize a verified lesson into a decision
rule rather than appending the incident narrative. Do not infer cross-repository
user preferences from one migration.

## References

Load only the reference needed for the current phase.

| Reference | When to load |
|---|---|
| [Toolkit commands](references/TOOLKIT_COMMANDS.md) | Optional generic inventory, export and comparison tools; adapter boundaries |
| [Tableau reference exports](references/TABLEAU_EXPORTS.md) | Authentication, API export and worksheet/state gaps |
| [Engineering workflow](references/ENGINEERING_WORKFLOW.md) | Data, model or Rayfin implementation |
| [Validation contract](references/VALIDATION_CONTRACT.md) | Coverage, comparisons, causes and release decisions |
