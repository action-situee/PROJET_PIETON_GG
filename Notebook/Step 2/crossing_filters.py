# crossing_filters.py
"""
Chargement et filtrage des nœuds de traversée OSM (walk_crossing_nodes.parquet).

Partagé par :
- 2_1_Filter_features_walk  : produit les couches n_traversees / n_traversees_feux
- 1_1_Prepare_features      : cellule de contrôle (rectangles exportés pour QGIS)

Les règles de sélection (CROSSING_VALUES_KEPT, SIGNAL_RULES) sont définies ICI
et nulle part ailleurs, pour que le contrôle et la chaîne de production
retiennent exactement les mêmes traversées.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import geopandas as gpd

# Valeurs du tag `crossing` retenues. None = nœud highway=crossing sans tag crossing.
CROSSING_VALUES_KEPT = ["traffic_signals", "uncontrolled", "marked", "zebra", "unmarked", None]

# Une traversée est « à feux » si l'une de ces colonnes prend l'une de ces valeurs
# (les colonnes absentes du fichier sont ignorées).
SIGNAL_RULES = {
    "crossing": ["traffic_signals"],
}

_LISTLIKE = (list, tuple, set, np.ndarray)
_ID_COLS = ["osmid", "id", "element"]   # conservées si présentes (traçabilité QGIS)


def _first(v):
    """Valeur OSM éventuellement en liste -> première valeur ; NaN/None -> None."""
    if isinstance(v, _LISTLIKE):
        v = list(v)
        v = v[0] if len(v) else None
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    return str(v)


def load_crossings(path, crs) -> gpd.GeoDataFrame:
    """Charge les nœuds de traversée (GeoParquet, ou parquet avec colonnes x/y ou lon/lat)."""
    try:
        gdf = gpd.read_parquet(path)
    except Exception:
        df = pd.read_parquet(path)
        for xc, yc, src_crs in [("x", "y", crs), ("lon", "lat", "EPSG:4326"),
                                ("longitude", "latitude", "EPSG:4326")]:
            if {xc, yc} <= set(df.columns):
                gdf = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df[xc], df[yc]), crs=src_crs)
                break
        else:
            raise ValueError(f"Pas de géométrie reconnue dans {path} (colonnes : {list(df.columns)})")
    return gdf.to_crs(crs)


def filter_crossings(
    crossings: gpd.GeoDataFrame,
    values_kept=CROSSING_VALUES_KEPT,
    signal_rules=SIGNAL_RULES,
    *,
    drop: bool = True,
    verbose: bool = True,
) -> gpd.GeoDataFrame:
    """
    Sélectionne les traversées dont le tag `crossing` est dans `values_kept`
    et marque celles à feux (`is_signal`).

    drop=True  : ne renvoie que les traversées retenues (usage contrôle 1_1).
    drop=False : renvoie toutes les traversées avec la colonne booléenne
                 `crossing_kept` (usage 2_1 : le filtre est porté par `filtered`).

    Colonnes renvoyées : [ids OSM présents], crossing_tag, crossing_kept, is_signal, geometry
    """
    cr = crossings.copy()
    tag = cr["crossing"].map(_first) if "crossing" in cr.columns else pd.Series(None, index=cr.index)
    keep_none = any(v is None for v in values_kept)
    keep_vals = {v for v in values_kept if v is not None}
    kept = tag.isin(keep_vals) | (tag.isna() & keep_none)

    is_signal = pd.Series(False, index=cr.index)
    for col, vals in signal_rules.items():
        if col in cr.columns:
            is_signal |= cr[col].map(_first).isin(vals)

    cr["crossing_tag"] = tag
    cr["crossing_kept"] = kept
    cr["is_signal"] = is_signal

    if verbose:
        print("Valeurs du tag crossing (avant filtre) :")
        print(tag.value_counts(dropna=False).to_string())
        print(f"\nTraversées retenues : {int(kept.sum()):,} / {len(cr):,} "
              f"(dont à feux : {int((kept & is_signal).sum()):,})")

    cols = [c for c in _ID_COLS if c in cr.columns] + ["crossing_tag", "crossing_kept", "is_signal", "geometry"]
    out = cr[cols]
    if drop:
        out = out.loc[kept]
    return out
