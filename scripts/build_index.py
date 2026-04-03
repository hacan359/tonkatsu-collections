#!/usr/bin/env python3
"""
Generates index.json from all .xcoll files in the repository.
Runs automatically via GitHub Actions on push to main.
"""

import json
import os
from pathlib import Path
from datetime import datetime, timezone


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_file_size(path):
    return os.path.getsize(path)


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

            for xcoll_path in sorted(platform_dir.glob("*.xcoll")):
                try:
                    xcoll = load_json(xcoll_path)
                    meta = xcoll.get("meta", {})
                    items = xcoll.get("items", [])

                    collection_id = f"{platform_id}-{xcoll_path.stem}"

                    collection = {
                        "id": collection_id,
                        "name": meta.get("name", xcoll_path.stem),
                        "description": meta.get("description", ""),
                        "mediaType": "game",
                        "platform": platform_id,
                        "platformName": platform_meta.get(
                            "shortName", platform_id.upper()
                        ),
                        "category": meta.get("category", "complete"),
                        "tags": meta.get("tags", []),
                        "itemsCount": len(items),
                        "author": meta.get("author", "unknown"),
                        "file": str(xcoll_path).replace("\\", "/"),
                        "created": meta.get("created"),
                        "updated": meta.get("updated"),
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

            for xcoll_path in sorted(type_dir.glob("*.xcoll")):
                try:
                    xcoll = load_json(xcoll_path)
                    meta = xcoll.get("meta", {})
                    items = xcoll.get("items", [])

                    collection_id = f"{media_id}-{xcoll_path.stem}"

                    collection = {
                        "id": collection_id,
                        "name": meta.get("name", xcoll_path.stem),
                        "description": meta.get("description", ""),
                        "mediaType": media_id,
                        "platform": None,
                        "platformName": None,
                        "category": meta.get("category", "curated"),
                        "tags": meta.get("tags", []),
                        "itemsCount": len(items),
                        "author": meta.get("author", "unknown"),
                        "file": str(xcoll_path).replace("\\", "/"),
                        "created": meta.get("created"),
                        "updated": meta.get("updated"),
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
        for xcoll_path in sorted(curated_dir.glob("*.xcoll")):
            try:
                xcoll = load_json(xcoll_path)
                meta = xcoll.get("meta", {})
                items = xcoll.get("items", [])

                collection = {
                    "id": xcoll_path.stem,
                    "name": meta.get("name", xcoll_path.stem),
                    "description": meta.get("description", ""),
                    "mediaType": "mixed",
                    "platform": None,
                    "platformName": None,
                    "category": meta.get("category", "curated"),
                    "tags": meta.get("tags", []),
                    "itemsCount": len(items),
                    "author": meta.get("author", "unknown"),
                    "file": str(xcoll_path).replace("\\", "/"),
                    "created": meta.get("created"),
                    "updated": meta.get("updated"),
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

    print(f"Generated index.json")
    print(f"  Collections: {len(collections)}")
    print(f"  Platforms: {len(platforms)}")
    print(f"  Media types: {len(media_types)}")
    print(f"  Total items: {total_items}")


if __name__ == "__main__":
    build_index()
