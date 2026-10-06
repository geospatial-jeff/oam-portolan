# OpenAerialMap (Portolan mirror): agent guide

This is a static STAC mirror of the $total scenes in [OpenAerialMap](https://imagery.hotosm.org/), harvested $harvested_at. The item metadata is local. The imagery stays on OpenAerialMap's S3 bucket as Cloud Optimized GeoTIFFs.

## Pick a collection by license

OpenAerialMap licenses each image separately, so the catalog has three collections:

| Collection | License | Scenes |
|---|---|---|
$collection_rows

Items with no `license` property inherit CC-BY-4.0 from the upstream collection. They sit in `oam-cc-by-4-0`. Exclude `oam-cc-by-nc-4-0` from anything commercial. CC BY-SA requires derivatives to carry the same license.

## Start here

Each collection has an `items.parquet` with one row per scene, and an `AGENTS.md` with tested queries, quirks and pixel-reading recipes. Read the collection guide before you filter on `gsd` or dates, because both have traps. To query all scenes at once:

```sql
SELECT collection, count(*) AS scenes
FROM read_parquet(['${base}oam-cc-by-4-0/items.parquet',
                   '${base}oam-cc-by-sa-4-0/items.parquet',
                   '${base}oam-cc-by-nc-4-0/items.parquet'], union_by_name = true)
GROUP BY collection;
```

## Upstream

The live, always-current source is the OpenAerialMap STAC API at `https://api.imagery.hotosm.org/stac`, collection `openaerialmap`. Every item here links to its upstream copy with `rel: canonical`. Scenes uploaded after the harvest are only upstream.
