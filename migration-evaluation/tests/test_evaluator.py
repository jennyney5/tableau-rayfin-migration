from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from zipfile import ZipFile

import pytest
from jsonschema import ValidationError

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("evaluator", ROOT / "evaluator.py")
assert SPEC and SPEC.loader
evaluator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evaluator)


def workbook(path: Path, formula: str = "SUM([Sales])", worksheet_xml: str = "") -> Path:
    source = path / "test.twbx"
    with ZipFile(source, "w") as archive:
        archive.writestr("test.twb", f'''<workbook><datasources><datasource name="Orders">
<column name="[Sales]" datatype="real"/><column name="[Calc]" caption="Calculated">
<calculation formula="{formula}"/></column></datasource></datasources>
<worksheets><worksheet name="Sales"><table><view><datasource-dependencies datasource="Orders"/>
</view><rows>[Orders].[Calc]</rows></table>{worksheet_xml}</worksheet></worksheets></workbook>''')
    return source


def assessment(tmp_path: Path) -> Path:
    output = tmp_path / "intake"
    evaluator.assess(workbook(tmp_path), ROOT / "capability-profile.json", output)
    return output / "assessment.json"


def evidence(tmp_path: Path, assessment_path: Path) -> Path:
    artifact = tmp_path / "acceptance.txt"
    artifact.write_text("Synthetic test fixture only; not real migration evidence.", encoding="utf-8")
    records = [{"file": artifact.name, "sha256": evaluator.digest(artifact)}]
    result = evaluator.load(assessment_path)
    declaration = {
        "assessment_sha256": evaluator.digest(assessment_path),
        "source_sha256": result["source"]["sha256"], "profile_sha256": result["profile_sha256"],
        "workflow_sha256": result["workflow_sha256"],
        "reviewer": "Independent test reviewer", "artifacts": records,
        "target_identity": {"tenant": "synthetic-tenant", "workspace": "synthetic-workspace", "model": "synthetic-model", "app": "synthetic-app", "deployment_version": "test-only"},
        "precision_policy": "Synthetic fixture: exact counts; not real accepted precision evidence.",
        "scope_approved": True, "independent_review_completed": True,
        "scenarios": [{"worksheet": "Sales", "id": "default", "status": "passed", "artifacts": records}],
        "gates": {gate: {"status": "passed", "artifacts": records} for gate in evaluator.GATES},
        "interventions": [{"task": "Review translation", "owner": "Engineer", "active_minutes": 15}],
        "finding_resolutions": {item["id"]: {"status": "resolved", "details": "Synthetic resolved fixture", "artifacts": records} for item in result["findings"]},
    }
    path = tmp_path / "evidence.json"
    evaluator.save(path, declaration)
    return path


def test_static_assessment_never_certifies(tmp_path: Path) -> None:
    result = evaluator.load(assessment(tmp_path))
    assert result["category"] is None
    assert result["recommended_category"] == 1
    assert not result["full_migration_certified"]
    assert {item["blocker"] for item in result["findings"]} >= {
        "calculation_semantics", "data_types", "security", "ambiguous_source_logic"}


@pytest.mark.parametrize("formula", ["WINDOW_SUM(SUM([Sales]))", "INDEX()", "TOTAL(SUM([Sales]))"])
def test_table_calc_detection(tmp_path: Path, formula: str) -> None:
    manifest = evaluator.inspect_workbook(workbook(tmp_path, formula))
    assert any(item["blocker"] == "visual_dependencies" for item in evaluator.findings_for(manifest))


def test_security_formula_detection(tmp_path: Path) -> None:
    manifest = evaluator.inspect_workbook(workbook(tmp_path, "USERNAME()"))
    assert any(item["detected"] == "Identity-dependent calculation detected." for item in evaluator.findings_for(manifest))


def test_comments_and_strings_do_not_invent_security(tmp_path: Path) -> None:
    manifest = evaluator.inspect_workbook(workbook(tmp_path, "SUM([Sales]) // USERNAME()"))
    assert not any(item["detected"] == "Identity-dependent calculation detected." for item in evaluator.findings_for(manifest))


def test_observed_manual_intervention_is_category_two(tmp_path: Path) -> None:
    original = assessment(tmp_path)
    declaration = evidence(tmp_path, original)
    result = evaluator.verify(original, declaration, tmp_path / "accepted")
    assert result["category"] == 2
    assert result["full_migration_certified"]
    assert result["intervention_count"] == 1


def test_observed_automation_without_interventions_is_category_one(tmp_path: Path) -> None:
    original = assessment(tmp_path)
    path = evidence(tmp_path, original)
    declaration = evaluator.load(path)
    declaration["interventions"] = []
    evaluator.save(path, declaration)
    result = evaluator.verify(original, path, tmp_path / "automatic")
    assert result["category"] == 1
    assert result["full_migration_certified"]


@pytest.mark.parametrize("formula", ["SUM([Sales])", "{FIXED : SUM([Sales])}",
                                    "WINDOW_SUM(SUM([Sales]))", "RANK_UNIQUE(SUM([Sales]))"])
def test_supported_complexity_is_not_human_intervention(tmp_path: Path, formula: str) -> None:
    source = workbook(tmp_path, formula)
    result = evaluator.assess(source, ROOT / "capability-profile.json", tmp_path / "auto")
    assert result["recommended_category"] == 1
    assert result["required_human_steps"] == []


@pytest.mark.parametrize("enabled, expected", [("true", 2), ("false", 1)])
def test_forecast_metadata_not_filename_controls_manual_step(tmp_path: Path, enabled: str, expected: int) -> None:
    source = workbook(tmp_path, worksheet_xml=f'<forecast-specification enabled="{enabled}" model-type="auto-season"/>')
    source = source.rename(tmp_path / "Arbitrary renamed source.twbx")
    result = evaluator.assess(source, ROOT / "capability-profile.json", tmp_path / "forecast")
    assert result["recommended_category"] == expected
    assert len(result["required_human_steps"]) == int(enabled == "true")
    if enabled == "true":
        step = result["required_human_steps"][0]
        assert step["feature"] == "native_forecast"
        assert "model details" in step["next_action"]
        assert step["worksheets"] == ["Sales"]
        assert result["worksheet_decisions"][0]["recommended_category"] == 2
    assert result["category"] is None
    assert not result["full_migration_certified"]


@pytest.mark.parametrize("formula, expected", [
    ("UNRECOGNIZED_FUNCTION([Sales])", None),
    ("SCRIPT_REAL('return 1', SUM([Sales]))", None),
    ("SUM([Sales]) // UNRECOGNIZED_FUNCTION()", 1),
    ("'SCRIPT_REAL() forecast-specification USERNAME()'", 1),
    ("USERNAME()", None),
])
def test_unrecognized_capabilities_are_not_silently_automated(tmp_path: Path, formula: str, expected: int | None) -> None:
    result = evaluator.assess(workbook(tmp_path, formula), ROOT / "capability-profile.json", tmp_path / "unknown")
    assert result["recommended_category"] == expected
    assert bool(result["unknown_capabilities"]) == (expected is None)


@pytest.mark.parametrize("status, expected", [("automatic", 1), ("manual", 2), ("unsupported", 3), ("unknown", None)])
def test_explicit_capability_profile_differentiates_all_categories(tmp_path: Path, status: str, expected: int | None) -> None:
    profile = evaluator.load(ROOT / "capability-profile.json")
    profile["automation_rules"]["external_analytics"] = {
        "status": status, "reason": "Fixture: required live external analytics service.",
        "next_action": "Fixture: follow the approved runtime decision.",
        "requirement": "Preserve live calls to the external analytics service, not a local replacement.",
        "constraint": "Approved target policy forbids calls to this external service.",
        "supported_path_review": "Local rewrite and materialization do not preserve the required live-service behavior.",
        "reassessment_condition": "Permit an approved live service endpoint or change the requirement.",
        "constraint_approved_by": "Synthetic security owner (fixture only)",
    }
    path = tmp_path / "profile.json"
    evaluator.save(path, profile)
    source = workbook(tmp_path, "SCRIPT_REAL('return 1', SUM([Sales]))")
    result = evaluator.assess(source, path, tmp_path / "explicit")
    assert result["recommended_category"] == expected
    assert len(result["unsupported_requirements"]) == int(expected == 3)
    assert not result["full_migration_certified"]


def test_category_three_requires_specific_constraint_and_path_review(tmp_path: Path) -> None:
    profile = evaluator.load(ROOT / "capability-profile.json")
    profile["automation_rules"]["core_workbook"]["status"] = "unsupported"
    path = tmp_path / "incomplete-profile.json"
    evaluator.save(path, profile)
    with pytest.raises(ValueError, match="Unsupported rules require"):
        evaluator.assess(workbook(tmp_path), path, tmp_path / "invalid")


def test_unknown_capability_is_not_hidden_by_manual_forecast(tmp_path: Path) -> None:
    source = workbook(tmp_path, "UNKNOWN_FUNCTION([Sales])", '<forecast-specification enabled="true"/>')
    result = evaluator.assess(source, ROOT / "capability-profile.json", tmp_path / "mixed")
    assert result["recommended_category"] is None
    assert result["required_human_steps"]
    assert result["unknown_capabilities"]


@pytest.mark.parametrize("gate", evaluator.GATES)
def test_any_unverified_gate_blocks_certification(tmp_path: Path, gate: str) -> None:
    original = assessment(tmp_path)
    path = evidence(tmp_path, original)
    declaration = evaluator.load(path)
    declaration["gates"][gate]["status"] = "unverified"
    evaluator.save(path, declaration)
    result = evaluator.verify(original, path, tmp_path / "review")
    assert result["category"] is None
    assert not result["full_migration_certified"]


def test_constraint_requires_owner_and_supported_path(tmp_path: Path) -> None:
    original = assessment(tmp_path)
    path = evidence(tmp_path, original)
    declaration = evaluator.load(path)
    declaration["constraint_conflict"] = {
        "requirement": "Preserve entitlement", "constraint": "Target identity access prohibited",
        "attempted_supported_path": "Requested approved test identities",
        "reassessment_condition": "Authorize identity mapping", "owner": "Security owner",
        "owner_approved": True, "artifacts": declaration["artifacts"],
    }
    evaluator.save(path, declaration)
    result = evaluator.verify(original, path, tmp_path / "stopped")
    assert result["category"] == 3
    assert not result["full_migration_certified"]


@pytest.mark.parametrize("mutation", ["hash", "missing_sheet", "duplicate_state", "escape", "artifact_hash"])
def test_bad_evidence_fails_closed(tmp_path: Path, mutation: str) -> None:
    original = assessment(tmp_path)
    path = evidence(tmp_path, original)
    declaration = evaluator.load(path)
    if mutation == "hash":
        declaration["source_sha256"] = "0" * 64
    elif mutation == "missing_sheet":
        declaration["scenarios"][0]["worksheet"] = "Different sheet"
    elif mutation == "duplicate_state":
        declaration["scenarios"] *= 2
    elif mutation == "escape":
        declaration["artifacts"][0]["file"] = "../outside.txt"
    else:
        declaration["artifacts"][0]["sha256"] = "0" * 64
    evaluator.save(path, declaration)
    with pytest.raises((ValueError, ValidationError)):
        evaluator.verify(original, path, tmp_path / "invalid")


def test_existing_output_is_never_overwritten(tmp_path: Path) -> None:
    original = assessment(tmp_path)
    before = original.read_bytes()
    with pytest.raises(FileExistsError):
        evaluator.assess(tmp_path / "test.twbx", ROOT / "capability-profile.json", original.parent)
    assert original.read_bytes() == before


def test_unresolved_finding_blocks_acceptance(tmp_path: Path) -> None:
    original = assessment(tmp_path)
    path = evidence(tmp_path, original)
    declaration = evaluator.load(path)
    next(iter(declaration["finding_resolutions"].values()))["status"] = "unresolved"
    evaluator.save(path, declaration)
    result = evaluator.verify(original, path, tmp_path / "unresolved")
    assert result["category"] is None
    assert not result["full_migration_certified"]


def test_template_is_deliberately_not_acceptable(tmp_path: Path) -> None:
    original = assessment(tmp_path)
    template = tmp_path / "template.json"
    evaluator.prepare_evidence(original, template)
    with pytest.raises(ValidationError):
        evaluator.verify(original, template, tmp_path / "unacceptable")


def test_inventory_integrity_is_checked(tmp_path: Path) -> None:
    original = assessment(tmp_path)
    path = evidence(tmp_path, original)
    (original.parent / "inventory.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="Inventory changed"):
        evaluator.verify(original, path, tmp_path / "changed")


def test_all_seven_blockers_are_reported(tmp_path: Path) -> None:
    source = workbook(tmp_path, "WINDOW_SUM(SUM([Sales]))")
    manifest = evaluator.inspect_workbook(source)
    manifest["counts"]["parameters"] = 1
    parameter = dict(manifest["fields"][0])
    parameter.update({"id": "Parameters::[Mode]", "datasource": "Parameters"})
    manifest["fields"].append(parameter)
    manifest["actions"].append({"type": "action", "source_xml": "<action/>"})
    manifest["datasources"][0]["relation_xml"] = ['<relation type="join"/>']
    manifest["issues"].append({"code": "worksheet_definition_override", "worksheet": "Sales"})
    assert {item["blocker"] for item in evaluator.findings_for(manifest)} == set(evaluator.BLOCKERS)


def test_evaluation_only_completes_without_migration_evidence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError("Evaluation must not invoke migration acceptance")

    monkeypatch.setattr(evaluator, "verify", forbidden)
    source = workbook(tmp_path, "WINDOW_SUM(SUM([Sales]))")
    output = tmp_path / "evaluation"
    assert evaluator.main(["evaluate", "--input", str(source), "--output", str(output)]) == 0
    result = evaluator.load(output / "evaluation-summary.json")
    assert result["evaluation_status"] == "completed"
    assert result["migration_performed"] is False
    assert result["cloud_access_required"] is False
    assert not result["full_migration_certified"]
    assert result["workbooks"][0]["findings"]["visual_dependencies"] > 0


def test_empty_evaluation_directory_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="No TWBX"):
        evaluator.evaluate_portfolio(tmp_path, ROOT / "capability-profile.json", tmp_path / "empty-output")


def test_evaluation_processing_failure_is_not_category_three(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.twbx"
    invalid.write_bytes(b"not a workbook")
    result = evaluator.evaluate_portfolio(invalid, ROOT / "capability-profile.json", tmp_path / "invalid-output")
    assert result["evaluation_status"] == "partial"
    assert result["workbooks"][0]["evaluation_status"] == "failed"
    assert "recommended_category" not in result["workbooks"][0]


@pytest.mark.parametrize("filename, expected", [
    ("All Different Types of Drill-Downs in Tableau _ #VOTD _ #VizOfTheDay.twbx", 1),
    ("HR Dashboard RWFD 2024.twbx", 1),
    ("KPI Business Dashboard.twbx", 1),
    ("Mastering Tableau 17. Table calculations #2 - Window comparisons.twbx", 1),
    ("Mastering Tableau 8. LOD #1 - FIXED, INCLUDE, EXCLUDE examples.twbx", 1),
    ("Performance Optimization with Crunchbase Data.twbx", 2),
    ("Seattle-Incidents-ComplexDashboard.twbx", 1),
    ("Two Eras of Safety (Iron Viz 2025 Winner) (1).twbx", 1),
])
def test_owner_labeled_calibration_workbooks(tmp_path: Path, filename: str, expected: int) -> None:
    directory = os.environ.get("TABLEAU_BENCHMARK_DIR")
    if not directory:
        pytest.skip("Set TABLEAU_BENCHMARK_DIR to authorized local workbook copies; inputs are not bundled")
    source = Path(directory) / filename
    assert source.is_file(), f"Calibration input missing: {filename}"
    result = evaluator.assess(source, ROOT / "capability-profile.json", tmp_path / "calibration")
    assert result["recommended_category"] == expected
    assert not result["unknown_capabilities"]
    assert not result["unsupported_requirements"]
    assert bool(result["required_human_steps"]) == (expected == 2)
    assert result["full_migration_certified"] is False