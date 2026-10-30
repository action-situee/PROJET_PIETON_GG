"""
Fonctions utilitaires du notebook « largeur_trottoir_step1 ».

Organisation :
    1. Lecture / préparation des couches
    2. Partie 1 — rectangles et couverture du sol
    3. Partie 2 — transects et changements de couverture
    4. Partie 3 — vérité terrain (domaine routier) et comparaison
    5. Diagnostics et exports

Conventions des transects :
    - gauche / droite relatives au sens de digitalisation du segment ;
    - colonnes cx, cy (centre) et nx, ny (normale gauche unitaire) ;
    - t > 0 = gauche, t < 0 = droite.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import geopandas as gpd
import shapely
import pyogrio
import matplotlib.pyplot as plt

try:
    from IPython.display import display
except ImportError:  # hors notebook
    display = print


# =====================================================================================
# 1. Lecture / préparation
# =====================================================================================

def lire_couche(path, layer=None):
    path = Path(path)
    if path.suffix.lower() == ".parquet":
        return gpd.read_parquet(path)
    return gpd.read_file(path, layer=layer)


def _nettoyer_geometries(gdf, crs):
    """Supprime vides, retire Z/M, reprojette, répare seulement les invalides."""
    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()
    gdf["geometry"] = shapely.force_2d(gdf.geometry.values)
    gdf = gdf.to_crs(crs).reset_index(drop=True)
    inv = ~shapely.is_valid(gdf.geometry.values)
    if inv.any():
        gdf.loc[inv, "geometry"] = shapely.make_valid(gdf.geometry.values[inv])
    return gdf, int(inv.sum())


def _lire_emprise(path, emprise, layer=None, columns=None):
    """Lecture limitée à l'emprise (GeoDataFrame) ; gère gpkg/shp et parquet."""
    path = Path(path)
    if path.suffix.lower() == ".parquet":
        g = gpd.read_parquet(path, columns=(columns + ["geometry"]) if columns else None)
        x0, y0, x1, y1 = emprise.to_crs(g.crs).total_bounds
        return g.cx[x0:x1, y0:y1], None
    info = pyogrio.read_info(path, layer=layer)
    bbox = tuple(emprise.to_crs(info["crs"]).total_bounds)
    g = gpd.read_file(path, layer=layer, columns=columns, bbox=bbox, use_arrow=True)
    return g, info


def charger_segments(path, layer, crs, echantillon=None, seed=0):
    seg = lire_couche(path, layer).to_crs(crs)
    if echantillon is not None and echantillon < len(seg):
        seg = seg.sample(echantillon, random_state=seed)
    seg["seg_len_m"] = seg.length
    print(f"{len(seg):,} segments, CRS = {seg.crs.to_string()}")
    return seg


# =====================================================================================
# 2. Partie 1 — rectangles et couverture du sol
# =====================================================================================

def repartition_highway(seg, liste_a, scores_directs):
    repart = (seg.groupby("highway", dropna=False)
                 .agg(n_segments=("segment_id", "size"), longueur_km=("seg_len_m", lambda s: s.sum() / 1000))
                 .sort_values("n_segments", ascending=False))

    def liste_de(hw):
        if hw in liste_a:
            return "A (géométrie)"
        if hw in scores_directs:
            return "B (score direct)"
        return "non assigné"

    repart["liste"] = [liste_de(h) for h in repart.index]
    doublons = set(liste_a) & set(scores_directs)
    assert not doublons, f"Ces types sont dans les deux listes : {doublons}"
    non_assignes = repart.index[repart["liste"] == "non assigné"].tolist()
    if non_assignes:
        print("⚠ Types highway dans aucune liste (ignorés) :", non_assignes)
    return repart


def plot_repartition_highway(repart):
    couleurs = {"A (géométrie)": "tab:blue", "B (score direct)": "tab:orange", "non assigné": "tab:gray"}
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))
    for ax, col, titre in zip(axes, ["n_segments", "longueur_km"], ["Nombre de segments", "Longueur totale (km)"]):
        ax.bar(repart.index.astype(str), repart[col], color=[couleurs[l] for l in repart["liste"]])
        ax.set_title(titre)
        ax.tick_params(axis="x", rotation=45)
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in couleurs.values()]
    axes[1].legend(handles, couleurs.keys())
    plt.tight_layout()
    plt.show()


def separer_listes(seg, liste_a, scores_directs):
    seg_A = seg[seg["highway"].isin(liste_a)].copy()
    seg_B = seg[seg["highway"].isin(scores_directs.keys())].copy()
    seg_B["score_largeur"] = seg_B["highway"].map(scores_directs)
    print(f"Liste A (géométrie)   : {len(seg_A):,} segments")
    print(f"Liste B (score direct): {len(seg_B):,} segments "
          f"(dont {seg_B['score_largeur'].isna().sum():,} sans score encore défini)")
    return seg_A, seg_B


def construire_rectangles(gdf, largeur, methode="buffer_plat"):
    """Rectangle (ou bande à bouts plats) de longueur = segment et de largeur totale `largeur`."""
    demi = largeur / 2.0
    geoms = gdf.geometry.values
    if methode == "buffer_plat":
        polys = shapely.buffer(geoms, demi, cap_style="flat", join_style="mitre", mitre_limit=2.0)
    elif methode == "rectangle":
        p0 = shapely.get_coordinates(shapely.get_point(geoms, 0))
        p1 = shapely.get_coordinates(shapely.get_point(geoms, -1))
        d = p1 - p0
        n = np.hypot(d[:, 0], d[:, 1])
        n[n == 0] = np.nan
        u = d / n[:, None]
        v = np.column_stack([-u[:, 1], u[:, 0]]) * demi
        coins = np.stack([p0 + v, p1 + v, p1 - v, p0 - v, p0 + v], axis=1)
        polys = shapely.polygons(coins)
        polys[np.isnan(n)] = None
    else:
        raise ValueError(f"methode inconnue : {methode}")

    out = gpd.GeoDataFrame(gdf.drop(columns="geometry").copy(), geometry=polys, crs=gdf.crs)
    out = out[out.geometry.notna() & ~out.geometry.is_empty]
    out["rect_area_m2"] = out.area
    print(f"{len(out):,} rectangles, surface médiane = {out['rect_area_m2'].median():.1f} m²")
    return out


def plot_rectangles_zone(seg_A, rect_A, methode, largeur, rayon=150):
    zone = seg_A.geometry.iloc[0].centroid.buffer(rayon)
    ax = rect_A[rect_A.intersects(zone)].plot(figsize=(7, 7), alpha=0.4, edgecolor="k")
    seg_A[seg_A.intersects(zone)].plot(ax=ax, color="red", linewidth=1)
    ax.set_title(f"Rectangles ({methode}, largeur {largeur} m)")
    ax.set_aspect("equal")
    plt.show()


def charger_couverture(path, layer, attr, emprise, crs):
    """Couverture du sol limitée aux polygones proches de `emprise` (rectangles)."""
    veg, info = _lire_emprise(path, emprise, layer=layer, columns=[attr])
    if info is not None:
        print(f"Couche complète : {info['features']:,} entités ({info['geometry_type']})")
    assert attr in veg.columns, f"Attribut '{attr}' absent. Colonnes : {list(veg.columns)}"
    veg = veg[veg.geometry.notna() & ~veg.geometry.is_empty]
    veg["geometry"] = shapely.force_2d(veg.geometry.values)
    veg = veg.to_crs(crs)
    _, idx = veg.sindex.query(emprise.geometry.values)
    veg = veg.iloc[np.unique(idx)].reset_index(drop=True)
    inv = ~shapely.is_valid(veg.geometry.values)
    if inv.any():
        veg.loc[inv, "geometry"] = shapely.make_valid(veg.geometry.values[inv])
    veg[attr] = veg[attr].astype(str)
    print(f"{inv.sum():,} géométries invalides réparées | {len(veg):,} polygones retenus, "
          f"{veg[attr].nunique()} catégories")
    return veg


def intersection_par_categorie(gdf, veg, attr, mesure, id_col="segment_id"):
    """Format long id | catégorie | mesure ; mesure = "length" (lignes) ou "area" (polygones)."""
    veg = veg.reset_index(drop=True)
    gauche = gdf[[id_col, "geometry"]].reset_index(drop=True)
    paires = gpd.sjoin(gauche, veg[[attr, "geometry"]], how="inner", predicate="intersects")
    g_geom = gauche.geometry.values[paires.index.values]
    v_geom = veg.geometry.values[veg.index.get_indexer(paires["index_right"])]
    inter = shapely.intersection(g_geom, v_geom)
    val = shapely.length(inter) if mesure == "length" else shapely.area(inter)
    res = pd.DataFrame({id_col: paires[id_col].values, attr: paires[attr].values, mesure: val})
    res = res[res[mesure] > 0]
    return res.groupby([id_col, attr], as_index=False)[mesure].sum()


def categorie_dominante(seg_A, veg, attr):
    """Ajoute veg_dominante / part_dominante à seg_A ; renvoie (seg_A, longueurs par catégorie)."""
    long_seg = intersection_par_categorie(seg_A, veg, attr, "length")
    couvert = long_seg.groupby("segment_id")["length"].sum()
    reste = seg_A.set_index("segment_id")["seg_len_m"].sub(couvert, fill_value=0).clip(lower=0)
    reste = reste[reste > 0.01]
    hors = pd.DataFrame({"segment_id": reste.index, attr: "hors_couverture", "length": reste.values})
    long_seg = pd.concat([long_seg, hors], ignore_index=True)

    idx = long_seg.groupby("segment_id")["length"].idxmax()
    dom = long_seg.loc[idx, ["segment_id", attr]].rename(columns={attr: "veg_dominante"})
    seg_len = seg_A.set_index("segment_id")["seg_len_m"]
    dom["part_dominante"] = long_seg.loc[idx, "length"].values / seg_len.loc[dom["segment_id"]].values
    seg_A = seg_A.drop(columns=["veg_dominante", "part_dominante"], errors="ignore").merge(
        dom, on="segment_id", how="left")
    return seg_A, long_seg


def plot_analyse_couverture(seg_A, long_seg, attr):
    """Histogrammes par catégorie dominante / longueur, ventilation par highway, pureté des segments."""
    hist_n = seg_A["veg_dominante"].value_counts()
    hist_km = long_seg.groupby(attr)["length"].sum().div(1000).sort_values(ascending=False)

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    axes[0].bar(hist_n.index, hist_n.values)
    axes[0].set_title("Segments (liste A) par catégorie dominante")
    axes[0].set_ylabel("Nombre de segments")
    axes[1].bar(hist_km.index, hist_km.values, color="tab:green")
    axes[1].set_title("Longueur de segments par catégorie")
    axes[1].set_ylabel("km")
    for ax in axes:
        ax.tick_params(axis="x", rotation=60)
    plt.tight_layout()
    plt.show()
    display(pd.DataFrame({"n_segments_dominante": hist_n, "longueur_km": hist_km.round(2),
                          "part_longueur_%": (100 * hist_km / hist_km.sum()).round(1)}).fillna(0))

    lg = long_seg.merge(seg_A[["segment_id", "highway"]], on="segment_id")
    tab = lg.pivot_table(index="highway", columns=attr, values="length", aggfunc="sum", fill_value=0)
    tab_pct = 100 * tab.div(tab.sum(axis=1), axis=0)
    ax = tab_pct.plot.barh(stacked=True, figsize=(12, 5), colormap="tab20")
    ax.set_xlabel("% de la longueur")
    ax.set_title("Couverture du sol traversée, par type highway")
    ax.legend(bbox_to_anchor=(1.01, 1), loc="upper left", fontsize=8)
    plt.tight_layout()
    plt.show()
    display(tab_pct.round(1))

    ax = seg_A["part_dominante"].plot.hist(bins=40, figsize=(7, 3.5))
    ax.set_xlabel("part de la longueur dans la catégorie dominante")
    ax.set_title("Segments 'mixtes' vs 'purs'")
    plt.show()
    print(f"{(seg_A['part_dominante'] < 0.6).mean():.1%} des segments ont moins de 60 % dans leur catégorie dominante")


def surfaces_par_rectangle(rect_A, veg, attr):
    """Ajoute m2_<cat> et pct_<cat> (+ hors_couverture) à chaque rectangle."""
    surf = intersection_par_categorie(rect_A, veg, attr, "area")
    large = surf.pivot_table(index="segment_id", columns=attr, values="area", fill_value=0)
    large.columns = [f"m2_{c}" for c in large.columns]
    rect_A = rect_A.drop(columns=[c for c in rect_A.columns if c.startswith(("m2_", "pct_"))], errors="ignore")
    rect_A = rect_A.merge(large, left_on="segment_id", right_index=True, how="left")
    cols = [c for c in rect_A.columns if c.startswith("m2_")]
    rect_A[cols] = rect_A[cols].fillna(0)
    rect_A["m2_hors_couverture"] = (rect_A["rect_area_m2"] - rect_A[cols].sum(axis=1)).clip(lower=0)
    for c in cols + ["m2_hors_couverture"]:
        rect_A["pct_" + c[3:]] = 100 * rect_A[c] / rect_A["rect_area_m2"]
    return rect_A


def exporter_partie1(out_dir, rect_A, seg_A, seg_B, long_seg, methode, largeur):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    suffixe = f"{methode}_{largeur:g}m"
    rect_A.to_file(out_dir / f"rectangles_{suffixe}.gpkg", layer="rectangles", driver="GPKG")
    seg_A.to_file(out_dir / f"segments_A_{suffixe}.gpkg", layer="segments_A", driver="GPKG")
    seg_B.to_file(out_dir / "segments_B_scores_directs.gpkg", layer="segments_B", driver="GPKG")
    long_seg.to_csv(out_dir / f"segments_longueur_par_categorie_{suffixe}.csv", index=False)
    print("Exports dans", out_dir.resolve())


# =====================================================================================
# 3. Partie 2 — transects
# =====================================================================================

def eclater_polygones(geoms):
    """Décompose Multi*/GeometryCollection jusqu'aux Polygon ; renvoie (polygones, index d'origine)."""
    idx = np.arange(len(geoms))
    while True:
        tid = shapely.get_type_id(geoms)
        if not np.isin(tid, [4, 5, 6, 7]).any():
            break
        parts, i = shapely.get_parts(geoms, return_index=True)
        geoms, idx = parts, idx[i]
    garder = shapely.get_type_id(geoms) == 3
    return geoms[garder], idx[garder]


def extraire_aretes(gdf, attr, eps, verbose=True):
    """Arêtes élémentaires des contours ; supprime celles partagées par deux polygones de même catégorie."""
    codes, noms = pd.factorize(gdf[attr])
    polys, i_g = eclater_polygones(gdf.geometry.values)
    anneaux, i_poly = shapely.get_rings(polys, return_index=True)
    coords, i_ann = shapely.get_coordinates(anneaux, return_index=True)

    meme = i_ann[1:] == i_ann[:-1]
    p1, p2 = coords[:-1][meme], coords[1:][meme]
    cat = codes[i_g[i_poly[i_ann[:-1][meme]]]]
    nn = np.any(p1 != p2, axis=1)
    p1, p2, cat = p1[nn], p2[nn], cat[nn]
    n_brut = len(p1)

    q1 = np.round(p1 / eps).astype(np.int64)
    q2 = np.round(p2 / eps).astype(np.int64)
    inv = (q1[:, 0] > q2[:, 0]) | ((q1[:, 0] == q2[:, 0]) & (q1[:, 1] > q2[:, 1]))
    a = np.where(inv[:, None], q2, q1)
    b = np.where(inv[:, None], q1, q2)
    df = pd.DataFrame({"ax": a[:, 0], "ay": a[:, 1], "bx": b[:, 0], "by": b[:, 1], "cat": cat})
    grp = df.groupby(["ax", "ay", "bx", "by"], sort=False)
    g = grp.ngroup().to_numpy()
    n = grp["cat"].transform("size").to_numpy()
    cmin = grp["cat"].transform("min").to_numpy()
    cmax = grp["cat"].transform("max").to_numpy()
    meme_nature = (n >= 2) & (cmin == cmax)
    premier = ~pd.Series(g).duplicated().to_numpy()
    garder = ~meme_nature & premier
    if verbose:
        print(f"{n_brut:,} arêtes brutes | {meme_nature.sum():,} supprimées (même nature des deux côtés) | "
              f"{(~meme_nature & ~premier).sum():,} doublons fusionnés | {garder.sum():,} arêtes conservées")
    return p1[garder], p2[garder], noms


def preparer_couverture(veg, attr, eps):
    """Structures pour les transects sur la couverture du sol (arêtes, index, codes de catégorie)."""
    E1, E2, noms = extraire_aretes(veg, attr, eps)
    return {
        "E1": E1, "E2": E2, "noms": noms,
        "arbre_aretes": shapely.STRtree(shapely.linestrings(np.stack([E1, E2], axis=1))),
        "arbre_poly": shapely.STRtree(veg.geometry.values),
        "codes": pd.Categorical(veg[attr], categories=noms).codes,
    }


def construire_transects(seg, n, d_max, long_min, pas):
    """n transects par segment, à k/(n+1) de la longueur, normale calculée sur la tangente locale."""
    s = seg[seg["seg_len_m"] >= long_min]
    geoms = s.geometry.values
    L = s["seg_len_m"].to_numpy()
    G, LL = np.repeat(geoms, n), np.repeat(L, n)
    K = np.tile(np.arange(n), len(s))
    pos = (K + 1) / (n + 1) * LL
    h = np.minimum(pas, LL / 4)

    c = shapely.get_coordinates(shapely.line_interpolate_point(G, pos))
    a = shapely.get_coordinates(shapely.line_interpolate_point(G, pos - h))
    b = shapely.get_coordinates(shapely.line_interpolate_point(G, pos + h))
    u = b - a
    norme = np.hypot(u[:, 0], u[:, 1])
    ok = norme > 0
    u = u / np.where(ok, norme, 1)[:, None]
    nl = np.column_stack([-u[:, 1], u[:, 0]])

    tr = pd.DataFrame({
        "segment_id": np.repeat(s["segment_id"].to_numpy(), n), "k": K,
        "cx": c[:, 0], "cy": c[:, 1], "nx": nl[:, 0], "ny": nl[:, 1],
    })[ok].reset_index(drop=True)
    print(f"{len(tr):,} transects sur {len(s):,} segments "
          f"({(seg['seg_len_m'] < long_min).sum():,} segments trop courts ignorés)")
    return tr


def _croisements(C, N, d_max, E1, E2, arbre):
    """Croisements transects × arêtes : DataFrame (i, cote, d) avec cote = +1 gauche / −1 droite."""
    A, B = C - d_max * N, C + d_max * N
    i_t, i_e = arbre.query(shapely.linestrings(np.stack([A, B], axis=1)))
    P, r = A[i_t], B[i_t] - A[i_t]
    Q, q = E1[i_e], E2[i_e] - E1[i_e]
    den = r[:, 0] * q[:, 1] - r[:, 1] * q[:, 0]
    QP = Q - P
    ok = np.abs(den) > 1e-12
    den = np.where(ok, den, 1)
    s = (QP[:, 0] * q[:, 1] - QP[:, 1] * q[:, 0]) / den
    w = (QP[:, 0] * r[:, 1] - QP[:, 1] * r[:, 0]) / den
    ok &= (s >= 0) & (s <= 1) & (w >= 0) & (w <= 1)
    t = (s[ok] - 0.5) * 2 * d_max
    return pd.DataFrame({"i": i_t[ok], "cote": np.where(t > 0, 1, -1), "d": np.abs(t)})


def _code_aux_points(x, y, couv):
    pts = shapely.points(x, y)
    i_pt, i_v = couv["arbre_poly"].query(pts, predicate="intersects")
    out = np.full(len(pts), -1, dtype=np.int64)
    premier = ~pd.Series(i_pt).duplicated().to_numpy()
    out[i_pt[premier]] = couv["codes"][i_v[premier]]
    return out


def _bloc_changements(b, d_max, seuil, couv):
    n = len(b)
    C, N = b[["cx", "cy"]].to_numpy(), b[["nx", "ny"]].to_numpy()
    x = _croisements(C, N, d_max, couv["E1"], couv["E2"], couv["arbre_aretes"])
    x = x[x["d"] > seuil].sort_values(["i", "cote", "d"], kind="stable").drop_duplicates(["i", "cote", "d"])

    demi = pd.DataFrame({"i": np.repeat(np.arange(n), 2), "cote": np.tile([1, -1], n)})
    d0 = max(seuil, 0.01)
    ii, sg = demi["i"].to_numpy(), demi["cote"].to_numpy()
    demi["cat0"] = _code_aux_points(C[ii, 0] + sg * d0 * N[ii, 0], C[ii, 1] + sg * d0 * N[ii, 1], couv)
    cat_axe = _code_aux_points(C[:, 0], C[:, 1], couv)

    d_suiv = x.groupby(["i", "cote"])["d"].shift(-1).fillna(d_max).to_numpy()
    dm = (x["d"].to_numpy() + d_suiv) / 2
    ii, sg = x["i"].to_numpy(), x["cote"].to_numpy()
    x["cat"] = _code_aux_points(C[ii, 0] + sg * dm * N[ii, 0], C[ii, 1] + sg * dm * N[ii, 1], couv)

    x = x.merge(demi, on=["i", "cote"], how="left")
    prec = x.groupby(["i", "cote"])["cat"].shift(1).fillna(x["cat0"]).astype(np.int64)
    x = x[x["cat"].to_numpy() != prec.to_numpy()]
    x["rang"] = x.groupby(["i", "cote"]).cumcount() + 1

    n_chg = x.groupby(["i", "cote"]).size().rename("n_chg")
    c1 = x[x["rang"] == 1].set_index(["i", "cote"])[["d", "cat"]].rename(columns={"d": "d1", "cat": "cat1"})
    c2 = x[x["rang"] == 2].set_index(["i", "cote"])[["d", "cat"]].rename(columns={"d": "d2", "cat": "cat2"})
    demi = demi.set_index(["i", "cote"]).join([c1, c2, n_chg]).reset_index()
    demi["n_chg"] = demi["n_chg"].fillna(0).astype(int)

    larg = demi.pivot(index="i", columns="cote", values=["cat0", "d1", "cat1", "d2", "cat2", "n_chg"])
    larg.columns = [f"{v}_{'l' if c == 1 else 'r'}" for v, c in larg.columns]
    out = b.reset_index(drop=True).join(larg.reindex(np.arange(n)))
    out["cat_axe"] = cat_axe
    return out


def _nommer(codes, noms):
    tab = np.append(np.asarray(noms, dtype=object), "hors_couverture")   # code -1 → dernier
    codes = pd.Series(codes)
    out = pd.Series(np.nan, index=codes.index, dtype=object)
    m = codes.notna()
    out[m] = tab[codes[m].astype(int).to_numpy()]
    return out.to_numpy()


def calculer_changements(tr, couv, d_max, seuil, taille_bloc, seg_A):
    """1er et 2e changements de couverture sur chaque demi-transect → DataFrame `res`."""
    res = pd.concat([_bloc_changements(tr.iloc[i:i + taille_bloc], d_max, seuil, couv)
                     for i in range(0, len(tr), taille_bloc)], ignore_index=True)
    for c in ["cat_axe", "cat0_l", "cat0_r", "cat1_l", "cat1_r", "cat2_l", "cat2_r"]:
        res[c] = _nommer(res[c], couv["noms"])
    for c in ["d1_l", "d1_r", "d2_l", "d2_r"]:
        res[c] = res[c].astype(float)
    res = res.rename(columns={"d1_l": "d_l", "d1_r": "d_r"})
    res = res.merge(seg_A[["segment_id", "highway", "veg_dominante"]], on="segment_id", how="left")
    print(f"{len(res):,} transects traités")
    return res


def geom_transects(r, d_max):
    C, N = r[["cx", "cy"]].to_numpy(), r[["nx", "ny"]].to_numpy()
    return shapely.linestrings(np.stack([C - d_max * N, C + d_max * N], axis=1))


def points_changement(r, col_d, signe):
    rr = r[r[col_d].notna()]
    d = rr[col_d].astype(float)
    return shapely.points(rr["cx"] + signe * d * rr["nx"], rr["cy"] + signe * d * rr["ny"])


def plot_transects_zone(res, veg, seg_A, attr, d_max, seuil, rayon=60):
    centre = shapely.Point(res["cx"].iloc[len(res) // 2], res["cy"].iloc[len(res) // 2])
    zone = centre.buffer(rayon)
    sel = res[shapely.intersects(shapely.points(res["cx"], res["cy"]), zone)]
    fig, ax = plt.subplots(figsize=(9, 9))
    veg[veg.intersects(zone)].clip(zone).plot(
        ax=ax, column=attr, categorical=True, legend=True, alpha=0.5, edgecolor="grey", linewidth=0.3,
        legend_kwds={"bbox_to_anchor": (1.01, 1), "loc": "upper left"})
    seg_A[seg_A.intersects(zone)].clip(zone).plot(ax=ax, color="k", linewidth=1.5)
    gpd.GeoSeries(geom_transects(sel, d_max)).plot(ax=ax, color="tab:blue", linewidth=0.7)
    for col, sg in [("d_l", 1), ("d_r", -1)]:
        gpd.GeoSeries(points_changement(sel, col, sg)).plot(ax=ax, color="red", markersize=12)
    for col, sg in [("d2_l", 1), ("d2_r", -1)]:
        gpd.GeoSeries(points_changement(sel, col, sg)).plot(ax=ax, color="darkred", marker="x", markersize=20)
    ax.set_aspect("equal")
    ax.set_title(f"Transects (D_MAX = {d_max} m, SEUIL_1 = {seuil} m)")
    plt.show()


def resume(s):
    return pd.Series({"n": s.size, "% NaN": 100 * s.isna().mean(), "moyenne": s.mean(),
                      "médiane": s.median(), "q25": s.quantile(0.25), "q75": s.quantile(0.75)})


def stats_d_par_nature(res, categories, seuil, d_max):
    """Tableau et histogrammes de d_l / d_r par nature du segment (veg_dominante)."""
    lignes = []
    for cat in categories:
        sub = res[res["veg_dominante"] == cat]
        for col in ["d_l", "d_r"]:
            lignes.append(resume(sub[col]).rename((cat, col)))
        lignes.append(pd.Series({"n": sub["segment_id"].nunique()}).rename((cat, "n_segments")))
    display(pd.DataFrame(lignes).round(2))

    bins = np.linspace(seuil, d_max, 40)
    fig, axes = plt.subplots(1, len(categories), figsize=(5 * len(categories), 4), sharex=True, squeeze=False)
    for ax, cat in zip(axes[0], categories):
        sub = res[res["veg_dominante"] == cat]
        ax.hist(sub["d_l"].dropna(), bins=bins, alpha=0.6, label="d_l (gauche)")
        ax.hist(sub["d_r"].dropna(), bins=bins, alpha=0.6, label="d_r (droite)")
        ax.set_title(f"{cat} — {sub['segment_id'].nunique():,} segments")
        ax.set_xlabel("distance au 1er changement (m)")
        ax.legend()
    axes[0][0].set_ylabel("demi-transects")
    plt.tight_layout()
    plt.show()

    long1 = pd.concat([res[["veg_dominante", f"cat1_{s}"]].rename(columns={f"cat1_{s}": "cat1"})
                       for s in ["l", "r"]], ignore_index=True)
    long1 = long1[long1["veg_dominante"].isin(categories) & long1["cat1"].notna()]
    print("Couverture rencontrée après le 1er changement (% des demi-transects avec changement)")
    display((100 * pd.crosstab(long1["veg_dominante"], long1["cat1"], normalize="index")).round(1))


def analyse_route(res, cat_route, d_max):
    """Segments de nature `cat_route` : 2e changement (d2 − d1), disponibilité et séquences de couverture."""
    route = res[res["veg_dominante"] == cat_route].copy()
    if route.empty:
        print(f"⚠ aucun segment de nature '{cat_route}'")
        return None
    route["delta_l"] = route["d2_l"] - route["d_l"]
    route["delta_r"] = route["d2_r"] - route["d_r"]

    par_seg = route.groupby("segment_id").agg(a_2e_l=("d2_l", lambda s: s.notna().any()),
                                              a_2e_r=("d2_r", lambda s: s.notna().any()))
    par_seg["au_moins_un"] = par_seg["a_2e_l"] | par_seg["a_2e_r"]
    par_seg["deux_cotes"] = par_seg["a_2e_l"] & par_seg["a_2e_r"]
    display(pd.Series({
        "segments": len(par_seg),
        "≥ 1 demi-transect avec 2e changement": par_seg["au_moins_un"].sum(),
        "  en %": 100 * par_seg["au_moins_un"].mean(),
        "2e changement des deux côtés": par_seg["deux_cotes"].sum(),
        "  en % ": 100 * par_seg["deux_cotes"].mean(),
        "% de demi-transects avec 2e changement": 100 * pd.concat([route["d2_l"], route["d2_r"]]).notna().mean(),
    }).round(1).to_frame("valeur"))
    deltas = pd.concat([route["delta_l"], route["delta_r"]]).dropna()
    display(resume(deltas).round(2).to_frame("d2 − d1 (m)"))

    fig, ax = plt.subplots(figsize=(7, 4))
    for col, lab in [("delta_l", "gauche"), ("delta_r", "droite")]:
        ax.hist(route[col].dropna(), bins=np.linspace(0, d_max, 40), alpha=0.6, label=lab)
    ax.set_xlabel("d2 − d1 (m)")
    ax.set_ylabel("demi-transects")
    ax.set_title(f"Segments en {cat_route} : écart entre 1er et 2e changement")
    ax.legend()
    plt.show()

    seq = pd.concat([route[[f"cat0_{s}", f"cat1_{s}", f"cat2_{s}", f"delta_{s}"]]
                     .set_axis(["cat0", "cat1", "cat2", "delta"], axis=1) for s in ["l", "r"]],
                    ignore_index=True).dropna(subset=["cat2"])
    seq_stats = (seq.groupby(["cat0", "cat1", "cat2"]).agg(n=("delta", "size"), delta_median_m=("delta", "median"))
                    .sort_values("n", ascending=False))
    seq_stats["%"] = 100 * seq_stats["n"] / seq_stats["n"].sum()
    display(seq_stats.head(15).round(2))
    return route


def exporter_transects(res, out_dir, d_max, seuil, crs):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    nom = out_dir / f"transects_D{d_max:g}m_seuil{seuil:g}m.gpkg"
    gpd.GeoDataFrame(res, geometry=geom_transects(res, d_max), crs=crs).to_file(nom, layer="transects", driver="GPKG")
    pts = []
    for col, sg, cote, rang in [("d_l", 1, "l", 1), ("d_r", -1, "r", 1), ("d2_l", 1, "l", 2), ("d2_r", -1, "r", 2)]:
        m = res[col].notna()
        pts.append(gpd.GeoDataFrame({"segment_id": res.loc[m, "segment_id"].values, "k": res.loc[m, "k"].values,
                                     "cote": cote, "rang": rang, "d": res.loc[m, col].values},
                                    geometry=points_changement(res, col, sg), crs=crs))
    gpd.GeoDataFrame(pd.concat(pts, ignore_index=True), crs=crs).to_file(nom, layer="changements", driver="GPKG")
    print("Exporté :", nom.resolve())


# =====================================================================================
# 4. Partie 3 — vérité terrain et comparaison
# =====================================================================================

def charger_domaine_routier(path, emprise, crs):
    dr, _ = _lire_emprise(path, emprise, columns=["OBJET", "REVETEMENT", "NIVEAU"])
    dr, _ = _nettoyer_geometries(dr, crs)
    display(dr["OBJET"].value_counts().to_frame("n polygones (emprise)"))
    return dr


def extraire_couches_gt(dr, couches, niveaux=None):
    """{nom: [valeurs OBJET]} → {nom: GeoDataFrame} (colonne `couche` = nom)."""
    out = {}
    for nom, objets in couches.items():
        c = dr[dr["OBJET"].isin(objets)]
        if niveaux is not None:
            c = c[c["NIVEAU"].isin(niveaux)]
        c = c.copy().reset_index(drop=True)
        inv = ~shapely.is_valid(c.geometry.values)
        if inv.any():
            c.loc[inv, "geometry"] = shapely.make_valid(c.geometry.values[inv])
        c["couche"] = nom
        out[nom] = c
        print(f"{nom:>10} : {len(c):,} polygones ({inv.sum()} réparés), surface {c.area.sum() / 1e4:,.1f} ha")
    return out


def apparier_rectangles(rect_A, seg_A, dr, couches_gt):
    """Ajoute couvert_GT et m2_<couche>_GT aux rectangles ; renvoie (rect_A, segments couverts, tableau)."""
    i_r, _ = dr.sindex.query(rect_A.geometry.values, predicate="intersects")
    seg_couverts = set(rect_A["segment_id"].to_numpy()[np.unique(i_r)])
    rect_A = rect_A.copy()
    rect_A["couvert_GT"] = rect_A["segment_id"].isin(seg_couverts)
    for nom, c in couches_gt.items():
        s = intersection_par_categorie(rect_A, c, "couche", "area")
        rect_A[f"m2_{nom}_GT"] = rect_A["segment_id"].map(s.set_index("segment_id")["area"]).fillna(0)

    cov = rect_A[rect_A["couvert_GT"]].drop(columns="veg_dominante", errors="ignore").merge(
        seg_A[["segment_id", "veg_dominante"]], on="segment_id")
    print(f"Segments liste A dans la zone couverte (GE) : {len(cov):,} / {len(rect_A):,}")
    tab = cov.groupby("veg_dominante").agg(n_segments=("segment_id", "size"))
    for nom in couches_gt:
        tab[f"part avec {nom}"] = cov.assign(x=cov[f"m2_{nom}_GT"] > 0).groupby("veg_dominante")["x"].mean()
    return rect_A, seg_couverts, tab.sort_values("n_segments", ascending=False).round(3)


def preparer_couche_gt(c, eps):
    E1, E2, _ = extraire_aretes(c, "couche", eps)
    return {"E1": E1, "E2": E2,
            "arbre_aretes": shapely.STRtree(shapely.linestrings(np.stack([E1, E2], axis=1))),
            "arbre_poly": shapely.STRtree(c.geometry.values)}


def _dans_couche(x, y, couche):
    i_pt, _ = couche["arbre_poly"].query(shapely.points(x, y), predicate="intersects")
    out = np.zeros(len(x), dtype=bool)
    out[i_pt] = True
    return out


def _bloc_gt(b, d_max, couche):
    n = len(b)
    C, N = b[["cx", "cy"]].to_numpy(), b[["nx", "ny"]].to_numpy()
    x = _croisements(C, N, d_max, couche["E1"], couche["E2"], couche["arbre_aretes"])
    x = x[x["d"] > 1e-6]
    demi = pd.DataFrame({"i": np.repeat(np.arange(n), 2), "cote": np.tile([1, -1], n), "d": 0.0})

    iv = (pd.concat([demi, x], ignore_index=True).sort_values(["i", "cote", "d"], kind="stable")
            .drop_duplicates(["i", "cote", "d"]).reset_index(drop=True))
    iv["fin"] = iv.groupby(["i", "cote"])["d"].shift(-1).fillna(d_max)
    dm = (iv["d"].to_numpy() + iv["fin"].to_numpy()) / 2
    ii, sg = iv["i"].to_numpy(), iv["cote"].to_numpy()
    iv["dedans"] = _dans_couche(C[ii, 0] + sg * dm * N[ii, 0], C[ii, 1] + sg * dm * N[ii, 1], couche)

    nouveau = ((iv["dedans"] != iv["dedans"].shift()) | (iv["i"] != iv["i"].shift())
               | (iv["cote"] != iv["cote"].shift()))
    iv["run"] = nouveau.cumsum()
    runs = iv.groupby("run").agg(i=("i", "first"), cote=("cote", "first"),
                                 a=("d", "min"), b=("fin", "max"), dedans=("dedans", "first"))
    sur = runs[runs["dedans"]]
    n_poly = sur.groupby(["i", "cote"]).size().rename("n_polys")
    premier = sur.groupby(["i", "cote"])[["a", "b"]].first()

    demi = demi[["i", "cote"]].set_index(["i", "cote"]).join([premier, n_poly]).reset_index()
    demi["w"] = demi["b"] - demi["a"]
    demi["b_tronque"] = demi["b"] >= d_max - 1e-6
    demi["n_polys"] = demi["n_polys"].fillna(0).astype(int)
    larg = demi.pivot(index="i", columns="cote", values=["a", "b", "w", "b_tronque", "n_polys"])
    larg.columns = [f"GT_{v}_{'l' if c == 1 else 'r'}" for v, c in larg.columns]
    return b[["segment_id", "k"]].reset_index(drop=True).join(larg.reindex(np.arange(n)))


def calculer_gt(tr_couv, couche, d_max, taille_bloc):
    """a, b, w (1er polygone de la couche rencontré) pour chaque demi-transect."""
    g = pd.concat([_bloc_gt(tr_couv.iloc[i:i + taille_bloc], d_max, couche)
                   for i in range(0, len(tr_couv), taille_bloc)], ignore_index=True)
    for c in ["GT_a_l", "GT_a_r", "GT_b_l", "GT_b_r", "GT_w_l", "GT_w_r"]:
        g[c] = g[c].astype(float)
    for c in ["GT_b_tronque_l", "GT_b_tronque_r"]:
        g[c] = g[c].astype("boolean")
    return g


def plot_hist_gt(gt_par_couche, d_max):
    bins = np.linspace(0, d_max, 41)
    for nom, g in gt_par_couche.items():
        a_all = pd.concat([g["GT_a_l"], g["GT_a_r"]], ignore_index=True)
        b_all = pd.concat([g["GT_b_l"], g["GT_b_r"]], ignore_index=True)
        w_all = pd.concat([g["GT_w_l"], g["GT_w_r"]], ignore_index=True)
        tronq = pd.concat([g["GT_b_tronque_l"], g["GT_b_tronque_r"]], ignore_index=True)
        print(f"[{nom}] demi-transects qui rencontrent la couche : {w_all.notna().mean():.1%} "
              f"| dont tronqués par D_MAX : {tronq[w_all.notna()].mean():.1%}")
        display(pd.DataFrame({"a (bord intérieur)": resume(a_all), "b (bord extérieur)": resume(b_all),
                              "w (largeur)": resume(w_all)}).round(2))
        fig, axes = plt.subplots(1, 3, figsize=(16, 3.8))
        for ax, (lab, v) in zip(axes, [("a : axe → bord intérieur", a_all), ("b : axe → bord extérieur", b_all),
                                      ("w = b − a : largeur traversée", w_all)]):
            ax.hist(v.dropna(), bins=bins, color="tab:purple")
            ax.set_title(f"{nom} — {lab}")
            ax.set_xlabel("m")
        axes[0].set_ylabel("demi-transects")
        plt.tight_layout()
        plt.show()


def table_comparaison(res, g, seg_A, exclure_tronques=True):
    """Joint proxy et GT par transect ; colonnes P_d1_*, P_delta_*, G_a_*, G_b_*, G_w_*."""
    comp = res[["segment_id", "k", "veg_dominante", "d_l", "d_r", "d2_l", "d2_r"]].merge(g, on=["segment_id", "k"])
    comp["highway"] = comp["segment_id"].map(seg_A.set_index("segment_id")["highway"])
    for s in ["l", "r"]:
        comp[f"P_d1_{s}"] = comp[f"d_{s}"]
        comp[f"P_delta_{s}"] = comp[f"d2_{s}"] - comp[f"d_{s}"]
        tronque = comp[f"GT_b_tronque_{s}"].fillna(False).astype(bool) if exclure_tronques else False
        comp[f"G_a_{s}"] = comp[f"GT_a_{s}"]
        for v in ["b", "w"]:
            comp[f"G_{v}_{s}"] = comp[f"GT_{v}_{s}"].mask(tronque)
    return comp


def calc_regle(comp, cat, p, g, mode, hw=None, seuil_asym=0.5, remplacement="2min", agreg="median"):
    """Comparaison par segment pour une règle ; renvoie un DataFrame (une ligne par segment) ou None.

    mode "somme"      : par transect P_l + P_r ↔ G_l + G_r (les deux côtés requis des deux bords)
    mode "somme_asym" : idem, mais si |P_l − P_r| / (P_l + P_r) > seuil_asym, le proxy devient
                        2 × min(P_l, P_r) (remplacement="2min") ou (P_l + P_r) / 2 (remplacement="moyenne")
    mode "moyenne"    : moyenne de tous les côtés disponibles, proxy et GT séparément
    """
    sub = comp[comp["veg_dominante"] == cat]
    if hw is not None:
        sub = sub[sub["highway"].isin(hw)]
    if sub.empty:
        return None

    if mode in ("somme", "somme_asym"):
        Pl, Pr = sub[f"P_{p}_l"], sub[f"P_{p}_r"]
        P = (Pl + Pr)
        asym = ((Pl - Pr).abs() / P).where(P > 0)
        if mode == "somme_asym":
            est_asym = asym > seuil_asym
            remp = 1.9 * np.minimum(Pl, Pr) if remplacement == "2min" else P / 2
            P = P.where(~est_asym, remp)
        else:
            est_asym = pd.Series(False, index=sub.index)
        G = sub[f"G_{g}_l"] + sub[f"G_{g}_r"]
        ok = P.notna() & G.notna()
        long = pd.DataFrame({
            "segment_id": sub["segment_id"].to_numpy(),
            "proxy": P.where(ok).to_numpy(), "gt": G.where(ok).to_numpy(),
            "proxy_dispo": P.notna().to_numpy(), "gt_dispo": G.notna().to_numpy(),
            "asym": asym.where(ok).to_numpy(), "est_asym": est_asym.where(ok).astype(float).to_numpy(),
        })
        libelle = f"{p}_l+{p}_r ↔ {g}_l+{g}_r"
        if mode == "somme_asym":
            libelle += f" ({'2·min' if remplacement == '2min' else 'moy.'} si asym>{seuil_asym:g})"
    elif mode == "moyenne":
        P = np.concatenate([sub[f"P_{p}_l"], sub[f"P_{p}_r"]])
        G = np.concatenate([sub[f"G_{g}_l"], sub[f"G_{g}_r"]])
        long = pd.DataFrame({
            "segment_id": np.concatenate([sub["segment_id"], sub["segment_id"]]),
            "proxy": P, "gt": G, "proxy_dispo": ~np.isnan(P), "gt_dispo": ~np.isnan(G),
            "asym": np.nan, "est_asym": np.nan,
        })
        libelle = f"moy({p}) ↔ moy({g})"
    else:
        raise ValueError(f"mode inconnu : {mode}")
    if hw is not None:
        libelle += f" [{','.join(hw)}]"

    agg = long.groupby("segment_id").agg(
        proxy_seg=("proxy", agreg), gt_seg=("gt", agreg),
        n_proxy=("proxy_dispo", "sum"), n_gt=("gt_dispo", "sum"),
        n_transects_compares=("proxy", "count"),
        asym_med=("asym", "median"), part_transects_asym=("est_asym", "mean"),
    ).reset_index()
    agg["regle"] = libelle
    return ajouter_erreurs(agg)


def ajouter_erreurs(d):
    d = d.copy()
    d["ecart_rel"] = (d["proxy_seg"] - d["gt_seg"]) / d["gt_seg"]
    d.loc[d["gt_seg"] <= 0, "ecart_rel"] = np.nan
    d["err_abs_m"] = d["proxy_seg"] - d["gt_seg"]
    ok = (d["proxy_seg"] > 0) & (d["gt_seg"] > 0)
    d["log2_ratio"] = np.where(ok, np.log2(d["proxy_seg"] / d["gt_seg"]), np.nan)
    return d


def _deballer_regle(regle):
    cat, p, g, mode, nom_c, *reste = regle
    return cat, p, g, mode, nom_c, (reste[0] if reste else None)


def comparer(regles, comp_par_couche, seuil_asym, remplacement, agreg):
    """Applique toutes les règles → cmp_seg (une ligne par segment et par règle)."""
    morceaux = []
    for regle in regles:
        cat, p, g, mode, nom_c, hw = _deballer_regle(regle)
        if nom_c not in comp_par_couche:
            print(f"⚠ couche GT inconnue : '{nom_c}'")
            continue
        agg = calc_regle(comp_par_couche[nom_c], cat, p, g, mode, hw, seuil_asym, remplacement, agreg)
        if agg is None:
            print(f"⚠ aucun segment couvert pour la règle {regle}")
            continue
        agg["nature"], agg["couche_GT"], agg["mode"] = cat, nom_c, mode
        morceaux.append(agg)
    return pd.concat(morceaux, ignore_index=True)


CLES = ["nature", "couche_GT", "regle"]


def bilan_disponibilite(cmp_seg):
    c = cmp_seg
    dispo = c.groupby(CLES).agg(n_segments=("segment_id", "size"),
                                proxy_dispo=("n_proxy", lambda s: (s > 0).sum()),
                                gt_dispo=("n_gt", lambda s: (s > 0).sum()),
                                compares=("ecart_rel", "count"))
    dispo["proxy sans GT"] = c[(c["n_proxy"] > 0) & (c["n_gt"] == 0)].groupby(CLES).size()
    dispo["GT sans proxy"] = c[(c["n_proxy"] == 0) & (c["n_gt"] > 0)].groupby(CLES).size()
    dispo["les deux, sans transect commun"] = c[(c["n_proxy"] > 0) & (c["n_gt"] > 0)
                                                & c["ecart_rel"].isna()].groupby(CLES).size()
    return dispo.fillna(0).astype(int)


def stats_erreurs(d):
    e, l = d["err_abs_m"].dropna(), d["log2_ratio"].dropna()
    pair = d[["proxy_seg", "gt_seg"]].dropna()
    return pd.Series({
        "n": e.size,
        "écart rel. médian": d["ecart_rel"].median(),
        "biais médian (m)": e.median(),
        "|erreur| médiane (m)": e.abs().median(),
        "|erreur| q90 (m)": e.abs().quantile(0.9),
        "% |err| ≤ 0.5 m": 100 * (e.abs() <= 0.5).mean(),
        "% |err| ≤ 1 m": 100 * (e.abs() <= 1.0).mean(),
        "facteur médian proxy/GT": 2 ** l.median() if len(l) else np.nan,
        "% dans facteur 1.25": 100 * (l.abs() <= np.log2(1.25)).mean(),
        "% dans facteur 1.5": 100 * (l.abs() <= np.log2(1.5)).mean(),
        "Spearman": pair.corr(method="spearman").iloc[0, 1] if len(pair) > 5 else np.nan,
        "% transects asym.": 100 * d["part_transects_asym"].mean() if "part_transects_asym" in d else np.nan,
    })


def stats_par_regle(cmp_seg, par=None):
    cles = CLES + ([par] if par else [])
    d = cmp_seg[cmp_seg["ecart_rel"].notna()]
    return d.groupby(cles)[[c for c in d.columns if c not in cles]].apply(stats_erreurs)


def _regles_presentes(cmp_seg):
    return cmp_seg[CLES + ["mode"]].drop_duplicates().to_numpy().tolist()


def _sous_ensemble(cmp_seg, cat, nom_c, libelle):
    return cmp_seg[(cmp_seg["nature"] == cat) & (cmp_seg["couche_GT"] == nom_c)
                   & (cmp_seg["regle"] == libelle) & cmp_seg["ecart_rel"].notna()]


def plot_ecarts_relatifs(cmp_seg, d_max, borne=2.0):
    regles = _regles_presentes(cmp_seg)
    bins = np.linspace(-1, borne, 61)
    fig, axes = plt.subplots(2, len(regles), figsize=(5.5 * len(regles), 9), squeeze=False)
    for j, (cat, nom_c, libelle, mode) in enumerate(regles):
        sub = _sous_ensemble(cmp_seg, cat, nom_c, libelle)
        e = sub["ecart_rel"]
        ax = axes[0][j]
        ax.hist(e.clip(upper=bins[-1]), bins=bins, color="tab:red")
        ax.axvline(0, color="k", linewidth=1)
        if len(e):
            ax.axvline(e.median(), color="k", linestyle="--", linewidth=1, label=f"médiane = {e.median():+.2f}")
            ax.legend()
        ax.set_title(f"{cat} vs GT {nom_c} — {len(sub):,} segments\n{libelle}", fontsize=10)
        ax.set_xlabel(f"écart relatif (proxy − GT) / GT\n[{(e > bins[-1]).sum()} valeurs > {bins[-1]:g} à droite]")

        m = max(d_max * (2 if mode in ("somme", "somme_asym") else 1), 1)
        ax = axes[1][j]
        ax.scatter(sub["gt_seg"], sub["proxy_seg"], s=4, alpha=0.3)
        ax.plot([0, m], [0, m], "k--", linewidth=1)
        ax.set_xlim(0, m)
        ax.set_ylim(0, m)
        ax.set_xlabel(f"vérité terrain {nom_c} (m)")
        ax.set_ylabel("proxy (m)")
        ax.set_aspect("equal")
    axes[0][0].set_ylabel("segments")
    plt.tight_layout()
    plt.show()


def plot_erreurs(cmp_seg):
    """Erreur absolue, log2 du rapport, et erreur selon la taille de la GT — une colonne par règle."""
    regles = _regles_presentes(cmp_seg)
    bins_abs, bins_log = np.linspace(-5, 5, 51), np.linspace(-3, 3, 49)
    ticks = [-3, -2, -1, 0, 1, 2, 3]
    fig, axes = plt.subplots(3, len(regles), figsize=(5.5 * len(regles), 12), squeeze=False)
    for j, (cat, nom_c, libelle, _) in enumerate(regles):
        sub = _sous_ensemble(cmp_seg, cat, nom_c, libelle)
        e = sub["err_abs_m"].dropna()
        ax = axes[0][j]
        ax.hist(e.clip(bins_abs[0], bins_abs[-1]), bins=bins_abs, color="tab:blue")
        ax.axvline(0, color="k", linewidth=1)
        if len(e):
            ax.axvline(e.median(), color="k", linestyle="--", linewidth=1, label=f"médiane = {e.median():+.2f} m")
            ax.legend()
        ax.set_title(f"{cat} vs GT {nom_c} — {len(sub):,} segments\n{libelle}", fontsize=10)
        ax.set_xlabel("erreur absolue proxy − GT (m)  [bornée à ±5]")

        l = sub["log2_ratio"].dropna()
        ax = axes[1][j]
        ax.hist(l.clip(bins_log[0], bins_log[-1]), bins=bins_log, color="tab:green")
        ax.axvline(0, color="k", linewidth=1)
        ax.axvspan(-np.log2(1.25), np.log2(1.25), color="grey", alpha=0.15, label="facteur 1.25")
        if len(l):
            ax.axvline(l.median(), color="k", linestyle="--", linewidth=1, label=f"facteur médian = ×{2 ** l.median():.2f}")
        ax.set_xticks(ticks)
        ax.set_xticklabels([f"×{2 ** t:g}" if t >= 0 else f"÷{2 ** -t:g}" for t in ticks])
        ax.set_xlabel("rapport proxy / GT (échelle log2)  [borné à ÷8 / ×8]")
        ax.legend()

        ax = axes[2][j]
        ax.scatter(sub["gt_seg"], sub["err_abs_m"], s=4, alpha=0.3)
        ax.axhline(0, color="k", linewidth=1)
        if len(sub) > 10:
            classes = pd.qcut(sub["gt_seg"], q=min(10, sub["gt_seg"].nunique()), duplicates="drop")
            prof = sub.groupby(classes, observed=True).agg(
                x=("gt_seg", "median"), med=("err_abs_m", "median"),
                q25=("err_abs_m", lambda s: s.quantile(0.25)), q75=("err_abs_m", lambda s: s.quantile(0.75)))
            ax.plot(prof["x"], prof["med"], "r-o", markersize=3, label="médiane par décile de GT")
            ax.fill_between(prof["x"], prof["q25"], prof["q75"], color="red", alpha=0.15, label="q25–q75")
            ax.legend()
        ax.set_xlabel(f"vérité terrain {nom_c} (m)")
        ax.set_ylabel("erreur absolue (m)")
    axes[0][0].set_ylabel("segments")
    axes[1][0].set_ylabel("segments")
    plt.tight_layout()
    plt.show()


def balayage_asym(regles, comp_par_couche, seuils, remplacement, agreg):
    """Refait les règles en mode somme_asym pour plusieurs seuils ; renvoie le tableau des stats."""
    lignes = []
    for regle in regles:
        cat, p, g, mode, nom_c, hw = _deballer_regle(regle)
        if mode != "somme_asym" or nom_c not in comp_par_couche:
            continue
        for s in seuils:
            a = calc_regle(comp_par_couche[nom_c], cat, p, g, mode, hw, s, remplacement, agreg)
            if a is None:
                continue
            st = stats_erreurs(a[a["ecart_rel"].notna()])
            st["nature"], st["highway"], st["SEUIL_ASYM"] = cat, ",".join(hw) if hw else "tous", s
            lignes.append(st)
    if not lignes:
        print("Aucune règle en mode 'somme_asym'.")
        return None
    return pd.DataFrame(lignes).set_index(["nature", "highway", "SEUIL_ASYM"])


def plot_balayage_asym(balayage, regles, comp_par_couche, seuil_actuel):
    fig, axes = plt.subplots(1, 3, figsize=(16, 4))
    for (nat, hw), b in balayage.groupby(level=[0, 1]):
        x = b.index.get_level_values("SEUIL_ASYM")
        lab = f"{nat} [{hw}]"
        axes[0].plot(x, b["|erreur| médiane (m)"], "o-", label=lab)
        axes[1].plot(x, b["% dans facteur 1.25"], "o-", label=lab)
        axes[2].plot(x, b["biais médian (m)"], "o-", label=lab)
    axes[2].axhline(0, color="k", linewidth=1)
    for ax, t in zip(axes, ["|erreur| médiane (m)", "% de segments dans un facteur 1.25", "biais médian (m)"]):
        ax.set_xlabel("SEUIL_ASYM  (0 = toujours remplacé, 1 = toujours somme)")
        ax.set_title(t)
    axes[0].legend()
    plt.tight_layout()
    plt.show()

    for regle in regles:
        cat, p, g, mode, nom_c, hw = _deballer_regle(regle)
        if mode != "somme_asym" or nom_c not in comp_par_couche:
            continue
        sub = comp_par_couche[nom_c]
        sub = sub[sub["veg_dominante"] == cat]
        if hw is not None:
            sub = sub[sub["highway"].isin(hw)]
        A = ((sub[f"P_{p}_l"] - sub[f"P_{p}_r"]).abs() / (sub[f"P_{p}_l"] + sub[f"P_{p}_r"])).dropna()
        plt.figure(figsize=(6, 3.5))
        plt.hist(A, bins=np.linspace(0, 1, 41), color="tab:gray")
        plt.axvline(seuil_actuel, color="r", linestyle="--", label=f"SEUIL_ASYM = {seuil_actuel}")
        plt.xlabel("asymétrie |d_l − d_r| / (d_l + d_r)")
        plt.ylabel("transects")
        plt.title(f"{cat} [{','.join(hw) if hw else 'tous'}]")
        plt.legend()
        plt.show()


# =====================================================================================
# 5. Diagnostics et exports
# =====================================================================================

def position_axe(gt_t, tol_axe=0.1):
    """Par segment : axe sur le trottoir GT, hors trottoir, mixte, ou pas de trottoir GT."""
    pos = gt_t[["segment_id", "GT_a_l", "GT_a_r"]].copy()
    pos["sur"] = ((pos["GT_a_l"] < tol_axe).astype(float) + (pos["GT_a_r"] < tol_axe).astype(float)) / 2
    pos["avec"] = (pos["GT_a_l"].notna().astype(float) + pos["GT_a_r"].notna().astype(float)) / 2
    p = pos.groupby("segment_id")[["sur", "avec"]].mean()
    p["position_axe"] = np.select([p["avec"] == 0, p["sur"] >= 0.5, p["sur"] == 0],
                                  ["pas de trottoir GT", "axe sur le trottoir", "axe hors trottoir (chaussée…)"],
                                  default="mixte")
    return p[["position_axe"]]


def diagnostic_highway(cmp_seg, seg_A, pos_seg):
    diag = (cmp_seg.drop(columns=["highway", "position_axe"], errors="ignore")
                   .merge(seg_A[["segment_id", "highway"]], on="segment_id", how="left")
                   .merge(pos_seg, left_on="segment_id", right_index=True, how="left"))
    diag["position_axe"] = diag["position_axe"].fillna("pas de trottoir GT")
    diag = diag[diag["ecart_rel"].notna()]
    print("Par type highway")
    display(stats_par_regle(diag, "highway").query("n >= 5").round(2))
    print("Par position de l'axe (trottoir GT)")
    display(stats_par_regle(diag, "position_axe").query("n >= 5").round(2))
    print("Croisement highway × position de l'axe (nombre de segments comparés)")
    display(pd.crosstab([diag[c] for c in CLES + ["highway"]], diag["position_axe"]))
    return diag


def plot_boxplot_highway(diag):
    regles = diag[CLES].drop_duplicates().to_numpy().tolist()
    fig, axes = plt.subplots(1, len(regles), figsize=(6 * len(regles), 4.5), squeeze=False)
    for ax, r in zip(axes[0], regles):
        sub = diag[(diag[CLES] == r).all(axis=1)]
        groupes = sub.groupby("highway")["log2_ratio"]
        noms = [h for h, s in groupes if s.notna().sum() >= 5]
        if not noms:
            ax.set_visible(False)
            continue
        ax.boxplot([groupes.get_group(h).dropna() for h in noms], showfliers=False)
        ax.set_xticks(range(1, len(noms) + 1))
        ax.set_xticklabels([f"{h}\n(n={groupes.get_group(h).notna().sum()})" for h in noms], rotation=45, ha="right")
        ax.axhline(0, color="k", linewidth=1)
        ax.axhspan(-np.log2(1.25), np.log2(1.25), color="grey", alpha=0.15)
        ax.set_yticks([-2, -1, 0, 1, 2])
        ax.set_yticklabels(["÷4", "÷2", "×1", "×2", "×4"])
        ax.set_title(" | ".join(map(str, r)), fontsize=9)
        ax.set_ylabel("rapport proxy / GT")
    plt.tight_layout()
    plt.show()


ORDRE_POSITION_D1 = [
    "avant le trottoir (sur la chaussée)", "≈ bord intérieur du trottoir", "au milieu du trottoir",
    "≈ bord extérieur du trottoir", "au-delà du trottoir", "trottoir tronqué par D_MAX (indéterminé)",
    "changement sans trottoir GT", "pas de changement (trottoir GT présent)", "ni changement ni trottoir",
]


def position_d1(res, gt_t, nature, tol_bord=0.5):
    """Demi-transects d'une nature : position du 1er changement par rapport au trottoir GT."""
    cc = res[["segment_id", "k", "veg_dominante", "highway", "d_l", "d_r"]].merge(gt_t, on=["segment_id", "k"])
    cc = cc[cc["veg_dominante"] == nature]
    cotes = pd.concat([
        pd.DataFrame({"segment_id": cc["segment_id"], "highway": cc["highway"], "cote": s,
                      "d1": cc[f"d_{s}"], "a": cc[f"GT_a_{s}"], "b": cc[f"GT_b_{s}"],
                      "tronque": cc[f"GT_b_tronque_{s}"].fillna(False).astype(bool)})
        for s in ["l", "r"]], ignore_index=True)
    d1, a, b = cotes["d1"], cotes["a"], cotes["b"]
    cotes["position_d1"] = np.select(
        [d1.isna() & a.isna(), d1.isna(), a.isna(), d1 < a - tol_bord, (d1 - a).abs() <= tol_bord,
         cotes["tronque"], (d1 - b).abs() <= tol_bord, d1 < b],
        ["ni changement ni trottoir", "pas de changement (trottoir GT présent)", "changement sans trottoir GT",
         "avant le trottoir (sur la chaussée)", "≈ bord intérieur du trottoir",
         "trottoir tronqué par D_MAX (indéterminé)", "≈ bord extérieur du trottoir", "au milieu du trottoir"],
        default="au-delà du trottoir")
    cotes["d1_moins_b"] = d1 - b

    tab = cotes["position_d1"].value_counts().reindex(ORDRE_POSITION_D1).fillna(0).astype(int).to_frame("demi-transects")
    tab["%"] = (100 * tab["demi-transects"] / tab["demi-transects"].sum()).round(1)
    print(f"Segments « {nature} » : position du 1er changement de couverture par rapport au trottoir GT")
    display(tab)
    compar = cotes[cotes["a"].notna() & cotes["d1"].notna()]
    print("Même tableau, par type highway (% des demi-transects avec changement ET trottoir GT)")
    display((100 * pd.crosstab(compar["highway"], compar["position_d1"], normalize="index"))
            .reindex(columns=[c for c in ORDRE_POSITION_D1 if c in set(compar["position_d1"])]).round(1))
    return cotes


def plot_d1_vs_b(cotes, d_max, tol_bord, nature):
    ok = cotes[cotes["a"].notna() & cotes["d1"].notna() & ~cotes["tronque"]]
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    axes[0].hist(ok["d1_moins_b"].clip(-d_max, d_max), bins=np.linspace(-d_max, d_max, 61), color="tab:orange")
    axes[0].axvline(0, color="k", linewidth=1)
    axes[0].axvspan(-tol_bord, tol_bord, color="grey", alpha=0.2, label=f"±{tol_bord} m du bord extérieur")
    axes[0].axvline(ok["d1_moins_b"].median(), color="k", linestyle="--",
                    label=f"médiane = {ok['d1_moins_b'].median():+.2f} m")
    axes[0].set_xlabel("d1 − b (m)   > 0 : le changement tombe au-delà du trottoir")
    axes[0].set_ylabel("demi-transects")
    axes[0].set_title(f"{nature} : 1er changement vs bord extérieur du trottoir")
    axes[0].legend()
    axes[1].scatter(ok["b"], ok["d1"], s=3, alpha=0.2, label="d1 vs b")
    axes[1].scatter(ok["a"], ok["d1"], s=3, alpha=0.2, color="tab:green", label="d1 vs a")
    axes[1].plot([0, d_max], [0, d_max], "k--", linewidth=1)
    axes[1].set_xlim(0, d_max)
    axes[1].set_ylim(0, d_max)
    axes[1].set_aspect("equal")
    axes[1].set_xlabel("distance GT (m)")
    axes[1].set_ylabel("d1 proxy (m)")
    axes[1].legend(markerscale=4)
    plt.tight_layout()
    plt.show()


def exporter_comparaison(out_dir, cmp_seg, seg_A, res, tr_couv, gt_par_couche, couches_gt, d_max, seuil, crs):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    nom = out_dir / f"comparaison_GT_D{d_max:g}m_seuil{seuil:g}m.gpkg"
    seg_A[["segment_id", "highway", "geometry"]].merge(cmp_seg, on="segment_id").to_file(
        nom, layer="segments_comparaison", driver="GPKG")
    geo = res[["segment_id", "k", "cx", "cy", "nx", "ny"]].merge(tr_couv[["segment_id", "k"]], on=["segment_id", "k"])
    geo = geo.assign(geometry=geom_transects(geo, d_max))[["segment_id", "k", "geometry"]]
    for nom_c, g in gt_par_couche.items():
        gpd.GeoDataFrame(geo.merge(g, on=["segment_id", "k"]), crs=crs).to_file(
            nom, layer=f"transects_GT_{nom_c}", driver="GPKG")
        couches_gt[nom_c].drop(columns="couche").to_file(nom, layer=f"{nom_c}_GT", driver="GPKG")
    print("Exporté :", nom.resolve())


def exporter_diagnostic(out_dir, cmp_seg, seg_A, res, gt_e, dr, veg, nature, highways, couche, mode,
                        d_max, crs, seuil_gros_ecart=10.0, marge=30.0, pos_seg=None):
    """Segments d'une nature / highway avec leur écart à la GT, transects, points proxy/GT, contexte."""
    sel = cmp_seg[(cmp_seg["nature"] == nature) & (cmp_seg["couche_GT"] == couche)]
    if mode is not None:
        sel = sel[sel["mode"] == mode]
    sel = sel.drop(columns=["highway"], errors="ignore").merge(
        seg_A[["segment_id", "highway", "seg_len_m", "geometry"]], on="segment_id")
    if highways is not None:
        sel = sel[sel["highway"].isin(highways)]
    sel = sel[sel["ecart_rel"].notna()].copy()
    sel["abs_err_m"] = sel["err_abs_m"].abs()
    sel["gros_ecart"] = sel["abs_err_m"] >= seuil_gros_ecart
    if pos_seg is not None:
        sel = sel.merge(pos_seg, left_on="segment_id", right_index=True, how="left")
    sel = sel.sort_values("abs_err_m", ascending=False)
    sel["rang_ecart"] = np.arange(1, len(sel) + 1)
    seg_exp = gpd.GeoDataFrame(sel, geometry="geometry", crs=crs)
    print(f"{len(seg_exp):,} segments exportés, dont {seg_exp['gros_ecart'].sum():,} "
          f"avec |erreur| ≥ {seuil_gros_ecart} m")

    ids = seg_exp["segment_id"]
    src = res[res["segment_id"].isin(ids)].merge(gt_e, on=["segment_id", "k"], how="left")
    tr_exp = src[["segment_id", "k", "cx", "cy", "nx", "ny", "cat0_l", "cat0_r", "d_l", "d_r", "cat1_l", "cat1_r",
                  "d2_l", "d2_r"] + [c for c in gt_e.columns if c.startswith("GT_")]].merge(
        seg_exp[["segment_id", "err_abs_m", "gros_ecart"]], on="segment_id")
    tr_exp = gpd.GeoDataFrame(tr_exp.drop(columns=["cx", "cy", "nx", "ny"]),
                              geometry=geom_transects(tr_exp, d_max), crs=crs)

    pts = []
    for col, sg, cote, type_pt in [("d_l", 1, "l", "P1 proxy"), ("d_r", -1, "r", "P1 proxy"),
                                   ("GT_a_l", 1, "l", "GT bord intérieur"), ("GT_a_r", -1, "r", "GT bord intérieur"),
                                   ("GT_b_l", 1, "l", "GT bord extérieur"), ("GT_b_r", -1, "r", "GT bord extérieur")]:
        m = src[col].notna()
        pts.append(gpd.GeoDataFrame({"segment_id": src.loc[m, "segment_id"].values, "k": src.loc[m, "k"].values,
                                     "cote": cote, "type": type_pt, "d": src.loc[m, col].astype(float).values},
                                    geometry=points_changement(src, col, sg), crs=crs))
    pts_exp = gpd.GeoDataFrame(pd.concat(pts, ignore_index=True), crs=crs)

    zone = shapely.union_all(seg_exp.buffer(marge).values)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    hw = "-".join(highways) if highways else "tous"
    nom = out_dir / f"diag_{nature.replace(' ', '_')}_{hw}_vs_{couche}.gpkg"
    seg_exp.to_file(nom, layer="segments_ecart", driver="GPKG")
    tr_exp.to_file(nom, layer="transects", driver="GPKG")
    pts_exp.to_file(nom, layer="points_proxy_GT", driver="GPKG")
    dr[dr.intersects(zone)].to_file(nom, layer="domaine_routier", driver="GPKG")
    veg[veg.intersects(zone)].to_file(nom, layer="couverture_sol", driver="GPKG")
    print("Exporté :", nom.resolve())
    return seg_exp
