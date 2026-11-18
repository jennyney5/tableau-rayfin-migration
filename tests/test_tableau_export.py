import json
from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from tableau_migration import tableau_export as export
from tableau_migration.common import sha256_file, write_json


URL = "https://example.online.tableau.com/#/site/contoso/views/SampleWorkbook/Dashboard?:iid=1"


@pytest.fixture
def capture_setup(tmp_path, monkeypatch):
    source = tmp_path / "source.twbx"
    source.write_bytes(b"synthetic source; inventory is mocked separately")
    config = {
        "schema_version": 1, "workbook_url": URL, "source_package": source.name,
        "source_workbook_sha256": sha256_file(source), "token_name": "sample-export",
        "scenarios": [{"id": "default", "filters": {}, "parameters": {}}],
    }
    config_path = tmp_path / "config.json"
    write_json(config_path, config)
    monkeypatch.setattr(export, "inspect_workbook", lambda path: {
        "source": {"sha256": sha256_file(path)},
        "worksheets": [{"name": "Sales"}, {"name": "Orders"}],
    })
    monkeypatch.setattr(export, "credentials", lambda cfg: ("sample-export", "not-a-real-secret"))
    workbook = SimpleNamespace(
        id="workbook-1", content_url="SampleWorkbook", name="Sample Workbook",
        updated_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
    )
    views = [
        SimpleNamespace(id="v1", workbook_id=workbook.id, name="Sales",
                        sheet_type="worksheet", content_url="SampleWorkbook/sheets/Sales"),
        SimpleNamespace(id="v2", workbook_id=workbook.id, name="Orders",
                        sheet_type="worksheet", content_url="SampleWorkbook/sheets/Orders"),
    ]

    def populate(view, options):
        view.csv = iter([b"Key,Amount\n", b"001,1.23000000000001\n"])

    server = SimpleNamespace(
        workbooks=SimpleNamespace(items=[workbook], get_by_id=lambda id: workbook),
        views=SimpleNamespace(items=views, populate_csv=populate),
        auth=SimpleNamespace(sign_in=lambda auth: nullcontext()),
        site_id="site-1", version="3.28",
        check_at_least_version=lambda version: False,
    )
    monkeypatch.setattr(export.TSC, "Server", lambda *args, **kwargs: server)
    monkeypatch.setattr(export.TSC, "Pager", lambda endpoint, *args: iter(endpoint.items))
    return config_path, config, server, workbook


def test_exports_each_exact_worksheet_and_records_immutable_evidence(capture_setup, tmp_path):
    path, config, _, _ = capture_setup
    result = export.capture(path, tmp_path / "new-capture")
    assert result["status"] == "completed"
    assert result["captured_count"] == result["expected_count"] == 2
    assert not result["full_migration_certified"]
    assert {row["worksheet"] for row in result["exports"]} == {"Sales", "Orders"}
    for row in result["exports"]:
        evidence = tmp_path / "new-capture" / row["file"]
        assert evidence.read_bytes().endswith(b"001,1.23000000000001\n")
        assert row["sha256"] == sha256_file(evidence)
        assert row["data_rows"] == 1
    assert "not-a-real-secret" not in json.dumps(result)
    with pytest.raises(FileExistsError):
        export.capture(path, tmp_path / "new-capture")


def test_hidden_or_dashboard_only_matches_leave_partial_coverage(capture_setup, tmp_path):
    path, _, server, _ = capture_setup
    server.views.items[1].sheet_type = "dashboard"
    result = export.capture(path, tmp_path / "capture")
    assert result["status"] == "partial"
    assert result["captured_count"] == 1 and result["expected_count"] == 2
    assert result["missing_worksheets"][0]["worksheet"] == "Orders"


def test_rejects_workbook_revision_changes_and_leaves_incomplete_status(capture_setup, tmp_path):
    path, _, server, workbook = capture_setup
    changed = SimpleNamespace(updated_at=datetime(2020, 1, 2, tzinfo=timezone.utc))
    versions = iter([workbook, changed])
    server.workbooks.get_by_id = lambda id: next(versions)
    with pytest.raises(ValueError, match="changed during capture"):
        export.capture(path, tmp_path / "capture")
    result = json.loads((tmp_path / "capture" / "capture-status.json").read_text())
    assert result["status"] == "incomplete"


def test_does_not_guess_at_workbook_names_or_ambiguous_sheet_matches(capture_setup, tmp_path):
    path, _, server, _ = capture_setup
    server.views.items.append(server.views.items[0])
    result = export.capture(path, tmp_path / "ambiguous-sheet")
    assert result["status"] == "partial"
    assert result["missing_worksheets"][0]["worksheet"] == "Sales"
    server.workbooks.items.clear()
    with pytest.raises(ValueError, match="no name fallback"):
        export.capture(path, tmp_path / "missing-workbook")


def test_applies_parameter_and_filter_options_without_rounding_or_empty_filter_widening():
    options = export.export_options({
        "filters": {"Region": "East,West"}, "parameters": {"Date View": "MTD"},
        "language": "en",
    })
    assert options.get_query_params() == {
        "maxAge": 1, "language": "en", "vf_Region": "East,West",
        "vf_Parameters.Date View": "MTD",
    }


@pytest.mark.parametrize("change", ["secret", "duplicate-scenario", "empty-filter", "unknown-sheet", "source-hash"])
def test_invalid_config_or_source_fails_before_network(capture_setup, tmp_path, change):
    path, config, server, _ = capture_setup
    if change == "secret":
        config["token_secret"] = "not-a-real-secret"
    elif change == "duplicate-scenario":
        config["scenarios"] *= 2
    elif change == "empty-filter":
        config["scenarios"][0]["filters"]["Region"] = ""
    elif change == "unknown-sheet":
        config["worksheets"] = ["Not in source"]
    else:
        config["source_workbook_sha256"] = "a" * 64
    write_json(path, config)
    server.auth.sign_in = lambda _: pytest.fail("No network should be attempted")
    with pytest.raises(ValueError):
        export.capture(path, tmp_path / "capture")


@pytest.mark.parametrize("body", [b"<html>Sign in</html>", b"Key,Amount\n1\n", b'{"error":"unavailable"}', b"Key,Amount\n"])
def test_malformed_or_unexpected_empty_csv_is_not_accepted(tmp_path, body):
    path = tmp_path / "data.csv"
    path.write_bytes(body)
    with pytest.raises(ValueError):
        export.csv_metadata(path, allow_empty=False)


def test_explicit_header_only_scenario_remains_empty_not_zero(tmp_path):
    path = tmp_path / "empty.csv"
    path.write_bytes(b"Key,Amount\n")
    assert export.csv_metadata(path, allow_empty=True)["data_rows"] == 0


def test_newline_only_empty_requires_verified_named_part_and_explicit_empty_scenario(tmp_path):
    path = tmp_path / "empty.csv"
    path.write_bytes(b"\n")
    for options in ({}, {"allow_empty": True}, {"named_empty_part": True}):
        with pytest.raises(ValueError):
            export.csv_metadata(path, **({"allow_empty": False} | options))
    metadata = export.csv_metadata(path, allow_empty=True, named_empty_part=True)
    assert metadata["data_rows"] == 0
    assert metadata["headers"] == []
    assert metadata["headerless_empty"] and metadata["contract_mapping_required"]


@pytest.mark.parametrize("body", [b"", b" ", b"<html>Sign in</html>", b'{"error":"unavailable"}'])
def test_named_empty_opt_in_does_not_accept_missing_or_error_bodies(tmp_path, body):
    path = tmp_path / "invalid.csv"
    path.write_bytes(body)
    with pytest.raises(ValueError):
        export.csv_metadata(path, allow_empty=True, named_empty_part=True)


def test_real_tableau_duplicate_captions_preserved_but_require_contract_mapping(tmp_path):
    path = tmp_path / "trend.csv"
    path.write_bytes(b"Max. Order Date,Max. Order Date,Sales\n2020,2021,0.10\n")
    metadata = export.csv_metadata(path, allow_empty=False)
    assert metadata["headers"] == ["Max. Order Date", "Max. Order Date", "Sales"]
    assert metadata["duplicate_headers"] == ["Max. Order Date"]
    assert metadata["contract_mapping_required"]


def multipart(parts):
    body = b""
    for name, payload, error in parts:
        body += (
            b"------=test-boundary\r\nContent-Type: text/csv\r\n"
            + f"X-Tableau-Sheet-Name: {name}\r\n".encode()
            + f"X-Tableau-Sheet-Status: {422 if error else 200}\r\n".encode()
            + (f"X-Tableau-Sheet-Error-Code: {error}\r\n".encode() if error else b"")
            + b"\r\n" + payload + b"\r\n"
        )
    return body + b"------=test-boundary--\r\n"


def test_all_data_parses_unquoted_equals_boundary_and_retains_error_parts():
    body = multipart([
        ("Sales", b'Key,Notes\n001,"one,\ntwo"\n', None), ("Orders", b"", "400081"),
    ])
    parts = export.multipart_sheets(body, "multipart/form-data; boundary=----=test-boundary")
    assert parts[0]["body"] == b'Key,Notes\n001,"one,\ntwo"\n'
    assert parts[1]["worksheet"] == "Orders" and parts[1]["error_code"] == "400081"
    with pytest.raises(ValueError, match="Malformed/truncated"):
        export.multipart_sheets(body[:-25], "multipart/form-data; boundary=----=test-boundary")
    with pytest.raises(ValueError, match="boundary"):
        export.multipart_sheets(body, "multipart/form-data")
    with pytest.raises(ValueError, match="ambiguous"):
        export.multipart_sheets(
            multipart([("Sales", b"A\n1", None), ("Sales", b"A\n2", None)]),
            "multipart/form-data; boundary=----=test-boundary",
        )


@pytest.mark.parametrize("view_type", ["dashboard", "story"])
def test_all_data_captures_hidden_worksheets_and_reports_per_sheet_failures(capture_setup, tmp_path, view_type):
    path, _, server, _ = capture_setup
    server.version = "3.30"
    server.check_at_least_version = lambda version: True
    server.views.items[:] = [
        SimpleNamespace(id="dashboard-1", workbook_id="workbook-1", name="Dashboard",
                        sheet_type=view_type, content_url="SampleWorkbook/sheets/Dashboard")
    ]
    server.views.baseurl = "https://example.online.tableau.com/api/3.30/sites/site-1/views"
    body = multipart([("Sales", b"Key,Amount\n001,100.10\n", None), ("Orders", b"", "400081")])
    requested = []

    def request(url, request_object, parameters):
        requested.append(url)
        return SimpleNamespace(
            headers={"Content-Type": "multipart/form-data; boundary=----=test-boundary"},
            iter_content=lambda size: iter([body]), close=lambda: None,
        )

    server.views.get_request = request
    result = export.capture(path, tmp_path / "modern")
    assert requested[0].endswith("/dashboard-1/allData")
    assert result["status"] == "partial"
    assert result["captured_count"] == 1
    assert result["exports"][0]["worksheet"] == "Sales"
    assert result["exports"][0]["parent_view"] == "Dashboard"
    assert result["export_errors"][0]["code"] == "400081"
    assert result["missing_worksheets"][0]["worksheet"] == "Orders"
    raw = result["raw_responses"][0]
    assert raw["sha256"] == sha256_file(tmp_path / "modern" / raw["file"])


def test_all_data_retains_same_sheet_in_multiple_dashboard_contexts(capture_setup, tmp_path):
    path, _, server, _ = capture_setup
    server.version = "3.30"
    server.check_at_least_version = lambda version: True
    for view in server.views.items:
        view.sheet_type = "dashboard"
    server.views.baseurl = "https://example.online.tableau.com/api/3.30/sites/site-1/views"
    body = multipart([
        ("Sales", b"Key,Amount\n001,100.10\n", None),
        ("Orders", b"Key,Amount\n001,2\n", None),
    ])
    server.views.get_request = lambda *args, **kwargs: SimpleNamespace(
        headers={"Content-Type": "multipart/form-data; boundary=----=test-boundary"},
        iter_content=lambda size: iter([body]), close=lambda: None,
    )
    result = export.capture(path, tmp_path / "modern")
    assert result["status"] == "completed"
    assert result["captured_count"] == result["expected_count"] == 2
    assert result["exported_csv_count"] == 4
    assert len({row["view_id"] for row in result["exports"]}) == 2


def test_configure_rejects_non_native_vault_before_prompting(monkeypatch):
    monkeypatch.setattr(export.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(export.keyring, "get_keyring", lambda: SimpleNamespace())
    monkeypatch.setattr(export.getpass, "getpass", lambda _: pytest.fail("Must not prompt before vault validation"))
    with pytest.raises(ValueError, match="Windows Credential Manager"):
        export.configure({"workbook_url": URL, "token_name": "sample-export"})


def test_parent_view_selection_fails_closed_when_missing(capture_setup, tmp_path):
    path, config, server, _ = capture_setup
    config["parent_views"] = ["Not published"]
    write_json(path, config)
    server.version = "3.30"
    server.check_at_least_version = lambda version: True
    with pytest.raises(ValueError, match="Parent view missing or ambiguous"):
        export.capture(path, tmp_path / "missing-parent")


def test_credentials_require_explicit_matching_environment_pair(monkeypatch):
    config = {"workbook_url": URL, "token_name": "sample-export"}
    monkeypatch.setenv("TABLEAU_TOKEN_NAME", "different-name")
    monkeypatch.setenv("TABLEAU_TOKEN_SECRET", "not-a-real-secret")
    with pytest.raises(ValueError, match="must match"):
        export.credentials(config)
    monkeypatch.setenv("TABLEAU_TOKEN_NAME", "sample-export")
    assert export.credentials(config) == ("sample-export", "not-a-real-secret")
    monkeypatch.delenv("TABLEAU_TOKEN_SECRET")
    with pytest.raises(ValueError, match="both"):
        export.credentials(config)


def test_missing_credentials_leave_incomplete_status_without_echoing_secret(capture_setup, tmp_path, monkeypatch, caplog):
    path, _, _, _ = capture_setup

    def missing(config):
        raise ValueError("No stored PAT. Run configure")

    monkeypatch.setattr(export, "credentials", missing)
    assert export.main(["capture", "--config", str(path), "--output", str(tmp_path / "run")]) == 2
    assert "Run configure" in caplog.text
    assert json.loads((tmp_path / "run" / "capture-status.json").read_text())["status"] == "incomplete"


@pytest.mark.parametrize("url", [
    "http://example.online.tableau.com/#/site/a/views/b/c",
    "https://user:password@example.online.tableau.com/#/site/a/views/b/c",
    "https://public.tableau.com/app/profile/example/viz/Test/Sheet",
])
def test_rejects_public_insecure_or_credential_bearing_urls(url):
    with pytest.raises(ValueError):
        export.target(url)
