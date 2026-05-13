"""Build platform-exclusive game collections from Wikipedia categories.

Pipeline: Wikipedia category -> Wikidata QIDs -> IGDB slug (P5794)
         -> IGDB numeric id (+ platform verification) -> light .xcoll file.

Requires IGDB credentials. Reads from either:
- env vars IGDB_CLIENT_ID / IGDB_CLIENT_SECRET, or
- config file path passed via --igdb-config (JSON with those keys).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

UA = "tonkatsu-collections-build/0.1 (https://github.com/hacan359/tonkatsu-collections)"

# Regional / variant platform IDs treated as equivalent during exclusivity check.
# Key = canonical IGDB platform id, value = full set of acceptable ids.
# Sources verified via IGDB /platforms endpoint.
PLATFORM_ALIASES: dict[int, list[int]] = {
    18: [18, 99],         # NES + Famicom (Family Computer)
    19: [19, 58, 306],    # SNES + Super Famicom + Satellaview
    62: [62, 410],        # Atari Jaguar + Atari Jaguar CD
    86: [86, 128],        # TurboGrafx-16/PC Engine + PC Engine SuperGrafx
}

# platform_slug -> (igdb_platform_id, wikipedia_category, display_name)
PLATFORMS: dict[str, tuple[int, str, str]] = {
    "3do":           (50,  "3DO Interactive Multiplayer-only games",        "3DO"),
    "atari-2600":    (59,  "Atari 2600-only games",                          "Atari 2600"),
    "atari-7800":    (60,  "Atari 7800-only games",                          "Atari 7800"),
    "atari-jaguar":  (62,  "Atari Jaguar-only games",                        "Atari Jaguar"),
    "dreamcast":     (23,  "Dreamcast-only games",                           "Dreamcast"),
    "game-gear":     (35,  "Game Gear-only games",                           "Game Gear"),
    "gamecube":      (21,  "GameCube-only games",                            "GameCube"),
    "gb":            (33,  "Game Boy-only games",                            "Game Boy"),
    "gba":           (24,  "Game Boy Advance-only games",                    "Game Boy Advance"),
    "gbc":           (22,  "Game Boy Color-only games",                      "Game Boy Color"),
    "genesis":       (29,  "Sega Genesis-only games",                        "Sega Genesis"),
    "master-system": (64,  "Master System-only games",                       "Master System"),
    "n64":           (4,   "Nintendo 64-only games",                         "Nintendo 64"),
    "nes":           (18,  "Nintendo Entertainment System-only games",       "NES"),
    "ps1":           (7,   "PlayStation (console)-only games",               "PlayStation"),
    "ps2":           (8,   "PlayStation 2-only games",                       "PlayStation 2"),
    "ps3":           (9,   "PlayStation 3-only games",                       "PlayStation 3"),
    "ps4":           (48,  "PlayStation 4-only games",                       "PlayStation 4"),
    "ps5":           (167, "PlayStation 5-only games",                       "PlayStation 5"),
    "psp":           (38,  "PlayStation Portable-only games",                "PSP"),
    "saturn":        (32,  "Sega Saturn-only games",                         "Sega Saturn"),
    "sega-32x":      (30,  "Sega 32X-only games",                            "Sega 32X"),
    "sega-cd":       (78,  "Sega CD-only games",                             "Sega CD"),
    "snes":          (19,  "Super Nintendo Entertainment System-only games", "SNES"),
    "switch":        (130, "Nintendo Switch-only games",                     "Nintendo Switch"),
    "turbografx":    (86,  "TurboGrafx-16-only games",                       "TurboGrafx-16"),
    "wii":           (5,   "Wii-only games",                                 "Wii"),
    "xbox":          (11,  "Xbox-only games",                                "Xbox"),
    "xbox-360":      (12,  "Xbox 360-only games",                            "Xbox 360"),
    "xbox-one":      (49,  "Xbox One-only games",                            "Xbox One"),
}


def http_get_json(url: str, headers: dict[str, str] | None = None) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def http_post_json(url: str, body: bytes, headers: dict[str, str]) -> object:
    req = urllib.request.Request(
        url,
        data=body,
        headers={"User-Agent": UA, **headers},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


# ---------- Wikipedia ----------

def fetch_category_members(category: str) -> list[str]:
    titles: list[str] = []
    cont: dict[str, str] = {}
    while True:
        params = {
            "action": "query", "list": "categorymembers", "format": "json",
            "cmtitle": f"Category:{category}", "cmlimit": "500", "cmtype": "page",
        }
        params.update(cont)
        url = "https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode(params)
        d = http_get_json(url)
        titles += [m["title"] for m in d["query"]["categorymembers"]]
        if "continue" not in d:
            break
        cont = d["continue"]
        time.sleep(0.1)
    return titles


def fetch_qids(titles: list[str]) -> dict[str, str | None]:
    """Returns title -> qid (None if no Wikidata link)."""
    out: dict[str, str | None] = {}
    for i in range(0, len(titles), 50):
        chunk = titles[i:i + 50]
        params = {
            "action": "query", "format": "json", "prop": "pageprops",
            "redirects": "1", "titles": "|".join(chunk),
        }
        url = "https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode(params)
        d = http_get_json(url)
        normalized = {n["from"]: n["to"]
                      for n in d.get("query", {}).get("normalized", [])}
        redirects = {r["from"]: r["to"]
                     for r in d.get("query", {}).get("redirects", [])}
        title_by_actual: dict[str, str] = {}
        for t in chunk:
            actual = normalized.get(t, t)
            actual = redirects.get(actual, actual)
            title_by_actual[actual] = t
        for p in d["query"]["pages"].values():
            qid = (p.get("pageprops") or {}).get("wikibase_item")
            orig = title_by_actual.get(p["title"], p["title"])
            out[orig] = qid
        time.sleep(0.1)
    return out


# ---------- Wikidata ----------

def fetch_igdb_slugs(qids: list[str]) -> dict[str, str | None]:
    """Returns qid -> igdb slug (None if no P5794 claim)."""
    out: dict[str, str | None] = {}
    for i in range(0, len(qids), 50):
        chunk = qids[i:i + 50]
        params = {
            "action": "wbgetentities", "format": "json",
            "props": "claims", "ids": "|".join(chunk),
        }
        url = "https://www.wikidata.org/w/api.php?" + urllib.parse.urlencode(params)
        d = http_get_json(url)
        for qid, ent in d.get("entities", {}).items():
            claims = (ent.get("claims") or {}).get("P5794", [])
            slug: str | None = None
            for c in claims:
                ds = c.get("mainsnak", {}).get("datavalue", {}).get("value")
                if isinstance(ds, str) and ds:
                    slug = ds
                    break
            out[qid] = slug
        time.sleep(0.1)
    return out


# ---------- IGDB ----------

@dataclass
class IgdbAuth:
    client_id: str
    client_secret: str
    token: str = ""
    expires_at: int = 0

    def ensure_token(self) -> None:
        if self.token and time.time() < self.expires_at - 60:
            return
        body = urllib.parse.urlencode({
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "client_credentials",
        }).encode()
        r = http_post_json("https://id.twitch.tv/oauth2/token", body,
                           {"Content-Type": "application/x-www-form-urlencoded"})
        assert isinstance(r, dict)
        self.token = r["access_token"]
        self.expires_at = int(time.time()) + int(r["expires_in"])

    def headers(self) -> dict[str, str]:
        self.ensure_token()
        return {
            "Client-ID": self.client_id,
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "text/plain",
        }


def fetch_games_by_slug(auth: IgdbAuth, slugs: list[str]) -> list[dict]:
    out: list[dict] = []
    for i in range(0, len(slugs), 500):
        chunk = slugs[i:i + 500]
        quoted = ",".join(f'"{s}"' for s in chunk)
        body = (
            f"fields id,slug,name,platforms;"
            f" where slug = ({quoted}); limit 500;"
        ).encode()
        r = http_post_json("https://api.igdb.com/v4/games", body, auth.headers())
        assert isinstance(r, list)
        out += r
        time.sleep(0.3)  # be polite (igdb cap is 4 req/s)
    return out


import re as _re

# Strip ANY parenthetical group in the title (Wikipedia disambiguators are
# always parenthesized, so removing all parens is safe for our pipeline).
_PARENS_RE = _re.compile(r"\s*\([^()]*\)")


def _strip_disambig(t: str) -> str:
    """Drop all parenthetical groups; applied repeatedly for nested cases."""
    prev = None
    while prev != t:
        prev = t
        t = _PARENS_RE.sub("", t)
    return " ".join(t.split())


def _normalize_title(t: str) -> str:
    return " ".join(_strip_disambig(t).lower().split())


def _word_tokens(t: str) -> set[str]:
    """Lowercase alphanumeric word tokens (strips punctuation)."""
    return set(_re.findall(r"[a-z0-9]+", _strip_disambig(t).lower()))


def _igdb_query_with_retry(
    auth: IgdbAuth, body: bytes, attempts: int = 4,
) -> list | None:
    """POST /games with retry/backoff on transient errors."""
    delay = 1.0
    last_err: Exception | None = None
    for _ in range(attempts):
        try:
            r = http_post_json("https://api.igdb.com/v4/games", body, auth.headers())
            time.sleep(0.3)
            return r if isinstance(r, list) else []
        except Exception as e:  # urllib HTTPError, URLError, etc.
            last_err = e
            time.sleep(delay)
            delay = min(delay * 2, 8.0)
    print(f"  ! igdb query failed after {attempts} attempts: {last_err}")
    return None


def igdb_search_for_platform(
    auth: IgdbAuth, title: str, allowed: list[int],
) -> dict | None:
    """Search IGDB by title, return best match with platform in [allowed].

    Title is sanitized: strips trailing parens disambiguation before sending
    to IGDB's fuzzy matcher (the parens otherwise tank relevance).
    Falls back to unfiltered search if the platform-filtered query yields
    nothing — accepted only on exact name match AND empty IGDB platforms
    list (i.e. IGDB knows the game but hasn't tagged platforms; we trust
    the Wikipedia category as authority).
    """
    clean = _strip_disambig(title)
    norm_query = clean.replace('"', '\\"')
    target = _normalize_title(title)
    allowed_set = set(allowed)

    # Pass 1: platform-filtered search.
    quoted_pids = ",".join(str(p) for p in allowed)
    body = (
        f'search "{norm_query}"; fields id,name,slug,platforms;'
        f' where platforms = ({quoted_pids}); limit 10;'
    ).encode()
    r = _igdb_query_with_retry(auth, body)
    if r:
        # Exact normalized name match wins outright.
        for g in r:
            if _normalize_title(g.get("name", "")) == target:
                return g
        # Single result on platform-filtered search: trust it.
        # ("Shox" wiki -> "Shox: Rally Reinvented" igdb, with platform=PS2)
        if len(r) == 1:
            return r[0]
        # Multiple results: require token overlap (punctuation stripped).
        target_tokens = _word_tokens(title)
        top = r[0]
        top_tokens = _word_tokens(top.get("name", ""))
        if target_tokens and top_tokens and len(target_tokens & top_tokens) / max(
            len(target_tokens), len(top_tokens)
        ) >= 0.6:
            return top
        # Title that's a single distinctive word also wins on top hit
        # if that word fully appears in top tokens.
        if len(target_tokens) == 1 and target_tokens.issubset(top_tokens):
            return top

    # Pass 2: unfiltered search, accept exact match if platforms empty
    # (IGDB has the entry but didn't tag platforms — trust Wikipedia).
    body2 = (
        f'search "{norm_query}"; fields id,name,slug,platforms; limit 10;'
    ).encode()
    r2 = _igdb_query_with_retry(auth, body2)
    if not r2:
        return None
    for g in r2:
        if _normalize_title(g.get("name", "")) != target:
            continue
        pls = g.get("platforms") or []
        if not pls or allowed_set.intersection(pls):
            return g
    return None


# ---------- Build ----------

@dataclass
class PlatformReport:
    slug: str
    wiki_titles: int = 0
    with_qid: int = 0
    with_igdb_slug: int = 0
    igdb_resolved: int = 0
    platform_verified: int = 0
    recovered_by_search: int = 0
    items: int = 0
    unresolved_no_qid: list[str] = field(default_factory=list)
    unresolved_no_slug: list[tuple[str, str]] = field(default_factory=list)
    unresolved_slug_404: list[tuple[str, str]] = field(default_factory=list)
    not_exclusive: list[tuple[str, int, list[int]]] = field(default_factory=list)
    not_found_in_igdb: list[str] = field(default_factory=list)


def build_xcoll(
    *,
    name: str,
    items: list[dict],
    description: str,
) -> dict:
    return {
        "version": 2,
        "format": "light",
        "name": name,
        "author": "tonkatsu-collections",
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "description": description,
        "items": items,
    }


def run_platform(
    auth: IgdbAuth,
    slug: str,
    platform_id: int,
    category: str,
    display: str,
    out_dir: Path,
    cache_dir: Path,
) -> PlatformReport:
    rep = PlatformReport(slug=slug)
    cache_file = cache_dir / f"{slug}.json"

    if cache_file.exists():
        cached = json.loads(cache_file.read_text(encoding="utf-8"))
        titles: list[str] = cached["titles"]
        title_qid: dict[str, str | None] = cached["title_qid"]
        qid_slug: dict[str, str | None] = cached["qid_slug"]
    else:
        titles = fetch_category_members(category)
        title_qid = fetch_qids(titles)
        qids = [q for q in title_qid.values() if q]
        qid_slug = fetch_igdb_slugs(qids)
        cache_file.write_text(json.dumps({
            "titles": titles, "title_qid": title_qid, "qid_slug": qid_slug,
        }, ensure_ascii=False, indent=2), encoding="utf-8")

    rep.wiki_titles = len(titles)
    rep.with_qid = sum(1 for q in title_qid.values() if q)
    rep.with_igdb_slug = sum(1 for s in qid_slug.values() if s)

    # title -> (qid, slug) for items kept
    title_to_slug: dict[str, str] = {}
    for title in titles:
        qid = title_qid.get(title)
        if not qid:
            rep.unresolved_no_qid.append(title)
            continue
        s = qid_slug.get(qid)
        if not s:
            rep.unresolved_no_slug.append((title, qid))
            continue
        title_to_slug[title] = s

    unique_slugs = list(set(title_to_slug.values()))
    games = fetch_games_by_slug(auth, unique_slugs)
    by_slug = {g["slug"]: g for g in games}
    rep.igdb_resolved = len(games)

    allowed = PLATFORM_ALIASES.get(platform_id, [platform_id])
    allowed_set = set(allowed)

    items: list[dict] = []
    seen_ids: set[int] = set()

    def _add(title: str, g: dict) -> None:
        if g["id"] in seen_ids:
            return
        seen_ids.add(g["id"])
        items.append({
            "media_type": "game",
            "external_id": g["id"],
            "platform_id": platform_id,
            "comment": f"https://en.wikipedia.org/wiki/"
                       f"{urllib.parse.quote(title.replace(' ', '_'))}",
        })

    # Pass 1: slugs from Wikidata.
    needs_search: list[str] = []
    for title, igdb_slug in title_to_slug.items():
        g = by_slug.get(igdb_slug)
        if not g:
            rep.unresolved_slug_404.append((title, igdb_slug))
            needs_search.append(title)
            continue
        platforms = g.get("platforms") or []
        if not platforms:
            # IGDB stub with no platforms -> Wikidata may point at a duplicate.
            # Fall through to name search for a better entry.
            rep.unresolved_slug_404.append((title, igdb_slug))
            needs_search.append(title)
            continue
        if not allowed_set.intersection(platforms):
            rep.not_exclusive.append((title, g["id"], platforms))
            needs_search.append(title)  # still try name search as last resort
            continue
        rep.platform_verified += 1
        _add(title, g)

    # Pass 2: name-search fallback for titles without a usable slug.
    fallback_titles = (
        rep.unresolved_no_qid
        + [t for t, _ in rep.unresolved_no_slug]
        + needs_search
    )
    for title in fallback_titles:
        g = igdb_search_for_platform(auth, title, allowed)
        if g is None:
            rep.not_found_in_igdb.append(title)
            continue
        rep.recovered_by_search += 1
        _add(title, g)

    rep.items = len(items)

    if items:
        items.sort(key=lambda it: it["external_id"])
        xcoll = build_xcoll(
            name=f"{display} Exclusives",
            items=items,
            description=(
                f"Games released exclusively on {display}, "
                f"sourced from Wikipedia category \"{category}\" and verified via IGDB."
            ),
        )
        out_path = out_dir / slug / "exclusives.xcoll"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(xcoll, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return rep


def load_igdb_auth(args: argparse.Namespace) -> IgdbAuth:
    cid = os.environ.get("IGDB_CLIENT_ID")
    csec = os.environ.get("IGDB_CLIENT_SECRET")
    if args.igdb_config:
        cfg = json.loads(Path(args.igdb_config).read_text(encoding="utf-8"))
        cid = cid or cfg.get("igdb_client_id")
        csec = csec or cfg.get("igdb_client_secret")
    if not cid or not csec:
        sys.exit("missing IGDB credentials (env or --igdb-config)")
    return IgdbAuth(client_id=cid, client_secret=csec)


def update_platform(
    auth: IgdbAuth,
    slug: str,
    platform_id: int,
    display: str,
    out_dir: Path,
    cache_dir: Path,
) -> tuple[int, int, list[str]]:
    """Append-only: search IGDB for Wikipedia titles not yet in the .xcoll.

    Returns (already_in_file, newly_added, still_missing_titles).
    """
    xcoll_path = out_dir / slug / "exclusives.xcoll"
    cache_file = cache_dir / f"{slug}.json"
    if not xcoll_path.exists() or not cache_file.exists():
        print(f"  [{slug}] skipped: missing .xcoll or cache")
        return 0, 0, []

    xcoll = json.loads(xcoll_path.read_text(encoding="utf-8"))
    items: list[dict] = xcoll.get("items", [])
    existing_ids: set[int] = {it["external_id"] for it in items}
    covered_titles: set[str] = set()
    for it in items:
        c = it.get("comment", "")
        if "/wiki/" in c:
            t = urllib.parse.unquote(c.split("/wiki/", 1)[1]).replace("_", " ")
            covered_titles.add(t)

    cache = json.loads(cache_file.read_text(encoding="utf-8"))
    wiki_titles: list[str] = cache["titles"]
    missing = [t for t in wiki_titles if t not in covered_titles]

    allowed = PLATFORM_ALIASES.get(platform_id, [platform_id])
    added: list[tuple[str, dict]] = []
    still_missing: list[str] = []
    for title in missing:
        g = igdb_search_for_platform(auth, title, allowed)
        if g is None or g["id"] in existing_ids:
            if g is None:
                still_missing.append(title)
            continue
        existing_ids.add(g["id"])
        items.append({
            "media_type": "game",
            "external_id": g["id"],
            "platform_id": platform_id,
            "comment": f"https://en.wikipedia.org/wiki/"
                       f"{urllib.parse.quote(title.replace(' ', '_'))}",
        })
        added.append((title, g))

    if added:
        items.sort(key=lambda it: it["external_id"])
        xcoll["items"] = items
        xcoll_path.write_text(
            json.dumps(xcoll, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return len(covered_titles), len(added), still_missing


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--platforms", nargs="*",
                    help="Subset of platform slugs to build (default: all).")
    ap.add_argument("--igdb-config",
                    help="JSON file with igdb_client_id/igdb_client_secret.")
    ap.add_argument("--root", default=str(Path(__file__).resolve().parent.parent),
                    help="Repo root (default: parent of this script's dir).")
    ap.add_argument("--update", action="store_true",
                    help="Append-only mode: only search for titles not already "
                         "in existing exclusives.xcoll. Does not rebuild.")
    args = ap.parse_args()

    root = Path(args.root)
    out_dir = root / "platforms"
    cache_dir = root / "scripts" / ".cache" / "exclusives"
    cache_dir.mkdir(parents=True, exist_ok=True)

    auth = load_igdb_auth(args)

    targets = args.platforms or list(PLATFORMS.keys())

    if args.update:
        print("UPDATE MODE: appending search-by-name finds to existing .xcoll\n")
        update_missing: dict[str, list[str]] = {}
        total_added = 0
        for slug in targets:
            if slug not in PLATFORMS:
                print(f"[skip] unknown platform: {slug}")
                continue
            platform_id, _, display = PLATFORMS[slug]
            covered, added, still = update_platform(
                auth, slug, platform_id, display, out_dir, cache_dir,
            )
            total_added += added
            update_missing[slug] = still
            print(f"[{slug}] had={covered} +added={added} still_missing={len(still)}")
        # rewrite missing.txt for update results
        miss_path = cache_dir / "missing_after_update.txt"
        with miss_path.open("w", encoding="utf-8") as f:
            for slug, titles in update_missing.items():
                if not titles:
                    continue
                f.write(f"# {slug}\n")
                for t in titles:
                    f.write(f"  [not in IGDB] {t}\n")
                f.write("\n")
        print(f"\nTOTAL added: {total_added}\nremaining: {miss_path}")
        return

    reports: list[PlatformReport] = []
    for slug in targets:
        if slug not in PLATFORMS:
            print(f"[skip] unknown platform: {slug}")
            continue
        platform_id, category, display = PLATFORMS[slug]
        print(f"[{slug}] fetching...", flush=True)
        rep = run_platform(auth, slug, platform_id, category, display,
                           out_dir, cache_dir)
        reports.append(rep)
        print(
            f"[{slug}] wiki={rep.wiki_titles} qid={rep.with_qid} "
            f"slug={rep.with_igdb_slug} resolved={rep.igdb_resolved} "
            f"ver={rep.platform_verified} +search={rep.recovered_by_search} "
            f"-> items={rep.items}  missing={len(rep.not_found_in_igdb)}"
        )

    # summary
    print()
    print(f'{"platform":<14} {"wiki":>5} {"verif":>6} {"+srch":>6} '
          f'{"out":>5} {"miss":>5} {"reject":>7}')
    print("-" * 54)
    for r in reports:
        print(f'{r.slug:<14} {r.wiki_titles:>5} {r.platform_verified:>6} '
              f'{r.recovered_by_search:>6} {r.items:>5} '
              f'{len(r.not_found_in_igdb):>5} {len(r.not_exclusive):>7}')

    # detailed report file
    report_path = cache_dir / "report.json"
    report_path.write_text(json.dumps([{
        "slug": r.slug,
        "wiki_titles": r.wiki_titles,
        "with_qid": r.with_qid,
        "with_igdb_slug": r.with_igdb_slug,
        "igdb_resolved": r.igdb_resolved,
        "platform_verified": r.platform_verified,
        "recovered_by_search": r.recovered_by_search,
        "items": r.items,
        "not_found_in_igdb": r.not_found_in_igdb,
        "not_exclusive": r.not_exclusive,
        "unresolved_no_qid": r.unresolved_no_qid,
        "unresolved_no_slug": r.unresolved_no_slug,
        "unresolved_slug_404": r.unresolved_slug_404,
    } for r in reports], ensure_ascii=False, indent=2), encoding="utf-8")

    # missing.txt -- flat list of titles to inspect by hand
    missing_path = cache_dir / "missing.txt"
    with missing_path.open("w", encoding="utf-8") as f:
        for r in reports:
            if not r.not_found_in_igdb and not r.not_exclusive:
                continue
            f.write(f"# {r.slug}\n")
            for t in r.not_found_in_igdb:
                f.write(f"  [not in IGDB] {t}\n")
            for t, gid, pls in r.not_exclusive:
                f.write(f"  [other platforms] {t}  (igdb:{gid}, platforms:{pls})\n")
            f.write("\n")
    print(f"\nfull report: {report_path}\nmissing list: {missing_path}")


if __name__ == "__main__":
    main()
