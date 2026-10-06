"""Split the built site into what git tracks and what is generated to object storage.

The build writes the whole catalog to build/site/. Only the root and the three
collection documents are committed under catalog/ and published by
tools/publish.py. The 21,863 items, their year subcatalogs and items.parquet
are too many and too large for git; tools/upload_generated.py sends them to
the bucket. This is the pattern Fields of the World uses for its Sentinel-2
item tree (see the portolan-spec git-backed catalogs guide, "Generate large
catalogs").

Usage: python -m oam_mirror.export build/site catalog
"""

import argparse
import json
import os
import shutil

from oam_mirror.layout import write_json

ROOT_FILES = ("catalog.json", "AGENTS.md", "README.md")
COLLECTION_FILES = ("collection.json", "AGENTS.md", "README.md", "thumbnail.png")
MIRROR_ASSET = "geoparquet-items"


def _collection_ids(site_root):
    with open(os.path.join(site_root, "catalog.json")) as f:
        root = json.load(f)
    return sorted(link["href"].split("/")[1] for link in root["links"] if link["rel"] == "child")


def committed_files(site_root):
    """Paths, relative to the site root, that git tracks."""
    paths = list(ROOT_FILES)
    for collection_id in _collection_ids(site_root):
        paths += [f"{collection_id}/{name}" for name in COLLECTION_FILES]
    return paths


def generated_files(site_root):
    """Paths that go to object storage only: the site minus committed files and dotfiles."""
    committed = set(committed_files(site_root))
    found = []
    for dirpath, dirnames, filenames in os.walk(site_root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for name in filenames:
            rel = os.path.relpath(os.path.join(dirpath, name), site_root).replace(os.sep, "/")
            if not name.startswith(".") and name != "versions.json" and rel not in committed:
                found.append(rel)
    return sorted(found)


def export_committed(site_root, catalog_root, public_url):
    """Copy the committed files into catalog_root.

    items.parquet is not committed, so each collection's mirror asset points
    at its published URL instead of a sibling file.
    """
    for rel in committed_files(site_root):
        source = os.path.join(site_root, rel)
        target = os.path.join(catalog_root, rel)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copyfile(source, target)
    for collection_id in _collection_ids(site_root):
        path = os.path.join(catalog_root, collection_id, "collection.json")
        with open(path) as f:
            document = json.load(f)
        if MIRROR_ASSET in document.get("assets", {}):
            document["assets"][MIRROR_ASSET]["href"] = f"{public_url}{collection_id}/items.parquet"
            write_json(path, document)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("site", help="full catalog written by oam_mirror.build")
    parser.add_argument("catalog", help="committed catalog directory")
    parser.add_argument("--public-url", required=True, help="published base URL, ending in /")
    args = parser.parse_args()
    export_committed(args.site, args.catalog, args.public_url)
    print(f"exported {len(committed_files(args.site))} committed files; {len(generated_files(args.site))} generated files stay in {args.site}")


if __name__ == "__main__":
    main()
