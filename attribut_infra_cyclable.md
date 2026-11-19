# Attribut `infra_cyclable` — récapitulatif

Indice de cyclabilité (bike index), Grand Genève. État au **19.11.2026**, après les modifications du jour dans `0_1`, `2_1` et `3_1` (dont la garde sur le schéma cyclable, §2).

`infra_cyclable` mesure le type d'aménagement cyclable du segment. Il est dans la classe **infrastructure**, avec `initial_weight = 0.5` et `class_weight = 0.5` (`attributs_info_bike_WIP.xlsx`), `buffer_size_GG = 2`, `how_GG = rectangle_weighted_mean`, `missing_value_strategy = zero_if_missing`.

> Les sorties actuelles de `step-1` à `step-3` ont été produites **avant** tout ou partie de ces modifications. Pour qu'elles s'appliquent, relancer dans l'ordre : `0_1` → `1_0` → `2_1` → `2_2` → `3_1` → `3_2`. En particulier, `1_0` est nécessaire pour que les `footway` ajoutés au graphe vélo deviennent des segments.

## 1. Classes

Une seule classe par way OSM : la première règle qui s'applique, dans l'ordre du tableau. Le **rang** sert ensuite à fusionner avec le schéma cyclable d'agglomération (la classe de rang le plus haut l'emporte). Le **score** est attribué dans `2_1`.

| Classe | Score | Rang | Règle OSM (`map_bike_infra`) | km avant 19.11 | km après | Filtre des doublons (3_1) | Modif. 19.11 |
|---|---|---|---|---|---|---|---|
| `piste_cyclable` | 1 | 8 | `highway=cycleway` (sauf `segregated=no`) ; `highway=path` + `bicycle=designated` + `segregated=yes` ; `cycleway:*=track` | 485 | 290 | retire (si dessinée à part) | `separate` retiré ; `cycleway` + `segregated=no` → `voie_mixte` |
| `voie_mixte` | 0,7 | 6 | `highway=cycleway` + `segregated=no` ; `highway=path` + `bicycle=designated` (non séparé) | — | 237 | retire | **nouvelle** |
| `bande_cyclable` | 0,7 | 7 | `cycleway:*=lane` | 516 | 526 | protégée, ne retire pas (portée par la route) | inchangée |
| `partage_bus` | 0,5 | 4 | `cycleway:*=share_busway / shared_busway / shared_lane` | 88 | 91 | protégée, ne retire pas | inchangée |
| `accotement` | 0,5 | 3 | `cycleway:*=shoulder` | — | 69 | protégée, ne retire pas | **nouvelle** |
| `footway_designe` | 0,6 | 5 | `highway=footway` + `bicycle=designated` | — | 67 | retire | **nouvelle** |
| `bike_pedestrian_area` | 0,4 | 2 | `highway=pedestrian / living_street` ; `highway=footway` + `bicycle=yes / permissive` | 298 | 429 | peut être retirée | footway `yes/permissive` ajoutés |
| `partage` | 0,3 | 1 | `highway=track / path / bridleway` (hors `path` désigné) | 7 786 | 7 662 | peut être retirée | `path` désigné → `voie_mixte` |
| `bike_road` | 0 | 0 | autres routes ouvertes aux vélos, dont celles taguées `cycleway=separate` | 8 455 | 8 456 | peut être retirée | reçoit les routes `separate` |
| *(hors graphe vélo)* | — | — | `footway` sans accès vélo, `service`, autoroutes, `bicycle=no`… | 15 336 | 15 138 | — | ~200 km de `footway` entrent dans le graphe |

km = longueur des ways de `GG.osm.pbf` (14.10.2026), classification OSM seule, **avant** fusion avec le schéma cyclable. Une route avec `cycleway:both=lane` compte une fois.

Principaux reclassements du 19.11 :

| De | Vers | km |
|---|---|---|
| hors graphe | `bike_pedestrian_area` | 131,5 |
| `piste_cyclable` | `voie_mixte` | 119,4 |
| `partage` | `voie_mixte` | 117,3 |
| `piste_cyclable` | `bike_road` (`separate`) | 70,1 |
| `bike_road` | `accotement` | 68,6 |
| hors graphe | `footway_designe` | 67,2 |
| `piste_cyclable` | `bande_cyclable` | 9,7 |
| `partage` | `piste_cyclable` | 6,5 |

## 2. Fusion avec le schéma cyclable d'agglomération (`0_1`, cellules 25–26)

Source : `AGGLO_SCHEMA_CYCLABLE.gpkg`, champ `amgt_exist`. Chaque arête reçoit la classe majoritaire du schéma dans un rectangle de demi-largeur 10 m (angle ≤ 45°, part couverte ≥ 50 %). La classe finale `infra_cyclable` est la plus haute (en rang) entre OSM et schéma ; `infra_cyclable_source` dit laquelle a gagné.

> Cette fusion n'est pas dans le dernier commit (18.11.2026, 18h01) : elle a été ajoutée depuis, sans commit, et sans indication d'auteur dans le notebook.

| `amgt_exist` | Classe |
|---|---|
| Site propre (voie verte ou piste cyclable) | `piste_cyclable` |
| Aménagement cyclable sur chaussée (marquage ou bande) | `bande_cyclable` |
| Route partagée sans nécessité d'aménagement | `partage` |
| Modération des vitesses | non utilisé |

### Garde sur les routes (ajout du 19.11)

**Problème.** La ligne « Site propre » du schéma suit le tracé de la piste, souvent à 5–8 m de l'axe OSM de la route. La route tombait donc dans son propre rectangle, recevait `piste_cyclable` et se retrouvait à égalité avec la vraie piste : le filtre des doublons de `3_1` ne pouvait pas la retirer. Cela concernait 190 km de routes.

**Règle.** Le schéma ne peut plus mettre en `piste_cyclable` une **route** déjà longée par une voie cyclable OSM **dessinée à part**.

| Paramètre | Valeur | Rôle |
|---|---|---|
| `SEPARATE_WAY_HW` | `cycleway, path, footway, pedestrian, track, bridleway` | tout autre `highway` est une route |
| `OSM_SEPARATE_DEDICATED` | `piste_cyclable, voie_mixte, footway_designe` | voies cyclables OSM dessinées à part qui bloquent le schéma |
| `SCHEMA_ROAD_GUARD_HALF_WIDTH_M` | 10 | demi-largeur du rectangle autour de la route |
| `SCHEMA_ROAD_GUARD_MAX_ANGLE_DEG` | 30 | voie OSM à peu près parallèle |
| `SCHEMA_ROAD_GUARD_MIN_SHARE` | 0,5 | part minimale de la route longée |

Ces routes gardent leur classe OSM (en général `bike_road`) et portent `schema_piste_ignoree = True` dans `bike_edges_graph`, pour contrôle dans QGIS. Le filtre des doublons de `3_1` les retire ensuite. Une route **sans** voie cyclable OSM à côté garde la piste du schéma : c'est un aménagement absent d'OSM, que seule la route peut porter.

**Effet** (sur `bike_edges_graph` du 19.11, 17h09) : 255 km de routes sont en « Site propre » dans le schéma ; la garde en écarte 177 km. Les routes passées en piste par le schéma tombent de **190 à 49 km** ; 136 km reviennent en `bike_road`, 4 km en `bande_cyclable`.

## 3. Pipeline

| Ordre | Notebook | Cellule | Ce qui est fait |
|---|---|---|---|
| 1 | `0_1_Load_osm_networks_and_nodes_bike_walk` | 14 | `classify_bike` : quelles ways entrent dans le graphe vélo (`bike_class`) |
| 2 | `0_1` | 18 | `map_bike_infra` : typologie OSM `infra_bike` ; `INFRA_RANK` ; `get_bike_direction` (sens vélo, pour le graphe orienté) |
| 3 | `0_1` | 26 | fusion avec le schéma cyclable, avec la garde sur les routes (§2) → `infra_cyclable` (classe), `infra_cyclable_source`, `schema_piste_ignoree` dans `bike_edges_graph` |
| 4 | `1_0_Prepare_network` | — | segmentation (segments ≤ 50 m) → `step1_all_segments` (contient `highway` et `infra_cyclable`) |
| 5 | `2_1_Filter_features_bike` | 43–44 | classe → score (`INFRA_SCORES`) ; classe inconnue → 0 |
| 6 | `2_2_Process_features` | — | `rectangle_weighted_mean`, demi-largeur 2 m → `infra_cyclable_2` par segment |
| 7 | `3_1_Compute_index` | 4, 9, 10 | filtre des doublons parallèles (voir §4), puis min-max et calcul de l'indice |
| 8 | `3_2_Agregated_index` | — | moyenne pondérée par la longueur → carreaux 200 m, GIREC, communes |

## 4. Filtre des doublons parallèles (`3_1`)

But : quand une piste est dessinée à côté d'une route, ne compter le corridor qu'une fois. Les segments retirés sortent de `step3_index` et de l'agrégation ; ils sont exportés dans `step3_doublons_paralleles.gpkg` (avec `part_couverte` et `score_max_voisin`) pour contrôle dans QGIS.

| Paramètre | Valeur | Rôle |
|---|---|---|
| `DEDUP_PARALLEL` | `network == "bike"` | vélo seulement |
| `DEDUP_ATTRIBUTE` | `infra_cyclable` | hiérarchie = score du segment |
| `DEDUP_HALF_WIDTH_M` | 10 | demi-largeur du rectangle (extrémités plates) |
| `DEDUP_MAX_ANGLE_DEG` | 30 | au-delà, croisement : rien n'est retiré |
| `DEDUP_MIN_SHARE` | 0,8 | part minimale du segment couverte |
| `DEDUP_DEDICATED_MIN_SCORE` | 0,5 | seuls les aménagements dédiés (≥ 0,5) retirent, et seulement des segments non dédiés (< 0,5) ; entre aménagements dédiés, rien n'est retiré |
| `DEDUP_ELIMINATOR_HIGHWAYS` | `cycleway, path, footway, pedestrian, track, bridleway` | seul un segment **dessiné à part** retire ; évite qu'une bande retire l'autre chaussée d'une route à chaussées séparées. `None` = pas de condition |

Effet mesuré sur les données du 19.11 (step2 de 16h16, avant le changement `separate`). Effet carreaux : approximation par point milieu, indice actuel, sans recalcul du min-max.

| Demi-largeur | km retirés | Carreaux modifiés | Δ bike_index (médiane / P90 / max) | Δ infra_cyclable (médiane / P90) |
|---|---|---|---|---|
| 6 m | 75 | 505 | +0,002 / +0,028 / +0,09 | +0,03 / +0,21 |
| **10 m (retenu)** | **145** | **788** | +0,004 / +0,036 / +0,14 | +0,04 / +0,27 |
| 15 m | 184 | 949 | +0,005 / +0,036 / +0,14 | +0,05 / +0,27 |

À 10 m, 126 des 145 km retirés sont des routes (69 km le long de pistes, 58 km le long de voies mixtes). Ces chiffres ont été mesurés avant le changement `separate` et la garde sur le schéma : environ 84 km de routes `separate` et 136 km de routes remontées par le schéma deviendront aussi retirables (en partie les mêmes).

## 5. Diagnostic (état de référence)

Sorties carreaux 200 m du 19.11 à 14h36, donc **avant** les modifications du jour. Source : `Notebook/Step 4/analyse_poids_attributs_bike.ipynb`.

| Indicateur | Valeur |
|---|---|
| Poids nominal dans l'indice | 4,8 % |
| Carreaux à 0 | 20,5 % |
| Carreaux à 1 | 0,5 % |
| Moyenne / médiane | 0,215 / 0,30 |
| Plage P5–P95 | 0,43 |
| Part de la variance du bike index expliquée | 10,4 % |
| Part de la variance de la classe « fondamental » (infra + sécurité) | 13,5 % |
| Spearman avec le bike index | 0,57 |
| Spearman avec `Classe_infrastructure` | 0,82 |

## 6. Points ouverts

| Sujet | km (OSM) | Constat | Statut |
|---|---|---|---|
| Contresens aménagés | 21 | `opposite_lane` / `opposite_track` non reconnus par `map_bike_infra` (comparaison exacte des valeurs) → `bike_road` | à faire |
| `get_bike_direction` | 39 | ne lit pas `cycleway=opposite*` : ces rues sont vues à sens unique pour les vélos dans le graphe orienté | à faire |
| Voies de bus | ~100 (25 gagnables) | `busway:*` et `bus:lanes` non lus ; 91 km sans info d'accès vélo ; ~40 km de voies bus dessinées à part, hors graphe | à trancher : accès strict ou permissif ; voies séparées hors graphe ou non |
| `cycleway=shared_lane` | 71 | classé `partage_bus`, alors que la valeur OSM désigne un marquage de chaussée partagée (pictogrammes), pas une voie bus | à vérifier |
| Bande suggérée / obligatoire | 213 renseignés | `cycleway:*:lane=advisory` (chaucidou) vs `exclusive` : tout est à 0,7 | à trancher (ex. 0,5 pour advisory) |
| Côtés de la rue | — | les côtés sont fusionnés : une bande d'un seul côté classe toute la way en `bande_cyclable` | limite connue |
| Largeur, séparation physique | 48 / ~0 | `width` sur 48 km des 330 km de `highway=cycleway` ; `cycleway:*:separation` quasi absent | non exploitable |
| Segments `footway` | ~200 | absents de `step1_all_segments` tant que `1_0` n'est pas relancé | relancer `1_0` |
| Schéma cyclable | 49 | routes encore passées en piste par le schéma, sans voie cyclable OSM à côté : à contrôler dans QGIS (aménagement réel absent d'OSM, ou décalage de tracé) | à vérifier |
