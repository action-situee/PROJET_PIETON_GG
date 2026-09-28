import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import networkx as nx
from shapely.geometry import LineString, MultiLineString
from shapely.ops import linemerge


def _as_linestring(geom):
    if geom is None or geom.is_empty:
        return None
    if isinstance(geom, LineString):
        return geom
    if isinstance(geom, MultiLineString):
        merged = linemerge(geom)
        if isinstance(merged, LineString):
            return merged
        if isinstance(merged, MultiLineString) and len(merged.geoms) > 0:
            return max(merged.geoms, key=lambda part: part.length)
    return None


def _endpoint_coords(geom):
    line = _as_linestring(geom)
    if line is None:
        return (np.nan, np.nan), (np.nan, np.nan)
    coords = list(line.coords)
    if len(coords) < 2:
        return (np.nan, np.nan), (np.nan, np.nan)
    start_xy = coords[0][:2]
    end_xy = coords[-1][:2]
    return start_xy, end_xy


def _sample_band(src, coords):
    sampled = list(src.sample(coords, indexes=1, masked=True))
    values = np.empty(len(sampled), dtype="float64")
    values.fill(np.nan)

    for index, value in enumerate(sampled):
        scalar = value[0]
        if np.ma.is_masked(scalar):
            continue
        values[index] = float(scalar)

    nodata = src.nodata
    if nodata is not None:
        values[np.isclose(values, nodata)] = np.nan

    return values


def _endpoint_node_ids(geom, precision: int = 3):
    start_xy, end_xy = _endpoint_coords(geom)

    def _node_id(xy):
        x, y = xy
        if np.isnan(x) or np.isnan(y):
            return None
        return (round(float(x), precision), round(float(y), precision))

    return _node_id(start_xy), _node_id(end_xy)


def _gaussian_topology_smoothing(values: pd.Series, segment_nodes: pd.DataFrame, sigma: float, hops: int) -> pd.Series:
    graph = nx.Graph()

    for row in segment_nodes.itertuples(index=False):
        graph.add_node(row.segment_id)

    node_to_segments: dict[tuple[float, float], list[str]] = {}
    for row in segment_nodes.itertuples(index=False):
        for node in (row.u, row.v):
            if node is None:
                continue
            node_to_segments.setdefault(node, []).append(row.segment_id)

    for segment_ids in node_to_segments.values():
        if len(segment_ids) < 2:
            continue
        for index, segment_id in enumerate(segment_ids):
            for other_segment_id in segment_ids[index + 1:]:
                graph.add_edge(segment_id, other_segment_id)

    smooth_values = pd.Series(index=values.index, dtype="float64")
    min_weight = np.exp(-(hops ** 2) / (2.0 * sigma ** 2)) if hops > 0 else 1.0

    for segment_id in values.index:
        if pd.isna(values.loc[segment_id]):
            smooth_values.loc[segment_id] = np.nan
            continue

        lengths = nx.single_source_shortest_path_length(graph, segment_id, cutoff=hops)
        weights = []
        neighbor_values = []

        for neighbor_id, distance in lengths.items():
            neighbor_value = values.loc[neighbor_id]
            if pd.isna(neighbor_value):
                continue
            weight = np.exp(-((distance ** 2) / (2.0 * sigma ** 2)))
            if weight < min_weight:
                continue
            weights.append(weight)
            neighbor_values.append(float(neighbor_value))

        if not weights:
            smooth_values.loc[segment_id] = values.loc[segment_id]
            continue

        smooth_values.loc[segment_id] = np.average(neighbor_values, weights=weights)

    return smooth_values


def compute_segment_slope(
    segmented_net: gpd.GeoDataFrame,
    raster_path: str,
    *,
    crs_meter_epsg: int | None = None,
    length_col: str | None = None,
    smooth_sigma: float | None = None,
    smooth_hops: int = 1,
    keep_original_cols: bool = True,
) -> gpd.GeoDataFrame:
    """
    Calcule une pente moyenne par troncon a partir de l'altitude des deux extremites.

    Colonnes ajoutees:
      - elev_start_m
      - elev_end_m
      - elev_delta_m
      - slope_pct_signed
      - slope_pct_abs
            - slope_pct_abs_smoothed
    """
    original_cols = list(segmented_net.columns)
    gdf = segmented_net.copy()

    if "segment_id" not in gdf.columns:
        raise ValueError("segmented_net must contain 'segment_id'.")
    if gdf.crs is None:
        raise ValueError("segmented_net must have a CRS.")

    metric_gdf = gdf
    if crs_meter_epsg is not None:
        if metric_gdf.crs.to_epsg() != crs_meter_epsg:
            metric_gdf = metric_gdf.to_crs(crs_meter_epsg)
    elif not metric_gdf.crs.is_projected:
        raise ValueError("Pass crs_meter_epsg or provide segmented_net in a projected CRS.")

    if length_col and length_col in metric_gdf.columns:
        lengths_m = metric_gdf[length_col].astype("float64").to_numpy()
    else:
        lengths_m = metric_gdf.geometry.length.astype("float64").to_numpy()

    with rasterio.open(raster_path) as src:
        sample_gdf = gdf.to_crs(src.crs) if gdf.crs != src.crs else gdf

        endpoint_pairs = sample_gdf.geometry.apply(_endpoint_coords)
        start_coords = [pair[0] for pair in endpoint_pairs]
        end_coords = [pair[1] for pair in endpoint_pairs]

        start_z = _sample_band(src, start_coords)
        end_z = _sample_band(src, end_coords)

    delta_z = end_z - start_z

    lengths_safe = lengths_m.copy()
    lengths_safe[lengths_safe == 0] = np.nan
    slope_signed = np.divide(delta_z, lengths_safe) * 100.0
    slope_abs = np.abs(slope_signed)

    gdf["elev_start_m"] = start_z
    gdf["elev_end_m"] = end_z
    gdf["elev_delta_m"] = delta_z
    gdf["slope_pct_signed"] = slope_signed
    gdf["slope_pct_abs"] = slope_abs

    if smooth_sigma is not None:
        if smooth_sigma <= 0:
            raise ValueError("smooth_sigma must be > 0.")
        if smooth_hops < 1:
            raise ValueError("smooth_hops must be >= 1.")

        node_pairs = metric_gdf.geometry.apply(_endpoint_node_ids)
        segment_nodes = pd.DataFrame({
            "segment_id": gdf["segment_id"].to_numpy(),
            "u": [pair[0] for pair in node_pairs],
            "v": [pair[1] for pair in node_pairs],
        })
        slope_series = pd.Series(gdf["slope_pct_abs"].to_numpy(), index=gdf["segment_id"].to_numpy())
        smoothed = _gaussian_topology_smoothing(
            slope_series,
            segment_nodes,
            sigma=smooth_sigma,
            hops=smooth_hops,
        )
        gdf["slope_pct_abs_smoothed"] = gdf["segment_id"].map(smoothed)
    else:
        gdf["slope_pct_abs_smoothed"] = gdf["slope_pct_abs"]

    if keep_original_cols:
        return gdf[original_cols + [
            "elev_start_m",
            "elev_end_m",
            "elev_delta_m",
            "slope_pct_signed",
            "slope_pct_abs",
            "slope_pct_abs_smoothed",
        ]]
    return gdf