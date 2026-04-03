#!/usr/bin/env python3
"""
Validates .xcoll files before merge.
Runs automatically via GitHub Actions on pull requests.
"""

import json
import sys
from pathlib import Path

REQUIRED_META_FIELDS = ["name", "description", "author", "category"]
VALID_CATEGORIES = ["complete", "curated", "hidden-gems", "challenge"]


def validate_xcoll(path):
    errors = []

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return [f"Invalid JSON: {e}"]

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


def main():
    has_errors = False

    for path in sorted(Path(".").rglob("*.xcoll")):
        errors = validate_xcoll(path)
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
