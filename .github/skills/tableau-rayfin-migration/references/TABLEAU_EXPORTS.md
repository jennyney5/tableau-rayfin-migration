# Tableau reference exports

## Supported route

Use the official Tableau Server Client SDK against a user-approved Tableau
Cloud/Server site. Tableau Public is not an authenticated REST-site substitute.
An active Cloud trial still needs API/export permissions and enabled PAT creation.
The exporter does not refresh, publish, unhide views or change permissions.

For a new local TWBX that has no approved hosted copy, obtain explicit permission
to upload the data to a selected private Cloud/Server project first. Resolve the
project and existing workbooks with the SDK before publishing an immutable
reference copy. Use the supported SDK publish workflow only with publishing
rights and the user's approval; never overwrite a baseline or expose data on
Tableau Public. Source upload is a separate write, not part of this exporter.

In the current Cloud UI, site admins enable PATs under **Settings > General >
Personal Access Tokens**, then save. Do not assume the Authentication tab owns
this switch. Users create their own PAT under **My Account Settings**.
Never change MFA or request a secret in chat. A site PAT is not a Cloud Manager PAT.

## Configuration and secure setup

Create a nonsecret JSON file using this schema, replacing every placeholder:

```json
{
  "schema_version": 1,
  "workbook_url": "https://example.online.tableau.com/#/site/contoso/views/SampleWorkbook/Dashboard",
  "source_package": "..\\Sample Workbook.twbx",
  "source_workbook_sha256": "<64 lowercase hex characters from the approved original>",
  "token_name": "sample-export",
  "scenarios": [
    {"id": "saved-default", "filters": {}, "parameters": {}}
  ]
}
```

Paths are relative to the config file, not the terminal's directory.
`worksheets` can explicitly select a nonempty subset of source worksheet names;
otherwise all source worksheets are required. Subset completion is not full
source coverage. Never put a PAT secret into this JSON.

Run `python -m tableau_migration.tableau_export configure --config <config>`
in the user's interactive terminal. The hidden prompt uses the Windows native
credential backend, scoped by server/site/token name. Non-Windows CI should inject
both `TABLEAU_TOKEN_NAME` and `TABLEAU_TOKEN_SECRET` through its protected secret
store; the name must match configuration. Do not print or persist those variables.

Then run `python -m tableau_migration.tableau_export capture --config <config>
--output <new-directory>` using the toolkit environment.
`capture-status.json` and raw CSVs are evidence, not source-control fixtures
unless specifically approved. Preserve each release/run separately.

## What completion means

The exporter resolves the exact published workbook content URL and paginates
view discovery. REST 3.30+ uses `GET /sites/{siteId}/views/{viewId}/allData` to
capture the named worksheet parts from every accessible dashboard/worksheet.
Older versions use Query View Data for individually exposed worksheets only.
It requests each declared scenario, preserves raw bytes, and records hashes,
rows, headers, IDs, revisions and coverage. It checks the source package hash
and workbook revision before/after.
Exit 0 = requested captures complete; 1 = missing sheets/export errors; 2 =
invalid input/auth/processing failure. Incomplete/partial output is not acceptance.

The local source hash does not prove that the published workbook/extract is the
same snapshot. Verify the published source or retain explicit operator attestation;
names, timestamps and a matching chart are insufficient. Freeze live sources or
capture consistent source versions; workbook revisions alone cannot detect
external data changes.

## Scenarios and limitations

- Empty filters/parameters objects mean saved defaults, not "all data."
- Each scenario requires a unique slug `id`, `filters` and `parameters`.
  Values are explicit strings. Optional `language` is a two-letter code.
  `allow_empty: true` must be intentional, not recovery from an unexpected blank.
  Verified allData empty shape: a named, successful `text/csv` part can contain
  only a newline and no headers. The exporter accepts that exact shape only
  after multipart status/MIME/length validation and explicit `allow_empty`,
  recording `headerless_empty: true` and unavailable schema. Do not infer a
  zero-valued business row, accept missing bodies, or generalize this exception
  to legacy first-sheet responses. Validate the selected member intersection
  independently; empty output alone does not prove correct filter propagation.
- CSV options use `vf` for view filters and `parameter` for workbook parameters.
  Empty filter strings are rejected: they can widen saved filters. Commas denote
  alternatives; literal commas and backslashes require Tableau-specific escaping.
- Requested parameter/filter values are not observed effective state. Prove they
  took effect using source outputs that discriminate the scenarios.
- Build per-worksheet scenarios consistent with source scope. Adding a filter
  through REST can impose a restriction that the original detail sheet did not
  receive from dashboard navigation. Do not mistake this for original behavior.
- Modern `allData` can export underlying sheets missing from the view list,
  without unhiding or republishing. Parse `X-Tableau-Sheet-Name`, status and
  error-code headers per multipart part; retain error parts as explicit failures.
  Fail on malformed/truncated responses or duplicate sheet names in one response.
  Preserve raw multipart bytes and the original Content-Type. Some servers emit
  unquoted `=` characters in the boundary; quote that boundary for MIME parsing
  without altering the recorded evidence.
- Include published story views in discovery where supported; enumerate actual
  worksheet coverage against the source inventory. Complete underlying-sheet
  coverage does not prove story-point state or navigation behavior.
  Stories can retain saved parameters despite successful alternate-state
  requests. Probe discriminating totals/titles; raw hash changes alone are not
  proof because mark order can vary.
  If the original publication cannot expose required states, report the gap.
  A separate private validation copy requires explicit approval, documented
  minimal changes, source equivalence checks and fresh state-discrimination
  checks; never overwrite the original or assume the copy resolves the gap.
  Use the optional exact `parent_views` list to select the intended export
  context. Missing/ambiguous parent names fail closed.
  When download is permitted, verify the Cloud/Server source independently:
  the downloaded TWBX's outer hash can differ because of server repackaging.
  Compare the embedded Hyper bytes, calculation definitions and worksheet
  filters against the approved local package, rather than equating a changed
  container hash with changed business data.
- Keep sheets exported under different parent dashboards distinct: their context
  can differ. `captured_count` is distinct required worksheet/scenario coverage;
  `exported_csv_count` counts actual files, including repeated dashboard contexts.
- Legacy dashboard CSV returns only one sheet and must never be treated as full
  coverage. If neither modern parts nor exposed worksheet views are available,
  report missing coverage and request approval before changing publication.
- CSV exports can differ from manual crosstabs in schema/grain and retain only
  formatted/rounded values. Inspect every measure's resolution. Do not claim
  unrounded precision from a displayed decimal merely because it has no suffix.
- Duplicate captions in valid API exports must be preserved, not silently
  renamed or dropped. Capture flags them `contract_mapping_required`; the strict
  comparator still requires a reviewed mapping to unique semantic columns.
- REST exports do not certify selection actions, navigation, drills, tooltips,
  context-filter order or session state. Use an approved interactive capture route
  for those; never scrape credentials/cookies or bypass denied access.
- Use sequential sessions per PAT and sign out. Concurrent sign-ins invalidate
  earlier sessions. Do not retry authentication/permission failures blindly.

## Official documentation

- [Personal access tokens](https://help.tableau.com/current/online/en-us/security_personal_access_tokens.htm)
- [Server Client API](https://tableau.github.io/server-client-python/docs/api-ref)
- [Tableau allData behavior](https://tableau.github.io/tableau-mcp/docs/tools/views/get-view-data)
- [Workbook/view exports](https://help.tableau.com/current/api/rest_api/en-us/REST/rest_api_ref_workbooks_and_views.htm)
- [View-filter syntax](https://help.tableau.com/current/api/rest_api/en-us/REST/rest_api_concepts_filtering_and_sorting.htm)
