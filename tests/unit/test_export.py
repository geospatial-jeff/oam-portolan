import json

import pytest

from oam_mirror.export import export_committed, generated_files

PUBLIC = "https://data.source.coop/x/y/"


@pytest.fixture
def site(tmp_path):
    root = tmp_path / "site"
    (root / ".portolan").mkdir(parents=True)
    (root / ".portolan" / "config.yaml").write_text("# cfg\n")
    root_doc = {"type": "Catalog", "links": [{"rel": "child", "href": "./oam-a/collection.json"}]}
    (root / "catalog.json").write_text(json.dumps(root_doc))
    for name in ("AGENTS.md", "README.md"):
        (root / name).write_text(name)
    coll = root / "oam-a"
    (coll / "2016" / "abc").mkdir(parents=True)
    collection = {"type": "Collection", "assets": {"geoparquet-items": {"href": "./items.parquet"}}}
    (coll / "collection.json").write_text(json.dumps(collection))
    for name in ("AGENTS.md", "README.md", "thumbnail.png", "items.parquet"):
        (coll / name).write_text(name)
    (coll / "2016" / "catalog.json").write_text("{}")
    (coll / "2016" / "AGENTS.md").write_text("y")
    (coll / "2016" / "abc" / "abc.json").write_text("{}")
    return root


def test_export_copies_root_and_collection_documents(site, tmp_path):
    out = tmp_path / "catalog"
    export_committed(str(site), str(out), PUBLIC)
    copied = sorted(p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file())
    assert copied == [
        "AGENTS.md", "README.md", "catalog.json",
        "oam-a/AGENTS.md", "oam-a/README.md", "oam-a/collection.json", "oam-a/thumbnail.png",
    ]


def test_export_makes_item_mirror_href_absolute(site, tmp_path):
    out = tmp_path / "catalog"
    export_committed(str(site), str(out), PUBLIC)
    collection = json.loads((out / "oam-a" / "collection.json").read_text())
    assert collection["assets"]["geoparquet-items"]["href"] == PUBLIC + "oam-a/items.parquet"


def test_generated_files_are_the_site_minus_committed_and_dotfiles(site):
    assert generated_files(str(site)) == [
        "oam-a/2016/AGENTS.md", "oam-a/2016/abc/abc.json", "oam-a/2016/catalog.json", "oam-a/items.parquet",
    ]
