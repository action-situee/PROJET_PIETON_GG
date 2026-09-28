import geopandas as gpd
import pandas as pd
import numpy as np
import shapely
from shapely import area as shp_area, length as shp_length, intersection as shp_intersection, make_valid as shp_make_valid


def extract_buffer_feature(
    segments_gdf: gpd.GeoDataFrame,
    feature_gdf: gpd.GeoDataFrame,
    feature_name: str,
    *,
    geom_kind: str,                    # "point" | "line" | "polygon"
    how: str,                          # "presence" | "count" | "sum" | "mean" | "length_ratio" | "area_ratio" | "length_area_ratio" | "raster"
    buffer_radius: float = 50.0,
    value_column: str | None = None,   # required if how in {"sum","mean"} (for point/line/polygon attrs) or for "raster" (point value)
    crs_meter_epsg: int | None = None,
    predicate: str | None = None,
    feature_query: str | None = None,
    segment_length_col: str | None = None,
    zero_for_missing: bool = True,
    raster_stats: str = "mean",
    buffer_resolution: int = 8,
) -> pd.DataFrame:
    """
    Compute segment-level features within segment buffers, fast.

    Fast-path design:
    - Presence / count / sum / mean: vectorized via sjoin + groupby
    - area_ratio (polygons) and length_area_ratio (polygons in buffers):
        -> Avoid expensive overlay. Use either:
            (a) preunion_geometry (unary_union of all polygons) if provided (fastest), OR
            (b) spatial index to fetch candidates + vectorized pairwise intersections.
    - length_ratio (lines): spatial index + vectorized intersections with buffers, then total length / segment length.

    Parameters
    ----------
    segments_gdf : GeoDataFrame
        Must contain 'segment_id' and 'geometry' (projected CRS in meters recommended).
    feature_gdf : GeoDataFrame
        Feature layer (points/lines/polygons) used to compute statistics.
    feature_name : str
        Output column name.
    geom_kind : {"point","line","polygon"}
        Geometry type of feature_gdf (used to guard certain 'how' modes).
    how : {"presence","count","sum","mean","length_ratio","area_ratio","length_area_ratio","raster"}
        Aggregation mode (see below).
    buffer_radius : float
        Buffer radius (in meters if CRS is projected).
    value_column : str | None
        Numeric attribute to aggregate for 'sum'/'mean' (and for 'raster' if using points-as-raster-samples).
    crs_meter_epsg : int | None
        EPSG for projected (meter) CRS. If None, segments_gdf must already be projected.
    predicate : str | None
        Spatial join predicate (default "intersects"). For points you may use "within"/"contains" if needed.
    feature_query : str | None
        Optional pandas-style query string to pre-filter feature_gdf.
    segment_length_col : str | None
        Optional length column already present in segments_gdf (avoid recomputing).
    zero_for_missing : bool
        If True, fill NaNs with 0 for segments with no matches.
    raster_stats : str
        Only "mean" is currently implemented (for point-based "raster" mode).
    buffer_resolution : int
        Shapely buffer resolution (default 8; lower is faster).
    preunion_geometry : shapely.Geometry | None
        If provided (e.g., shapely.unary_union of feature polygons/lines), uses it to compute intersections
        in one shot. Ideal for repeated calls with the same feature layer.

    Returns
    -------
    DataFrame with columns ["segment_id", feature_name]
    """
    # --- Guards ----------------------------------------------------------------
    if geom_kind not in {"point", "line", "polygon"}:
        raise ValueError("geom_kind must be 'point', 'line', or 'polygon'")
    if how not in {"presence", "count", "sum", "mean", "length_ratio", "area_ratio", "length_area_ratio", "raster"}:
        raise ValueError("how must be one of the supported modes.")
    if how == "length_ratio" and geom_kind != "line":
        raise ValueError("length_ratio requires geom_kind='line'")
    if how == "area_ratio" and geom_kind != "polygon":
        raise ValueError("area_ratio requires geom_kind='polygon'")
    if how in {"sum", "mean"} and not value_column:
        raise ValueError(f"how='{how}' requires value_column")
    if predicate is None:
        predicate = "intersects"

    # --- Copy & CRS handling ---------------------------------------------------
    seg = segments_gdf[["segment_id", "geometry"]].copy()
    feat = feature_gdf.copy()

    if feature_query:
        feat = feat.query(feature_query)

    # Ensure projected CRS (meters)
    if crs_meter_epsg is not None:
        if seg.crs is None or not seg.crs.is_projected or seg.crs.to_epsg() != crs_meter_epsg:
            seg = seg.to_crs(crs_meter_epsg)
        if feat.crs is None or feat.crs != seg.crs:
            feat = feat.to_crs(seg.crs)
    elif seg.crs is None or not seg.crs.is_projected:
        raise ValueError("Segments must be in a projected CRS (meters) or pass crs_meter_epsg.")

    # --- Segment length (if needed) -------------------------------------------
    if segment_length_col and segment_length_col in segments_gdf.columns:
        seg = seg.merge(segments_gdf[["segment_id", segment_length_col]], on="segment_id", how="left")
        seg_len = seg[segment_length_col].to_numpy()
    else:
        seg_len = seg.geometry.length.to_numpy()

    # --- Buffer once; reuse ----------------------------------------------------
    seg_buf_geom = seg.geometry.buffer(buffer_radius, resolution=buffer_resolution)
    # Buffer area used by area-based ratios:
    buf_area = shapely.area(seg_buf_geom)

    # --- Fix invalid geometries only when necessary ---------------------------
    if not feat.geometry.is_valid.all():
        # Shapely 2: make_valid is robust and usually faster than buffer(0)
        feat["geometry"] = shp_make_valid(feat.geometry.values)

    # --- Simple modes via sjoin ------------------------------------------------
    if how in {"presence", "count", "sum", "mean"}:
        right_cols = ["geometry"] if how in {"presence", "count"} else ["geometry", value_column]
        left = gpd.GeoDataFrame(seg[["segment_id"]].copy(), geometry=seg_buf_geom, crs=seg.crs)

        joined = gpd.sjoin(
            left,
            feat[right_cols],
            how="inner",
            predicate=predicate
        )

        if joined.empty:
            out = seg[["segment_id"]].copy()
            if how == "presence":
                out[feature_name] = 0
            else:
                out[feature_name] = 0.0 if zero_for_missing else pd.NA
            return out

        if how == "presence":
            agg = (joined.groupby("segment_id").size().gt(0).astype(int)
                   .rename(feature_name).reset_index())
            out = seg[["segment_id"]].merge(agg, on="segment_id", how="left")
            out[feature_name] = out[feature_name].fillna(0).astype(int) if zero_for_missing else out[feature_name]
            return out[["segment_id", feature_name]]

        if how == "count":
            agg = joined.groupby("segment_id").size().rename(feature_name).reset_index()
            out = seg[["segment_id"]].merge(agg, on="segment_id", how="left")
            out[feature_name] = out[feature_name].fillna(0.0) if zero_for_missing else out[feature_name]
            return out[["segment_id", feature_name]]

        # sum / mean on numeric attribute
        joined[value_column] = pd.to_numeric(joined[value_column], errors="coerce")
        if how == "sum":
            agg = (joined.groupby("segment_id")[value_column]
                         .sum(min_count=1)
                         .rename(feature_name)
                         .reset_index())
        else:  # mean
            agg = (joined.groupby("segment_id")[value_column]
                         .mean()
                         .rename(feature_name)
                         .reset_index())
        out = seg[["segment_id"]].merge(agg, on="segment_id", how="left")
        if zero_for_missing:
            out[feature_name] = out[feature_name].fillna(0.0)
        return out[["segment_id", feature_name]]

    # --- Helper: pairwise vectorized intersections via spatial index ----------
    def _pairwise_intersections_sum_metric(seg_buffers: np.ndarray, feat_geom: gpd.GeoSeries, metric: str) -> np.ndarray:
        """
        For each buffer, use the spatial index to get candidate features, compute
        vectorized intersections, and sum the chosen metric ("area" or "length").
        Returns a numpy array of per-buffer totals aligned with seg_buffers.
        """
        sidx = feat_geom.sindex
        n = len(seg_buffers)
        totals = np.zeros(n, dtype="float64")

        # candidate lookup per buffer (bbox filter)
        for i, b in enumerate(seg_buffers):
            if b is None or b.is_empty:
                continue
            # FIX: Use intersection() with bounds tuple, not query()
            cand_idx = list(sidx.intersection(b.bounds))
            if not cand_idx:
                continue

            A = np.repeat(b, len(cand_idx))  # same buffer vs multiple features
            B = feat_geom.values[np.array(cand_idx)]
            inter = shp_intersection(A, B)
            if metric == "area":
                vals = shp_area(inter)
            elif metric == "length":
                vals = shp_length(inter)
            else:
                raise ValueError("metric must be 'area' or 'length'")
            if np.size(vals) > 0:
                # vals may be a scalar if a single geom; coerce to float
                totals[i] = np.nansum(np.asarray(vals, dtype="float64"))
        return totals

    # --- area_ratio (polygons inside buffer) ----------------------------------
    if how == "area_ratio":
        out = seg[["segment_id"]].copy()

        # Use spatial-index driven pairwise intersections (much faster)
        inter_area = _pairwise_intersections_sum_metric(seg_buf_geom.values, feat.geometry, metric="area")

        # ratio = area covered by polygons / total buffer area
        denom = buf_area.copy()
        denom[denom == 0] = np.nan
        ratio = np.divide(inter_area, denom)
        ratio = np.clip(ratio, 0.0, 1.0)
        if zero_for_missing:
            ratio = np.nan_to_num(ratio, nan=0.0)
        out[feature_name] = ratio
        return out

    # --- length_area_ratio (polygon coverage proportion in buffer) -----------
    if how == "length_area_ratio":
        out = seg[["segment_id"]].copy()

        inter_area = _pairwise_intersections_sum_metric(seg_buf_geom.values, feat.geometry, metric="area")

        denom = buf_area.copy()
        denom[denom == 0] = np.nan
        ratio = np.divide(inter_area, denom)
        ratio = np.clip(ratio, 0.0, 1.0)
        if zero_for_missing:
            ratio = np.nan_to_num(ratio, nan=0.0)
        out[feature_name] = ratio
        return out[["segment_id", feature_name]]

    # --- length_ratio (total length of linework in buffer / segment length) ---
    if how == "length_ratio":
        out = seg[["segment_id"]].copy()

        # Use spatial-index driven pairwise intersections (much faster)
        inter_len = _pairwise_intersections_sum_metric(seg_buf_geom.values, feat.geometry, metric="length")

        denom = seg_len.copy().astype("float64")
        denom[denom == 0] = np.nan
        ratio = np.divide(inter_len, denom)
        ratio = np.clip(ratio, 0.0, 1.0)
        if zero_for_missing:
            ratio = np.nan_to_num(ratio, nan=0.0)
        out[feature_name] = ratio
        return out[["segment_id", feature_name]]

    # --- "raster" mode (point samples as proxy; mean in buffers) --------------
    # NOTE: This keeps your original approach (points-in-buffers). If you truly
    # have a raster, prefer rasterstats.zonal_stats upstream and pass the result.
    if how == "raster":
        if value_column is None:
            raise ValueError("how='raster' requires value_column (point attribute).")

        left = gpd.GeoDataFrame(seg[["segment_id"]].copy(), geometry=seg_buf_geom, crs=seg.crs)
        joined = gpd.sjoin(
            left,
            feat[["geometry", value_column]],
            how="left",
            predicate="intersects"
        )

        out = seg[["segment_id"]].copy()
        if joined.empty:
            out[feature_name] = 0.0 if zero_for_missing else pd.NA
            return out

        joined[value_column] = pd.to_numeric(joined[value_column], errors="coerce")
        if raster_stats == "mean":
            agg = joined.groupby("segment_id")[value_column].mean()
        else:
            raise ValueError(f"Unsupported raster_stats: {raster_stats}")

        out = out.merge(agg.rename(feature_name).reset_index(), on="segment_id", how="left")
        if zero_for_missing:
            out[feature_name] = out[feature_name].fillna(0.0)
        return out[["segment_id", feature_name]]

    # Fallback (shouldn't happen with guards above)
    raise RuntimeError("Unhandled 'how' branch.")