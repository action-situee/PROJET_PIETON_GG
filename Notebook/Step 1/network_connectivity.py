import geopandas as gpd
import pandas as pd
import numpy as np
import networkx as nx
from shapely.geometry import Point, box


def add_uv_columns(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Ajoute les colonnes u, v, key à partir des extrémités de la géométrie.
    u = départ, v = arrivée, key = identifiant unique (ici segment_id).
    """
    gdf = gdf.copy()
    gdf["u"] = gdf.geometry.apply(lambda g: hash(g.coords[0]))
    gdf["v"] = gdf.geometry.apply(lambda g: hash(g.coords[-1]))
    gdf["key"] = gdf["segment_id"]
    return gdf


def compute_connectivity_metrics(
    segmented_net: gpd.GeoDataFrame,
    buffer_m: int = 50,
    compute_betweenness: bool = False,
    betweenness_k: int | None = None,
    crs_meter_epsg: int | None = None,
    main_metrics_only: bool = False,
    conn_index_metric: str = "conn_branching_in_buffer",
) -> gpd.GeoDataFrame:
    """
    Calcule des métriques de connectivité locale par segment et un
    indice de connectivité conn_index_score basé sur les alternatives
    cheminatoires (conn_branching_in_buffer), avec impasses forcées à 0.

    Métriques calculées (par segment) :
      - conn_deadend_flag          : 1 si cul-de-sac (au moins un nœud de degré 1)
      - conn_intersection_flag     : 1 si au moins un nœud de degré ≥ 3
      - conn_nodes_in_buffer       : nombre de nœuds dans le buffer (50 m)
      - conn_intersections_in_buffer : nombre de nœuds de degré ≥ 3 dans le buffer
      - conn_branching_in_buffer   : somme des max(degree - 2, 0) dans le buffer
      - conn_betweenness (optionnel, moyenne des 2 nœuds)
      - conn_index_score           : indice synthétique basé sur conn_branching_in_buffer
    """

    # conserver les colonnes d'origine pour main_metrics_only
    original_cols = list(segmented_net.columns)

    gdf = segmented_net.copy()

    # 1. Assurer un CRS métrique
    if crs_meter_epsg is not None and (gdf.crs is None or not gdf.crs.is_projected):
        gdf = gdf.to_crs(crs_meter_epsg)

    # 2. Longueur en mètres si manquante
    if "length_m" not in gdf.columns:
        gdf["length_m"] = gdf.geometry.length

    # 3. Graphe simple pour degrés et betweenness
    G = nx.Graph()
    for r in gdf.itertuples(index=False):
        G.add_edge(
            getattr(r, "u"),
            getattr(r, "v"),
            segment_id=getattr(r, "segment_id"),
            weight=getattr(r, "length_m"),
        )

    # 4. Degré des nœuds
    node_degree = dict(G.degree())

    # 5. Table des nœuds avec géométrie
    node_rows = []
    for r in gdf.itertuples(index=False):
        geom = getattr(r, "geometry")
        x0, y0 = geom.coords[0]
        x1, y1 = geom.coords[-1]
        node_rows.append({"node": getattr(r, "u"), "geometry": Point(x0, y0)})
        node_rows.append({"node": getattr(r, "v"), "geometry": Point(x1, y1)})

    nodes_gdf = gpd.GeoDataFrame(node_rows, geometry="geometry", crs=gdf.crs)
    nodes_gdf = nodes_gdf.drop_duplicates(subset="node", keep="first").reset_index(drop=True)
    nodes_gdf["degree"] = nodes_gdf["node"].map(node_degree).fillna(0).astype(int)

    n_sindex = nodes_gdf.sindex
    e_sindex = gdf.sindex

    # 6. Betweenness des nœuds (optionnelle)
    node_bet = None
    if compute_betweenness:
        node_bet = nx.betweenness_centrality(
            G,
            k=betweenness_k,
            weight="weight",
            normalized=True,
            endpoints=False,
            seed=42,
        )

    # 7. Calcul des métriques locales par segment
    out = {
        "segment_id": [],
        "conn_deadend_flag": [],
        "conn_intersection_flag": [],
        "conn_nodes_in_buffer": [],
        "conn_intersections_in_buffer": [],
        "conn_branching_in_buffer": [],
    }

    for r in gdf.itertuples(index=False):
        seg_id = getattr(r, "segment_id")
        u, v = getattr(r, "u"), getattr(r, "v")

        deg_u = node_degree.get(u, 0)
        deg_v = node_degree.get(v, 0)

        deadend_flag = (deg_u == 1) or (deg_v == 1)
        intersection_flag = (deg_u >= 3) or (deg_v >= 3)

        buf = getattr(r, "geometry").buffer(buffer_m)
        minx, miny, maxx, maxy = buf.bounds
        query_geom = box(minx, miny, maxx, maxy)

        # Nœuds dans le buffer
        cand_nodes_idx = list(n_sindex.query(query_geom, predicate="intersects"))
        nodes_in_buf = nodes_gdf.iloc[cand_nodes_idx]
        nodes_in_buf = nodes_in_buf[nodes_in_buf.geometry.intersects(buf)]

        nb_nodes = len(nodes_in_buf)
        nb_intersections = int((nodes_in_buf["degree"] >= 3).sum())
        branching = int(((nodes_in_buf["degree"] - 2).clip(lower=0)).sum())

        out["segment_id"].append(seg_id)
        out["conn_deadend_flag"].append(bool(deadend_flag))
        out["conn_intersection_flag"].append(bool(intersection_flag))
        out["conn_nodes_in_buffer"].append(int(nb_nodes))
        out["conn_intersections_in_buffer"].append(int(nb_intersections))
        out["conn_branching_in_buffer"].append(int(branching))

    metrics = pd.DataFrame(out)
    gdf = gdf.merge(metrics, on="segment_id", how="left")

    # 8. Betweenness reportée au segment (si calculée)
    if compute_betweenness and node_bet is not None:
        bet_vals = []
        for r in gdf.itertuples(index=False):
            u, v = getattr(r, "u"), getattr(r, "v")
            b = 0.5 * (node_bet.get(u, 0.0) + node_bet.get(v, 0.0))
            bet_vals.append(b)
        gdf["conn_betweenness"] = bet_vals

    # 9. Normalisation + shift de conn_index_metric en place

    def _minmax(series: pd.Series) -> pd.Series:
        s = series.astype(float)
        smin = s.min()
        smax = s.max()
        if pd.isna(smin) or pd.isna(smax) or smax == smin:
            return pd.Series(0.0, index=s.index)
        return (s - smin) / (smax - smin)

    def _shift(x: pd.Series, min_shift: float = 0.1) -> pd.Series:
        # Transforme x_norm ∈ [0,1] en [min_shift, 1]
        return min_shift + (1.0 - min_shift) * x

    # normalisation puis shift directement dans la même colonne
    gdf[conn_index_metric] = _minmax(gdf[conn_index_metric])
    gdf[conn_index_metric] = _shift(gdf[conn_index_metric])

    # 10. Indice synthétique = conn_branching_in_buffer ajusté, impasses = 0
    gdf["conn_index_score"] = gdf[conn_index_metric]
    gdf.loc[gdf["conn_deadend_flag"] == True, conn_index_metric] = 0.0

    # 11. Si main_metrics_only, on ne renvoie que les colonnes d'origine + l'indice
    if main_metrics_only:
        return gdf[original_cols + ["conn_index_score"]]

    return gdf