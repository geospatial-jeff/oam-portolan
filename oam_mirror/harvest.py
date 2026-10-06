"""Harvest every item of an OAM STAC API collection into one NDJSON file.

The API spends about 0.25 s per item when paging unfiltered, so the harvest
splits the collection into datetime slices and pages them in parallel. Items
whose interval crosses a slice boundary come back more than once; they are
deduplicated by id. A sidecar JSON records when the harvest ran, which the
build writes to `updated` (PORTO-CORE-057).

Usage: python -m oam_mirror.harvest data/openaerialmap.ndjson
"""

import argparse
import json
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

SEARCH_URL = "https://api.imagery.hotosm.org/stac/search"
STATS_URL = "https://s3.amazonaws.com/oin-hotosm-temp/stats.json"
PAGE_SIZE = 100
WORKERS = 7


def year_slices(first_year, last_year):
    """Return datetime ranges: one open-ended before first_year, one per year, one open after."""
    slices = [("..", f"{first_year - 1}-12-31T23:59:59Z")]
    slices += [(f"{y}-01-01T00:00:00Z", f"{y}-12-31T23:59:59Z") for y in range(first_year, last_year + 1)]
    slices.append((f"{last_year + 1}-01-01T00:00:00Z", ".."))
    return slices


def _post(body):
    req = urllib.request.Request(
        SEARCH_URL, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
    )
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                return json.load(resp)
        except OSError as exc:
            print(f"search retry {attempt} for {body}: {exc}", file=sys.stderr)
            time.sleep(2**attempt)
    raise RuntimeError(f"STAC search failed after retries: {body}")


def _harvest_slice(collection, start, end):
    body = {"collections": [collection], "limit": PAGE_SIZE, "datetime": f"{start}/{end}"}
    items = []
    while True:
        page = _post(body)
        items.extend(page["features"])
        next_links = [link for link in page.get("links", []) if link["rel"] == "next"]
        if not next_links or not page["features"]:
            break
        body = next_links[0]["body"]
    print(f"{start}/{end}: {len(items)}", file=sys.stderr, flush=True)
    return items


def dedupe(item_lists):
    """Merge item lists, keeping one item per id, ordered by id."""
    by_id = {}
    for items in item_lists:
        for item in items:
            by_id[item["id"]] = item
    return [by_id[item_id] for item_id in sorted(by_id)]


def upstream_item_count():
    with urllib.request.urlopen(STATS_URL, timeout=60) as resp:
        return json.load(resp)["items"]


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("out", help="NDJSON output path")
    parser.add_argument("--collection", default="openaerialmap")
    args = parser.parse_args()

    started = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    this_year = datetime.now(timezone.utc).year
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        lists = list(pool.map(lambda s: _harvest_slice(args.collection, *s), year_slices(2015, this_year)))
    items = dedupe(lists)

    with open(args.out, "w") as out:
        for item in items:
            out.write(json.dumps(item) + "\n")

    expected = upstream_item_count()
    sidecar = {"harvested_at": started, "collection": args.collection, "items": len(items), "upstream_stats_items": expected}
    with open(args.out + ".harvest.json", "w") as out:
        json.dump(sidecar, out, indent=2)
    print(json.dumps(sidecar), file=sys.stderr)
    if len(items) != expected:
        print(f"WARNING: harvested {len(items)} items, upstream stats.json reports {expected}", file=sys.stderr)


if __name__ == "__main__":
    main()
