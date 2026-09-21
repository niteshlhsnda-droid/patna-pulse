#!/usr/bin/env python3
"""Patna News Watch — story collector and genuineness scorer.

Collects Patna/Bihar news from:
  1. RSS feeds (Google News RSS for Patna/Bihar queries + outlet feeds) — no API key needed.
  2. curated.json — hand-verified items collected via web/social search tools,
     each with real source URLs.

Stories are clustered by headline keyword overlap. Genuineness is a
corroboration heuristic based ONLY on the number of *independent outlets*
reporting the same story:
    3+ outlets -> "verified"
    2 outlets  -> "corroborated"
    1 outlet   -> "single"

This is NOT absolute truth — see README.md and the on-site disclaimer.

Usage:
    python3 generate.py            # writes data.json
    python3 generate.py --no-rss   # curated items only (offline)

Requires only the Python standard library.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

BASE = dt.datetime.now(dt.timezone.utc)
SEVEN_DAYS_AGO = BASE - dt.timedelta(days=7)

RSS_FEEDS = [
    ("Google News — Patna",
     "https://news.google.com/rss/search?q=Patna&hl=en-IN&gl=IN&ceid=IN%3Aen"),
    ("Google News — Bihar",
     "https://news.google.com/rss/search?q=Bihar&hl=en-IN&gl=IN&ceid=IN%3Aen"),
    ("Google News — Patna (Hindi)",
     "https://news.google.com/rss/search?q=%E0%A4%AA%E0%A4%9F%E0%A4%A8%E0%A4%BE&hl=hi-IN&gl=IN&ceid=IN%3Ahi"),
]

# Merge rules for near-duplicate clusters the keyword clustering splits
# (same event, different headline phrasing, or different languages).
# Format: (date, [keywords], into, headline_override)
#   into=None            -> merge matching RSS-only clusters into one story
#   into=<curated slug>  -> merge matching RSS-only clusters into that
#                          hand-verified curated story
#   headline_override    -> headline to use for a merged story (None = keep)
MANUAL_MERGES = [
    ("2026-09-21", ["ganja"], None, None),
    ("2026-09-21", ["jamui"], None,
     "Jamui harassment case: girl and boy harassed in viral videos; "
     "3 arrested, SIT formed, political row erupts"),
    ("2026-09-21", ["\u0928\u093e\u092c\u093e\u0932\u093f\u0917"],
     "minor-student-alleges-sexual-assault-in-patna-s-shastr", None),
]

# RSS-only clusters need at least this many independent outlets to be shown.
# (Curated items are hand-verified, so they are always shown.)
MIN_RSS_OUTLETS = 2

STOPWORDS = set("""
a an the and or of to in on for with at by from as is are was were be been has
have had will would can could should who what when where how why this that these
those it its into over after before between during over under news today live
bihar patna s bihar s patna s
""".split())

TOPIC_KEYWORDS = {
    "politics": ["bjp", "congress", "rjd", "jdu", "nitish", "tejashwi", "election",
                 "minister", "chief minister", "mla", "protest", "dharna", "lathi",
                 "vidhan", "poll", "political", "politics"],
    "crime": ["police", "arrest", "murder", "rape", "assault", "fraud", "cyber",
              "smuggling", "liquor", "bomb threat", "fir", "robbery", "theft",
              "molestation", "kidnap", "ganja", "drug", "narcotic", "cannabis",
              "opium"],
    "weather": ["rain", "imd", "storm", "monsoon", "weather", "lightning",
                "depression", "forecast", "alert"],
    "civic": ["flood", "airport", "railway", "train", "road", "bridge", "water",
              "municipal", "suspended", "scheme", "barrage", "embankment",
              "encroachment"],
    "education": ["exam", "bpsc", "ugmac", "counselling", "counseling", "rank card",
                  "college", "students", "school", "teacher", "university",
                  "admission", "recruitment"],
    "health": ["hospital", "ill", "food poisoning", "disease", "fever",
               "diarrhoea", "virus"],
    "entertainment": ["film", "movie", "actor", "cinema", "bollywood", "song"],
    "economy": ["mou", "crore", "lakh", "investment", "shares", "budget",
                "industry"],
}


def fetch_rss():
    """Return list of {title, link, published(datetime|None), outlet}."""
    items = []
    for feed_name, url in RSS_FEEDS:
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "patna-news-watch/1.0"})
            with urllib.request.urlopen(req, timeout=25) as resp:
                root = ET.fromstring(resp.read())
            for it in root.iter("item"):
                title = (it.findtext("title") or "").strip()
                link = (it.findtext("link") or "").strip()
                src_el = it.find("source")
                outlet = (src_el.text.strip() if src_el is not None and src_el.text
                          else feed_name)
                pub = None
                pub_txt = it.findtext("pubDate")
                if pub_txt:
                    try:
                        pub = parsedate_to_datetime(pub_txt)
                    except Exception:
                        pub = None
                if title and link:
                    items.append({"title": title, "link": link,
                                  "published": pub, "outlet": outlet,
                                  "feed": feed_name})
            print(f"  RSS ok: {feed_name} ({len(items)} total so far)",
                  file=sys.stderr)
        except Exception as exc:  # network / parse failure -> skip feed
            print(f"  RSS failed: {feed_name}: {exc}", file=sys.stderr)
    return items


def tokens(text):
    words = re.findall(r"[a-zA-Z\u0900-\u097F]{4,}", text.lower())
    return {w for w in words if w not in STOPWORDS}


def jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def cluster_items(items):
    """Single-link clustering of RSS items by headline token overlap."""
    clusters, used = [], [False] * len(items)
    toks = [tokens(i["title"]) for i in items]
    for i, item in enumerate(items):
        if used[i]:
            continue
        used[i] = True
        cluster = [item]
        changed = True
        while changed:
            changed = False
            for j, other in enumerate(items):
                if used[j]:
                    continue
                if any(jaccard(toks[j], tokens(m["title"])) >= 0.30
                       for m in cluster):
                    used[j] = True
                    cluster.append(other)
                    toks[j] = toks[j] | tokens(other["title"])
                    changed = True
        clusters.append(cluster)
    return clusters


def tag_topics(text):
    low = text.lower()
    found = []
    for t, kws in TOPIC_KEYWORDS.items():
        if any(re.search(r"\b" + re.escape(k) + r"\w*", low) for k in kws):
            found.append(t)
    return found or ["general"]


def outlet_key(outlet):
    """Normalize outlet names so the same outlet isn't double-counted."""
    o = outlet.lower()
    o = re.sub(r"\s*\(.*?\)\s*", " ", o)   # drop parentheticals
    o = re.sub(r"^(facebook|instagram|youtube|x|threads)\s+", "", o)
    o = re.sub(r"[^a-z0-9 ]", "", o)
    return re.sub(r"\s+", " ", o).strip()


def genuineness(source_count):
    if source_count >= 3:
        return "verified", "Verified"
    if source_count == 2:
        return "corroborated", "Corroborated"
    return "single", "Single source"


def slugify(text):
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:60] or "story"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-rss", action="store_true",
                    help="skip RSS fetching, use curated items only")
    args = ap.parse_args()

    curated = json.load(open("curated.json", encoding="utf-8"))
    print(f"Loaded {len(curated)} curated items", file=sys.stderr)

    rss_items = [] if args.no_rss else fetch_rss()
    fresh = [i for i in rss_items
             if i["published"] is None or i["published"] >= SEVEN_DAYS_AGO]
    print(f"{len(fresh)} RSS items within 7 days", file=sys.stderr)

    stories = []
    for c in curated:
        stories.append({
            "headline": c["headline"],
            "summary": c["summary"],
            "date": c["date"],
            "topics": c.get("topics") or tag_topics(
                c["headline"] + " " + c["summary"]),
            "sources": list(c["sources"]),
            "curated_tokens": tokens(c["headline"]),
        })

    # Attach fresh RSS items to matching curated stories, else new clusters.
    matched = [False] * len(fresh)
    for s in stories:
        for i, r in enumerate(fresh):
            if matched[i]:
                continue
            if jaccard(s["curated_tokens"], tokens(r["title"])) >= 0.30:
                if not any(src["url"] == r["link"] for src in s["sources"]):
                    s["sources"].append({
                        "outlet": r["outlet"], "type": "news",
                        "url": r["link"]})
                matched[i] = True

    unmatched = [r for i, r in enumerate(fresh) if not matched[i]]
    for cluster in cluster_items(unmatched):
        rep = max(cluster, key=lambda x: len(x["title"]))
        pub_dates = [x["published"] for x in cluster if x["published"]]
        stories.append({
            "headline": rep["title"],
            "summary": "",
            "date": (max(pub_dates).date().isoformat() if pub_dates
                     else BASE.date().isoformat()),
            "topics": tag_topics(" ".join(x["title"] for x in cluster)),
            "sources": [{"outlet": x["outlet"], "type": "news",
                         "url": x["link"]} for x in cluster],
            "curated_tokens": tokens(rep["title"]),
            "is_curated": False,
        })
    for s in stories:
        s.setdefault("is_curated", True)

    # Manual near-duplicate merges (RSS-only stories).
    def mergeable(s):
        return not s["is_curated"]

    def do_merge(base, others):
        for other in others:
            base["sources"].extend(other["sources"])
            base["topics"] = sorted(set(base["topics"]) | set(other["topics"]))
            if not base["summary"] and other["summary"]:
                base["summary"] = other["summary"]
            stories.remove(other)
        # Recompute topics from the final headline so merged topic unions
        # don't accumulate noise.
        base["topics"] = tag_topics(base["headline"] + " " + base["summary"])

    for mdate, keywords, into, headline_override in MANUAL_MERGES:
        if into:
            targets = [s for s in stories
                       if s["is_curated"]
                       and slugify(s["headline"]).startswith(into)]
            group = [s for s in stories
                     if mergeable(s) and s["date"] == mdate
                     and all(k in s["headline"].lower() for k in keywords)]
            if targets and group:
                do_merge(targets[0], group)
                print(f"  merged {len(group)} RSS clusters into curated "
                      f"'{targets[0]['headline'][:60]}'", file=sys.stderr)
        else:
            group = [s for s in stories
                     if mergeable(s) and s["date"] == mdate
                     and all(k in s["headline"].lower() for k in keywords)]
            if len(group) > 1:
                if headline_override:
                    group[0]["headline"] = headline_override
                do_merge(group[0], group[1:])
                print(f"  merged {len(group)} clusters on {mdate} {keywords}",
                      file=sys.stderr)

    # Drop thin RSS-only clusters; keep every hand-verified curated story.
    def outlet_count(s):
        return len({outlet_key(x["outlet"]) for x in s["sources"]})
    before = len(stories)
    stories = [s for s in stories
               if s["is_curated"] or outlet_count(s) >= MIN_RSS_OUTLETS]
    print(f"  filtered {before} -> {len(stories)} stories "
          f"(RSS-only need >={MIN_RSS_OUTLETS} outlets)", file=sys.stderr)

    # Score + shape final stories.
    out_stories = []
    for s in stories:
        seen_urls, uniq_sources = set(), []
        for src in s["sources"]:
            if src["url"] in seen_urls:
                continue
            seen_urls.add(src["url"])
            uniq_sources.append(src)
        outlets = {outlet_key(x["outlet"]) for x in uniq_sources}
        g_key, g_label = genuineness(len(outlets))
        out_stories.append({
            "id": slugify(s["headline"]),
            "headline": s["headline"],
            "summary": s["summary"],
            "date": s["date"],
            "topics": s["topics"],
            "sources": uniq_sources,
            "source_count": len(outlets),
            "genuineness": g_key,
            "genuineness_label": g_label,
        })

    out_stories.sort(key=lambda x: x["date"], reverse=True)
    data = {
        "generated_at": BASE.strftime("%Y-%m-%d %H:%M UTC"),
        "generated_at_ist": (BASE + dt.timedelta(hours=5, minutes=30)
                             ).strftime("%d %b %Y, %I:%M %p IST"),
        "story_count": len(out_stories),
        "method": ("RSS (Google News) + hand-verified web/social collection; "
                   "genuineness = count of independent outlets per story"),
        "stories": out_stories,
    }
    json.dump(data, open("data.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    counts = {}
    for st in out_stories:
        counts[st["genuineness"]] = counts.get(st["genuineness"], 0) + 1
    print(f"Wrote data.json: {len(out_stories)} stories {counts}",
          file=sys.stderr)


if __name__ == "__main__":
    main()
