#!/usr/bin/env python3
"""
Validates .xcoll, _platform.json, and _media.json files before merge.
Runs automatically via GitHub Actions on pull requests.
"""

import json
import re
import sys
from pathlib import Path

REQUIRED_META_FIELDS = ["name", "description", "author", "category"]
VALID_CATEGORIES = ["complete", "curated", "hidden-gems", "challenge"]

REQUIRED_PLATFORM_FIELDS = ["id", "name", "shortName", "igdbId"]
REQUIRED_MEDIA_FIELDS = ["id", "name", "shortName", "source"]

KEBAB_CASE_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_xcoll(path):
    errors = []

    try:
        data = load_json(path)
    except json.JSONDecodeError as e:
        return [f"Invalid JSON: {e}"]

    # Check filename is kebab-case
    stem = path.stem
    if not KEBAB_CASE_RE.match(stem):
        errors.append(f"Filename must be kebab-case: '{stem}' (e.g. 'best-rpgs')")

    # Check version
    if data.get("version") != 2:
        errors.append(f"Expected version 2, got {data.get('version')}")

    # Check format
    if data.get("format") not in ("light", "full"):
        errors.append(f"Invalid format: {data.get('format')}. Must be 'light' or 'full'")

    # Check meta
    meta = data.get("meta", {})
    for field in REQUIRED_META_FIELDS:
        if field not in meta:
            errors.append(f"Missing required meta field: {field}")

    if meta.get("category") and meta["category"] not in VALID_CATEGORIES:
        errors.append(
            f"Invalid category: {meta['category']}. Must be one of: {VALID_CATEGORIES}"
        )

    # Check items
    items = data.get("items", [])
    if not items:
        errors.append("Collection has no items")

    for i, item in enumerate(items):
        if "externalId" not in item:
            errors.append(f"Item {i} missing externalId")

    # Check for duplicate externalIds
    ext_ids = [item.get("externalId") for item in items if item.get("externalId")]
    duplicates = set(x for x in ext_ids if ext_ids.count(x) > 1)
    if duplicates:
        errors.append(f"Duplicate externalIds: {duplicates}")

    return errors


def validate_platform(path):
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

    # Validate .xcoll files
    for path in sorted(Path(".").rglob("*.xcoll")):
        errors = validate_xcoll(path)
        if errors:
            print(f"FAIL {path}")
            for error in errors:
                print(f"   - {error}")
            has_errors = True
        else:
            print(f"OK   {path}")

    # Validate _platform.json files
    for path in sorted(Path("platforms").rglob("_platform.json")) if Path("platforms").exists() else []:
        errors = validate_platform(path)
        if errors:
            print(f"FAIL {path}")
            for error in errors:
                print(f"   - {error}")
            has_errors = True
        else:
            print(f"OK   {path}")

    # Validate _media.json files
    for path in sorted(Path("media").rglob("_media.json")) if Path("media").exists() else []:
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

    print(f"\nAll files valid!")


if __name__ == "__main__":
    main()
