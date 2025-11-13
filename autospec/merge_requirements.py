#!/usr/bin/env python3
"""
merge_requirements_into_steps.py

Take:
  1) A models JSON file (GraphWalker/AltWalker format, with `models[].edges`
     and `models[].vertices`, each edge/vertex possibly having `requirements`).
  2) A steps JSON file (AltWalker `offline` output: an array (or array of arrays)
     of steps, each with `id` and `modelName`).

Produce:
  A new steps JSON file where EACH step has a `requirements` field:
    - If the matching edge/vertex has requirements: that array.
    - Otherwise: [].

Usage:
  python merge_requirements_into_steps.py models.json steps.json output.json
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Any

Key = Tuple[str, str]  # (modelName, elementId)


def _extract_models_list(models_data: Any) -> List[dict]:
    """
    Normalize various wrappers around the models.

    Supports:
      - {"models": [...], ...}
      - [{"models": [...], ...}, ...]  (takes first that has "models")
    """
    if isinstance(models_data, dict):
        return models_data.get("models", [])

    if isinstance(models_data, list):
        for item in models_data:
            if isinstance(item, dict) and "models" in item:
                return item["models"]

    return []


def build_requirements_map(models_data: Any) -> Dict[Key, List[str]]:
    """
    Build a map of (modelName, elementId) -> requirements_list
    from the models JSON.
    """
    req_map: Dict[Key, List[str]] = {}

    models_list = _extract_models_list(models_data)

    for model in models_list:
        model_name = model.get("name")
        if not model_name:
            continue

        # Edges
        for edge in model.get("edges", []):
            element_id = edge.get("id")
            if not element_id:
                continue
            reqs = edge.get("requirements")
            if isinstance(reqs, list):
                req_map[(model_name, element_id)] = list(reqs)

        # Vertices
        for vertex in model.get("vertices", []):
            element_id = vertex.get("id")
            if not element_id:
                continue
            reqs = vertex.get("requirements")
            if isinstance(reqs, list):
                req_map[(model_name, element_id)] = list(reqs)

    return req_map


def _annotate_step(step: dict, req_map: Dict[Key, List[str]]) -> None:
    """
    Mutate a single step in place, adding a `requirements` field.

    Always sets:
      step["requirements"] = <list>

    If (modelName, id) is found in req_map: use that list.
    Otherwise: [].
    """
    step_id = step.get("id")
    model_name = step.get("modelName")

    if step_id is None or model_name is None:
        # No way to look up – still ensure requirements is present.
        step["requirements"] = []
        return

    key = (model_name, step_id)
    requirements = req_map.get(key, [])
    # Always an array, even if empty
    step["requirements"] = list(requirements)


def annotate_steps(steps_data: Any, req_map: Dict[Key, List[str]]) -> Any:
    """
    Annotate the steps JSON with requirements.

    Supports:
      - [ {step}, {step}, ... ]
      - { "steps": [ {step}, ... ], ... }
      - [ [ {step}, ... ], [ {step}, ... ] ]
    """
    # Dict wrapper: { "steps": [...] }
    if isinstance(steps_data, dict) and "steps" in steps_data:
        steps_list = steps_data["steps"]
        if isinstance(steps_list, list):
            if steps_list and isinstance(steps_list[0], list):
                # Multiple paths: [[...], [...]]
                for path in steps_list:
                    for step in path:
                        if isinstance(step, dict):
                            _annotate_step(step, req_map)
            else:
                # Single path: [...]
                for step in steps_list:
                    if isinstance(step, dict):
                        _annotate_step(step, req_map)
        return steps_data

    # Top-level list
    if isinstance(steps_data, list):
        if steps_data and isinstance(steps_data[0], list):
            # Multiple paths: [[...], [...]]
            for path in steps_data:
                for step in path:
                    if isinstance(step, dict):
                        _annotate_step(step, req_map)
        else:
            # Single path: [...]
            for step in steps_data:
                if isinstance(step, dict):
                    _annotate_step(step, req_map)

        return steps_data

    # Fallback: unknown structure, just return as-is
    return steps_data

def merge_requirements_files(models_json: str, steps_json: str, output_json: str) -> None:
    """Convenience wrapper for library-style usage."""
    from pathlib import Path
    import json

    models_path = Path(models_json)
    steps_path = Path(steps_json)
    output_path = Path(output_json)

    with models_path.open("r", encoding="utf-8") as f:
        models_data = json.load(f)

    with steps_path.open("r", encoding="utf-8") as f:
        steps_data = json.load(f)

    req_map = build_requirements_map(models_data)
    annotated_steps = annotate_steps(steps_data, req_map)

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(annotated_steps, f, indent=2, ensure_ascii=False)
        
def main(argv: List[str]) -> int:
    if len(argv) != 4:
        print(
            f"Usage: {argv[0]} MODELS_JSON STEPS_JSON OUTPUT_JSON",
            file=sys.stderr,
        )
        return 1

    models_path = Path(argv[1])
    steps_path = Path(argv[2])
    output_path = Path(argv[3])

    # Load files
    with models_path.open("r", encoding="utf-8") as f:
        models_data = json.load(f)

    with steps_path.open("r", encoding="utf-8") as f:
        steps_data = json.load(f)

    # Build lookup from models
    req_map = build_requirements_map(models_data)

    # Annotate steps
    annotated_steps = annotate_steps(steps_data, req_map)

    # Save output
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(annotated_steps, f, indent=2, ensure_ascii=False)

    print(
        f"Done. Requirements merged into steps and written to {output_path}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

__all__ = ["merge_requirements_files"]