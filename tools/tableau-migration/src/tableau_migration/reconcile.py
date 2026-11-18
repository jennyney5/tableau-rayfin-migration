"""Fail-closed, typed reconciliation of independently captured CSV results."""

from __future__ import annotations

import csv
import json
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path
from typing import Any

from jsonschema import validate

from .common import sha256_file

COLUMN_RULE = {
    "type": "object",
    "required": ["type"],
    "additionalProperties": False,
    "properties": {
        "type": {"enum": ["string", "integer", "decimal", "date", "datetime", "boolean"]},
        "absolute_tolerance": {"type": "string"},
        "relative_tolerance": {"type": "string"},
        "format": {"type": "string"},
    },
}
EXPORT_RULE = {
    "type": "object",
    "required": ["file", "sha256", "engine", "workbook_sha256", "worksheet", "state"],
    "additionalProperties": False,
    "properties": {
        "file": {"type": "string", "minLength": 1},
        "sha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
        "engine": {"type": "string", "minLength": 1},
        "workbook_sha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
        "worksheet": {"type": "string", "minLength": 1},
        "state": {
            "type": "object", "required": ["filters", "parameters"],
            "properties": {"filters": {"type": "object"}, "parameters": {"type": "object"}},
        },
        "delimiter": {"type": "string", "minLength": 1, "maxLength": 1},
    },
}
CONTRACT_SCHEMA = {
    "type": "object",
    "required": ["schema_version", "scenario", "keys", "columns", "baseline", "candidate"],
    "additionalProperties": False,
    "properties": {
        "schema_version": {"const": 1},
        "scenario": {"type": "string", "minLength": 1},
        "keys": {"type": "array", "uniqueItems": True, "items": {"type": "string"}},
        "columns": {"type": "object", "minProperties": 1, "additionalProperties": COLUMN_RULE},
        "baseline": EXPORT_RULE, "candidate": EXPORT_RULE,
        "null_tokens": {"type": "array", "uniqueItems": True, "items": {"type": "string"}},
        "allow_empty": {"type": "boolean"},
    },
}


def decimal_value(value: str) -> Decimal:
    try:
        result = Decimal(value)
    except InvalidOperation as error:
        raise ValueError(f"Invalid decimal value: {value!r}") from error
    if not result.is_finite():
        raise ValueError(f"Non-finite decimal value: {value!r}")
    return result


def typed_value(value: str, rule: dict[str, str], null_tokens: list[str]) -> Any:
    if value in null_tokens:
        return None
    kind = rule["type"]
    if kind == "string":
        return value
    if kind in {"integer", "decimal"}:
        if kind == "integer" and not re.fullmatch(r"[+-]?[0-9]+", value):
            raise ValueError(f"Invalid integer value: {value!r}")
        return decimal_value(value)
    if kind == "date":
        return datetime.strptime(value, rule["format"]).date() if "format" in rule else date.fromisoformat(value)
    if kind == "datetime":
        return datetime.strptime(value, rule["format"]) if "format" in rule else datetime.fromisoformat(value)
    if kind == "boolean":
        if value not in {"true", "false", "True", "False"}:
            raise ValueError(f"Invalid boolean value: {value!r}")
        return value.lower() == "true"
    raise ValueError(f"Unsupported comparison type: {kind}")


def read_export(
    path: Path, contract: dict[str, Any], export: dict[str, Any],
) -> dict[tuple[Any, ...], dict[str, Any]]:
    with path.open("rb") as stream:
        prefix = stream.read(2)
    encoding = "utf-16" if prefix in {b"\xff\xfe", b"\xfe\xff"} else "utf-8-sig"
    rows: dict[tuple[Any, ...], dict[str, Any]] = {}
    with path.open(encoding=encoding, newline="") as stream:
        reader = csv.reader(stream, delimiter=export.get("delimiter", ","), strict=True)
        header = next(reader, None)
        expected = set(contract["columns"])
        if not header or len(header) != len(set(header)) or set(header) != expected:
            raise ValueError(f"{path.name}: headers must exactly match contract columns, without duplicates")
        for line, values in enumerate(reader, 2):
            if len(values) != len(header):
                raise ValueError(f"{path.name}:{line}: unexpected column count")
            try:
                row = {
                    name: typed_value(value, contract["columns"][name], contract.get("null_tokens", []))
                    for name, value in zip(header, values, strict=True)
                }
            except ValueError as error:
                raise ValueError(f"{path.name}:{line}: {error}") from error
            key = tuple(row[name] for name in contract["keys"])
            if any(value is None for value in key):
                raise ValueError(f"{path.name}:{line}: null comparison key")
            if key in rows:
                raise ValueError(f"{path.name}:{line}: duplicate comparison key; declare the full visual grain")
            rows[key] = row
    if not rows and not contract.get("allow_empty", False):
        raise ValueError(f"{path.name}: empty export requires explicit allow_empty")
    return rows


def compare_contract(path: Path) -> dict[str, Any]:
    contract = json.loads(path.read_text(encoding="utf-8-sig"))
    validate(contract, CONTRACT_SCHEMA)
    for key in contract["keys"]:
        if key not in contract["columns"]:
            raise ValueError(f"Comparison key not declared in columns: {key}")
    for name, rule in contract["columns"].items():
        for setting in ("absolute_tolerance", "relative_tolerance"):
            tolerance = decimal_value(rule.get(setting, "0"))
            if tolerance < 0:
                raise ValueError(f"{name}: tolerances must be non-negative")
            if tolerance and (rule["type"] != "decimal" or name in contract["keys"]):
                raise ValueError(f"{name}: nonzero tolerance is allowed only on non-key decimal measures")
    baseline, candidate = contract["baseline"], contract["candidate"]
    if baseline["engine"] not in {"tableau-desktop", "tableau-server", "tableau-cloud"}:
        raise ValueError("Baseline must declare an independent Tableau engine")
    if candidate["engine"].startswith("tableau"):
        raise ValueError("Candidate must identify the recreated backend, not Tableau")
    for attribute in ("workbook_sha256", "worksheet", "state"):
        if baseline[attribute] != candidate[attribute]:
            raise ValueError(f"Baseline and candidate {attribute} differ")
    exports = [
        (path.parent / export["file"]).resolve() for export in (baseline, candidate)
    ]
    if exports[0] == exports[1]:
        raise ValueError("Baseline and candidate must be different files")
    for export_path, export in zip(exports, (baseline, candidate), strict=True):
        if sha256_file(export_path) != export["sha256"]:
            raise ValueError(f"{export_path.name}: export hash does not match the capture contract")
    left = read_export(exports[0], contract, baseline)
    right = read_export(exports[1], contract, candidate)
    differences: list[dict[str, Any]] = []
    for key in sorted(left.keys() | right.keys(), key=repr):
        if key not in left or key not in right:
            differences.append({
                "kind": "missing_candidate_row" if key not in right else "unexpected_candidate_row",
                "key": [str(value) for value in key],
            })
            continue
        for name, rule in contract["columns"].items():
            expected, actual = left[key][name], right[key][name]
            equal = expected == actual
            if rule["type"] == "decimal" and expected is not None and actual is not None:
                # Avoid rounding differences away at Decimal's default precision.
                values = [expected, actual, decimal_value(rule.get("absolute_tolerance", "0")),
                          decimal_value(rule.get("relative_tolerance", "0"))]
                precision = 32 + sum(len(v.as_tuple().digits) + abs(v.as_tuple().exponent) for v in values)
                with localcontext() as context:
                    context.prec = precision
                    delta = abs(expected - actual)
                    bound = max(values[2], values[3] * abs(expected))
                    equal = delta <= bound
            if not equal:
                differences.append({
                    "kind": "value_mismatch", "key": [str(value) for value in key],
                    "column": name,
                    "expected": None if expected is None else str(expected),
                    "actual": None if actual is None else str(actual),
                })
    return {
        "schema_version": 1, "scenario": contract["scenario"],
        "status": "passed" if not differences else "failed",
        "baseline_rows": len(left), "candidate_rows": len(right),
        "difference_count": len(differences), "differences": differences,
        "contract_sha256": sha256_file(path),
        "baseline_sha256": baseline["sha256"], "candidate_sha256": candidate["sha256"],
        "scope": "Only this exported worksheet/scenario is compared; not whole-workbook certification.",
        "provenance": "Engine and state metadata are operator-attested; file integrity is hash-verified.",
    }
