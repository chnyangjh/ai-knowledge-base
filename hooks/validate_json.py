#!/usr/bin/env python3
"""Validate knowledge base JSON files against schema requirements.

Usage:
    python hooks/validate_json.py <json_file> [json_file2 ...]
    python hooks/validate_json.py "knowledge/articles/**/*.json"

Exit code: 0 on success (all files pass), 1 on failure (errors found).
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

REQUIRED_FIELDS: dict[str, type] = {
    "id": str,
    "title": str,
    "source_url": str,
    "summary": str,
    "tags": list,
    "status": str,
}

VALID_STATUSES = frozenset({"draft", "review", "published", "archived"})
VALID_AUDIENCES = frozenset({"beginner", "intermediate", "advanced"})

ID_PATTERN = re.compile(r"^[a-z][a-z0-9_-]+-\d{8}-\d{3}$")
URL_PATTERN = re.compile(r"^https?://")

SUMMARY_MIN_CHARS = 20
TAGS_MIN_COUNT = 1
SCORE_MIN = 1
SCORE_MAX = 10


def _field_type_name(t: type) -> str:
    """Return human-readable type name."""
    return t.__name__


def _find_field(data: dict[str, Any], field_name: str) -> tuple[bool, Any]:
    """Search for a field in *data* and nested ``metadata`` dict.

    Returns ``(found, value)`` tuple.
    """
    if field_name in data:
        return True, data[field_name]
    metadata = data.get("metadata")
    if isinstance(metadata, dict) and field_name in metadata:
        return True, metadata[field_name]
    return False, None


def validate_file(file_path: Path) -> list[str]:
    """Validate a single JSON file.

    Returns a list of error message strings (empty means valid).
    Errors are *without* filepath prefix — display code adds grouping.
    """
    errors: list[str] = []

    try:
        raw_text = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"cannot read file - {exc}")
        return errors

    if not raw_text.strip():
        errors.append("empty file")
        return errors

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        errors.append(f"invalid JSON - {exc}")
        return errors

    if not isinstance(data, dict):
        errors.append(
            f"top-level must be a JSON object, got {type(data).__name__}"
        )
        return errors

    # -- Required fields ---------------------------------------------------
    for field_name, field_type in REQUIRED_FIELDS.items():
        if field_name not in data:
            errors.append(f"missing required field '{field_name}'")
            continue
        value = data[field_name]
        if not isinstance(value, field_type):
            errors.append(
                f"field '{field_name}' type mismatch - "
                f"expected {_field_type_name(field_type)}, "
                f"got {type(value).__name__}"
            )

    # Only run dependent checks on fields that exist *and* have correct type
    def _ok(field_name: str, field_type: type) -> bool:
        return field_name in data and isinstance(data[field_name], field_type)

    # -- ID format ---------------------------------------------------------
    if _ok("id", str):
        raw_id = data["id"]
        if not ID_PATTERN.match(raw_id):
            errors.append(
                f"field 'id' format invalid - "
                f"expected {{source}}-{{YYYYMMDD}}-{{NNN}} "
                f"(e.g. github-20260317-001), got '{raw_id}'"
            )

    # -- Status values -----------------------------------------------------
    if _ok("status", str):
        raw_status = data["status"]
        if raw_status not in VALID_STATUSES:
            valid_list = ", ".join(sorted(VALID_STATUSES))
            errors.append(
                f"field 'status' invalid value '{raw_status}' - "
                f"must be one of: {valid_list}"
            )

    # -- URL format --------------------------------------------------------
    if _ok("source_url", str):
        raw_url = data["source_url"]
        if not URL_PATTERN.match(raw_url):
            errors.append(
                f"field 'source_url' invalid - "
                f"must start with http:// or https://, got '{raw_url}'"
            )

    # -- Summary length ----------------------------------------------------
    if _ok("summary", str):
        length = len(data["summary"])
        if length < SUMMARY_MIN_CHARS:
            errors.append(
                f"field 'summary' too short "
                f"({length} chars, min {SUMMARY_MIN_CHARS})"
            )

    # -- Tags count --------------------------------------------------------
    if _ok("tags", list):
        count = len(data["tags"])
        if count < TAGS_MIN_COUNT:
            errors.append(
                f"field 'tags' must have at least "
                f"{TAGS_MIN_COUNT} item(s), got {count}"
            )

    # -- Optional: score (1-10) --------------------------------------------
    found_score, score_value = _find_field(data, "score")
    if found_score and score_value is not None:
        if not isinstance(score_value, (int, float)):
            errors.append(
                f"field 'score' must be a number, "
                f"got {type(score_value).__name__}"
            )
        elif isinstance(score_value, bool):
            errors.append("field 'score' must be a number, got bool")
        elif not (SCORE_MIN <= score_value <= SCORE_MAX):
            errors.append(
                f"field 'score' must be {SCORE_MIN}-{SCORE_MAX}, "
                f"got {score_value}"
            )

    # -- Optional: audience (beginner|intermediate|advanced) ----------------
    found_aud, aud_value = _find_field(data, "audience")
    if found_aud and aud_value is not None:
        if isinstance(aud_value, str):
            if aud_value not in VALID_AUDIENCES:
                valid_list = ", ".join(sorted(VALID_AUDIENCES))
                errors.append(
                    f"field 'audience' invalid value "
                    f"'{aud_value}', must be one of: {valid_list}"
                )
        elif isinstance(aud_value, list):
            for item in aud_value:
                if item not in VALID_AUDIENCES:
                    valid_list = ", ".join(sorted(VALID_AUDIENCES))
                    errors.append(
                        f"field 'audience' contains invalid "
                        f"value '{item}', must be one of: {valid_list}"
                    )
        else:
            errors.append(
                f"field 'audience' unexpected type "
                f"{type(aud_value).__name__}"
            )

    return errors


def _collect_files(raw_args: list[str]) -> list[Path]:
    """Resolve file paths from CLI arguments, expanding glob patterns."""
    files: list[Path] = []
    seen: set[Path] = set()

    for raw in raw_args:
        path = Path(raw)
        has_glob = any(c in raw for c in ("*", "?", "["))

        if has_glob:
            matches = list(Path.cwd().glob(raw)) if not path.is_absolute() else list(Path().glob(raw))
            for match in sorted(matches):
                if match.is_file() and match.suffix == ".json" and match not in seen:
                    files.append(match)
                    seen.add(match)
        elif path.is_file():
            if path not in seen:
                files.append(path)
                seen.add(path)
        elif path.is_dir():
            for match in sorted(path.glob("**/*.json")):
                if match not in seen:
                    files.append(match)
                    seen.add(match)
        else:
            print(f"Warning: '{raw}' not found, skipping", file=sys.stderr)

    return files


def main() -> int:
    """Entry point: parse args, validate files, print summary, return exit code."""
    parser = argparse.ArgumentParser(
        description="Validate knowledge base JSON files against schema requirements.",
    )
    parser.add_argument(
        "files",
        nargs="+",
        help="JSON file paths or glob patterns (e.g. *.json, knowledge/**/*.json)",
    )
    args_namespace = parser.parse_args()

    files = _collect_files(args_namespace.files)
    if not files:
        print("Error: no JSON files found to validate", file=sys.stderr)
        return 1

    total = len(files)
    all_errors: dict[str, list[str]] = {}
    passed = 0

    for fp in files:
        errs = validate_file(fp)
        if errs:
            all_errors[str(fp)] = errs
        else:
            passed += 1

    # -- Print errors ------------------------------------------------------
    if all_errors:
        print(f"\n{'=' * 60}")
        print("VALIDATION ERRORS")
        print(f"{'=' * 60}")
        for filepath, err_list in all_errors.items():
            print(f"\n  {filepath}:")
            for err in err_list:
                print(f"    - {err}")

    # -- Print summary -----------------------------------------------------
    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print(f"{'=' * 60}")
    print(f"  Total files:   {total}")
    print(f"  Passed:        {passed}")
    print(f"  Failed:        {len(all_errors)}")

    if all_errors:
        total_errors = sum(len(v) for v in all_errors.values())
        print(f"  Total errors:  {total_errors}")
        print()
        return 1

    print("  Result:        ALL PASSED")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
