# oam-portolan

A [Portolan](https://www.portolan-sdi.org/) catalog of [OpenAerialMap](https://imagery.hotosm.org/), the open drone, aircraft and satellite imagery service run by the [Humanitarian OpenStreetMap Team](https://www.hotosm.org/).

- **Published:** [source.coop/geospatialjeff/oam-portolan](https://source.coop/geospatialjeff/oam-portolan) ([catalog.json](https://data.source.coop/geospatialjeff/oam-portolan/catalog.json))
- **Browse:** [Portolan Browser](https://browser.portolan-sdi.org/#/external/data.source.coop/geospatialjeff/oam-portolan/catalog.json)

The catalog mirrors the metadata of every scene in HOT's OAM v2 STAC API (21,863 scenes on 2026-10-06). The imagery stays where HOT hosts it, as Cloud Optimized GeoTIFFs in `s3://oin-hotosm-temp` (us-east-1). Scenes are split into three collections by license (CC BY 4.0, CC BY-SA 4.0, CC BY-NC 4.0) and grouped by acquisition year. Each collection has an `items.parquet` for searching every scene in one query.

The mirror removes uploader email addresses and fixes a few STAC validity problems in the upstream metadata. Each collection's README lists every change.

## How this repository works

The build writes the whole catalog to `build/site/`. Only the root and the three collections are committed in `catalog/`. The 21,863 items, their year subcatalogs and the `items.parquet` indexes are generated and uploaded without passing through git, the way the [git-backed catalogs guide](https://github.com/portolan-sdi/portolan-spec/blob/main/specs/best-practices/git-backed-catalogs.md) recommends for large item collections.

| Path | What it is |
|---|---|
| `oam_mirror/` | Harvest, transform, layout, build, export, doc check, local server |
| `metadata/` | Hand-written descriptions, metadata and `AGENTS.md` templates |
| `catalog/` | The committed part of the catalog: root and collections |
| `tools/publish.py` | Sync `catalog/` to Source Cooperative. Dry run by default |
| `tools/upload_generated.py` | Upload the generated items, year catalogs and `items.parquet`. Dry run by default |
| `tests/run_all.py` | Catalog gates: links, STAC validity, Portolan conformance |
| `tests/unit/` | Generator unit tests |

[AGENTS.md](AGENTS.md) has the rebuild and publish loop, and [docs/conformance.md](docs/conformance.md) explains the two validator exemptions the generated tree causes in a checkout.

## Reporting a problem

Open an [issue](https://github.com/geospatial-jeff/oam-portolan/issues). Problems with the imagery itself, or with the upstream metadata, belong to [HOT's OpenAerialMap](https://github.com/hotosm/openaerialmap/issues).
