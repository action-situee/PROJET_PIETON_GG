# Walkability and Pedestrian Equity in the Canton of Geneva

Master's thesis project analysing pedestrian mobility practices across socio-demographic groups in the Canton of Geneva, combining GPS tracking data from the **Panel Lémanique** mobility survey with a multifactorial **Walk Index** developed by Bureau Action Située.

**Author:** Quentin
**Institution:** EPFL — LaSUR laboratory
**Supervision:** Marc-Edouard Schultheiss (Action Située, primary supervisor), Prof. Gabriel Manoli (EPFL URBES lab, academic co-supervisor)
**Data access:** Clément Rames (LaSUR)

---

## Overview

This project investigates how pedestrian conditions and walking practices vary across five socio-demographic dimensions — gender, age, income, car ownership, and public transport subscription level — in the Canton of Geneva. It combines GPS-tracked walking trajectories with a spatial Walk Index to identify patterns of pedestrian equity or not.

---

## Repository structure

```
Notebook/
├── Step 3/
│   └── 3_2_Agregated_index.ipynb            # Enrichment of the Walk Index with cantonal statistics
└── PANEL_LEMANIQUE/
    ├── extract_panel_lemanique_data.R          # Raw data extraction (R)
    ├── mobility_1_and_rythm&mobilty.ipynb       # Exploratory analysis of survey waves
    ├── 01_DATAFRAME_CREATION.ipynb
    ├── 02_DATAFRAME_ANALYSES.ipynb
    ├── 03_RASTER_WALK_DENSITY.ipynb
    ├── 04_RASTER_ANALYSES.ipynb
    ├── 05_RASTER_PROFILE.ipynb
    └── utils/
        ├── config.py
        └── functions.py
```

---

## Pipeline description

### `extract_panel_lemanique_data.R`
Extracts and consolidates data from the Panel Lémanique survey waves (raw source data, R script).

### `mobility_1_and_rythm&mobilty.ipynb`
Exploratory analysis of the **Mobility 1** and **Rythme et Mobilité** survey waves — descriptive overview of survey responses to understand the population and context before working with GPS data.

### `01_DATAFRAME_CREATION.ipynb`
Builds the core GPS analysis dataset: filters relevant records, aggregates trip- and user-level metrics (distances, characteristics per GPS trace, etc.). Produces the base dataframes used throughout the rest of the pipeline.

### `02_DATAFRAME_ANALYSES.ipynb`
Descriptive statistical analysis of the dataset produced in step 01 — general overview of sample composition, walking behaviour, and data quality.

### `03_RASTER_WALK_DENSITY.ipynb`
Generates all pedestrian density rasters (10m × 10m grid, normalised by `n_days_GE`) used in the rest of the analysis — overall, by socio-demographic group, and by hour.

### `04_RASTER_ANALYSES.ipynb`
Analyses the rasters generated in step 03: computes density metrics (`mean_canton`, `mean_active_canton`, `intensite_relative`, `spatial coverage`, etc.) and aggregates results to larger spatial scales (GIREC sub-sectors) for each group.

### `05_RASTER_PROFILE.ipynb`
Builds density-weighted Walk Index attribute profiles at the specific unit scale, using the aggregated density scores produced in step 04.

### `utils/`
- **`config.py`** — shared variables: group filters and labels, colour palettes, CRS definitions, spatial constants.
- **`functions.py`** — shared functions used across notebooks (raster building/normalisation, statistics computation, plotting utilities).

### `Step 3/3_2_Agregated_index.ipynb`
Builds on the pre-existing Walk Index to enrich it with additional cantonal statistics at the different spatial scales of analysis — precarity score, public transport service quality score, spatial unit population, and other variables used throughout this study.


---

## Data sources

- Panel Lémanique GPS mobility survey
- Walk Index (Bureau Action Située)
- GIREC sub-sectors (OCSTAT)
- ARE public transport quality classifications
- CATI-GE precarity index
- SwissBOUNDARIES3D / SITG cantonal geodata

---
