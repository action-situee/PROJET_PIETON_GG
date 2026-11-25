# derived_attributes.py
"""
Attributs dérivés : calculés APRÈS l'extraction de l'étape 2 (boucle V3 de 2_2),
en combinant des colonnes déjà présentes dans step2_features.

Convention
----------
Dans attributs_info, un attribut dérivé a how_<territoire> = "derived".
La boucle V3 le saute ; la section « Attributs dérivés » de 2_2 appelle la
fonction enregistrée sous son nom dans DERIVED_ATTRIBUTES.

Signature d'une fonction dérivée :
    f(features: pd.DataFrame, ctx: dict) -> pd.DataFrame
- features : step2_features (une ligne par segment, colonne 'segment_id')
- ctx      : contexte fourni par le notebook (colname(), vitesse par segment…)
- retour   : DataFrame aligné sur features.index, colonnes à ajouter
             (la première colonne est la valeur de l'attribut dérivé)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# ============================================================================
# Traversées
# ============================================================================
# Classes de vitesse : bornes droites incluses
SPEED_BINS   = [-np.inf, 10, 30, 50, np.inf]
SPEED_LABELS = ["no_car", "slow_cars", "normal", "intense"]

# Besoin de traversées par classe (0 = aucun besoin, 1 = besoin maximal)
BESOIN_BY_CLASS = {"no_car": 0.0, "slow_cars": 0.3, "normal": 0.7, "intense": 1.0}

# Attributs de comptage (lignes de attributs_info, how = count_rectangle)
CROSSING_COUNT_ATTR = "n_traversees"
CROSSING_SIGNAL_COUNT_ATTR = "n_traversees_feux"


def speed_class(speed_kph) -> pd.Series:
    """Classe de vitesse (catégorielle) ; vitesse manquante -> NaN."""
    return pd.cut(pd.Series(speed_kph), bins=SPEED_BINS, labels=SPEED_LABELS, right=True)


# >>> BLOC SCORE TRAVERSÉES : c'est ici que se règle la logique du score
def compute_crossing_score(vitesse_classe, n_traversees, n_traversees_feux,
                           besoin_by_class=BESOIN_BY_CLASS):
    """
    score = 1 - besoin × (1 - offre)

    besoin : selon la classe de vitesse (besoin_by_class)
    offre  :
      - no_car, slow_cars : 1 dès qu'il y a une traversée, sinon 0 (pas de bonus feux)
      - normal, intense   : 1 si au moins une traversée à feux,
                            0.5 si traversée(s) sans feux uniquement,
                            0 si aucune traversée
    Classe inconnue (vitesse manquante) -> NaN.
    """
    cls = pd.Series(vitesse_classe).astype("object")
    n = pd.Series(n_traversees, index=cls.index)
    n_sig = pd.Series(n_traversees_feux, index=cls.index)

    besoin = cls.map(besoin_by_class).astype(float)

    has_any = n > 0
    has_sig = n_sig > 0
    car_heavy = cls.isin(["normal", "intense"])

    offre = np.where(
        car_heavy,
        np.where(has_sig, 1.0, np.where(has_any, 0.5, 0.0)),
        np.where(has_any, 1.0, 0.0),
    )
    offre = pd.Series(offre, index=cls.index).where(besoin.notna())

    score = 1 - besoin * (1 - offre)
    return besoin, offre, score
# <<< FIN BLOC SCORE TRAVERSÉES


def crossing_score_table(speed_kph, n_traversees, n_traversees_feux,
                         besoin_by_class=BESOIN_BY_CLASS) -> pd.DataFrame:
    """Vitesse + comptages -> classe, besoin, offre, score (même index que speed_kph)."""
    speed = pd.Series(speed_kph)
    cls = speed_class(speed)
    cls.index = speed.index
    besoin, offre, score = compute_crossing_score(cls, n_traversees, n_traversees_feux, besoin_by_class)
    return pd.DataFrame({
        "vitesse_classe": cls.astype("object"),
        "besoin": besoin,
        "offre": offre,
        "score": score,
    }, index=speed.index)


def derive_traversees(features: pd.DataFrame, ctx: dict) -> pd.DataFrame:
    """
    Score traversées à partir des comptages de l'étape 2 et d'une vitesse par segment.

    ctx attendu :
      - colname(attr) -> nom de colonne step2 d'un attribut (ex. 'n_traversees_10')
      - segment_speed : pd.Series vitesse (km/h) indexée par segment_id
      - out_name      : nom de la colonne de score (ex. 'traversees_10')
    """
    n_col = ctx["colname"](CROSSING_COUNT_ATTR)
    sig_col = ctx["colname"](CROSSING_SIGNAL_COUNT_ATTR)
    missing = [c for c in (n_col, sig_col) if c not in features.columns]
    if missing:
        raise KeyError(f"Colonnes de comptage absentes de step2_features : {missing} "
                       f"(lignes {CROSSING_COUNT_ATTR} / {CROSSING_SIGNAL_COUNT_ATTR} calculées dans la boucle V3 ?)")

    speed = features["segment_id"].map(ctx["segment_speed"])
    tab = crossing_score_table(speed, features[n_col], features[sig_col])

    out_name = ctx["out_name"]
    return pd.DataFrame({
        out_name: tab["score"],                       # valeur de l'attribut (NaN si vitesse inconnue)
        f"{out_name}_offre": tab["offre"],
        f"{out_name}_besoin": tab["besoin"],
        f"{out_name}_vitesse_classe": tab["vitesse_classe"],
    }, index=features.index)


# ============================================================================
# Coupures (vélo) — ajout Claude, 2026-11-24
# Méthode détaillée : attribut_coupure.md (racine du dépôt)
# ============================================================================
# Couche de hiérarchie routière (relative à input_file_path), champ de classe et conversion
COUPURE_HIERARCHIE_FILE = "network_agreg/AGGLO_HIERARCHIE_ROUTE.gpkg"
COUPURE_CLASS_FIELD = "classe"
COUPURE_CLASS_MAP = {"primaire": 1, "secondaire": 2, "tertiaire": 3}   # autoroute, bretelle, vide -> ignorés
COUPURE_HORS_HIERARCHIE = 4        # classe du cycliste sans route colinéaire (path, footway...)
COUPURE_MAX_ECART = 3              # écart maximal possible : 4 - 1
COUPURE_HALF_WIDTH_M = 10.0        # demi-largeur du rectangle (défaut si buffer_size vide dans l'Excel)
COUPURE_EXTEND_M = 10.0            # prolongement du segment à chaque bout (défaut si extend_m vide dans l'Excel)
COUPURE_COLINEAR_MIN = 0.8         # |cos| >= seuil : candidat « route du cycliste » ; < seuil : coupure possible
COUPURE_MIN_PIECE_M = 2.0          # morceaux de route plus courts ignorés (coins de rectangle, orientation instable)
COUPURE_N_SCALE = 2.0              # f(n_eff) = 1 / (1 + n_eff / COUPURE_N_SCALE)
# >>> POIDS DES BRANCHES (Claude, 2026-11-25) : poids d'une branche de croisement dans n_eff,
# selon (classe du cycliste, classe de la route croisée). 1 primaire, 2 secondaire, 3 tertiaire, 4 hors hiérarchie.
#   sous la diagonale (route croisée plus intense, écart > 0) : 1 (comme avant le 25.11)
#   diagonale (même classe) : croisement d'égal à égal, plus fort pour les grands axes
#   au-dessus (route croisée moins intense) : petit poids, un carrefour reste un carrefour
# Mettre la diagonale et le dessus à 0 redonne le calcul du 24.11 (seules les coupures par une route plus intense).
COUPURE_POIDS_BRANCHE = {
    #  croisée :  1     2     3
    1: {1: 0.50, 2: 0.30, 3: 0.15},   # cycliste sur une primaire
    2: {1: 1.00, 2: 0.35, 3: 0.15},   # cycliste sur une secondaire
    3: {1: 1.00, 2: 1.00, 3: 0.20},   # cycliste sur une tertiaire
    4: {1: 1.00, 2: 1.00, 3: 1.00},   # cycliste hors hiérarchie
}
# <<< FIN POIDS DES BRANCHES
COUPURE_GIRATOIRE_ATTR = "giratoire"   # segments avec giratoire_<buffer> > 0 -> coupure = NaN
COUPURE_CRS = "EPSG:2056"


def compute_coupure_intensity(classe_cycliste, n_coupures, ecart_max,
                              max_ecart=COUPURE_MAX_ECART, n_scale=COUPURE_N_SCALE):
    """Intensité de coupure (attribut défavorable, inversé dans 3_1) :
    1 - (1 - écart_max / max_ecart) / (1 + n_eff / n_scale). 0 = aucune coupure.
    n_coupures = n_eff, somme pondérée des branches (COUPURE_POIDS_BRANCHE)."""
    good = (1 - np.asarray(ecart_max, dtype=float) / max_ecart) / (1 + np.asarray(n_coupures, dtype=float) / n_scale)
    return 1 - good


def derive_coupure(features: pd.DataFrame, ctx: dict) -> pd.DataFrame:
    """
    Coupures de l'itinéraire cyclable par des routes plus intenses (hiérarchie routière).

    Pour chaque segment vélo : rectangle (demi-largeur, segment prolongé aux deux bouts),
    morceaux de route découpés par le rectangle, colinéarité locale |cos θ| de chaque morceau.
      - route du cycliste : morceau le plus colinéaire parmi |cos| >= COUPURE_COLINEAR_MIN
        (égalité -> classe la plus intense) ; aucun -> hors hiérarchie (4)
      - branches de croisement : morceaux |cos| < COUPURE_COLINEAR_MIN, pondérés par
        COUPURE_POIDS_BRANCHE[classe cycliste][classe croisée] -> n_eff (25.11)
      - écart_max : branches de classe plus intense que celle du cycliste
      - intensité = 1 - (1 - écart_max / 3) / (1 + n_eff / 2)   (0 = aucune coupure)
    Segments avec giratoire à proximité (giratoire_<buffer> > 0) : intensité NaN.

    ctx attendu : colname(attr), out_name, row (ligne Excel), input_file_path.
    """
    import geopandas as gpd
    import shapely
    from feature_to_network import segment_rectangles

    row = ctx.get("row", {})
    def _num(key, default):
        v = row.get(key, np.nan) if hasattr(row, "get") else np.nan
        try:
            v = float(v)
        except (TypeError, ValueError):
            return default
        return default if np.isnan(v) else v
    territory = ctx.get("territory", "GG")
    half_width = _num(f"buffer_size_{territory}", COUPURE_HALF_WIDTH_M)
    extend = _num(f"extend_m_{territory}", COUPURE_EXTEND_M)
    out_name = ctx["out_name"]

    # --- Segments vélo -------------------------------------------------------
    if not isinstance(features, gpd.GeoDataFrame) or features.geometry is None:
        raise TypeError("derive_coupure : features doit être un GeoDataFrame (step2_features avec géométrie)")
    seg = features.geometry.to_crs(COUPURE_CRS)
    seg_geoms = np.asarray(seg.values)
    n_seg = len(seg_geoms)
    rect = np.asarray(segment_rectangles(seg, half_width, extend).values)
    c0, c1 = shapely.get_point(seg_geoms, 0), shapely.get_point(seg_geoms, -1)
    d_seg = np.c_[shapely.get_x(c1) - shapely.get_x(c0), shapely.get_y(c1) - shapely.get_y(c0)]
    nrm = np.linalg.norm(d_seg, axis=1, keepdims=True)
    d_seg = np.divide(d_seg, nrm, out=np.full_like(d_seg, np.nan), where=nrm > 0)

    # --- Hiérarchie routière -------------------------------------------------
    path = f"{ctx['input_file_path']}/{COUPURE_HIERARCHIE_FILE}"
    roads = gpd.read_file(path).to_crs(COUPURE_CRS)
    roads["classe_num"] = roads[COUPURE_CLASS_FIELD].map(COUPURE_CLASS_MAP)
    n_ignored = int(roads["classe_num"].isna().sum())
    roads = roads[roads["classe_num"].notna() & roads.geometry.notna()]
    roads = roads.set_geometry(shapely.force_2d(roads.geometry.values)).explode(index_parts=False, ignore_index=True)
    road_geoms = np.asarray(roads.geometry.values)
    road_cls = roads["classe_num"].to_numpy(dtype=float)
    print(f"  Hiérarchie routière : {len(roads):,} lignes retenues ({n_ignored:,} ignorées : autoroute, bretelle, sans classe)")

    # --- Morceaux de route dans les rectangles -------------------------------
    i_seg, i_road = shapely.STRtree(road_geoms).query(rect, predicate="intersects")
    pieces = shapely.intersection(rect[i_seg], road_geoms[i_road])
    parts, i_pair = shapely.get_parts(pieces, return_index=True)
    is_line = shapely.get_type_id(parts) == 1
    parts, i_pair = parts[is_line], i_pair[is_line]
    keep = shapely.length(parts) >= COUPURE_MIN_PIECE_M
    parts, i_pair = parts[keep], i_pair[keep]
    s_idx, cls = i_seg[i_pair], road_cls[i_road[i_pair]]

    p0, p1 = shapely.get_point(parts, 0), shapely.get_point(parts, -1)
    d_p = np.c_[shapely.get_x(p1) - shapely.get_x(p0), shapely.get_y(p1) - shapely.get_y(p0)]
    nrm = np.linalg.norm(d_p, axis=1, keepdims=True)
    d_p = np.divide(d_p, nrm, out=np.full_like(d_p, np.nan), where=nrm > 0)
    cos = np.abs((d_p * d_seg[s_idx]).sum(axis=1)).round(3)
    ok = ~np.isnan(cos)
    s_idx, cls, cos = s_idx[ok], cls[ok], cos[ok]
    pdf = pd.DataFrame({"seg": s_idx, "cls": cls, "cos": cos})

    # --- Route du cycliste : plus colinéaire, puis plus intense ---------------
    cand = pdf[pdf["cos"] >= COUPURE_COLINEAR_MIN].sort_values(["seg", "cos", "cls"], ascending=[True, False, True])
    own = cand.drop_duplicates("seg").set_index("seg")
    classe_cyc = np.full(n_seg, float(COUPURE_HORS_HIERARCHIE))
    classe_cyc[own.index.to_numpy()] = own["cls"].to_numpy()
    cos_cyc = np.full(n_seg, np.nan)
    cos_cyc[own.index.to_numpy()] = own["cos"].to_numpy()

    # --- Croisements : toutes les branches non colinéaires, pondérées (25.11) --
    # AVANT : seules les branches plus intenses que la route du cycliste, poids 1
    cross = pdf[pdf["cos"] < COUPURE_COLINEAR_MIN].copy()
    cut = cross.copy()
    own_cut = classe_cyc[cut["seg"].to_numpy()].astype(int)
    cut["w"] = [COUPURE_POIDS_BRANCHE.get(o, {}).get(int(k), 0.0) for o, k in zip(own_cut, cut["cls"].to_numpy())]
    cut = cut[cut["w"] > 0]
    n_branch = np.zeros(n_seg)
    n_eff = np.zeros(n_seg)
    if len(cut):
        gb = cut.groupby("seg")["w"]
        n_branch[gb.size().index.to_numpy()] = gb.size().to_numpy()
        n_eff[gb.sum().index.to_numpy()] = gb.sum().to_numpy()
    # écart : toutes les branches plus intenses que la route du cycliste, indépendamment des poids (inchangé)
    cut = cross[cross["cls"].to_numpy() < classe_cyc[cross["seg"].to_numpy()]]
    n_cut = np.zeros(n_seg)
    ecart = np.zeros(n_seg)
    if len(cut):
        g = cut.groupby("seg")["cls"]
        n_cut[g.size().index.to_numpy()] = g.size().to_numpy()
        mins = g.min()
        ecart[mins.index.to_numpy()] = classe_cyc[mins.index.to_numpy()] - mins.to_numpy()

    intensity = compute_coupure_intensity(classe_cyc, n_eff, ecart)   # AVANT : n_cut

    # Segments sans géométrie exploitable
    bad = ~shapely.is_valid(seg_geoms) | shapely.is_empty(seg_geoms) | np.isnan(d_seg).any(axis=1)
    intensity[bad] = np.nan

    # --- Giratoires : déjà comptés par l'attribut giratoire -> NaN ------------
    n_gir = 0
    try:
        gcol = ctx["colname"](COUPURE_GIRATOIRE_ATTR)
    except KeyError:
        gcol = None
    if gcol and gcol in features.columns:
        gir = (pd.to_numeric(features[gcol], errors="coerce") > 0).to_numpy()
        intensity[gir] = np.nan
        n_gir = int(gir.sum())
    else:
        print(f"  ⚠️ colonne giratoire absente : pas de NaN près des giratoires")
    print(f"  {len(pdf):,} morceaux de route dans les rectangles | {n_gir:,} segments près d'un giratoire -> NaN")

    return pd.DataFrame({
        out_name: intensity,                                  # intensité de coupure (défavorable)
        f"{out_name}_n": n_branch,                            # nombre de branches de croisement comptées (poids > 0)
        f"{out_name}_n_eff": n_eff,                           # somme pondérée des branches (utilisée dans le score)
        f"{out_name}_n_ecart": n_cut,                         # dont branches plus intenses que la route du cycliste
        f"{out_name}_ecart": ecart,                           # écart de classe maximal (0 à 3)
        f"{out_name}_classe_cycliste": classe_cyc,            # 1, 2, 3, ou 4 hors hiérarchie
        f"{out_name}_cos_cycliste": cos_cyc,                  # colinéarité de la route retenue (NaN si hors hiérarchie)
    }, index=features.index)


# ============================================================================
# Registre : nom de l'attribut dans attributs_info -> fonction
# ============================================================================
DERIVED_ATTRIBUTES = {
    "traversees": derive_traversees,
    "coupure": derive_coupure,       # >>> ajout 2026-11-24
}
