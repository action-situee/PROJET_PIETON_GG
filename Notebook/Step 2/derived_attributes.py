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
# Registre : nom de l'attribut dans attributs_info -> fonction
# ============================================================================
DERIVED_ATTRIBUTES = {
    "traversees": derive_traversees,
}
