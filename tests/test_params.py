import json
import sys

from pixcake_use.params import collect_params, maybe_json


# --------------------------------------------------------------------------- #
# maybe_json
# --------------------------------------------------------------------------- #
def test_maybe_json_returns_non_str_unchanged():
    assert maybe_json(42) == 42
    assert maybe_json(None) is None
    sentinel = {"already": "dict"}
    assert maybe_json(sentinel) is sentinel
    items = [1, 2, 3]
    assert maybe_json(items) is items


def test_maybe_json_plain_string_unchanged():
    # No leading [ or { -> returned as-is.
    assert maybe_json("hello") == "hello"
    assert maybe_json("123") == "123"
    assert maybe_json("true") == "true"


def test_maybe_json_empty_or_whitespace_unchanged():
    assert maybe_json("") == ""
    assert maybe_json("   ") == "   "


def test_maybe_json_parses_object_and_array():
    assert maybe_json('{"a": 1}') == {"a": 1}
    assert maybe_json("[1, 2, 3]") == [1, 2, 3]
    # Leading/trailing whitespace is stripped before parsing.
    assert maybe_json('  {"a": 1}  ') == {"a": 1}


def test_maybe_json_malformed_returns_original():
    assert maybe_json("{not json}") == "{not json}"
    bad = '{"a": '
    assert maybe_json(bad) == bad
    bad_arr = "[1, 2,"
    assert maybe_json(bad_arr) == bad_arr


# --------------------------------------------------------------------------- #
# collect_params — basic extraction
# --------------------------------------------------------------------------- #
def test_collect_params_basic_pf_record():
    config = {"Params": [{"pf": "color", "name": "Tint", "fe": 0.5}]}
    result = collect_params(config)
    assert len(result) == 1
    entry = result[0]
    assert entry["pf"] == "color"
    assert entry["name"] == "Tint"
    assert entry["value_type"] == "fe"
    assert entry["value"] == 0.5
    assert entry["path"] == "$"


def test_collect_params_value_type_precedence_ie_before_se():
    # Order of precedence is fixed: fe < ie < se < ae (first match wins).
    # A param containing both ie and se selects ie.
    config = {"Params": [{"pf": "p", "se": "str-val", "ie": 7}]}
    result = collect_params(config)
    assert result[0]["value_type"] == "ie"
    assert result[0]["value"] == 7


def test_collect_params_value_type_only_ae():
    config = {"Params": [{"pf": "p", "ae": [1, 2, 3]}]}
    result = collect_params(config)
    assert result[0]["value_type"] == "ae"
    assert result[0]["value"] == [1, 2, 3]


def test_collect_params_value_type_fe_beats_all():
    config = {"Params": [{"pf": "p", "ae": "a", "se": "s", "ie": 1, "fe": 9.9}]}
    result = collect_params(config)
    assert result[0]["value_type"] == "fe"
    assert result[0]["value"] == 9.9


def test_collect_params_skips_params_without_pf():
    config = {"Params": [{"name": "no-pf", "fe": 1.0}, {"pf": "ok", "fe": 2.0}]}
    result = collect_params(config)
    assert len(result) == 1
    assert result[0]["pf"] == "ok"


def test_collect_params_strparams_descended():
    # StrParams holding a JSON string is parsed and mined; path includes .StrParams.
    inner = json.dumps({"Params": [{"pf": "inner", "fe": 1.0}]})
    config = {"StrParams": inner}
    result = collect_params(config)
    assert len(result) == 1
    assert result[0]["pf"] == "inner"
    assert result[0]["path"] == "$.StrParams"


def test_collect_params_json_in_string_columns():
    # A string value (under a normal key) that is JSON gets parsed and mined.
    column_value = json.dumps({"Params": [{"pf": "embedded", "se": "v"}]})
    config = {"column": column_value}
    result = collect_params(config)
    assert len(result) == 1
    assert result[0]["pf"] == "embedded"
    assert result[0]["value_type"] == "se"
    assert result[0]["path"] == "$.column"


def test_collect_params_json_string_top_level_column():
    value = '{"Params": [{"pf": 5, "fe": 0.1}]}'
    result = collect_params(value)
    assert len(result) == 1
    assert result[0]["pf"] == 5


def test_collect_params_non_json_string_no_params():
    assert collect_params("just a plain string") == []
    assert collect_params({"k": "plain text value"}) == []


def test_collect_params_nested_lists_and_dicts_paths():
    config = {
        "outer": [
            {"Params": [{"pf": "a", "fe": 1.0}]},
            {"Params": [{"pf": "b", "ie": 2}]},
        ]
    }
    result = collect_params(config)
    pfs = {e["pf"]: e["path"] for e in result}
    assert pfs["a"] == "$.outer[0]"
    assert pfs["b"] == "$.outer[1]"


# --------------------------------------------------------------------------- #
# Depth guard
# --------------------------------------------------------------------------- #
def test_collect_params_depth_guard_marker():
    # Nest deeper than a small max_depth and assert the marker appears
    # without raising.
    nested = {"pf_holder": {"Params": [{"pf": "deep", "fe": 1.0}]}}
    config = {"a": {"b": {"c": nested}}}
    result = collect_params(config, max_depth=2)
    errors = [e for e in result if e.get("error") == "max recursion depth exceeded"]
    assert errors, f"expected depth marker, got {result}"


def test_collect_params_pathological_depth_does_not_blow_recursion():
    # Build input nested far deeper than Python's recursion limit would allow
    # a naive recursion to survive; the depth guard must stop first.
    limit = sys.getrecursionlimit()
    depth = limit + 500
    obj = {"pf_target": {"Params": [{"pf": "x", "fe": 1.0}]}}
    for _ in range(depth):
        obj = {"nest": obj}
    # Default max_depth (64) is far below the nesting, so this returns a marker
    # rather than raising RecursionError.
    result = collect_params(obj)
    assert any(e.get("error") == "max recursion depth exceeded" for e in result)


def test_collect_params_depth_marker_carries_path():
    config = {"x": {"y": {"z": "deeper"}}}
    result = collect_params(config, max_depth=1)
    marker = next(e for e in result if e.get("error") == "max recursion depth exceeded")
    assert marker["path"].startswith("$")


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
