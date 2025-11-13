import argparse
import json
from typing import Any, Dict, Iterable, List, Optional, Tuple
import re

Step = Dict[str, Any]
Path = List[Step]


# -------------------------
# Utilities: classification
# -------------------------


def _is_edge(step: Step) -> bool:
    """Heuristic: edges start with 'e_' in GraphWalker exports."""
    return step.get("name", "").startswith("e_")


def _is_vertex(step: Step) -> bool:
    """Heuristic: vertices start with 'v_' in GraphWalker exports."""
    return step.get("name", "").startswith("v_")


def _find_prev_vertex(path: Path, idx: int) -> Optional[Step]:
    """Scan backwards from idx for the nearest vertex."""
    for j in range(idx - 1, -1, -1):
        if _is_vertex(path[j]):
            return path[j]
    return None


def _find_next_vertex(path: Path, idx: int) -> Optional[Step]:
    """Scan forwards from idx for the nearest vertex."""
    for j in range(idx + 1, len(path)):
        if _is_vertex(path[j]):
            return path[j]
    return None

def dedupe_cases(cases: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Remove duplicate test-case objects.

    Two cases are considered duplicates if:
      - they have the same `name`, and
      - their `steps` arrays have the same length and identical contents.

    Returns a new list, preserving the first occurrence of each unique case.
    """
    seen: set[Tuple[str, Tuple[str, ...]]] = set()
    unique: List[Dict[str, Any]] = []

    for case in cases:
        name = str(case.get("name", ""))
        steps = case.get("steps", [])

        # Normalise steps to a tuple of strings
        if not isinstance(steps, list):
            steps = [str(steps)]
        else:
            steps = [str(s) for s in steps]

        key = (name, tuple(steps))

        if key in seen:
            # Duplicate -> skip
            continue

        seen.add(key)
        unique.append(case)

    return unique

# -------------------------
# Utilities: text building
# -------------------------


def _normalise_requirements(*sources: Optional[Step]) -> List[str]:
    """Collect requirements from all provided steps and normalise them.

    - Accepts comma-separated strings in the requirements array and splits them.
    - Deduplicates while preserving order.
    """
    raw: List[str] = []

    for src in sources:
        if not src:
            continue
        reqs = src.get("requirements") or []
        if not isinstance(reqs, list):
            reqs = [reqs]

        for r in reqs:
            if r is None:
                continue
            if isinstance(r, str):
                parts = [p.strip() for p in r.split(",") if p.strip()]
                raw.extend(parts)
            else:
                raw.append(str(r).strip())

    seen = set()
    result: List[str] = []
    for r in raw:
        if r and r not in seen:
            seen.add(r)
            result.append(r)
    return result


def _summarise_actions(step: Step) -> str:
    """Turn the actions array into a single 'changed: ...' string.

    We just dump the raw assignments and ignore JsonContext noise.
    """
    actions = step.get("actions") or []
    parts: List[str] = []

    for act in actions:
        if not isinstance(act, str):
            continue
        cleaned = act.strip().rstrip(";")
        if not cleaned:
            continue
        # Skip pure JsonContext noise if any
        if "JsonContext" in cleaned:
            continue
        parts.append(cleaned)

    return ", ".join(parts) if parts else "None"


# -------------------------
# Core: build human strings
# -------------------------

def _format_vertex_description(raw_name: str) -> str:
    """Turn a vertex name like 'v_ContactDetailForm' into 'Contact Detail Form'."""
    name = raw_name

    if name.startswith("v_"):
        name = name[2:]
    elif name.startswith("v") and len(name) > 1 and name[1].isupper():
        # Handle names like 'vContactDetailForm'
        name = name[1:]

    # Split on underscores first
    segments = [seg for seg in name.split("_") if seg]

    words: List[str] = []
    for seg in segments:
        # Split CamelCase into pieces
        parts = re.split(r"(?<!^)(?=[A-Z])", seg)
        for p in parts:
            p = p.strip()
            if not p:
                continue
            words.append(p.capitalize())

    return " ".join(words) if words else raw_name

def _format_edge_description(raw_name: str) -> str:
    """Turn an edge name like 'e_load_default_data' into 'Load default data'."""
    name = raw_name
    if name.startswith("e_"):
        name = name[2:]

    parts = [p for p in name.split("_") if p]
    if not parts:
        return raw_name

    first = parts[0].capitalize()
    rest = [p.lower() for p in parts[1:]]
    return " ".join([first] + rest)
    
def build_step_strings_for_path(path: Path) -> List[str]:
    """Convert a single path (list of steps) into human-readable lines.

    Rules:
    - We create *one* 'perform ...' line per EDGE in the path.
    - 'perform' is always the edge name (never a vertex).
    - 'results in' points to the nearest vertex *after* the edge;
      if none exists (e.g. final e_restart_test), we fall back to the
      nearest vertex *before* the edge.
    - Step numbers are sequential within this path:
      Step [1] is a synthetic START TEST line (if we find a vertex),
      then each edge increments the step number.
    """
    lines: List[str] = []

    # Step 1: synthetic start from first vertex, if present
    first_vertex = next((s for s in path if _is_vertex(s)), None)
    step_num = 0

    if first_vertex is not None:
        step_num = 1
        lines.append("Step [1] START TEST")

    # One line per edge
    for idx, step in enumerate(path):
        if not _is_edge(step):
            continue

        step_num += 1

        # Nearest vertices before/after this edge
        prev_vertex = _find_prev_vertex(path, idx)
        next_vertex = _find_next_vertex(path, idx)
        target_vertex = next_vertex or prev_vertex

        if target_vertex:
            target_name = _format_vertex_description(target_vertex["name"])
        else:
            target_name = "<no vertex>"

        changed = _summarise_actions(step)

        # Only show requirements if we actually have some
        reqs = _normalise_requirements(step, target_vertex)
        if reqs:
            req_part = f" -> meets requirements: {', '.join(reqs)}"
        else:
            req_part = ""

        human_edge = _format_edge_description(step["name"])

        lines.append(
            f"Step [{step_num}] {human_edge}"
            f" -> results in {target_name} with data"
            f" -> changed: {changed}"
            f"{req_part}"
        )

    lines.append(f"Step [{step_num + 1}] END TEST")

    return lines


def paths_to_step_strings(paths: Iterable[Path]) -> List[str]:
    """Flatten many paths into a single list of step strings."""
    all_lines: List[str] = []
    for path in paths:
        all_lines.extend(build_step_strings_for_path(path))
    return all_lines


def paths_to_cases(paths: Iterable[Path]) -> List[Dict[str, Any]]:
    """Return a list of {name: '', steps: [...] } objects, one per path."""
    cases: List[Dict[str, Any]] = []
    for path in paths:
        steps = build_step_strings_for_path(path)
        cases.append({"name": "", "steps": steps})
    return cases


# -------------------------
# split_path (unchanged)
# -------------------------


def split_path(
    steps: Path,
    *,
    start_name: str = "v_Start",
    start_id: Optional[str] = None,
) -> List[Path]:
    """Split a single long path into smaller paths starting at the given node.

    We look for steps whose *name* matches start_name (or whose id matches
    start_id if provided) and start a new sub-path at each such occurrence.
    """
    if not steps:
        return []

    def is_start(step: Step) -> bool:
        if start_id:
            return step.get("id") == start_id
        return step.get("name") == start_name

    paths: List[Path] = []
    current: Path = []

    for step in steps:
        if is_start(step):
            # Close previous path, if any
            if current:
                paths.append(current)
                current = []
        current.append(step)

    if current:
        paths.append(current)

    return paths


# -------------------------
# CLI entrypoint
# -------------------------


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Path utilities:\n"
            "- mode=split: split a single refined path into smaller paths\n"
            "- mode=describe: take a list of paths and emit {name, steps[]} objects"
        )
    )
    parser.add_argument(
        "input",
        help=(
            "Input JSON file.\n"
            "  - mode=split: list of steps (one long path)\n"
            "  - mode=describe: list of paths (list[list[steps]])"
        ),
    )
    parser.add_argument(
        "output",
        help=(
            "Output JSON file.\n"
            "  - mode=split: list of paths\n"
            "  - mode=describe: list of {name, steps[]} objects"
        ),
    )
    parser.add_argument(
        "--mode",
        choices=["split", "describe"],
        default="split",
        help="Which operation to run (default: split).",
    )
    parser.add_argument(
        "--start-name",
        default="v_Start",
        help='Name of the start node (default: "v_Start"). Ignored if --start-id is provided.',
    )
    parser.add_argument(
        "--start-id",
        default=None,
        help="ID of the start node (takes precedence over --start-name).",
    )

    args = parser.parse_args(argv)

    with open(args.input, encoding="utf-8") as f:
        data = json.load(f)

    if args.mode == "split":
        # data is a single long path (list of steps)
        paths = split_path(
            data,
            start_name=args.start_name,
            start_id=args.start_id,
        )
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(paths, f, indent=2, ensure_ascii=False)
    else:  # describe
        # data is expected to be a list of paths
        if not data:
            paths: List[Path] = []
        elif isinstance(data[0], dict):
            # User accidentally passed a single path; wrap it
            paths = [data]  # type: ignore[assignment]
        else:
            paths = data  # type: ignore[assignment]

        cases = dedupe_cases(paths_to_cases(paths))
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(cases, f, indent=2, ensure_ascii=False)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "merge_requirements_files",
    "split_path",
    "paths_to_step_strings",
]