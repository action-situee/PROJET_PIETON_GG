import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import os

operation_crs = "EPSG:2056"
target_crs = "EPSG:4326"

# ─── Paths ────────────────────────────────────────────────────────────────────
# Chemin absolu basé sur la position du config.py
_config_dir   = os.path.dirname(os.path.abspath(__file__))  # .../utils
_project_root = os.path.join(_config_dir,'..','..','..')  # remonte 3 niveaux


input_file_path       = os.path.join(_project_root, 'Data', 'input')
output_step1_path     = os.path.join(_project_root, 'Data', 'output', 'walk','GG', 'step-1')
output_step2_path     = os.path.join(_project_root, 'Data', 'output', 'walk','GG', 'step-2')
output_step3_path     = os.path.join(_project_root, 'Data', 'output', 'walk','GG', 'step-3')
output_step3_geo_weighted_path = os.path.join(_project_root, 'Data', 'output', 'walk','GG', 'step-3_geo_weighted')

input_file_path_PL       = "/Users/maximiliantrique/Documents/GitHub/projet_pieton_gg/Data/input/PL_input/"
output_file_path_PL      = "/Users/maximiliantrique/Documents/GitHub/projet_pieton_gg/Data/output/PL_output/"
input_file_path_PL_wave1 = "/Volumes/T7_lin_win/PANEL_LEMANIQUE/WAVE1_MOBILITY/INPUT/"
output_file_path_PL_wave1= "/Users/maximiliantrique/Documents/GitHub/projet_pieton_gg/Data/output/PL_output/"

# ─── Imports ──────────────────────────────────────────────────────────────────
attributs_info = pd.read_excel(
    os.path.join(input_file_path, 'attributs', 'attributs_info_walk_unweighted.xlsx'),
    sheet_name="attributs_info"
)

# ─── Couleurs par classe ───────────────────────────────────────────────────────
classes      = attributs_info['Class'].dropna().unique().tolist()
palette      = plt.cm.Set2.colors
ATTRIBUTS_CLASS_COLORS = {cls: palette[i % len(palette)] for i, cls in enumerate(classes)}

#############################################################################################

# ─── Regroupement des modes ───────────────────────────────────────────────────
mode_groups = {
    "walk"                     : ["Mode::Walk"],
    "car"                      : ["Mode::Car", "Mode::Ecar", "Mode::Carsharing", "Mode::TaxiUber"],
    "public_transit"           : ["Mode::Bus", "Mode::Tram", "Mode::LightRail", "Mode::Subway"],
    "train"                    : ["Mode::Train", "Mode::RegionalTrain"],
    "bicycle"                  : ["Mode::Bicycle", "Mode::Ebicycle"],
    "vehicle_equivalent_device": ["Mode::KickScooter"],
    "2WV"                      : ["Mode::Motorbike"],
    "boat"                     : ["Mode::Boat"],
    "airplane"                 : ["Mode::Airplane"],
    "other"                    : ["Mode::Other"],
}

#############################################################################################

# ─── Labels Q120 — Revenu mensuel du ménage (CHF) ────────────────────────────


income_labels_Q120 = {
    1 : "< 2'000 CHF",
    2 : "2'000 – 4'000 CHF",
    3 : "4'001 – 6'000 CHF",
    4 : "6'001 – 8'000 CHF",
    5 : "8'001 – 10'000 CHF",
    6 : "10'001 – 12'000 CHF",
    7 : "12'001 – 14'000 CHF",
    8 : "14'001 – 16'000 CHF",
    9 : "> 16'000 CHF",
    10: "Don't know / Prefer not to answer",
}

income_order_Q120 = list(income_labels_Q120.values())

# ─── Labels Q121 — Revenu mensuel personnel (€) ───────────────────────────────
income_labels_Q121 = {
    1 : "< 1'000 €",
    2 : "1'001 - 2'000 €",
    3 : "2'001 - 3'000 €",
    4 : "3'001 - 4'000 €",
    5 : "4'001 - 5'000 €",
    6 : "5'001 - 6'000 €",
    7 : "6'001 - 7'000 €",
    8 : "7'001 - 8'000 €",
    9 : "8'001 - 9'000 €",
    10: "9'001 - 10'000 €",
    11: "> 10'000 €",
    12: "Ne sait pas / Préfère ne pas répondre",
}

# ─── Ordre logique pour les graphiques ────────────────────────────────────────


income_order_Q121 = [
    "< 1'000 €",
    "1'001 - 2'000 €",
    "2'001 - 3'000 €",
    "3'001 - 4'000 €",
    "4'001 - 5'000 €",
    "5'001 - 6'000 €",
    "6'001 - 7'000 €",
    "7'001 - 8'000 €",
    "8'001 - 9'000 €",
    "9'001 - 10'000 €",
    "> 10'000 €",
    "Ne sait pas / Préfère ne pas répondre",
]



#############################################################################################

# ─── Labels abonnements TP (Q10) ──────────────────────────────────────────────
tp_labels_Q10 = {
    'Q10_1_R': 'AG',
    'Q10_2_R': 'Demi-tarif',
    'Q10_3_R': 'Abo forfaitaire SNCF',
    'Q10_4_R': 'Carte réduction SNCF',
    'Q10_5_R': 'Abo parcours CFF',
    'Q10_6_R': 'Léman Pass',
    'Q10_7_R': 'Abo communautaire',
    'Q10_8_R': 'Autre',
    'Q10_9_R': 'Aucun abonnement',
}

# ─── Labels abonnements mobilité (Q11) ────────────────────────────────────────
tp_labels_Q11 = {
    'Q11_1_R': 'Vignette autoroute',
    'Q11_2_R': 'Badge télépéage',
    'Q11_3_R': 'Abo P+R',
    'Q11_4_R': 'Abo B+R (bike and ride)',
    'Q11_5_R': 'Autopartage (perso)',
    'Q11_6_R': 'Autopartage (employeur)',
    'Q11_7_R': 'VLS (perso)',
    'Q11_8_R': 'VLS (employeur)',
    'Q11_9_R': 'Aucun abo',
}

#############################################################################################

# ─── Ordre intensité de marche ────────────────────────────────────────────────


walk_intensity_order = [
    'Very low (<100m)',
    'Low (100–500m)',
    'Moderate (500m–1km)',
    'Regular (1–2km)',
    'Intensive (>2km)',
]

# ─── Labels Q108_new — Santé physique perçue ──────────────────────────────────

physical_cond_labels = {
    1: "Strongly disagree",
    2: "Rather disagree",
    3: "Rather agree",
    4: "Strongly agree",
}
physical_cond_label_order = list(physical_cond_labels.values())


#############################################################################################

# ─── Profile to age group mapping ─────────────────────────────────────────────
profile_age_map = {
    "senior" : ["60-74 ans", "75 ans et plus"],
    "young"  : ["18-29 ans"],
    "middle" : ["30-44 ans", "45-59 ans"],
    ""       : None
}

#############################################################################################

gender_filters = [
    ("homme", "Homme"),
    ("femme", "Femme"),
]

gender_labels = {
    "homme" : "Men",
    "femme" : "Women",
}

#############################################################################################

# ─── Définition des groupes âge ───────────────────────────────────────────────
age_filters = [
    ("18-29",    "18-29 ans"),
    ("30-44",    "30-44 ans"),
    ("45-59",    "45-59 ans"),
    ("60+",      "60 ans +"),
]

age_labels = {
    "18-29" : "18-29",
    "30-44" : "30-44",
    "45-59" : "45-59",
    "60+"   : "60+",
}


#############################################################################################

# ─── Définition des groupes revenu ────────────────────────────────────────────
income_filters = [
    ("tres_modeste", "Modeste (< Q1 GE)"),
    ("modeste",      "Modeste (Q1 - Q3 GE)"),
    #("median",       "Médian ( Q1 - Q3 GE)"),
    ("aise",         "Aisé (> Q3 GE)"),
]

income_labels = {
    "tres_modeste" : "Low income",
    "modeste"      : "Median income",
    #"median"       : "Median income",
    "aise"         : "High income",
}

#############################################################################################

car_filters = [
    ("no_car",  "Sans voiture"),
    ("has_car", "Avec voiture"),
]

car_labels = {
    "no_car"  : "No car",
    "has_car" : "Car owner",
}

#############################################################################################

tp_filters = [
    ("no_tp",       0),
    ("partial_tp",  1),
    ("full_tp",     2),
]

tp_labels = {
    "no_tp"      : "No PT subscription",
    "partial_tp" : "Partial PT subscription",
    "full_tp"    : "Full PT subscription",
}


#############################################################################################

time_slots = [
    ("all_day",       0,  0, 23, 59),
    ("morning_early",  5,  0,  7,  0),
    ("morning_peak",  7,  0,  9,  0),
    ("mid_morning",   9,  0, 11, 30),
    ("lunch",        11, 30, 14,  0),
    ("afternoon",    14,  0, 16,  0),
    ("evening_peak", 16,  0, 19,  0),
    ("evening",      19,  0, 21, 30),
]

slot_labels = {
    "all_day"      : "All day",
    "morning_early": "Early morning\n05:00 - 07:00",
    "morning_peak" : "Morning peak\n07:00 - 09:00",
    "mid_morning"  : "Mid morning\n09:00 - 11:30",
    "lunch"        : "Lunch\n11:30 - 14:00",
    "afternoon"    : "Afternoon\n14:00 - 16:00",
    "evening_peak" : "Evening peak\n16:00 - 19:00",
    "evening"      : "Evening\n19:00 - 21:30",
}

#############################################################################################

# ═══ Paramètres globaux de visualisation des raster de fréquentation piétonne ══════════════════════════════════════
clip_percentile = 99      # ← P90, P95, P99
cmap_name       = "magma"  # ← "magma", "plasma", "viridis"
norm_mode       = "linear"  # ← "log1p" ou "linear"
#print("Norm mode :", norm_mode)

# ─── Dictionnaire des transformations disponibles ─────────────────────────────
# Pour ajouter un mode : ajouter une entrée ici, tout le reste s'adapte
NORM_TRANSFORMS = {
    "log1p"  : lambda x: np.log1p(x),
    "linear" : lambda x: x,
}


labels_all_groups = {
    "all"          : "All users",
    "homme"        : "Men",
    "femme"        : "Women",
    "18-29"        : "18-29",
    "30-44"        : "30-44",
    "45-59"        : "45-59",
    "60+"          : "60+",
    "tres_modeste" : "Low income",
    "modeste"      : "Median income",
    "aise"         : "High income",
    "no_car"       : "No car",
    "has_car"      : "Car owner",
    "no_tp"        : "No PT subscription",
    "partial_tp"   : "Partial PT subscription",
    "full_tp"      : "Full PT subscription",
}

#"median"       : "Median income",

#############################################################################################

# ─── AREA_TYPE order and colors ───────────────────────────────────────────────
AREA_TYPE_ORDER = [
    "major metro centers",
    "central urban areas",
    "urban suburbs",
    "secondary centers",
    "low densities",
]

AREA_TYPE_COLORS = {
    "major metro centers" : "#377eb8",  # bleu
    "central urban areas" : "#984ea3",  # violet
    "urban suburbs"       : "#ff7f00",  # orange
    "secondary centers"   : "#a65628",  # brun
    "low densities"       : "#f781bf",  # rose pâle
}

AREA_TYPE_LABELS = {
    "major metro centers" : "Major metropolitan centres",
    "central urban areas" : "Central and suburban agglomeration areas",
    "urban suburbs"       : "Agglomeration periphery",
    "secondary centers"   : "Secondary centres",
    "low densities"       : "Low-density and peri-urban areas",
}

#############################################################################################


prof_fr_to_en = {
    'Population active occupée'  : 'Employed',
    'Personnes retraitées'        : 'Retired',
    'Personnes en formation'      : 'Student',
    'Personnes sans emploi'       : 'Unemployed',
    'Femmes / hommes au foyer'    : 'Homemaker',
}

car_fr_to_en = {fr_val: labels_all_groups[key] for key, fr_val in car_filters}
# → {"Sans voiture": "No car", "Avec voiture": "Car owner"}

income_class_fr_to_en = {fr_val: labels_all_groups[key] for key, fr_val in income_filters}
# → {"Très modeste (< Q1 GE)": "Very low income", ...}

income_class_order = [labels_all_groups[key] for key, _ in income_filters]
# → ['Very low income', 'Low income', 'Median income', 'High income']

gender_fr_to_en = {fr_val: labels_all_groups[key] for key, fr_val in gender_filters}

age_fr_to_en    = {fr_val: labels_all_groups[key] for key, fr_val in age_filters}
tp_level_map      = {float(val): labels_all_groups[key] for key, val in tp_filters}
# → {0.0: "No PT subscription", 1.0: "Partial PT subscription", 2.0: "Full PT subscription"}

income_filters_en = [(key, labels_all_groups[key]) for key, _ in income_filters]
# → [("tres_modeste", "Low income"), ("modeste", "Median income"), ("aise", "High income")]
gender_filters_en = [(key, labels_all_groups[key]) for key, _ in gender_filters]
age_filters_en    = [(key, labels_all_groups[key]) for key, _ in age_filters]
car_filters_en    = [(key, labels_all_groups[key]) for key, _ in car_filters]
tp_level_order    = [labels_all_groups[key] for key, _ in tp_filters]

_PALETTE = ["#4C72B0", "#DD8452", "#55A868", "#C44E52",
            "#8172B2", "#937860", "#DA8BC3", "#8C8C8C"]

CATEGORY_COLORS = {
    # Gender
    labels_all_groups["homme"] : _PALETTE[0],
    labels_all_groups["femme"] : _PALETTE[1],
    # Age
    labels_all_groups["18-29"] : _PALETTE[0],
    labels_all_groups["30-44"] : _PALETTE[1],
    labels_all_groups["45-59"] : _PALETTE[2],
    labels_all_groups["60+"]   : _PALETTE[3],
    # Income
    labels_all_groups["tres_modeste"] : _PALETTE[0],
    labels_all_groups["modeste"]      : _PALETTE[1],
    #labels_all_groups["median"]       : _PALETTE[2],
    labels_all_groups["aise"]         : _PALETTE[2],
    # Car
    labels_all_groups["no_car"]  : _PALETTE[0],
    labels_all_groups["has_car"] : _PALETTE[1],
    # PT
    labels_all_groups["no_tp"]      : _PALETTE[0],
    labels_all_groups["partial_tp"] : _PALETTE[1],
    labels_all_groups["full_tp"]    : _PALETTE[2],
    # PT numérique
    "0" : _PALETTE[0],
    "1" : _PALETTE[1],
    "2" : _PALETTE[2],
    # Fallback
    "NaN"           : "#D3D3D3",
    "NaN / missing" : "#D3D3D3",
}



# ─── Group categories for density analysis ────────────────────────────────────
group_categories = {
    'all':    ['density_all'],
    'gender': [f'density_{key}' for key, _ in gender_filters],
    'age':    [f'density_{key}' for key, _ in age_filters],
    'income': [f'density_{key}' for key, _ in income_filters],
    'car':    [f'density_{key}' for key, _ in car_filters],
    'tp':     [f'density_{key}' for key, _ in tp_filters],
}

# ─── Precarity area categories ────────────────────────────────────────────────
def assign_precarity_area(score):
    if pd.isna(score):   return np.nan
    elif score == 0:     return 'Non-precarious (0)'
    elif score <= 2:     return 'Low precarity (1-2)'
    elif score <= 4:     return 'Precarious (3-4)'
    else:                return 'Highly precarious (5-6)'

PRECARITY_AREA_ORDER = [
    'Non-precarious (0)',
    'Low precarity (1-2)',
    'Precarious (3-4)',
    'Highly precarious (5-6)'
]

PRECARITY_AREA_COLORS = {
    'Non-precarious (0)':      '#ffffd4',  # jaune très pâle
    'Low precarity (1-2)':     '#fed98e',  # jaune-brun clair
    'Precarious (3-4)':        '#fe9929',  # brun-orange
    'Highly precarious (5-6)': '#8c2d04'   # brun très foncé
}

# ─── Trip Purpose — Group mapping ─────────────────────────────────────────────
PURPOSE_GROUP_MAP = {
    "work"          : "Constrained",
    "study"         : "Constrained",
    "medical_visit" : "Constrained",
    "wait"          : "Constrained",
    "home"          : "Home",
    "eat"           : "Semi-constrained",
    "assistance"    : "Semi-constrained",
    "errand"        : "Semi-constrained",
    "shopping"      : "Unconstrained",
    "sport"         : "Unconstrained",
    "family_friends": "Unconstrained",
    "leisure"       : "Unconstrained",
    "other"         : "Other",
    "unknown"       : "Other",
}

# ─── Trip Purpose — Group order ───────────────────────────────────────────────
PURPOSE_GROUP_ORDER = ["Constrained", "Semi-constrained", "Unconstrained", "Home", "Other"]

# ─── Trip Purpose — Colors per group ──────────────────────────────────────────

PURPOSE_GROUP_COLORS = {
    "Constrained"      : "#8172B2",  # violet    — PALETTE[4]
    "Semi-constrained" : "#937860",  # brun      — PALETTE[5]
    "Unconstrained"    : "#DA8BC3",  # rose      — PALETTE[6]
    "Home"             : "#64B5CD",  # bleu ciel — PALETTE[8]
    "Other"            : "#8C8C8C",  # gris      — PALETTE[7]
}

# ─── Landmarks de référence (EPSG:2056) ───────────────────────────────────────
LANDMARKS_GE = {
    "Geneva Cornavin \n Train Station"           : (2499950, 1118400),
    "Lancy-Pont-Rouge \n Train Station"   : (2498613.48, 1115907.82),
    "Geneva University \n Hospitals (HUG)"        : (2500642.20, 1116694.20),
    "Airport"           : (2497679.49, 1121062.09),
    "Plainpalais"        : (2499804.38, 1117161.66),
    "Sciences University" : (2499208.76, 1117128.44),
    "Geneva University" : (2500114.28, 1117223.43),
    "Human Science University \n (Uni Mai /Uni Pignon)" : (2499764.86, 1116735.96),
    "HEPIA" : (2499442.53, 1118379.10),
    "HEAD" : (2499520.32, 1118390.75),
    "United Nation \n (ONU)" : (2499891.86, 1120277.18),
    "WTO (OMC)" : (2500558.62, 1119954.16),
    "Pictet \n (Wealth Management)" : (2499079.84, 1116078.91),
    "Rhône Street" : (2500545.32, 1117691.41),
    "Geneva Champelle \n Train Station" : (2500813.67, 1116500.28)
}

# ─── Quadrant classification colors ───────────────────────────────────────────
QUADRANT_COLORS = {
    'Optimal':      '#2166ac',
    'Critical':     '#d73027',
    'Unexploited':  '#f4a582',
    'Low priority': '#92c5de',
    'Neutral':      '#c6c2c2',
}

QUADRANT_ORDER = ['Optimal', 'Critical', 'Unexploited', 'Low priority', 'Neutral']

# ─── Palette pour les courbes LOWESS multi-groupes ────────────────────────────
ALL_GROUP_COLORS = {
    # Gender
    "homme"        : "#4C72B0",
    "femme"        : "#DD8452",
    # Age
    "18-29"        : "#55A868",
    "30-44"        : "#6B9E3E",
    "45-59"        : "#A8C56E",
    "60+"          : "#C44E52",
    # Income
    "tres_modeste" : "#2196F3",
    "modeste"      : "#4CAF50",
    "aise"         : "#FF5722",
    # Car
    "no_car"       : "#8172B2",
    "has_car"      : "#937860",
    # PT
    "no_tp"        : "#DA8BC3",
    "partial_tp"   : "#B05A8C",
    "full_tp"      : "#8C8C8C",
}


print("config.py - All is good")

