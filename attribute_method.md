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
- `Notebook/Step 1/1_1_Prepare_features.ipynb` : connectivite locale et couche `vitesse_all_edges`.
- `Notebook/Step 2/feature_to_network.py` : logique d'agregation des attributs sur les segments.
- `Notebook/Step 2/2_1_Filter_features_bike.ipynb` et `Notebook/Step 2/2_1_Filter_features_walk.ipynb` : filtres et scores avant agregation.
- `Data/input/attributs/attributs_info_bike.xlsx` et `Data/input/attributs/attributs_info_walk.xlsx` : parametrage aval des attributs.

## Perimetre

Sont couverts ici :

- les couches extraites directement d'OSM dans `osm_attributes.gpkg`;
- les couches derivees du reseau OSM prepare, par exemple `piste`, `bande`, `vitesse_all_edges`, `connectivite`;
- la couche `conflit_md`, calculee a partir de la relation geometrique entre reseau marche et reseau velo.

Ne sont pas documentees en detail dans cette version :

- les couches SITG/opendata non derivees d'OSM ou du reseau, par exemple `accident`, `air`, `temperature`, `bruit`, `largeur_trottoir`, `stationnement_genant`;
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
| `crossing` | point | OSM | `crossing=*` | couche informative, noeuds/traversees |
| `traffic_signals` | point | OSM | `highway=traffic_signals` | couche informative, noeuds |
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
| `canopee` | polygone | OSM | `landuse=forest`, `natural=wood` | bike/walk, area_ratio |
| `espaces_ouverts` | polygone | OSM | `leisure=park|playground`, `landuse=recreation_ground`, `amenity=grave_yard` | walk, presence |
| `landuse_env` | polygone | OSM | valeurs selectionnees de `landuse=*` | bike `alentours`, area_ratio |

## Synthese des couches reseau

| Couche | Geometrie | Source | Calcul principal | Usage aval observe |
|---|---:|---|---|---|
| `piste` | ligne | `bike_edges_graph.geojson` | filtre `infra_bike=piste_cyclable` ou tags `cycleway=*track/separated` | bike, `length_ratio` |
| `bande` | ligne | `bike_edges_graph.geojson` | filtre `infra_bike=bande_cyclable` ou tags `cycleway=*lane/advisory/shared` | bike, `length_ratio` |
| `vitesse` | ligne | `bike_edges_graph.geojson` ou OSM fallback | objets avec `maxspeed` | couche brute, distincte de `vitesse_all_edges` |
| `vitesse_all_edges` | ligne | reseau prepare | `speed_kph` calcule par tags de vitesse puis fallback par type de voie | bike/walk, vitesse et zones apaisees |
| `zone_apaisee` | ligne | `vitesse_all_edges` | filtre `5 < speed_kph < 30` dans les notebooks Step 2 | bike/walk, favorable |
| `vitesse_motorisee` | ligne | `vitesse_all_edges` | filtre `speed_kph > 25` | bike, defavorable |
| `zone_pietonne` | ligne | `vitesse_all_edges` pour GG | filtre actuel `5 < speed_kph < 30`; en version GE, source SITG zone pietonne | walk, favorable |
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

Usage actuel : couche informative extraite dans `0_2`; les traverses synthetiques du reseau marche sont plutot construites dans `0_1` a partir des noeuds `highway=crossing`.

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

Agregations observees : polygone, `area_ratio`, buffer 25 m bike et 30 m walk, impact favorable.

Limites : ne mesure pas la canopee urbaine fine, les arbres d'alignement ou l'ombre effective. Les couches SITG de canopee sont plus appropriees lorsqu'elles existent.

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
- colonnes conservees : `highway`, `maxspeed`, `source:maxspeed`, `name`.

`vitesse_all_edges` dans Step 1 :

- source : `bike_edges_graph.geojson`;
- calcule `speed_kph`;
- priorite aux tags explicites `maxspeed:forward`, `maxspeed:backward`, `maxspeed`;
- conversion mph si necessaire;
- prise en compte de `zone:maxspeed` pour `CH:urban`, `CH:rural`, `CH:motorway`;
- fallback par `highway`, par exemple `residential=30`, `service=20`, `living_street=20`, `pedestrian=10`, `footway/path/steps=5`;
- fallback final a 30 km/h.

Attributs derives :

- `zone_apaisee` : filtre actuel `5 < speed_kph < 30`;
- `vitesse_motorisee` : filtre actuel `speed_kph > 25`;
- `zone_pietonne` pour GG : filtre actuel `5 < speed_kph < 30` dans le notebook walk, a clarifier car ce filtre capture plus largement les zones apaisees et pas seulement les zones pietonnes.

Limites : la vitesse issue d'un fallback par type de voie est une approximation. Les zones pietonnes devraient idealement etre detectees par `highway=pedestrian`, `area:highway=pedestrian`, `access`, `motor_vehicle`, et non seulement par vitesse estimee.

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

## Points a consolider

Les points suivants doivent etre verifies avant de considerer ce document comme complet :

- harmoniser le traitement de `eclairage` entre bike et walk (`lit=yes` seulement ou tout objet `lit=*`);
- clarifier `zone_pietonne` pour GG, car le filtre actuel par `speed_kph` ressemble davantage a une zone apaisee qu'a une zone pietonne stricte;
- decider si `shared` doit rester classe avec `bande` ou devenir une categorie separee;
- revoir le score de `revetement`, notamment la valeur de `paved`;
- separer `amenite`, `rez_actif` et les amenites de proximite avec des listes documentees et stables;
- documenter les attributs non OSM/opendata restants dans les classeurs : `accident`, `air`, `temperature`, `bruit`, `stationnement_genant`, `largeur_trottoir`, `charge`, `attente`;
- verifier les buffers et methodes d'agregation de chaque ligne des deux classeurs apres stabilisation du schema.
