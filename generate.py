#!/usr/bin/env python3
"""Patna Pulse — story collector and genuineness scorer.

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
import os
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
                url, headers={"User-Agent": "patna-pulse/1.0"})
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


def type_for_url(url, declared="news"):
    """Map a source URL to the frontend's source-type vocabulary so social
    links render with their platform icon/label instead of a generic link."""
    u = (url or "").lower()
    if "facebook.com" in u or "fb.watch" in u:
        return "facebook"
    if "instagram.com" in u:
        return "instagram"
    if "youtube.com" in u or "youtu.be" in u:
        return "youtube"
    if "x.com" in u or "twitter.com" in u:
        return "x"
    if "threads.com" in u or "threads.net" in u:
        return "threads"
    return declared or "news"


def genuineness(source_count):
    if source_count >= 3:
        return "verified", "Verified"
    if source_count == 2:
        return "corroborated", "Corroborated"
    return "single", "Single source"


UA = {"User-Agent": "patna-pulse/1.0 (+https://niteshlhsnda-droid.github.io/patna-pulse/)"}
IMG_DIR = "images"
SKIP_IMG_HOSTS = ("facebook.com", "fb.watch", "instagram.com", "x.com",
                  "twitter.com", "threads.com", "threads.net")


def og_image_from_url(url):
    """Fetch a page and extract its og:image. Returns absolute URL or None."""
    if "news.google.com" in (url or ""):
        return None  # interstitial redirect page: never carries og:image
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=12) as resp:
            ctype = resp.headers.get("Content-Type", "")
            if "html" not in ctype.lower():
                return None
            html = resp.read(300_000).decode("utf-8", "ignore")
        for pat in (r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
                    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']'):
            m = re.search(pat, html, re.I)
            if m:
                return m.group(1)
        return None
    except Exception as exc:  # network / parse failure -> no image
        print(f"    og:image miss {url[:70]}: {exc}", file=sys.stderr)
        return None


def youtube_id(url):
    m = re.search(
        r"(?:youtube\.com/(?:watch\?[^#]*v=|shorts/|embed/|live/)|youtu\.be/)"
        r"([A-Za-z0-9_-]{6,})", url or "")
    return m.group(1) if m else None


def youtube_thumb(video_id):
    """oEmbed thumbnail for a YouTube video (no API key needed)."""
    try:
        api = ("https://www.youtube.com/oembed?url="
               "https://www.youtube.com/watch?v=" + video_id + "&format=json")
        req = urllib.request.Request(api, headers=UA)
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read(50_000).decode("utf-8", "ignore"))
        return data.get("thumbnail_url")
    except Exception as exc:
        print(f"    yt oembed miss {video_id}: {exc}", file=sys.stderr)
        return None


def download_image(img_url, story_id):
    """Download an image into images/<story-id>.<ext>. Returns rel path or None."""
    try:
        req = urllib.request.Request(img_url, headers=UA)
        with urllib.request.urlopen(req, timeout=15) as resp:
            ctype = resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
            if not ctype.startswith("image/"):
                return None
            data = resp.read(3_000_000)
        if len(data) < 2000:  # too small to be a real photo
            return None
        ext = {"image/jpeg": "jpg", "image/png": "png",
               "image/webp": "webp", "image/gif": "gif"}.get(ctype, "jpg")
        os.makedirs(IMG_DIR, exist_ok=True)
        for e in ("jpg", "png", "webp", "gif"):
            p = os.path.join(IMG_DIR, story_id + "." + e)
            if os.path.exists(p):
                os.remove(p)
        with open(os.path.join(IMG_DIR, story_id + "." + ext), "wb") as fh:
            fh.write(data)
        return IMG_DIR + "/" + story_id + "." + ext
    except Exception as exc:
        print(f"    image download miss {img_url[:70]}: {exc}", file=sys.stderr)
        return None


def enrich_media(out_stories):
    """Add 'image' (local path) and 'video_embed' (YouTube iframe URL) per story."""
    for s in out_stories:
        s["image"] = None
        s["video_embed"] = None
        news_srcs = [x for x in s["sources"] if x["type"] == "news"]
        yt_ids = []
        for x in s["sources"]:
            vid = youtube_id(x["url"])
            if vid and vid not in yt_ids:
                yt_ids.append(vid)
        if yt_ids:
            s["video_embed"] = ("https://www.youtube-nocookie.com/embed/"
                                + yt_ids[0])
        tried = 0
        for src in news_srcs:
            if tried >= 3 or s["image"]:
                break
            host = (src["url"] or "").lower()
            if any(h in host for h in SKIP_IMG_HOSTS):
                continue
            tried += 1
            og = og_image_from_url(src["url"])
            if not og:
                continue
            if og.startswith("//"):
                og = "https:" + og
            s["image"] = download_image(og, s["id"])
        if not s["image"]:
            for vid in yt_ids[:2]:  # fall back to a video thumbnail
                thumb = youtube_thumb(vid)
                if thumb:
                    s["image"] = download_image(thumb, s["id"])
                    if s["image"]:
                        break
        print(f"  media {s['id'][:44]:44} "
              f"img={'y' if s['image'] else 'n'} vid={'y' if s['video_embed'] else 'n'}",
              file=sys.stderr)
    keep = {s["image"] for s in out_stories if s["image"]}
    if os.path.isdir(IMG_DIR):
        for f in os.listdir(IMG_DIR):
            rel = IMG_DIR + "/" + f
            if rel not in keep:
                os.remove(os.path.join(IMG_DIR, f))


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
            "sources": [{"outlet": s["outlet"],
                         "type": type_for_url(s["url"], s.get("type")),
                         "url": s["url"]} for s in c["sources"]],
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

    def headline_ok(s):
        """RSS-only headlines must look like real headlines, not outlet names."""
        if s["is_curated"]:
            return True
        words = re.findall(r"[A-Za-z\u0900-\u097F]{2,}", s["headline"])
        if len(words) < 4:
            return False
        outlets = {outlet_key(x["outlet"]) for x in s["sources"]}
        if outlet_key(s["headline"]) in outlets:
            return False
        return True

    before = len(stories)
    stories = [s for s in stories
               if (s["is_curated"] or outlet_count(s) >= MIN_RSS_OUTLETS)
               and headline_ok(s)]
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
    enrich_media(out_stories)
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
