from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile

import pytest

from test_evaluator import workbook

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SPEC = importlib.util.spec_from_file_location("evaluation_cloud", ROOT / "cloud.py")
assert SPEC and SPEC.loader
cloud = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cloud)
CONFIG = {"schema_version": 1, "server_url": "https://example.online.tableau.com",
          "site_content_url": "test-site", "token_name": "evaluation"}


def server_for(payload: bytes, *, denied=False, inconsistent=False):
    class Workbooks:
        def __init__(self):
            self.pages = []
            self.downloads = []

        def get(self, options):
            self.pages.append(options.pagenumber)
            index = options.pagenumber
            total = 3 if inconsistent and index == 2 else 2
            return [SimpleNamespace(id=f"id-{index}", name=f"Workbook {index}")], SimpleNamespace(
                total_available=total, page_number=index, page_size=1)

        def download(self, workbook_id, filepath, include_extract):
            self.downloads.append((workbook_id, include_extract))
            if denied and workbook_id == "id-1":
                raise PermissionError("Sensitive server response must not be logged")
            filepath.write(payload)

    return SimpleNamespace(workbooks=Workbooks())


@pytest.mark.parametrize("plain_xml", [False, True])
def test_paginated_cloud_evaluation(tmp_path, plain_xml):
    source = workbook(tmp_path)
    payload = source.read_bytes()
    if plain_xml:
        with ZipFile(source) as archive:
            payload = archive.read(archive.namelist()[0])
    server = server_for(payload)
    output = tmp_path / "run"
    result = cloud.scan(server, CONFIG, ROOT / "capability-profile.json", output)
    assert server.workbooks.pages == [1, 2]
    assert server.workbooks.downloads == [("id-1", False), ("id-2", False)]
    assert result["evaluation_status"] == "completed"
    assert [item["recommended_category"] for item in result["workbooks"]] == [1, 1]
    assert result["migration_performed"] is False
    assert result["full_migration_certified"] is False
    inventory = json.loads((output / "cloud-inventory.json").read_text())
    assert len(inventory["workbooks"]) == 2
    assert (output / "cloud-summary.md").exists()
    assert not list(output.rglob("*.tmp"))


def test_denied_download_does_not_stop_other_workbooks(tmp_path):
    server = server_for(workbook(tmp_path).read_bytes(), denied=True)
    output = tmp_path / "run"
    result = cloud.scan(server, CONFIG, ROOT / "capability-profile.json", output)
    assert result["evaluation_status"] == "partial"
    assert result["workbooks"][0]["recommended_category"] is None
    assert result["workbooks"][1]["recommended_category"] == 1
    assert "Sensitive server response" not in (output / "cloud-summary.json").read_text()


def test_inconsistent_inventory_is_not_a_complete_site_assessment(tmp_path):
    server = server_for(b"", inconsistent=True)
    result = cloud.scan(server, CONFIG, ROOT / "capability-profile.json", tmp_path / "run")
    assert result["discovery_status"] == "failed"
    assert result["evaluation_status"] == "partial"
    assert not server.workbooks.downloads


def test_download_limit(monkeypatch, tmp_path):
    monkeypatch.setattr(cloud, "MAX_DOWNLOAD_BYTES", 4)
    with cloud.BoundedDownload(io.FileIO(tmp_path / "payload", "w")) as stream:
        stream.write(b"1234")
        with pytest.raises(ValueError, match="limit"):
            stream.write(b"5")


def test_installed_sdk_streams_into_bounded_writer(monkeypatch, tmp_path):
    from tableauserverclient.server.endpoint.workbooks_endpoint import Workbooks

    monkeypatch.setattr(cloud, "MAX_DOWNLOAD_BYTES", 4)
    response = SimpleNamespace(headers={"Content-Disposition": 'attachment; filename="server.twbx"'},
                               iter_content=lambda size: iter([b"1234", b"5"]), close=lambda: None)
    endpoint = SimpleNamespace(get_request=lambda url, parameters: response)
    with cloud.BoundedDownload(io.FileIO(tmp_path / "payload", "w")) as stream:
        with pytest.raises(ValueError, match="limit"):
            Workbooks._download_content(endpoint, "https://example.com/content", stream)


def test_empty_site_is_a_complete_empty_inventory(tmp_path):
    server = SimpleNamespace(workbooks=SimpleNamespace(get=lambda options: (
        [], SimpleNamespace(total_available=0, page_number=1))))
    result = cloud.scan(server, CONFIG, ROOT / "capability-profile.json", tmp_path / "run")
    assert result["evaluation_status"] == "completed"
    assert result["discovered_workbooks"] == 0
    assert result["workbooks"] == []


def test_duplicate_ids_rejected():
    server = SimpleNamespace(workbooks=SimpleNamespace(get=lambda options: (
        [SimpleNamespace(id="same"), SimpleNamespace(id="same")],
        SimpleNamespace(total_available=2, page_number=1))))
    with pytest.raises(ValueError, match="Duplicate"):
        cloud.discover(server)


@pytest.mark.parametrize("payload", [b"<html>Login required</html>", b"not XML", b""])
def test_invalid_downloads_are_not_classified(tmp_path, payload):
    result = cloud.scan(server_for(payload), CONFIG, ROOT / "capability-profile.json", tmp_path / "run")
    assert result["evaluation_status"] == "partial"
    assert all(item["recommended_category"] is None for item in result["workbooks"])


def test_existing_output_is_not_overwritten(tmp_path):
    output = tmp_path / "run"
    output.mkdir()
    with pytest.raises(FileExistsError):
        cloud.scan(server_for(b""), CONFIG, ROOT / "capability-profile.json", output)


def test_site_credentials_share_existing_vault_namespace():
    from tableau_migration.tableau_export import credential_service

    assert credential_service(CONFIG) == "tableau-rayfin:https://example.online.tableau.com/site/test-site"


def test_cloud_forecast_remains_semi_automated(tmp_path):
    source = workbook(tmp_path, worksheet_xml='<forecast-specification enabled="true"/>')
    result = cloud.scan(server_for(source.read_bytes()), CONFIG, ROOT / "capability-profile.json", tmp_path / "run")
    assert all(item["recommended_category"] == 2 for item in result["workbooks"])


def test_cloud_unknown_feature_remains_undetermined(tmp_path):
    source = workbook(tmp_path, worksheet_xml='<dashboard-extension/>')
    result = cloud.scan(server_for(source.read_bytes()), CONFIG, ROOT / "capability-profile.json", tmp_path / "run")
    assert result["evaluation_status"] == "completed"
    assert all(item["recommended_category"] is None for item in result["workbooks"])
    assert all(any(decision["feature"] == "dashboard_extension"
                   for decision in item["unknown_capabilities"]) for item in result["workbooks"])


@pytest.mark.parametrize("changes", [{"token_secret": "never"}, {"server_url": "http://example.com"},
                                     {"server_url": "https://public.tableau.com"},
                                     {"server_url": "https://user:secret@example.com"}])
def test_unsafe_config_rejected(tmp_path, changes):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({**CONFIG, **changes}))
    with pytest.raises(ValueError):
        cloud.load_config(path)