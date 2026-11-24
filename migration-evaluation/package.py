"""Bundle first-party evaluation code and guidance, excluding workbook data."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parent
MODULES = ("__init__.py", "common.py", "expressions.py", "inventory.py", "profile.py",
           "reconcile.py", "cli.py", "tableau_export.py")


def bundle(output: Path) -> int:
    repository = ROOT.parent
    files = [repository / "README.md", repository / "pyproject.toml", repository / "requirements.windows.lock"]
    toolkit = repository / "tools" / "tableau-migration" / "src" / "tableau_migration"
    files.extend(toolkit / name for name in MODULES)
    files.extend((repository / ".github" / "skills" / "tableau-rayfin-migration").rglob("*.md"))
    files.extend((repository / ".github" / "skills" / "tableau-migration-evaluation").rglob("*.md"))
    files.extend(ROOT.glob("*.py"))
    files.extend(ROOT.glob("*.json"))
    files.extend(ROOT.glob("*.md"))
    files.extend((ROOT / "tests").glob("*.py"))
    files.extend([repository / "publish" / "old_blockers.md", repository / "publish" / "migration-evaluation-plan.md"])
    manifest = {path.relative_to(repository).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted(files)}
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "x", compression=ZIP_DEFLATED) as archive:
        for path in sorted(files):
            archive.write(path, path.relative_to(repository).as_posix())
        archive.writestr("bundle-manifest.json", json.dumps({"files": manifest, "third_party_workbooks_included": False}, indent=2))
    return len(files)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(f"Bundled {bundle(args.output)} first-party files: {args.output}")