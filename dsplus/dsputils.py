# dsplus/dsputils.py
from __future__ import annotations
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Mapping, Union, Optional, Dict, Any

try:
    from ruamel.yaml import YAML
except Exception:
    print("ERROR: ruamel.yaml is required. pip install ruamel.yaml", file=sys.stderr)
    raise


# ---------- Paths ----------
def package_root() -> Path:
    """Absolute path to the dsplus package directory."""
    return Path(__file__).resolve().parent


def resolve_catalog_paths(expected_files: Mapping[str, str]) -> SimpleNamespace:
    """
    Resolve required files inside the dsplus package directory.
    Returns a SimpleNamespace with attributes named "abs_<key>".
    Raises FileNotFoundError if any expected file is missing.
    """
    base = package_root()
    if not base.is_dir():
        raise FileNotFoundError(f"Directory not found: {base}")

    paths = {k: (base / v).resolve() for k, v in expected_files.items()}
    missing = [p.name for p in paths.values() if not p.exists()]
    if missing:
        expected_list = "\n".join(f"- {name}" for name in expected_files.values())
        raise FileNotFoundError(
            f"Missing required files in {base}: {', '.join(missing)}\n"
            f"Expected names:\n{expected_list}"
        )

    return SimpleNamespace(**{f"abs_{k}": p for k, p in paths.items()})


# ---------- YAML helpers ----------
def _yaml_or(yaml: Optional[YAML]) -> YAML:
    if yaml is not None:
        return yaml
    y = YAML()
    y.preserve_quotes = True
    y.indent(mapping=2, sequence=2, offset=0)
    return y


def yload(path: Path, yaml: Optional[YAML] = None):
    """Load YAML file (returns dict/obj or None if not exists)."""
    if not path.exists():
        return None
    y = _yaml_or(yaml)
    with path.open("r", encoding="utf-8") as f:
        return y.load(f)


def ydump(path: Path, data, yaml: Optional[YAML] = None):
    """Dump YAML file, creating parent dirs if needed."""
    y = _yaml_or(yaml)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        y.dump(data, f)


def cfg_load(config_path: Union[str, Path], yaml: Optional[YAML] = None) -> Dict[str, Any]:
    """
    Load catalog_config.yml (merge over defaults). `config_path` must point to the file.
    """
    cfg = {}
    config_path = Path(config_path)
    data = yload(config_path, yaml) or {}
    if isinstance(data, dict):
        for k, v in data.items():
            if v is not None:
                cfg[k] = v
    if "catalog_file" not in cfg:
        cfg["catalog_file"] = "catalog.yaml"
    return cfg

def find_doc_dir_by_prefix(root_str: str, parent_prefix: str, yaml: Optional[YAML] = None) -> Path:
    root = Path(root_str).expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Root directory not found: {root}")

    found = None
    for dirpath, _, filenames in os.walk(root):
        if ".doorstop.yml" in filenames:
            cfg_path = Path(dirpath) / ".doorstop.yml"
            doc = yload(cfg_path, yaml) or {}
            if (doc.get("settings") or {}).get("prefix") == parent_prefix:
                if found is not None:
                    raise RuntimeError(
                        f"Multiple documents share prefix '{parent_prefix}': {found} and {dirpath}"
                    )
                found = Path(dirpath)

    if found is None:
        raise FileNotFoundError(f"No document with prefix '{parent_prefix}' found under {root}")

    return found

# ---------- Headers from registry ----------
def headers_from_registry(reg_path: Path, group_key: str, yaml: Optional[YAML] = None) -> List[str]:
    data = yload(reg_path, yaml) or {}
    headers = data.get('headers')
    key = str(group_key).lower()
    print(data)
    print(key)
    vals = headers.get(key)
    return list(vals) if isinstance(vals, list) else []

def bump_registry_counter(reg_path: Union[str, Path], yaml: Optional[YAML] = None) -> int:
    """
    Increment `last_number` in the registry YAML. Creates/initializes if missing.
    Returns the new last_number.
    """
    p = Path(reg_path)
    data = yload(p, yaml) or {}
    try:
        last = int(data.get("last_number", 0))
    except Exception:
        last = 0
    data["last_number"] = last + 1
    ydump(p, data, yaml)
    return data["last_number"]

def _safe_list(v):
    return v if isinstance(v, list) else []


def get_doc_dir(
    root: Union[str, Path],
    doc_prefix: str,
    catalog_path: Union[str, Path],
    yaml: Optional[YAML] = None,
    update_catalog: bool = True,
) -> Path:
    rootp = Path(root).expanduser().resolve()
    if not rootp.is_dir():
        raise FileNotFoundError(f"Root directory not found: {rootp}")

    catalog_path = Path(catalog_path).expanduser().resolve()
    catalog = yload(catalog_path, yaml) or {}
    locations = _safe_list(catalog.get("locations"))   # <-- coerce to list

    # Step 1: try catalog.yml -> locations
    doc_dir: Optional[Path] = None
    cat_entry: Optional[dict] = None
    for loc in locations:                               # safe to iterate
        if isinstance(loc, dict) and loc.get("id") == doc_prefix:
            cat_entry = loc
            loc_str = str(loc.get("location", "")).strip()
            if loc_str:
                p = Path(loc_str)
                if not p.is_absolute():
                    p = rootp / p
                p = p.expanduser().resolve()
                cfg_path = p / ".doorstop.yml"
                if cfg_path.exists():
                    data = yload(cfg_path, yaml) or {}
                    if (data.get("settings") or {}).get("prefix") == doc_prefix:
                        doc_dir = p
            break

    # Step 2: fallback scan
    if doc_dir is None:
        found: Optional[Path] = None
        for dirpath, _, filenames in os.walk(rootp):
            if ".doorstop.yml" in filenames:
                cfg_path = Path(dirpath) / ".doorstop.yml"
                data = yload(cfg_path, yaml) or {}
                if (data.get("settings") or {}).get("prefix") == doc_prefix:
                    if found is not None:
                        raise RuntimeError(
                            f"Multiple documents share prefix '{doc_prefix}': {found} and {dirpath}"
                        )
                    found = Path(dirpath)
        if found is None:
            raise FileNotFoundError(f"No document with prefix '{doc_prefix}' found under {rootp}")
        doc_dir = found

    # Step 3: update catalog.yml -> locations
    if update_catalog and doc_dir is not None:
        try:
            loc_str = str(doc_dir.resolve().relative_to(rootp))
        except ValueError:
            loc_str = str(doc_dir.resolve())

        updated = False
        if cat_entry is None:
            locations.append({"id": doc_prefix, "location": loc_str})
            updated = True
        else:
            if str(cat_entry.get("location", "")).strip() != loc_str:
                cat_entry["location"] = loc_str
                updated = True

        # ensure we write back a list (even if original was null)
        catalog["locations"] = locations
        if updated:
            ydump(catalog_path, catalog, yaml)

    return doc_dir

__all__ = ["package_root", "resolve_catalog_paths", "yload", "ydump", "cfg_load", "find_doc_dir_by_prefix", "headers_from_registry", "bump_registry_counter", "get_doc_dir"]
