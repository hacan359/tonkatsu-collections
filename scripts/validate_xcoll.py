#!/usr/bin/env python3
"""
Validates .xcoll/.xcollx, _platform.json, and _media.json files before merge.
Runs automatically via GitHub Actions on pull requests.

.xcoll/.xcollx files must be in native Tonkatsu Box XcollFile format (v2).
"""

import json
import re
import sys
from pathlib import Path

VALID_FORMATS = ("light", "full")
VALID_MEDIA_TYPES = ("game", "movie", "tv_show", "animation", "visual_novel", "manga")

REQUIRED_PLATFORM_FIELDS = ["id", "name", "shortName", "igdbId"]
REQUIRED_MEDIA_FIELDS = ["id", "name", "shortName", "source"]

KEBAB_CASE_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_xcoll(path):
    """Validate a .xcoll/.xcollx file against XcollFile v2 format."""
    errors = []

    try:
        data = load_json(path)
    except json.JSONDecodeError as e:
        return [f"Invalid JSON: {e}"]

    # Check filename is kebab-case
    stem = path.stem
    if not KEBAB_CASE_RE.match(stem):
        errors.append(f"Filename must be kebab-case: '{stem}' (e.g. 'best-rpgs')")

    # version (required, must be 2)
    if data.get("version") != 2:
        errors.append(f"Expected version 2, got {data.get('version')}")

    # format (required, "light" or "full")
    fmt = data.get("format")
    if fmt not in VALID_FORMATS:
        errors.append(f"Invalid format: {fmt}. Must be one of: {VALID_FORMATS}")

    # Verify extension matches format
    suffix = path.suffix.lower()
    if fmt == "full" and suffix != ".xcollx":
        errors.append(f"Full format should use .xcollx extension, got '{suffix}'")
    if fmt == "light" and suffix not in (".xcoll", ".xcollx"):
        errors.append(f"Unexpected extension '{suffix}' for format '{fmt}'")

    # name (required)
    if not data.get("name"):
        errors.append("Missing required field: name")

    # author (required)
    if not data.get("author"):
        errors.append("Missing required field: author")

    # created (required, ISO 8601)
    created = data.get("created")
    if not created:
        errors.append("Missing required field: created")
    elif not isinstance(created, str):
        errors.append(f"'created' must be an ISO 8601 string, got {type(created).__name__}")

    # items (required, non-empty)
    items = data.get("items")
    if not isinstance(items, list):
        errors.append("Missing or invalid 'items' array")
        return errors

    if not items:
        errors.append("Collection has no items")

    for i, item in enumerate(items):
        # media_type (required)
        mt = item.get("media_type")
        if not mt:
            errors.append(f"Item {i}: missing media_type")
        elif mt not in VALID_MEDIA_TYPES:
            errors.append(f"Item {i}: invalid media_type '{mt}'")

        # external_id (required)
        if "external_id" not in item:
            errors.append(f"Item {i}: missing external_id")

    # Check for duplicate external_ids (per media_type + platform_id)
    seen = set()
    duplicates = set()
    for item in items:
        mt = item.get("media_type", "")
        eid = item.get("external_id")
        pid = item.get("platform_id", "")
        key = f"{mt}:{eid}:{pid}"
        if key in seen:
            duplicates.add(key)
        seen.add(key)
    if duplicates:
        errors.append(f"Duplicate items: {duplicates}")

    return errors


def validate_platform(path):
    """Validate a _platform.json file."""
    errors = []

    try:
        data = load_json(path)
    except json.JSONDecodeError as e:
        return [f"Invalid JSON: {e}"]

    for field in REQUIRED_PLATFORM_FIELDS:
        if field not in data:
            errors.append(f"Missing required field: {field}")

    # id should match parent folder name
    parent_name = path.parent.name
    if data.get("id") and data["id"] != parent_name:
        errors.append(f"id '{data['id']}' does not match folder name '{parent_name}'")

    if "igdbId" in data and not isinstance(data["igdbId"], int):
        errors.append(f"igdbId must be an integer, got {type(data['igdbId']).__name__}")

    return errors


def validate_media(path):
    """Validate a _media.json file."""
    errors = []

    try:
        data = load_json(path)
    except json.JSONDecodeError as e:
        return [f"Invalid JSON: {e}"]

    for field in REQUIRED_MEDIA_FIELDS:
        if field not in data:
            errors.append(f"Missing required field: {field}")

    # id should match parent folder name
    parent_name = path.parent.name
    if data.get("id") and data["id"] != parent_name:
        errors.append(f"id '{data['id']}' does not match folder name '{parent_name}'")

    return errors


def main():
    has_errors = False

    # Validate .xcoll and .xcollx files
    for pattern in ("*.xcoll", "*.xcollx"):
        for path in sorted(Path(".").rglob(pattern)):
            errors = validate_xcoll(path)
            if errors:
                print(f"FAIL {path}")
                for error in errors:
                    print(f"   - {error}")
                has_errors = True
            else:
                print(f"OK   {path}")

    # Validate _platform.json files
    if Path("platforms").exists():
        for path in sorted(Path("platforms").rglob("_platform.json")):
            errors = validate_platform(path)
            if errors:
                print(f"FAIL {path}")
                for error in errors:
                    print(f"   - {error}")
                has_errors = True
            else:
                print(f"OK   {path}")

    # Validate _media.json files
    if Path("media").exists():
        for path in sorted(Path("media").rglob("_media.json")):
            errors = validate_media(path)
            if errors:
                print(f"FAIL {path}")
                for error in errors:
                    print(f"   - {error}")
                has_errors = True
            else:
                print(f"OK   {path}")

    if has_errors:
        print("\nValidation failed!")
        sys.exit(1)

    print("\nAll files valid!")


if __name__ == "__main__":
    main()
