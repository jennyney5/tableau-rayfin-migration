from decimal import Decimal
from zipfile import ZipFile

from tableauhyperapi import (
    Connection, CreateMode, HyperProcess, Inserter, Nullability, SqlType,
    TableDefinition, TableName, Telemetry,
)

from tableau_migration.common import sha256_file
from tableau_migration.profile import profile_package


def test_profile_discovers_multiple_tables_and_preserves_decimal_null_and_source(tmp_path):
    database = tmp_path / "source.hyper"
    with HyperProcess(Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU, parameters={"log_config": ""}) as process:
        with Connection(process.endpoint, database, CreateMode.CREATE) as connection:
            for name in ["Orders", "Returns"]:
                definition = TableDefinition(TableName("public", name), [
                    TableDefinition.Column("Id", SqlType.big_int(), Nullability.NOT_NULLABLE),
                    TableDefinition.Column("Amount", SqlType.numeric(18, 2)),
                ])
                connection.catalog.create_table(definition)
                with Inserter(connection, definition) as inserter:
                    inserter.add_rows([[1, Decimal("0.10")], [2, Decimal("0.20")], [3, None]])
                    inserter.execute()
    package = tmp_path / "source.twbx"
    with ZipFile(package, "w") as archive:
        archive.write(database, "Data/source.hyper")
    original_hash = sha256_file(package)
    profile = profile_package(package)
    tables = profile["extracts"][0]["tables"]
    assert {t["name"] for t in tables} == {'"public"."Orders"', '"public"."Returns"'}
    for table in tables:
        assert table["row_count"] == 3
        columns = {c["name"]: c for c in table["columns"]}
        assert columns["Id"]["single_column_key_candidate"] is True
        assert columns["Amount"]["null_count"] == 1
        assert Decimal(columns["Amount"]["sum"]) == Decimal("0.30")
    assert sha256_file(package) == original_hash
