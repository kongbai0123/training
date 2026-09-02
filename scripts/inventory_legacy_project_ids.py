"""Dry-run inventory for project identifiers that need a manual migration."""

from __future__ import annotations

import json
import argparse
import shutil
from datetime import datetime
from pathlib import Path

from src.config import PROJECTS_DIR
from src.path_security import validate_resource_id


def main() -> int:
    parser = argparse.ArgumentParser(description="Inventory legacy IDs; migration is opt-in and backup-first.")
    parser.add_argument("--mapping-file", type=Path, help="JSON object mapping old folder names to new resource IDs")
    parser.add_argument("--apply", action="store_true", help="Apply the mapping after creating ZIP backups")
    args = parser.parse_args()
    findings = []
    for entry in sorted(PROJECTS_DIR.iterdir()) if PROJECTS_DIR.exists() else []:
        if not entry.is_dir():
            continue
        try:
            validate_resource_id(entry.name, label="project_id")
        except ValueError as exc:
            findings.append({"project_id": entry.name, "path": str(entry), "issue": str(exc), "action": "manual-backup-and-rename"})
    result = {"dry_run": not args.apply, "count": len(findings), "projects": findings, "migrated": []}
    if args.mapping_file:
        mapping = json.loads(args.mapping_file.read_text(encoding="utf-8"))
        if not isinstance(mapping, dict):
            raise ValueError("mapping file must be a JSON object")
        for old_name, new_name in mapping.items():
            validate_resource_id(str(new_name), label="new project_id")
            source = PROJECTS_DIR / str(old_name)
            target = PROJECTS_DIR / str(new_name)
            if not source.is_dir() or target.exists():
                raise ValueError(f"Cannot migrate {old_name!r}: source missing or target exists")
            if args.apply:
                backup_root = PROJECTS_DIR / "_migration-backups"
                backup_root.mkdir(parents=True, exist_ok=True)
                stamp = datetime.now().strftime("%Y%m%d%H%M%S")
                archive = shutil.make_archive(str(backup_root / f"{source.name}-{stamp}"), "zip", root_dir=source)
                source.rename(target)
                project_file = target / "project.json"
                if project_file.exists():
                    data = json.loads(project_file.read_text(encoding="utf-8"))
                    data["project_id"] = str(new_name)
                    project_file.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                result["migrated"].append({"from": old_name, "to": new_name, "backup": archive})
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
