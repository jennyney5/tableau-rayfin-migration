from __future__ import annotations

import importlib.util
import io
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SPEC = importlib.util.spec_from_file_location("suite", ROOT / "suite.py")
assert SPEC and SPEC.loader
suite = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(suite)


@pytest.mark.parametrize("url", ["http://public.tableau.com/x", "https://evil.example/x", "https://public.tableau.com.evil/x",
                                 "https://user:secret@public.tableau.com/x", "https://public.tableau.com:444/x"])
def test_download_host_is_restricted(url: str) -> None:
    with pytest.raises(ValueError):
        suite.public_url(url)


def test_valid_package_and_no_fake_html() -> None:
    stream = io.BytesIO()
    with ZipFile(stream, "w") as archive:
        archive.writestr("source.twb", "<workbook/>")
    suite.validate_payload(stream.getvalue())
    with pytest.raises(Exception):
        suite.validate_payload(b"<html>Permission denied</html>")


def test_oversize_and_wrong_xml_rejected() -> None:
    with pytest.raises(ValueError):
        suite.validate_payload(b"0" * (suite.MAX_DOWNLOAD + 1))
    stream = io.BytesIO()
    with ZipFile(stream, "w") as archive:
        archive.writestr("source.twb", "<error/>")
    with pytest.raises(ValueError):
        suite.validate_payload(stream.getvalue())


def test_partial_suite_records_failure_and_never_certifies(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.json"
    suite.evaluator.save(catalog, {"workbooks": [{"id": "missing", "title": "Missing fixture", "local_file": "missing.twbx"}]})
    result = suite.run(catalog, tmp_path / "run", False, False)
    assert result["status"] == "partial"
    assert result["workbooks"][0]["status"] == "failed"
    assert not result["full_migration_certified"]