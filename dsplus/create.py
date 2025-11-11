#!/usr/bin/env python3
"""
doorstop_create_plus.py — wrapper around `doorstop create` and header seeding.

- Runs: doorstop create <doc_prefix> <abs_path> --parent <parent>
- Patches the new .doorstop.yml with: digits, itemformat, sep, parent, prefix
  and document defaults (title, by, major, minor, copyright) if provided.
- Seeds headers from `catalog_registry.yml` group (e.g., `form: ["Form Fields","UI Behavior"]`)
  by calling custom/doorstop_add_plus.py with --header, --text, --level 0.

Requires:
  - ruamel.yaml
  - Doorstop CLI
  - plus.py available (default: dsplus/plus.py)
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
import subprocess
from .dsputils import (
    resolve_catalog_paths,
    yload,
    ydump,
    cfg_load,
    find_doc_dir_by_prefix,
    headers_from_registry
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

# ---------- Patch .doorstop.yml ----------
def patch_doordoc_yaml(doc_dir: Path, parent: str, prefix: str, digits: int, itemformat: str, sep: str,
                       title: Optional[str], by: Optional[str], major: Optional[str], minor: Optional[str], copyright_text: Optional[str]):
    cfg_path = doc_dir / ".doorstop.yml"
    doc = yload(cfg_path, yaml) or {}
    doc.setdefault("settings", {})
    doc["settings"]["digits"] = digits
    doc["settings"]["itemformat"] = itemformat
    doc["settings"]["parent"] = parent
    doc["settings"]["prefix"] = prefix
    doc["settings"]["sep"] = sep

    doc.setdefault("attributes", {})
    doc["attributes"].setdefault("defaults", {})
    doc["attributes"]["defaults"].setdefault("doc", {})
    ddoc = doc["attributes"]["defaults"]["doc"]
    if title is not None:
        ddoc["title"] = str(title)
    if by is not None:
        ddoc["by"] = str(by)
    if major is not None:
        ddoc["major"] = str(major)
    if minor is not None:
        ddoc["minor"] = str(minor)
    if copyright_text is not None:
        ddoc["copyright"] = str(copyright_text)
    ydump(cfg_path, doc, yaml)
    return cfg_path

def main(argv=None):
    ap = argparse.ArgumentParser(description="Create a Doorstop document and seed headers from catalog_registry.yml.")

    # Arguments
    ap.add_argument("prefix", help="prefix used in doc creation")
    ap.add_argument("--name", required=True, help="Directory name for the document (folder).")
    ap.add_argument("--type", required=True, help="Header group key from catalog_registry.yml (e.g., 'form', 'interface').")
    ap.add_argument("--title", required=True, help="Title for html header")
    ap.add_argument("--path", help="Base path where the document folder will be created. Default prefix location ")
    ap.add_argument("--root", default="reqs/", help="Root folder for Doorstop docs;")
    ap.add_argument("--header-defaults", default="defaults/header.yml", help="Defaults YAML for headers")

    
    args = ap.parse_args(argv)
    cwd = Path(os.getcwd())

    paths = resolve_catalog_paths(DEFAULT_EXPECTED_FILES)

    abs_config     = paths.abs_config
    abs_registry   = paths.abs_registry
    abs_catalog    = paths.abs_catalog
    abs_add_script = paths.abs_add_script

    # load config
    cfg = cfg_load(abs_config, yaml)

    # 1) config must not be empty
    if cfg == {}:
        ap.error(f"Config file is empty or invalid: {abs_config}")

    # 2) root must exist in args or config and not be blank
    root_str = (args.root or cfg.get("root", "")).strip()
    if not root_str:
        ap.error("`root` is empty. Provide --root or set 'root' in catalog_config.yml.")

    root = Path(root_str).expanduser().resolve()
    doc_prefix = args.prefix
    docs = [seg for seg in doc_prefix.strip().split("-") if seg]

    if len(docs) < 2:
        ap.error(f"Prefix needs to have a parent document: {docs}")

    parent = "-".join(docs[:-1])

    parent_dir = find_doc_dir_by_prefix(root_str, parent, yaml)

    doc_dir = (parent_dir / args.name) if isinstance(parent_dir, Path) else Path(parent_dir) / args.name
    doc_dir.mkdir(parents=True, exist_ok=True)

    # doorstop create
    cmd = ["doorstop", "create", doc_prefix, str(doc_dir), "--parent", parent]

    try:
        result = subprocess.run(
            cmd, check=True, cwd=root, capture_output=True, text=True
        )
    except subprocess.CalledProcessError as e:
        print(f"[doorstop create] failed (exit {e.returncode})", file=sys.stderr)
        if e.stdout:
            print(e.stdout, file=sys.stderr)
        if e.stderr:
            print(e.stderr, file=sys.stderr)
        sys.exit(e.returncode)


    # patch .doorstop.yml
    digits = int(cfg.get("digits", 3))
    itemformat = str(cfg.get("itemformat", "yaml"))
    sep = str(cfg.get("sep", "-"))

    # ensure the file exists (fail fast if Doorstop wrote somewhere else)
    cfg_path = doc_dir / ".doorstop.yml"
    if not cfg_path.exists():
        raise RuntimeError(f".doorstop.yml not found at {cfg_path}")

    patch_doordoc_yaml(
        doc_dir,
        parent=parent,
        prefix=doc_prefix,
        digits=digits,
        itemformat=itemformat,
        sep=sep,
        title=args.title,
        by="QA Team",
        major="0",
        minor=".0",
        copyright_text="copyright: '© 2025 AIF - *All rights reserved*'",
    )

    headers = headers_from_registry(Path(abs_registry), args.type, yaml)

    # resolve absolute header-defaults path once
    abs_header_defaults = Path(args.header_defaults).expanduser().resolve()

    seeded = 0
    # seed headers at level 0
    for label in headers:
        add_cmd = [
            sys.executable, "-m", "dsplus.add",
            doc_prefix,
            "--title", str(label),
            "--type", "header",
            "--root", str(root),
            "--item_defaults", str(abs_header_defaults)
        ]
        print("[seed]", " ".join(add_cmd))
        try:
            subprocess.run(add_cmd, check=True, cwd=str(Path(os.getcwd())))
            seeded += 1
        except subprocess.CalledProcessError as e:
            print(f"[doorstop create] failed (exit {e.returncode})", file=sys.stderr)
            if e.stdout:
                print(e.stdout, file=sys.stderr)
            if e.stderr:
                print(e.stderr, file=sys.stderr)
            sys.exit(e.returncode)

    print(f"OK: created {doc_prefix} at {doc_dir} and seeded {seeded} header(s).")

if __name__ == "__main__":
    main()
