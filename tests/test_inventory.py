from pathlib import Path
from zipfile import ZipFile

import pytest

from tableau_migration.common import check_package
from tableau_migration.expressions import calculation_features, expression_tokens
from tableau_migration.inventory import inspect_workbook


def package(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "source.twbx"
    with ZipFile(path, "w") as archive:
        archive.writestr("source.twb", text)
    return path


def test_identifiers_ignore_literals_and_comments_and_preserve_escaped_names():
    refs, _ = expression_tokens(
        """SUM([Sales]) + [Parameters].[Period] // [Ignore]
        + '[Not a Field]' + "WINDOW_SUM([Fake])" /* [Other] */ + [a]]b]"""
    )
    assert refs == [("Sales",), ("Parameters", "Period"), ("a]b",)]
    assert calculation_features("'FIXED WINDOW_SUM([Fake])' + COUNT([Order])") == ["count"]


def test_unterminated_expression_never_becomes_a_complete_dependency_graph():
    with pytest.raises(ValueError, match="Unterminated"):
        expression_tokens("SUM([broken)")


def test_scoped_dependencies_worksheet_local_calcs_and_implicit_context(tmp_path):
    source = package(tmp_path, """<workbook xmlns="urn:tableau">
      <datasources>
        <datasource name="A">
          <column name="[Sales]" datatype="real"/>
          <column name="[Calc]"><calculation formula="SUM([Sales])"/></column>
        </datasource>
        <datasource name="B"><column name="[Sales]" datatype="integer"/></datasource>
      </datasources>
      <worksheets><worksheet name="View"><table><view>
        <datasource-dependencies datasource="A">
          <column name="[Sales]" datatype="real"/>
          <column name="[Calc]"><calculation formula="SUM([Sales])"/></column>
          <column name="[Local]"><calculation formula="[Calc] * 2"/></column>
          <column-instance name="[usr:Local:qk]" column="[Local]">
            <table-calc type="PctTotal" ordering-type="Rows"/>
          </column-instance>
        </datasource-dependencies>
      </view><rows>[A].[usr:Local:qk]</rows></table></worksheet></worksheets>
      <dashboards>
        <dashboard name="Main"><zones>
          <zone name="View"/><zone type="bitmap" param="Image/missing.png"/>
        </zones></dashboard>
        <dashboard name="Story" type="storyboard"/>
      </dashboards>
    </workbook>""")
    result = inspect_workbook(source)
    sheet = result["worksheets"][0]
    assert set(sheet["required_fields"]) == {
        "A::[Sales]", "A::[Calc]", "worksheet::View::A::[Local]",
    }
    assert "B::[Sales]" not in sheet["required_fields"]
    assert "PctTotal" in sheet["table_calculations"][0]
    assert result["counts"]["worksheet_local_calculations"] == 1
    assert result["counts"]["stories"] == 1
    assert {"code": "missing_asset", "asset": "Image/missing.png"} in result["issues"]
    assert result["accuracy_status"] == "unverified"


def test_unresolved_calculation_references_are_review_findings(tmp_path):
    source = package(tmp_path, """<workbook><datasources><datasource name="A">
    <column name="[Calc]"><calculation formula="[Missing] + [Other].[Foreign]"/></column>
    </datasource></datasources></workbook>""")
    result = inspect_workbook(source)
    assert result["fields"][0]["unresolved_references"] == [["Missing"], ["Other", "Foreign"]]
    assert any(i["code"] == "unresolved_field_references" for i in result["issues"])


def test_default_raw_fields_are_resolved_from_connection_metadata(tmp_path):
    source = package(tmp_path, """<workbook><datasources><datasource name="A">
      <connection><metadata-records><metadata-record class="column">
        <local-name>[Sales]</local-name><local-type>real</local-type>
        <remote-name>Sales</remote-name><object-id>[Orders]</object-id>
      </metadata-record></metadata-records></connection>
      <column name="[Calc]"><calculation formula="SUM([Sales])"/></column>
    </datasource></datasources>
    <worksheets><worksheet name="View"><table><view>
      <datasource-dependencies datasource="A"><column name="[Calc]"/></datasource-dependencies>
    </view><rows>[A].[Calc]</rows></table></worksheet></worksheets></workbook>""")
    result = inspect_workbook(source)
    sheet = result["worksheets"][0]
    assert set(sheet["required_fields"]) == {"A::[Calc]", "A::[Sales]"}
    assert not any(i["code"] == "unresolved_field_references" for i in result["issues"])
    assert result["fields"][1]["definition_origin"] == "connection-metadata"
    assert "[Orders]" in result["datasources"][0]["column_mapping_xml"][0]


def test_datasource_filters_are_included_in_sheet_requirements(tmp_path):
    source = package(tmp_path, """<workbook><datasources><datasource name="A">
      <column name="[Sales]"/><column name="[Keep]"><calculation formula="[Sales] &gt; 0"/></column>
      <filter column="[A].[Keep]"/>
      <group name="[Set]"><groupfilter function="union"/></group>
    </datasource></datasources>
    <worksheets><worksheet name="View"><table><view>
      <datasource-dependencies datasource="A"><column name="[Sales]"/></datasource-dependencies>
    </view><rows>[A].[Sales]</rows><cols>[A].[:Measure Names]</cols></table></worksheet></worksheets>
    </workbook>""")
    result = inspect_workbook(source)
    sheet = result["worksheets"][0]
    assert set(sheet["required_fields"]) == {"A::[Keep]", "A::[Sales]"}
    assert sheet["unresolved_references"] == []
    assert '[Set]' in result["datasources"][0]["group_xml"][0]


@pytest.mark.parametrize("member", ["../escape.twb", "/root.twb", "C:\\escape.twb", "a\\..\\escape.twb"])
def test_unsafe_archive_members_are_rejected(tmp_path, member):
    source = tmp_path / "unsafe.twbx"
    with ZipFile(source, "w") as archive:
        archive.writestr(member, "<workbook/>")
    with ZipFile(source) as archive, pytest.raises(ValueError, match="Unsafe"):
        check_package(archive)


def test_xml_entities_are_not_resolved(tmp_path):
    source = package(tmp_path, """<!DOCTYPE workbook [
      <!ENTITY secret SYSTEM "file:///nonexistent-secret">
    ]><workbook>&secret;</workbook>""")
    from defusedxml.common import DefusedXmlException

    with pytest.raises(DefusedXmlException):
        inspect_workbook(source)
