"""Convert platforms/*/exclusives.xcoll (light) -> exclusives.xcollx (full, no images).

Embeds IGDB metadata so the site can render game names/covers/years without
making API calls at view time. Image bytes are NOT embedded (covers reference
the IGDB CDN URL with t_cover_big resolution).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

UA = "tonkatsu-collections-build/0.1 (https://github.com/hacan359/tonkatsu-collections)"
IGDB_URL = "https://api.igdb.com/v4/games"


def http_post_json(url: str, body: bytes, headers: dict[str, str]) -> object:
    req = urllib.request.Request(
        url, data=body, headers={"User-Agent": UA, **headers},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def get_token(cid: str, csec: str) -> str:
    body = urllib.parse.urlencode({
        "client_id": cid, "client_secret": csec,
        "grant_type": "client_credentials",
    }).encode()
    req = urllib.request.Request(
        "https://id.twitch.tv/oauth2/token", data=body,
        headers={"User-Agent": UA,
                 "Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())["access_token"]


def fetch_games_full(
    cid: str, token: str, ids: list[int],
) -> dict[int, dict]:
    headers = {
        "Client-ID": cid, "Authorization": f"Bearer {token}",
        "Content-Type": "text/plain",
    }
    out: dict[int, dict] = {}
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        body = (
            "fields id,name,summary,slug,first_release_date,"
            "rating,rating_count,cover.image_id,"
            "genres.name,platforms;"
            f" where id = ({','.join(map(str, chunk))}); limit 500;"
        ).encode()
        attempts = 0
        delay = 1.0
        while True:
            try:
                r = http_post_json(IGDB_URL, body, headers)
                break
            except Exception as e:
                attempts += 1
                if attempts >= 4:
                    raise
                print(f"  ! retry after {delay}s: {e}")
                time.sleep(delay)
                delay = min(delay * 2, 8.0)
        for g in r:
            out[g["id"]] = g
        time.sleep(0.3)
    return out


def to_db_row(g: dict, cached_at: int) -> dict:
    """Mirror Game.toDb() format used by Tonkatsu Box embedded media."""
    cover_url: str | None = None
    cover = g.get("cover")
    if isinstance(cover, dict):
        img = cover.get("image_id")
        if img:
            cover_url = (
                f"https://images.igdb.com/igdb/image/upload/t_cover_big/{img}.jpg"
            )

    genres_list = g.get("genres") or []
    if genres_list and isinstance(genres_list[0], dict):
        genres_str: str | None = ",".join(
            x["name"] for x in genres_list if x.get("name")
        ) or None
    else:
        genres_str = None

    platforms = g.get("platforms") or []
    platforms_str: str | None = ",".join(map(str, platforms)) if platforms else None

    slug = g.get("slug")
    external_url = f"https://www.igdb.com/games/{slug}" if slug else None

    return {
        "id": g["id"],
        "name": g.get("name"),
        "summary": g.get("summary"),
        "cover_url": cover_url,
        "release_date": g.get("first_release_date"),
        "rating": g.get("rating"),
        "rating_count": g.get("rating_count"),
        "genres": genres_str,
        "platform_ids": platforms_str,
        "external_url": external_url,
        "cached_at": cached_at,
    }


def convert_one(
    cid: str, token: str, xcoll_path: Path,
) -> tuple[int, int]:
    """Read xcoll, fetch metadata, write xcollx, delete xcoll.

    Returns (items, missing_metadata).
    """
    xcoll = json.loads(xcoll_path.read_text(encoding="utf-8"))
    items = xcoll.get("items", [])
    ids = sorted({it["external_id"] for it in items if it.get("media_type") == "game"})
    if not ids:
        return 0, 0
    games_map = fetch_games_full(cid, token, ids)
    cached_at = int(time.time())
    games_rows = [to_db_row(games_map[i], cached_at) for i in ids if i in games_map]
    missing = [i for i in ids if i not in games_map]

    out = dict(xcoll)
    out["format"] = "full"
    out["created"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    out["media"] = {"games": games_rows}
    # No "images" block -> covers fetched from IGDB CDN at view time.

    new_path = xcoll_path.with_suffix(".xcollx")
    new_path.write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    xcoll_path.unlink()
    return len(items), len(missing)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--igdb-config", required=True,
                    help="JSON file with igdb_client_id/igdb_client_secret.")
    ap.add_argument("--root",
                    default=str(Path(__file__).resolve().parent.parent))
    ap.add_argument("--pattern", default="platforms/*/exclusives.xcoll")
    args = ap.parse_args()

    cfg = json.loads(Path(args.igdb_config).read_text(encoding="utf-8"))
    cid = cfg["igdb_client_id"]
    csec = cfg["igdb_client_secret"]
    token = get_token(cid, csec)

    root = Path(args.root)
    paths = sorted(root.glob(args.pattern))
    total_items = total_missing = 0
    for p in paths:
        slug = p.parent.name
        try:
            n, miss = convert_one(cid, token, p)
        except Exception as e:
            print(f"[{slug}] FAILED: {e}")
            continue
        total_items += n
        total_missing += miss
        size_kb = p.with_suffix(".xcollx").stat().st_size / 1024
        flag = f"  (missing meta for {miss} ids)" if miss else ""
        print(f"[{slug}] {n} items -> exclusives.xcollx ({size_kb:.0f} KB){flag}")

    print(f"\ntotal: {total_items} items across {len(paths)} platforms, "
          f"missing metadata for {total_missing} ids")


if __name__ == "__main__":
    main()
