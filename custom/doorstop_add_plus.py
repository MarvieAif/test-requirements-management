#!/usr/bin/env python3
"""
doorstop_add_plus.py — a thin wrapper around `doorstop add` that:
  1) Finds the target Doorstop document by prefix (composed from segments like APP/QL/CNI/FF),
  2) Runs `doorstop add <doc_prefix>`,
  3) Locates the newly created item YAML,
  4) Auto-fills metadata (created_date, catalog_id, isCatalogued, catalog_date)
     using a simple global counter registry.

Requirements:
  - Python 3.8+
  - ruamel.yaml (pip install ruamel.yaml)
  - Doorstop CLI must be on PATH (the same `doorstop` you've been using)

Typical usage:
  # Create under APP-QL-CNI-FF, assign next catalog id from defaults
  python doorstop_add_plus.py QL CNI FF

  # Or provide the full document prefix directly (bypasses segments):
  python doorstop_add_plus.py --doc-prefix APP-QL-CNI-FF

  # Dry run (no writes):
  python doorstop_add_plus.py QL CNI FF --dry-run

  # Custom cataloging settings:
  python doorstop_add_plus.py QL CNI FF --catalog-prefix RQ --width 6 --registry ./defaults/catalog_registry.yml

Notes:
  - Segments are joined to the base prefix with '-', e.g., base APP + [QL, CNI, FF] => APP-QL-CNI-FF
  - The script scans ./docs (override with --root) for a .doorstop.yml whose 'settings.prefix' matches the target.
  - The registry file stores the last issued global number; it is created automatically if missing.
"""

import argparse
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple
from datetime import datetime
import sys

from ruamel.yaml import YAML

def load_yaml(path: Path):
    yaml = YAML()
    yaml.preserve_quotes = True
    with path.open('r', encoding='utf-8') as f:
        return yaml.load(f), yaml

def dump_yaml(path: Path, data, yaml: YAML):
    with path.open('w', encoding='utf-8') as f:
        yaml.dump(data, f)

def find_doc_dir_by_prefix(root: Path, target_prefix: str) -> Optional[Path]:
    """
    Search under 'root' for a .doorstop.yml whose settings.prefix == target_prefix.
    Return its directory path.
    """
    for dot in root.rglob(".doorstop.yml"):
        try:
            data, _ = load_yaml(dot)
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        settings = data.get("settings") or {}
        if settings.get("prefix") == target_prefix:
            return dot.parent
    return None

def existing_item_files(doc_dir: Path) -> List[Path]:
    """
    Return the list of YAML item files in a document directory (skip the .doorstop.yml itself).
    """
    items = []
    for ext in ("*.yml", "*.yaml"):
        for p in doc_dir.glob(ext):
            if p.name.lower() in (".doorstop.yml", ".doorstop.yaml"):
                continue
            items.append(p)
    return sorted(items)

def compute_next_catalog_id(registry_path: Path, prefix: str, width: int) -> Tuple[str, int]:
    """
    Load or create registry YAML and compute the next catalog ID.
    Structure:
        last_number: 12
    """
    reg_data = {}
    if registry_path.exists():
        try:
            reg_data, yaml = load_yaml(registry_path)
        except Exception:
            reg_data = {}
    last_number = int((reg_data or {}).get("last_number", 0))
    next_number = last_number + 1
    cat_id = f"{prefix}-{next_number:0{width}d}"
    # Persist
    reg_data["last_number"] = next_number
    # Make sure folder exists
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    yaml = YAML()
    yaml.preserve_quotes = True
    dump_yaml(registry_path, reg_data, yaml)
    return cat_id, next_number

def update_item_metadata(item_path: Path, created_date_field: str, catalog_prefix: str, width: int,
                         registry_path: Path, set_catalog: bool, dry_run: bool) -> None:
    """
    Open the YAML and set created_date field. Optionally set catalog fields using registry.
    """
    data, yaml = load_yaml(item_path)
    if not isinstance(data, dict):
        return

    today = datetime.now().date().isoformat()

    changed = False
    # created_date
    if created_date_field not in data or not data.get(created_date_field):
        data[created_date_field] = today
        changed = True

    if set_catalog:
        # Only assign if not already catalogued
        if not data.get("isCatalogued") or not data.get("catalog_id"):
            catalog_id, _ = compute_next_catalog_id(registry_path, catalog_prefix, width)
            data["isCatalogued"] = True
            data["catalog_id"] = catalog_id
            if "catalog_date" not in data or not data.get("catalog_date"):
                data["catalog_date"] = today
            changed = True

    if changed and not dry_run:
        dump_yaml(item_path, data, yaml)

def main(argv=None):
    ap = argparse.ArgumentParser(description="Wrapper around `doorstop add` that auto-fills metadata.")
    ap.add_argument("segments", nargs="*", help="Hierarchy segments (e.g., QL CNI FF). Joined with base prefix.")
    ap.add_argument("--doc-prefix", help="Explicit document prefix (e.g., APP-QL-CNI-FF). Overrides segments.")
    ap.add_argument("--base-prefix", default="APP", help="Base prefix used with segments (default: APP)")
    ap.add_argument("--root", default="./docs", help="Root folder to scan for .doorstop.yml (default: ./docs)")
    ap.add_argument("--created-date-field", default="created_date", help="Field name for created date (default: created_date)")
    ap.add_argument("--no-catalog", action="store_true", help="Do not assign a catalog_id/isCatalogued")
    ap.add_argument("--catalog-prefix", default="RQ", help="Prefix for global catalog IDs (default: RQ)")
    ap.add_argument("--width", type=int, default=5, help="Zero-padding width for catalog number (default: 5)")
    ap.add_argument("--registry", default="./defaults/catalog_registry.yml", help="Path to the global catalog registry YAML")
    ap.add_argument("--dry-run", action="store_true", help="Scan and create, but do not write item metadata")
    args = ap.parse_args(argv)

    root = Path(args.root).resolve()
    if not root.exists():
        print(f"[error] Root not found: {root}", file=sys.stderr)
        sys.exit(2)

    if args.doc_prefix:
        doc_prefix = args.doc_prefix
    else:
        if not args.segments:
            print("[error] Provide segments (e.g., QL CNI FF) or --doc-prefix", file=sys.stderr)
            sys.exit(2)
        doc_prefix = "-".join([args.base_prefix] + args.segments)

    doc_dir = find_doc_dir_by_prefix(root, doc_prefix)
    if not doc_dir:
        print(f"[error] No document found with prefix '{doc_prefix}' under {root}", file=sys.stderr)
        sys.exit(2)

    # Collect item files before
    before = set(existing_item_files(doc_dir))

    # Run doorstop add
    cmd = ["doorstop", "add", doc_prefix]
    try:
        print(f"[info] Running: {' '.join(cmd)}")
        res = subprocess.run(cmd, cwd=root.parent, capture_output=True, text=True)
    except FileNotFoundError:
        print("[error] Could not find 'doorstop' on PATH. Please ensure Doorstop CLI is installed.", file=sys.stderr)
        sys.exit(2)

    if res.returncode != 0:
        print(res.stdout)
        print(res.stderr, file=sys.stderr)
        sys.exit(res.returncode)

    # Collect item files after
    after = set(existing_item_files(doc_dir))
    new_files = sorted(list(after - before))
    if not new_files:
        print("[warn] No new item file detected; listing recent files:")
        for p in sorted(after):
            print(" -", p)
        sys.exit(0)

    # Update the most recent new file (Doorstop creates exactly one per add)
    item_path = new_files[-1]
    print(f"[info] New item: {item_path}")

    update_item_metadata(
        item_path=item_path,
        created_date_field=args.created_date_field,
        catalog_prefix=args.catalog_prefix,
        width=args.width,
        registry_path=Path(args.registry),
        set_catalog=(not args.no_catalog),
        dry_run=args.dry_run,
    )

    if args.dry_run:
        print("[info] Dry run complete (no writes).")
    else:
        print("[info] Metadata updated.")
        print(f"[info] Catalog registry: {Path(args.registry).resolve()}")

if __name__ == "__main__":
    main()
