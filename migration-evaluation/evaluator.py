"""Read-only Tableau assessment and explicitly attested acceptance review."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zipfile import ZipFile

from defusedxml.ElementTree import fromstring
from jsonschema import validate

from tableau_migration.expressions import expression_tokens
from tableau_migration.inventory import inspect_workbook

VERSION = "0.3.0"
ROOT = Path(__file__).resolve().parent
BLOCKERS = {
    "calculation_semantics": "Calculation semantics",
    "visual_dependencies": "Visual dependencies",
    "parameters_interactions": "Parameters and interactions",
    "data_types": "Data types",
    "ambiguous_source_logic": "Ambiguous source logic",
    "relationships": "Relationships",
    "security": "Security",
}
GATES = ("provenance", "physical_data", "worksheet_calculations", "app_queries",
         "runtime", "security", "independent_review")
CATEGORIES = {1: "Fully automated", 2: "Semi automated", 3: "Not feasible", None: "Undetermined"}


def automation_decision(manifest: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    rules = profile["automation_rules"]
    supported = set(profile["supported_functions"])
    decisions: list[dict[str, Any]] = []

    def add(feature: str, coordinate: str, worksheets: list[str]) -> None:
        rule = rules.get(feature, {"status": "unknown", "reason": "No capability rule covers this feature.",
                                   "next_action": "Establish a supported automatic or manual path."})
        if rule.get("status") not in {"automatic", "manual", "unsupported", "unknown"}:
            raise ValueError(f"Invalid automation status for {feature}")
        if not rule.get("reason") or not rule.get("next_action"):
            raise ValueError(f"Capability rule requires reason and next_action: {feature}")
        if rule["status"] == "unsupported" and not all(
            isinstance(rule.get(key), str) and rule[key].strip()
            for key in ("requirement", "constraint", "supported_path_review", "reassessment_condition", "constraint_approved_by")
        ):
            raise ValueError("Unsupported rules require requirement, constraint, supported_path_review, reassessment_condition and constraint_approved_by")
        decisions.append({"feature": feature, "source_coordinate": coordinate,
                          "worksheets": worksheets, **rule})

    names = [sheet["name"] for sheet in manifest["worksheets"]]
    add("core_workbook", "workbook", names)
    for field in manifest["fields"]:
        if not field["required_by_worksheets"] or field.get("formula") is None:
            continue
        try:
            _, code = expression_tokens(field["formula"])
        except ValueError:
            add("unparsed_expression", field["id"], field["required_by_worksheets"])
            continue
        functions = set(re.findall(r"\b([A-Z_][A-Z_0-9]*)\s*\(", code.upper())) - {"IF", "ELSEIF", "THEN", "ELSE", "AND", "OR", "NOT"}
        external = {name for name in functions if name.startswith(("SCRIPT_", "MODEL_EXTENSION_"))}
        if external:
            add("external_analytics", field["id"], field["required_by_worksheets"])
        for name in sorted(functions - supported - external):
            add(f"function:{name}", field["id"], field["required_by_worksheets"])
    for marker in manifest.get("automation_metadata", []):
        add(marker["feature"], marker["source_coordinate"], marker["worksheets"])

    def category_for(items: list[dict[str, Any]]) -> int | None:
        statuses = {item["status"] for item in items}
        if "unsupported" in statuses:
            return 3
        if "unknown" in statuses:
            return None
        return 2 if "manual" in statuses else 1

    category = category_for(decisions)
    return {
        "recommended_category": category,
        "recommendation": CATEGORIES[category],
        "basis": "Feature-based prediction of required human intervention, not migration-parity certification.",
        "automation_assumptions": profile["assumptions"],
        "capability_decisions": decisions,
        "required_human_steps": [item for item in decisions if item["status"] == "manual"],
        "unsupported_requirements": [item for item in decisions if item["status"] == "unsupported"],
        "unknown_capabilities": [item for item in decisions if item["status"] == "unknown"],
        "worksheet_decisions": [{"worksheet": name, "category": None,
                                  "recommended_category": category_for([item for item in decisions if name in item["worksheets"]]),
                                  "status": "readiness_prediction"} for name in names],
    }


def automation_metadata(workbook: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    with ZipFile(workbook) as archive:
        root = fromstring(archive.read(manifest["source"]["twb_member"]))
    for element in root.iter():
        element.tag = element.tag.rsplit("}", 1)[-1]
    markers: list[dict[str, Any]] = []
    for sheet in root.findall("./worksheets/worksheet"):
        for index, element in enumerate(sheet.iter()):
            feature = None
            if element.tag == "forecast-specification" and element.get("enabled", "false").lower() == "true":
                feature = "native_forecast"
            elif element.tag in {"trend-line", "trend-lines", "cluster", "clustering"}:
                feature = "analytic_model"
            if feature:
                markers.append({"feature": feature, "source_coordinate": f"worksheet::{sheet.get('name')}::{element.tag}[{index}]",
                                "worksheets": [sheet.get("name")], "attributes": dict(element.attrib)})
    names = [sheet["name"] for sheet in manifest["worksheets"]]
    for index, element in enumerate(root.iter()):
        if element.tag in {"dashboard-extension", "extension", "extension-manifest"}:
            markers.append({"feature": "dashboard_extension", "source_coordinate": f"{element.tag}[{index}]",
                            "worksheets": names, "attributes": dict(element.attrib)})
    return markers


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def workflow_digest() -> str:
    folder = ROOT.parent / ".github" / "skills" / "tableau-rayfin-migration"
    files = sorted(folder.rglob("*.md"))
    if not files:
        raise ValueError("Migration skill snapshot is missing; use the complete handoff bundle")
    hashes = {path.relative_to(folder).as_posix(): digest(path) for path in files}
    return hashlib.sha256(json.dumps(hashes, sort_keys=True).encode("utf-8")).hexdigest()


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def save(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=True, allow_nan=False) + "\n", encoding="utf-8")


def new_run(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=False)
    save(path / "run-status.json", {"status": "incomplete", "tool_version": VERSION})


def findings_for(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []

    def add(blocker: str, coordinate: str, detected: str, remedy: str,
            worksheets: list[str] | None = None) -> None:
        findings.append({
            "id": f"F{len(findings) + 1:04d}", "blocker": blocker,
            "capability": "requires_review", "source_coordinate": coordinate,
            "worksheets": worksheets or [], "detected": detected,
            "owner": "Security owner" if blocker == "security" else "Migration / Tableau owner",
            "remedy": remedy, "closure_check": f"Accepted independent {BLOCKERS[blocker].lower()} evidence",
        })

    for field in manifest["fields"]:
        coordinate = field["id"]
        sheets = field["required_by_worksheets"]
        formula = field.get("formula")
        if formula is not None and field["datasource"] != "Parameters":
            add("calculation_semantics", coordinate,
                "Calculation definition requires a reviewed translation; reachability is conservative.",
                "Map dependencies, filter context, aggregation and independent worksheet states.", sheets)
            try:
                _, code = expression_tokens(formula)
            except ValueError:
                code = ""
            if set(field["features"]) & {"window", "running", "ranking", "lookup"} or re.search(
                r"\b(?:INDEX|FIRST|LAST|SIZE|TOTAL|PREVIOUS_VALUE)\s*\(", code, re.I
            ):
                add("visual_dependencies", coordinate, "Table calculation depends on visual context.",
                    "Record grain, sort, addressing, partitions, ties, totals and changed-state outputs.", sheets)
            if re.search(r"\b(?:USERNAME|FULLNAME|ISMEMBEROF|USERDOMAIN|USERATTRIBUTE\w*)\s*\(", code, re.I):
                add("security", coordinate, "Identity-dependent calculation detected.",
                    "Approve identity/RLS mappings and test allowed, forbidden and unmapped identities.", sheets)
            if "external_script" in field["features"]:
                add("calculation_semantics", coordinate, "External calculation service dependency detected.",
                    "Establish an approved equivalent and service access; otherwise document a constraint conflict.", sheets)
        if field["datasource"] == "Parameters":
            add("parameters_interactions", coordinate, "Parameter definition detected.",
                "Capture saved values, supported domains and actual dependent results for changed states.", sheets)
        if field.get("datatype") in {"real", "date", "datetime"}:
            add("data_types", coordinate, f"Source datatype: {field['datatype']}.",
                "Preserve physical values, nulls, locale/timezone and separately approve export precision.", sheets)

    for worksheet in manifest["worksheets"]:
        if worksheet["table_calculations"]:
            add("visual_dependencies", f"worksheet::{worksheet['name']}",
                "Worksheet table-calculation configuration detected.",
                "Review source addressing/sorting and compare full mark-grain outputs.", [worksheet["name"]])
        if worksheet["filters"]:
            add("parameters_interactions", f"worksheet::{worksheet['name']}", "Worksheet filters detected.",
                "Verify worksheet-specific scope, intersections, empty/multi-select and reset.", [worksheet["name"]])
    for index, action in enumerate(manifest["actions"]):
        add("parameters_interactions", f"action::{index}", f"Dashboard action: {action['type']}.",
            "Observe the source and deployed browser action; API-requested state is not action evidence.")
    for source in manifest["datasources"]:
        if source["is_parameter"]:
            continue
        if source["relation_xml"] or source["relationship_xml"] or source["object_graph_xml"]:
            add("relationships", f"datasource::{source['name']}", "Source relation/model metadata detected.",
                "Review keys, cardinality, physical versus logical joins, filter direction and duplicate multiplicity.")
    for issue in manifest["issues"]:
        add("ambiguous_source_logic", str(issue.get("field") or issue.get("worksheet") or issue["code"]),
            f"Inventory review finding: {issue['code']}.",
            "Resolve the exact inventory finding with the source owner; do not guess business intent.")
    add("ambiguous_source_logic", "workbook", "Captions and business intent cannot be certified from XML.",
        "Have the source owner review used formulas, captions and saved defaults.")
    add("data_types", "workbook", "Nulls, defaults and export precision require independent validation.",
        "Profile and compare typed duplicate-preserving rows and required measure precision.")
    add("security", "workbook", "Public visibility or absence of identity formulas does not establish target security.",
        "Approve the security requirement; test backend authorization or independently approve non-applicability.")
    return findings


def assess(workbook: Path, profile_path: Path, output: Path) -> dict[str, Any]:
    if workbook.suffix.lower() != ".twbx" or not workbook.is_file():
        raise ValueError("Input must be an existing TWBX file")
    profile = load(profile_path)
    if profile.get("target") != "rayfin-semantic-model" or profile.get("automation_boundary") != "required-human-intervention":
        raise ValueError("A Rayfin required-human-intervention capability profile is required")
    manifest = inspect_workbook(workbook)
    if not manifest["worksheets"]:
        raise ValueError("Workbook has no inventoried worksheets")
    manifest["automation_metadata"] = automation_metadata(workbook, manifest)
    automation = automation_decision(manifest, profile)
    new_run(output)
    save(output / "inventory.json", manifest)
    save(output / "profile.json", profile)
    findings = findings_for(manifest)
    result = {
        "schema_version": 1, "tool_version": VERSION,
        "assessment_id": output.name, "created_utc": datetime.now(timezone.utc).isoformat(),
        "tool_sha256": digest(Path(__file__)), "inventory_tool_version": manifest["tool_version"],
        "workflow_sha256": workflow_digest(),
        "source": manifest["source"], "profile_sha256": digest(profile_path),
        "inventory_sha256": digest(output / "inventory.json"), "target": profile["target"],
        "profile_version": profile["version"], "assessment_status": "needs_evidence",
        "category": None, "decision_stage": "provisional",
        "full_migration_certified": False,
        "explanation": automation["basis"],
        "counts": manifest["counts"], "findings": findings,
        **automation,
        "gates": {gate: "unverified" for gate in GATES},
        "limitations": manifest["limitations"] + [
            "No Tableau or Fabric connection, migration, source-result capture or deployment was performed.",
            "Detection is conservative; missing detections do not certify feature absence.",
        ],
    }
    validate(result, load(ROOT / "assessment.schema.json"))
    save(output / "assessment.json", result)
    (output / "report.md").write_text(render(result), encoding="utf-8")
    save(output / "run-status.json", {"status": "completed", "command": "assess", "accuracy_status": "unverified"})
    return result


def evaluate_portfolio(input_path: Path, profile_path: Path, output: Path) -> dict[str, Any]:
    packages = sorted(input_path.glob("*.twbx")) if input_path.is_dir() else [input_path]
    if not packages:
        raise ValueError("No TWBX files found; directory discovery is nonrecursive")
    new_run(output)
    results: list[dict[str, Any]] = []
    for index, package in enumerate(packages, start=1):
        relative = f"workbook-{index:03d}"
        try:
            assessment = assess(package, profile_path, output / relative)
            results.append({
                "workbook": package.name, "evaluation_status": "completed",
                "recommendation": assessment["recommendation"] + " (predicted)",
                "recommended_category": assessment["recommended_category"],
                "required_human_steps": assessment["required_human_steps"],
                "unsupported_requirements": assessment["unsupported_requirements"],
                "unknown_capabilities": assessment["unknown_capabilities"],
                "worksheets": assessment["counts"]["worksheets"],
                "findings": {key: sum(item["blocker"] == key for item in assessment["findings"])
                             for key in BLOCKERS},
                "report": f"{relative}/report.md", "full_migration_certified": False,
            })
        except Exception as error:
            results.append({"workbook": package.name, "evaluation_status": "failed", "error": str(error)})
        save(output / "evaluation-summary.json", {"workbooks": results, "evaluation_status": "incomplete"})
    status = "completed" if all(item["evaluation_status"] == "completed" for item in results) else "partial"
    result = {"evaluation_status": status, "mode": "evaluation-only", "workbooks": results,
              "migration_performed": False, "cloud_access_required": False,
              "full_migration_certified": False}
    save(output / "evaluation-summary.json", result)
    lines = ["# Tableau Evaluation Results", "",
             "Evaluation only: no apps/models were migrated, deployed or queried. No cloud access was used.", "",
             "These are readiness recommendations, not certification of migrated results.",
             "1 = supported agent-executed work; 2 = required manual step; 3 = explicit unsupported requirement/constraint conflict.",
             "Unknown capabilities remain undetermined. Review-finding counts do not set the category.", "",
             "| Workbook | Evaluation | Recommendation | Worksheets | Review findings | Report |",
             "|---|---|---|---:|---:|---|"]
    for item in results:
        name = item["workbook"].replace("|", "/")
        report = f"[Details]({item['report']})" if item.get("report") else "Processing failed"
        lines.append(f"| {name} | {item['evaluation_status']} | {item.get('recommendation', 'Undetermined')} | "
                     f"{item.get('worksheets', '-')} | {sum(item.get('findings', {}).values())} | {report} |")
        if item.get("error"):
            lines.extend(["", f"Processing error for {name}: {item['error']}", ""])
    lines.extend(["", "## Blocker Review Findings", "",
                  "Counts are review items, not confirmed defects or evidence that an absent feature is safe.", "",
                  "| Workbook | " + " | ".join(BLOCKERS.values()) + " |",
                  "|---|" + "---:|" * len(BLOCKERS)])
    for item in results:
        lines.append("| " + item["workbook"].replace("|", "/") + " | " + " | ".join(
            str(item.get("findings", {}).get(key, "-")) for key in BLOCKERS) + " |")
    lines.extend(["", "## Testing This Evaluation", "",
                  "Open each Details report and check its source coordinates and blocker explanations.",
                  "Compare LOD, Window and Drill-Downs findings, then evaluate another TWBX using a new output folder.",
                  "Unverified migration acceptance gates do not mean this local evaluation failed.",
                  "Do not run verify or migrate anything just to test evaluation.", ""])
    (output / "evaluation-summary.md").write_text("\n".join(lines), encoding="utf-8")
    save(output / "run-status.json", {"status": status, "command": "evaluate", "migration_performed": False})
    return result


def checked_artifacts(records: list[dict[str, Any]], base: Path) -> None:
    if not records:
        raise ValueError("Each declaration requires at least one evidence artifact")
    for record in records:
        relative = Path(record["file"])
        path = (base / relative).resolve()
        if relative.is_absolute() or not path.is_relative_to(base.resolve()):
            raise ValueError("Evidence paths must stay inside the evidence directory")
        if not path.is_file() or digest(path) != record["sha256"]:
            raise ValueError(f"Missing or changed evidence artifact: {relative}")


def verify(assessment_path: Path, evidence_path: Path, output: Path) -> dict[str, Any]:
    assessment = load(assessment_path)
    evidence = load(evidence_path)
    validate(assessment, load(ROOT / "assessment.schema.json"))
    validate(evidence, load(ROOT / "evidence.schema.json"))
    if assessment.get("tool_version") != VERSION or assessment.get("decision_stage") != "provisional":
        raise ValueError("Verify requires a provisional assessment from this tool version")
    if assessment.get("tool_sha256") != digest(Path(__file__)):
        raise ValueError("Evaluator changed since assessment; create a new assessment")
    if assessment.get("workflow_sha256") != workflow_digest():
        raise ValueError("Migration guidance changed since assessment; create a new assessment")
    if digest(assessment_path.parent / "inventory.json") != assessment["inventory_sha256"]:
        raise ValueError("Inventory changed since assessment")
    for name, expected in (("assessment_sha256", digest(assessment_path)),
                           ("source_sha256", assessment["source"]["sha256"]),
                           ("profile_sha256", assessment["profile_sha256"]),
                           ("workflow_sha256", assessment["workflow_sha256"])):
        if evidence.get(name) != expected:
            raise ValueError(f"Evidence binding mismatch: {name}")
    if not isinstance(evidence.get("reviewer"), str) or not evidence["reviewer"].strip():
        raise ValueError("An identified independent reviewer is required")
    base = evidence_path.parent
    if not isinstance(evidence.get("artifacts"), list):
        raise ValueError("Evidence artifacts must be a list")
    checked_artifacts(evidence["artifacts"], base)
    expected_sheets = {item["worksheet"] for item in assessment["worksheet_decisions"]}
    scenarios = evidence.get("scenarios", [])
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError("An approved worksheet/scenario manifest is required")
    keys = [(item["worksheet"], item["id"]) for item in scenarios]
    if len(set(keys)) != len(keys) or {key[0] for key in keys} != expected_sheets:
        raise ValueError("Scenario manifest must cover every inventoried worksheet with unique state IDs")
    for scenario in scenarios:
        if not isinstance(scenario["id"], str) or not scenario["id"].strip():
            raise ValueError("Scenario IDs must be nonempty strings")
        if scenario.get("status") not in {"passed", "failed", "unverified"}:
            raise ValueError("Invalid scenario status")
        checked_artifacts(scenario.get("artifacts", []), base)
    declarations = evidence.get("gates", {})
    if set(declarations) != set(GATES):
        raise ValueError("All required gate declarations must be supplied")
    for gate, declaration in declarations.items():
        if declaration.get("status") not in {"passed", "failed", "unverified"}:
            raise ValueError(f"Invalid gate status: {gate}")
        checked_artifacts(declaration.get("artifacts", []), base)
    interventions = evidence.get("interventions", [])
    if not isinstance(interventions, list):
        raise ValueError("Interventions must be a list")
    for item in interventions:
        if not item.get("task") or not item.get("owner") or type(item.get("active_minutes")) not in {int, float} or item["active_minutes"] < 0:
            raise ValueError("Each intervention requires a task, owner and nonnegative active minutes")
    resolutions = evidence["finding_resolutions"]
    if set(resolutions) != {item["id"] for item in assessment["findings"]}:
        raise ValueError("Finding resolutions must cover exactly the inventoried finding IDs")
    for resolution in resolutions.values():
        checked_artifacts(resolution["artifacts"], base)
    conflict = evidence.get("constraint_conflict")
    if conflict is not None:
        for key in ("requirement", "constraint", "attempted_supported_path", "reassessment_condition", "owner"):
            if not isinstance(conflict.get(key), str) or not conflict[key].strip():
                raise ValueError(f"Constraint conflict requires {key}")
        if conflict.get("owner_approved") is not True:
            raise ValueError("A category-3 constraint requires explicit owner approval")
        checked_artifacts(conflict.get("artifacts", []), base)
    passed = all(item["status"] == "passed" for item in scenarios) and all(
        declaration["status"] == "passed" for declaration in declarations.values()
    ) and evidence.get("scope_approved") is True and evidence.get("independent_review_completed") is True and all(
        resolution["status"] == "resolved" for resolution in resolutions.values()
    )
    observed_category = 2 if interventions else 1
    category = 3 if conflict else observed_category if passed else None
    result = dict(assessment)
    result.update({
        "category": category, "recommended_category": category if category else assessment["recommended_category"],
        "recommendation": CATEGORIES[category if category else assessment["recommended_category"]],
        "decision_stage": "confirmed" if category else "provisional",
        "assessment_status": "complete" if category else "needs_evidence",
        "full_migration_certified": passed and not bool(conflict),
        "gates": {gate: item["status"] for gate, item in declarations.items()},
        "evidence_sha256": digest(evidence_path), "reviewer": evidence["reviewer"],
        "target_identity": evidence["target_identity"], "precision_policy": evidence["precision_policy"],
        "finding_resolutions": resolutions,
        "evidence_origin": "operator-attested; artifact integrity checked, not semantic proof by this command",
        "scenario_counts": {"required": len(scenarios), "passed": sum(item["status"] == "passed" for item in scenarios)},
        "intervention_count": len(interventions),
        "active_minutes": sum(item["active_minutes"] for item in interventions),
        "constraint_conflict": conflict,
        "explanation": "Owner-approved requirement/constraint conflict." if conflict else
                       "Independent reviewer accepted required evidence for the reviewed migration workflow." if passed else
                       "Required evidence, scope approval or independent acceptance is incomplete.",
        "worksheet_decisions": [{"worksheet": name, "category": None if conflict else observed_category if passed else None,
                                 "status": "see workbook constraint" if conflict else "accepted" if passed else "needs_evidence"}
                                for name in sorted(expected_sheets)],
    })
    new_run(output)
    validate(result, load(ROOT / "assessment.schema.json"))
    save(output / "assessment.json", result)
    save(output / "evidence-declarations.json", evidence)
    (output / "report.md").write_text(render(result), encoding="utf-8")
    save(output / "run-status.json", {"status": "completed", "command": "verify"})
    return result


def prepare_evidence(assessment_path: Path, output: Path) -> None:
    assessment = load(assessment_path)
    validate(assessment, load(ROOT / "assessment.schema.json"))
    template = {
        "assessment_sha256": digest(assessment_path), "source_sha256": assessment["source"]["sha256"],
        "profile_sha256": assessment["profile_sha256"], "reviewer": "",
        "workflow_sha256": assessment["workflow_sha256"],
        "target_identity": {"tenant": "", "workspace": "", "model": "", "app": "", "deployment_version": ""},
        "precision_policy": "", "scope_approved": False, "independent_review_completed": False,
        "artifacts": [], "interventions": [], "constraint_conflict": None,
        "scenarios": [{"worksheet": item["worksheet"], "id": "saved-default", "status": "unverified",
                       "artifacts": []} for item in assessment["worksheet_decisions"]],
        "gates": {gate: {"status": "unverified", "artifacts": []} for gate in GATES},
        "finding_resolutions": {item["id"]: {"status": "unresolved", "details": "", "artifacts": []}
                                for item in assessment["findings"]},
    }
    with output.open("x", encoding="utf-8") as stream:
        json.dump(template, stream, indent=2, ensure_ascii=True, allow_nan=False)
        stream.write("\n")


def render(result: dict[str, Any]) -> str:
    lines = ["# Tableau Migration Assessment", "",
             f"Workbook: {result['source']['file']}",
             f"Category: {result['category'] or 'undetermined'} ({result['decision_stage']})",
             f"Recommendation: {CATEGORIES[result['recommended_category']]} (category {result['recommended_category'] or 'undetermined'})",
             f"Status: {result['assessment_status']}",
             f"Full migration certified: {str(result['full_migration_certified']).lower()}",
             "", result["explanation"], "",
             f"Source SHA256: {result['source']['sha256']}",
             f"Tool / profile: {result['tool_version']} / {result['profile_version']}",
             "", "## Automation Decision", ""]
    for decision in result.get("capability_decisions", []):
        lines.extend([f"- {decision['status']}: {decision['feature']} at {decision['source_coordinate']}",
                      f"  Reason: {decision['reason']}", f"  Next action: {decision['next_action']}"])
        if decision["status"] == "unsupported":
            lines.extend(f"  {key}: {decision[key]}" for key in (
                "requirement", "constraint", "supported_path_review", "reassessment_condition", "constraint_approved_by"))
    lines.extend(["", "### Assumptions", "", *[f"- {item}" for item in result.get("automation_assumptions", [])]])
    lines.extend(["", "## Acceptance Gates", ""])
    lines.extend(f"- {gate}: {status}" for gate, status in result["gates"].items())
    lines.extend(["", "## Findings", ""])
    for finding in result["findings"]:
        lines.extend([f"### {finding['id']} - {BLOCKERS[finding['blocker']]}",
                      f"Source coordinate: {finding['source_coordinate']}",
                      finding["detected"], f"Owner: {finding['owner']}",
                      f"Next action: {finding['remedy']}", f"Close with: {finding['closure_check']}", ""])
    lines.extend(["## Limitations", "", *[f"- {item}" for item in result["limitations"]], ""])
    if result.get("evidence_origin"):
        lines.extend([result["evidence_origin"], ""])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    evaluation = commands.add_parser("evaluate", help="Local evaluation only; no cloud or migration acceptance required")
    evaluation.add_argument("--input", type=Path, required=True, help="TWBX file or directory (nonrecursive)")
    evaluation.add_argument("--profile", type=Path, default=ROOT / "capability-profile.json")
    evaluation.add_argument("--output", type=Path, required=True)
    intake = commands.add_parser("assess")
    intake.add_argument("--workbook", type=Path, required=True)
    intake.add_argument("--profile", type=Path, default=ROOT / "capability-profile.json")
    intake.add_argument("--output", type=Path, required=True)
    acceptance = commands.add_parser("verify")
    acceptance.add_argument("--assessment", type=Path, required=True)
    acceptance.add_argument("--evidence", type=Path, required=True)
    acceptance.add_argument("--output", type=Path, required=True)
    template = commands.add_parser("prepare-evidence")
    template.add_argument("--assessment", type=Path, required=True)
    template.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "evaluate":
            result = evaluate_portfolio(args.input, args.profile, args.output)
            print(f"Local evaluation {result['evaluation_status']}: {len(result['workbooks'])} workbook(s); no migration performed")
            print(args.output / "evaluation-summary.md")
            return 0 if result["evaluation_status"] == "completed" else 1
        if args.command == "prepare-evidence":
            prepare_evidence(args.assessment, args.output)
            print(f"Created unapproved evidence template: {args.output}")
            return 0
        result = assess(args.workbook, args.profile, args.output) if args.command == "assess" else verify(
            args.assessment, args.evidence, args.output)
        print(f"{result['assessment_status']}: category={result['category']}, recommendation={result['recommended_category']}")
        print(args.output / "report.md")
        return 0 if result["assessment_status"] == "complete" else 1
    except Exception as error:
        print(f"Assessment failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())