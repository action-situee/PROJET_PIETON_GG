# Indice de cyclabilité hiérarchisé — méthode (socle + bonus)

`bike_index_hierarchised` : un indice en deux temps. Un segment doit d'abord atteindre un **socle** minimal (attributs du mandat : infrastructure, sécurité) ; seulement ensuite les autres attributs (confort, attractivité, équipement…) apportent un **bonus**. Calculé dans `3_1` **en plus** de l'indice habituel `bike_index`, qui ne change pas.

État au **24.11.2026**. Code : `Notebook/Step 3/3_1_Compute_index.ipynb`, cellule 4 (paramètres) et section « SCORE HIÉRARCHISÉ » (après le calcul des classes).

## 1. Paramètres

| Paramètre | Valeur actuelle | Rôle |
|---|---|---|
| `HIERARCHISED_SCORE` | `True` | active le calcul |
| `SOCLE_COLUMN` | `"socle"` | colonne True / False de l'Excel qui désigne les attributs du socle |
| `SOCLE_THRESHOLD` (T) | 0,5 | seuil sur `classe_socle` |
| `SOCLE_DELTA` (δ) | 0 | adoucissement : le bonus monte de 0 à 100 % entre T − δ et T + δ (0 = marche franche) |
| `SOCLE_AGG` | `"mean"` | méthode de calcul de F : `mean`, `median` ou `geomean` (voir §2 bis) — ajout du 25.11 |
| `SOCLE_GEOMEAN_EPS` | 0,01 | `geomean` : plancher appliqué aux attributs avant le log |
| `BONUS_MINMAX` | `True` | `classe_bonus` min-maxée sur [0, 1] (tous les segments) |
| `SOCLE_HIST_THRESHOLDS` | 0,30 à 0,70 par pas de 0,05 | seuils du tableau « km au-dessus du seuil » |
| `NAN_POLICY` | `"ignore"` | traitement des NaN dans `bike_index` et les classes (voir §5) |

Poids : `initial_weight` de l'Excel, pour le socle comme pour le bonus. Un attribut de poids 0 est ignoré.

**Socle actuel** (25.11 : 6 attributs, poids 0,5 chacun, soit 1/6 du socle chacun) : `infra_cyclable`, `coupure`, `giratoire` (infrastructure) ; `eclairage`, `vitesse_motorisee`, `accident` (sécurité).

**Bonus actuel** (attributs inclus, de poids > 0, hors socle) : `amenite`, `pente`, `eau`, `canopee`, `environnement_ouvert_naturel`, `stationnement_velo`, `borne_reparation`, `location`, `service_velo`, `conflit_md`, `charge`.

## 2. Calcul

Les attributs sont pris **après** normalisation (min-max) et inversion des attributs défavorables : tous sont dans [0, 1], « plus = mieux ».

1. **Socle** F (`classe_socle`, alias *minimal_cyclability_score*) : agrégation pondérée par `initial_weight` des attributs du socle, selon `SOCLE_AGG` (moyenne arithmétique par défaut, voir §2 bis). Les NaN sont ignorés (poids répartis sur les attributs présents).
2. **Bonus** B (`classe_bonus`) : moyenne pondérée des autres attributs, NaN ignorés, puis min-max sur [0, 1] si `BONUS_MINMAX`. Calculée pour tous les segments.
3. **Indice hiérarchisé** :
   - F < T : `bike_index_hierarchised = F` ;
   - F ≥ T : `bike_index_hierarchised = F + (1 − F) × B`.

   Le bonus comble une part de ce qui manque au socle : un segment déjà très bon gagne peu, l'indice ne dépasse jamais 1, et il n'est **pas** min-maxé (T garde son sens). Forme équivalente : 1 − (1 − F)(1 − B).
4. **Rampe** (δ > 0) : part du bonus appliquée g = (F − (T − δ)) / (2δ), bornée à [0, 1] ; indice = F + g (1 − F) B. Sous T − δ l'indice vaut F, au-delà de T + δ le bonus est entier.
5. **`seuil_atteint`** = 1 si F ≥ T, 0 sinon (toujours une marche, même avec δ > 0).
6. Segments masqués « sans données » (`MAX_MISSING_SHARE`) : NaN.

Exemples (T = 0,5, δ = 0) :

| F | B | Indice |
|---|---|---|
| 0,49 | 0,8 | 0,49 |
| 0,51 | 0,8 | 0,90 |
| 0,90 | 0,8 | 0,98 |
| 0,90 | 0,2 | 0,92 |

## 2 bis. Méthode de calcul de F (`SOCLE_AGG`, ajout du 25.11)

Les trois méthodes sont pondérées par `initial_weight` et ignorent les NaN. Le bonus B reste une moyenne arithmétique.

| `SOCLE_AGG` | Calcul | Comportement |
|---|---|---|
| `mean` | Σ w·x / Σ w | compensatoire : un très bon attribut compense un mauvais |
| `median` | médiane pondérée (si la moitié du poids tombe entre deux valeurs, moyenne des deux) | robuste aux valeurs extrêmes ; ignore un attribut isolé très bas ou très haut |
| `geomean` | exp(Σ w·log(max(x, ε)) / Σ w) | peu compensatoire : un attribut proche de 0 tire F vers le bas ; ε = `SOCLE_GEOMEAN_EPS` évite qu'un seul 0 donne F = 0 |

Exemple, quatre attributs de même poids valant 0 ; 0,9 ; 0,9 ; 0,9 : `mean` 0,68, `median` 0,90, `geomean` 0,29.

Sur le `step3_index` du 25.11 (6 attributs socle) :

| `SOCLE_AGG` | P10 | Médiane | P90 | Part du réseau avec F ≥ 0,5 |
|---|---|---|---|---|
| `mean` | 0,52 | 0,70 | 0,72 | 98 % |
| `median` | 0,55 | 0,95 | 1,00 | 98 % |
| `geomean` | 0,16 | 0,37 | 0,39 | 3 % |

Le seuil T doit être choisi **pour chaque méthode**, sur l'histogramme de `classe_socle`. Avec `geomean`, F est dominée par les attributs souvent nuls (en premier `infra_cyclable` = 0 sur les routes sans aménagement) et la valeur de ε compte beaucoup : 0,01 pénalise très fort, 0,1 beaucoup moins.

## 3. Arbitrages

| Sujet | Décision | Raison |
|---|---|---|
| Forme du bonus | F + (1 − F) B plutôt que F + (1 − T) B écrêté à 1 | pas d'entassement à 1 en haut de l'échelle ; un segment très bon a « déjà fait le travail » |
| Hiérarchie stricte | avec δ = 0, tout segment sous T est moins bien classé que tout segment au-dessus | le confort ne compense pas un socle insuffisant |
| Marche au seuil | assumée (δ = 0), rampe disponible | deux segments presque identiques peuvent être loin l'un de l'autre ; avec δ > 0 le classement strict disparaît dans la rampe |
| Poids | `initial_weight` de l'Excel pour F et B | cohérence avec `bike_index` |
| NaN | ignorés dans les moyennes | un attribut manquant ne fait pas sortir le segment |
| Indice habituel | conservé et calculé en parallèle (`bike_index`, `Classe_*`) | comparaison des deux méthodes |

## 4. Sorties

| Colonne | Contenu | Dans les gpkg agrégés (`3_2`) |
|---|---|---|
| `classe_socle` | F | moyenne pondérée par la longueur |
| `classe_bonus` | B | moyenne pondérée par la longueur |
| `seuil_atteint` | 1 / 0 | **part du réseau** (pondérée par la longueur) qui atteint le socle, entre 0 et 1 |
| `bike_index_hierarchised` | indice | moyenne des segments (la formule n'est pas réappliquée au carreau) |

`3_1` affiche aussi un histogramme de `classe_socle` (en km de réseau, avec T et la rampe), la comparaison des distributions `bike_index_hierarchised` / `bike_index`, et un tableau des km et du % du réseau au-dessus de chaque seuil de `SOCLE_HIST_THRESHOLDS`.

## 5. `NAN_POLICY`

Avant le 24.11, `bike_index` et les `Classe_*` étaient une somme pondérée : un seul attribut NaN (attributs en `keep_nan`) rendait le segment NaN, même avec un poids 0. Avec `NAN_POLICY = "ignore"`, `calculate_index` fait la somme pondérée sur les attributs **présents**, ramenée à l'échelle de la somme complète : résultat identique sans NaN, et un segment avec un attribut manquant garde un indice. `"propagate"` rétablit l'ancien comportement. Les deux indices (habituel et hiérarchisé) suivent ainsi la même règle.

## 6. Choisir le seuil

- Regarder l'histogramme de `classe_socle` : il a des **pics** (beaucoup de segments partagent les mêmes valeurs par défaut). Un seuil placé juste à côté d'un pic fait basculer des milliers de km pour un réglage de 0,01.
- Le tableau des seuils donne directement les km perdus d'un seuil à l'autre.
- Avec δ > 0, la rampe doit rester étroite (0,05 à 0,1) : à δ = 0,2 elle couvre presque toute la distribution et il n'y a plus vraiment de seuil.

## 7. Limites

- Le résultat dépend fortement de la liste du socle et de la qualité de ses attributs (`vitesse_motorisee` a été refait le 24.11 ; `conflit_md`, hors socle, repose encore sur le graphe marche).
- `classe_bonus` est relative au territoire (min-max) : sa valeur absolue n'a pas de sens hors du Grand Genève.
- Non calculé en `GEO_WEIGHTING` ni avec `CENTER_AROUND_ZERO`.

## 8. Relancer

`3_1` → `3_2` (après toute modification de l'Excel ou des attributs en amont).
