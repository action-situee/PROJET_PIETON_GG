# projet-index-walk-bike-ge-gg

Ce dépôt contient le pipeline de travail utilisé pour produire et documenter des indices de marchabilité et de cyclabilité sur les périmètres `GE` et `GG`.

Le projet repose principalement sur des notebooks Python et des traitements géospatiaux. Il combine des données de réseau, des attributs issus d'OpenStreetMap, des données locales placées dans `Data/`, puis des traitements d'agrégation et de calcul d'indice.

Ce n'est pas un package Python stabilisé. C'est un environnement analytique de projet, structuré pour permettre la reprise, le contrôle et la livraison des traitements, à condition de disposer des données locales attendues.

## Ce qui est livré

Le dépôt versionne :

- les notebooks de traitement ;
- les scripts auxiliaires utilisés par certains notebooks ;
- les fichiers de dépendances Python ;
- la documentation méthodologique disponible ;
- les hooks de nettoyage des notebooks avant commit.

Le dépôt ne versionne pas :

- les données sources ;
- les sorties intermédiaires ou finales ;
- les environnements virtuels ;
- les caches ;
- les fichiers locaux sensibles.

Le dossier `Data/` est ignoré par Git. Les résultats ne peuvent donc être reproduits que si les données locales nécessaires sont disponibles avec la structure attendue.

## Périmètre

La configuration actuelle prévoit deux périmètres :

- `GE` : canton de Genève ou périmètre genevois selon les données d'entrée disponibles ;
- `GG` : Grand Genève ou périmètre élargi selon les données d'entrée disponibles.

Les chemins de sortie sont définis dans `Notebook/path_config.py` :

- `Data/output/GE/step-1`, `step-2`, `step-3` ;
- `Data/output/GG/step-1`, `step-2`, `step-3`.

Les sources exactes, millésimes, droits d'usage et périmètres géographiques doivent être vérifiés dans les données locales avant toute diffusion d'un résultat. [À COMPLÉTER]

## Structure du dépôt

`Notebook/Step 0/` contient les extractions initiales :

- chargement et préparation des réseaux marche et vélo ;
- extraction des attributs OSM ;
- anciennes variantes séparées, conservées comme références de travail.

`Notebook/Step 1/` prépare les objets réseau et attributs :

- préparation du réseau ;
- préparation des features ;
- calculs auxiliaires de pente et de connectivité locale.

`Notebook/Step 2/` filtre et projette les attributs sur le réseau :

- filtrage des attributs pour le vélo ;
- filtrage des attributs pour la marche ;
- traitement et agrégation des features vers les segments.

`Notebook/Step 3/` calcule, agrège et cartographie les indices :

- calcul des indices ;
- agrégations spatiales ;
- cartes et sorties de contrôle.

`Notebook/Step 4/` contient des analyses de terrain ou d'enquêtes, lorsque les données correspondantes sont disponibles.

`attribute_method.md` documente les attributs OSM et réseau déjà explicités. Ce document sert à comprendre les transformations réalisées avant l'interprétation des indices.

`SECURITY_NOTEBOOKS.md`, `install_git_hooks.sh` et `clear_notebooks.py` servent à éviter la publication accidentelle de sorties de notebooks ou de données sensibles.

## Données attendues

Structure attendue par les notebooks :

```text
Data/
  input/
  output/
    GE/
      step-1/
      step-2/
      step-3/
    GG/
      step-1/
      step-2/
      step-3/
```

Les fichiers d'attributs attendus par la méthodologie incluent notamment :

- `Data/input/attributs/attributs_info_bike.xlsx`
- `Data/input/attributs/attributs_info_walk.xlsx`

La liste exhaustive des données d'entrée, leur origine, leur millésime, leur statut de diffusion et les restrictions d'usage restent à documenter. [À COMPLÉTER]

## Environnement Python

Deux fichiers de dépendances existent :

- `requirements.txt` : capture large de l'environnement de travail utilisé ;
- `requirements_osm.txt` : environnement minimal testé pour les extractions OSM et les exports géospatiaux de base.

Installation indicative :

```bash
python3 -m venv venv-indices
source venv-indices/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Pour un traitement limité à l'extraction OSM, `requirements_osm.txt` peut suffire.

## Ordre d'exécution

L'ordre logique est le suivant :

1. Exécuter `Notebook/Step 0/0_1_Load_osm_networks_and_nodes_bike_walk.ipynb`.
2. Exécuter `Notebook/Step 0/0_2_Load_osm_features.ipynb`.
3. Exécuter les notebooks de `Notebook/Step 1/`.
4. Exécuter les notebooks de `Notebook/Step 2/`, en distinguant si nécessaire les traitements marche et vélo.
5. Exécuter les notebooks de `Notebook/Step 3/` pour calculer, agréger et cartographier les indices.
6. Exécuter `Notebook/Step 4/` uniquement si les données de terrain correspondantes sont disponibles.

Les chemins relatifs des notebooks supposent une exécution depuis leur contexte de dossier. En cas d'erreur de chemin, vérifier d'abord `Notebook/path_config.py` et la présence de `Data/input`.

## Contrôles avant livraison

Avant de livrer ou pousser une version :

```bash
git status --short
git diff --stat
```

Vérifier en particulier :

- absence de fichiers issus de `Data/` ;
- absence d'outputs volumineux ou sensibles dans les notebooks ;
- cohérence entre `README.md`, `attribute_method.md` et les notebooks ;
- absence de chemins personnels dans les fichiers versionnés ;
- cohérence entre les branches `marced` et `main`.

Installer les hooks Git avant de travailler sur les notebooks :

```bash
./install_git_hooks.sh
```

Ces hooks nettoient les sorties des notebooks au commit et limitent le risque de publier des résultats, extraits de données ou métadonnées locales.

## Limites connues

Le projet contient encore des traces de noms historiques dans certains kernels de notebooks ou commentaires. Elles ne modifient pas nécessairement le calcul, mais peuvent rendre la lecture moins claire.

La documentation méthodologique n'est pas exhaustive. Les attributs, pondérations, seuils et sources doivent être contrôlés avant toute interprétation publique ou livraison client.

Certains notebooks peuvent contenir des chemins hérités ou dépendre de fichiers locaux non versionnés. Ces éléments doivent être vérifiés lors d'une reprise par un tiers.

Pour une diffusion formelle, il faudra encore consolider les chemins, les paramètres d'entrée, les contrôles qualité et la description complète des données. [À COMPLÉTER]
