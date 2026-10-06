import yaml

from oam_mirror.build import collection_stats, degree_gsd_summary, gsd_note, multihash_sha256, platform_phrase, render_collection_metadata
from oam_mirror.layout import collection_document, year_catalog
from oam_mirror.verify_docs import localize

AGENTS_URL = "https://source.coop/x/y/oam-cc-by-4-0/AGENTS.md"


def item(item_id, start, bbox=(0.0, 0.0, 1.0, 1.0), gsd=0.05, platform="uav"):
    return {
        "id": item_id,
        "bbox": list(bbox),
        "assets": {"visual": {"href": f"https://example.org/{item_id}.tif"}},
        "properties": {
            "title": f"Scene {item_id}",
            "datetime": None,
            "start_datetime": start,
            "end_datetime": start,
            "gsd": gsd,
            "oam:platform_type": platform,
        },
    }


def links_by_rel(document, rel):
    return [link for link in document["links"] if link["rel"] == rel]


def test_year_catalog_links_each_item_with_title():
    catalog = year_catalog("oam-cc-by-4-0", "CC-BY-4.0", "2016", [item("a", "2016-01-01T00:00:00Z")], AGENTS_URL)
    assert links_by_rel(catalog, "item") == [
        {"rel": "item", "href": "./a/a.json", "type": "application/geo+json", "title": "Scene a"}
    ]


def test_year_catalog_parent_is_collection():
    catalog = year_catalog("oam-cc-by-4-0", "CC-BY-4.0", "2016", [item("a", "2016-01-01T00:00:00Z")], AGENTS_URL)
    assert links_by_rel(catalog, "parent")[0]["href"] == "../collection.json"


def test_year_catalog_declares_portolan_schema():
    catalog = year_catalog("oam-cc-by-4-0", "CC-BY-4.0", "2016", [item("a", "2016-01-01T00:00:00Z")], AGENTS_URL)
    assert catalog["stac_extensions"] == ["https://schemas.portolan-sdi.org/portolan/v0.2.0/schema.json"]


def collection(items=None):
    items = items or [item("a", "2016-01-01T00:00:00Z"), item("b", "2020-05-01T00:00:00Z", bbox=(-5, -2, 3, 4))]
    return collection_document("oam-cc-by-4-0", "CC-BY-4.0", ["2020", "2016"], items, "2026-10-06T17:48:03Z", [], "d")


def test_collection_child_links_sorted_by_year():
    assert [link["href"] for link in links_by_rel(collection(), "child")] == ["./2016/catalog.json", "./2020/catalog.json"]


def test_collection_has_mirror_provenance_links():
    rels = {link["rel"] for link in collection()["links"]}
    assert {"via", "canonical", "license"} <= rels


def test_collection_temporal_extent_spans_items():
    assert collection()["extent"]["temporal"]["interval"] == [["2016-01-01T00:00:00Z", "2020-05-01T00:00:00Z"]]


def test_collection_spatial_extent_is_union():
    assert collection()["extent"]["spatial"]["bbox"] == [[-5, -2, 3, 4]]


def test_collection_records_sync_time():
    assert collection()["updated"] == "2026-10-06T17:48:03Z"


def test_stats_names_early_scene_ids():
    stats = collection_stats([item("old", "1944-12-31T13:00:00Z"), item("new", "2020-01-01T00:00:00Z")])
    assert stats["dates_note"].startswith("1 items start before 1990 (old)")


def test_stats_without_early_scenes_says_so():
    stats = collection_stats([item("new", "2020-01-01T00:00:00Z")])
    assert stats["dates_note"] == "No item in this collection starts before 1990."


def test_gsd_note_counts_degree_like_and_large_values():
    assert gsd_note([3.8e-7, 0.05, 30.0, 1000.0]) == "In this collection 1 items have gsd below 0.0001 and 2 have gsd of 10 or more, up to 1,000."


def test_gsd_note_when_all_plausible():
    assert gsd_note([0.05, 0.3]).startswith("Every item in this collection")


def test_stats_example_point_is_newest_scene_centre():
    stats = collection_stats([item("a", "2016-01-01T00:00:00Z"), item("b", "2020-01-01T00:00:00Z", bbox=(10, 20, 12, 22))])
    assert (stats["lon"], stats["lat"]) == ("11.0", "21.0")


def test_rendered_collection_metadata_puts_host_last():
    stats = collection_stats([item("a", "2020-01-01T00:00:00Z")])
    metadata = yaml.safe_load(render_collection_metadata("CC-BY-NC-4.0", {**stats, "degree_gsd_summary": "s"}, "2026-10-06T17:48:03Z"))
    assert metadata["providers"][-1]["roles"] == ["host"]


def test_rendered_collection_metadata_carries_license():
    stats = collection_stats([item("a", "2020-01-01T00:00:00Z")])
    metadata = yaml.safe_load(render_collection_metadata("CC-BY-NC-4.0", {**stats, "degree_gsd_summary": "s"}, "2026-10-06T17:48:03Z"))
    assert metadata["license"] == "CC-BY-NC-4.0"


def test_multihash_sha256_prefixes_digest(tmp_path):
    path = tmp_path / "f.bin"
    path.write_bytes(b"abc")
    assert multihash_sha256(str(path)) == "1220ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_platform_phrase_skips_empty_platforms():
    assert platform_phrase({"uav": 604, "aircraft": 39, "satellite": 1396, "kite": 0}) == "drones (604), aircraft (39) and satellites (1,396)"


def test_degree_gsd_summary_counts_geographic_cogs():
    tiny = item("a", "2020-01-01T00:00:00Z", gsd=3.8e-7)
    tiny["assets"]["visual"]["proj:code"] = "EPSG:4326"
    summary = degree_gsd_summary([tiny, item("b", "2020-01-01T00:00:00Z")])
    assert summary.startswith("Across the catalog, 1 of the 1 items")


def test_localize_maps_public_url_to_catalog(tmp_path):
    sql = "SELECT * FROM read_parquet('https://data.source.coop/x/y/a/items.parquet')"
    assert localize(sql, "https://data.source.coop/x/y/", str(tmp_path)) == f"SELECT * FROM read_parquet('{tmp_path}/a/items.parquet')"


def test_year_catalog_description_links_agents_absolutely():
    catalog = year_catalog("oam-cc-by-4-0", "CC-BY-4.0", "2016", [item("a", "2016-01-01T00:00:00Z")], AGENTS_URL)
    assert f"[AGENTS.md]({AGENTS_URL})" in catalog["description"]


def test_rendered_collection_description_links_agents_on_source_coop():
    stats = collection_stats([item("a", "2020-01-01T00:00:00Z")])
    text = render_collection_metadata("CC-BY-NC-4.0", {**stats, "degree_gsd_summary": "s"}, "2026-10-06T17:48:03Z", "https://data.source.coop/x/y/")
    assert "[AGENTS.md](https://source.coop/x/y/oam-cc-by-nc-4-0/AGENTS.md)" in yaml.safe_load(text)["description"]
