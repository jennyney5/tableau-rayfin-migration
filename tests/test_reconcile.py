import csv
import json
from pathlib import Path

import pytest

from tableau_migration.cli import main
from tableau_migration.common import sha256_file, write_json
from tableau_migration.reconcile import compare_contract


def capture(tmp_path: Path, expected, actual, *, rules=None, keys=None, encoding="utf-8"):
    rules = rules or {"Key": {"type": "string"}, "Amount": {"type": "decimal"}}
    delimiter = "\t" if encoding == "utf-16" else ","
    for name, rows in [("source", expected), ("target", actual)]:
        with (tmp_path / f"{name}.csv").open("w", encoding=encoding, newline="") as stream:
            writer = csv.writer(stream, delimiter=delimiter)
            writer.writerow(rules)
            writer.writerows(rows)
    exports = []
    for name, engine in [("source", "tableau-desktop"), ("target", "fabric-sql")]:
        path = tmp_path / f"{name}.csv"
        exports.append({
            "file": path.name, "sha256": sha256_file(path), "engine": engine,
            "workbook_sha256": "a" * 64, "worksheet": "Sales",
            "state": {"filters": {}, "parameters": {"Period": "YTD"}},
            "delimiter": delimiter,
        })
    contract = {
        "schema_version": 1, "scenario": "sales-ytd",
        "keys": ["Key"] if keys is None else keys, "columns": rules,
        "baseline": exports[0], "candidate": exports[1],
    }
    path = tmp_path / "contract.json"
    write_json(path, contract)
    return path, contract


def test_decimal_precision_and_row_order_are_preserved(tmp_path):
    path, _ = capture(
        tmp_path, [["001", "123456789012345678901234567890.01"], ["002", "0.10"]],
        [["002", "0.100"], ["001", "123456789012345678901234567890.02"]],
    )
    result = compare_contract(path)
    assert result["status"] == "failed"
    assert result["difference_count"] == 1
    assert result["differences"][0]["key"] == ["001"]


def test_explicit_tolerance_and_utf16_tableau_exports(tmp_path):
    path, _ = capture(
        tmp_path, [["001", "2.00"]], [["001", "2.001"]],
        rules={"Key": {"type": "string"}, "Amount": {"type": "decimal", "absolute_tolerance": "0.001"}},
        encoding="utf-16",
    )
    assert compare_contract(path)["status"] == "passed"


def test_missing_and_unexpected_rows_fail(tmp_path):
    path, _ = capture(tmp_path, [["001", "1"]], [["002", "1"]])
    assert {d["kind"] for d in compare_contract(path)["differences"]} == {
        "missing_candidate_row", "unexpected_candidate_row",
    }


def test_duplicate_keys_are_not_aggregated_away(tmp_path):
    path, _ = capture(tmp_path, [["001", "1"], ["001", "2"]], [["001", "3"]])
    with pytest.raises(ValueError, match="duplicate comparison key"):
        compare_contract(path)


def test_empty_string_is_not_implicitly_null_or_zero(tmp_path):
    path, contract = capture(
        tmp_path, [["001", ""]], [["001", "\\N"]],
        rules={"Key": {"type": "string"}, "Label": {"type": "string"}},
    )
    contract["null_tokens"] = ["\\N"]
    write_json(path, contract)
    assert compare_contract(path)["status"] == "failed"


@pytest.mark.parametrize("change", ["state", "hash", "integer", "negative_tolerance", "nan", "empty"])
def test_invalid_capture_never_passes(tmp_path, change):
    expected, actual = [["001", "1"]], [["001", "1"]]
    rules = None
    if change == "integer":
        rules = {"Key": {"type": "string"}, "Amount": {"type": "integer"}}
        actual = [["001", "1.1"]]
    if change == "nan":
        actual = [["001", "NaN"]]
    if change == "empty":
        expected, actual = [], []
    path, contract = capture(tmp_path, expected, actual, rules=rules)
    if change == "state":
        contract["candidate"]["state"]["parameters"]["Period"] = "MTD"
    if change == "hash":
        contract["baseline"]["sha256"] = "b" * 64
    if change == "negative_tolerance":
        contract["columns"]["Amount"]["absolute_tolerance"] = "-1"
    write_json(path, contract)
    with pytest.raises(ValueError):
        compare_contract(path)


def test_schema_drift_and_duplicate_headers_are_rejected(tmp_path):
    path, contract = capture(tmp_path, [["001", "1"]], [["001", "1"]])
    target = tmp_path / "target.csv"
    target.write_text("Key,Key\n001,1\n", encoding="utf-8")
    contract["candidate"]["sha256"] = sha256_file(target)
    write_json(path, contract)
    with pytest.raises(ValueError, match="headers"):
        compare_contract(path)


def test_single_aggregate_needs_no_artificial_key(tmp_path):
    path, _ = capture(
        tmp_path, [["1.00"]], [["1"]], rules={"Total": {"type": "decimal"}}, keys=[],
    )
    assert compare_contract(path)["status"] == "passed"


def test_cli_returns_nonzero_for_mismatch_and_preserves_input(tmp_path):
    path, _ = capture(tmp_path, [["001", "1"]], [["001", "2"]])
    output = tmp_path / "report.json"
    assert main(["compare", "--contract", str(path), "--output", str(output)]) == 1
    assert json.loads(output.read_text())["status"] == "failed"
    before = sha256_file(path)
    assert main(["compare", "--contract", str(path), "--output", str(path)]) == 2
    assert sha256_file(path) == before


def test_tolerance_cannot_hide_count_or_key_differences(tmp_path):
    path, contract = capture(
        tmp_path, [["001", "1"]], [["001", "2"]],
        rules={"Key": {"type": "string"}, "Amount": {"type": "integer"}},
    )
    contract["columns"]["Amount"]["absolute_tolerance"] = "1"
    write_json(path, contract)
    with pytest.raises(ValueError, match="only on non-key decimal"):
        compare_contract(path)


def test_cli_rejects_malformed_csv_and_does_not_overwrite_evidence(tmp_path):
    path, contract = capture(tmp_path, [["001", "1"]], [["001", "1"]])
    target = tmp_path / "target.csv"
    before = sha256_file(target)
    assert main(["compare", "--contract", str(path), "--output", str(target)]) == 2
    assert sha256_file(target) == before
    target.write_text('Key,Amount\n"unclosed,1\n', encoding="utf-8")
    contract["candidate"]["sha256"] = sha256_file(target)
    write_json(path, contract)
    assert main(["compare", "--contract", str(path), "--output", str(tmp_path / "report.json")]) == 2


def test_failed_audit_invalidates_previous_run_completion(tmp_path):
    output = tmp_path / "output"
    write_json(output / "run-status.json", {"status": "completed"})
    assert main(["audit", "--input", str(tmp_path / "missing.twbx"), "--output", str(output)]) == 2
    assert json.loads((output / "run-status.json").read_text())["status"] == "incomplete"
