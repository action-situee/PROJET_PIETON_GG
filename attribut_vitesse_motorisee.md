# Attribut `vitesse_motorisee` — méthode (indice de cyclabilité)

Vitesse du trafic motorisé sur la route où roule le cycliste, convertie en score de calme (1 = pas de voiture, 0 = plus de 80 km/h). Classe **sécurité**, attribut **socle**, **favorable**.

État au **24.11.2026**. Remplace l'ancienne version, qui réutilisait la vitesse calculée pour la marche (voir §5).

## 1. Paramètres

| Paramètre | Valeur | Où | Rôle |
|---|---|---|---|
| Graphe | `Data/input/networkGG/bike_edges_graph.parquet` | `1_1`, cellule Vitesse (`network = "bike"`) | une vitesse par arête du graphe **vélo** |
| Fichier produit | `Data/input/attributs/GG/vitesse/vitesse_bike_edges.parquet` (+ `.geojson`) | `1_1` | le fichier marche `vitesse_all_edges` n'est pas touché |
| Tache urbaine | `AGGLO_TACHE_URBAINE_2022.gpkg`, dilatée de 200 m | `TACHE_BUFFER_M` | base urbain / hors urbain |
| Vitesse de base | 50 km/h dans la tache, 80 km/h hors tache | `SPEED_URBAN_KMH`, `SPEED_RURAL_KMH` | sans autre information |
| Vitesse par type de route | `living_street` 20, `residential` 30, `service` 30 km/h | `TYPE_SPEED_KMH` | sans tag de vitesse |
| Tags de zone | `zone:maxspeed`, `maxspeed:type`, `maxspeed` texte : `…zone30` → 30, `…:urban` → 50, `…:rural` → 80, `…:living_street` → 20 | `BIKE_ZONE_TAG_COLS`, `parse_zone_speed` | |
| Vitesse explicite | `maxspeed`, `maxspeed:forward`, `maxspeed:backward` numériques ; on garde la plus élevée | `BIKE_SPEED_TAG_COLS` | écrase tout le reste |
| Chemins agricoles | `track` → 10 km/h | `TRACK_SPEED_KMH` | véhicules agricoles |
| Voies sans voiture | `cycleway`, `path`, `footway`, `pedestrian`, `bridleway`, `steps`, `corridor` → 0 km/h | `BIKE_NO_CAR_HW` | voie dessinée à part, cycliste séparé du trafic |
| Paliers de score | voir §3 | `2_1`, `VITESSE_BORNES`, `VITESSE_SCORES` | |
| Agrégation | `rectangle_weighted_mean`, demi-largeur `buffer_size_GG` | Excel | **recommandé : 2 m** (lit l'arête du segment) ; actuellement 10 m |

Ligne `vitesse_motorisee` de `attributs_info_bike_WIP.xlsx` : classe `securite`, `socle = True`, `initial_weight = 0.5`, `class_weight = 0.5`, `impact_attribut = favorable`, `source_path_GG = attributs/GG/vitesse`, `file_name_GG = vitesse_bike_edges.parquet`, `how_GG = rectangle_weighted_mean`, `value_column_GG = vitesse_score`, `geometry_type_GG = line`, `missing_value_strategy = keep_nan`, `clip_GG` vide.

## 2. Vitesse par arête (`1_1`)

Pour chaque arête du graphe vélo, la **route de référence est l'arête elle-même** (le cycliste roule dessus, y compris sur une bande ou un contresens). Les règles s'appliquent dans cet ordre, chacune écrasant la précédente :

1. **Base** : milieu de l'arête dans la tache urbaine dilatée → 50 km/h, sinon 80 km/h (`vitesse_type = zone`).
2. **Type de route** sans tag : `living_street` 20, `residential` 30, `service` 30 km/h (`type_inferred`).
3. **Tag de zone OSM** (`osm_zone_tag`).
4. **`maxspeed` numérique** : la plus élevée des valeurs générale / sens aller / sens retour (`osm_tag`).
5. **Cas particuliers** : `track` → 10 km/h ; voies dessinées à part → 0 km/h (`no_car`).

Différence avec la marche : pour un piéton, un trottoir prend la vitesse de la **chaussée voisine** (`adj_highway`, `speed_ctx_kmh` de `0_1`). Pour le vélo, il n'y a pas de recherche de route voisine ; une voie cyclable séparée est « sans voiture ».

## 3. Score par paliers (`2_1`)

| Vitesse de l'arête | Score `vitesse_score` |
|---|---|
| 0 (pas de voiture) | 1 |
| 1 à 20 km/h | 0,9 |
| 21 à 30 km/h | 0,8 |
| 31 à 50 km/h | 0,4 |
| 51 à 80 km/h | 0,1 |
| plus de 80 km/h | 0 |

Bornes hautes incluses (`pd.cut(..., right=True)`) : 40 km/h compte comme 50, un `track` à 10 km/h vaut 0,9.

Puis `2_2` lit le score des arêtes dans un rectangle autour de chaque segment (moyenne pondérée par la longueur, lignes à plus de 45° écartées). Avec 2 m, c'est le score de l'arête dont le segment est issu ; avec 10 m, une piste séparée fait la moyenne avec la route qui la longe. Dans `3_1`, min-max (sans effet notable : 0 et 1 sont présents), pas d'inversion (favorable).

## 4. Résultats (graphe vélo du 23.11, avant relance de `0_1`)

Score moyen par type de route OSM (segments `step1`, moyenne pondérée par la longueur) :

| Type de route | Rectangle 2 m | Rectangle 10 m |
|---|---|---|
| path, footway, cycleway | 0,99 – 1,00 | 0,78 – 0,99 |
| track | 0,90 | 0,90 |
| living_street | 0,89 | 0,89 |
| residential | 0,77 | 0,77 |
| unclassified | 0,36 | 0,37 |
| tertiary | 0,33 | 0,36 |
| secondary | 0,28 | 0,32 |
| primary | 0,24 | 0,30 |

Origine de la vitesse (arêtes) : `type_inferred` 41 %, `no_car` 23 %, `osm_tag` 22 %, `zone` 14 %, `osm_zone_tag` 0,1 % (les tags de zone ne sont lus qu'après relance de `0_1`).

## 5. Pourquoi l'ancienne version était à l'envers

L'ancienne version lisait `vitesse_all_edges` (vitesse calculée sur le **graphe marche**) et mesurait la part du segment longée, à moins de 10 m, par une arête marche à plus de 25 km/h (`length_ratio`), puis l'inversait (défavorable).

- Le graphe marche suit l'axe des rues résidentielles (on y marche sur la chaussée) à 30 km/h : 30 > 25, la rue est vue comme rapide, part ≈ 1, score ≈ 0.
- Il ne contient pas l'axe des primaires et secondaires (on y marche sur les trottoirs, décalés de 5 à 15 m) : part ≈ 0,2, score ≈ 0,7.

Résultat : rues résidentielles 0,01, primaires 0,68 — le classement inverse de la réalité. La même vitesse marche était utilisée par le score `traversees` vélo (jointure par `edge_id` entre deux graphes différents) : `2_2` lit désormais `vitesse_bike_edges` pour le vélo.

## 6. Limites et points ouverts

- **Rectangle de 10 m** dans l'Excel : dilue le score des voies séparées (0,995 → 0,78 pour `cycleway`). Passer `buffer_size_GG` à 2 pour appliquer pleinement le choix « 0 km/h sur les voies séparées ».
- **`unclassified`** (≈ 15 700 arêtes) : pas de règle de type ; sans tag, 50 ou 80 km/h selon la tache urbaine. Souvent des petites routes de campagne : une vitesse par défaut plus basse est à discuter.
- **Voies séparées à 0 km/h** : l'exposition au trafic voisin (bruit, carrefours) n'est pas comptée ici ; les carrefours le sont par `coupure`.
- **`maxspeed` par sens** : on retient la valeur la plus élevée (prudent).
- **`conflit_md`** est encore construit à partir du graphe marche : à revoir.

## 7. Relancer

`0_1` → `1_1` (cellule Vitesse, `network = "bike"`) → `2_1` (cellule `vitesse_motorisee`) → `2_2` → `3_1` → `3_2`. Pour recalculer la vitesse marche, repasser `network = "walk"` dans `1_1`.
