"""Build the Portolan catalog from a harvest.

Usage: python -m oam_mirror.build data/openaerialmap.ndjson catalog/

Writes every generated file (item JSON, year subcatalogs, collections,
metadata.yaml, AGENTS.md, thumbnails), then runs `portolan stac-geoparquet`
and `portolan readme`. Hand-written text lives in metadata/ and is rendered
here, so a rebuild reproduces the whole tree.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from collections import Counter
from string import Template

import yaml

from oam_mirror import layout, thumbnail
from oam_mirror.transform import COLLECTION_BY_LICENSE, EARLY_GROUP, WITHHELD

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
METADATA_DIR = os.path.join(REPO, "metadata")
LAND = os.path.join(REPO, "vendor", "naturalearth", "ne_110m_land.geojson")

# Sibling collections get distinct colours so their cards do not read as one dataset.
THUMB_COLOURS = {"oam-cc-by-4-0": "#1b6b93", "oam-cc-by-sa-4-0": "#2e8540", "oam-cc-by-nc-4-0": "#b5541c"}
ASSET_ORDER = ["geoparquet-items", "thumbnail"]

# geoparquet-io ships inside the portolan-cli tool environment, which uv does
# not put on PATH. Point GPIO at it, e.g. ~/.local/share/uv/tools/portolan-cli/bin/gpio.
GPIO = os.environ.get("GPIO", "gpio")

# Where the catalog is served from. Machine-facing (data.source.coop), so DuckDB
# recipes and the root self link resolve to raw bytes.
DEFAULT_PUBLIC_URL = "https://data.source.coop/geospatialjeff/oam-portolan/"

# The repository this catalog is maintained in; written to the root vcs and issues links.
REPO_URL = "https://github.com/geospatial-jeff/oam-portolan"


def _template(name):
    with open(os.path.join(METADATA_DIR, name)) as f:
        return Template(f.read())


def _write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as out:
        out.write(text)


def _acquired(item):
    props = item["properties"]
    return props.get("datetime") or props["start_datetime"]


PLATFORM_NAMES = [("uav", "drones"), ("aircraft", "aircraft"), ("satellite", "satellites"), ("kite", "kites"), ("balloon", "balloons")]


def platform_phrase(platforms):
    """'drones (604), aircraft (39) and satellites (1,396)', skipping platforms with no scenes."""
    parts = [f"{name} ({platforms[key]:,})" for key, name in PLATFORM_NAMES if platforms.get(key)]
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


def gsd_note(gsd):
    """Sentence on implausible gsd values in one collection."""
    degrees = sum(1 for g in gsd if g < 1e-4)
    large = [g for g in gsd if g >= 10]
    if not degrees and not large:
        return "Every item in this collection has a gsd between 0.0001 and 10, but sibling collections do not."
    parts = []
    if degrees:
        parts.append(f"{degrees:,} items have gsd below 0.0001")
    if large:
        parts.append(f"{len(large):,} have gsd of 10 or more, up to {max(large):,.0f}")
    return "In this collection " + " and ".join(parts) + "."


def degree_gsd_summary(items):
    """Catalog-wide sentence linking tiny gsd values to EPSG:4326 COGs."""
    tiny = [item for item in items if (item["properties"].get("gsd") or 1) < 1e-4]
    geographic = sum(1 for item in tiny if item["assets"]["visual"].get("proj:code") == "EPSG:4326")
    return f"Across the catalog, {geographic} of the {len(tiny)} items with gsd below 0.0001 are EPSG:4326 COGs, so their gsd is in degrees."


def dates_note(early_ids):
    if not early_ids:
        return "No item in this collection starts before 1990."
    return (
        f"{len(early_ids)} items start before 1990 ({', '.join(early_ids)}). "
        "Some are historical surveys and some look like typos, so check them before relying on the date."
    )


def collection_stats(items):
    """Derived numbers the collection templates quote. Every value is recomputed per build."""
    platforms = Counter(item["properties"]["oam:platform_type"] for item in items)
    gsd = [item["properties"]["gsd"] for item in items if item["properties"].get("gsd") is not None]
    early = sorted(item["id"] for item in items if _acquired(item)[:4] < "1990")
    wide = [item for item in items if item["bbox"][2] - item["bbox"][0] > 20 or item["bbox"][3] - item["bbox"][1] > 20]
    # The newest scene anchors the example queries, so they return rows.
    example = max(items, key=lambda item: (_acquired(item), item["id"]))
    lon = round((example["bbox"][0] + example["bbox"][2]) / 2, 5)
    lat = round((example["bbox"][1] + example["bbox"][3]) / 2, 5)
    return {
        "count": f"{len(items):,}",
        "platforms": platform_phrase(platforms),
        "gsd_note": gsd_note(gsd),
        "dates_note": dates_note(early),
        "wide_scenes": str(len(wide)),
        "wkt2_items": str(sum(1 for item in items if "proj:wkt2" in item["assets"]["visual"])),
        "lon": str(lon),
        "lat": str(lat),
        "example_cog": example["assets"]["visual"]["href"],
        "clip_xmin": str(round(lon - 0.001, 5)),
        "clip_xmax": str(round(lon + 0.001, 5)),
        "clip_ymin": str(round(lat - 0.001, 5)),
        "clip_ymax": str(round(lat + 0.001, 5)),
    }


def _license_fields(license_id):
    name, url = layout.LICENSES[license_id]
    return {"license_id": license_id, "license_name": name, "license_url": url}


def human_url_for(public_url):
    """Human-facing base for links people click: source.coop renders Markdown, data.source.coop serves bytes."""
    return public_url.replace("https://data.source.coop/", "https://source.coop/", 1)


def render_collection_metadata(license_id, stats, harvested_at, public_url=None):
    public_url = public_url or DEFAULT_PUBLIC_URL
    values = {
        "human_url": human_url_for(public_url),
        "collection_id": COLLECTION_BY_LICENSE[license_id],
        **stats,
        **_license_fields(license_id),
        "title": layout.collection_title(license_id),
        "harvested_at": harvested_at,
        "harvested_date": harvested_at[:10],
        "withheld": WITHHELD,
    }
    return _template("collection.yaml").substitute(values)


def _remove_generated_years(collection_dir):
    """Delete year subcatalogs so items dropped upstream do not linger."""
    if not os.path.isdir(collection_dir):
        return
    for name in os.listdir(collection_dir):
        path = os.path.join(collection_dir, name)
        if os.path.isfile(os.path.join(path, "catalog.json")):
            shutil.rmtree(path)


def multihash_sha256(path):
    """file:checksum value: multihash prefix 0x12 (sha2-256), 0x20 (32 bytes), then the digest."""
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return "1220" + digest.hexdigest()


def _sort_item_mirror(collection_dir):
    """Hilbert-sort items.parquet in place.

    portolan stac-geoparquet 0.8.0 writes rows in link order, which fails the
    spatial-ordering MUST (PTL-DAT-006). gpio keeps every row and the
    stac-geoparquet metadata; 2,048-row groups let readers skip by bbox.
    """
    path = os.path.join(collection_dir, "items.parquet")
    sorted_path = path + ".sorted.parquet"
    subprocess.run(
        [GPIO, "sort", "hilbert", path, sorted_path, "--row-group-size", "2048", "--overwrite"],
        check=True,
    )
    os.replace(sorted_path, path)


def _finish_collection_assets(collection_path):
    """Refresh the item mirror's size and checksum, and put it first for the README Quick Start."""
    with open(collection_path) as f:
        document = json.load(f)
    assets = document.get("assets", {})
    mirror_path = os.path.join(os.path.dirname(collection_path), "items.parquet")
    assets["geoparquet-items"]["file:size"] = os.path.getsize(mirror_path)
    assets["geoparquet-items"]["file:checksum"] = multihash_sha256(mirror_path)
    ordered = {key: assets[key] for key in ASSET_ORDER if key in assets}
    ordered.update({key: value for key, value in assets.items() if key not in ordered})
    document["assets"] = ordered
    layout.write_json(collection_path, document)


def _portolan(catalog_root, *args):
    subprocess.run(["portolan", *args], cwd=catalog_root, check=True)


def build(harvest_path, catalog_root, public_url=DEFAULT_PUBLIC_URL):
    with open(harvest_path + ".harvest.json") as f:
        harvested_at = json.load(f)["harvested_at"]
    with open(harvest_path) as f:
        upstream = [json.loads(line) for line in f]

    if not os.path.exists(os.path.join(catalog_root, "catalog.json")):
        os.makedirs(catalog_root, exist_ok=True)
        _portolan(catalog_root, "init", "--auto", "--license", "CC-BY-4.0", "--title", "OpenAerialMap (Portolan mirror)")

    groups = layout.group_items(upstream)
    degree_summary = degree_gsd_summary(upstream)
    license_by_collection = {cid: lic for lic, cid in COLLECTION_BY_LICENSE.items()}
    rendered = {}
    for collection_id, by_year in groups.items():
        license_id = license_by_collection[collection_id]
        items = [item for year_items in by_year.values() for item in year_items]
        stats = {**collection_stats(items), "degree_gsd_summary": degree_summary}
        rendered[license_id] = (stats, yaml.safe_load(render_collection_metadata(license_id, stats, harvested_at, public_url)))
        _remove_generated_years(os.path.join(catalog_root, collection_id))

    counts = layout.write_tree(
        catalog_root,
        groups,
        harvested_at,
        providers_for=lambda lic: rendered[lic][1]["providers"],
        description_for=lambda lic: rendered[lic][1]["description"],
        human_url=human_url_for(public_url),
    )
    layout.link_collections(catalog_root, counts)

    for collection_id, by_year in groups.items():
        license_id = license_by_collection[collection_id]
        stats, _ = rendered[license_id]
        collection_dir = os.path.join(catalog_root, collection_id)
        title = layout.collection_title(license_id)
        _write_text(
            os.path.join(collection_dir, ".portolan", "metadata.yaml"),
            render_collection_metadata(license_id, stats, harvested_at, public_url),
        )
        _write_text(
            os.path.join(collection_dir, "AGENTS.md"),
            _template("AGENTS.collection.md").substitute(
                {
                    **stats,
                    **_license_fields(license_id),
                    "title": title,
                    "collection_id": collection_id,
                    "harvested_at": harvested_at,
                    "base": public_url,
                }
            ),
        )
        for year, year_items in by_year.items():
            when = "before 2010" if year == EARLY_GROUP else f"in {year}"
            year_values = {
                **_license_fields(license_id),
                "title": layout.year_title(license_id, year),
                "count": f"{len(year_items):,}",
                "when": when,
                "harvested_at": harvested_at,
                "collection_id": collection_id,
                "year_filter": " < 2010" if year == EARLY_GROUP else f" = {year}",
                "human_url": human_url_for(public_url),
            }
            _write_text(os.path.join(collection_dir, year, ".portolan", "metadata.yaml"), _template("year.yaml").substitute(year_values))
            _write_text(os.path.join(collection_dir, year, "AGENTS.md"), _template("AGENTS.year.md").substitute(year_values))

        items = [item for year_items in by_year.values() for item in year_items]
        thumbnail.draw(items, LAND, os.path.join(collection_dir, "thumbnail.png"), THUMB_COLOURS[collection_id])
        collection_path = os.path.join(collection_dir, "collection.json")
        with open(collection_path) as f:
            document = json.load(f)
        document["assets"]["thumbnail"] = {
            "href": "./thumbnail.png",
            "type": "image/png",
            "roles": ["thumbnail"],
            "title": "Scene locations (centre of each footprint) over Natural Earth land",
        }
        layout.write_json(collection_path, document)

    _write_root(catalog_root, counts, harvested_at, public_url)
    _portolan(catalog_root, "stac-geoparquet")
    for collection_id in counts:
        _sort_item_mirror(os.path.join(catalog_root, collection_id))
        _finish_collection_assets(os.path.join(catalog_root, collection_id, "collection.json"))
    _portolan(catalog_root, "readme")
    _remove_versions_files(catalog_root)
    return counts


def _remove_versions_files(catalog_root):
    """Drop portolan-cli's versions.json files: CLI sync state, not part of the spec.

    This catalog publishes with tools/publish.py, which keeps no state.
    """
    for dirpath, _, filenames in os.walk(catalog_root):
        if "versions.json" in filenames:
            os.remove(os.path.join(dirpath, "versions.json"))


def _write_root(catalog_root, counts, harvested_at, public_url):
    template = _template("catalog.yaml")
    metadata_text = template.substitute({"harvested_at": harvested_at, "human_url": human_url_for(public_url)})
    metadata = yaml.safe_load(metadata_text)
    _write_text(os.path.join(catalog_root, ".portolan", "metadata.yaml"), metadata_text)

    license_by_collection = {cid: lic for lic, cid in COLLECTION_BY_LICENSE.items()}
    rows = "\n".join(
        f"| `{cid}` | {layout.LICENSES[license_by_collection[cid]][0]} | {counts[cid]:,} |" for cid in sorted(counts)
    )
    _write_text(
        os.path.join(catalog_root, "AGENTS.md"),
        _template("AGENTS.catalog.md").substitute(
            {"total": f"{sum(counts.values()):,}", "harvested_at": harvested_at, "collection_rows": rows, "base": public_url}
        ),
    )

    path = os.path.join(catalog_root, "catalog.json")
    with open(path) as f:
        root = json.load(f)
    root["id"] = public_url.rstrip("/").rsplit("/", 1)[-1]
    root["title"] = metadata["title"]
    root["description"] = metadata["description"]
    root["updated"] = harvested_at
    root["stac_extensions"] = [layout.PORTOLAN_SCHEMA]
    # An absolute self link records the canonical location (PORTO-CORE-081).
    # vcs and issues point back at the repository; they stay absolute because
    # the repository sits outside the published catalog.
    root["links"] = [link for link in root["links"] if link["rel"] not in {"self", "vcs", "issues"}]
    root["links"].insert(0, {"rel": "self", "href": public_url + "catalog.json", "type": "application/json"})
    root["links"].append({"rel": "vcs", "href": REPO_URL, "type": "text/html", "title": "Source repository"})
    root["links"].append({"rel": "issues", "href": REPO_URL + "/issues", "type": "text/html", "title": "Issue tracker"})
    layout.write_json(path, root)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("harvest", help="NDJSON written by oam_mirror.harvest")
    parser.add_argument("catalog", help="catalog root directory")
    parser.add_argument("--public-url", default=DEFAULT_PUBLIC_URL, help="base URL the catalog is served from, ending in /")
    args = parser.parse_args()
    if not args.public_url.endswith("/"):
        parser.error("--public-url must end with /")
    print(build(args.harvest, args.catalog, args.public_url))


if __name__ == "__main__":
    main()
