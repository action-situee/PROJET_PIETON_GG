# Methodologie des attributs issus d'OSM et du reseau

Ce document explicite les choix methodologiques des couches issues d'OpenStreetMap ou des reseaux prepares dans les notebooks du depot `projet-index-walk-bike-ge-gg`.

Il complete le `README.md` en detaillant les attributs utilises pour les indices marche et velo. Il sert aussi de base pour controler de maniere systematique les fichiers de parametrage `Data/input/attributs/attributs_info_bike.xlsx` et `Data/input/attributs/attributs_info_walk.xlsx`.

## Statut du document

Ce document est une documentation de travail avancee, mais il n'est pas exhaustif. Il couvre surtout les couches issues d'OpenStreetMap et les couches derivees du reseau. Les attributs provenant d'autres sources locales ou opendata doivent encore etre documentes avec leur source, leur millesime, leur perimetre, leur traitement et leurs limites. [À COMPLÉTER]

Les hypotheses de score, d'agregation, de buffer et de sens d'impact doivent etre relues avec les classeurs d'attributs et les notebooks avant toute diffusion publique d'un resultat.

Sources locales utilisees :

- `Notebook/Step 0/0_1_Load_osm_networks_and_nodes_bike_walk.ipynb` : construction des reseaux marche et velo, classification des liens, calcul de `conflit_md`.
- `Notebook/Step 0/0_2_Load_osm_features.ipynb` : extraction des couches OSM attributaires.
- `Notebook/Step 0/0_2_Load_osm_features_walk.ipynb` : ancienne version marche, utilisee comme reference pour certaines couches pietonnes.
- `Notebook/Step 1/1_0_Prepare_network.ipynb` : decoupage du reseau en segments de 50 m (`step1_all_segments.parquet`).
- `Notebook/Step 1/1_1_Prepare_features.ipynb` : connectivite locale, pente, couche `vitesse_all_edges` et controle des traversees.
- `Notebook/Step 2/feature_to_network.py` : logique d'agregation des attributs sur les segments (dont `count_rectangle` et `weighted_length`).
- `Notebook/Step 2/crossing_filters.py` : regles de selection des traversees (partagees entre 1_1 et 2_1).
- `Notebook/Step 2/derived_attributes.py` : attributs derives calcules apres agregation (`traversees`).
- `Notebook/Step 2/2_1_Filter_features_bike.ipynb` et `Notebook/Step 2/2_1_Filter_features_walk.ipynb` : filtres et scores avant agregation.
- `Notebook/Step 2/2_2_Process_features.ipynb` : agregation sur les segments (boucle V3) et attributs derives.
- `Data/input/attributs/attributs_info_bike.xlsx` et `Data/input/attributs/attributs_info_walk.xlsx` : parametrage aval des attributs.

## Perimetre

Sont couverts ici :

- les couches extraites directement d'OSM dans `osm_attributes.gpkg`;
- les couches derivees du reseau OSM prepare, par exemple `piste`, `bande`, `vitesse_all_edges`, `connectivite`;
- la couche `conflit_md`, calculee a partir de la relation geometrique entre reseau marche et reseau velo.

Ne sont pas documentees en detail dans cette version :

- les couches SITG/opendata non derivees d'OSM ou du reseau, par exemple `accident`, `air`, `temperature`, `largeur_trottoir`, `stationnement_genant`. Exception : `bruit`, `canopee` (GG walk) et `environnement_ouvert_naturel` sont documentes dans la section « Couches environnementales non OSM (walk GG) »;
- les ponderations finales d'indice, qui relevent des notebooks d'indexation;
- les controles de qualite exhaustifs de completude OSM.

## Principes generaux

Les extractions OSM sont faites avec `osmnx.features_from_polygon(aoi_polygon, tags)`, sur l'aire d'etude definie par `AOI_MODE`. Les geometries sont filtrees par type (`Point`, `LineString`, `Polygon`, etc.) puis exportees en `EPSG:4326`. Les calculs metriques utilisent `EPSG:2056`.

La valeur `True` dans les tags OSM signifie : recuperer tous les objets pour lesquels le tag existe. Exemple : `{"amenity": True}` recupere les objets ayant un tag `amenity`, quelle que soit sa valeur.

Les couches sont exportees dans un GeoPackage, en conservant `geometry`, un identifiant OSM si disponible (`osmid`, `id`, `fid` ou `edge_id`) et les colonnes utiles declarees dans les definitions de couche.

Les agregations aval sur le reseau utilisent principalement `extract_buffer_feature` :

- `presence` : 1 si au moins un objet intersecte le buffer du segment, sinon 0.
- `count` : nombre d'objets intersectant le buffer.
- `sum` : somme d'une colonne numerique dans le buffer.
- `mean` : moyenne d'une colonne numerique dans le buffer.
- `length_ratio` : longueur de lignes intersectant le buffer divisee par la longueur du segment, bornee entre 0 et 1.
- `area_ratio` : surface de polygones dans le buffer divisee par la surface du buffer, bornee entre 0 et 1.
- `raster` : moyenne de points echantillonnes representant une source raster.
- `count_rectangle` : nombre de points dans un rectangle oriente le long du segment (demi-largeur `buffer_size_<T>`, segment prolonge de `extend_m_<T>` a chaque bout), au lieu d'un buffer rond. Utilise pour les traversees.
- `weighted_length` : moyenne de carreaux (raster vectorise) ponderee par la longueur du segment traversee, sans buffer; valeur NaN si la part couverte est inferieure a `MIN_VALID_SHARE = 0.5`.
- `derived` : ligne sautee par la boucle d'agregation et calculee ensuite a partir de colonnes deja presentes dans `step2_features` (fonctions de `derived_attributes.DERIVED_ATTRIBUTES`).

Dans 2_2, une ligne du classeur est traitee si `include_in_index_<T> = True` ou `compute_step2_<T> = True`. Ce second drapeau sert aux comptages intermediaires qui ne vont pas dans l'indice mais alimentent un attribut derive (`n_traversees`, `n_traversees_feux`). La colonne produite s'appelle `<attribut>_<buffer>` (ex. `vitesse_10`, `traversees_10`).

Les champs `filtered` crees dans les notebooks Step 2 permettent de ne retenir que les objets pertinents pour l'attribut final. Les classeurs `attributs_info_*.xlsx` appliquent ensuite `filter_column = filtered` et `filter_values = 1` pour la plupart des attributs.

## Synthese des couches OSM directes

| Couche | Geometrie | Source | Tags principaux | Usage aval observe |
|---|---:|---|---|---|
| `borne_reparation` | point | OSM | `amenity=bicycle_repair_station` | bike, equipement, count |
| `stationnement_velo` | point | OSM | `amenity=bicycle_parking` | bike, equipement, score capacite ou parking abrite |
| `location` | point | OSM | `amenity=bicycle_rental` | bike, equipement, count |
| `service_velo` | point | OSM | `shop=bicycle` | bike, equipement, count |
| `fontaine` | point | OSM | `amenity=drinking_water|fountain` | walk, attractivite, count |
| `banc` | point | OSM | `amenity=bench` | walk, commodite, count |
| `toilette` | point | OSM | `amenity=toilets` | walk, commodite, count |
| `transport_public` | point | OSM | `highway=bus_stop`, `railway=station|halt|tram_stop`, `amenity=bus_station`, `public_transport=station` | walk, attribut `tp`, presence |
| `amenite` | point | OSM | `amenity=*` | bike/walk, filtre selon familles d'amenites |
| `barrier` | point | OSM | `barrier=*` | couche informative, accessibilite |
| `traffic_calming_point` | point | OSM | `traffic_calming=*` | couche informative, apaisement |
| `chemin` | ligne | OSM | `highway=path` | walk, infrastructure, presence |
| `revetement` | ligne | OSM | `surface=*` | bike, infrastructure, score surface |
| `etat_chaussee` | ligne | OSM | `smoothness=*` | couche informative, qualite de roulement |
| `eclairage` | ligne | OSM | `lit=*` | bike/walk, securite ou commodite |
| `largeur` | ligne | OSM | `width=*` | bike, infrastructure, encore peu exploite |
| `pente` | ligne | OSM | `incline=*` | couche OSM indicative, distincte de la pente raster/opendata |
| `giratoire` | ligne | OSM | `junction=roundabout` | bike, infrastructure, count |
| `lac_cours_deau` | ligne/polygone | OSM | `waterway=*`, `natural=water`, `water=*`, `waterway=riverbank` | bike `eau`, walk `lac_cours_deau`, presence |
| `canopee` | polygone | OSM (bike, ancien walk) | `landuse=forest`, `natural=wood` | bike area_ratio; pour walk GG, remplacee par la couverture du sol (voir fiche) |
| `espaces_ouverts` | polygone | OSM | `leisure=park|playground`, `landuse=recreation_ground`, `amenity=grave_yard` | walk, presence |
| `landuse_env` | polygone | OSM | valeurs selectionnees de `landuse=*` | bike `alentours`, area_ratio | potentiellement

## Synthese des couches reseau

| Couche | Geometrie | Source | Calcul principal | Usage aval observe |
|---|---:|---|---|---|
| `piste` | ligne | `bike_edges_graph.geojson` | filtre `infra_bike=piste_cyclable` ou tags `cycleway=*track/separated` | bike, `length_ratio` |
| `bande` | ligne | `bike_edges_graph.geojson` | filtre `infra_bike=bande_cyclable` ou tags `cycleway=*lane/advisory/shared` | bike, `length_ratio` |
| `vitesse` | ligne | `bike_edges_graph.geojson` ou OSM fallback | objets avec `maxspeed` | couche brute, distincte de `vitesse_all_edges` |
| `vitesse_all_edges` | ligne | `walk_edges_graph.geojson` + tache urbaine 2022 | `speed_kph` : zone urbaine/rurale, puis type de route de reference, puis `maxspeed` propre ou de la chaussee adjacente, puis cas sans voiture | walk, attribut `vitesse` (`mean`, 10 m), zones apaisees, besoin en traversees |
| `zone_apaisee` | ligne | `vitesse_all_edges` (bike); SITG (walk GE) | bike : filtre `5 < speed_kph < 30`; GE : `TYPE_LIMIT` zone 30 / prescription 30 ou 20 km/h | bike, walk GE, favorable; retire pour walk GG |
| `vitesse_motorisee` | ligne | `vitesse_all_edges` | filtre `speed_kph > 25` | bike, defavorable |
| `zone_pietonne` | polygone | GE : SITG uniquement | filtre `TYPE_ZONE` = « Zone pietonne » ou « Zone de rencontre (20) » | walk GE, favorable; retire pour GG |
| `n_traversees` / `n_traversees_feux` | point | `walk_crossing_nodes.parquet` (0_1) | traversees retenues par `crossing_filters.py`, comptees dans un rectangle | walk GG, intermediaire (`compute_step2`) |
| `traversees` | ligne (derive) | `n_traversees_10`, `n_traversees_feux_10`, vitesse de l'arete | `1 - besoin x (1 - offre)` | walk GG, favorable |
| `connectivite` | ligne | segment de reseau | `conn_branching_in_buffer` dans un buffer local | bike/walk, favorable |
| `conflit_md` | point | croisement reseau marche/reseau velo | intersections et espaces partages, score de severite | bike/walk, defavorable |

## Fiches methodologiques

### `borne_reparation`

Source : OSM.

Tags : `amenity=bicycle_repair_station`.

Hypothese : la presence d'une borne de reparation constitue une ressource favorable pour la cyclabilite, surtout a proximite immediate ou moyenne du segment.

Colonnes conservees : `amenity`, `access`.

Filtrage aval : tous les objets sont conserves (`filtered = 1`).

Agregation observee dans `attributs_info_bike.xlsx` : point, `count`, buffer 50 m, impact favorable.

Limites : depend fortement de la contribution OSM; la qualite effective de l'equipement n'est pas controlee.

### `stationnement_velo`

Source : OSM.

Tags : `amenity=bicycle_parking`.

Hypothese : la presence de stationnement velo est favorable. La capacite renseignee peut servir de score lorsqu'elle existe.

Colonnes conservees : `amenity`, `access`, `capacity`, `covered`, `bicycle_parking`.

Filtrage aval : tous les objets sont conserves pour `stationnement_velo`. Le champ `capacity` est converti en `capacity_num`; le score vaut `capacity_num`, avec fallback a 1 si la capacite manque ou vaut 0.

Cas derive : `parking_abris` utilise la meme couche source, avec filtre `covered == "yes"`.

Agregation observee : point, `sum` de `score`, buffer 30 m pour `stationnement_velo`; point, `count`, buffer 25 m pour `parking_abris`.

Limites : `capacity` et `covered` sont souvent incomplets dans OSM; les stationnements prives peuvent etre inclus si `access` n'est pas renseigne ou filtre.

### `location`

Source : OSM.

Tags : `amenity=bicycle_rental`.

Hypothese : les services de location velo renforcent l'attractivite ou l'equipement cyclable.

Colonnes conservees : `amenity`, `operator`.

Filtrage aval : tous les objets sont conserves.

Agregation observee : point, `count`, buffer 100 m, impact favorable.

Limites : ne distingue pas toujours les stations publiques, les commerces prives ou les services occasionnels.

### `service_velo`

Source : OSM.

Tags : `shop=bicycle`.

Hypothese : les commerces et services velo sont favorables a l'usage cyclable.

Colonnes conservees : `shop`, `name`, `operator`, `service:bicycle:repair`, `service:bicycle:sales`, `service:bicycle:rental`, `service:bicycle:pump`.

Filtrage aval : tous les objets sont conserves.

Agregation observee : point, `count`, buffer 25 m, impact favorable.

Limites : la couche ne verifie pas l'etendue effective des services; certains magasins peuvent vendre des velos sans offrir de reparation.

### `fontaine`

Source : OSM.

Tags : `amenity=drinking_water` ou `amenity=fountain`.

Hypothese : les points d'eau ou fontaines ameliorent le confort pieton, surtout en situation de chaleur ou de parcours longs.

Colonnes conservees : `amenity`, `name`, `operator`, `access`.

Filtrage aval : tous les objets sont conserves.

Agregation observee dans `attributs_info_walk.xlsx` : point, `count`, buffer 50 m, impact favorable.

Limites : `fountain` ne garantit pas toujours l'eau potable; `drinking_water` est plus explicite. Un filtrage plus strict pourrait separer les deux cas.

### `banc`

Source : OSM.

Tags : `amenity=bench`.

Hypothese : les bancs soutiennent la marchabilite, notamment pour les personnes a mobilite reduite, les personnes agees ou les parcours d'attente.

Colonnes conservees : `amenity`, `backrest`, `covered`.

Filtrage aval : tous les objets sont conserves.

Agregation observee : point, `count`, buffer 10 m, impact favorable.

Limites : OSM ne garantit ni l'etat, ni l'accessibilite, ni l'ombre effective.

### `toilette`

Source : OSM.

Tags : `amenity=toilets`.

Hypothese : les toilettes accessibles augmentent le confort et l'autonomie pietonne.

Colonnes conservees : `amenity`, `access`, `wheelchair`, `fee`, `opening_hours`.

Filtrage aval : tous les objets sont conserves.

Agregation observee : point, `count`, buffer 10 m, impact favorable.

Limites : l'ouverture, le cout, l'accessibilite PMR et la qualite sont partiellement renseignes seulement.

### `transport_public` / attribut `tp`

Source : OSM.

Tags : `highway=bus_stop`, `railway=station|halt|tram_stop`, `amenity=bus_station`, `public_transport=station`.

Hypothese : la proximite d'un arret ou d'une station de transport public renforce l'accessibilite pietonne.

Geometrie : points; les stations cartographiees comme polygones sont converties en `representative_point`.

Colonnes conservees : `highway`, `railway`, `amenity`, `public_transport`, `name`, `operator`, `network`, `ref`, `wheelchair`, `shelter`, `bench`.

Filtrage aval : tous les objets sont conserves.

Agregation observee : attribut final `tp`, point, `presence`, buffer 150 m, impact favorable.

Limites : ne mesure pas la frequence, les destinations desservies, l'accessibilite horaire ou la qualite de l'arret.

### `amenite`

Source : OSM.

Tags : `amenity=*`.

Hypothese : les amenites constituent des destinations ou services qui augmentent l'attractivite d'un environnement de marche ou de velo. La couche brute est volontairement large; le sens analytique vient du filtrage aval.

Colonnes conservees : `amenity`, `name`, `operator`, `access`.

Filtrages aval observes :

- attribut bike `amenite` : conserve notamment `restaurant`, `cafe`, `bar`, `pub`, `fast_food`, `ice_cream`, `biergarten`, `bank`, `atm`, `bureau_de_change`, `cinema`, `theatre`, `nightclub`, `casino`, `marketplace`, `vending_machine`;
- attribut walk `amenite` : conserve notamment sante, education, culture, culte, services publics et certains equipements sociaux (`hospital`, `clinic`, `doctors`, `dentist`, `pharmacy`, `school`, `library`, `museum`, `place_of_worship`, `police`, etc.);
- attribut walk `rez_actif` : conserve une famille plus orientee rez-de-chaussee actif (`restaurant`, `cafe`, `bar`, `pub`, `fast_food`, `bank`, `atm`, `cinema`, `theatre`, `marketplace`, etc.).

Agregations observees : point, `count`, buffer 75 m pour `amenite`; point, `count`, buffer 50 m pour `rez_actif`.

Limites : OSM ne donne pas toujours l'etage, l'ouverture effective ou le caractere actif de facade. Les listes de valeurs doivent etre stabilisees et documentees dans les classeurs.

### `crossing`

Source : OSM.

Tags : `crossing=*`.

Hypothese : les passages pietons sont des elements structurants de franchissement et de securite.

Colonnes conservees : `crossing`, `crossing:markings`, `crossing:signals`.

Usage actuel : couche informative extraite dans `0_2`. L'attribut `traversees` de l'indice marche ne l'utilise pas : il part des noeuds `highway=crossing` exportes par `0_1` (`walk_crossing_nodes.parquet`), voir la fiche `traversees` plus bas. Les traversees synthetiques (aretes du reseau creees depuis ces noeuds) sont desactivees dans `0_1` (`add_crossing_edges = False`).

Limites : les traverses marquees au sol peuvent etre incompletes dans OSM; la qualite et la regulation du franchissement ne sont pas deduites automatiquement.

### `traffic_signals`

Source : OSM.

Tags : `highway=traffic_signals`.

Hypothese : les feux de signalisation indiquent des intersections regulees, utiles pour interpreter la securite et les discontinuites.

Colonnes conservees : `highway`, `button_operated`, `tactile_paving`.

Usage actuel : couche informative; peut enrichir les noeuds du graphe.

Limites : ne distingue pas toujours le mode concerne ni les phases de feu.

### `barrier`

Source : OSM.

Tags : `barrier=*`.

Hypothese : les barrieres, bornes et obstacles peuvent affecter la continuite ou l'accessibilite.

Colonnes conservees : `barrier`, `access`, `bicycle`, `wheelchair`.

Usage actuel : couche informative; pas encore pleinement integree comme attribut final d'indice.

Limites : l'impact depend fortement du type de barriere et des droits d'acces.

### `traffic_calming_point`

Source : OSM.

Tags : `traffic_calming=*`.

Hypothese : les dispositifs ponctuels d'apaisement signalent un environnement routier potentiellement plus favorable aux modes actifs.

Colonnes conservees : `traffic_calming`.

Usage actuel : couche informative.

Limites : ne remplace pas une couche officielle de moderation du trafic; les dispositifs peuvent etre incomplets ou heterogenes.

### `chemin`

Source : OSM pour GG; sources SITG possibles pour GE selon `attributs_info_walk.xlsx`.

Tags OSM : `highway=path`.

Hypothese : les chemins et sentiers constituent des supports de marche distincts du reseau routier ordinaire.

Colonnes conservees : `highway`.

Filtrage aval GG : `highway == "path"`.

Agregation observee walk : ligne, `presence`, buffer 1 m, impact favorable.

Limites : `path` peut couvrir des situations tres differentes : sentier, chemin non revetu, liaison mixte, chemin rural. Il faudrait documenter separement l'effet de `surface`, `smoothness`, `segregated` et `bicycle`.

### `revetement`

Source : OSM.

Tags : `surface=*`.

Hypothese : les surfaces lisses et dures sont favorables a la cyclabilite; les surfaces non revetues ou irregulieres sont moins favorables.

Colonnes conservees : `surface`.

Score aval `surface_score` :

- 1 : `asphalt`, `concrete`, `concrete:plates`, `concrete:lanes`;
- 0 : `paved`, `paving_stones`, `sett`, `metal`, `wood`, `fine_gravel`, `compacted`, `gravel`, `pebblestone`, `ground`, `dirt`, `earth`, `grass`, `grass_paver`, `sand`, `rock`, `unpaved`, `woodchips`.

Filtrage aval : seuls les objets avec `surface_score == 1` sont retenus.

Agregation observee bike : ligne, `sum` de `surface_score`, buffer 10 m, impact favorable.

Limites : la distinction actuelle est stricte. `paved` est mis a 0 alors qu'il peut etre favorable dans certains contextes; ce choix devrait etre confirme.

### `etat_chaussee`

Source : OSM.

Tags : `smoothness=*`.

Hypothese : `smoothness` renseigne la praticabilite et le confort de roulement.

Colonnes conservees : `smoothness`.

Usage actuel : couche extraite mais pas identifiee comme attribut final dans les deux classeurs inspectes.

Limites : couverture OSM souvent faible; necessite une table de correspondance vers un score avant integration dans l'indice.

### `eclairage`

Source : OSM.

Tags : `lit=*`.

Hypothese : l'eclairage public est favorable au sentiment de securite et a la praticabilite nocturne.

Colonnes conservees : `lit`.

Filtrage aval bike : `lit == "yes"`.

Filtrage aval walk : dans le notebook walk actuel, tous les objets charges sont conserves; a harmoniser avec le filtrage bike si l'objectif est de ne garder que `lit=yes`.

Agregations observees : bike ligne `length_ratio`, buffer 10 m; walk ligne `presence`, buffer 10 m. Impact favorable.

Limites : `lit=yes` ne mesure ni intensite, ni regularite, ni qualite de l'eclairage. Les valeurs `automatic`, `limited`, `no` ou non renseignees doivent etre traitees explicitement si disponibles.

### `largeur`

Source : OSM.

Tags : `width=*`.

Hypothese : une largeur plus importante peut etre favorable, sous reserve de savoir si elle decrit la chaussee, le chemin, la bande cyclable ou un trottoir.

Colonnes conservees : `width`.

Usage actuel : couche extraite; attribut bike `largeur` present dans le classeur mais `include_in_index=false` et commentaire "peu d'info".

Limites : semantique variable selon le type de voie; couverture probablement insuffisante pour un score robuste sans nettoyage approfondi.

### `pente`

Source OSM directe : `incline=*`.

Hypothese : les pentes fortes sont defavorables a la marche et au velo.

Colonnes conservees : `incline`.

Important : le `pente` OSM de `0_2` est indicatif. Dans les classeurs, l'attribut final `pente` pointe plutot vers une source topographique/raster (`pente_2056.tif`) ou une couche reseau preparee selon le territoire.

Limites : `incline=*` est tres incomplet dans OSM et peut etre exprime en pourcentage, degres ou valeurs textuelles (`up`, `down`). La pente fiable doit rester calculee a partir d'un MNT ou d'une couche topographique controlee.

### `giratoire`

Source : OSM.

Tags : `junction=roundabout`.

Hypothese : les giratoires constituent des configurations potentiellement defavorables ou complexes pour les cyclistes.

Colonnes conservees : `junction`.

Filtrage aval : tous les objets sont conserves.

Agregation observee bike : ligne, `count`, buffer 20 m, impact defavorable.

Limites : ne distingue pas les giratoires avec amenagement cyclable, les mini-giratoires, les priorites ou les vitesses d'approche.

### `lac_cours_deau` / attribut bike `eau`

Source : OSM.

Tags lignes : `waterway=river|stream|canal|ditch|flowline`.

Tags polygones : `natural=water`, `water=river|lake|pond|reservoir|lagoon`, `waterway=riverbank`.

Hypothese : les plans d'eau et cours d'eau sont des elements d'attractivite, de confort paysager et parfois de fraicheur.

Colonnes conservees : `natural`, `water`, `name`, `waterway`.

Filtrage aval GG : tous les objets sont conserves.

Agregations observees : bike attribut `eau`, polygone `presence`, buffer 50 m; walk attribut `lac_cours_deau`, polygone `presence`, buffer 50 m.

Limites : melange lignes et polygones; les petits fosses ou canaux techniques peuvent etre inclus si `waterway` est present.

### `canopee`

Source : OSM.

Tags : `landuse=forest`, `natural=wood`.

Hypothese : les zones boisees sont un proxy de canopee, d'ombre et de confort thermique.

Colonnes conservees : `landuse`, `natural`, `name`.

Filtrage aval : tous les objets sont conserves.

Agregations observees : polygone, `area_ratio`, buffer 25 m bike.

Limites : ne mesure pas la canopee urbaine fine, les arbres d'alignement ou l'ombre effective. Les couches SITG de canopee sont plus appropriees lorsqu'elles existent.

Mise a jour walk GG : l'attribut walk `canopee` ne vient plus d'OSM mais d'un GeoPackage de couverture du sol. Voir la fiche `canopee` (walk GG) dans la section « Couches environnementales non OSM (walk GG) ».

### `espaces_ouverts`

Source : OSM pour GG; source SITG possible pour GE dans le classeur walk.

Tags OSM : `leisure=park|playground`, `landuse=recreation_ground`, `amenity=grave_yard`.

Hypothese : les parcs, places de jeux, terrains de recreation et cimetieres accessibles constituent des espaces ouverts favorables a la marche.

Colonnes conservees : `leisure`, `landuse`, `amenity`, `name`, `access`, `operator`, `ownership`.

Filtrage aval GG : tous les objets sont conserves.

Agregation observee walk : polygone, `presence`, buffer 1 m, impact favorable.

Limites : `amenity=grave_yard` est inclus comme espace ouvert potentiellement vert, mais son accessibilite et son usage ne sont pas equivalents a un parc. Le champ `access` devrait etre exploite pour exclure certains espaces non accessibles.

### `landuse_env` / attribut bike `alentours`

Source : OSM.

Tags : `landuse=forest|grass|meadow|recreation_ground|residential|cemetery|allotments|commercial|retail|industrial|construction|railway`.

Hypothese : l'environnement immediat du segment influe sur le confort et l'attractivite. Dans l'etat actuel, seules certaines valeurs agreables sont retenues pour l'attribut `alentours`.

Colonnes conservees : `landuse`, `name`.

Filtrage aval `alentours` : conserve `forest`, `grass`, `meadow`, `recreation_ground`.

Agregation observee bike : polygone, `area_ratio`, buffer 50 m, impact favorable.

Limites : les classes defavorables (`industrial`, `construction`, `railway`, etc.) sont extraites mais non utilisees dans ce filtrage favorable. Une version plus complete pourrait produire deux scores distincts : environnement favorable et environnement defavorable.

## Reseaux marche et velo

### Construction generale

Le notebook `0_1_Load_osm_networks_and_nodes_bike_walk.ipynb` telecharge les ways OSM avec `highway=*` dans l'aire d'etude et les noeuds `highway=crossing`. Les ways sont ensuite classes pour construire un reseau marche et un reseau velo.

Les operations de consolidation sont faites en `EPSG:2056` :

- explosion des multilignes;
- calcul de `len_m`;
- simplification optionnelle;
- deduplication geometrique;
- export des noeuds, aretes et graphes.

### Classification marche

Classes principales :

- `walk_dedicated` : `highway` dans `footway`, `pedestrian`, `steps`, `corridor`, `platform`;
- `walk_path` : `highway=path`;
- `walk_proxy_sidewalk` : axe routier avec trottoir explicite (`sidewalk=*` ou `footway=sidewalk`);
- `walk_proxy_zone20` : axe routier en zone 20 ou avec `maxspeed <= 20`;
- `crossing_synthetic` : traversee synthetique creee depuis les noeuds `highway=crossing`;
- `platform_edge` : limite de polygone `public_transport=platform` convertie en ligne.

Dans la version actuelle, un filtre supprime certains `sidewalk_proxy_road_axis` redondants avec des liens `walk_dedicated` proches :

- buffer autour des lignes dediees : 12 m;
- longueur minimale couverte : 20 m;
- ratio minimal couvert : 0.65;
- longueur minimale des lignes dediees candidates : 8 m.

Hypothese : les axes proxy sont utiles la ou le trottoir n'est pas cartographie comme ligne dediee, mais ils deviennent des doublons si un cheminement pieton dedie colineaire ou quasi colineaire existe a proximite.

Limites : le filtre est geometrique; il ne verifie pas la lateralisaton exacte, la topologie fine, ni l'existence d'obstacles entre l'axe routier et le cheminement dedie.

### Classification velo

Classes principales :

- `bike_cycleway` : `highway=cycleway`;
- `bike_track` : tags `cycleway`, `cycleway:left`, `cycleway:right` ou `cycleway:both` contenant `track` ou `separated`;
- `bike_lane` : tags `cycleway*` contenant `lane` ou `advisory`;
- `bike_shared` : tags `cycleway*` contenant `shared`;
- `bike_path` ou `bike_path_designated` : `highway=path|track|bridleway`, selon `bicycle`;
- `bike_pedestrian_area` : `highway=pedestrian` avec `bicycle=yes|designated|permissive`;
- `bike_road` : voirie routiere partagee lorsque le velo n'est pas explicitement exclu;
- `bike_busway` : `highway=bus_guideway` avec acces velo explicite.

Mapping final `infra_bike` :

- `piste_cyclable` : `bike_cycleway`, `bike_track`;
- `bande_cyclable` : `bike_lane`, `bike_shared`;
- `chemin` : `bike_path`, `bike_path_designated`;
- `voie_spéciale` : `bike_pedestrian_area`, `bike_busway`;
- `sur_chaussée` : `bike_road`;
- `inconnu` : autres cas.

Le sens velo `bike_direction` priorise `oneway:bicycle`, puis `oneway`, avec valeurs `oneway`, `reverse` ou `both`.

## Couches reseau derivees

### `piste`

Source preferee : `bike_edges_graph.geojson`, produit par `0_1`.

Filtre dans `0_2` :

- `infra_bike == "piste_cyclable"`;
- ou `highway == "cycleway"`;
- ou tags `cycleway`, `cycleway:left`, `cycleway:right`, `cycleway:both` contenant `track` ou `separated`.

Fallback OSM possible mais desactive par defaut dans `0_2` (`ALLOW_OSM_API_FALLBACK = False`).

Agregation observee bike : ligne, `length_ratio`, buffer 10 m, impact favorable.

Limites : depend de la classification amont `infra_bike`; les tags OSM heterogenes peuvent rendre la distinction piste/bande incertaine.

### `bande`

Source preferee : `bike_edges_graph.geojson`.

Filtre dans `0_2` :

- `infra_bike == "bande_cyclable"`;
- ou tags `cycleway`, `cycleway:left`, `cycleway:right`, `cycleway:both` contenant `lane`, `advisory` ou `shared`.

Agregation observee bike : ligne, `length_ratio`, buffer 10 m, impact favorable.

Limites : `shared` est classe avec les bandes dans la logique actuelle. Ce choix peut etre discute, car une voie partagee n'offre pas toujours le meme niveau de protection qu'une bande marquee.

### `vitesse` et `vitesse_all_edges`

Deux couches doivent etre distinguees.

`vitesse` dans `0_2` :

- source preferee : `bike_edges_graph.geojson`;
- filtre : presence de `maxspeed`;
- tags de fallback OSM : `maxspeed=*`;
- colonnes conservees : `highway`, `maxspeed`, `source:maxspeed`, `name`;
- couche brute uniquement : elle n'alimente pas l'attribut walk `vitesse`, qui part de `vitesse_all_edges`.

`vitesse_all_edges` dans Step 1 (`1_1_Prepare_features.ipynb`, section « Vitesse ») :

- source : `walk_edges_graph.geojson` (reseau marche de `0_1`), plus la tache urbaine 2022 (`AGGLO_TACHE_URBAINE_2022.gpkg`) dilatee de 200 m (`TACHE_BUFFER_M`);
- sortie : `Data/input/attributs/GG/vitesse/vitesse_all_edges.geojson` et `.parquet`, une ligne par arete du reseau marche;
- colonnes principales : `speed_kph` (vitesse retenue), `vitesse_type` (origine de la valeur), `ref_highway`, `adj_highway`, `adj_dist_m`, `speed_ctx_kmh`, `in_tache_urbaine`.

Preparation dans `0_1` (vitesse de contexte) :

- chaque segment pieton est rattache a la chaussee la plus proche (`sjoin_nearest` depuis son milieu, distance maximale 15 m) parmi les `highway` routiers (`motorway` a `service`, y compris `*_link`, `living_street`);
- la vitesse d'une chaussee est lue dans `maxspeed`, puis `zone:maxspeed`, puis `maxspeed:type` (premier nombre trouve, ex. `CH:zone30 -> 30`; `none`, `signals`, `variable` -> vide);
- `speed_ctx_kmh` = vitesse propre de l'arete si c'est un axe routier proxy (`walk_class = sidewalk_proxy_road_axis`), sinon vitesse de la chaussee adjacente.

Regles appliquees dans l'ordre (une regle ecrase la precedente) :

1. Zone : milieu de l'arete dans la tache urbaine dilatee -> 50 km/h, sinon 80 km/h (`vitesse_type = zone`).
2. Type de route de reference : l'arete elle-meme pour un axe proxy, sinon la chaussee adjacente. `living_street = 20`, `residential = 30`, `service = 30` km/h (`type_inferred`).
3. Vitesse explicite : `speed_ctx_kmh > 0` ecrase le reste (`osm_tag` pour un axe proxy, `osm_tag_adjacent` pour un trottoir ou un chemin le long d'une chaussee).
4. Pas de voiture : arete `highway = pedestrian|corridor`, ou arete non proxy sans chaussee a moins de 15 m -> 0 km/h (`no_car`). Exception : un `track` isole recoit 10 km/h (`type_inferred`, vehicules agricoles).

Repartition observee pour GG (aretes / longueur) : `type_inferred` 58.5 % / 54.5 %, `osm_tag` 12.4 % / 9.1 %, `no_car` 11.6 % / 19.3 %, `osm_tag_adjacent` 9.9 % / 5.5 %, `zone` 7.7 % / 11.5 %. Aucune arete sans `speed_kph`. Les aretes notees par la zone sont surtout des `unclassified`, `tertiary` et `track` sans tag de vitesse.

Changements par rapport a la version precedente :

- la source est le reseau marche, et non plus `bike_edges_graph.geojson`;
- plus de conversion mph ni de fallback final a 30 km/h; la valeur par defaut depend de la tache urbaine (50/80 km/h);
- les trottoirs et chemins prennent la vitesse de la chaussee voisine au lieu d'une valeur fixe par type de cheminement (`footway/path/steps = 5`);
- les espaces sans voiture valent 0 km/h et sont reperes par `vitesse_type = no_car`.

Attribut walk `vitesse` (GG) :

- filtrage aval (`2_1`) : tous les objets sont conserves (`filtered = 1`);
- source (classeur) : `attributs/GG/vitesse/vitesse_all_edges.geojson`;
- agregation (`2_2`) : ligne, `mean` de `speed_kph` (`value_column_GG`), buffer 10 m, colonne `vitesse_10`;
- impact : defavorable (plus la vitesse est elevee, moins le segment est favorable a la marche);
- parametres d'etape 3 dans le classeur : `clip_GG = 50`, `missing_value_strategy = keep_nan`; classe « Securite », `class_weight = 0.5`.

Pour GE, l'attribut `vitesse` vient d'une couche SITG, filtree sur `TYPE_ZONE == 0`.

Attributs derives :

- `zone_apaisee` : retire pour walk GG (l'effet de la vitesse est porte par l'attribut `vitesse` et par `traversees`). Reste pour walk GE (SITG, `TYPE_LIMIT` = « Zone 30 km/h », « Prescription 30 km/h » ou « Prescription 20 km/h ») et pour bike;
- `vitesse_motorisee` : filtre actuel `speed_kph > 25`;
- `zone_pietonne` : retire pour GG (plus d'attribut ni de couche). Reste disponible pour GE uniquement (SITG, `TYPE_ZONE` = « Zone pietonne » ou « Zone de rencontre (20) »);
- besoin en traversees : la vitesse de l'arete sert a calculer le score `traversees` (voir fiche suivante).

Limites : la vitesse issue de la zone ou du type de route est une approximation de la vitesse reglementaire, pas de la vitesse pratiquee. Le rattachement a la chaussee la plus proche (15 m) peut se tromper de voie aux carrefours ou pour un chemin entre deux routes. La tache urbaine dilatee de 200 m classe en 50 km/h des routes peri-urbaines qui peuvent etre a 60 ou 80 km/h.

### `traversees` (walk GG)

Sources :

- noeuds OSM `highway=crossing` telecharges dans `0_1` et exportes en `walk_crossing_nodes.parquet`;
- vitesse par arete `vitesse_all_edges.parquet` (jointure par `edge_id`).

Hypothese : le besoin en traversees amenagees depend de la vitesse du trafic le long du segment. Sur un espace sans voiture, il n'y a pas de besoin; le long d'une route rapide, l'absence de traversee est fortement penalisante. Sur les routes a trafic soutenu, une traversee a feux vaut plus qu'une traversee simple.

Chaine de calcul :

1. `2_1` : les memes points sont enregistres deux fois avec un champ `filtered` different (les points non retenus restent dans le fichier avec `filtered = 0`, pour controle dans QGIS) :
   - `n_traversees` : `filtered = 1` si la traversee est retenue (`CROSSING_VALUES_KEPT`);
   - `n_traversees_feux` : `filtered = 1` si elle est retenue et a feux (`SIGNAL_RULES`).
   Les regles sont dans `crossing_filters.py`. Pour GG, 17 153 traversees sur 17 168 sont retenues, dont 1 820 a feux. Valeurs du tag `crossing` observees : `uncontrolled` 8 168, sans valeur 2 621, `marked` 2 280, `unmarked` 2 079, `traffic_signals` 1 820, `zebra` 185, `informal` 11, `pavement` 2, autres 2. 
   Regles de `crossing_filters.py` (definies uniquement dans ce fichier, partage par 1_1 et 2_1) :
   - `CROSSING_VALUES_KEPT = traffic_signals, uncontrolled, marked, zebra, unmarked`, plus les noeuds sans tag `crossing` (`None`);
   - `SIGNAL_RULES` : une traversee est a feux si `crossing = traffic_signals`;
   - une valeur OSM en liste est reduite a sa premiere valeur; la comparaison est exacte (pas de decoupage sur `;`).
   Les 15 points exclus pour GG sont `informal` (11), `pavement` (2), `island` (1) et `uncontrolled;traffic_signals` (1).
2. `2_2`, boucle V3 : comptage par segment avec `how = count_rectangle`. Le rectangle a une demi-largeur de 10 m (`buffer_size_GG`) et le segment est prolonge de 5 m a chaque bout (`extend_m_GG`). Colonnes `n_traversees_10` et `n_traversees_feux_10`. Ces deux lignes ont `include_in_index_GG = False` et `compute_step2_GG = True`.
3. `2_2`, section « Attributs derives » : `traversees_10 = 1 - besoin x (1 - offre)`, calcule par `crossing_score_table` (`derived_attributes.py`). Si la vitesse est inconnue, le score reste NaN. Colonnes annexes : `traversees_10_offre`, `traversees_10_besoin`, `traversees_10_vitesse_classe`.

Vitesse utilisee (`SPEED_SOURCE`) : par defaut `"edge"`, soit la vitesse propre de l'arete du segment. L'option `"attribute"` utilise `vitesse_10` (moyenne dans un buffer).

Classes de vitesse (`speed_class`, `pd.cut` avec `SPEED_BINS = [-inf, 10, 30, 50, inf]`, bornes droites incluses) et besoin (`BESOIN_BY_CLASS`) :

| Classe | Vitesse (km/h) | Besoin | Segments GG | Score moyen |
|---|---|---:|---:|---:|
| `no_car` | <= 10 | 0 | 171 021 | 1.000 |
| `slow_cars` | ]10, 30] | 0.3 | 262 067 | 0.735 |
| `normal` | ]30, 50] | 0.7 | 88 048 | 0.387 |
| `intense` | > 50 | 1 | 15 598 | 0.045 |

`no_car` regroupe les espaces sans voiture (0 km/h) et les `track` isoles (10 km/h). Les rues a 30 km/h sont en `slow_cars`, les rues a 50 km/h en `normal`.

Offre (`compute_crossing_score`) :

- `no_car` et `slow_cars` : 1 des qu'il y a au moins une traversee dans le rectangle, sinon 0 (pas de bonus pour les feux);
- `normal` et `intense` : 1 si au moins une traversee a feux, 0.5 si seulement des traversees sans feux, 0 si aucune traversee.

Score : `traversees = 1 - besoin x (1 - offre)`. Il vaut 1 quand il n'y a pas de besoin ou quand l'offre est complete, et `1 - besoin` sans traversee (0.7 en `slow_cars`, 0.3 en `normal`, 0 en `intense`). Exemples : une route a 50 km/h avec un passage pieton sans feux obtient `1 - 0.7 x 0.5 = 0.65`; une route a 60 km/h dans le meme cas obtient 0.5.

Valeurs manquantes : une vitesse inconnue donne une classe NaN, donc besoin, offre et score NaN (jamais remplaces par 0; `missing_value_strategy = keep_nan` dans le classeur). Dans le classeur : classe « Infrastructure », impact favorable, `class_weight = 0.5`. Pour GG, aucun segment n'est concerne. 50 987 segments ont au moins une traversee dans leur rectangle.

Parametrage : les seuils, les besoins et la regle d'offre se reglent dans `derived_attributes.py` (`SPEED_BINS`, `BESOIN_BY_CLASS`, bloc « SCORE TRAVERSEES »). Le meme code sert au controle de `1_1` et au calcul de `2_2`. Un nouvel attribut derive s'ajoute en ecrivant une fonction `f(features, ctx)` et en l'enregistrant dans `DERIVED_ATTRIBUTES`, avec `how_<T> = derived` dans le classeur.

Controle : `1_1` (section « Traversees : controle ») recalcule les memes comptages avec un `sjoin` `within` et les memes regles, et exporte `Data/output/{network}/{territory}/traversees_control/` (table par segment, segments, rectangles, traversees retenues). La comparaison en fin de `2_2` donne 0 difference sur `n_traversees`, `n_traversees_feux` et `traversees`. Des ecarts restent possibles pour une traversee posee exactement sur le bord d'un rectangle (`intersects` en 2_2, `within` en 1_1).

Limites :

- une traversee OSM sans tag `crossing` (2 621 noeuds pour GG) est comptee comme une traversee ordinaire;
- les feux ne sont reconnus que par `crossing = traffic_signals` : un noeud a feux tague autrement (`crossing:signals = yes`, `crossing = uncontrolled;traffic_signals`, ou feu porte par un noeud `highway=traffic_signals` voisin) n'est pas compte comme traversee a feux, voire est exclu (cas du point `uncontrolled;traffic_signals`);
- `island` designe un ilot de traversee, souvent sur une traversee valable : son exclusion est a confirmer (1 point pour GG);
- l'offre ne tient pas compte de la qualite (ilot, abaissement de trottoir, visibilite) ni du cote de la route;
- le rectangle de 10 m peut capter une traversee d'une rue perpendiculaire proche;
- routine implementee pour GG uniquement.

### `connectivite`

Source : reseau segmente prepare.

Calcul : `compute_connectivity_metrics` calcule les degres de noeuds du graphe et des indicateurs locaux dans un buffer.

Dans `1_1_Prepare_features.ipynb`, le calcul observe utilise :

- buffer : 35 m;
- graphe non oriente;
- metrique principale : `conn_branching_in_buffer`;
- `conn_branching_in_buffer` : somme des `max(degree - 2, 0)` pour les noeuds situes dans le buffer du segment;
- normalisation min-max puis decalage vers une plage positive;
- les impasses (`conn_deadend_flag`) sont forcees a 0 pour le score final.

Agregation observee dans les classeurs : ligne, `sum` de `conn_branching_in_buffer`, buffer 10 m bike et 7 m walk selon les tables inspectees, impact favorable.

Hypothese : un segment proche de plusieurs embranchements offre plus d'alternatives cheminatoires et donc une meilleure connectivite locale.

Limites : l'indicateur mesure la structure geometrique/topologique du reseau, pas la continuite qualitative, les temps d'attente, les barrieres ou la lisibilite.

### `conflit_md`

Source : couche preparee `pedestrian_bike_conflicts.geojson`, exportee ensuite comme layer `conflit_md` dans `0_2`.

Le calcul n'est pas refait dans `0_2`; il est produit dans `0_1` par `detect_pedestrian_bike_conflicts(walk_edges_gdf_graph, bike_edges_gdf_graph, operation_crs)`.

Methode :

1. conversion des reseaux marche et velo en CRS metrique;
2. recherche d'intersections geometriques entre les aretes velo et les aretes marche;
3. si l'intersection est un point : creation d'un conflit `conflict_type = "intersection"`;
4. si l'intersection est lineaire : creation d'un conflit `conflict_type = "shared_space"` avec geometrie au centroide de l'intersection;
5. ajout d'espaces partages explicites : `highway=pedestrian` avec `bicycle=yes|designated`, classes comme `shared_pedestrian_area`.

Colonnes produites :

- `conflict_type`;
- `walk_class`;
- `bike_infra`;
- `severity`;
- `geometry`.

Regle de severite dans `0_1` :

- `high` si `bike_infra == "sur_chaussée"` pour une intersection;
- `medium` pour les autres intersections et les superpositions lineaires;
- `low` pour les aires pietonnes partagees explicites.

Filtrage et score aval :

- tous les conflits sont conserves (`filtered = 1`);
- `severity_score = high:3, medium:2, low:1`;
- agregation observee : point, `sum` de `severity_score`, buffer 25 m bike et 1 m walk pour GG selon les classeurs.

Hypothese : une superposition ou intersection geometrique entre reseau marche et reseau velo signale un conflit potentiel d'usage, surtout lorsque le velo est sur chaussee ou dans une configuration partagee.

Limites :

- il s'agit de conflits potentiels, pas d'observations d'accidents ou de comportements;
- la detection est geometrique et depend de la qualite/topologie des reseaux;
- une intersection geometrique peut representer un croisement normal et amenage;
- la severite ne tient pas compte des volumes pietons/velos, vitesses observees, largeur, visibilite, regulation ou priorites;
- les conflits longitudinaux sont reduits au centroide de la superposition.

## Couches environnementales non OSM (walk GG)

### `bruit`

Source GG : raster de classes de bruit ORHANE 1 a 7 (`bruit_classes_grand_geneve.tif`, sortie du notebook bruit), qui assemble les donnees suisses reclassees et celles d'Auvergne-Rhone-Alpes. EPSG:2056, 0 = pas de donnee. Chemin et nom de fichier lus dans le classeur. Source GE : couche SITG, tous les objets conserves.

Hypothese : une exposition au bruit elevee degrade le confort de marche.

Traitement (`2_1`) :

- chaque pixel valide (hors NoData) devient un point au centre du pixel, comme pour la temperature (`SAMPLE_STEP = 1` : tous les pixels; une valeur `n > 1` garde un pixel sur `n` en x et en y);
- controle : le raster doit contenir uniquement les classes entieres 1 a 7, sinon le notebook s'arrete;
- colonnes : `bruit_classe` (1 a 7) et `bruit_norm = (classe - 1) / 6`, soit 0 = calme, 1 = hautement degrade;
- tous les points sont conserves (`filtered = 1`).

Agregation observee (`2_2`) : `how = raster`, buffer 100 m, colonne `bruit_100`. La valeur est la moyenne de `bruit_norm` dans le buffer (`value_column_GG = bruit_norm` dans le classeur). Environ 18.7 millions de points pour GG.

Impact : defavorable (valeur haute = environnement bruyant). Parametres d'etape 3 : `missing_value_strategy = mean_if_missing`, pas de `clip`. Classe « Commodite », `initial_weight = 0.5`.

Limites : les classes ORHANE sont deja une reclassification; la normalisation lineaire suppose des ecarts egaux entre classes. Le raccord Suisse/France peut produire des discontinuites a la frontiere. La couche est lourde (export d'environ 3 min).

### `canopee` (walk GG)

Source GG : GeoPackage de couverture du sol SITG `attributs/GG/canopee/SIPV_MN_CARTO_GG.gpkg` (meme structure que dans `0_1_bis_canopee_unifiee`), chemin lu dans le classeur. Une seule couche attendue (sinon renseigner `CANOPEE_LAYER`). Colonne de classe : `vegetation`. Source GE : couche SITG, geometries simplifiees a 0.01 m, tous les objets conserves.

Classes retenues (`CANOPEE_CLASSES`) :

- forets : « Forets fermees de coniferes », « Forets fermees de feuillus », « Forets ouvertes », « Forets humides »;
- vegetation arboree : « vegetation urbaine », « Vegetation arboree perturbee »;

Traitement (`2_1`) :

- verification que chaque classe existe exactement dans la colonne (sinon arret avec suggestions de noms proches);
- lecture filtree directement dans GDAL (classes retenues + emprise du perimetre);
- geometries rendues valides, eclatees, seules les parties polygonales gardees;
- decoupe au perimetre Grand Geneve (`AGGLO_PERIMETRE_AVEC_LAC`);
- tous les polygones lus sont conserves (`filtered = 1`), la selection etant faite a la lecture.

Agregation (`2_2`) : polygone, `area_ratio`, buffer 30 m, colonne `canopee_30`. Impact favorable. Parametres d'etape 3 : `clip_GG = 0.99`, `missing_value_strategy = zero_if_missing`. Classe « Commodite », `initial_weight = 0.5`.

Hypothese : la vegetation arboree apporte ombre, fraicheur et agrement.

Les milieux ouverts (prairies, cultures, vigne, verger) ne sont plus dans `canopee` : ils relevent de `environnement_ouvert_naturel`. Les deux attributs ne partagent plus aucune classe.

Limites : la couverture du sol ne capte pas forcement les arbres isoles ou d'alignement; l'ombre effective sur le cheminement n'est pas mesuree.

### `environnement_ouvert_naturel` (walk GG)

Source : meme GeoPackage de couverture du sol que `canopee` (`attributs/GG/environnement_ouvert_naturel/SIPV_MN_CARTO_GG.gpkg`, colonne `vegetation`). Pas de routine pour GE.

Classes retenues (`AGRICOLE_CLASSES`) : « Prairies humides », « Prairies seches », « Prairies extensives », « Prairies d'altitudes », « Cultures et prairies intensives », « Vigne », « Verger ».

Hypothese : les milieux ouverts naturels ou agricoles offrent un cadre paysager agreable pour la marche.

Traitement (`2_1`) : identique a `canopee` (verification des classes, lecture filtree, nettoyage, decoupe au perimetre Grand Geneve, `filtered = 1`).

Agregation (`2_2`) : polygone, `area_ratio`, buffer 30 m, colonne `environnement_ouvert_naturel_30`. Impact favorable. Parametres d'etape 3 : `clip_GG = 0.99`, `missing_value_strategy = zero_if_missing`. Classe « Commodite », `initial_weight = 0` (dans l'indice mais pas pondere pour l'instant).

Limites : les cultures intensives n'ont pas la meme valeur d'agrement que les prairies extensives, et leur accessibilite n'est pas garantie. Le message GE du notebook mentionne une « vectorisation par carreaux » qui ne correspond pas au traitement par polygones [message a corriger].

## Points a consolider

Les points suivants doivent etre verifies avant de considerer ce document comme complet :

- harmoniser le traitement de `eclairage` entre bike et walk (`lit=yes` seulement ou tout objet `lit=*`);
- `zone_pietonne` GG : retire; nettoyer les lignes correspondantes du classeur walk et de `2_1`;
- `zone_apaisee` walk GG : retire; supprimer la ligne du classeur walk et la branche GG de la cellule `zone_apaisee` dans `2_1`;
- `traversees` : decider s'il faut reconnaitre les feux via `crossing:signals` et les valeurs multiples (`uncontrolled;traffic_signals`), et garder ou non `island`;
- decider si `shared` doit rester classe avec `bande` ou devenir une categorie separee;
- revoir le score de `revetement`, notamment la valeur de `paved`;
- separer `amenite`, `rez_actif` et les amenites de proximite avec des listes documentees et stables;
- documenter les attributs non OSM/opendata restants dans les classeurs : `accident`, `air`, `temperature`, `stationnement_genant`, `largeur_trottoir`, `charge`, `attente`;
- verifier les buffers et methodes d'agregation de chaque ligne des deux classeurs apres stabilisation du schema.
