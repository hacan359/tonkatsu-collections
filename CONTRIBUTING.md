# Contributing to Tonkatsu Collections

Thanks for wanting to contribute! Here's how to add your own collections.

## Rules

1. **One collection = one file** — don't edit multiple collections in one PR
2. **Don't edit index.json** — it's auto-generated
3. **Use correct folder** — platform collections go in `platforms/{platform}/`
4. **Validate your JSON** — make sure it's valid before submitting
5. **Include required fields** — see format below

## Where to Put Your Collection

| Type | Location |
|------|----------|
| Platform-specific (all SNES games, best NES RPGs) | `platforms/{platform}/your-collection.xcoll` |
| Movies / TV Shows / Anime | `media/{type}/your-collection.xcoll` |
| Cross-platform (best JRPGs ever, couch co-op) | `curated/your-collection.xcoll` |

## Collection Format (.xcoll)

```json
{
  "version": 2,
  "format": "light",

  "meta": {
    "name": "Your Collection Name",
    "description": "Brief description of what's in this collection",
    "author": "your-github-username",
    "category": "curated",
    "tags": ["rpg", "retro"]
  },

  "items": [
    { "externalId": 1234, "platformId": 19 },
    { "externalId": 5678, "platformId": 19 }
  ]
}
```

### Required Fields

| Field | Description |
|-------|-------------|
| `meta.name` | Collection name |
| `meta.description` | What's in this collection |
| `meta.author` | Your GitHub username |
| `meta.category` | One of: `complete`, `curated`, `hidden-gems`, `challenge` |
| `items[].externalId` | IGDB game ID or TMDB ID (depending on media type) |

### Optional Fields

| Field | Description |
|-------|-------------|
| `items[].platformId` | IGDB platform ID (for games) |
| `meta.tags` | Tags for search |
| `meta.created` | ISO date of creation |
| `meta.updated` | ISO date of last update |

### Categories

| Category | When to use |
|----------|-------------|
| `complete` | All titles for a platform/series |
| `curated` | Hand-picked selection |
| `hidden-gems` | Underrated/overlooked titles |
| `challenge` | Gaming challenges (beat X games in Y time) |

## Finding IGDB IDs

1. Go to [igdb.com](https://www.igdb.com)
2. Search for the game
3. Use the IGDB API to get the numeric ID:

```
POST https://api.igdb.com/v4/games
Body: search "Chrono Trigger"; fields id,name; limit 1;
```

## Finding TMDB IDs

1. Go to [themoviedb.org](https://www.themoviedb.org)
2. Search for the movie/show
3. The ID is in the URL: `themoviedb.org/movie/278-the-shawshank-redemption` — ID is `278`

## Before Submitting

- [ ] JSON is valid (no syntax errors)
- [ ] All required fields present
- [ ] No duplicate externalIds
- [ ] File is in correct folder
- [ ] Filename is kebab-case: `best-rpgs.xcoll`, not `Best RPGs.xcoll`

## Submitting

1. Fork this repo
2. Add your `.xcoll` file
3. Create a Pull Request
4. Wait for validation checks
5. Get merged!

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
