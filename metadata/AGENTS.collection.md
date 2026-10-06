# $title: agent guide

$count OpenAerialMap scenes licensed $license_name ($license_id). Each scene is one STAC item. The pixels are a Cloud Optimized GeoTIFF on OpenAerialMap's S3 bucket, and this catalog does not copy them. The mirror snapshot was taken $harvested_at.

The catalog has one collection per license: `oam-cc-by-4-0`, `oam-cc-by-sa-4-0` and `oam-cc-by-nc-4-0`. All three share one schema. Read them together when the license does not matter (see the last recipe).

## Keys and identity

- `id` is the OpenAerialMap STAC item id, unchanged. It is a 24-character hex id for scenes from the legacy OAM catalogue and a UUID for uploads made in v2. The same id works in the upstream STAC API, `https://api.imagery.hotosm.org/stac/collections/openaerialmap/items/{id}`, and in HOT's tile server (see "Tiles without reading the COG").
- `title` is free text written by the uploader and is not unique. Do not join on it.
- `properties.providers[0].name` and `oam:producer_name` name the producer to credit. They differ from the uploader: `oam:uploader_name` is set only for recent uploads.

## Files

- `items.parquet` in this directory holds one row per item (stac-geoparquet). Use it for every search. Item JSON sits under `<year>/<id>/<id>.json`, where `<year>` is the year the acquisition started (`pre-2010` groups the earlier years).
- Each item's COG is `assets.visual.href` (https). `assets.visual.alternate.s3.href` gives the `s3://oin-hotosm-temp/...` form for tools that read the bucket directly. Other assets are `thumbnail` (PNG), `metadata` (OpenAerialMap's upload JSON) and, on a few recent items, `original` (the unconverted upload, role `source`), `pmtiles` and `mbtiles`.

## Quirks that change answers

- **Time is an interval.** Most items have `datetime: null` and carry `start_datetime` and `end_datetime`. Filter on `coalesce(datetime, start_datetime)`.
- **`gsd` is in CRS units, not always metres.** $degree_gsd_summary $gsd_note Guard resolution filters with `gsd BETWEEN 0.005 AND 100`, or compute the resolution from `proj:transform` and `proj:code`.
- **The COG's CRS is the uploader's.** It is in `assets.visual."proj:code"` (EPSG:4326, EPSG:3857, many UTM zones; $wkt2_items items in this collection give `proj:wkt2` instead). Item `geometry` and `bbox` are always WGS84 lon/lat.
- **Black borders.** Older COGs often have no mask: in a random sample of 40 scenes, 16 had none. Treat 0 as nodata when you mosaic or render them.
- **Not all scenes are RGB.** The sample had 33 three-band, 5 four-band and 2 single-band COGs, 38 of them 8-bit. `oam:product_type` exists only on recent uploads, so check the band count before you assume RGB.
- **Dates.** $dates_note

## Recipes

Run these with DuckDB 1.3 or later. DuckDB reads the published files over HTTP range requests, so nothing is downloaded in full.

Scenes that cover a point, best resolution first:

```sql
INSTALL spatial; LOAD spatial;
SELECT id, title, coalesce(datetime, start_datetime) AS acquired, gsd,
       "oam:platform_type" AS platform, assets.visual.href AS cog
FROM read_parquet('${base}$collection_id/items.parquet')
WHERE bbox.xmin <= $lon AND bbox.xmax >= $lon
  AND bbox.ymin <= $lat AND bbox.ymax >= $lat
  AND ST_Intersects(geometry, ST_Point($lon, $lat))
ORDER BY gsd;
```

Scenes per year and platform:

```sql
SELECT year(coalesce(datetime, start_datetime)) AS year,
       "oam:platform_type" AS platform, count(*) AS scenes
FROM read_parquet('${base}$collection_id/items.parquet')
GROUP BY ALL ORDER BY year, platform;
```

Who to credit for a set of scenes:

```sql
SELECT providers[1].name AS producer, count(*) AS scenes
FROM read_parquet('${base}$collection_id/items.parquet')
GROUP BY producer ORDER BY scenes DESC LIMIT 10;
```

Every collection together, keeping the license column:

```sql
SELECT collection, coalesce(license, 'CC-BY-4.0') AS license, count(*) AS scenes
FROM read_parquet(['${base}oam-cc-by-4-0/items.parquet',
                   '${base}oam-cc-by-sa-4-0/items.parquet',
                   '${base}oam-cc-by-nc-4-0/items.parquet'], union_by_name = true)
GROUP BY ALL ORDER BY scenes DESC;
```

`license` is null on items that inherit CC-BY-4.0 from the collection, so coalesce it. Drop `oam-cc-by-nc-4-0` for commercial work.

## Reading pixels

The COGs are tiled 512×512 with internal overviews, so GDAL reads only the bytes it needs. To clip a lon/lat window from a scene:

```bash
gdal_translate -projwin_srs EPSG:4326 \
  -projwin $clip_xmin $clip_ymax $clip_xmax $clip_ymin \
  /vsicurl/$example_cog clip.tif
```

Set `GDAL_DISABLE_READDIR_ON_OPEN=EMPTY_DIR` so GDAL does not list the bucket.

## Tiles without reading the COG

HOT runs a TiTiler for every item: `https://api.imagery.hotosm.org/raster/collections/openaerialmap/items/{id}/tiles/WebMercatorQuad/{z}/{x}/{y}?assets=visual&nodata=0`. A global XYZ mosaic is at `https://global.imagery.hotosm.org/{z}/{x}/{y}.png`; zoom 14 and above shows imagery. Both are documented in [Using OAM Imagery](https://docs.imagery.hotosm.org/usage/using-imagery/).

## Provenance

The build is in the mirror's repository, `oam_mirror/`. `python -m oam_mirror.harvest` pages the upstream STAC API. `python -m oam_mirror.build` writes this tree. `portolan stac-geoparquet` writes `items.parquet`, and `gpio sort hilbert` then orders its rows spatially in 2,048-row groups. The collection README lists every change made to the upstream metadata. In short: emails are removed, `datetime: null` is added, http links become https, and one inverted bbox is fixed.
