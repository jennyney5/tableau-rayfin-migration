"""Acquire approved public examples and produce a reproducible local benchmark."""

from __future__ import annotations

import argparse
import io
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from zipfile import ZipFile

from defusedxml.ElementTree import fromstring

import evaluator
from tableau_migration.common import check_package
from tableau_migration.profile import profile_package

MAX_DOWNLOAD = 50 * 1024 * 1024


def public_url(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != "public.tableau.com" or parsed.port not in {None, 443} or parsed.username or parsed.password:
        raise ValueError("Only HTTPS public.tableau.com URLs are allowed")
    return url


class PublicRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def validate_payload(payload: bytes) -> None:
    if len(payload) > MAX_DOWNLOAD:
        raise ValueError("Workbook exceeds the 50 MB download limit")
    with ZipFile(io.BytesIO(payload)) as archive:
        check_package(archive)
        names = [name for name in archive.namelist() if name.lower().endswith(".twb")]
        if len(names) != 1:
            raise ValueError("Download must contain exactly one Tableau workbook")
        root = fromstring(archive.read(names[0]))
        if root.tag.rsplit("}", 1)[-1] != "workbook":
            raise ValueError("The downloaded XML is not a Tableau workbook")


def download(entry: dict, destination: Path) -> dict:
    url = public_url(entry["download_url"])
    request = Request(url, headers={"User-Agent": f"TableauMigrationAssessment/{evaluator.VERSION}"})
    with build_opener(PublicRedirects()).open(request, timeout=30) as response:
        public_url(response.url)
        length = response.headers.get("Content-Length")
        if length and int(length) > MAX_DOWNLOAD:
            raise ValueError("Workbook exceeds the 50 MB download limit")
        payload = response.read(MAX_DOWNLOAD + 1)
        metadata = {"http_status": response.status, "content_type": response.headers.get("Content-Type"),
                    "download_url": url, "resolved_url": response.url}
    validate_payload(payload)
    with destination.open("xb") as stream:
        stream.write(payload)
    return metadata


def coverage(manifest: dict) -> dict:
    features = {feature for field in manifest["fields"] for feature in field["features"]}
    table_calcs = any(sheet["table_calculations"] for sheet in manifest["worksheets"])
    relation_nodes = []
    for source in manifest["datasources"]:
        for text in source["relation_xml"] + source["relationship_xml"] + source["object_graph_xml"]:
            root = fromstring(text)
            relation_nodes.extend(node for node in root.iter()
                                  if node.tag.rsplit("}", 1)[-1] in {"join", "relationship"} or node.get("type") == "join")
    identities = any(item["detected"] == "Identity-dependent calculation detected."
                     for item in evaluator.findings_for(manifest))
    return {
        "calculation_semantics": "detected_candidate" if features & {"fixed_lod", "include_lod", "exclude_lod", "window", "running", "ranking", "lookup"} else "not_established",
        "visual_dependencies": "detected_candidate" if table_calcs or features & {"window", "running", "ranking", "lookup"} else "not_established",
        "parameters_interactions": "detected_candidate" if manifest["counts"]["parameters"] or manifest["actions"] else "not_established",
        "data_types": "partial_candidate; edge cases and physical rows still need review",
        "ambiguous_source_logic": "review_candidate; no owner-confirmed intentional conflict",
        "relationships": "detected_candidate; cardinality still unverified" if relation_nodes else "not_established",
        "security": "formula_candidate; multi-identity evidence unavailable on Public" if identities else "private_test_required",
    }


def scenario_plan(manifest: dict, entry: dict) -> dict:
    scenarios = []
    for sheet in manifest["worksheets"]:
        scenarios.append({"worksheet": sheet["name"], "id": "saved-default", "status": "unverified",
                          "effective_state": "Record published/saved filters and parameters before capture",
                          "source_export": None, "source_sha256": manifest["source"]["sha256"],
                          "artifacts": [], "owner_review_required": True})
        if sheet["filters"]:
            for state in ("single-select", "multi-select", "empty", "reset"):
                scenarios.append({"worksheet": sheet["name"], "id": state, "status": "unverified",
                                  "effective_state": "Owner must define a valid source-specific selection",
                                  "source_export": None, "source_sha256": manifest["source"]["sha256"],
                                  "artifacts": [], "owner_review_required": True})
    return {"workbook_id": entry["id"], "source_sha256": manifest["source"]["sha256"],
            "approved": False, "scenarios": scenarios,
            "additional_required_review": [
                "All supported parameters and their dependent results; finite domains versus boundary coverage",
                "LOD context and table-calculation partitions/addressing, ties and totals where applicable",
                "Browser drill, highlight, navigation, action scope and reset where applicable",
                "Physical nulls/zeros/duplicates/dates, export precision and relationship grain",
                "Restricted identities, unmapped identity and direct backend access in a private environment",
                "Repeated full-mark transitions, responsiveness, loading/errors, reload and viewer access",
            ]}


def run(catalog_path: Path, output: Path, download_public: bool, profile: bool, public_only: bool = False) -> dict:
    catalog = evaluator.load(catalog_path)
    entries = [entry for entry in catalog["workbooks"] if not public_only or entry.get("download_url")]
    if not entries:
        raise ValueError("No matching workbook candidates")
    ids = [entry["id"] for entry in entries]
    if len(set(ids)) != len(ids) or any(not re.fullmatch(r"[a-z0-9-]+", name) for name in ids):
        raise ValueError("Catalog IDs must be unique safe slugs")
    evaluator.new_run(output)
    (output / "workbooks").mkdir()
    results = []
    for entry in entries:
        record = {"id": entry["id"], "title": entry["title"], "status": "incomplete",
                  "source_page": entry.get("source_page"), "author": entry.get("author"),
                  "acquired_utc": datetime.now(timezone.utc).isoformat(),
                  "reuse_review": entry.get("reuse_review", "required before redistribution")}
        results.append(record)
        evaluator.save(output / "catalog-results.json", {"workbooks": results})
        try:
            destination = output / "workbooks" / f"{entry['id']}.twbx"
            if download_public and entry.get("download_url"):
                record.update(download(entry, destination))
                record["acquisition"] = "tableau-public-download"
            else:
                source = (catalog_path.parent / entry["local_file"]).resolve()
                if not source.is_file():
                    raise ValueError(f"Local candidate unavailable: {source.name}")
                shutil.copyfile(source, destination)
                record["acquisition"] = "existing-local-copy; current public revision not attested"
            record["sha256"] = evaluator.digest(destination)
            assessment_dir = output / "assessments" / entry["id"]
            decision = evaluator.assess(destination, evaluator.ROOT / "capability-profile.json", assessment_dir)
            manifest = evaluator.load(assessment_dir / "inventory.json")
            record["counts"] = decision["counts"]
            record["coverage"] = coverage(manifest)
            record["assessment"] = f"assessments/{entry['id']}/assessment.json"
            evaluator.save(assessment_dir / "scenario-plan.json", scenario_plan(manifest, entry))
            if profile:
                evaluator.save(assessment_dir / "physical-profile.json", profile_package(destination))
                record["physical_profile_status"] = "completed; not business-measure parity"
            record["status"] = "completed"
        except Exception as error:
            record["status"] = "failed"
            record["error"] = str(error)
        evaluator.save(output / "catalog-results.json", {"workbooks": results})
    result = {"status": "completed" if all(item["status"] == "completed" for item in results) else "partial",
              "workbooks": results, "full_migration_certified": False}
    evaluator.save(output / "catalog-results.json", result)
    lines = ["# Public-First Benchmark Coverage", "",
             "Detected candidate is not accepted test coverage or migration parity.", "",
             "| Workbook | Status | Sheets | Public source |", "|---|---|---:|---|"]
    for item in results:
        source = f"[Public page]({item['source_page']})" if item.get("source_page") else "Local provenance; URL unverified"
        lines.append(f"| {item['title'].replace('|', '/')} | {item['status']} | {item.get('counts', {}).get('worksheets', '-')} | {source} |")
    lines.extend(["", "## Older Blocker Coverage", ""])
    for blocker, label in evaluator.BLOCKERS.items():
        lines.extend([f"### {label}", ""])
        lines.extend(f"- {item['id']}: {item.get('coverage', {}).get(blocker, 'acquisition failed')}" for item in results)
        lines.append("")
    lines.extend(["## Remaining Required Evidence", "",
                  "- Public sources cannot establish private multi-identity security parity.",
                  "- Precision boundary cases and intentional business-logic conflicts are not established by titles or datatype detection.",
                  "- Scenario plans are unapproved drafts; capture independent Tableau outputs and effective browser states.",
                  "- No Fabric model/app was created, deployed or tested in this local run.", ""])
    (output / "coverage.md").write_text("\n".join(lines), encoding="utf-8")
    evaluator.save(output / "run-status.json", {"status": result["status"], "command": "suite", "accuracy_status": "unverified"})
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=evaluator.ROOT / "workbook-catalog.json")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--download-public", action="store_true", help="Download only listed public workbook endpoints")
    parser.add_argument("--profile", action="store_true", help="Profile local Hyper extracts; does not contact Tableau/Fabric")
    parser.add_argument("--public-only", action="store_true", help="Use only candidates with verified Public download URLs")
    args = parser.parse_args(argv)
    try:
        result = run(args.catalog, args.output, args.download_public, args.profile, args.public_only)
        for item in result["workbooks"]:
            print(f"{item['id']}: {item['status']} {item.get('error', '')}")
        print(args.output / "coverage.md")
        return 0 if result["status"] == "completed" else 1
    except Exception as error:
        print(f"Benchmark failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())