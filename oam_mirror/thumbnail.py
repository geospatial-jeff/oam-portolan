"""Draw a collection thumbnail: scene footprint centroids over Natural Earth land.

The COGs are hosted upstream and span the globe, so a coverage map is the
only preview that shows the whole collection. The image is 3:2, the data
browser's card shape.
"""

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

LAND = "#d9d6cf"
OCEAN = "#f4f2ee"
EXTENT = (-180, 180, -60, 80)


def _land_rings(land_geojson_path):
    with open(land_geojson_path) as f:
        land = json.load(f)
    for feature in land["features"]:
        geometry = feature["geometry"]
        polygons = geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
        for polygon in polygons:
            yield polygon[0]


def draw(items, land_geojson_path, out_path, color):
    """Write a PNG of item bbox centres over land."""
    fig = plt.figure(figsize=(6, 4), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_facecolor(OCEAN)
    for ring in _land_rings(land_geojson_path):
        ax.fill([p[0] for p in ring], [p[1] for p in ring], color=LAND, linewidth=0)
    xs = [(item["bbox"][0] + item["bbox"][2]) / 2 for item in items]
    ys = [(item["bbox"][1] + item["bbox"][3]) / 2 for item in items]
    ax.scatter(xs, ys, s=6, c=color, alpha=0.6, linewidths=0)
    ax.set_xlim(EXTENT[0], EXTENT[1])
    ax.set_ylim(EXTENT[2], EXTENT[3])
    # Equal aspect keeps shapes honest; the 3:2 frame letterboxes in ocean colour.
    ax.set_aspect("equal", adjustable="box")
    ax.set_axis_off()
    fig.savefig(out_path, facecolor=OCEAN)
    plt.close(fig)
