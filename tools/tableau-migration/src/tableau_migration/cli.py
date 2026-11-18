"""Command-line entry point; invalid inputs and mismatches never exit successfully."""

from __future__ import annotations

import argparse
import csv
import json
import logging
from pathlib import Path
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile

from defusedxml.common import DefusedXmlException
from jsonschema import ValidationError
from tableauhyperapi import HyperException

from .common import write_json
from .inventory import MANIFEST_SCHEMA, inspect_workbook, readiness_report
from .profile import profile_package
from .reconcile import compare_contract

LOGGER = logging.getLogger("tableau_migration")


def safe_stem(path: Path) -> str:
    import hashlib
    import re

    stem = re.sub(r"[^a-z0-9]+", "-", path.stem.lower()).strip("-")[:75]
    suffix = hashlib.sha256(path.name.encode("utf-8")).hexdigest()[:10]
    return f"{stem}-{suffix}"


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("inventory", "profile", "audit"):
        sub = commands.add_parser(command)
        sub.add_argument("--input", type=Path, default=Path.cwd(), help="TWBX file or directory (nonrecursive)")
        sub.add_argument("--output", type=Path, default=Path("migration") / "output")
    compare = commands.add_parser("compare")
    compare.add_argument("--contract", type=Path, required=True)
    compare.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "compare":
            if args.output.resolve() == args.contract.resolve():
                raise ValueError("Report output must not overwrite the capture contract")
            result = compare_contract(args.contract)
            # Never overwrite the evidence CSVs with a report.
            contract = json.loads(args.contract.read_text(encoding="utf-8-sig"))
            for export in (contract["baseline"], contract["candidate"]):
                if args.output.resolve() == (args.contract.parent / export["file"]).resolve():
                    raise ValueError("Report output must not overwrite an evidence export")
            write_json(args.output, result)
            LOGGER.info("%s: %s (%d differences)", args.command, result["status"], result["difference_count"])
            return 0 if result["status"] == "passed" else 1
        write_json(args.output / "run-status.json", {
            "status": "incomplete", "command": args.command,
            "input": str(args.input.resolve()),
            "message": "Do not consume reports unless this run finishes successfully.",
        })
        packages = (
            sorted(args.input.glob("*.twbx"), key=lambda p: p.name.casefold())
            if args.input.is_dir() else [args.input]
        )
        if not packages:
            raise ValueError("No TWBX packages found")
        manifests, profiles = [], []
        for package in packages:
            if package.suffix.lower() != ".twbx":
                raise ValueError(f"Expected a TWBX package: {package}")
            if args.command in {"inventory", "audit"}:
                manifest = inspect_workbook(package)
                manifests.append(manifest)
                write_json(args.output / "manifests" / f"{safe_stem(package)}.json", manifest)
            if args.command in {"profile", "audit"}:
                profile = profile_package(package)
                profiles.append(profile)
                write_json(args.output / "profiles" / f"{safe_stem(package)}.json", profile)
            LOGGER.info("%s: processed %s", args.command, package.name)
        if manifests:
            write_json(args.output / "manifest.schema.json", MANIFEST_SCHEMA)
            report = args.output / "accuracy-readiness.md"
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(readiness_report(manifests, profiles), encoding="utf-8")
            write_json(args.output / "summary.json", {
                "workbooks": len(manifests), "accuracy_status": "unverified",
                "counts": {
                    key: sum(m["counts"][key] for m in manifests)
                    for key in manifests[0]["counts"]
                },
                "issues": sum(len(m["issues"]) for m in manifests),
            })
        write_json(args.output / "run-status.json", {
            "status": "completed", "command": args.command,
            "accuracy_status": "unverified",
            "processed_files": [package.name for package in packages],
        })
        return 0
    except (OSError, ValueError, csv.Error, BadZipFile, ParseError, DefusedXmlException, ValidationError, HyperException) as error:
        LOGGER.error("%s", error)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
