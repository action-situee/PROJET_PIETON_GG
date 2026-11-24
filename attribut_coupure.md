# Attribut `coupure` — méthode (indice de cyclabilité)

Attribut propre à la **cyclabilité** (pas repris pour la marchabilité). Il mesure combien l'itinéraire cyclable est coupé par des routes **plus intenses** que celle sur laquelle roule le cycliste, et de combien. Il remplace l'ancien attribut `traversees` vélo (passé hors indice le 24.11.2026).

État au **24.11.2026**. Code : `Notebook/Step 2/derived_attributes.py` (`derive_coupure`), calculé dans `2_2` (section « Attributs dérivés »).

## 1. Paramètres

| Paramètre | Valeur | Où | Rôle |
|---|---|---|---|
| Couche de hiérarchie routière | `Data/input/network_agreg/AGGLO_HIERARCHIE_ROUTE.gpkg` | `COUPURE_HIERARCHIE_FILE` | réseau routier hiérarchisé du Grand Genève (état actuel, champ `classe`) |
| Conversion des classes | primaire = 1, secondaire = 2, tertiaire = 3 | `COUPURE_CLASS_MAP` | 1 = trafic le plus intense |
| Classes ignorées | `autoroute`, `bretelle`, sans classe | `COUPURE_CLASS_MAP` | lignes retirées : traitées comme si elles n'existaient pas |
| Classe hors hiérarchie | 4 | `COUPURE_HORS_HIERARCHIE` | cycliste sans route colinéaire (path, footway, piste séparée…) |
| Demi-largeur du rectangle | 10 m | Excel `buffer_size_GG` (défaut `COUPURE_HALF_WIDTH_M`) | de chaque côté du segment |
| Prolongement du rectangle | 10 m à chaque bout | Excel `extend_m_GG` si rempli, sinon `COUPURE_EXTEND_M` | capte les carrefours aux extrémités du segment |
| Seuil de colinéarité | 0,8 (≈ 37°) | `COUPURE_COLINEAR_MIN` | ≥ 0,8 : candidat « route du cycliste » ; < 0,8 : coupure possible |
| Longueur minimale d'un morceau | 2 m | `COUPURE_MIN_PIECE_M` | ignore les coins de rectangle à l'orientation instable |
| Écart maximal | 3 (= 4 − 1) | `COUPURE_MAX_ECART` | normalise l'écart de classe |
| Échelle du facteur de nombre | 2 | `COUPURE_N_SCALE` | f(n) = 1 / (1 + n / 2) |
| Giratoires | `giratoire_20 > 0` → NaN | `COUPURE_GIRATOIRE_ATTR` | déjà pénalisés par l'attribut `giratoire` |
| CRS de calcul | EPSG:2056 | `COUPURE_CRS` | |

Ligne `coupure` de `attributs_info_bike_WIP.xlsx` : classe `infrastructure`, `socle = True`, `initial_weight = 0.5`, `class_weight = 0.5`, `impact_attribut = defavorable`, `how_GG = derived`, `buffer_size_GG = 10`, `missing_value_strategy = keep_nan`, `clip_GG` vide.

## 2. Arbitrages

| Sujet | Décision | Raison |
|---|---|---|
| Graphe networkx | non utilisé : traitement géométrique (index spatial) | la méthode n'a besoin que de géométrie ; seules 43 % des extrémités de la couche sont partagées, un graphe serait fragmenté |
| Autoroutes, bretelles | ignorées | pas de donnée pertinente pour le vélo ; évite aussi la plupart des faux carrefours sur ouvrages dénivelés |
| Ponts, tunnels | non traités | effet minoritaire une fois les autoroutes retirées |
| État de la hiérarchie | champ `classe` (actuel) | `nature_chgmt` / `changement` (hiérarchie projetée) non utilisés |
| Route du cycliste | morceau le plus colinéaire parmi |cos θ| ≥ 0,8 ; égalité → classe la plus intense | |
| Aucun morceau colinéaire | classe 4 (hors hiérarchie) | le cycliste est sur un axe moins important que toute route classée |
| Aucune route dans le rectangle | aucune coupure → meilleur score | |
| Ce qui compte comme coupure | morceau |cos θ| < 0,8 **et** de classe plus intense que la route du cycliste (écart > 0) | une primaire coupée par une tertiaire garde un bon score |
| Regroupement des coupures | aucun : chaque morceau compte | n se lit comme un nombre de **branches** en conflit (un carrefour en croix = 2, un T = 1) ; un carrefour à la jonction de deux segments compte pour les deux |
| Giratoires | NaN | déjà comptés par l'attribut `giratoire` ; avec `NAN_POLICY = "ignore"` (3_1), ces segments restent dans l'indice, coupure ignorée |
| Sens de l'attribut | défavorable : l'attribut exporté est une **intensité** (0 = aucune coupure) | lecture « plus c'est haut, plus c'est coupé », comme `accident` ; `3_1` l'inverse |

## 3. Traitement géométrique

1. **Hiérarchie routière** : lecture, passage en 2D (couche 3D mesurée), conversion des classes, retrait des classes ignorées, éclatement des multilignes.
2. **Rectangle** autour de chaque segment vélo (segments ≤ 50 m de `step1`) : segment prolongé de 10 m à chaque bout dans l'axe de son premier / dernier tronçon, puis buffer à bouts plats de 10 m de chaque côté (`segment_rectangles` de `feature_to_network.py`, même géométrie que les anciennes traversées). Le rectangle fait donc 20 m de large et environ L + 20 m de long.
3. **Morceaux de route** : index spatial (`STRtree`) entre rectangles et lignes de la hiérarchie ; chaque ligne est découpée par le rectangle ; seules les parties linéaires d'au moins 2 m sont gardées.
4. **Colinéarité locale** : pour chaque morceau, |cos θ| entre la direction du morceau (de son premier à son dernier point) et celle du segment vélo (de son premier à son dernier point). 1 = colinéaire, 0 = perpendiculaire. L'angle est mesuré sur le **morceau découpé**, pas sur la ligne entière (certaines lignes font plusieurs kilomètres et tournent).

## 4. Calcul du score

Pour chaque segment :

- **classe du cycliste** c : classe du morceau le plus colinéaire parmi ceux de |cos θ| ≥ 0,8 (égalité → la plus intense) ; aucun → c = 4 ;
- **coupures** : morceaux de |cos θ| < 0,8 et de classe k < c ;
- **n** = nombre de coupures ; **écart_max** = c − (classe la plus intense parmi les coupures), 0 sans coupure ;
- **score** (1 = bon) = (1 − écart_max / 3) × 1 / (1 + n / 2) ;
- **attribut exporté** `coupure_10` = **intensité** = 1 − score (défavorable).

| Situation | c | coupures | écart_max | n | score | intensité |
|---|---|---|---|---|---|---|
| aucune route proche, ou aucune coupure | — | — | 0 | 0 | 1 | 0 |
| primaire coupée par des tertiaires | 1 | aucune (k ≥ c) | 0 | 0 | 1 | 0 |
| tertiaire coupée par une secondaire (T) | 3 | 1 | 1 | 1 | 0,44 | 0,56 |
| tertiaire traversant une primaire (croix) | 3 | 2 | 2 | 2 | 0,17 | 0,83 |
| chemin traversant une primaire (croix) | 4 | 2 | 3 | 2 | 0 | 1 |
| chemin coupé par une tertiaire (T) | 4 | 1 | 1 | 1 | 0,44 | 0,56 |

Ensuite, comme tout attribut : `keep_nan` (pas de remplissage), min-max puis inversion (défavorable) dans `3_1`. Avec `NAN_POLICY = "ignore"`, un segment NaN (giratoire) garde un indice calculé sur ses autres attributs.

## 5. Colonnes produites (`step2_features`, puis `step3_index` et gpkg agrégés)

| Colonne | Contenu |
|---|---|
| `coupure_10` | intensité de coupure (0 à 1, NaN près d'un giratoire) — c'est l'attribut |
| `coupure_10_n` | nombre de coupures |
| `coupure_10_ecart` | écart de classe maximal (0 à 3) |
| `coupure_10_classe_cycliste` | classe de la route du cycliste (1, 2, 3, ou 4 hors hiérarchie) |
| `coupure_10_cos_cycliste` | colinéarité de la route retenue (NaN si hors hiérarchie) |

`2_2` affiche après le calcul (section « Contrôle coupure ») : la répartition du nombre de coupures, la route du cycliste par classe, et la part des segments sans route colinéaire.

## 6. Premiers résultats (step2 vélo du 23.11, 620 047 segments, 25 383 km)

Calcul en ~10 s. 32 035 lignes de hiérarchie retenues (845 ignorées).

| Route du cycliste | % segments | % km | % avec coupure |
|---|---|---|---|
| 1 primaire | 7,1 | 6,6 | 0,0 |
| 2 secondaire | 9,1 | 8,5 | 1,9 |
| 3 tertiaire | 37,3 | 36,1 | 6,6 |
| 4 hors hiérarchie | 46,5 | 48,8 | 8,6 |

- 6,6 % des segments ont au moins une coupure (1,3 en moyenne, écart maximal moyen 1,4) ; 93,4 % n'en ont aucune.
- 2,6 % des segments (16 204) sont près d'un giratoire → NaN.
- Une primaire n'a jamais de coupure par construction (aucune route plus intense).

## 7. Limites connues

- **Ponts et tunnels** : une primaire en viaduc au-dessus d'une voie verte compte comme coupure (les autoroutes étant retirées, c'est marginal).
- **Comptage par branches** : n dépend du découpage des lignes de la hiérarchie aux carrefours ; une route à chaussées séparées compte double.
- **Segments voisins** : un même carrefour est compté pour les segments dont le rectangle le touche ; sans effet notable sur les moyennes par carreau.
- **Orientation** : mesurée de bout à bout ; un morceau très courbe dans le rectangle peut avoir une colinéarité approximative.
- **Hiérarchie** : la qualité dépend de la couche ; une route absente de la hiérarchie est vue comme hors hiérarchie (et ne coupe rien).

## 8. Relancer

`2_2` (au moins la section « Attributs dérivés » puis « Contrôle coupure ») → `3_1` → `3_2`.
