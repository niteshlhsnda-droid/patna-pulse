# Patna News Watch

A static, mobile-friendly dashboard of current Patna & Bihar news, published via GitHub Pages.
No build step, no API keys, no backend — just Python (standard library only) + static files.

**Live site:** https://niteshlhsnda-droid.github.io/patna-news-watch/

## What it shows

- Newest stories first, covering the last 7 days of Patna/Bihar news.
- Every story card shows its headline, date, topic tags, and every source link found.
- A **genuineness badge** on each story, based purely on how many *independent outlets*
  reported the same story:
  - 🟢 **Verified** — 3 or more independent outlets
  - 🟡 **Corroborated** — 2 independent outlets
  - ⚪ **Single source** — 1 outlet; treat with caution

**Important:** corroboration counts how many outlets reported a story. It is *not* proof
the story is true. Outlets can repeat the same wire copy or the same unverified claim.
Always open the source links and judge for yourself. This disclaimer is also shown on the site.

## How it works

```
python3 generate.py   # collects RSS + merges curated.json -> data.json
```

1. **RSS collection** — `generate.py` fetches Google News RSS feeds for Patna/Bihar
   queries (English + Hindi), keeps items from the last 7 days, and clusters
   near-duplicate headlines by keyword overlap.
2. **Hand-verified items** — `curated.json` holds stories collected via web/social
   search, each with real source URLs (news sites, Facebook, Instagram, YouTube).
   These are always shown, even when single-source.
3. **Scoring** — outlets are deduplicated (two articles from the same outlet count once),
   then the badge is assigned from the distinct-outlet count.
4. **Noise filter** — auto-collected clusters with only one outlet are dropped;
   near-duplicate clusters (same event, different phrasing or language) are merged
   via rules in `MANUAL_MERGES`.

`index.html` + `styles.css` + `app.js` render `data.json` with topic chips,
genuineness filters, and search. To refresh the site, re-run `generate.py` and
commit the updated `data.json`.

## Source coverage & limitations

- **News websites:** covered via Google News RSS (TOI, NDTV, Indian Express,
  Deccan Herald, Hindustan Times, Dainik Jagran, News18, etc.).
- **Facebook / Instagram / YouTube:** represented through manually collected public
  links in `curated.json` (e.g. PTI, News18 Bihar, Patna Press, Town Post).
  Automated collection from these platforms isn't possible without logins/APIs,
  so coverage here is best-effort.
- **X (Twitter):** no usable public links were found during collection
  (search results were login-walled or linkless). Nothing is shown for X rather
  than fabricating it.
- Some outlets block automated fetching; their stories appear only if found via
  Google News or manual collection.
- Nothing on this page is invented: every card links to real, retrievable sources.

## Files

| File | Purpose |
|---|---|
| `generate.py` | Collector, deduper, scorer (stdlib only) |
| `curated.json` | Hand-verified stories with real source URLs |
| `data.json` | Generated feed consumed by the page |
| `index.html` / `styles.css` / `app.js` | The dashboard |
