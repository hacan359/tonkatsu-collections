# Contributing to Tonkatsu Collections

Thanks for wanting to contribute! Here's how to add your own collections.

## The Easy Way

1. Build your collection in [Tonkatsu Box](https://github.com/hacan359/tonkatsu_box)
2. Export it (light `.xcoll` or full `.xcollx`)
3. Fork this repo
4. Place the file in the correct folder (see below)
5. Create a Pull Request
6. CI validates your file automatically
7. Get merged!

## Where to Put Your Collection

| Type | Location |
|------|----------|
| Platform-specific (all SNES games, best NES RPGs) | `platforms/{platform}/your-collection.xcoll` |
| Movies / TV Shows / Anime | `media/{type}/your-collection.xcoll` |
| Cross-platform / mixed media | `curated/your-collection.xcoll` |

## Rules

1. **One collection = one file** — don't edit multiple collections in one PR
2. **Don't edit index.json** — it's auto-generated
3. **Use correct folder** — see table above
4. **Filename is kebab-case** — `best-rpgs.xcoll` not `Best RPGs.xcoll`
5. **Export from Tonkatsu Box** — this guarantees valid format

## File Format

Files are standard Tonkatsu Box exports. Light export (`.xcoll`):

```json
{
  "version": 2,
  "format": "light",
  "name": "Best SNES RPGs",
  "author": "your-username",
  "created": "2026-04-03T12:00:00Z",
  "description": "Must-play RPGs for Super Nintendo",
  "items": [
    {
      "media_type": "game",
      "external_id": 1234,
      "platform_id": 19
    }
  ]
}
```

Full export (`.xcollx`) includes canvas layout, cover images, and embedded media data for offline import.

Both formats are accepted. See [RCOLL_FORMAT.md](https://github.com/hacan359/tonkatsu_box/blob/main/docs/RCOLL_FORMAT.md) for full specification.

## Before Submitting

- [ ] File exported from Tonkatsu Box (or valid JSON matching the format)
- [ ] No duplicate items
- [ ] File is in the correct folder
- [ ] Filename is kebab-case

## Adding a New Platform

If your platform doesn't have a folder yet:

1. Create `platforms/{platform-id}/`
2. Add `_platform.json`:

```json
{
  "id": "platform-id",
  "name": "Full Platform Name",
  "shortName": "SHORT",
  "igdbId": 123
}
```

3. Add your `.xcoll`/`.xcollx` file

## Ideas for Collections

- Best games of a specific decade (80s, 90s, 2000s)
- Genre-specific (metroidvanias, shmups, fighting games)
- Regional exclusives (Japan-only, PAL-only)
- Games with specific features (co-op, 4-player, link cable)
- Personal "best of" lists
- Challenge sets (beat these 12 games in 2026)
- Best sci-fi movies, horror TV shows, studio Ghibli films

## Questions?

Open an [issue](https://github.com/hacan359/tonkatsu-collections/issues) or ask in discussions!
