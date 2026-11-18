"""Preserve source calculation and worksheet context without claiming equivalence."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from defusedxml.ElementTree import fromstring
from jsonschema import validate

from . import __version__
from .common import check_package, sha256_file
from .expressions import calculation_features, expression_tokens

MANIFEST_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": [
        "schema_version", "tool_version", "source", "accuracy_status", "counts",
        "datasources", "fields", "worksheets", "dashboards", "actions", "issues",
    ],
    "properties": {
        "schema_version": {"const": 1},
        "accuracy_status": {"const": "unverified"},
        "source": {
            "type": "object",
            "required": ["file", "sha256", "twb_member"],
            "properties": {"sha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"}},
        },
        "fields": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "datasource", "name", "dependencies", "status"],
                "properties": {
                    "id": {"type": "string"},
                    "dependencies": {"type": "array", "items": {"type": "string"}},
                    "status": {"const": "review-required"},
                },
            },
        },
        "issues": {"type": "array"},
    },
}

ACTION_TAGS = {"action", "edit-parameter-action", "edit-group-action", "toggle-action"}
BUILTINS = {
    "Measure Names", ":Measure Names", "Measure Values", ":Measure Values",
    "Latitude (generated)", "Longitude (generated)",
}


def xml(element: ET.Element) -> str:
    return ET.tostring(element, encoding="unicode").strip()


def unbracket(name: str) -> str:
    return name[1:-1].replace("]]", "]") if name.startswith("[") and name.endswith("]") else name


def inspect_workbook(path: Path) -> dict[str, Any]:
    source_hash = sha256_file(path)
    with ZipFile(path) as archive:
        check_package(archive)
        workbook_names = [name for name in archive.namelist() if name.lower().endswith(".twb")]
        if len(workbook_names) != 1:
            raise ValueError(f"{path.name}: expected one TWB, found {len(workbook_names)}")
        workbook_name = workbook_names[0]
        root = fromstring(archive.read(workbook_name))
        members = [
            {"name": member.filename, "bytes": member.file_size, "crc32": f"{member.CRC:08x}"}
            for member in archive.infolist() if not member.is_dir()
        ]
    for element in root.iter():
        element.tag = element.tag.rsplit("}", 1)[-1]

    fields: dict[str, dict[str, Any]] = {}
    lookup: dict[tuple[str | None, str, str], str] = {}
    issues: list[dict[str, Any]] = []
    datasource_records: list[dict[str, Any]] = []
    datasources = root.findall("./datasources/datasource")
    top_calculations = 0
    parameter_count = 0

    def add_field(column: ET.Element, datasource: str, sheet: str | None = None) -> str:
        name = column.get("name")
        if not name:
            raise ValueError(f"{path.name}: column without a source name")
        global_id = lookup.get((None, datasource, unbracket(name)))
        calc = column.find("calculation")
        formula = calc.get("formula") if calc is not None else None
        if global_id is not None:
            existing = fields[global_id]
            if formula is None or existing["formula"] == formula:
                if sheet:
                    lookup[(sheet, datasource, unbracket(name))] = global_id
                return global_id
            issues.append({
                "code": "worksheet_definition_override", "worksheet": sheet,
                "datasource": datasource, "field": name,
            })
        field_id = f"{datasource}::{name}"
        if sheet:
            field_id = f"worksheet::{sheet}::{field_id}"
        if field_id in fields:
            raise ValueError(f"Duplicate field definition: {field_id}")
        references: list[tuple[str, ...]] = []
        features: list[str] = []
        if formula is not None:
            try:
                references, _ = expression_tokens(formula)
                features = calculation_features(formula)
            except ValueError as error:
                issues.append({"code": "expression_parse_required", "field": field_id, "message": str(error)})
        fields[field_id] = {
            "id": field_id, "datasource": datasource, "worksheet_scope": sheet,
            "name": name, "caption": column.get("caption", name),
            "datatype": column.get("datatype"), "role": column.get("role"),
            "attributes": dict(column.attrib), "formula": formula,
            "definition_xml": xml(column), "features": features,
            "references": [list(ref) for ref in references],
            "dependencies": [], "unresolved_references": [],
            "status": "review-required", "required_by_worksheets": [],
        }
        lookup[(sheet, datasource, unbracket(name))] = field_id
        return field_id

    for datasource in datasources:
        name = datasource.get("name")
        if not name:
            raise ValueError("Datasource without a name")
        is_parameter = name == "Parameters"
        for column in datasource.findall("./column"):
            add_field(column, name)
            parameter_count += int(is_parameter)
            top_calculations += int(not is_parameter and column.find("calculation") is not None)
        metadata = datasource.findall(".//metadata-record[@class='column']")
        for record in metadata:
            local_name = record.findtext("local-name")
            if local_name and (None, name, unbracket(local_name)) not in lookup:
                # Tableau may omit default raw-field declarations from direct columns.
                column = ET.Element("column", {"name": local_name})
                datatype = record.findtext("local-type")
                if datatype:
                    column.set("datatype", datatype)
                field_id = add_field(column, name)
                fields[field_id]["definition_xml"] = xml(record)
                fields[field_id]["definition_origin"] = "connection-metadata"
        datasource_records.append({
            "name": name, "caption": datasource.get("caption", name),
            "is_parameter": is_parameter,
            "connection_classes": sorted({c.get("class", "") for c in datasource.iter("connection")}),
            "relation_xml": [xml(e) for e in datasource.findall("./connection/relation")],
            "relationship_xml": [xml(e) for e in datasource.findall(".//relationships")],
            "filter_xml": [xml(e) for e in datasource.findall("./filter")],
            "group_xml": [xml(e) for e in datasource.findall("./group")],
            "column_instance_xml": [xml(e) for e in datasource.findall("./column-instance")],
            "drill_paths_xml": [xml(e) for e in datasource.findall("./drill-paths")],
            "aliases_xml": [xml(e) for e in datasource.findall("./aliases")],
            "column_mapping_xml": [xml(e) for e in metadata],
            "object_graph_xml": [xml(e) for e in datasource.findall("./object-graph")],
        })

    sheet_nodes = root.findall("./worksheets/worksheet")
    global_instances = {
        (datasource.get("name", ""), unbracket(instance.get("name", ""))): instance
        for datasource in datasources for instance in datasource.findall("./column-instance")
    }
    sheet_instances: dict[str, dict[tuple[str, str], ET.Element]] = {}
    for sheet in sheet_nodes:
        name = sheet.get("name", "")
        aliases: dict[tuple[str, str], ET.Element] = {}
        for block in sheet.findall(".//datasource-dependencies"):
            datasource = block.get("datasource", "")
            for column in block.findall("./column"):
                add_field(column, datasource, name)
            for instance in block.findall("./column-instance"):
                aliases[(datasource, unbracket(instance.get("name", "")))] = instance
        sheet_instances[name] = aliases

    def resolve(ref: tuple[str, ...], datasource: str, sheet: str | None) -> str | None:
        if len(ref) == 1:
            source, field = datasource, ref[0]
        elif len(ref) == 2:
            source, field = ref
        else:
            return None
        aliases = sheet_instances.get(sheet or "", {})
        instance = aliases.get((source, field))
        if instance is None:
            instance = global_instances.get((source, field))
        if instance is not None:
            field = unbracket(instance.get("column", ""))
        return lookup.get((sheet, source, field)) or lookup.get((None, source, field))

    for record in fields.values():
        for raw_ref in record["references"]:
            ref = tuple(raw_ref)
            dependency = resolve(ref, record["datasource"], record["worksheet_scope"])
            if dependency is None:
                record["unresolved_references"].append(raw_ref)
            elif dependency not in record["dependencies"]:
                record["dependencies"].append(dependency)
        if record["unresolved_references"]:
            issues.append({
                "code": "unresolved_field_references", "field": record["id"],
                "references": record["unresolved_references"],
            })

    worksheets: list[dict[str, Any]] = []
    for sheet in sheet_nodes:
        name = sheet.get("name", "")
        sheet_sources = {
            e.get("datasource", "") for e in sheet.findall(".//datasource-dependencies")
        }
        roots: set[str] = set()
        unknowns: set[tuple[str, ...]] = set()

        def find_uses(element: ET.Element) -> None:
            if element.tag == "datasource-dependencies":
                return
            values = list(element.attrib.values())
            if element.text and element.text.strip():
                values.append(element.text)
            for value in values:
                if "[" not in value:
                    continue
                try:
                    refs, _ = expression_tokens(value)
                except ValueError:
                    # Labels/format strings are not necessarily Tableau expressions.
                    continue
                for ref in refs:
                    matches = {
                        match for source in sheet_sources
                        if (match := resolve(ref, source, name)) is not None
                    }
                    if matches:
                        roots.update(matches)
                        if len(matches) > 1:
                            issues.append({"code": "ambiguous_sheet_reference", "worksheet": name, "reference": list(ref)})
                    elif ref[-1] not in BUILTINS:
                        unknowns.add(ref)
            for child in element:
                find_uses(child)

        find_uses(sheet)
        for datasource in datasources:
            if datasource.get("name") in sheet_sources:
                for source_filter in datasource.findall("./filter"):
                    find_uses(source_filter)
        # Instance-specific window ordering can reference further required fields.
        for (datasource, _), instance in sheet_instances[name].items():
            resolved = resolve((unbracket(instance.get("column", "")),), datasource, name)
            if resolved not in roots:
                continue
            for calc in instance.findall(".//table-calc"):
                for value in [*calc.attrib.values(), *(v for e in calc.iter() for v in e.attrib.values())]:
                    if "[" not in value:
                        continue
                    try:
                        refs, _ = expression_tokens(value)
                    except ValueError as error:
                        issues.append({"code": "table_calc_reference_parse_required", "worksheet": name, "message": str(error)})
                        continue
                    for ref in refs:
                        match = resolve(ref, datasource, name)
                        if match:
                            roots.add(match)
                        elif ref[-1] not in BUILTINS:
                            unknowns.add(ref)
        pending = list(roots)
        reachable: set[str] = set()
        while pending:
            field_id = pending.pop()
            if field_id in reachable:
                continue
            reachable.add(field_id)
            pending.extend(fields[field_id]["dependencies"])
        for field_id in sorted(reachable):
            fields[field_id]["required_by_worksheets"].append(name)
        if unknowns:
            issues.append({"code": "unresolved_sheet_references", "worksheet": name, "references": [list(ref) for ref in sorted(unknowns)]})
        worksheets.append({
            "name": name,
            "datasources": sorted(sheet_sources),
            "root_fields": sorted(roots), "required_fields": sorted(reachable),
            "unresolved_references": [list(ref) for ref in sorted(unknowns)],
            "marks": sorted({e.get("class", "") for e in sheet.findall(".//mark")}),
            "table_calculations": [xml(e) for e in sheet.findall(".//table-calc")],
            "filters": [xml(e) for e in sheet.findall(".//filter")],
            "rows": [e.text or "" for e in sheet.findall(".//rows")],
            "cols": [e.text or "" for e in sheet.findall(".//cols")],
            "source_context_xml": xml(sheet),
            "status": "review-required",
        })

    dashboards = []
    member_names = {m["name"].replace("\\", "/") for m in members}
    for dashboard in root.findall("./dashboards/dashboard"):
        dashboards.append({
            "name": dashboard.get("name"), "is_story": dashboard.get("type") == "storyboard",
            "size": [dict(e.attrib) for e in dashboard.findall("./size")],
            "worksheets": sorted({
                e.get("name") for e in dashboard.iter("zone")
                if e.get("name") in {s["name"] for s in worksheets}
            }),
            "source_layout_xml": xml(dashboard),
        })
        for zone in dashboard.iter("zone"):
            if zone.get("type-v2", zone.get("type")) == "bitmap":
                asset = (zone.get("param") or "").replace("\\", "/")
                if asset and asset not in member_names:
                    issue = {"code": "missing_asset", "asset": asset}
                    if issue not in issues:
                        issues.append(issue)

    actions = [{"type": e.tag, "source_xml": xml(e)} for e in root.iter() if e.tag in ACTION_TAGS]
    for record in fields.values():
        if record["formula"] is not None and not record["required_by_worksheets"]:
            issues.append({"code": "reachability_review_required", "field": record["id"]})
    counts = {
        "worksheets": len(worksheets),
        "dashboards": sum(not d["is_story"] for d in dashboards),
        "stories": sum(d["is_story"] for d in dashboards),
        "datasources": sum(not d["is_parameter"] for d in datasource_records),
        "hyper_files": sum(m["name"].lower().endswith(".hyper") for m in members),
        "calculated_fields": top_calculations, "parameters": parameter_count,
        "worksheet_local_calculations": sum(
            r["worksheet_scope"] is not None and r["formula"] is not None for r in fields.values()
        ),
        "conventional_actions": sum(a["type"] == "action" for a in actions),
    }
    manifest = {
        "schema_version": 1, "tool_version": __version__,
        "accuracy_status": "unverified",
        "source": {"file": path.name, "sha256": source_hash, "twb_member": workbook_name},
        "counts": counts, "members": members, "datasources": datasource_records,
        "fields": list(fields.values()), "worksheets": worksheets,
        "dashboards": dashboards, "actions": actions,
        "issues": issues,
        "limitations": [
            "Identifier discovery is conservative, not a complete Tableau grammar or formula evaluator.",
            "No field is certified unused or equivalent; every calculation needs reviewed mapping and source-result evidence.",
            "Source XML is retained for audit of unsupported and implicit behavior.",
        ],
    }
    validate(manifest, MANIFEST_SCHEMA)
    if sha256_file(path) != source_hash:
        raise ValueError(f"{path.name}: source changed while inventorying")
    return manifest


def readiness_report(manifests: list[dict[str, Any]], profiles: list[dict[str, Any]]) -> str:
    lines = [
        "# Tableau accuracy readiness",
        "",
        "**Not numerically certified.** Inventory and extract statistics are not Tableau-engine result parity.",
        "",
        "| Workbook | Sheets | Dashboards | Stories | Calculations | Parameters | Hyper tables | Rows (physical, not business grain) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    by_hash = {p["source_sha256"]: p for p in profiles}
    for manifest in manifests:
        counts = manifest["counts"]
        profile = by_hash.get(manifest["source"]["sha256"])
        tables = [t for e in profile["extracts"] for t in e["tables"]] if profile else []
        rows = str(sum(t["row_count"] for t in tables)) if profile else "not profiled"
        name = manifest["source"]["file"].replace("|", "\\|")
        lines.append(
            f"| {name} | {counts['worksheets']} | {counts['dashboards']} | {counts['stories']} | "
            f"{counts['calculated_fields']} | {counts['parameters']} | {len(tables) if profile else '-'} | {rows} |"
        )
    lines.extend(["", "## Review queue", ""])
    for manifest in manifests:
        features: Counter[str] = Counter()
        for record in manifest["fields"]:
            if record["formula"] is not None and record["datasource"] != "Parameters":
                features.update(record["features"])
        issues = Counter(issue["code"] for issue in manifest["issues"])
        lines.extend([
            f"### {manifest['source']['file']}", "",
            f"- Features (definitions, including worksheet-local): {dict(features)}",
            f"- Review findings: {dict(issues)}",
            "- Pending: independently exported Tableau results, approved target mappings, and scenario comparisons.",
            "",
        ])
    lines.extend([
        "## Accuracy gates", "",
        "1. Open the exact packaged workbook in Tableau Desktop; record filters and parameter state.",
        "2. Export unformatted worksheet data at its actual displayed grain, including totals separately where needed.",
        "3. Hash the workbook and both CSV exports; declare keys, types, null tokens, tolerances, and identical scenario metadata.",
        "4. Run `tableau-migration compare` against the recreated backend result.",
        "5. Resolve every mismatch, missing row, duplicate key, unresolved reference, and implicit table calculation before accepting the view.",
        "",
        "Summing rows across physical extract tables does not establish a shared fact grain or validate joins.",
        "Outputs may contain source formulas and aggregate data; keep them under the same access controls as the original packages.",
        "",
    ])
    return "\n".join(lines)
