# Récapitulatif — refonte de l'indice de cyclabilité

**Date : 24.11.2026** · Période couverte : 19 au 24.11.2026 · Dépôt `projet_pieton_gg`, réseau vélo, territoire Grand Genève (GG).

Notes méthodologiques détaillées (racine du dépôt) : `attribut_infra_cyclable.md`, `attribut_coupure.md`, `attribut_vitesse_motorisee.md`, `methode_indice_hierarchise.md`.

## 1. Vue d'ensemble

| Thème | Ce qui a changé | Notebooks / fichiers |
|---|---|---|
| Infrastructure cyclable | typologie OSM refondue (11 classes), fusion avec le schéma cyclable encadrée | `0_1`, `2_1` vélo |
| Doublons parallèles | une route qui longe une voie cyclable séparée n'est plus comptée | `3_1` |
| Coupure | nouvel attribut : coupures de l'itinéraire par des routes plus intenses | `derived_attributes.py`, `2_2` |
| Vitesse motorisée | recalculée sur le graphe vélo, score par paliers (l'ancienne version était inversée) | `0_1`, `1_1`, `2_1` vélo, `2_2` |
| Stationnement | `stationnement_velo` et `parking_abris` fusionnés | `2_1` vélo, `feature_to_network.py` |
| Bruit | ajouté en confort, même méthode que la marche | `2_1` vélo |
| Attributs retirés | `sens_inverse`, `traversees`, `parking_abris` | Excel |
| Indice hiérarchisé | nouvel indice socle + bonus, en parallèle de `bike_index` | `3_1` |
| NaN | un attribut manquant ne fait plus sortir le segment de l'indice | `3_1` |
| Analyse | notebook d'analyse des poids des attributs vélo | `Step 4/analyse_poids_attributs_bike.ipynb` |

## 2. Infrastructure cyclable (`infra_cyclable`)

**Graphe vélo (`0_1`, `classify_bike`)** : les `footway` avec `bicycle=designated/yes/permissive` entrent dans le graphe (≈ 200 km jusque-là exclus).

**Typologie OSM (`0_1`, `map_bike_infra`)** — scores dans `2_1` :

| Classe | Score | Règle principale | Nouveauté |
|---|---|---|---|
| `piste_cyclable` | 1 | `highway=cycleway` séparée, `path` désigné séparé, `cycleway:*=track` | `separate` ne vaut plus piste (19.11) |
| `bande_cyclable` | 0,7 | `cycleway:*=lane` | |
| `voie_mixte` | 0,7 | `cycleway` + `segregated=no`, `path` + `bicycle=designated` | nouvelle (19.11) |
| `footway_designe` | 0,6 | `footway` + `bicycle=designated` | nouvelle (19.11) |
| `contresens` | 0,5 | `cycleway:*=opposite_lane / opposite_track` | nouvelle (23.11) |
| `partage_bus` | 0,5 | `share_busway`, `busway:*`, `bus:lanes` / `psv:lanes` | voies bus ajoutées (23.11) |
| `accotement` | 0,5 | `cycleway:*=shoulder` | nouvelle (19.11) |
| `bike_pedestrian_area` | 0,4 | `pedestrian`, `living_street`, `footway` + `bicycle=yes` | footways ajoutés |
| `partage` | 0,3 | `track`, `path`, `bridleway` | |
| `chaussee_partagee` | 0,2 | `cycleway:*=shared_lane` | nouvelle, sortie de `partage_bus` (23.11) |
| `bike_road` | 0 | autres routes | |

**Fusion avec le schéma cyclable d'agglomération (`0_1`, cellule 26)** :
- *garde sur les routes* (19.11) : le schéma ne met plus en piste une route déjà longée par une voie cyclable OSM dessinée à part (190 → 49 km de routes passées en piste par le schéma) ;
- *classes OSM protégées* (23.11) : le schéma ne surclasse plus `voie_mixte` ni `footway_designe` (≈ 90 km retrouvent leur classe OSM) ; « Site propre » reste `piste_cyclable`.

**Contrôle (`2_1`, cellule 44)** : couverture par classe en km et en % du réseau vélo (chaque voie comptée une fois). Réseau de ~13 000 km : pistes ≈ 3 %, bandes ≈ 3 %, aménagements dédiés ≈ 7,5 %.

## 3. Doublons parallèles (`3_1`)

Une route (ou un chemin) longée par une voie cyclable **dessinée à part** est retirée de l'indice, pour que le corridor ne compte qu'une fois.
- Rectangle 10 m, angle ≤ 30°, segment couvert à ≥ 80 %.
- Seuls les aménagements dédiés (score ≥ 0,5) dessinés à part (`cycleway`, `path`, `footway`…) retirent ; seuls les segments non dédiés (< 0,5) sont retirés ; entre aménagements dédiés, rien n'est retiré.
- Effet mesuré : ≈ 145 km retirés, ≈ 790 carreaux modifiés. Contrôle : `step3_doublons_paralleles.gpkg`.

## 4. Nouvel attribut `coupure`

Mesure les coupures de l'itinéraire par des routes plus intenses que celle du cycliste, à partir de `AGGLO_HIERARCHIE_ROUTE.gpkg` (primaire 1, secondaire 2, tertiaire 3 ; autoroutes et bretelles ignorées).
- Rectangle 10 m, prolongé de 10 m ; route du cycliste = morceau le plus colinéaire (|cos| ≥ 0,8), sinon hors hiérarchie (4).
- Coupures = morceaux |cos| < 0,8 d'une classe plus intense ; intensité = 1 − (1 − écart_max/3) / (1 + n/2) (défavorable).
- NaN près d'un giratoire (déjà compté par `giratoire`).
- Classe infrastructure, socle, poids 0,5. Statistiques affichées dans `2_2` (section « Contrôle coupure »).
- Premiers résultats : 6,6 % des segments coupés ; 46,5 % des segments sans route colinéaire.

## 5. Vitesse motorisée (`vitesse_motorisee`)

**Problème trouvé** : l'attribut réutilisait la vitesse du **graphe marche** (pas d'axe des primaires, rues résidentielles à 30 km/h > seuil 25). Classement inversé : rues résidentielles 0,01, primaires 0,68.

**Nouvelle méthode** :
- `1_1` (mode vélo) : vitesse par arête du graphe vélo → `vitesse_bike_edges.parquet` (le fichier marche n'est plus écrasé). Base 50/80 km/h (tache urbaine), type de route, tags de zone, `maxspeed` ; `track` 10 km/h ; voies séparées 0 km/h.
- `2_1` : score par paliers (0 → 1 ; ≤ 20 → 0,9 ; ≤ 30 → 0,8 ; ≤ 50 → 0,4 ; ≤ 80 → 0,1 ; > 80 → 0), favorable.
- `2_2` : `rectangle_weighted_mean`, 2 m.
- Résultat : rues résidentielles 0,77, primaires 0,24.
- `0_1` conserve désormais `zone:maxspeed`, `maxspeed:type`, `maxspeed:forward/backward`.
- Effet de bord corrigé : les traversées vélo lisaient la même vitesse marche (`2_2`, cellule 12, lit maintenant `vitesse_bike_edges`).

## 6. Autres attributs

| Attribut | Changement |
|---|---|
| `stationnement_velo` | fusionné avec `parking_abris` : score par parking = 0,8 × min(capacité, 20)/20 + 0,2 si abrité (`covered=yes` ou `shed`) ; agrégation `max` dans un buffer de 30 m (nouvelle méthode `max` dans `feature_to_network.py`), `clip_GG` vide |
| `bruit` | ajouté en confort, même méthode que la marche (raster ORHANE → points, `bruit_norm`, mode `raster` 100 m), `SAMPLE_STEP = 2` |
| `sens_inverse` | retiré (source Genève seulement, 88 % « Dérogation 2R », doublon avec `contresens`) |
| `traversees` | retiré de l'indice (vitesse fausse ; remplacé par `coupure`) |
| `parking_abris` | retiré (fusionné dans `stationnement_velo`) |
| `temperature` | diagnostic : l'ancien fichier (scène du 29.06.2025) ne couvrait que 79 % du GG et codait l'absence de donnée en 0 ; fichier d'entrée corrigé |

## 7. Indice hiérarchisé et NaN (`3_1`)

**`bike_index_hierarchised`** (en plus de `bike_index`, qui ne change pas) :
- `classe_socle` F = moyenne pondérée des attributs `socle = True` (actuellement `infra_cyclable`, `revetement`, `coupure`, `giratoire`, `eclairage`, `vitesse_motorisee`, `accident`) ;
- `classe_bonus` B = moyenne pondérée des autres, min-maxée ;
- indice = F si F < T, sinon F + (1 − F) × B ; rampe optionnelle δ ; `seuil_atteint` = 1 / 0 (part du réseau dans les gpkg agrégés) ;
- paramètres actuels : T = 0,5, δ = 0 ; histogramme de `classe_socle` et tableau des km au-dessus de chaque seuil.

**`NAN_POLICY = "ignore"`** : `bike_index` et les `Classe_*` sont calculés sur les attributs présents (résultat identique sans NaN). Avant, un seul NaN rendait le segment NaN.

## 8. Analyse et documentation

- `Notebook/Step 4/analyse_poids_attributs_bike.ipynb` : poids des attributs dans les classes et l'indice (distribution, contribution, variance, déficit, Spearman, pondéré vs non pondéré), plus une section sur la classe infrastructure + sécurité.
- Notes : `attribut_infra_cyclable.md`, `attribut_coupure.md`, `attribut_vitesse_motorisee.md`, `methode_indice_hierarchise.md`, et ce récapitulatif.

## 9. Fichiers modifiés

| Fichier | Modifications |
|---|---|
| `Notebook/Step 0/0_1_Load_osm_networks_and_nodes_bike_walk.ipynb` | `classify_bike`, `map_bike_infra`, `INFRA_RANK`, colonnes conservées, schéma (garde + classes protégées) |
| `Notebook/Step 1/1_1_Prepare_features.ipynb` | vitesse en mode vélo |
| `Notebook/Step 2/2_1_Filter_features_bike.ipynb` | scores infra, couverture, stationnement, vitesse, bruit |
| `Notebook/Step 2/2_2_Process_features.ipynb` | contexte des attributs dérivés, vitesse des traversées, contrôle coupure |
| `Notebook/Step 2/derived_attributes.py` | `derive_coupure` |
| `Notebook/Step 2/feature_to_network.py` | méthode d'agrégation `max` |
| `Notebook/Step 3/3_1_Compute_index.ipynb` | doublons parallèles, indice hiérarchisé, `NAN_POLICY` |
| `Data/input/network_agreg/AGGLO_HIERARCHIE_ROUTE.gpkg` | nouvelle couche |
| `Data/input/attributs/attributs_info_bike_WIP.xlsx` | modifié à la main (lignes `coupure`, `bruit`, `vitesse_motorisee`, `stationnement_velo`, colonne `socle`…) |

## 10. Points ouverts

- `conflit_md` repose encore sur le graphe marche (même biais que l'ancienne vitesse).
- Mode `raster` de `2_2` : les segments sans point dans leur buffer valent 0 (`zero_for_missing`) — « silencieux » pour le bruit, « frais » pour la température ; à corriger (marche et vélo).
- `unclassified` sans tag de vitesse : 50 / 80 km/h par défaut, peut-être trop élevé en campagne.
- `get_bike_direction` ne lit pas `cycleway=opposite*` (graphe orienté).
- `cycleway=opposite` sans marquage (≈ 18 km) non classé.
- Voies bus dessinées à part (≈ 40 km) hors graphe ; accès vélo aux voies bus supposé (option permissive).
- Bande suggérée (`advisory`) vs obligatoire : même score.
- 49 km de routes encore passées en piste par le schéma cyclable : à contrôler dans QGIS.
- Choix du seuil T de l'indice hiérarchisé à faire sur l'histogramme de `classe_socle` (pics de valeurs).

## 11. Relance complète

`0_1` → `1_0` → `1_1` (cellule Vitesse, `network = "bike"`) → `2_1` → `2_2` → `3_1` → `3_2`.

Fermer et rouvrir les notebooks dans l'éditeur avant de les lancer : à plusieurs reprises, une sauvegarde depuis une version ouverte avant une modification a écrasé celle-ci.
