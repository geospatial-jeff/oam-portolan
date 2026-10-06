"""Turn an upstream OAM STAC item into an item of this Portolan mirror.

Each change here is listed in the collections' processing_notes. Keep the two in step.
"""

import copy
import re

UPSTREAM_ITEM_URL = "https://api.imagery.hotosm.org/stac/collections/openaerialmap/items/{id}"

# The upstream collection declares CC-BY-4.0. Items without their own
# `license` inherit it, per STAC's collection-to-item inheritance.
DEFAULT_LICENSE = "CC-BY-4.0"

COLLECTION_BY_LICENSE = {
    "CC-BY-4.0": "oam-cc-by-4-0",
    "CC-BY-SA-4.0": "oam-cc-by-sa-4-0",
    "CC-BY-NC-4.0": "oam-cc-by-nc-4-0",
}

# Years before this hold a handful of scans each, so they share one subcatalog.
FIRST_GROUPED_YEAR = 2010
EARLY_GROUP = "pre-2010"

WITHHELD = "Withheld (email address removed by mirror)"

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")


def scrub_emails(text):
    """Remove email addresses and the separators left around them."""
    return _EMAIL.sub("", text).strip(" ,;:<>()[]")


def _scrub_name(name):
    return WITHHELD if _EMAIL.search(name) else name


def clean_providers(providers):
    """Return providers with emails removed from names and descriptions."""
    cleaned = []
    for provider in providers:
        provider = dict(provider)
        provider["name"] = _scrub_name(provider["name"])
        description = scrub_emails(provider.get("description", ""))
        if description:
            provider["description"] = description
        else:
            provider.pop("description", None)
        cleaned.append(provider)
    return cleaned


def item_license(item):
    return item["properties"].get("license") or DEFAULT_LICENSE


def collection_for(item):
    license_id = item_license(item)
    if license_id not in COLLECTION_BY_LICENSE:
        raise ValueError(f"item {item['id']} has unmapped license {license_id!r}")
    return COLLECTION_BY_LICENSE[license_id]


def year_group(item):
    """Name of the year subcatalog an item belongs to, from its acquisition start."""
    props = item["properties"]
    start = props.get("start_datetime") or props.get("datetime")
    if not start:
        raise ValueError(f"item {item['id']} has no datetime or start_datetime")
    year = int(start[:4])
    return EARLY_GROUP if year < FIRST_GROUPED_YEAR else str(year)


def _geometry_bbox(geometry):
    coords = []

    def walk(node):
        if isinstance(node[0], (int, float)):
            coords.append(node)
        else:
            for child in node:
                walk(child)

    walk(geometry["coordinates"])
    xs = [c[0] for c in coords]
    ys = [c[1] for c in coords]
    return [min(xs), min(ys), max(xs), max(ys)]


def _links(item_id):
    return [
        {"rel": "root", "href": "../../../catalog.json", "type": "application/json"},
        {"rel": "parent", "href": "../catalog.json", "type": "application/json"},
        {"rel": "collection", "href": "../../collection.json", "type": "application/json"},
        {
            "rel": "canonical",
            "href": UPSTREAM_ITEM_URL.format(id=item_id),
            "type": "application/geo+json",
            "title": "This item in the OpenAerialMap STAC API",
        },
    ]


def transform_item(upstream, collection_id):
    """Return a new item for `collection_id`; `upstream` is left unchanged."""
    item = copy.deepcopy(upstream)
    props = item["properties"]

    props.pop("oam:uploader_email", None)
    props["providers"] = clean_providers(props.get("providers", []))
    if "oam:producer_name" in props:
        props["oam:producer_name"] = _scrub_name(props["oam:producer_name"])

    # STAC 1.1 requires the datetime key; it is null when an interval is given.
    if "datetime" not in props:
        props["datetime"] = None

    bbox = item["bbox"]
    if bbox[1] > bbox[3]:
        item["bbox"] = _geometry_bbox(item["geometry"])

    # Legacy items link S3 over http; the same objects are served over https
    # (identical ETag), and PORTO-CORE-023 requires https.
    for asset in item["assets"].values():
        if asset["href"].startswith("http://"):
            asset["href"] = "https://" + asset["href"][len("http://") :]

    # The unmodified upload is the upstream original the COG was derived from.
    if "original" in item["assets"]:
        item["assets"]["original"]["roles"] = ["source"]

    item["collection"] = collection_id
    item["links"] = _links(item["id"])
    return item
