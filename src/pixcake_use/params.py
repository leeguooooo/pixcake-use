from __future__ import annotations

import json
from typing import Any


def maybe_json(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if not stripped or stripped[0] not in "[{":
        return value
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return value


def collect_params(value: Any, path: str = "$", depth: int = 0, max_depth: int = 64) -> list[dict[str, Any]]:
    if depth > max_depth:
        return [{"path": path, "error": "max recursion depth exceeded"}]
    value = maybe_json(value)
    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        if "StrParams" in value:
            found.extend(
                collect_params(value["StrParams"], f"{path}.StrParams", depth + 1, max_depth)
            )
        params = value.get("Params")
        if isinstance(params, list):
            for param in params:
                if not isinstance(param, dict) or "pf" not in param:
                    continue
                entry = {
                    "path": path,
                    "pf": param.get("pf"),
                    "name": param.get("name"),
                }
                for key in ("fe", "ie", "se", "ae"):
                    if key in param:
                        entry["value_type"] = key
                        entry["value"] = param[key]
                        break
                found.append(entry)
        for key, nested in value.items():
            if key in {"Params", "StrParams"}:
                continue
            if isinstance(nested, (dict, list, str)):
                found.extend(collect_params(nested, f"{path}.{key}", depth + 1, max_depth))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(collect_params(item, f"{path}[{index}]", depth + 1, max_depth))
    return found
