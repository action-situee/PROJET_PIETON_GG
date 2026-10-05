import geopandas as gpd
import pandas as pd
import numpy as np
import shapely
from shapely import area as shp_area, length as shp_length, intersection as shp_intersection, make_valid as shp_make_valid
import rasterio
from rasterio.features import rasterize
from rasterio.windows import Window, from_bounds



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








def _dilate_mask(mask: np.ndarray, n_pixels: int = 1) -> np.ndarray:
    """
    Dilatation binaire 8-connexe (carré 3x3) répétée n_pixels fois.
    Implémentée en numpy pur pour éviter une dépendance à scipy.
    """
    out = mask.copy()
    for _ in range(n_pixels):
        src = out.copy()
        out[1:, :] |= src[:-1, :]      # voisin du dessus
        out[:-1, :] |= src[1:, :]      # voisin du dessous
        out[:, 1:] |= src[:, :-1]      # voisin de gauche
        out[:, :-1] |= src[:, 1:]      # voisin de droite
        out[1:, 1:] |= src[:-1, :-1]   # diagonales
        out[1:, :-1] |= src[:-1, 1:]
        out[:-1, 1:] |= src[1:, :-1]
        out[:-1, :-1] |= src[1:, 1:]
    return out


def raster_cells_touching_network(
    raster_path: str,
    segments_gdf: gpd.GeoDataFrame,
    value_column: str = "value",
    *,
    band: int = 1,
    dilation_pixels: int = 1,
    all_touched: bool = True,
    keep_nodata: bool = False,
    verbose: bool = True,
) -> gpd.GeoDataFrame:
    """
    Vectorise en carrés uniquement les pixels du raster touchés par le réseau
    (masque de rasterisation dilaté), sans jamais vectoriser le raster entier.

    Étapes
    ------
    1. Reprojection des segments dans le CRS du raster (le raster n'est jamais
       rééchantillonné, ses valeurs restent intactes).
    2. Lecture d'une fenêtre du raster limitée à l'emprise du réseau (+ marge).
    3. Rasterisation des lignes sur la grille du raster (all_touched=True)
       -> masque booléen des pixels touchés.
    4. Dilatation du masque de `dilation_pixels` pixels : un carreau en trop
       ne coûte rien (longueur d'intersection nulle dans le 2_2), un carreau
       manquant biaiserait la moyenne pondérée.
    5. Construction vectorisée des carrés (shapely.box) pour ces pixels.

    Parameters
    ----------
    raster_path : str
        Chemin du GeoTIFF (grille régulière, nord en haut, CRS projeté).
    segments_gdf : GeoDataFrame
        Réseau (lignes). Le CRS doit être défini.
    value_column : str
        Nom de la colonne qui reçoit la valeur du pixel.
    band : int
        Bande à lire (1 par défaut).
    dilation_pixels : int
        Nombre de pixels de dilatation autour du réseau (0 = pas de dilatation).
    all_touched : bool
        Option de rasterio.features.rasterize : tout pixel touché par la ligne
        est retenu (recommandé).
    keep_nodata : bool
        Si False (défaut), les pixels NoData / non finis sont exclus.
        Si True, ils sont conservés avec une valeur NaN.
    verbose : bool
        Affiche un résumé (nombre de carreaux, NoData touchés, etc.).

    Returns
    -------
    GeoDataFrame dans le CRS du raster avec les colonnes
    [value_column, "raster_row", "raster_col", "geometry"].
    raster_row / raster_col sont les indices dans le raster complet
    (utiles pour le débogage et pour recouper avec QGIS).
    """
    if segments_gdf.crs is None:
        raise ValueError("segments_gdf doit avoir un CRS défini.")

    with rasterio.open(raster_path) as src:
        if src.crs is None or not src.crs.is_projected:
            raise ValueError("Le raster doit être dans un CRS projeté (mètres).")
        t_full = src.transform
        if t_full.b != 0 or t_full.d != 0:
            raise ValueError("Raster avec rotation non supporté (grille non alignée nord-sud).")

        # 1) Segments dans le CRS du raster
        seg = segments_gdf[["geometry"]]
        if seg.crs != src.crs:
            seg = seg.to_crs(src.crs)
        geoms = seg.geometry
        geoms = geoms[geoms.notna() & ~geoms.is_empty]
        if geoms.empty:
            raise ValueError("Aucune géométrie valide dans segments_gdf.")

        # 2) Fenêtre = emprise du réseau + marge (dilatation + 2 pixels de sécurité)
        pad = dilation_pixels + 2
        full = Window(0, 0, src.width, src.height)
        win = from_bounds(*geoms.total_bounds, transform=t_full)
        win = Window(
            int(np.floor(win.col_off)) - pad,
            int(np.floor(win.row_off)) - pad,
            int(np.ceil(win.width)) + 2 * pad + 1,
            int(np.ceil(win.height)) + 2 * pad + 1,
        )
        try:
            win = win.intersection(full)
        except Exception:
            raise ValueError("Le réseau ne recouvre pas l'emprise du raster.")
        win = Window(int(win.col_off), int(win.row_off), int(win.width), int(win.height))

        data = src.read(band, window=win)
        t_win = src.window_transform(win)
        nodata = src.nodata

    # 3) Rasterisation du réseau sur la grille de la fenêtre
    touched = rasterize(
        ((g, 1) for g in geoms.values),
        out_shape=data.shape,
        transform=t_win,
        fill=0,
        all_touched=all_touched,
        dtype="uint8",
    ).astype(bool)
    n_touched = int(touched.sum())

    # 4) Dilatation
    mask = _dilate_mask(touched, dilation_pixels) if dilation_pixels > 0 else touched

    # Pixels valides
    valid = np.isfinite(data)
    if nodata is not None and not np.isnan(nodata):
        valid &= data != nodata
    n_touched_nodata = int((touched & ~valid).sum())

    if not keep_nodata:
        mask = mask & valid

    rows, cols = np.nonzero(mask)
    values = data[rows, cols].astype("float64")
    if keep_nodata:
        values[~valid[rows, cols]] = np.nan

    # 5) Carrés vectorisés (coordonnées depuis la transform de la fenêtre)
    x_a = t_win.c + cols * t_win.a
    x_b = x_a + t_win.a
    y_a = t_win.f + rows * t_win.e
    y_b = y_a + t_win.e
    boxes = shapely.box(
        np.minimum(x_a, x_b), np.minimum(y_a, y_b),
        np.maximum(x_a, x_b), np.maximum(y_a, y_b),
    )

    gdf = gpd.GeoDataFrame(
        {
            value_column: values,
            "raster_row": rows + int(win.row_off),
            "raster_col": cols + int(win.col_off),
        },
        geometry=boxes,
        crs=src.crs,
    )

    if verbose:
        print(f"  Fenêtre lue : {data.shape[0]} x {data.shape[1]} pixels "
              f"(raster complet : {full.height} x {full.width})")
        print(f"  Pixels touchés par le réseau : {n_touched:,}")
        print(f"  Après dilatation ({dilation_pixels} px) : {int(mask.sum()):,} carreaux vectorisés")
        if n_touched_nodata:
            print(f"  ⚠️ {n_touched_nodata:,} pixels touchés par le réseau sont NoData "
                  f"({'conservés en NaN' if keep_nodata else 'exclus'})")

    return gdf






def extract_length_weighted_feature(
    segments_gdf: gpd.GeoDataFrame,
    cells_gdf: gpd.GeoDataFrame,
    feature_name: str,
    value_column: str,
    *,
    min_valid_share: float = 0.5,
    crs_meter_epsg: int | str | None = None,
    chunk_size: int = 100_000,
    verbose: bool = True,
) -> pd.DataFrame:
    """
    Moyenne de la valeur des carreaux traversés par chaque tronçon, pondérée
    par la longueur du tronçon dans chaque carreau :

        V = sum(v_i * l_i) / sum(l_i)

    Les carreaux sont des polygones (typiquement issus de
    raster_cells_touching_network, NoData déjà exclus). Pas de buffer :
    c'est la ligne du tronçon elle-même qui est intersectée.

    Gestion des zones sans donnée
    -----------------------------
    La longueur "valide" d'un tronçon est la longueur couverte par des
    carreaux portant une valeur. La moyenne est calculée sur cette seule
    longueur (renormalisation). Si la part valide (longueur valide / longueur
    du tronçon) est inférieure à `min_valid_share`, la valeur est NaN.
    Les NaN ne sont JAMAIS remplacés par 0 (0 = "aucun trafic" serait un biais).

    Tronçon posé exactement sur une limite de carreaux
    --------------------------------------------------
    Il intersecte les deux carreaux sur toute sa longueur : chacun compte
    une fois au numérateur et au dénominateur, ce qui revient à un partage
    50/50. La part valide est plafonnée à 1 pour ce cas.

    Parameters
    ----------
    segments_gdf : GeoDataFrame
        Doit contenir 'segment_id' et 'geometry' (lignes).
    cells_gdf : GeoDataFrame
        Carreaux (polygones) avec la colonne `value_column`.
    feature_name : str
        Nom de la colonne de sortie.
    value_column : str
        Colonne des valeurs des carreaux.
    min_valid_share : float
        Seuil de part de longueur valide en dessous duquel la valeur est NaN.
    crs_meter_epsg : int | str | None
        CRS métrique de travail. Si None, on travaille dans le CRS des carreaux
        (qui doit être projeté).
    chunk_size : int
        Nombre de tronçons traités par paquet (limite la mémoire).
    verbose : bool
        Affiche un résumé de la couverture.

    Returns
    -------
    DataFrame avec les colonnes
    ["segment_id", feature_name, f"{feature_name}_valid_share"].
    Une ligne par tronçon, NaN conservés.
    """
    if value_column not in cells_gdf.columns:
        raise ValueError(f"Colonne '{value_column}' absente des carreaux.")
    if not 0.0 <= min_valid_share <= 1.0:
        raise ValueError("min_valid_share doit être compris entre 0 et 1.")

    # --- CRS commun et métrique ------------------------------------------------
    target_crs = crs_meter_epsg if crs_meter_epsg is not None else cells_gdf.crs
    seg = segments_gdf[["segment_id", "geometry"]].reset_index(drop=True)
    cells = cells_gdf[[value_column, "geometry"]].reset_index(drop=True)
    if seg.crs != target_crs:
        seg = seg.to_crs(target_crs)
    if cells.crs != target_crs:
        cells = cells.to_crs(target_crs)
    if seg.crs is None or not seg.crs.is_projected:
        raise ValueError("Il faut un CRS projeté (mètres) : passer crs_meter_epsg.")

    # Carreaux sans valeur exploitable -> retirés (ils ne comptent pas comme valides)
    vals_all = pd.to_numeric(cells[value_column], errors="coerce").to_numpy(dtype="float64")
    keep = np.isfinite(vals_all)
    cells = cells.loc[keep].reset_index(drop=True)
    cell_vals = vals_all[keep]
    cell_geoms = cells.geometry.values
    sidx = cells.sindex

    seg_geoms = seg.geometry.values
    seg_len = shapely.length(seg_geoms)
    n = len(seg)
    weighted_sum = np.zeros(n, dtype="float64")
    valid_len = np.zeros(n, dtype="float64")

    # --- Intersections exactes tronçon x carreau, par paquets ------------------
    for start in range(0, n, chunk_size):
        stop = min(start + chunk_size, n)
        geoms_chunk = seg_geoms[start:stop]
        # paires (indice tronçon dans le paquet, indice carreau) qui s'intersectent
        i_seg, i_cell = sidx.query(geoms_chunk, predicate="intersects")
        if len(i_seg) == 0:
            continue
        pieces_len = shapely.length(shapely.intersection(geoms_chunk[i_seg], cell_geoms[i_cell]))
        np.add.at(valid_len, i_seg + start, pieces_len)
        np.add.at(weighted_sum, i_seg + start, pieces_len * cell_vals[i_cell])

    # --- Moyenne pondérée, part valide, seuil ----------------------------------
    with np.errstate(invalid="ignore", divide="ignore"):
        value = np.where(valid_len > 0, weighted_sum / valid_len, np.nan)
        valid_share = np.where(seg_len > 0, np.minimum(valid_len / seg_len, 1.0), np.nan)

    below = ~(valid_share >= min_valid_share)          # inclut les NaN (longueur nulle)
    value[below] = np.nan

    out = pd.DataFrame({
        "segment_id": seg["segment_id"].to_numpy(),
        feature_name: value,
        f"{feature_name}_valid_share": valid_share,
    })

    if verbose:
        full = np.sum(valid_share >= 0.999)
        none = np.sum(~(valid_share > 0))
        partial = n - full - none
        print(f"  Tronçons entièrement couverts : {full:,} | partiellement : {partial:,} | sans couverture : {none:,}")
        print(f"  Seuil part valide = {min_valid_share:.0%} -> {int(below.sum()):,} tronçons en NaN "
              f"({below.mean():.1%})")

    return out