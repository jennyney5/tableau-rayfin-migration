"""Read-only Tableau Cloud discovery and detailed definition evaluation."""

from __future__ import annotations

import argparse
import io
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from zipfile import ZipFile, is_zipfile

import tableauserverclient as TSC
from defusedxml.ElementTree import fromstring

from tableau_migration.common import check_package, sha256_file
from tableau_migration.tableau_export import configure, credentials

from evaluator import CATEGORIES, ROOT, VERSION, assess, load, new_run, save

MAX_DOWNLOAD_BYTES = 50 * 1024 * 1024


def load_config(path: Path) -> dict:
    config = load(path)
    if set(config) != {"schema_version", "server_url", "site_content_url", "token_name"}:
        raise ValueError("Expected schema_version, server_url, site_content_url and token_name only; never store secrets in JSON")
    if config["schema_version"] != 1:
        raise ValueError("Expected schema_version 1")
    if not all(isinstance(config[key], str) for key in ("server_url", "site_content_url", "token_name")):
        raise ValueError("Connection fields must be strings")
    parts = urlsplit(config["server_url"])
    if (parts.scheme != "https" or not parts.hostname or parts.username or parts.password
            or parts.port not in {None, 443} or parts.path not in {"", "/"}
            or parts.query or parts.fragment or parts.hostname.lower() == "public.tableau.com"):
        raise ValueError("server_url must be an HTTPS Tableau Cloud/Server origin, not Tableau Public")
    if not config["token_name"].strip() or any(character in config["site_content_url"] for character in "/\\?#"):
        raise ValueError("Set a PAT name and the site content URL slug (not its display name)")
    config["server_url"] = f"https://{parts.netloc.lower()}"
    return config


class BoundedDownload(io.BufferedWriter):
    def write(self, data):
        if self.tell() + len(data) > MAX_DOWNLOAD_BYTES:
            raise ValueError("Workbook definition download exceeds 50 MiB limit")
        return super().write(data)


def package_definition(download: Path, destination: Path) -> None:
    if not download.stat().st_size or download.stat().st_size > MAX_DOWNLOAD_BYTES:
        raise ValueError("Empty or oversized workbook download")
    if is_zipfile(download):
        with ZipFile(download) as archive:
            check_package(archive)
            definitions = [name for name in archive.namelist() if name.lower().endswith(".twb")]
            if len(definitions) != 1:
                raise ValueError("Expected exactly one workbook definition")
            root = fromstring(archive.read(definitions[0]))
        if root.tag.rsplit("}", 1)[-1] != "workbook":
            raise ValueError("Downloaded XML is not a Tableau workbook")
        download.replace(destination)
    else:
        root = fromstring(download.read_bytes())
        if root.tag.rsplit("}", 1)[-1] != "workbook":
            raise ValueError("Downloaded XML is not a Tableau workbook")
        with ZipFile(destination, "w") as archive:
            archive.write(download, "workbook.twb")
        download.unlink()


def discover(server) -> list:
    workbooks = []
    seen = set()
    page_number = 1
    expected_total = None
    while True:
        page, pagination = server.workbooks.get(TSC.RequestOptions(pagenumber=page_number, pagesize=100))
        if expected_total is None:
            expected_total = pagination.total_available
        if pagination.total_available != expected_total or pagination.page_number != page_number:
            raise ValueError("Workbook inventory changed during pagination; rerun for a consistent inventory")
        for item in page:
            if not item.id or item.id in seen:
                raise ValueError("Duplicate or missing workbook ID during pagination")
            seen.add(item.id)
            workbooks.append(item)
        if len(workbooks) == expected_total:
            return workbooks
        if not page or len(workbooks) > expected_total:
            raise ValueError("Incomplete or inconsistent workbook pagination")
        page_number += 1


def scan(server, config: dict, profile: Path, output: Path) -> dict:
    new_run(output)
    result = {
        "schema_version": 1, "tool_version": VERSION, "mode": "cloud-detailed",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "server_url": config["server_url"], "site_content_url": config["site_content_url"],
        "scope": "Workbooks visible to the authenticated principal in this site, not all tenant content.",
        "discovery_status": "incomplete", "evaluation_status": "incomplete", "workbooks": [],
        "extracts_requested": False, "migration_performed": False, "full_migration_certified": False,
        "limitations": [
            "No metadata-only screening mode is implemented.",
            "Extracts are not requested, but returned packages may still contain sensitive embedded content; retained outputs require approved storage and retention.",
            "Capability detection is not exhaustive; unknown detected features require review, and predictions do not guarantee migration parity.",
            "Definitions may reference published data sources whose full definitions are not included.",
            "No physical-data profiling, live result capture, numerical parity or runtime/security validation.",
            "Source definitions, assets and reports are sensitive customer data; protect the output directory.",
        ],
    }
    save(output / "cloud-summary.json", result)
    try:
        workbooks = discover(server)
    except Exception as error:
        result.update(discovery_status="failed", evaluation_status="partial", error_type=type(error).__name__)
        finish(output, result)
        return result
    result.update(discovery_status="completed", discovered_workbooks=len(workbooks))
    save(output / "cloud-inventory.json", {
        "scope": result["scope"], "discovery_status": "completed",
        "workbooks": [{"id": item.id, "name": item.name,
                       "project_id": getattr(item, "project_id", None),
                       "owner_id": getattr(item, "owner_id", None),
                       "updated_at": str(getattr(item, "updated_at", ""))} for item in workbooks],
    })
    save(output / "cloud-summary.json", result)
    for index, workbook in enumerate(workbooks, start=1):
        relative = f"workbook-{index:04d}"
        folder = output / relative
        folder.mkdir()
        download = folder / "download.tmp"
        package = folder / "definition.twbx"
        record = {
            "id": workbook.id, "name": workbook.name,
            "project_id": getattr(workbook, "project_id", None),
            "owner_id": getattr(workbook, "owner_id", None),
            "updated_at": str(getattr(workbook, "updated_at", "")),
            "evaluation_status": "incomplete", "recommended_category": None,
            "full_migration_certified": False,
        }
        stage = "download"
        try:
            with BoundedDownload(io.FileIO(download, "w")) as stream:
                server.workbooks.download(workbook.id, filepath=stream, include_extract=False)
            stage = "definition_validation"
            record["download_sha256"] = sha256_file(download)
            package_definition(download, package)
            stage = "assessment"
            assessment = assess(package, profile, folder / "assessment")
            record.update(
                evaluation_status="completed", recommended_category=assessment["recommended_category"],
                required_human_steps=assessment["required_human_steps"],
                unknown_capabilities=assessment["unknown_capabilities"],
                report=f"{relative}/assessment/report.md",
            )
        except Exception as error:
            record.update(evaluation_status="failed", failed_stage=stage, error_type=type(error).__name__)
        finally:
            download.unlink(missing_ok=True)
        result["workbooks"].append(record)
        save(output / "cloud-summary.json", result)
    result["evaluation_status"] = "completed" if all(
        item["evaluation_status"] == "completed" for item in result["workbooks"]
    ) else "partial"
    finish(output, result)
    return result


def finish(output: Path, result: dict) -> None:
    save(output / "cloud-summary.json", result)
    lines = ["# Tableau Cloud Detailed Evaluation", "", result["scope"], "",
             f"Discovery: {result['discovery_status']}. Evaluation: {result['evaluation_status']}.", "",
             "Readiness predictions only. No migration or parity certification was performed.",
             "Downloads requested workbook definitions without extracts.", "",
             "| Workbook | Evaluation | Predicted category | Report |", "|---|---|---|---|"]
    for item in result["workbooks"]:
        name = item["name"].replace("|", "/").replace("\n", " ").replace("\r", " ")
        report = f"[Details]({item['report']})" if item.get("report") else f"Failed: {item.get('failed_stage')} ({item.get('error_type')})"
        lines.append(f"| {name} | {item['evaluation_status']} | {CATEGORIES[item['recommended_category']]} | {report} |")
    lines.extend(["", "## Limitations", "", *[f"- {text}" for text in result["limitations"]]])
    if result.get("error_type"):
        lines.extend(["", f"Discovery failed ({result['error_type']}); no complete site assessment is available."])
    (output / "cloud-summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    save(output / "run-status.json", {"status": result["evaluation_status"], "command": "cloud-evaluate",
                                     "migration_performed": False})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("configure", "evaluate"))
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--profile", type=Path, default=ROOT / "capability-profile.json")
    args = parser.parse_args()
    try:
        config = load_config(args.config)
        if args.command == "configure":
            configure(config)
            return 0
        if args.output is None:
            raise ValueError("evaluate requires a new --output directory")
        if args.output.exists():
            raise ValueError("Output already exists; choose a new directory")
        load(args.profile)
        name, secret = credentials(config)
        server = TSC.Server(config["server_url"], use_server_version=True, http_options={"timeout": 120})
        with server.auth.sign_in(TSC.PersonalAccessTokenAuth(name, secret, config["site_content_url"])):
            result = scan(server, config, args.profile, args.output)
        print(f"{result['evaluation_status']}: {args.output / 'cloud-summary.md'}")
        return 0 if result["evaluation_status"] == "completed" else 1
    except Exception as error:
        print(f"Cloud evaluation stopped ({type(error).__name__}). Check config, permissions, credentials and output path; secrets are not logged.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())