from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

from test_evaluator import workbook

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("evaluation_package", ROOT / "package.py")
assert SPEC and SPEC.loader
package = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(package)


def test_bundle_is_first_party_and_imports_its_toolkit(tmp_path: Path) -> None:
    archive_path = tmp_path / "handoff.zip"
    assert package.bundle(archive_path) > 10
    extracted = tmp_path / "extracted"
    with ZipFile(archive_path) as archive:
        names = archive.namelist()
        assert "README.md" in names
        assert "migration-evaluation/evaluator.py" in names
        assert "migration-evaluation/cloud.py" in names
        assert "migration-evaluation/cloud-config.example.json" in names
        assert "bundle-manifest.json" in names
        assert ".github/skills/tableau-rayfin-migration/SKILL.md" in names
        assert ".github/skills/tableau-migration-evaluation/SKILL.md" in names
        assert not any(name.endswith(".twbx") or "/runs/" in name or ".env" in name for name in names)
        archive.extractall(extracted)
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(extracted / "tools" / "tableau-migration" / "src")
    check = subprocess.run(
        [sys.executable, "-c", "from pathlib import Path; import tableau_migration.inventory as inventory; assert Path(inventory.__file__).resolve().is_relative_to(Path.cwd()); print('Bundled toolkit import verified')"],
        cwd=extracted, env=environment, capture_output=True, text=True, check=False,
    )
    assert check.returncode == 0, check.stderr
    help_result = subprocess.run(
        [sys.executable, "migration-evaluation/evaluator.py", "--help"],
        cwd=extracted, env=environment, capture_output=True, text=True, check=False,
    )
    assert help_result.returncode == 0, help_result.stderr
    assert "prepare-evidence" in help_result.stdout
    assert "evaluate" in help_result.stdout
    cloud_help = subprocess.run(
        [sys.executable, "migration-evaluation/cloud.py", "--help"],
        cwd=extracted, env=environment, capture_output=True, text=True, check=False,
    )
    assert cloud_help.returncode == 0, cloud_help.stderr
    assert "configure" in cloud_help.stdout
    evaluation_result = subprocess.run(
        [sys.executable, "migration-evaluation/evaluator.py", "evaluate", "--input", str(workbook(tmp_path)),
         "--output", "migration-evaluation/runs/customer-test"],
        cwd=extracted, env=environment, capture_output=True, text=True, check=False,
    )
    assert evaluation_result.returncode == 0, evaluation_result.stderr
    summary = json.loads((extracted / "migration-evaluation/runs/customer-test/evaluation-summary.json").read_text())
    assert summary["evaluation_status"] == "completed"
    assert summary["migration_performed"] is False
    assert summary["workbooks"][0]["recommended_category"] == 1
    skill_path = extracted / ".github/skills/tableau-migration-evaluation/SKILL.md"
    skill = skill_path.read_text(encoding="utf-8")
    assert skill.startswith("---\nname: tableau-migration-evaluation\n")
    assert len(skill.splitlines()) <= 500
    description = next(line for line in skill.splitlines() if line.startswith("description:"))
    assert len(description) < 1024
    for link in re.findall(r"\]\(([^)#]+)(?:#[^)]*)?\)", skill):
        assert (skill_path.parent / link).resolve().is_file(), link