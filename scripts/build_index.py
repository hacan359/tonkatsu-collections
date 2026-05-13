#!/usr/bin/env python3
"""
Generates index.json from all .xcoll/.xcollx/.zip files in the repository.
Runs automatically via GitHub Actions on push to main.

Reads native Tonkatsu Box XcollFile format (v2) and extracts metadata
for the collection browser in the app. Supports zip-compressed collections.
"""

import json
import os
import zipfile
from pathlib import Path
from datetime import datetime, timezone

XCOLL_EXTENSIONS = (".xcoll", ".xcollx")


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_xcoll(path):
    """Load collection data from .xcoll, .xcollx, or .zip file."""
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path, "r") as zf:
            xcoll_files = [
                n for n in zf.namelist() if n.lower().endswith(XCOLL_EXTENSIONS)
            ]
            if not xcoll_files:
                raise ValueError(f"No .xcoll/.xcollx found inside {path}")
            raw = zf.read(xcoll_files[0])
            return json.loads(raw.decode("utf-8"))
    return load_json(path)


def get_file_size(path):
    return os.path.getsize(path)


def detect_category(xcoll_data, filename):
    """Detect collection category from file content or naming convention."""
    # Check if description hints at complete library
    desc = (xcoll_data.get("description") or "").lower()
    name = (xcoll_data.get("name") or "").lower()

    if "top" in filename or "top " in name or "best " in name or "highest rated" in desc:
        return "curated"
    if "hidden" in filename or "hidden gem" in name:
        return "hidden-gems"
    if "complete" in filename or "complete" in desc or "all games" in desc or "full library" in desc:
        return "complete"

    return "curated"


def scan_xcoll_files(directory):
    """Find all .xcoll, .xcollx, and .zip files in a directory."""
    files = []
    if directory.exists():
        for ext in ("*.xcoll", "*.xcollx", "*.zip"):
            files.extend(sorted(directory.rglob(ext)))
    return files


def list_xcoll_files(directory):
    """List .xcoll, .xcollx, and .zip files in a single directory."""
    files = []
    for ext in ("*.xcoll", "*.xcollx", "*.zip"):
        files.extend(sorted(directory.glob(ext)))
    return files


def build_index():
    collections = []
    platforms = {}
    media_types = {}

    # === Scan platforms/ ===
    platforms_dir = Path("platforms")

    if platforms_dir.exists():
        for platform_dir in sorted(platforms_dir.iterdir()):
            if not platform_dir.is_dir():
                continue

            platform_meta_path = platform_dir / "_platform.json"
            if not platform_meta_path.exists():
                print(f"Warning: {platform_dir} has no _platform.json, skipping")
                continue

            platform_meta = load_json(platform_meta_path)
            platform_id = platform_meta["id"]

            platforms[platform_id] = {
                "id": platform_id,
                "name": platform_meta.get("name", platform_id),
                "shortName": platform_meta.get("shortName", platform_id.upper()),
                "igdbId": platform_meta.get("igdbId"),
                "manufacturer": platform_meta.get("manufacturer"),
                "releaseYear": platform_meta.get("releaseYear"),
                "collectionsCount": 0,
                "gamesCount": 0,
            }

            # Scan .xcoll and .xcollx files
            xcoll_files = list_xcoll_files(platform_dir)
            for xcoll_path in xcoll_files:
                if xcoll_path.name.startswith("_"):
                    continue
                try:
                    xcoll = load_xcoll(xcoll_path)
                    items = xcoll.get("items", [])
                    category = detect_category(xcoll, xcoll_path.stem)

                    collection_id = f"{platform_id}-{xcoll_path.stem}"

                    collection = {
                        "id": collection_id,
                        "name": xcoll.get("name", xcoll_path.stem),
                        "description": xcoll.get("description", ""),
                        "mediaType": "game",
                        "platform": platform_id,
                        "platformName": platform_meta.get(
                            "shortName", platform_id.upper()
                        ),
                        "category": category,
                        "itemsCount": len(items),
                        "author": xcoll.get("author", "unknown"),
                        "format": xcoll.get("format", "light"),
                        "file": str(xcoll_path).replace("\\", "/"),
                        "created": xcoll.get("created"),
                        "size": get_file_size(xcoll_path),
                    }

                    collections.append(collection)
                    platforms[platform_id]["collectionsCount"] += 1
                    platforms[platform_id]["gamesCount"] += len(items)

                except Exception as e:
                    print(f"Error processing {xcoll_path}: {e}")

    # === Scan media/ ===
    media_dir = Path("media")

    if media_dir.exists():
        for type_dir in sorted(media_dir.iterdir()):
            if not type_dir.is_dir():
                continue

            media_meta_path = type_dir / "_media.json"
            if not media_meta_path.exists():
                print(f"Warning: {type_dir} has no _media.json, skipping")
                continue

            media_meta = load_json(media_meta_path)
            media_id = media_meta["id"]

            media_types[media_id] = {
                "id": media_id,
                "name": media_meta.get("name", media_id),
                "shortName": media_meta.get("shortName", media_id),
                "source": media_meta.get("source", "TMDB"),
                "collectionsCount": 0,
                "itemsCount": 0,
            }

            xcoll_files = list_xcoll_files(type_dir)
            for xcoll_path in xcoll_files:
                if xcoll_path.name.startswith("_"):
                    continue
                try:
                    xcoll = load_xcoll(xcoll_path)
                    items = xcoll.get("items", [])
                    category = detect_category(xcoll, xcoll_path.stem)

                    collection_id = f"{media_id}-{xcoll_path.stem}"

                    collection = {
                        "id": collection_id,
                        "name": xcoll.get("name", xcoll_path.stem),
                        "description": xcoll.get("description", ""),
                        "mediaType": media_id,
                        "platform": None,
                        "platformName": None,
                        "category": category,
                        "itemsCount": len(items),
                        "author": xcoll.get("author", "unknown"),
                        "format": xcoll.get("format", "light"),
                        "file": str(xcoll_path).replace("\\", "/"),
                        "created": xcoll.get("created"),
                        "size": get_file_size(xcoll_path),
                    }

                    collections.append(collection)
                    media_types[media_id]["collectionsCount"] += 1
                    media_types[media_id]["itemsCount"] += len(items)

                except Exception as e:
                    print(f"Error processing {xcoll_path}: {e}")

    # === Scan curated/ ===
    curated_dir = Path("curated")

    if curated_dir.exists():
        xcoll_files = list_xcoll_files(curated_dir)
        for xcoll_path in xcoll_files:
            try:
                xcoll = load_xcoll(xcoll_path)
                items = xcoll.get("items", [])

                collection = {
                    "id": xcoll_path.stem,
                    "name": xcoll.get("name", xcoll_path.stem),
                    "description": xcoll.get("description", ""),
                    "mediaType": "mixed",
                    "platform": None,
                    "platformName": None,
                    "category": detect_category(xcoll, xcoll_path.stem),
                    "itemsCount": len(items),
                    "author": xcoll.get("author", "unknown"),
                    "format": xcoll.get("format", "light"),
                    "file": str(xcoll_path).replace("\\", "/"),
                    "created": xcoll.get("created"),
                    "size": get_file_size(xcoll_path),
                }

                collections.append(collection)

            except Exception as e:
                print(f"Error processing {xcoll_path}: {e}")

    # === Build index ===
    total_items = sum(c["itemsCount"] for c in collections)

    index = {
        "version": 1,
        "generated": datetime.now(timezone.utc).isoformat(),
        "totalCollections": len(collections),
        "totalItems": total_items,
        "platforms": sorted(platforms.values(), key=lambda p: p["name"]),
        "mediaTypes": sorted(media_types.values(), key=lambda m: m["name"]),
        "collections": collections,
        "categories": [
            {
                "id": "complete",
                "name": "Complete Libraries",
                "description": "All titles for a platform",
            },
            {
                "id": "curated",
                "name": "Curated Lists",
                "description": "Hand-picked selections",
            },
            {
                "id": "hidden-gems",
                "name": "Hidden Gems",
                "description": "Underrated classics",
            },
            {
                "id": "challenge",
                "name": "Challenges",
                "description": "Gaming challenges",
            },
        ],
    }

    with open("index.json", "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)

    # Mirror for the GitHub Pages site (served from /docs).
    docs_data = Path("docs/data")
    docs_data.mkdir(parents=True, exist_ok=True)
    with open(docs_data / "index.json", "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)

    print(f"Generated index.json")
    print(f"  Collections: {len(collections)}")
    print(f"  Platforms: {len(platforms)}")
    print(f"  Media types: {len(media_types)}")
    print(f"  Total items: {total_items}")


if __name__ == "__main__":
    build_index()
