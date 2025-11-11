#!/usr/bin/env python3
"""
doorstop_create_plus.py — wrapper around `doorstop create` and header seeding.

- Runs: doorstop add <doc_prefix> -d <abs_path>
- Patches the new .doorstop.yml with: digits, itemformat, sep, parent, prefix
  and item defaults (title, by, major, minor, copyright) if provided.

Requires:
  - ruamel.yaml
  - Doorstop CLI

Modes:
1) Header bootstrap:       --type header
   - Creates a header item (level N.0), uid=<doorstop_id>, catalog_id=<RQ-xxxxx>,
     header=<title>, derived=false, normative=false, form_id=<prefix>, form_name=<parent doc title>.
   - Adds to catalog.yml as type: header.

2) Requirement under header: --type "<Existing Header Title>"
   - Verifies header exists in catalog for this document; if not, exits with error (no item created).
   - Computes level as H.K (H=index of header among headers, K=next item count under that header).
   - uid=<doorstop_id>, catalog_id=<RQ-xxxxx>, header=<type>, form_id=<prefix>, form_name=<parent doc title>,
     derived=true, normative=true.

"""
import argparse
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
import subprocess
import re
import datetime
from datetime import date
from .dsputils import (
    resolve_catalog_paths,
    yload,
    ydump,
    cfg_load,
    get_doc_dir,
    headers_from_registry,   
    bump_registry_counter,   
)

try:
    from ruamel.yaml import YAML
except Exception as e:
    raise SystemExit("ERROR: ruamel.yaml is required. Try: pip install ruamel.yaml") from e

yaml = YAML()
yaml.preserve_quotes = True
yaml.indent(mapping=2, sequence=2, offset=0)

DEFAULT_EXPECTED_FILES = {
    "config": "catalog_config.yml",
    "add_script": "add.py",
    "registry": "catalog_registry.yml",
    "catalog": "catalog.yml",
}

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
import subprocess
import re
from datetime import date

from .dsputils import (
    resolve_catalog_paths,
    yload,
    ydump,
    cfg_load,
    get_doc_dir,
    bump_registry_counter,
)

try:
    from ruamel.yaml import YAML
except Exception as e:
    raise SystemExit("ERROR: ruamel.yaml is required. Try: pip install ruamel.yaml") from e

yaml = YAML()
yaml.preserve_quotes = True
yaml.indent(mapping=2, sequence=2, offset=0)

DEFAULT_EXPECTED_FILES = {
    "config": "catalog_config.yml",
    "add_script": "add.py",
    "registry": "catalog_registry.yml",
    "catalog": "catalog.yml",
}

def _ensure_list(d: dict, key: str):
    val = d.get(key)
    if isinstance(val, list):
        return val
    d[key] = []
    return d[key]

def _headers_for_prefix(cat_data: dict, item_prefix: str) -> List[str]:
    """Return header titles in catalog.yml order for this document/prefix."""
    items = cat_data.get("items") or []
    headers = []
    for it in items:
        if not isinstance(it, dict):
            continue
        if str(it.get("type", "")).lower() != "header":
            continue
        iid = str(it.get("id", ""))
        if iid.startswith(item_prefix):
            title = it.get("title")
            if title:
                headers.append(str(title))
    return headers

def _header_index(headers: List[str], label: str) -> Optional[int]:
    """1-based index of label in headers (exact match), else None."""
    try:
        return headers.index(label) + 1
    except ValueError:
        return None

def _count_items_under_header(cat_data: dict, item_prefix: str, header_label: str) -> int:
    """Count non-header items already registered under given header (by catalog 'type')."""
    items = cat_data.get("items") or []
    n = 0
    for it in items:
        if not isinstance(it, dict):
            continue
        iid = str(it.get("id", ""))
        if not iid.startswith(item_prefix):
            continue
        t = it.get("type")
        if isinstance(t, str) and t == header_label:
            n += 1
    return n

def main(argv=None):
    ap = argparse.ArgumentParser(description="Add a Doorstop item with strict header policy.")
    ap.add_argument("prefix", help="Document prefix (e.g., APP-QL-CNI)")
    ap.add_argument("--title", required=True, help="Item title (for headers, this is the header label)")
    ap.add_argument("--type", required=True, help="Either 'header' to bootstrap a header, or the EXACT header label to add under")
    ap.add_argument("--root", default="reqs/", help="Root folder for Doorstop docs")
    ap.add_argument("--item_defaults", required=True, help="Defaults YAML for the new item")
    args = ap.parse_args(argv)

    # Resolve paths / config
    paths = resolve_catalog_paths(DEFAULT_EXPECTED_FILES)
    abs_config   = paths.abs_config
    abs_registry = paths.abs_registry
    abs_catalog  = paths.abs_catalog

    cfg = cfg_load(abs_config, yaml)
    if cfg == {}:
        ap.error(f"Config file is empty or invalid: {abs_config}")

    root_str = (args.root or cfg.get("root", "")).strip()
    if not root_str:
        ap.error("`root` is empty. Provide --root or set 'root' in catalog_config.yml.")
    root = Path(root_str).expanduser().resolve()

    item_prefix = args.prefix
    item_title  = args.title
    item_type   = args.type  # either 'header' or the header label to file under

    # Locate document dir and settings
    doc_dir = get_doc_dir(root, item_prefix, abs_catalog, yaml)
    doc_cfg = yload(doc_dir / ".doorstop.yml", yaml) or {}
    settings = (doc_cfg.get("settings") or {})
    digits = int(settings.get("digits") or cfg.get("digits", 3))
    sep = str(settings.get("sep") or cfg.get("sep", "-") or "")
    itemformat = (settings.get("itemformat") or cfg.get("itemformat") or "yaml").lower()
    ext = ".yaml" if itemformat in ("yaml",) else ".yml"

    # Parent doc title -> form_name
    doc_title = None
    try:
        doc_title = (doc_cfg.get("attributes") or {}) \
            .get("defaults", {}) \
            .get("doc", {}) \
            .get("title")
    except Exception:
        doc_title = None

    # Load catalog; build header index
    cat_data = yload(abs_catalog, yaml) or {}
    items_list = _ensure_list(cat_data, "items")
    headers = _headers_for_prefix(cat_data, item_prefix)

    is_header = (str(item_type).strip().lower() == "header")
    header_label_for_item = None
    H = None  # header index (1-based)

    if is_header:
        # Header bootstrap: new header will be appended after existing ones
        H = len(headers) + 1
        header_label_for_item = item_title  # the header's own label
    else:
        # Requirement must target an existing header
        header_label_for_item = item_type.strip()
        if not headers:
            print(f"ERROR: No headers exist yet for {item_prefix}. Seed headers first (e.g., `dsplus.add {item_prefix} --type header --title \"{header_label_for_item}\"`).", file=sys.stderr)
            sys.exit(2)
        H = _header_index(headers, header_label_for_item)
        if H is None:
            print(f"ERROR: Header '{header_label_for_item}' not found for {item_prefix}. Run create/seed or add the header first.", file=sys.stderr)
            sys.exit(2)

    # For requirements, compute next K under that header from catalog
    if not is_header:
        K_existing = _count_items_under_header(cat_data, item_prefix, header_label_for_item)
        K = K_existing + 1
    else:
        K = 0  # unused for headers

    # Create the item via Doorstop
    cmd = ["doorstop", "add", item_prefix, "-d", args.item_defaults]
    try:
        result = subprocess.run(cmd, check=True, cwd=root, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        print(f"[doorstop add] failed (exit {e.returncode})", file=sys.stderr)
        if e.stdout:
            print(e.stdout, file=sys.stderr)
        if e.stderr:
            print(e.stderr, file=sys.stderr)
        sys.exit(e.returncode)

    # Determine the new file path / doorstop id
    # The new number is one more than last_number *before* we bump the counter persistently.
    reg_before = yload(abs_registry, yaml) or {}
    last_number_before = int(reg_before.get("last_number", 0))
    next_number = last_number_before + 1
    doorstop_id = f"{item_prefix}{sep}{next_number:0{digits}d}"

    candidate = doc_dir / f"{doorstop_id}{ext}"
    if not candidate.exists():
        alt = doc_dir / f"{doorstop_id}{('.yml' if ext == '.yaml' else '.yaml')}"
        if alt.exists():
            candidate = alt
        else:
            m = re.search(r"([A-Z]+-[A-Z0-9-]+-\d{"+str(digits)+r"})", (result.stdout or ""))
            if m:
                doorstop_id = m.group(1)
                c1 = doc_dir / f"{doorstop_id}.yaml"
                c2 = doc_dir / f"{doorstop_id}.yml"
                if c1.exists():
                    candidate = c1
                elif c2.exists():
                    candidate = c2

    if not candidate.exists():
        raise RuntimeError(f"Could not locate new item file for id '{doorstop_id}' under {doc_dir}")

    print("[new item]", candidate.name)

    # Persist bump AFTER successful add -> yields the catalog_id counter
    new_last = bump_registry_counter(abs_registry, yaml)
    print(f"[registry] last_number -> {new_last}")

    # Catalog uid (global RQ-xxxxx)
    catalog_prefix = str(cfg.get("catalog_prefix", "RQ"))
    width = int(cfg.get("width", 5))
    catalog_uid = f"{catalog_prefix}-{new_last:0{width}d}"

    # Load the new item and patch attributes
    item_data = yload(candidate, yaml) or {}

    # Basic identity
    today_iso = date.today().isoformat()
    item_data["uid"] = doorstop_id              # <-- item's own unique id (e.g., APP-QL-CNI-004)
    item_data["catalog_id"] = catalog_uid       # <-- global catalog uid (e.g., RQ-00004)

    # Dates
    if not item_data.get("created_date"):
        item_data["created_date"] = today_iso
    if item_data.get("reviewed") in (None, "", "null"):
        item_data["reviewed"] = today_iso

    # Form fields
    base_form_id = item_prefix
    if not item_data.get("form_id"):
        item_data["form_id"] = base_form_id
    if not item_data.get("form_name"):
        item_data["form_name"] = doc_title or base_form_id

    # Header attribute
    if is_header:
        item_data["header"] = item_title
    else:
        item_data["header"] = header_label_for_item

    # Title / text
    if item_title:
        item_data["title"] = item_title
    item_data.setdefault("text", item_data.get("text") or "")

    # Flags
    if is_header:
        item_data["derived"] = False
        item_data["normative"] = False
    else:
        item_data.setdefault("derived", True)
        item_data.setdefault("normative", True)
    item_data.setdefault("active", True)

    # Level
    level_str = f"{H}.0" if is_header else f"{H}.{K}"
    try:
        item_data["level"] = float(level_str)
    except Exception:
        item_data["level"] = level_str  # fallback as string if needed

    # Links (preserve if seeded elsewhere, else [])
    item_data.setdefault("links", [])

    # Tags list sanity
    if not isinstance(item_data.get("tags"), list):
        item_data["tags"] = []

    ydump(candidate, item_data, yaml)
    print(f"[item] patched attributes for {doorstop_id} (uid={doorstop_id}, catalog_id={catalog_uid}, level={item_data['level']})")

    # Update catalog.yml
    cat_entry = {
        "id": doorstop_id,
        "uid": catalog_uid,
        "title": item_title,
        "type": ("header" if is_header else header_label_for_item),
        "reqs": [],
    }
    exists = any(isinstance(it, dict) and it.get("id") == doorstop_id for it in items_list)
    if not exists:
        items_list.append(cat_entry)
        ydump(abs_catalog, cat_data, yaml)
        print(f"[catalog] appended item id={doorstop_id}, uid={catalog_uid}, type={cat_entry['type']}")
    else:
        print(f"[catalog] item id={doorstop_id} already present; skipping")

if __name__ == "__main__":
    main()
