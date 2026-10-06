## This repository

A git-backed [Portolan](https://www.portolan-sdi.org/) catalog that mirrors the item metadata of [OpenAerialMap](https://imagery.hotosm.org/) (HOT's OAM v2 STAC API). It publishes to [source.coop/geospatialjeff/oam-portolan](https://source.coop/geospatialjeff/oam-portolan). The imagery stays on HOT's `oin-hotosm-temp` bucket, and the catalog points at it.

### Two parts: committed and generated

`python -m oam_mirror.build` writes the full catalog to `build/site/`, which is gitignored. `python -m oam_mirror.export` then copies the committed part into `catalog/`.

| Part | What | Tracked | Published by |
|---|---|---|---|
| Committed | root `catalog.json`, `AGENTS.md`, `README.md`; per collection `collection.json`, `AGENTS.md`, `README.md`, `thumbnail.png` | yes, in `catalog/` | `tools/publish.py` |
| Generated | 21,863 item JSONs, 46 year subcatalogs, each collection's `items.parquet` | no, in `build/site/` | `tools/upload_generated.py` |

The item tree is too large to commit, as the spec's git-backed catalogs guide advises for large item collections. Fields of the World uses the same split. `docs/conformance.md` explains the two scoped gate exemptions this causes in a checkout.

### The loop

```bash
python -m oam_mirror.harvest data/openaerialmap.ndjson       # refresh from HOT
python -m oam_mirror.build data/openaerialmap.ndjson build/site
(cd build/site && portolan check --data-scope local)          # full catalog
python -m oam_mirror.export build/site catalog --public-url https://data.source.coop/geospatialjeff/oam-portolan/
python -m oam_mirror.verify_docs build/site --local https://data.source.coop/geospatialjeff/oam-portolan/
python -m pytest -q tests/unit
python3 tests/run_all.py                                      # committed catalog gates
python3 tools/publish.py && python3 tools/upload_generated.py # dry runs
python3 tools/upload_generated.py --confirm                   # generated tree first
python3 tools/publish.py --confirm                            # then the collections that link to it
```

The build needs portolan-cli 0.8.0 on `PATH` for `init`, `stac-geoparquet` and `readme`. Set `GPIO` to the `gpio` that ships inside the portolan-cli tool environment. Uploads use the `source-coop` AWS profile described in `catalog.publish.yaml`, after `source-coop login`.

`--data-scope local` matters. Without it, `portolan check` reads all 21,863 remote COGs. Never run `portolan check --fix` here, because it would download every COG to compute checksums.

### Edit the generator, not generated output

Do not hand-edit `catalog/` or `build/site/`. A rebuild overwrites the edit.

- Change prose in `metadata/`. `catalog.yaml`, `collection.yaml` and `year.yaml` feed the descriptions and READMEs. The `AGENTS.*.md` files are the agent-guide templates.
- Change item handling in `oam_mirror/transform.py`. List every change there in the `processing_notes` of `metadata/collection.yaml`.
- Change the tree layout in `oam_mirror/layout.py`, and the committed/generated split in `oam_mirror/export.py`.

### Publishing

Publish with `tools/publish.py` and `tools/upload_generated.py`, never `portolan push`. `portolan push` uploads only the files portolan-cli tracks in `versions.json`, and the build deletes those. Neither script deletes. Removing a file locally does not unpublish it.

The root `self` link is written into the committed `catalog.json` from `--public-url`. The skill allows this. The spec guide prefers a publish-step rewrite. Change `REPO_URL` and `DEFAULT_PUBLIC_URL` in `oam_mirror/build.py` together with `catalog.publish.yaml` if the catalog moves.

### Data never enters git

Never commit a GeoParquet, COG, PMTiles, Zarr or COPC file. `items.parquet` is generated and uploaded. The committed collections reference it by its published URL.

### The conformance allow-list

`ACCEPTED` in `tests/test_conformance.py` ships empty. Never add an entry without a matching row in `docs/conformance.md` giving the rule, where it fires, why it is accepted, and the issue tracking its removal. The generated-tree exemptions are matched by file and target, not by rule id. Keep them that narrow.

### Published agent guides

Every claim in a published `AGENTS.md` is either quoted from a source or measured from the data. Every SQL recipe must run. `python -m oam_mirror.verify_docs` executes them.

### Personal data

Upstream items carry uploader email addresses. `oam_mirror/transform.py` removes them, and nothing published may contain one. Check for them after any transform change.

### The links back to this repository

The build writes the root `vcs` and `issues` links from `REPO_URL`. Keep both absolute, because the repository sits outside the published catalog.
