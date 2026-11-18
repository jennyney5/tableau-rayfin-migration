"""Read-only aggregate profiling of every user table in packaged Hyper files."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from zipfile import ZipFile

from tableauhyperapi import Connection, CreateMode, HyperProcess, Telemetry, TypeTag

from . import __version__
from .common import check_package, copy_member, sha256_file

COMPARABLE = {
    TypeTag.BOOL, TypeTag.BIG_INT, TypeTag.SMALL_INT, TypeTag.INT,
    TypeTag.NUMERIC, TypeTag.FLOAT, TypeTag.DOUBLE, TypeTag.OID,
    TypeTag.TEXT, TypeTag.VARCHAR, TypeTag.CHAR, TypeTag.DATE,
    TypeTag.TIME, TypeTag.TIMESTAMP, TypeTag.TIMESTAMP_TZ,
}
RANGED = {
    TypeTag.BIG_INT, TypeTag.SMALL_INT, TypeTag.INT, TypeTag.NUMERIC,
    TypeTag.FLOAT, TypeTag.DOUBLE, TypeTag.OID, TypeTag.DATE,
    TypeTag.TIME, TypeTag.TIMESTAMP, TypeTag.TIMESTAMP_TZ,
}
NUMERIC = RANGED - {TypeTag.DATE, TypeTag.TIME, TypeTag.TIMESTAMP, TypeTag.TIMESTAMP_TZ}


def profile_package(path: Path) -> dict[str, Any]:
    source_hash = sha256_file(path)
    extracts: list[dict[str, Any]] = []
    with ZipFile(path) as archive, TemporaryDirectory(prefix="tableau-profile-") as temp:
        check_package(archive)
        names = sorted(n for n in archive.namelist() if n.lower().endswith(".hyper"))
        with HyperProcess(
            Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU,
            user_agent="tableau-rayfin-migration",
            parameters={"log_config": ""},
        ) as process:
            for index, name in enumerate(names):
                database = Path(temp) / f"extract-{index}.hyper"
                copy_member(archive, name, database)
                extract: dict[str, Any] = {
                    "member": name, "sha256": sha256_file(database), "tables": [],
                }
                with Connection(process.endpoint, database, CreateMode.NONE) as connection:
                    for schema in connection.catalog.get_schema_names():
                        for table in connection.catalog.get_table_names(schema):
                            definition = connection.catalog.get_table_definition(table)
                            columns = list(definition.columns)
                            expressions = ["COUNT(*)"]
                            stats: list[dict[str, Any]] = []
                            for column in columns:
                                identifier = str(column.name)
                                item: dict[str, Any] = {
                                    "name": column.name.unescaped,
                                    "type": str(column.type),
                                    "nullability": str(column.nullability),
                                    "non_null_index": len(expressions),
                                }
                                expressions.append(f"COUNT({identifier})")
                                if column.type.tag in COMPARABLE:
                                    item["distinct_index"] = len(expressions)
                                    expressions.append(f"COUNT(DISTINCT {identifier})")
                                else:
                                    item["distinct_status"] = "unsupported_type_requires_review"
                                if column.type.tag in RANGED:
                                    item["min_index"] = len(expressions)
                                    expressions.extend([f"MIN({identifier})", f"MAX({identifier})"])
                                if column.type.tag in NUMERIC:
                                    item["sum_index"] = len(expressions)
                                    expressions.append(f"SUM({identifier})")
                                stats.append(item)
                            result = connection.execute_list_query(
                                f"SELECT {', '.join(expressions)} FROM {table}"
                            )[0]
                            row_count = int(result[0])
                            output_columns = []
                            for item in stats:
                                non_null = int(result[item.pop("non_null_index")])
                                item["null_count"] = row_count - non_null
                                if "distinct_index" in item:
                                    distinct = int(result[item.pop("distinct_index")])
                                    item["distinct_non_null_count"] = distinct
                                    item["single_column_key_candidate"] = (
                                        row_count > 0 and non_null == row_count and distinct == row_count
                                    )
                                if "min_index" in item:
                                    offset = item.pop("min_index")
                                    item["minimum"] = str(result[offset]) if result[offset] is not None else None
                                    item["maximum"] = str(result[offset + 1]) if result[offset + 1] is not None else None
                                if "sum_index" in item:
                                    value = result[item.pop("sum_index")]
                                    item["sum"] = str(value) if value is not None else None
                                output_columns.append(item)
                            extract["tables"].append({
                                "name": str(table), "row_count": row_count,
                                "columns": output_columns,
                            })
                extracts.append(extract)
    if sha256_file(path) != source_hash:
        raise ValueError(f"Source package changed during profiling: {path.name}")
    return {
        "schema_version": 1, "tool_version": __version__,
        "source_file": path.name, "source_sha256": source_hash,
        "accuracy_status": "unverified", "telemetry": "disabled",
        "extracts": extracts,
        "limitations": [
            "Statistics describe physical tables, not validated business measures or joined grain.",
            "Single-column key candidates are diagnostics, not declared keys.",
            "Text values and raw rows are not exported; numeric/date aggregate ranges may still be sensitive.",
            "Hyper SQL does not evaluate Tableau workbook calculations or filter order.",
        ],
    }
