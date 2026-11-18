"""Read-only, worksheet-specific Tableau Cloud/Server reference captures."""

from __future__ import annotations

import argparse
import csv
import getpass
import io
import json
import logging
import os
import re
import sys
from collections import Counter
from contextlib import closing
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
from pathlib import Path
from urllib.parse import unquote, unquote_plus, urlsplit
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile

import keyring
import tableauserverclient as TSC
from defusedxml.common import DefusedXmlException
from keyring.errors import KeyringError
from requests.exceptions import RequestException

from .common import sha256_file, write_json
from .inventory import inspect_workbook

LOGGER = logging.getLogger("tableau_migration")
CONFIG_KEYS = {
    "schema_version", "workbook_url", "source_package", "source_workbook_sha256",
    "token_name", "scenarios", "worksheets", "parent_views",
}


def target(url: str) -> tuple[str, str, str]:
    if not isinstance(url, str):
        raise ValueError("workbook_url must be a Tableau Cloud/Server URL string")
    parts = urlsplit(url)
    if (
        parts.scheme != "https" or not parts.hostname or parts.username or parts.password
        or parts.query or parts.path not in {"", "/"} or parts.port not in {None, 443}
        or parts.hostname.lower() == "public.tableau.com"
    ):
        raise ValueError("Use an HTTPS Tableau Cloud/Server site workbook URL, not Tableau Public")
    match = re.fullmatch(r"/site/([^/]+)/views/([^/]+)/[^/?]+(?:\?.*)?", parts.fragment)
    if not match:
        raise ValueError("Expected a workbook URL containing #/site/<site>/views/<workbook>/<view>")
    return f"https://{parts.netloc.lower()}", unquote(match[1]), unquote(match[2])


def load_config(path: Path) -> dict:
    config = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(config, dict) or set(config) - CONFIG_KEYS:
        raise ValueError("Unknown configuration fields; never put tokens or passwords in this file")
    if config.get("schema_version") != 1:
        raise ValueError("Expected export configuration schema_version 1")
    target(config["workbook_url"])
    if not isinstance(config.get("token_name"), str) or not config["token_name"].strip():
        raise ValueError("Set token_name to the PAT name, never its secret")
    source_hash = config.get("source_workbook_sha256")
    if not isinstance(source_hash, str) or not re.fullmatch(r"[a-f0-9]{64}", source_hash):
        raise ValueError("Set source_workbook_sha256 to the approved package SHA256")
    if not isinstance(config.get("source_package"), str):
        raise ValueError("Set source_package to the original TWBX")
    scenarios = config.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError("At least one explicit scenario is required")
    ids = set()
    for scenario in scenarios:
        if not isinstance(scenario, dict) or set(scenario) - {
            "id", "filters", "parameters", "allow_empty", "language",
        }:
            raise ValueError("Unknown scenario fields; actions require a separate interactive capture")
        name = scenario.get("id")
        if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,79}", name):
            raise ValueError("Scenario IDs must be short lowercase slugs")
        if name in ids:
            raise ValueError("Duplicate scenario ID")
        ids.add(name)
        if not isinstance(scenario.get("allow_empty", False), bool):
            raise ValueError("allow_empty must be a boolean")
        if "language" in scenario and (
            not isinstance(scenario["language"], str)
            or not re.fullmatch(r"[a-z]{2}", scenario["language"])
        ):
            raise ValueError("language must be a two-letter Tableau language code")
        for field in ("filters", "parameters"):
            values = scenario.get(field)
            if not isinstance(values, dict) or not all(
                isinstance(k, str) and k.strip() and isinstance(v, str) and v
                for k, v in values.items()
            ):
                raise ValueError("Each scenario needs explicit string-valued filters and parameters objects")
    if "worksheets" in config and (
        not isinstance(config["worksheets"], list) or not config["worksheets"]
        or not all(isinstance(s, str) and s for s in config["worksheets"])
        or len(set(config["worksheets"])) != len(config["worksheets"])
    ):
        raise ValueError("worksheets must be a nonempty, unique list of source worksheet names")
    if "parent_views" in config and (
        not isinstance(config["parent_views"], list) or not config["parent_views"]
        or not all(isinstance(s, str) and s for s in config["parent_views"])
        or len(set(config["parent_views"])) != len(config["parent_views"])
    ):
        raise ValueError("parent_views must be a nonempty, unique list of exact published view names")
    return config


def credential_service(config: dict) -> str:
    server, site, _ = target(config["workbook_url"])
    return f"tableau-rayfin:{server}/site/{site}"


def windows_vault():
    backend = keyring.get_keyring()
    if os.name != "nt" or type(backend).__module__ != "keyring.backends.Windows":
        raise ValueError("Windows Credential Manager is required; CI must inject TABLEAU_TOKEN_SECRET instead")
    return backend


def configure(config: dict) -> None:
    if not sys.stdin.isatty():
        raise ValueError("Run configure in your own interactive terminal; never paste secrets into chat")
    backend = windows_vault()
    secret = getpass.getpass(f"Secret for Tableau PAT '{config['token_name']}' (hidden): ")
    if not secret.strip():
        raise ValueError("Token secret cannot be empty")
    backend.set_password(credential_service(config), config["token_name"], secret)


def credentials(config: dict) -> tuple[str, str]:
    name = os.environ.get("TABLEAU_TOKEN_NAME")
    secret = os.environ.get("TABLEAU_TOKEN_SECRET")
    if name is not None or secret is not None:
        if not name or not secret or name != config["token_name"]:
            raise ValueError("Set both Tableau token environment variables; name must match configuration")
    else:
        name = config["token_name"]
        secret = windows_vault().get_password(credential_service(config), name)
    if not secret or not secret.strip():
        raise ValueError("No stored PAT. Run the configure command in your terminal first")
    return name, secret


def csv_metadata(path: Path, allow_empty: bool, *, named_empty_part: bool = False) -> dict:
    raw = path.read_bytes()
    encoding = "utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
    text = raw.decode(encoding)
    if allow_empty and named_empty_part and text in ("\n", "\r\n"):
        return {
            "sha256": sha256_file(path), "bytes": len(raw), "encoding": encoding,
            "delimiter": ",", "headers": [], "data_rows": 0,
            "duplicate_headers": [], "contract_mapping_required": True,
            "headerless_empty": True,
        }
    if not text.strip() or text.lstrip().startswith("<"):
        raise ValueError("Export is empty or an HTML/XML/JSON response, not worksheet CSV")
    try:
        json.loads(text)
    except ValueError:
        pass
    else:
        raise ValueError("Export is a JSON response, not worksheet CSV")
    # Query View Data emits CSV, not the TSV produced by the manual crosstab UI.
    rows = csv.reader(io.StringIO(text, newline=""), delimiter=",", strict=True)
    headers = next(rows)
    if not headers or not all(headers):
        raise ValueError("Export has missing CSV headers; inspect the raw response")
    count = 0
    for row in rows:
        if len(row) != len(headers):
            raise ValueError("Export row width differs from its CSV headers")
        count += 1
    if not count and not allow_empty:
        raise ValueError("Unexpected empty worksheet; allow_empty must be explicit for this scenario")
    return {
        "sha256": sha256_file(path), "bytes": len(raw), "encoding": encoding,
        "delimiter": ",", "headers": headers, "data_rows": count,
        "duplicate_headers": [name for name, count in Counter(headers).items() if count > 1],
        "contract_mapping_required": len(set(headers)) != len(headers),
    }


def multipart_sheets(raw: bytes, content_type: str) -> list[dict]:
    boundary_match = re.search(r'(?:^|;)\s*boundary=(?:"([^"]+)"|([^;\s]+))', content_type, re.I)
    if not content_type.lower().startswith("multipart/") or not boundary_match:
        raise ValueError("allData response has no multipart boundary")
    boundary = boundary_match[1] or boundary_match[2]
    if not re.fullmatch(r"[a-zA-Z0-9'()+_,./:=?-]{1,200}", boundary):
        raise ValueError("allData response has an invalid multipart boundary")
    # Tableau can emit an unquoted '=' in its boundary. Quote it for MIME parsing.
    prefix = f'Content-Type: multipart/mixed; boundary="{boundary}"\r\nMIME-Version: 1.0\r\n\r\n'
    message = BytesParser(policy=policy.default).parsebytes(prefix.encode("ascii") + raw)
    if not message.is_multipart() or message.defects:
        raise ValueError("Malformed/truncated allData multipart response")
    result = []
    seen = set()
    for part in message.iter_parts():
        name = str(part.get("X-Tableau-Sheet-Name", ""))
        if part.is_multipart() or part.defects or not name or name in seen:
            raise ValueError("Malformed or ambiguous allData worksheet part")
        seen.add(name)
        body = part.get_payload(decode=True)
        if not isinstance(body, bytes):
            raise ValueError("allData worksheet part has no byte payload")
        error = part.get("X-Tableau-Sheet-Error-Code")
        status = str(part.get("X-Tableau-Sheet-Status", ""))
        if not error and (not status.isdigit() or not 200 <= int(status) < 300):
            raise ValueError("allData worksheet part has no successful status or explicit error code")
        declared_length = part.get("Content-Length")
        if declared_length is not None and (
            not str(declared_length).isdigit() or int(str(declared_length)) != len(body)
        ):
            raise ValueError("allData worksheet byte length differs from its declared Content-Length")
        if not error and part.get_content_type() != "text/csv":
            raise ValueError("Successful allData worksheet is not CSV")
        result.append({
            "worksheet": name, "body": body, "error_code": str(error) if error else None,
            "error_detail": unquote_plus(str(part.get("X-Tableau-Sheet-Error-Detail", ""))),
        })
    if not result:
        raise ValueError("allData returned no worksheet parts")
    return result


def capture_all_data(server, views: list, config: dict, output: Path, report: dict) -> None:
    report["capture_route"] = "Tableau REST 3.30+ allData; explicit per-worksheet multipart parts"
    report["raw_responses"] = []
    expected = set(report["expected_worksheets"])
    covered = set()
    for view_index, view in enumerate(views, 1):
        if view.sheet_type not in {"dashboard", "worksheet", "story"}:
            continue
        for scenario in config["scenarios"]:
            raw_path = output / f"view-{view_index:03d}-{scenario['id']}.multipart"
            with closing(server.views.get_request(
                f"{server.views.baseurl}/{view.id}/allData",
                request_object=export_options(scenario), parameters={"stream": True},
            )) as response:
                content_type = response.headers.get("Content-Type", "")
                total = 0
                with raw_path.open("xb") as stream:
                    for chunk in response.iter_content(64 * 1024):
                        total += len(chunk)
                        if total > 256 * 1024 * 1024:
                            raise ValueError("allData response exceeds the reviewed 256 MiB capture limit")
                        stream.write(chunk)
            parts = multipart_sheets(raw_path.read_bytes(), content_type)
            report["raw_responses"].append({
                "file": raw_path.name, "sha256": sha256_file(raw_path),
                "content_type": content_type, "bytes": total, "view_id": view.id,
                "view_name": view.name, "scenario": scenario["id"],
                "returned_worksheets": [part["worksheet"] for part in parts],
            })
            for index, part in enumerate(parts, 1):
                worksheet = part["worksheet"]
                if part["error_code"]:
                    report["export_errors"].append({
                        "worksheet": worksheet, "scenario": scenario["id"], "view_id": view.id,
                        "code": part["error_code"], "message": part["error_detail"],
                    })
                    if part["error_code"].startswith(("401", "403")):
                        raise ValueError("allData worksheet permission/authentication failure; capture stopped")
                    continue
                destination = output / f"view-{view_index:03d}-{scenario['id']}-sheet-{index:03d}.csv"
                with destination.open("xb") as stream:
                    stream.write(part["body"])
                try:
                    metadata = csv_metadata(
                        destination, scenario.get("allow_empty", False), named_empty_part=True,
                    )
                except (ValueError, UnicodeError, csv.Error) as error:
                    report["export_errors"].append({
                        "worksheet": worksheet, "scenario": scenario["id"],
                        "view_id": view.id, "error_type": type(error).__name__, "message": str(error),
                    })
                    continue
                report["exports"].append({
                    "worksheet": worksheet, "scenario": scenario["id"], "view_id": view.id,
                    "parent_view": view.name, "requested_state": scenario,
                    "file": destination.name, "requested_worksheet": worksheet in expected,
                    **metadata, "captured_at_utc": datetime.now(timezone.utc).isoformat(),
                })
                if worksheet in expected:
                    covered.add((worksheet, scenario["id"]))
            write_json(output / "capture-status.json", report)
    report["missing_worksheets"] = [
        {"worksheet": worksheet, "scenarios": [
            s["id"] for s in config["scenarios"] if (worksheet, s["id"]) not in covered
        ], "reason": "No successful explicit worksheet part in these scenarios"}
        for worksheet in report["expected_worksheets"]
        if any((worksheet, s["id"]) not in covered for s in config["scenarios"])
    ]


def timestamp(value) -> str | None:
    return value.isoformat() if value is not None else None


def export_options(scenario: dict):
    # The REST cache minimum is one minute; this does not refresh the extract.
    options = TSC.CSVRequestOptions(maxage=1)
    for name, value in scenario["filters"].items():
        options.vf(name, value)
    for name, value in scenario["parameters"].items():
        options.parameter(name, value)
    if "language" in scenario:
        options.language = scenario["language"]
    return options


def capture(config_path: Path, output: Path) -> dict:
    config = load_config(config_path)
    package = (config_path.parent / config["source_package"]).resolve()
    if not package.is_file() or sha256_file(package) != config["source_workbook_sha256"]:
        raise ValueError("Original source package is missing or its SHA256 changed")
    manifest = inspect_workbook(package)
    all_names = [sheet["name"] for sheet in manifest["worksheets"]]
    names = config.get("worksheets", all_names)
    if not names or set(names) - set(all_names):
        raise ValueError("Requested worksheet is absent from the source package")
    output.mkdir(parents=True, exist_ok=False)
    report = {
        "schema_version": 1, "status": "incomplete",
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "workbook_url": config["workbook_url"],
        "source_package_sha256": manifest["source"]["sha256"],
        "source_identity": "local hash verified; published-copy identity remains operator-attested",
        "expected_worksheets": names, "source_worksheet_count": len(all_names),
        "scenarios": config["scenarios"], "exports": [], "missing_worksheets": [],
        "export_errors": [], "full_migration_certified": False,
        "state_verification": "Requested REST filters/parameters, not observed interactive state.",
        "precision": "CSV export precision only; not guaranteed full-precision Tableau values.",
        "limits": [
            "Worksheet parts are identified explicitly; legacy first-dashboard-sheet CSVs are never substituted.",
            "REST view filters are not proof of dashboard action/context-filter semantics.",
            "Workbook revision checks do not prove external/live sources stayed unchanged.",
            "No Tableau refresh, publish, visibility or permission changes are performed.",
            "Returned schema/grain must be reviewed before using the existing compare contracts.",
        ],
    }
    status_path = output / "capture-status.json"
    write_json(status_path, report)
    name, secret = credentials(config)
    server_url, site, content_url = target(config["workbook_url"])
    server = TSC.Server(server_url, use_server_version=True, http_options={"timeout": 120})
    auth = TSC.PersonalAccessTokenAuth(name, secret, site_id=site)
    with server.auth.sign_in(auth):
        workbooks = [w for w in TSC.Pager(server.workbooks) if w.content_url == content_url]
        if len(workbooks) != 1:
            raise ValueError("Published workbook content URL is missing or ambiguous; no name fallback used")
        workbook = server.workbooks.get_by_id(workbooks[0].id)
        if workbook.updated_at is None:
            raise ValueError("Server returned no workbook revision timestamp")
        report["published_workbook"] = {
            "id": workbook.id, "name": workbook.name, "content_url": workbook.content_url,
            "updated_at": timestamp(workbook.updated_at), "site_id": server.site_id,
            "api_version": server.version,
        }
        # Pager covers all published views, including sites with >100 views.
        view_options = TSC.RequestOptions(pagesize=1000)
        view_options.all_fields = True
        views = [
            v for v in TSC.Pager(server.views, view_options)
            if v.workbook_id == workbook.id
        ]
        report["available_views"] = [
            {"id": v.id, "name": v.name, "sheet_type": v.sheet_type, "content_url": v.content_url}
            for v in views
        ]
        write_json(status_path, report)
        modern = server.check_at_least_version("3.30")
        if "parent_views" in config:
            if not modern:
                raise ValueError("Explicit parent_views requires REST 3.30+ allData")
            selected = []
            for parent in config["parent_views"]:
                matches = [v for v in views if v.name == parent]
                if len(matches) != 1:
                    raise ValueError(f"Parent view missing or ambiguous: {parent}")
                selected.extend(matches)
            views = selected
            report["selected_parent_views"] = config["parent_views"]
        if modern:
            capture_all_data(server, views, config, output, report)
        else:
            report["capture_route"] = "Legacy Query View Data for individually exposed worksheets"
        for worksheet in ([] if modern else names):
            matches = [v for v in views if v.name == worksheet]
            if len(matches) != 1 or matches[0].sheet_type != "worksheet":
                report["missing_worksheets"].append({
                    "worksheet": worksheet,
                    "reason": "Not exposed as exactly one REST worksheet; no dashboard fallback.",
                })
                write_json(status_path, report)
                continue
            view = matches[0]
            for scenario in config["scenarios"]:
                # Numeric filenames avoid collisions and unsafe source sheet names.
                destination = output / f"{names.index(worksheet) + 1:03d}-{scenario['id']}.csv"
                try:
                    server.views.populate_csv(view, export_options(scenario))
                    with destination.open("xb") as stream:
                        for chunk in view.csv:
                            stream.write(chunk)
                    metadata = csv_metadata(destination, scenario.get("allow_empty", False))
                    report["exports"].append({
                        "worksheet": worksheet, "scenario": scenario["id"], "view_id": view.id,
                        "requested_state": scenario, "file": destination.name, **metadata,
                        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
                    })
                except TSC.ServerResponseError as error:
                    if error.code.startswith(("401", "403")):
                        raise
                    report["export_errors"].append({
                        "worksheet": worksheet, "scenario": scenario["id"],
                        "error_type": type(error).__name__, "code": error.code,
                    })
                except (ValueError, UnicodeError, csv.Error) as error:
                    report["export_errors"].append({
                        "worksheet": worksheet, "scenario": scenario["id"],
                        "error_type": type(error).__name__, "message": str(error),
                    })
                write_json(status_path, report)
        after = server.workbooks.get_by_id(workbook.id)
        if after.updated_at != workbook.updated_at:
            raise ValueError("Published workbook changed during capture; reject this run")
    if sha256_file(package) != config["source_workbook_sha256"]:
        raise ValueError("Local source package changed during capture; reject this run")
    report["status"] = "partial" if report["missing_worksheets"] or report["export_errors"] else "completed"
    report["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
    report["captured_count"] = len({
        (row["worksheet"], row["scenario"]) for row in report["exports"]
        if row["worksheet"] in names
    })
    report["exported_csv_count"] = len(report["exports"])
    report["expected_count"] = len(names) * len(config["scenarios"])
    write_json(status_path, report)
    return report


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    setup = commands.add_parser("configure", help="Store a PAT in Windows Credential Manager")
    setup.add_argument("--config", type=Path, required=True)
    run = commands.add_parser("capture", help="Export read-only reference CSVs into a NEW directory")
    run.add_argument("--config", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "configure":
            configure(load_config(args.config))
            print("PAT saved in Windows Credential Manager; no secret written to the workspace.")
            return 0
        report = capture(args.config, args.output)
        print(json.dumps({
            "status": report["status"], "captured": report["captured_count"],
            "expected": report["expected_count"], "missing_worksheets": len(report["missing_worksheets"]),
            "export_errors": len(report["export_errors"]), "full_migration_certified": False,
        }))
        return 0 if report["status"] == "completed" else 1
    except TSC.ServerResponseError as error:
        LOGGER.error("Tableau REST error %s. Check PAT/site/export permissions; no retry or permission changes.", error.code)
        return 2
    except (RequestException, TSC.NotSignedInError, KeyringError) as error:
        # SDK/HTTP exception strings may include sensitive request details.
        LOGGER.error("%s: check secure credentials, Tableau availability and TLS; no automatic retry.", type(error).__name__)
        return 2
    except (OSError, ValueError, KeyError, csv.Error, BadZipFile, ParseError, DefusedXmlException) as error:
        LOGGER.error("%s", error)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
