"""Write the STAC tree: collections split by license, items grouped by year.

    catalog.json
    oam-cc-by-4-0/
        collection.json
        2016/
            catalog.json
            <item id>/<item id>.json

PORTO-CORE-015 puts each item in its own directory. The year subcatalogs keep
each node's child count browsable (core.md, Nested Catalogs, Flat Collections).
"""

import json
import os
from collections import defaultdict

from oam_mirror.transform import COLLECTION_BY_LICENSE, EARLY_GROUP, collection_for, transform_item, year_group

PORTOLAN_SCHEMA = "https://schemas.portolan-sdi.org/portolan/v0.2.0/schema.json"
UPSTREAM_COLLECTION_URL = "https://api.imagery.hotosm.org/stac/collections/openaerialmap"
UPSTREAM_SITE_URL = "https://imagery.hotosm.org/"

LICENSES = {
    "CC-BY-4.0": ("CC BY 4.0", "https://creativecommons.org/licenses/by/4.0/"),
    "CC-BY-SA-4.0": ("CC BY-SA 4.0", "https://creativecommons.org/licenses/by-sa/4.0/"),
    "CC-BY-NC-4.0": ("CC BY-NC 4.0", "https://creativecommons.org/licenses/by-nc/4.0/"),
}


def collection_title(license_id):
    return f"OpenAerialMap imagery, {LICENSES[license_id][0]}"


def year_title(license_id, year):
    when = "before 2010" if year == EARLY_GROUP else f"in {year}"
    return f"{collection_title(license_id)}, acquired {when}"


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as out:
        json.dump(obj, out, indent=2)
        out.write("\n")


def _doc_links():
    return [
        {"rel": "agents", "href": "./AGENTS.md", "type": "text/markdown", "title": "Agent/LLM usage guide"},
        {"rel": "describedby", "href": "./README.md", "type": "text/markdown", "title": "Human-readable documentation"},
    ]


def _interval(items):
    starts, ends = [], []
    for item in items:
        props = item["properties"]
        starts.append(props.get("start_datetime") or props["datetime"])
        ends.append(props.get("end_datetime") or props["datetime"])
    return [min(starts), max(ends)]


def _bbox_union(items):
    boxes = [item["bbox"] for item in items]
    return [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]


def year_catalog(collection_id, license_id, year, items, agents_url):
    links = [
        {"rel": "root", "href": "../../catalog.json", "type": "application/json"},
        {"rel": "parent", "href": "../collection.json", "type": "application/json", "title": collection_title(license_id)},
        *_doc_links(),
    ]
    for item in sorted(items, key=lambda i: i["id"]):
        links.append(
            {
                "rel": "item",
                "href": f"./{item['id']}/{item['id']}.json",
                "type": "application/geo+json",
                "title": item["properties"].get("title") or item["id"],
            }
        )
    when = "before 2010" if year == EARLY_GROUP else f"in {year}"
    return {
        "type": "Catalog",
        "stac_version": "1.1.0",
        "stac_extensions": [PORTOLAN_SCHEMA],
        "id": f"{collection_id}-{year}",
        "title": year_title(license_id, year),
        "description": (
            f"The {len(items)} OpenAerialMap scenes licensed {LICENSES[license_id][0]} whose acquisition "
            f"started {when}. Each scene is one item with its Cloud Optimized GeoTIFF hosted by OpenAerialMap. "
            f"See the collection's [AGENTS.md]({agents_url}) for how to query them."
        ),
        "links": links,
    }


def collection_document(collection_id, license_id, years, items, harvested_at, providers, description):
    gsd = [item["properties"]["gsd"] for item in items if item["properties"].get("gsd") is not None]
    links = [
        {"rel": "root", "href": "../catalog.json", "type": "application/json"},
        {"rel": "parent", "href": "../catalog.json", "type": "application/json"},
        *_doc_links(),
        {"rel": "license", "href": LICENSES[license_id][1], "type": "text/html", "title": f"{LICENSES[license_id][0]} license"},
        {"rel": "via", "href": UPSTREAM_SITE_URL, "type": "text/html", "title": "OpenAerialMap"},
        {"rel": "canonical", "href": UPSTREAM_COLLECTION_URL, "type": "application/json", "title": "OpenAerialMap STAC collection"},
    ]
    for year in sorted(years):
        links.append(
            {"rel": "child", "href": f"./{year}/catalog.json", "type": "application/json", "title": year_title(license_id, year)}
        )
    return {
        "type": "Collection",
        "stac_version": "1.1.0",
        "stac_extensions": [PORTOLAN_SCHEMA],
        "id": collection_id,
        "title": collection_title(license_id),
        "description": description,
        "license": license_id,
        "keywords": ["OpenAerialMap", "aerial imagery", "drone", "UAV", "satellite", "orthomosaic", "humanitarian"],
        "providers": providers,
        "extent": {"spatial": {"bbox": [_bbox_union(items)]}, "temporal": {"interval": [_interval(items)]}},
        "summaries": {
            "oam:platform_type": sorted({item["properties"]["oam:platform_type"] for item in items}),
            "gsd": {"minimum": min(gsd), "maximum": max(gsd)},
        },
        "item_assets": {
            "visual": {
                "type": "image/tiff; application=geotiff; profile=cloud-optimized",
                "roles": ["data"],
                "title": "Imagery (Cloud Optimized GeoTIFF)",
            },
            "thumbnail": {"type": "image/png", "roles": ["thumbnail"], "title": "Thumbnail"},
            "metadata": {"type": "application/json", "roles": ["metadata"], "title": "OpenAerialMap upload metadata"},
        },
        "updated": harvested_at,
        "links": links,
        "assets": {},
    }


def group_items(upstream_items):
    """Transform items and group them as {collection_id: {year: [item, ...]}}."""
    groups = defaultdict(lambda: defaultdict(list))
    for upstream in upstream_items:
        collection_id = collection_for(upstream)
        groups[collection_id][year_group(upstream)].append(transform_item(upstream, collection_id))
    return groups


def write_tree(catalog_root, groups, harvested_at, providers_for, description_for, human_url):
    """Write collections, year catalogs and items; return {collection_id: item count}.

    groups is the output of group_items. providers_for and description_for
    take a license id and return that collection's providers and description.
    human_url is the catalog's human-facing base URL, ending in /; browsers
    resolve description links against their own page, so links are absolute.
    """
    license_by_collection = {cid: lic for lic, cid in COLLECTION_BY_LICENSE.items()}
    counts = {}
    for collection_id, by_year in sorted(groups.items()):
        license_id = license_by_collection[collection_id]
        collection_dir = os.path.join(catalog_root, collection_id)
        all_items = [item for items in by_year.values() for item in items]
        for year, items in by_year.items():
            for item in items:
                write_json(os.path.join(collection_dir, year, item["id"], f"{item['id']}.json"), item)
            write_json(os.path.join(collection_dir, year, "catalog.json"), year_catalog(collection_id, license_id, year, items, f"{human_url}{collection_id}/AGENTS.md"))
        collection_path = os.path.join(collection_dir, "collection.json")
        document = collection_document(
            collection_id, license_id, by_year.keys(), all_items, harvested_at, providers_for(license_id), description_for(license_id)
        )
        if os.path.exists(collection_path):
            # Keep assets added by later steps (items.parquet, thumbnail).
            with open(collection_path) as existing:
                document["assets"] = json.load(existing).get("assets", {})
        write_json(collection_path, document)
        counts[collection_id] = len(all_items)
    return counts


def link_collections(catalog_root, counts):
    """Point the root catalog's child links at the written collections."""
    path = os.path.join(catalog_root, "catalog.json")
    with open(path) as f:
        root = json.load(f)
    license_by_collection = {cid: lic for lic, cid in COLLECTION_BY_LICENSE.items()}
    root["links"] = [link for link in root["links"] if link["rel"] != "child"]
    for collection_id in sorted(counts):
        root["links"].append(
            {
                "rel": "child",
                "href": f"./{collection_id}/collection.json",
                "type": "application/json",
                "title": collection_title(license_by_collection[collection_id]),
            }
        )
    write_json(path, root)
