# feature_rectangle.py
"""
Agrégation de lignes dans un rectangle autour de chaque segment, moyenne
pondérée par la longueur de chaque ligne à l'intérieur du rectangle.

Utilisé par 2_2 (boucle V3) pour how_<T> = "rectangle_weighted_mean",
par exemple la charge de trafic TIM (VOLVEHPRT(AP)) sur le réseau vélo.
Version catégorielle (extract_rectangle_majority_class) utilisée par 0_1 pour
lire le schéma cyclable d'agglomération sur les arêtes vélo.

Principe, pour un segment s :
  1. rectangle R(s) = buffer du segment à extrémités plates (cap_style="flat"),
     demi-largeur = buffer_size_<T>. Les extrémités restent celles du segment :
     une route qui part d'un carrefour au bout du segment n'est pas captée.
  2. on découpe les lignes de la couche dans R(s) : morceaux p_i, longueur L_i,
     valeur v_i (value_column).
  3. option : on écarte les morceaux trop obliques par rapport au segment
     (angle > max_angle_deg), pour qu'une route qui traverse le segment
     (chemin qui croise une route) ne lui donne pas sa charge.
  4. valeur = somme(L_i * v_i) / somme(L_i).
  5. part couverte = somme(L_i) / longueur du segment (diagnostic ; peut
     dépasser 1 si plusieurs lignes parallèles sont dans le rectangle).

Segments sans aucun morceau retenu, ou dont la part couverte est inférieure à
min_covered_share : valeur NaN (traitée à l'étape 3 via missing_value_strategy).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import geopandas as gpd
import shapely


def _endpoints(geoms):
    """Premier et dernier sommet de chaque géométrie linéaire (Multi incluses)."""
    coords, idx = shapely.get_coordinates(geoms, return_index=True)
    n = len(geoms)
    first = np.full((n, 2), np.nan)
    last = np.full((n, 2), np.nan)
    if len(idx):
        _, i_first = np.unique(idx, return_index=True)
        i_last = len(idx) - 1 - np.unique(idx[::-1], return_index=True)[1]
        g = idx[i_first]
        first[g] = coords[i_first]
        last[idx[i_last]] = coords[i_last]
    return first, last


def _unit_direction(geoms):
    a, b = _endpoints(geoms)
    d = b - a
    norm = np.hypot(d[:, 0], d[:, 1])
    with np.errstate(invalid="ignore", divide="ignore"):
        return d / norm[:, None]


def rectangle_pieces(seg_geom, line_geom, half_width, max_angle_deg=45.0):
    """
    Morceaux des lignes dans le rectangle (extrémités plates) de chaque segment.
    Retourne (i_seg, i_line, longueur, keep, n_obliques) : une entrée par paire
    segment-ligne qui se touchent ; keep = morceau de longueur > 0 et assez aligné.
    """
    rect = shapely.buffer(seg_geom, float(half_width), cap_style="flat", join_style="mitre")
    tree = shapely.STRtree(line_geom)
    i_seg, i_line = tree.query(rect, predicate="intersects")
    if len(i_seg) == 0:
        empty = np.array([], dtype=int)
        return empty, empty, np.array([]), np.array([], dtype=bool), 0
    pieces = shapely.intersection(rect[i_seg], line_geom[i_line])
    piece_len = shapely.length(pieces)
    keep = piece_len > 0
    n_oblique = 0
    if max_angle_deg is not None:
        u_seg = _unit_direction(seg_geom)[i_seg]
        u_piece = _unit_direction(pieces)
        cos = np.abs(np.sum(u_seg * u_piece, axis=1))          # orientation sans sens
        aligned = np.nan_to_num(cos, nan=0.0) >= np.cos(np.radians(max_angle_deg))
        n_oblique = int((keep & ~aligned).sum())
        keep &= aligned
    return i_seg, i_line, piece_len, keep, n_oblique


def extract_rectangle_weighted_mean(
    segments_gdf: gpd.GeoDataFrame,
    lines_gdf: gpd.GeoDataFrame,
    feature_name: str,
    value_column: str,
    half_width: float,
    *,
    max_angle_deg: float | None = 45.0,
    min_covered_share: float = 0.0,
    crs_meter_epsg="EPSG:2056",
    segment_id_col: str = "segment_id",
    verbose: bool = True,
) -> pd.DataFrame:
    """
    Retourne un DataFrame [segment_id, feature_name, f"{feature_name}_valid_share"],
    une ligne par segment (NaN si aucune ligne retenue).

    half_width        : demi-largeur du rectangle (m)
    max_angle_deg     : angle maximal entre le segment et un morceau de ligne
                        (None = pas de filtre d'orientation)
    min_covered_share : part couverte minimale ; en dessous -> NaN
    """
    if value_column is None:
        raise ValueError("rectangle_weighted_mean : value_column_<T> doit être renseigné dans le classeur")

    seg = segments_gdf.to_crs(crs_meter_epsg)[[segment_id_col, "geometry"]].reset_index(drop=True)
    lines = lines_gdf.to_crs(crs_meter_epsg)
    lines = lines[[value_column, "geometry"]].copy()
    lines[value_column] = pd.to_numeric(lines[value_column], errors="coerce")
    lines = lines[lines[value_column].notna() & lines.geometry.notna() & ~lines.geometry.is_empty]
    lines = lines.reset_index(drop=True)

    seg_geom = seg.geometry.values
    seg_len = shapely.length(seg_geom)

    out = pd.DataFrame({
        segment_id_col: seg[segment_id_col].values,
        feature_name: np.nan,
        f"{feature_name}_valid_share": 0.0,
    })
    i_seg, i_line, piece_len, keep, n_oblique = rectangle_pieces(
        seg_geom, lines.geometry.values, half_width, max_angle_deg)
    if len(i_seg) == 0:
        if verbose:
            print("  Aucune ligne dans les rectangles")
        return out

    w = piece_len[keep]
    v = lines[value_column].to_numpy(dtype="float64")[i_line[keep]]
    s = i_seg[keep]

    sum_w = np.bincount(s, weights=w, minlength=len(seg))
    sum_wv = np.bincount(s, weights=w * v, minlength=len(seg))
    with np.errstate(invalid="ignore", divide="ignore"):
        value = np.where(sum_w > 0, sum_wv / sum_w, np.nan)
        share = np.where(seg_len > 0, sum_w / seg_len, 0.0)

    too_low = (sum_w > 0) & (share < min_covered_share)
    value[too_low] = np.nan

    out[feature_name] = value
    out[f"{feature_name}_valid_share"] = share

    if verbose:
        n = len(seg)
        n_val = int(np.isfinite(value).sum())
        print(f"  Rectangle demi-largeur {half_width} m, extrémités plates | "
              f"morceaux retenus : {int(keep.sum()):,} (écartés car obliques : {n_oblique:,})")
        print(f"  Segments avec valeur : {n_val:,} / {n:,} ({100 * n_val / n:.1f} %) | "
              f"sous le seuil de part couverte : {int(too_low.sum()):,}")
    return out


def extract_rectangle_majority_class(
    segments_gdf: gpd.GeoDataFrame,
    lines_gdf: gpd.GeoDataFrame,
    class_column: str,
    half_width: float,
    *,
    max_angle_deg: float | None = 45.0,
    min_share: float = 0.5,
    crs_meter_epsg="EPSG:2056",
    segment_id_col: str = "segment_id",
    verbose: bool = True,
) -> pd.DataFrame:
    """
    Version catégorielle de extract_rectangle_weighted_mean (même rectangle, même
    filtre d'orientation) : pour chaque segment, la classe de `class_column` dont
    les lignes couvrent la plus grande longueur dans le rectangle.

    Retourne [segment_id, class_column, f"{class_column}_share"] : la classe est
    None si aucune ligne n'est retenue, ou si sa longueur couverte est inférieure
    à min_share × longueur du segment.
    """
    seg = segments_gdf.to_crs(crs_meter_epsg)[[segment_id_col, "geometry"]].reset_index(drop=True)
    lines = lines_gdf.to_crs(crs_meter_epsg)
    lines = lines[lines[class_column].notna() & lines.geometry.notna() & ~lines.geometry.is_empty]
    lines = lines[[class_column, "geometry"]].reset_index(drop=True)
    seg_len = shapely.length(seg.geometry.values)

    out = pd.DataFrame({segment_id_col: seg[segment_id_col].values,
                        class_column: None, f"{class_column}_share": 0.0})
    i_seg, i_line, piece_len, keep, n_oblique = rectangle_pieces(
        seg.geometry.values, lines.geometry.values, half_width, max_angle_deg)
    if not keep.any():
        if verbose:
            print("  Aucune ligne retenue dans les rectangles")
        return out

    pairs = pd.DataFrame({"seg": i_seg[keep],
                          "cls": lines[class_column].to_numpy()[i_line[keep]],
                          "len": piece_len[keep]})
    by_cls = pairs.groupby(["seg", "cls"], as_index=False)["len"].sum()
    best = by_cls.sort_values("len", ascending=False).drop_duplicates("seg")
    share = best["len"].to_numpy() / np.where(seg_len[best["seg"]] > 0, seg_len[best["seg"]], np.nan)
    ok = share >= min_share
    out.loc[best["seg"].to_numpy()[ok], class_column] = best["cls"].to_numpy()[ok]
    out.loc[best["seg"].to_numpy(), f"{class_column}_share"] = np.round(share, 3)

    if verbose:
        n = int(out[class_column].notna().sum())
        print(f"  Rectangle demi-largeur {half_width} m | morceaux retenus : {int(keep.sum()):,} "
              f"(obliques écartés : {n_oblique:,}) | segments classés : {n:,} / {len(out):,} "
              f"(part couverte >= {min_share:.0%})")
    return out
