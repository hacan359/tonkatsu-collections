#!/usr/bin/env python3
"""
Validates .xcoll/.xcollx/.zip, _platform.json, and _media.json files before merge.
Runs automatically via GitHub Actions on pull requests.

.xcoll/.xcollx files must be in native Tonkatsu Box XcollFile format (v2).
.zip files must contain exactly one .xcoll or .xcollx file inside.
"""

import json
import re
import sys
import zipfile
from pathlib import Path

VALID_FORMATS = ("light", "full")
VALID_MEDIA_TYPES = ("game", "movie", "tv_show", "animation", "visual_novel", "manga")

REQUIRED_PLATFORM_FIELDS = ["id", "name", "shortName", "igdbId"]
REQUIRED_MEDIA_FIELDS = ["id", "name", "shortName", "source"]

KEBAB_CASE_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
XCOLL_EXTENSIONS = (".xcoll", ".xcollx")


def load_json_from_path(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_json_from_zip(zip_path):
    """Load the .xcoll/.xcollx file from inside a zip archive.

    Returns (data, inner_filename) or raises ValueError.
    """
    with zipfile.ZipFile(zip_path, "r") as zf:
        xcoll_files = [
            n for n in zf.namelist() if n.lower().endswith(XCOLL_EXTENSIONS)
        ]
        if not xcoll_files:
            raise ValueError("No .xcoll/.xcollx file found inside zip")
        if len(xcoll_files) > 1:
            raise ValueError(
                f"Zip contains multiple collection files: {xcoll_files}"
            )
        inner = xcoll_files[0]
        raw = zf.read(inner)
        return json.loads(raw.decode("utf-8")), inner


def validate_xcoll_data(data, display_path, inner_filename=None):
    """Validate parsed XcollFile v2 data."""
    errors = []

    # version (required, must be 2)
    if data.get("version") != 2:
        errors.append(f"Expected version 2, got {data.get('version')}")

    # format (required, "light" or "full")
    fmt = data.get("format")
    if fmt not in VALID_FORMATS:
        errors.append(f"Invalid format: {fmt}. Must be one of: {VALID_FORMATS}")

    # Verify inner file extension matches format (skip for zips without inner name)
    if inner_filename:
        suffix = Path(inner_filename).suffix.lower()
        if fmt == "full" and suffix != ".xcollx":
            errors.append(f"Full format should use .xcollx extension, got '{suffix}'")

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
        errors.append(
            f"'created' must be an ISO 8601 string, got {type(created).__name__}"
        )

    # items (required, non-empty)
    items = data.get("items")
    if not isinstance(items, list):
        errors.append("Missing or invalid 'items' array")
        return errors

    if not items:
        errors.append("Collection has no items")

    for i, item in enumerate(items):
        mt = item.get("media_type")
        if not mt:
            errors.append(f"Item {i}: missing media_type")
        elif mt not in VALID_MEDIA_TYPES:
            errors.append(f"Item {i}: invalid media_type '{mt}'")

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


def validate_xcoll(path):
    """Validate a .xcoll/.xcollx file."""
    errors = []

    # Check filename is kebab-case
    stem = path.stem
    if not KEBAB_CASE_RE.match(stem):
        errors.append(f"Filename must be kebab-case: '{stem}' (e.g. 'best-rpgs')")

    try:
        data = load_json_from_path(path)
    except json.JSONDecodeError as e:
        return errors + [f"Invalid JSON: {e}"]

    # Verify extension matches format
    suffix = path.suffix.lower()
    fmt = data.get("format")
    if fmt == "full" and suffix != ".xcollx":
        errors.append(f"Full format should use .xcollx extension, got '{suffix}'")
    if fmt == "light" and suffix not in XCOLL_EXTENSIONS:
        errors.append(f"Unexpected extension '{suffix}' for format '{fmt}'")

    errors.extend(validate_xcoll_data(data, path))
    return errors


def validate_zip(path):
    """Validate a .zip file containing a .xcoll/.xcollx.

    Security checks:
    - Must be a valid zip file
    - No path traversal (../ in filenames)
    - No unexpected files (only .xcoll/.xcollx allowed)
    - Zip bomb protection (uncompressed size limit)
    - Exactly one collection file inside
    """
    errors = []
    max_uncompressed_size = 500 * 1024 * 1024  # 500 MB limit

    # Check filename is kebab-case
    stem = path.stem
    if not KEBAB_CASE_RE.match(stem):
        errors.append(f"Filename must be kebab-case: '{stem}' (e.g. 'best-rpgs')")

    if not zipfile.is_zipfile(path):
        return errors + ["Not a valid zip file"]

    try:
        with zipfile.ZipFile(path, "r") as zf:
            # Check for path traversal
            for name in zf.namelist():
                if ".." in name or name.startswith("/"):
                    errors.append(f"Suspicious path in zip: '{name}'")
                    return errors

            # Check all files have allowed extensions
            for name in zf.namelist():
                if name.endswith("/"):
                    continue  # skip directories
                if not name.lower().endswith(XCOLL_EXTENSIONS):
                    errors.append(
                        f"Unexpected file in zip: '{name}' "
                        f"(only .xcoll/.xcollx allowed)"
                    )

            if errors:
                return errors

            # Check total uncompressed size (zip bomb protection)
            total_size = sum(info.file_size for info in zf.infolist())
            if total_size > max_uncompressed_size:
                errors.append(
                    f"Uncompressed size too large: {total_size / 1024 / 1024:.0f} MB "
                    f"(limit: {max_uncompressed_size / 1024 / 1024:.0f} MB)"
                )
                return errors
    except zipfile.BadZipFile:
        return errors + ["Corrupted zip file"]

    try:
        data, inner = load_json_from_zip(path)
    except ValueError as e:
        return errors + [str(e)]
    except json.JSONDecodeError as e:
        return errors + [f"Invalid JSON inside zip: {e}"]

    errors.extend(validate_xcoll_data(data, path, inner_filename=inner))
    return errors


def validate_platform(path):
    """Validate a _platform.json file."""
    errors = []

    try:
        data = load_json_from_path(path)
    except json.JSONDecodeError as e:
        return [f"Invalid JSON: {e}"]

    for field in REQUIRED_PLATFORM_FIELDS:
        if field not in data:
            errors.append(f"Missing required field: {field}")

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
        data = load_json_from_path(path)
    except json.JSONDecodeError as e:
        return [f"Invalid JSON: {e}"]

    for field in REQUIRED_MEDIA_FIELDS:
        if field not in data:
            errors.append(f"Missing required field: {field}")

    parent_name = path.parent.name
    if data.get("id") and data["id"] != parent_name:
        errors.append(f"id '{data['id']}' does not match folder name '{parent_name}'")

    return errors


def check_files(pattern, validator):
    """Run validator on all files matching pattern. Returns error count."""
    error_count = 0
    for path in sorted(Path(".").rglob(pattern)):
        errors = validator(path)
        if errors:
            print(f"FAIL {path}")
            for error in errors:
                print(f"   - {error}")
            error_count += 1
        else:
            print(f"OK   {path}")
    return error_count


def main():
    errors = 0

    # Validate .xcoll, .xcollx, and .zip files
    errors += check_files("*.xcoll", validate_xcoll)
    errors += check_files("*.xcollx", validate_xcoll)
    errors += check_files("*.zip", validate_zip)

    # Validate _platform.json files
    if Path("platforms").exists():
        errors += check_files("platforms/**/_platform.json", validate_platform)

    # Validate _media.json files
    if Path("media").exists():
        errors += check_files("media/**/_media.json", validate_media)

    if errors:
        print(f"\nValidation failed! ({errors} file(s) with errors)")
        sys.exit(1)

    print("\nAll files valid!")


if __name__ == "__main__":
    main()
