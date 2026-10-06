import copy

from oam_mirror.transform import (
    WITHHELD,
    clean_providers,
    collection_for,
    scrub_emails,
    transform_item,
    year_group,
)


def upstream_item(**props):
    properties = {
        "gsd": 0.06,
        "title": "Localidad Luribay",
        "license": "CC-BY-4.0",
        "providers": [
            {"name": "Rodolfo Vargas", "roles": ["producer", "licensor"], "description": "Rodolfo Vargas,rv@example.com"}
        ],
        "oam:producer_name": "Rodolfo Vargas",
        "oam:platform_type": "uav",
        "start_datetime": "2026-10-06T04:00:00Z",
        "end_datetime": "2026-10-06T14:52:10Z",
    }
    properties.update(props)
    return {
        "type": "Feature",
        "stac_version": "1.1.0",
        "stac_extensions": ["https://docs.imagery.hotosm.org/oam/v0.3.0/schema.json"],
        "id": "abc123",
        "collection": "openaerialmap",
        "bbox": [-67.668, -17.069, -67.649, -17.049],
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[-67.668, -17.049], [-67.668, -17.069], [-67.649, -17.069], [-67.649, -17.049], [-67.668, -17.049]]],
        },
        "links": [
            {"rel": "self", "href": "https://api.imagery.hotosm.org/stac/collections/openaerialmap/items/abc123"},
            {"rel": "root", "href": "https://api.imagery.hotosm.org/stac/"},
        ],
        "assets": {
            "visual": {
                "href": "https://oin-hotosm-temp.s3.amazonaws.com/a/0/b.tif",
                "type": "image/tiff; application=geotiff; profile=cloud-optimized",
                "roles": ["data"],
            }
        },
        "properties": properties,
    }


def test_scrub_emails_drops_trailing_email_after_name():
    assert scrub_emails("Bobby Howe,bh7406@bard.edu") == "Bobby Howe"


def test_scrub_emails_returns_empty_for_bare_email():
    assert scrub_emails("drcog@drcog.org") == ""


def test_scrub_emails_leaves_text_without_email():
    assert scrub_emails("Denver Regional Council of Governments") == "Denver Regional Council of Governments"


def test_clean_providers_removes_empty_description():
    cleaned = clean_providers([{"name": "DRCOG", "roles": ["producer"], "description": "drcog@drcog.org"}])
    assert "description" not in cleaned[0]


def test_clean_providers_withholds_email_name():
    cleaned = clean_providers([{"name": "rio.tapem@gmail.com", "roles": ["producer"], "description": ""}])
    assert cleaned[0]["name"] == WITHHELD


def test_transform_drops_uploader_email():
    item = transform_item(upstream_item(**{"oam:uploader_email": "x@example.com"}), "oam-cc-by-4-0")
    assert "oam:uploader_email" not in item["properties"]


def test_transform_keeps_uploader_name():
    item = transform_item(upstream_item(**{"oam:uploader_name": "Rodolfo"}), "oam-cc-by-4-0")
    assert item["properties"]["oam:uploader_name"] == "Rodolfo"


def test_transform_scrubs_provider_description():
    item = transform_item(upstream_item(), "oam-cc-by-4-0")
    assert item["properties"]["providers"][0]["description"] == "Rodolfo Vargas"


def test_transform_withholds_email_producer_name():
    item = transform_item(upstream_item(**{"oam:producer_name": "janunez@umsa.bo"}), "oam-cc-by-4-0")
    assert item["properties"]["oam:producer_name"] == WITHHELD


def test_transform_adds_null_datetime_for_interval():
    item = transform_item(upstream_item(), "oam-cc-by-4-0")
    assert "datetime" in item["properties"] and item["properties"]["datetime"] is None


def test_transform_keeps_existing_datetime():
    raw = upstream_item(datetime="2020-01-01T00:00:00Z")
    del raw["properties"]["start_datetime"], raw["properties"]["end_datetime"]
    assert transform_item(raw, "oam-cc-by-4-0")["properties"]["datetime"] == "2020-01-01T00:00:00Z"


def test_transform_recomputes_inverted_bbox_from_geometry():
    raw = upstream_item()
    raw["bbox"] = [-67.668, -17.049, -67.649, -17.069]
    assert transform_item(raw, "oam-cc-by-4-0")["bbox"] == [-67.668, -17.069, -67.649, -17.049]


def test_transform_marks_original_upload_as_source():
    raw = upstream_item()
    raw["assets"]["original"] = {"href": "https://x/o.tif", "type": "image/tiff; application=geotiff", "roles": ["data"]}
    assert transform_item(raw, "oam-cc-by-4-0")["assets"]["original"]["roles"] == ["source"]


def test_transform_upgrades_http_asset_hrefs_to_https():
    raw = upstream_item()
    raw["assets"]["visual"]["href"] = "http://oin-hotosm-temp.s3.amazonaws.com/1/0/a.tif"
    assert transform_item(raw, "oam-cc-by-4-0")["assets"]["visual"]["href"] == "https://oin-hotosm-temp.s3.amazonaws.com/1/0/a.tif"


def test_transform_sets_collection_id():
    assert transform_item(upstream_item(), "oam-cc-by-4-0")["collection"] == "oam-cc-by-4-0"


def test_transform_writes_relative_structural_links():
    links = {link["rel"]: link["href"] for link in transform_item(upstream_item(), "oam-cc-by-4-0")["links"]}
    assert (links["root"], links["parent"], links["collection"]) == (
        "../../../catalog.json",
        "../catalog.json",
        "../../collection.json",
    )


def test_transform_links_canonical_upstream_item():
    links = {link["rel"]: link for link in transform_item(upstream_item(), "oam-cc-by-4-0")["links"]}
    assert links["canonical"]["href"] == "https://api.imagery.hotosm.org/stac/collections/openaerialmap/items/abc123"


def test_transform_drops_upstream_self_link():
    rels = [link["rel"] for link in transform_item(upstream_item(), "oam-cc-by-4-0")["links"]]
    assert "self" not in rels


def test_transform_does_not_mutate_input():
    raw = upstream_item(**{"oam:uploader_email": "x@example.com"})
    before = copy.deepcopy(raw)
    transform_item(raw, "oam-cc-by-4-0")
    assert raw == before


def test_collection_for_missing_license_is_cc_by():
    raw = upstream_item()
    del raw["properties"]["license"]
    assert collection_for(raw) == "oam-cc-by-4-0"


def test_collection_for_nc_license():
    assert collection_for(upstream_item(license="CC-BY-NC-4.0")) == "oam-cc-by-nc-4-0"


def test_year_group_uses_start_datetime():
    assert year_group(upstream_item()) == "2026"


def test_year_group_folds_early_years():
    assert year_group(upstream_item(start_datetime="1944-12-31T13:00:00Z")) == "pre-2010"
