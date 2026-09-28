import numpy as np
from affine import Affine
from scipy.ndimage import gaussian_filter
from rasterio.features import rasterize, geometry_mask
import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd
import matplotlib.patches as mpatches
import os
import fiona
import rasterio
from rasterio.enums import MergeAlg
from sklearn.preprocessing import MinMaxScaler
from shapely.geometry import Point
import libpysal
import esda
import rasterstats
import warnings
warnings.filterwarnings("ignore")
import math
from statsmodels.nonparametric.smoothers_lowess import lowess
import matplotlib.gridspec as gridspec
from matplotlib.patches import Patch
from matplotlib.patches import FancyArrowPatch
import matplotlib.patheffects as pe
import matplotlib.transforms as mtransforms
from scipy.stats import pearsonr, spearmanr


# ─── Import config ────────────────────────────────────────────────────────────
try:
    from .config import *       # ← quand importé comme module depuis le notebook
except ImportError:
    from config import *        # ← quand exécuté directement avec python functions.py

#############################################################################################


def normalize_raster(raster, d_max, mode="log1p"):
    if mode not in NORM_TRANSFORMS:
        raise ValueError(f"mode inconnu : '{mode}'. Modes disponibles : {list(NORM_TRANSFORMS.keys())}")
    transform_fn = NORM_TRANSFORMS[mode]
    transformed  = np.where(raster > 0, transform_fn(raster), np.nan)
    return np.clip(transformed / d_max, 0, 1)

def compute_scale(rasters_list, clip_percentile, mode="log1p"):
    if mode not in NORM_TRANSFORMS:
        raise ValueError(f"mode inconnu : '{mode}'. Modes disponibles : {list(NORM_TRANSFORMS.keys())}")
    transform_fn = NORM_TRANSFORMS[mode]
    all_vals = np.concatenate([
        transform_fn(r[r > 0])
        for r in rasters_list
        if (r > 0).any()
    ])
    return np.nanpercentile(all_vals, clip_percentile)

# ─── Colormap avec fond blanc ─────────────────────────────────────────────────
def make_cmap(cmap_name):
    cmap = plt.cm.get_cmap(cmap_name).copy()
    cmap.set_bad(color="white")
    cmap.set_under(color="white")
    return cmap

cmap_plot = make_cmap(cmap_name)

# ─── Fonction de plot générique ───────────────────────────────────────────────
def plot_density_map(density_norm, title, extent, canton_GE, girec,
                     focus=None, zoom_bounds=None, margin=200,
                     meta=None,
                     norm_mode_label=None,
                     clip_percentile_label=None):

    # Affiche une carte de densité piétonne.
    #
    # Parameters
    # ----------
    # density_norm          : np.ndarray   → raster normalisé [0, 1]
    # title                 : str          → titre de la figure
    # extent                : list         → [xmin, xmax, ymin, ymax]
    # canton_GE             : GeoDataFrame → contour du canton
    # girec                 : GeoDataFrame → contour des zones GIREC
    # focus                 : GeoDataFrame → commune à mettre en évidence (optionnel)
    # zoom_bounds           : tuple        → (xmin_z, ymin_z, xmax_z, ymax_z) pour zoomer (optionnel)
    # margin                : int          → marge autour du zoom en mètres (défaut 200)
    # meta                  : dict         → métadonnées de build_density_raster (optionnel)
    #                                        si fourni, ajoute automatiquement un subtitle
    # norm_mode_label       : str          → override norm_mode pour le label colorbar (optionnel)
    # clip_percentile_label : int/float    → override clip_percentile pour le label colorbar (optionnel)

    # ─── Fallback sur les variables globales si non spécifié ──────────────────
    _norm_mode       = norm_mode_label       if norm_mode_label       is not None else norm_mode
    _clip_percentile = clip_percentile_label if clip_percentile_label is not None else clip_percentile

    # ─── Subtitle automatique depuis meta ─────────────────────────────────────
    if meta is not None:
        auto_subtitle = (
            f"{meta.get('days_retained', '?')} days | "
            f"≥ {meta.get('effective_threshold', '?')} distinct users/pixel | "
            f"{_norm_mode} | P{_clip_percentile}"
        )
        full_title = f"{title}\n{auto_subtitle}"
    else:
        full_title = title

    fig, ax = plt.subplots(figsize=(10, 10))
    #fig.patch.set_facecolor('white')
    #ax.set_facecolor('white')
    fig.patch.set_alpha(0)  # ← remplace set_facecolor('white') par transparent
    ax.patch.set_alpha(0)   # ← remplace set_facecolor('white') par transparent
    fig.suptitle(full_title, fontsize=14, fontweight="bold")

    im = ax.imshow(density_norm, origin='upper', extent=extent,
                   cmap=cmap_plot, alpha=0.8, vmin=0, vmax=1)
    if canton_GE is not None:
        canton_GE.boundary.plot(ax=ax, color='black', linewidth=1.5)
    if girec is not None:
        girec.boundary.plot(ax=ax, color='gray', linewidth=0.5, alpha=0.4)

    if focus is not None:
        focus.boundary.plot(ax=ax, color='red', linewidth=2)

    if zoom_bounds is not None:
        x0, y0, x1, y1 = zoom_bounds
        ax.set_xlim(x0 - margin, x1 + margin)
        ax.set_ylim(y0 - margin, y1 + margin)

    ax.set_axis_off()
    # Dans plot_density_map et plot_small_multiples
    _label = f"Density (P{_clip_percentile})" if _norm_mode == "linear" \
            else f"Density {_norm_mode} (P{_clip_percentile})"

    cbar = plt.colorbar(im, ax=ax, fraction=0.03, pad=0.01)
    cbar.set_label(_label, size=14)        # ← taille du label
    cbar.ax.tick_params(labelsize=12)      # ← taille des graduations
    plt.tight_layout()
    plt.show()




def plot_small_multiples(rasters_dict, slot_names, labels_dict, title,
                          extent, canton_GE, girec, d_max,
                          focus=None, zoom_bounds=None, margin=200,
                          ncols=4,
                          norm_mode_label=None,
                          clip_percentile_label=None,
                          plot_individual=True,
                          subtitle_fontsize=10,
                          cbar_fontsize=12):

    # Affiche un grid de small multiples pour une liste de slots/groupes,
    # et optionnellement chaque carte individuellement.
    #
    # Parameters
    # ----------
    # rasters_dict          : dict         → {slot_name: raster}
    # slot_names            : list         → noms des slots à afficher
    # labels_dict           : dict         → {slot_name: label affiché}
    # title                 : str          → titre de la figure
    # extent                : list         → [xmin, xmax, ymin, ymax]
    # canton_GE             : GeoDataFrame → contour du canton
    # girec                 : GeoDataFrame → contour des zones GIREC
    # d_max                 : float        → échelle de normalisation commune
    # focus                 : GeoDataFrame → commune à zoomer (optionnel)
    # zoom_bounds           : tuple        → (xmin_z, ymin_z, xmax_z, ymax_z) (optionnel)
    # margin                : int          → marge en mètres (défaut 200)
    # ncols                 : int          → nombre de colonnes (défaut 4)
    # norm_mode_label       : str          → override norm_mode pour le label colorbar (optionnel)
    # clip_percentile_label : int/float    → override clip_percentile pour le label colorbar (optionnel)
    # plot_individual       : bool         → plot aussi chaque carte individuellement (défaut True)
    # subtitle_fontsize     : int          → taille de police des sous-titres (défaut 10)
    # cbar_fontsize         : int          → taille de police du label + ticks colorbar (défaut 12)

    # ─── Fallback sur les variables globales si non spécifié ──────────────────
    _norm_mode       = norm_mode_label       if norm_mode_label       is not None else norm_mode
    _clip_percentile = clip_percentile_label if clip_percentile_label is not None else clip_percentile
    _label           = f"Density (P{_clip_percentile})" if _norm_mode == "linear" \
                       else f"Density {_norm_mode} (P{_clip_percentile})"

    # ─── Grid small multiples ─────────────────────────────────────────────────
    nrows = math.ceil(len(slot_names) / ncols)
    fig, axes = plt.subplots(nrows, ncols, figsize=(20, nrows * 5))
    fig.suptitle(title, fontsize=16, fontweight="bold")
    axes = axes.flatten()

    for i, slot_name in enumerate(slot_names):
        density_norm = normalize_raster(rasters_dict[slot_name], d_max, mode=_norm_mode)

        axes[i].imshow(density_norm, origin='upper', extent=extent,
                       cmap=cmap_plot, vmin=0.001, vmax=1)
        canton_GE.boundary.plot(ax=axes[i], color='black', linewidth=0.8)
        if girec is not None:
            girec.boundary.plot(ax=axes[i], color='gray', linewidth=0.3, alpha=0.3)

        if focus is not None:
            focus.boundary.plot(ax=axes[i], color='red', linewidth=1)

        if zoom_bounds is not None:
            x0, y0, x1, y1 = zoom_bounds
            axes[i].set_xlim(x0 - margin, x1 + margin)
            axes[i].set_ylim(y0 - margin, y1 + margin)

        axes[i].set_title(labels_dict.get(slot_name, slot_name), fontsize=subtitle_fontsize)
        axes[i].set_axis_off()

    for j in range(i + 1, len(axes)):
        axes[j].set_visible(False)

    cbar_ax = fig.add_axes([1.01, 0.15, 0.015, 0.7])
    sm = plt.cm.ScalarMappable(cmap=cmap_plot, norm=plt.Normalize(vmin=0, vmax=1))
    sm.set_array([])
    cbar = fig.colorbar(sm, cax=cbar_ax, label=_label)
    cbar.set_label(_label, fontsize=cbar_fontsize)
    cbar.ax.tick_params(labelsize=cbar_fontsize - 2)

    plt.tight_layout()
    plt.show()

    # ─── Plots individuels ────────────────────────────────────────────────────
    if plot_individual:
        for slot_name in slot_names:
            density_norm = normalize_raster(rasters_dict[slot_name], d_max, mode=_norm_mode)
            label        = labels_dict.get(slot_name, slot_name)

            plot_density_map(
                density_norm,
                title=f"{title} — {label}",
                extent=extent,
                canton_GE=canton_GE,
                girec=girec,
                focus=focus,
                zoom_bounds=zoom_bounds,
                margin=margin,
                norm_mode_label=_norm_mode,
                clip_percentile_label=_clip_percentile
            )




def build_density_raster_v2(gdf_group, raster_height, raster_width, transform,
                             canton_mask, n_days_per_user, sigma=1, verbose=True,
                             output_path=None, raster_name=None):
    """
    Calcule d'un raster de densité piétonne journalière moyenne par user.

    Pour chaque user :
      1. Rasterise ses traces (comptage de passages par pixel)
      2. Divise par n_days_GG (jours de présence dans le canton)
      3. Applique un lissage gaussien
    Puis moyenne sur tous les users valides du groupe.

    Parameters
    ----------
    gdf_group       : GeoDataFrame → legs filtrés sur le groupe souhaité
    raster_height   : int          → hauteur du raster en pixels
    raster_width    : int          → largeur du raster en pixels
    transform       : Affine       → transformation géographique du raster
    canton_mask     : np.ndarray   → masque booléen du canton (True = dans le canton)
    n_days_per_user : dict         → {user_id: n_days_GG}
    sigma           : float        → sigma du lissage gaussien (défaut 1)
    verbose         : bool         → affiche le détail par user (défaut True)
    output_path     : str          → dossier d'export du raster (optionnel)
    raster_name     : str          → nom du fichier sans extension (optionnel)

    Returns
    -------
    raster_mean_clipped : np.ndarray → raster moyenné, NaN hors canton
    meta                : dict       → métadonnées (n_users_valid, n_users_skipped, ...)
    """

    unique_users  = gdf_group["user_id_fors"].unique()
    raster_sum    = np.zeros((raster_height, raster_width), dtype='float32')
    n_users_valid = 0
    n_users_skip  = 0

    for j, user_id in enumerate(unique_users):

        gdf_u  = gdf_group[gdf_group["user_id_fors"] == user_id]
        n_days = n_days_per_user.get(user_id, None)

        if n_days is None or n_days == 0:
            if verbose:
                print(f"  [{j+1}/{len(unique_users)}] user={user_id} | n_days=INVALIDE → skippé")
            n_users_skip += 1
            continue

        if verbose:
            print(f"  [{j+1}/{len(unique_users)}] user={user_id} | n_days={n_days} | n_legs={len(gdf_u)}")

        r = rasterize(
            shapes=((geom, 1) for geom in gdf_u.geometry if geom is not None),
            out_shape=(raster_height, raster_width),
            transform=transform,
            fill=0,
            dtype='float32',
            merge_alg=MergeAlg.add
        )

        r_daily    = r / n_days
        r_smoothed = gaussian_filter(r_daily, sigma=sigma)

        raster_sum    += r_smoothed
        n_users_valid += 1

    if n_users_valid == 0:
        print("  ⚠ Aucun user valide — raster vide retourné")
        return np.full((raster_height, raster_width), np.nan), {}

    # ─── Moyenne sur le groupe ────────────────────────────────────────────────
    raster_mean = raster_sum / n_users_valid

    # ─── Clipping canton ──────────────────────────────────────────────────────
    raster_mean_clipped = raster_mean.copy()
    raster_mean_clipped[~canton_mask] = np.nan

    # ─── Métadonnées ──────────────────────────────────────────────────────────
    meta = {
        "n_users_total"  : len(unique_users),
        "n_users_valid"  : n_users_valid,
        "n_users_skipped": n_users_skip,
        "sigma"          : sigma,
        "pixels_actifs"  : int((raster_mean_clipped > 0).sum()),
        "raster_max"     : float(np.nanmax(raster_mean_clipped)),
        "raster_min"     : float(np.nanmin(raster_mean_clipped)),
    }

    print(f"\n  → {n_users_valid} users valides / {len(unique_users)} total")
    print(f"  → {n_users_skip} users skippés")
    print(f"  → pixels actifs : {meta['pixels_actifs']:,}")
    print(f"  → raster max    : {meta['raster_max']:.6f}")

    # ─── Export GeoTIFF ───────────────────────────────────────────────────────
    if output_path is not None and raster_name is not None:
        import os
        import rasterio
        os.makedirs(output_path, exist_ok=True)
        filepath = os.path.join(output_path, f"{raster_name}.tif")

        with rasterio.open(
            filepath,
            mode    = "w",
            driver  = "GTiff",
            height  = raster_height,
            width   = raster_width,
            count   = 1,
            dtype   = "float32",
            crs     = "EPSG:2056",
            transform = transform,
            nodata  = np.nan
        ) as dst:
            dst.write(raster_mean_clipped, 1)

        print(f"  → raster exporté : {filepath}")
        meta["filepath"] = filepath

    return raster_mean_clipped, meta


def plot_user_contribution(gdf_group, group_filters, group_labels,
                           group_col, title="User contribution by group",
                           show_lowess=True, lowess_frac=0.4):
    
    #Scatter plot of n_days_GG vs n_legs per user for each group.
    #Color encodes daily walking intensity (legs/day).
    #Includes a linear regression trend line with R² coefficient,
    #and optionally a LOWESS curve to visualize the actual shape.

    #Parameters
    #----------
    #gdf_group     : GeoDataFrame → legs filtered on the desired context (e.g. gdf)
    #group_filters : list         → [(group_name, group_value), ...]
    #group_labels  : dict         → {group_name: displayed label}
    #group_col     : str          → filter column name (e.g. "gdr", "age_fr_grouped")
    #title         : str          → figure title
    #show_lowess   : bool         → show LOWESS curve (default True)
    #lowess_frac   : float        → smoothing fraction for LOWESS (default 0.4)
    
    n_groups = len(group_filters)
    n_cols   = min(2, n_groups)
    n_rows   = math.ceil(n_groups / n_cols)

    fig, axes = plt.subplots(n_rows, n_cols, 
                            figsize=(7 * n_cols, 6 * n_rows))
    fig.patch.set_alpha(0)
    axes = axes.flatten() if n_groups > 1 else [axes]

    for idx in range(n_groups, len(axes)):
        axes[idx].set_visible(False)

    #if len(group_filters) == 1:
        #axes = [axes]

    for i, (group_name, group_value) in enumerate(group_filters):
        label    = group_labels.get(group_name, group_name)
        gdf_filt = gdf_group if group_value is None \
                   else gdf_group[gdf_group[group_col] == group_value]

        if len(gdf_filt) == 0:
            print(f"  ⚠ groupe vide : {label} — skipped")
            axes[i].set_visible(False)
            continue

        user_stats = (
            gdf_filt
            .groupby("user_id_fors")
            .agg(
                n_legs    = ("user_id_fors", "count"),
                n_days_GG = ("n_days_GG", "first")
            )
            .reset_index()
        )
        user_stats["legs_per_day"] = user_stats["n_legs"] / user_stats["n_days_GG"]

        median_legs_per_day = np.median(user_stats["legs_per_day"])  # ← nouveau

        x = user_stats["n_days_GG"].values
        y = user_stats["n_legs"].values

        sc = axes[i].scatter(x, y,
                             c=user_stats["legs_per_day"],
                             cmap="BrBG",
                             alpha=0.6,
                             edgecolor="gray",
                             s=30)

        coeffs = np.polyfit(x, y, deg=1)
        trend  = np.poly1d(coeffs)
        x_line = np.linspace(x.min(), x.max(), 100)

        y_pred = trend(x)
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - y.mean()) ** 2)
        r2     = 1 - (ss_res / ss_tot)

        axes[i].plot(x_line, trend(x_line),
                     color="black", linewidth=1, linestyle="--",
                     label=f"linear (slope={coeffs[0]:.2f}, R²={r2:.2f})")

        if show_lowess:
            lowess_vals = lowess(y, x, frac=lowess_frac)
            axes[i].plot(lowess_vals[:, 0], lowess_vals[:, 1],
                         color="grey", linewidth=1, linestyle="-",
                         label=f"lowess (frac={lowess_frac})")

        print(f"  {label} (n={len(user_stats)}) — "
            f"median n_days={np.median(x):.0f} | "
            f"median n_legs={np.median(y):.0f} | "
            f"median legs/day={median_legs_per_day:.2f} | "  # ← nouveau
            f"slope={coeffs[0]:.2f} | R²={r2:.2f}")

        axes[i].set_title(
             f"{label} (n={len(user_stats)})\n"
             f"median n_days={np.median(x):.0f} | "
             f"median n_legs={np.median(y):.0f} | "
             f"median legs/day={median_legs_per_day:.2f}",  # ← nouveau
             fontsize=14
         )
        axes[i].patch.set_alpha(0)
        axes[i].set_xlabel("n_days_GG", fontsize=12)
        axes[i].set_ylabel("n_legs", fontsize=12)
        axes[i].legend(fontsize=12)
        axes[i].tick_params(labelsize=12)
        cbar = plt.colorbar(sc, ax=axes[i], label="legs / day")
        cbar.ax.tick_params(labelsize=12)
        cbar.set_label("legs / day", size=12)

    plt.tight_layout()
    plt.show()



def compute_group_stats(rasters_dict, group_filters, canton_mask,
                        rasters_hourly=None, hourly_range=range(6, 22)):

    rows = []

    for group_name, *_ in group_filters:
        raster         = rasters_dict[group_name]
        active         = raster[raster > 0]
        active_canton  = raster[(raster > 0) & canton_mask]  # ← nouveau
        canton_pixels  = raster[canton_mask]

        if len(active) == 0:
            continue

        n_canton = canton_mask.sum()

        row = {
            "groupe" : group_name,

            # ─── Intensité sur pixels actifs (propre au groupe) ───────────────
            "mean_active"   : np.nanmean(active),
            "median_active" : np.nanmedian(active),
            "p75_active"    : np.nanpercentile(active, 75),
            "p90_active"    : np.nanpercentile(active, 90),
            "p99_active"    : np.nanpercentile(active, 99),
            "max_active"    : active.max(),
            "std_active"    : np.nanstd(active),
            "cv_active"     : np.nanstd(active) / np.nanmean(active),

            # ─── Intensité sur pixels actifs dans le canton ───────────────────
            # → numérateur de intensite_relative, affichable côte à côte avec mean_canton
            # intensite_relative = mean_active_canton / mean_canton
            "mean_active_canton" : np.nanmean(active_canton) if len(active_canton) > 0 else np.nan,

            # ─── Intensité sur tous pixels canton (base commune) ──────────────
            "mean_canton"     : np.nanmean(canton_pixels),
            "std_canton"      : np.nanstd(canton_pixels),
            "cv_canton"       : np.nanstd(canton_pixels) / np.nanmean(canton_pixels)
                                if np.nanmean(canton_pixels) > 0 else np.nan,
            "pct_zero_canton" : (canton_pixels == 0).sum() / n_canton * 100,

            # ─── Étendue spatiale ─────────────────────────────────────────────
            "n_pixels_actifs"    : len(active),
            "pct_canton_couvert" : len(active) / n_canton * 100,

            # ─── Intensité relative ───────────────────────────────────────────
            # = mean_active_canton / mean_canton
            "intensite_relative" : np.nanmean(active_canton) / np.nanmean(canton_pixels)
                                   if np.nanmean(canton_pixels) > 0 and len(active_canton) > 0
                                   else np.nan,

            # ─── Concentration ────────────────────────────────────────────────
            "ratio_p90_median"  : np.nanpercentile(active, 90) / np.nanmedian(active),
            "pct_freq_top10pct" : active[active >= np.nanpercentile(active, 90)].sum()
                                  / active.sum() * 100,
        }
        rows.append(row)

    df_stats = pd.DataFrame(rows).set_index("groupe")

    # ─── Profils temporels ────────────────────────────────────────────────────
    df_hourly = None
    if rasters_hourly is not None:
        hourly_rows = []
        for group_name, *_ in group_filters:
            for h in hourly_range:
                h_key = f"{h:02d}h"
                if h_key not in rasters_hourly[group_name]:
                    continue
                r_h      = rasters_hourly[group_name][h_key]
                active_h = r_h[r_h > 0]
                canton_h = r_h[canton_mask]

                hourly_rows.append({
                    "groupe"      : group_name,
                    "heure"       : h,
                    "mean_active" : np.nanmean(active_h) if len(active_h) > 0 else 0,
                    "mean_canton" : np.nanmean(canton_h),
                    "n_pixels"    : len(active_h),
                })
        df_hourly = pd.DataFrame(hourly_rows)

    return df_stats, df_hourly


def compute_morans(zones_gdf, col, w=None):
    """
    Calculates global Moran's I and LISA for a given variable.

    Parameters
    ----------
    zones_gdf : GeoDataFrame → zones with the variable to analyse
    col       : str          → column name to analyse
    w         : libpysal.weights → weight matrix (Queen by default)

    Returns
    -------
    mi         : global Moran's I
    lisa       : local Moran's I (LISA)
    w          : weight matrix used
    zones_lisa : GeoDataFrame with LISA columns added
    """
    zones = zones_gdf.dropna(subset=[col]).copy()
    zones = zones[zones[col] > 0].copy()  # ← exclude zones with no activity

    if len(zones) < 10:
        print(f"  ⚠ Not enough zones for {col} ({len(zones)})")
        return None, None, None, None

    # ─── Queen weight matrix ──────────────────────────────────────────────────
    if w is None:
        w = libpysal.weights.Queen.from_dataframe(zones, silence_warnings=True)
        w.transform = "r"  # ← row-standardization

    # ─── Global Moran's I ─────────────────────────────────────────────────────
    y  = zones[col].values
    mi = esda.Moran(y, w, permutations=999)

    print(f"  Moran's I = {mi.I:.4f} | p-value = {mi.p_sim:.4f} | "
          f"{'✓ significant' if mi.p_sim < 0.05 else '✗ not significant'}")

    # ─── LISA ─────────────────────────────────────────────────────────────────
    lisa = esda.Moran_Local(y, w, permutations=999, seed=42)
    sig  = lisa.p_sim < 0.05

    labels = np.full(len(zones), "Not significant", dtype=object)
    labels[(lisa.q == 1) & sig] = "High-High"
    labels[(lisa.q == 2) & sig] = "Low-High"
    labels[(lisa.q == 3) & sig] = "Low-Low"
    labels[(lisa.q == 4) & sig] = "High-Low"

    zones["lisa_label"] = labels
    zones["lisa_I"]     = lisa.Is
    zones["lisa_p"]     = lisa.p_sim

    return mi, lisa, w, zones


def compute_lisa_walkindex(zones_lisa, zones_gdf, col, group_label,
                           walk_col="walk_index_norm"):
    """
    Crosses LISA clusters with walk_index to identify critical zones
    and planning opportunities.

    Parameters
    ----------
    zones_lisa  : GeoDataFrame → output from compute_morans()
    zones_gdf   : GeoDataFrame → original zones (for walk_index if missing)
    col         : str          → density column name
    group_label : str          → group label for print output
    walk_col    : str          → walk index column name (default: walk_index)

    Returns
    -------
    zones_typed : GeoDataFrame with zone_type column added
    """

    # ─── Add walk_index if not already present ────────────────────────────────
    if walk_col not in zones_lisa.columns:
        zones_lisa = zones_lisa.merge(
            zones_gdf[["OBJECTID", walk_col]],
            on="OBJECTID", how="left"
        )

    # ─── Walk index thresholds ────────────────────────────────────────────────
    seuil_walk_low  = zones_gdf[walk_col].quantile(0.25)
    seuil_walk_high = zones_gdf[walk_col].quantile(0.75)

    # ─── Zone typology : LISA × walk_index ───────────────────────────────────────
    conditions = {
        "Critical"                    : (zones_lisa["lisa_label"] == "High-High") &
                                        (zones_lisa[walk_col] < seuil_walk_low),
        "Performing"                  : (zones_lisa["lisa_label"] == "High-High") &
                                        (zones_lisa[walk_col] > seuil_walk_high),
        "Opportunity"                 : (zones_lisa["lisa_label"] == "Low-Low") &
                                        (zones_lisa[walk_col] > seuil_walk_high),
        "Low potential"               : (zones_lisa["lisa_label"] == "Low-Low") &
                                        (zones_lisa[walk_col] < seuil_walk_low),
        "High outlier — low walk"     : (zones_lisa["lisa_label"] == "High-Low") &
                                        (zones_lisa[walk_col] < seuil_walk_low),
        "High outlier — high walk"    : (zones_lisa["lisa_label"] == "High-Low") &
                                        (zones_lisa[walk_col] > seuil_walk_high),
        "High outlier — medium walk"  : (zones_lisa["lisa_label"] == "High-Low") &
                                        (zones_lisa[walk_col] >= seuil_walk_low) &
                                        (zones_lisa[walk_col] <= seuil_walk_high),
        "Low outlier — low walk"      : (zones_lisa["lisa_label"] == "Low-High") &
                                        (zones_lisa[walk_col] < seuil_walk_low),
        "Low outlier — high walk"     : (zones_lisa["lisa_label"] == "Low-High") &
                                        (zones_lisa[walk_col] > seuil_walk_high),
        "Low outlier — medium walk"   : (zones_lisa["lisa_label"] == "Low-High") &
                                        (zones_lisa[walk_col] >= seuil_walk_low) &
                                        (zones_lisa[walk_col] <= seuil_walk_high),
    }

    zones_lisa["zone_type"] = "Other"
    for zone_type, condition in conditions.items():
        zones_lisa.loc[condition, "zone_type"] = zone_type

    # ─── Walk index stats by LISA cluster ────────────────────────────────────
    print(f"\n── {group_label} | Walk index by LISA cluster ───────────────────")
    print(f"  {'Cluster':<20} {'n':>5} {'mean':>10} {'median':>10} "
          f"{'min':>10} {'max':>10}")
    print(f"  {'-'*68}")

    for label in ["High-High", "High-Low", "Low-High", "Low-Low", "Not significant"]:
        subset = zones_lisa[zones_lisa["lisa_label"] == label]
        if len(subset) == 0:
            continue
        w_vals = subset[walk_col].dropna()
        if len(w_vals) == 0:
            continue
        print(f"  {label:<20} {len(subset):>5} {w_vals.mean():>10.3f} "
              f"{w_vals.median():>10.3f} {w_vals.min():>10.3f} "
              f"{w_vals.max():>10.3f}")

    # ─── Summary by zone type ─────────────────────────────────────────────────
    print(f"\n── {group_label} | Summary by zone type ────────────────────────")
    print(f"  Walk index threshold low  (P25) : {seuil_walk_low:.3f}")
    print(f"  Walk index threshold high (P75) : {seuil_walk_high:.3f}")
    print()

    """for zone_type in ["Critical", "Performing", "Opportunity",
                      "Low potential", "High outlier", "Low outlier", "Other"]:"""
    for zone_type in ["Critical", "Performing", "Opportunity", "Low potential",
                  "High outlier — low walk", "High outlier — high walk", "High outlier — medium walk",
                  "Low outlier — low walk", "Low outlier — high walk", "Low outlier — medium walk",
                  "Other"]:
        subset = zones_lisa[zones_lisa["zone_type"] == zone_type]
        if len(subset) == 0:
            continue
        print(f"  {zone_type:<20} : {len(subset):>4} zones")

    # ─── Detail by zone type ──────────────────────────────────────────────────

    descriptions = {
    "Critical"                   : "high frequency cluster + low walkability → intervention priority",
    "Performing"                 : "high frequency cluster + high walkability → to maintain",
    "Opportunity"                : "low frequency cluster + high walkability → untapped potential",
    "Low potential"              : "low frequency cluster + low walkability → low potential",
    "High outlier — low walk"    : "isolated high frequency + low walkability → potential issue",
    "High outlier — high walk"   : "isolated high frequency + high walkability → performing outlier",
    "High outlier — medium walk" : "isolated high frequency + medium walkability",
    "Low outlier — low walk"     : "isolated low frequency + low walkability",
    "Low outlier — high walk"    : "isolated low frequency + high walkability → untapped outlier",
    "Low outlier — medium walk"  : "isolated low frequency + medium walkability",
}


    # ─── Colonnes d'identification disponibles ────────────────────────────────
    id_cols      = [c for c in ["NOM", "COMMUNE", "OBJECTID"] if c in zones_lisa.columns]
    display_cols = id_cols + [walk_col, col]

    for zone_type, description in descriptions.items():
        subset = zones_lisa[zones_lisa["zone_type"] == zone_type]
        if len(subset) == 0:
            continue
        print(f"\n  ── {zone_type} ({description})")
        print(subset[display_cols]
              .sort_values(col, ascending=False)
              .to_string(index=False))

    return zones_lisa


def plot_lisa_walkindex(zones_typed, col, title, canton_GE,
                        walk_col="walk_index_norm", zones_gdf=None):
    """
    Plots three maps side by side:
    1. LISA clusters
    2. Normalised walk index
    3. LISA × walk index typology

    Parameters
    ----------
    zones_typed : GeoDataFrame → output from compute_lisa_walkindex()
    col         : str          → density column name
    title       : str          → figure title
    canton_GE   : GeoDataFrame → canton boundary
    walk_col    : str          → walk index column name (default: walk_index_norm)
    """

    # ─── Color maps ───────────────────────────────────────────────────────────
    color_map_lisa = {
        "High-High"      : "#d7191c",
        "Low-Low"        : "#2c7bb6",
        "High-Low"       : "#fdae61",
        "Low-High"       : "#abd9e9",
        "Not significant": "#f0f0f0",
    }

    label_descriptions_lisa = {
        "High-High"      : "High-High — high frequency cluster",
        "Low-Low"        : "Low-Low — low frequency cluster",
        "High-Low"       : "High-Low — high outlier surrounded by low",
        "Low-High"       : "Low-High — low outlier surrounded by high",
        "Not significant": "Not significant",
    }

    color_map_type = {
        "Critical"                   : "#d7191c",   # rouge foncé
        "Performing"                 : "#1a9641",   # vert foncé
        "Opportunity"                : "#74c476",   # vert clair
        "Low potential"              : "#2c7bb6",   # bleu foncé
        "High outlier — low walk"    : "#d6604d",   # rouge-orange
        "High outlier — high walk"   : "#92c5de",   # bleu clair
        "High outlier — medium walk" : "#fdae61",   # orange
        "Low outlier — low walk"     : "#4393c3",   # bleu moyen
        "Low outlier — high walk"    : "#a6d96a",   # vert-jaune
        "Low outlier — medium walk"  : "#abd9e9",   # bleu très clair
        "Other"                      : "#f0f0f0",   # gris
    }

    label_descriptions_type = {
        "Critical"                   : "Critical — high frequency cluster + low walkability",
        "Performing"                 : "Performing — high frequency cluster + high walkability",
        "Opportunity"                : "Opportunity — low frequency cluster + high walkability",
        "Low potential"              : "Low potential — low frequency cluster + low walkability",
        "High outlier — low walk"    : "High outlier — isolated high frequency + low walkability",
        "High outlier — high walk"   : "High outlier — isolated high frequency + high walkability",
        "High outlier — medium walk" : "High outlier — isolated high frequency + medium walkability",
        "Low outlier — low walk"     : "Low outlier — isolated low frequency + low walkability",
        "Low outlier — high walk"    : "Low outlier — isolated low frequency + high walkability",
        "Low outlier — medium walk"  : "Low outlier — isolated low frequency + medium walkability",
        "Other"                      : "Other",
    }

    # ─── Figure ───────────────────────────────────────────────────────────────
    fig = plt.figure(figsize=(24, 10))
    axes = [
        fig.add_axes([0.02, 0.15, 0.30, 0.78]),
        fig.add_axes([0.35, 0.15, 0.30, 0.78]),
        fig.add_axes([0.68, 0.15, 0.30, 0.78]),
    ]
    fig.suptitle(title, fontsize=14, fontweight="bold", y=0.98)

    # ─── Map 1 : LISA clusters ────────────────────────────────────────────────
    zones_gdf.plot(ax=axes[0], color="#e0e0e0", linewidth=0.3, edgecolor="white")
    for label, color in color_map_lisa.items():
        subset = zones_typed[zones_typed["lisa_label"] == label]
        if len(subset) > 0:
            subset.plot(ax=axes[0], color=color, linewidth=0.3,
                        edgecolor="white",
                        label=f"{label_descriptions_lisa[label]} (n={len(subset)})")
    canton_GE.boundary.plot(ax=axes[0], color="black", linewidth=1.5)
    axes[0].set_title("LISA Clusters", fontsize=11, fontweight="bold")
    axes[0].set_axis_off()

    # ─── Map 2 : walk index ───────────────────────────────────────────────────
    """zones_gdf.plot(ax=axes[1], color="#e0e0e0", linewidth=0.3, edgecolor="white")
    zones_typed.plot(
        column=walk_col, cmap="RdYlGn", linewidth=0.3, edgecolor="white",
        legend=True, ax=axes[1],
        legend_kwds={"label": "Walk index", "shrink": 0.6}
    )"""
    # ─── Map 2 : walk index ───────────────────────────────────────────────────────
    zones_gdf.plot(
        column=walk_col, cmap="RdYlGn", linewidth=0.3, edgecolor="white",
        legend=True, ax=axes[1],
        legend_kwds={"label": "Walk index", "shrink": 0.6},
        missing_kwds={"color": "#e0e0e0"}  # ← zones sans walk_index en gris
)
    canton_GE.boundary.plot(ax=axes[1], color="black", linewidth=1.5)
    axes[1].set_title("Walk index", fontsize=11, fontweight="bold")
    axes[1].set_axis_off()

    # ─── Map 3 : LISA × walk index typology ──────────────────────────────────
    zones_gdf.plot(ax=axes[2], color="#e0e0e0", linewidth=0.3, edgecolor="white")
    for zone_type, color in color_map_type.items():
        subset = zones_typed[zones_typed["zone_type"] == zone_type]
        if len(subset) > 0:
            subset.plot(ax=axes[2], color=color, linewidth=0.3,
                        edgecolor="white",
                        label=f"{label_descriptions_type[zone_type]} (n={len(subset)})")
    canton_GE.boundary.plot(ax=axes[2], color="black", linewidth=1.5)
    axes[2].set_title("LISA × Walk index typology", fontsize=11, fontweight="bold")
    axes[2].set_axis_off()

    # ─── Legend LISA (bottom left) ────────────────────────────────────────────
    from matplotlib.patches import Patch
    legend_lisa = [
        Patch(facecolor=color_map_lisa[label], edgecolor="gray",
              label=label_descriptions_lisa[label])
        for label in color_map_lisa
    ]
    leg1 = fig.legend(
        handles=legend_lisa,
        loc="lower left",
        ncol=1,
        fontsize=7,
        bbox_to_anchor=(0.02, 0.0),
        frameon=True,
        title="LISA cluster interpretation",
        title_fontsize=8
    )

    # ─── Legend typology (bottom right) ──────────────────────────────────────
    legend_type = [
        Patch(facecolor=color_map_type[zt], edgecolor="gray",
              label=label_descriptions_type[zt])
        for zt in color_map_type
        if zt != "Other"
    ]
    fig.legend(
        handles=legend_type,
        loc="lower right",
        ncol=1,
        fontsize=7,
        bbox_to_anchor=(0.98, 0.0),
        frameon=True,
        title="Zone typology (LISA × Walk index)",
        title_fontsize=8
    )
    fig.add_artist(leg1)

    plt.show()

def load_raster(output_path, raster_name):
    """
    Load a previously exported GeoTIFF raster.

    Parameters
    ----------
    output_path : str → folder containing the raster
    raster_name : str → filename without extension

    Returns
    -------
    np.ndarray → raster as float32 array
    """
    import rasterio
    filepath = os.path.join(output_path, f"{raster_name}.tif")
    if not os.path.exists(filepath):
        print(f"  ⚠ File not found : {filepath}")
        return None
    with rasterio.open(filepath) as src:
        return src.read(1)
    
def format_val(v):
    """Format a numeric value according to its order of magnitude."""
    if np.isnan(v):
        return ""
    if v == 0:
        return "0"
    if abs(v) >= 100:
        return f"{v:.1f}"
    if abs(v) >= 1:
        return f"{v:.2f}"
    if abs(v) >= 0.01:
        return f"{v:.4f}"
    if abs(v) >= 0.0001:
        return f"{v:.6f}"
    return f"{v:.2e}"



def plot_group_stats(df_stats, title, color_palette=None, label_map=None, show_active_metrics=True):

    metrics_canton = {
        "pct_canton_couvert" : r"$\text{cover}_G$ [%]",
        "mean_active_canton" : r"$\mu_G^{\text{active}}$" + "  [legs·day⁻¹·user⁻¹]",
        "mean_canton"        : r"$\mu_G^{\text{canton}}$" + "  [legs·day⁻¹·user⁻¹]",
        "intensite_relative" : r"$\rho_G$",
    }
    metrics_active = {
        "cv_active"         : "Coefficient of variation",
        "ratio_p90_median"  : "Concentration (P90/median)",
        "pct_freq_top10pct" : "% frequency in top 10% pixels",
    }

    # ─── Text summary ──────────────────────────────────────────────────────────
    groups_raw     = df_stats.index.tolist()
    groups_display = [label_map.get(g, g) for g in groups_raw] if label_map else groups_raw

    all_metrics = {**metrics_canton, **metrics_active}
    col_w  = max(len(l.replace('\n', ' ')) for l in all_metrics.values()) + 2
    name_w = max(len(g) for g in groups_display) + 2

    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

    for section, metrics in [("Canton-based metrics (comparable ✓)", metrics_canton),
                              ("Active-pixel metrics (group-specific ⚠)", metrics_active)]:
        print(f"\n── {section} {'─'*(54 - len(section))}")
        header = f"{'Group':<{name_w}}" + "".join(f"{lbl.replace(chr(10), ' '):>{col_w}}" for lbl in metrics.values())
        print(header)
        print("─" * len(header))
        for g_raw, g_disp in zip(groups_raw, groups_display):
            row = f"{g_disp:<{name_w}}"
            for metric in metrics:
                val = df_stats.loc[g_raw, metric]
                row += f"{format_val(val):>{col_w}}"
            print(row)

    # ─── Plot — uniquement métriques canton sur 1 ligne ───────────────────────
    ncols = len(metrics_canton)
    fig, axes = plt.subplots(1, ncols, figsize=(4 * ncols, 4))
    fig.patch.set_alpha(0)
    #fig.suptitle(title, fontsize=12, fontweight="bold")  # commenter pour export rapport

    colors = color_palette or plt.cm.Set2(np.linspace(0, 1, len(groups_display)))

    for i, (metric, label) in enumerate(metrics_canton.items()):
        ax = axes[i]
        ax.patch.set_alpha(0)
        vals = df_stats[metric].values

        ax.bar(groups_display, vals, color=colors, edgecolor="white", linewidth=0.5)
        #ax.set_title(label, fontsize=9, fontweight="bold")  # commenter pour export rapport
        ax.set_ylabel(label, fontsize=12)
        ax.tick_params(axis='x', rotation=30, labelsize=12)
        ax.tick_params(axis='y', labelsize=12)
        ax.grid(axis='y', alpha=0.3)

        if metric in ("mean_active_canton", "mean_canton"):
            ax.yaxis.set_major_formatter(plt.ScalarFormatter(useMathText=True))
            ax.ticklabel_format(axis='y', style='sci', scilimits=(0, 0))

        valid_vals = vals[~np.isnan(vals)]
        if len(valid_vals) > 0:
            ax.set_ylim(0, max(valid_vals) * 1.15)

    plt.tight_layout()
    plt.show()
    plt.close()


def compute_spatial_correlation(rasters_dict, group_filters, canton_mask,
                                 method="spearman"):
    """
    Calcule la corrélation spatiale pixel par pixel entre tous les groupes.
    Utilise les pixels actifs dans au moins un des deux groupes comparés
    ET dans le canton (base commune).

    Parameters
    ----------
    rasters_dict  : dict       → {group_name: raster_array}
    group_filters : list       → [(group_name, ...), ...]
    canton_mask   : np.ndarray → masque booléen canton (hors lac)
    method        : str        → "spearman" ou "pearson"

    Returns
    -------
    df_corr : DataFrame matrice de corrélation entre groupes
    df_pval : DataFrame matrice des p-values associées
    """
    from scipy.stats import spearmanr, pearsonr

    groups     = [g for g, *_ in group_filters]
    n          = len(groups)
    corr_matrix = np.full((n, n), np.nan)
    pval_matrix = np.full((n, n), np.nan)

    for i, g1 in enumerate(groups):
        for j, g2 in enumerate(groups):
            if i == j:
                corr_matrix[i, j] = 1.0
                pval_matrix[i, j] = 0.0
                continue
            if i > j:  # ← matrice symétrique, on ne calcule que le triangle supérieur
                corr_matrix[i, j] = corr_matrix[j, i]
                pval_matrix[i, j] = pval_matrix[j, i]
                continue

            r1 = rasters_dict[g1]
            r2 = rasters_dict[g2]

            # ─── Masque : pixels actifs dans au moins un groupe ET dans le canton
            mask = canton_mask & (~np.isnan(r1)) & (~np.isnan(r2)) & \
                   ((r1 > 0) | (r2 > 0))

            if mask.sum() < 10:
                continue

            v1 = r1[mask]
            v2 = r2[mask]

            if method == "spearman":
                r, p = spearmanr(v1, v2)
            else:
                r, p = pearsonr(v1, v2)

            corr_matrix[i, j] = r
            pval_matrix[i, j] = p

    df_corr = pd.DataFrame(corr_matrix, index=groups, columns=groups)
    df_pval = pd.DataFrame(pval_matrix, index=groups, columns=groups)

    return df_corr, df_pval




def plot_correlation_matrix(df_corr, df_pval, title, group_labels=None,
                             threshold=None):
    """
    Displays the correlation matrix with p-values.
    Correlations below threshold are shown in light grey if threshold is set.

    Parameters
    ----------
    df_corr      : DataFrame → correlation matrix
    df_pval      : DataFrame → p-value matrix
    title        : str       → figure title
    group_labels : dict      → {group_name: displayed label} (optional)
    threshold    : float     → minimum absolute correlation to highlight (optional)
                               e.g. 0.6 → correlations < 0.6 shown in grey
    """
    import matplotlib.colors as mcolors

    labels = [group_labels.get(g, g) if group_labels else g
              for g in df_corr.index]

    fig, ax = plt.subplots(figsize=(max(6, len(labels)), max(5, len(labels) - 1)))
    fig.suptitle(title, fontsize=13, fontweight="bold")

    im = ax.imshow(df_corr.values, cmap="RdYlGn", vmin=-1, vmax=1, aspect="auto")

    ax.set_xticks(range(len(labels)))
    ax.set_yticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=35, ha="right", fontsize=12)
    ax.set_yticklabels(labels, fontsize=12)

    # ─── Valeurs dans les cellules ────────────────────────────────────────────
    for i in range(len(labels)):
        for j in range(len(labels)):
            r = df_corr.values[i, j]
            p = df_pval.values[i, j]

            if np.isnan(r):
                continue

            # ─── Corrélations sous le seuil → gris discret ───────────────────
            if threshold is not None and i != j and abs(r) < threshold:
                ax.text(j, i, f"{r:.3f}",
                        ha="center", va="center",
                        fontsize=7, color="#cccccc")
                continue

            # ─── Symbole de significativité ───────────────────────────────────
            if i == j:
                sig = ""
            elif p < 0.001:
                sig = "***"
            elif p < 0.01:
                sig = "**"
            elif p < 0.05:
                sig = "*"
            else:
                sig = "ns"

            text_color = "white" if abs(r) > 0.6 else "black"
            ax.text(j, i, f"{r:.3f}", #\n{sig}",
                     ha="center", va="center", fontsize=10,
                     color=text_color,
                     fontweight="bold" if i != j else "normal")

    # ─── Légende seuil ────────────────────────────────────────────────────────
    if threshold is not None:
        ax.set_xlabel(f"Grey = |r| < {threshold} (below threshold)", fontsize=8)

    cbar = plt.colorbar(im, ax=ax, fraction=0.03, pad=0.01,
                     label="Spearman Correlation")
    cbar.set_label("Spearman Correlation", fontsize=12)
    cbar.ax.tick_params(labelsize=12)  # taille des graduations sur l'échelle
    plt.tight_layout()
    plt.show()


def print_correlation_summary(df_corr, df_pval, title, group_labels=None):
    """
    Affiche un résumé textuel des corrélations par paires.
    """
    groups = df_corr.index.tolist()
    print(f"\n{'═'*60}")
    print(f"── {title}")
    print(f"{'═'*60}")
    print(f"{'Pair':<30} {'r':>8} {'p-value':>12} {'Sig':>6} {'Interpretation'}")
    print(f"{'-'*80}")

    for i, g1 in enumerate(groups):
        for j, g2 in enumerate(groups):
            if j <= i:
                continue
            r = df_corr.loc[g1, g2]
            p = df_pval.loc[g1, g2]

            if np.isnan(r):
                continue

            l1 = group_labels.get(g1, g1) if group_labels else g1
            l2 = group_labels.get(g2, g2) if group_labels else g2

            sig = "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else "ns"

            if r >= 0.8:
                interp = "Very strong spatial similarity"
            elif r >= 0.6:
                interp = "Strong spatial similarity"
            elif r >= 0.4:
                interp = "Moderate spatial similarity"
            elif r >= 0.2:
                interp = "Weak spatial similarity"
            else:
                interp = "No spatial similarity"

            print(f"{l1} vs {l2:<20} {r:>8.3f} {p:>12.2e} {sig:>6}  {interp}")




def aggregate_raster_to_area(zones_gdf, rasters_dict, group_filters, transform):
    """
    Enrichit zones_gdf avec les densités piétonnes agrégées par zone.
    Modifie zones_gdf in-place et le retourne.
    Moyenne des valeurs de pixels qui intersectent la zone en question.

    Parameters
    ----------
    zones_gdf    : GeoDataFrame → zones en EPSG:2056 (modifié in-place)
    rasters_dict : dict         → {group_name: raster_array}
    group_filters: list         → [(group_name, ...), ...]
    transform    : Affine       → transform du raster
    """
    for group_name, *_ in group_filters:
        print(f"  Agrégation : {group_name}...")
        raster = rasters_dict[group_name].copy()

        # ─── Remplacer NaN par nodata pour rasterstats ────────────────────────
        raster_filled = np.where(np.isnan(raster), -9999, raster)

        stats = rasterstats.zonal_stats(
            zones_gdf.geometry,
            raster_filled,
            affine=transform,
            stats=["mean", "count"],
            nodata=-9999
        )

        zones_gdf[f"density_{group_name}"] = [
            s["mean"]  if s["mean"]  is not None else np.nan for s in stats
        ]
        zones_gdf[f"n_pixels_{group_name}"] = [
            s["count"] if s["count"] is not None else 0      for s in stats
        ]

        # ─── Normalisation MinMax de la densité ───────────────────────────────
        col         = f"density_{group_name}"
        col_norm    = f"density_{group_name}_norm"
        valid_mask  = zones_gdf[col].notna()
        
        if valid_mask.sum() > 0:
            scaler = MinMaxScaler()
            zones_gdf.loc[valid_mask, col_norm] = scaler.fit_transform(
                zones_gdf.loc[valid_mask, [col]]
            )
        else:
            zones_gdf[col_norm] = np.nan

    return zones_gdf


def plot_synthesis_dashboard(all_results, zones_gdf, filters_dict, labels_dict_all,
                             walk_col="walk_index"):
    """
    Synthesis dashboard combining:
    - Moran's I per group
    - LISA cluster distribution (HH/LL/HL/LH)
    - Mean walk index of HH zones (discrimination proxy)

    Parameters
    ----------
    all_results     : dict         → Moran's I results already computed
    zones_gdf       : GeoDataFrame → with density_* and walk_index columns
    filters_dict    : dict         → {"Gender": gender_filters_with_all, ...}
    labels_dict_all : dict         → {"Gender": {"all": "All users", ...}, ...}
    walk_col        : str          → walk index column name (default: walk_index)
    """

    # ─── Recalculate mean walk_index of HH zones per group ───────────────────
    walk_hh      = {}
    pct_critique = {}

    seuil_walk_low  = zones_gdf[walk_col].quantile(0.25)
    seuil_walk_high = zones_gdf[walk_col].quantile(0.75)

    for dim_label, filters in filters_dict.items():
        labels_dict = labels_dict_all[dim_label]
        for group_name, *_ in filters:
            col   = f"density_{group_name}"
            label = labels_dict.get(group_name, group_name)
            key   = f"{dim_label} — {label}"

            if col not in zones_gdf.columns:
                continue

            mi, _, _, zones_lisa = compute_morans(zones_gdf, col)
            if zones_lisa is None:
                continue

            hh_zones = zones_lisa[zones_lisa["lisa_label"] == "High-High"]
            if len(hh_zones) > 0:
                walk_hh[key]      = hh_zones[walk_col].mean()
                n_critique        = (hh_zones[walk_col] < seuil_walk_low).sum()
                pct_critique[key] = n_critique / len(hh_zones) * 100
            else:
                walk_hh[key]      = np.nan
                pct_critique[key] = np.nan

    # ─── Prepare data ─────────────────────────────────────────────────────────
    keys      = list(all_results.keys())
    I_vals    = [all_results[k]["I"]       for k in keys]
    HH_vals   = [all_results[k]["HH"]      for k in keys]
    LL_vals   = [all_results[k]["LL"]      for k in keys]
    n_vals    = [all_results[k]["n_zones"] for k in keys]
    pct_HH    = [HH_vals[i] / n_vals[i] * 100 if n_vals[i] > 0 else 0 for i in range(len(keys))]
    pct_LL    = [LL_vals[i] / n_vals[i] * 100 if n_vals[i] > 0 else 0 for i in range(len(keys))]
    walk_vals = [walk_hh.get(k, np.nan)    for k in keys]
    crit_vals = [pct_critique.get(k, np.nan) for k in keys]

    # ─── Colors : All users in grey, groups by dimension ─────────────────────
    dim_colors = {
        "Gender"          : "#4C72B0",  # bleu
        "Age"             : "#55A868",  # vert
        "Income"          : "#C44E52",  # rouge
        "Car ownership"   : "#DD8452",  # orange
        "PT subscription" : "#8172B2",  # violet
    }
    bar_colors = []
    for k in keys:
        dim = k.split(" — ")[0]
        if "All users" in k:
            bar_colors.append("#aaaaaa")
        else:
            bar_colors.append(dim_colors.get(dim, "#8C8C8C"))

    short_labels = [k.split(" — ")[1] if " — " in k else k for k in keys]
    x = np.arange(len(keys))

    # ─── Figure ───────────────────────────────────────────────────────────────
    fig = plt.figure(figsize=(22, 18))
    gs  = gridspec.GridSpec(3, 2, figure=fig, hspace=0.45, wspace=0.35)

    ax1 = fig.add_subplot(gs[0, :])
    ax2 = fig.add_subplot(gs[1, 0])
    ax3 = fig.add_subplot(gs[1, 1])
    ax4 = fig.add_subplot(gs[2, 0])
    ax5 = fig.add_subplot(gs[2, 1])

    fig.suptitle(
        f"Synthesis dashboard — Spatial walking patterns by socio-demographic group",
        fontsize=14, fontweight="bold"
    )

    # ─── Dimension separators ─────────────────────────────────────────────────
    def add_dim_separators(ax, keys):
        prev_dim = None
        for i, k in enumerate(keys):
            dim = k.split(" — ")[0]
            if dim != prev_dim and i > 0:
                ax.axvline(i - 0.5, color="gray", linewidth=0.8,
                           linestyle="--", alpha=0.5)
            prev_dim = dim

    # ─── Plot 1 : Moran's I ───────────────────────────────────────────────────
    bars = ax1.bar(x, I_vals, color=bar_colors, edgecolor="white", linewidth=0.5)
    ax1.axhline(0, color="black", linewidth=0.8, linestyle="--")
    for bar, val in zip(bars, I_vals):
        ax1.text(bar.get_x() + bar.get_width() / 2,
                 bar.get_height() + 0.005,
                 f"{val:.3f}", ha='center', va='bottom', fontsize=7)
    add_dim_separators(ax1, keys)
    ax1.set_xticks(x)
    ax1.set_xticklabels(short_labels, rotation=35, ha='right', fontsize=8)
    ax1.set_ylabel("Moran's I")
    ax1.set_title("Moran's I — spatial autocorrelation of walking activity",
                  fontweight="bold")
    ax1.grid(axis='y', alpha=0.3)

    # ─── Plot 2 : % surface HH ────────────────────────────────────────────────
    pct_surf_HH = [all_results[k].get("pct_surface_HH", 0) for k in keys]

    bars2 = ax2.bar(x, pct_surf_HH, color=bar_colors, edgecolor="white", linewidth=0.5)
    for bar, val in zip(bars2, pct_surf_HH):
        if val > 0:
            ax2.text(bar.get_x() + bar.get_width() / 2,
                     bar.get_height() + 0.05,
                     f"{val:.1f}%", ha='center', va='bottom', fontsize=6)
    add_dim_separators(ax2, keys)
    ax2.set_xticks(x)
    ax2.set_xticklabels(short_labels, rotation=35, ha='right', fontsize=7)
    ax2.set_ylabel("% of canton surface")
    ax2.set_title("% Canton surface covered by HH zones\n(pedestrian activity hotspots)",
                  fontweight="bold")
    ax2.grid(axis='y', alpha=0.3)


    # ─── Plot 3 : % LL zones ──────────────────────────────────────────────────
    bars3 = ax3.bar(x, pct_LL, color=bar_colors, edgecolor="white", linewidth=0.5)
    for bar, val in zip(bars3, pct_LL):
        if val > 0:
            ax3.text(bar.get_x() + bar.get_width() / 2,
                     bar.get_height() + 0.3,
                     f"{val:.1f}%", ha='center', va='bottom', fontsize=6)
    add_dim_separators(ax3, keys)
    ax3.set_xticks(x)
    ax3.set_xticklabels(short_labels, rotation=35, ha='right', fontsize=7)
    ax3.set_ylabel("% of analysed zones")
    ax3.set_title("% Low-Low zones\n(pedestrian activity cold spots)",
                  fontweight="bold")
    ax3.grid(axis='y', alpha=0.3)

    # ─── Plot 4 : mean walk index in HH zones ─────────────────────────────────
    bars4 = ax4.bar(x, walk_vals, color=bar_colors, edgecolor="white", linewidth=0.5)
    ax4.axhline(seuil_walk_low,  color="red",   linestyle="--", linewidth=1,
                label=f"P25 {walk_col} = {seuil_walk_low:.3f}")
    ax4.axhline(seuil_walk_high, color="green", linestyle="--", linewidth=1,
                label=f"P75 {walk_col} = {seuil_walk_high:.3f}")
    for bar, val in zip(bars4, walk_vals):
        if not np.isnan(val):
            ax4.text(bar.get_x() + bar.get_width() / 2,
                     bar.get_height() + 0.005,
                     f"{val:.3f}", ha='center', va='bottom', fontsize=6)
    add_dim_separators(ax4, keys)
    ax4.set_xticks(x)
    ax4.set_xticklabels(short_labels, rotation=35, ha='right', fontsize=7)
    ax4.set_ylabel(f"Mean {walk_col}")
    ax4.set_title("Mean walk index in High-High zones\n(↓ = group walks in less walkable areas)",
                  fontweight="bold")
    ax4.legend(fontsize=7)
    ax4.grid(axis='y', alpha=0.3)

    # ─── Plot 5 : % surface critique ─────────────────────────────────────────
    pct_surf_crit = [all_results[k].get("pct_surface_critical_total", 0) for k in keys]

    bars5 = ax5.bar(x, pct_surf_crit, color=bar_colors, edgecolor="white", linewidth=0.5)

    # ─── Décalage dynamique basé sur le max des valeurs ──────────────────────
    max_val = max([v for v in pct_surf_crit if not np.isnan(v) and v > 0], default=1)
    offset  = max_val * 0.02  # ← 2% du max

    for bar, val in zip(bars5, pct_surf_crit):
        if not np.isnan(val) and val > 0:
            ax5.text(bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + offset,
                    f"{val:.3f}%", ha='center', va='bottom', fontsize=6)

    add_dim_separators(ax5, keys)
    ax5.set_xticks(x)
    ax5.set_xticklabels(short_labels, rotation=35, ha='right', fontsize=7)
    ax5.set_ylabel("% of canton surface")
    ax5.set_title("% Canton surface covered by critical zones\n"
              "(HH + walk < P25) + (High outlier + walk < P25)",
              fontweight="bold")
    ax5.grid(axis='y', alpha=0.3)

    # ─── Dimension legend ─────────────────────────────────────────────────────
    legend_handles = [
        Patch(facecolor="#aaaaaa", label="All users (reference)"),
    ] + [
        Patch(facecolor=color, label=dim)
        for dim, color in dim_colors.items()
    ]
    fig.legend(handles=legend_handles, loc="lower center", ncol=6,
               fontsize=9, bbox_to_anchor=(0.5, 0.0),
               frameon=True, title="Socio-demographic dimension", title_fontsize=9)

    #plt.savefig(output_file_path_PL + f"synthesis_dashboard_{profile if profile else 'all'}.png",
                #dpi=150, bbox_inches='tight')
    plt.show()

def find_balanced_percentile(raster_a, raster_b, percentile_range=range(1, 100, 1)):
    """
    Searches for the pooled percentile that minimizes the imbalance
    in the share of active pixels filtered out between group A and B.

    Returns
    -------
    best_percentile : int   → percentile minimizing the asymmetry
    diagnostics      : list → [(percentile, pct_a_filtered, pct_b_filtered, gap), ...]
    """
    r_a = np.where(np.isnan(raster_a), 0, raster_a)
    r_b = np.where(np.isnan(raster_b), 0, raster_b)

    active_a = r_a[r_a > 0]
    active_b = r_b[r_b > 0]
    active_vals = np.concatenate([active_a, active_b])

    diagnostics = []
    for p in percentile_range:
        tau = np.percentile(active_vals, p)
        pct_a_filtered = (active_a < tau).mean() * 100
        pct_b_filtered = (active_b < tau).mean() * 100
        gap = abs(pct_a_filtered - pct_b_filtered)
        diagnostics.append((p, pct_a_filtered, pct_b_filtered, gap))

    best_percentile = min(diagnostics, key=lambda x: x[3])[0]

    print(f"{'P':>4} {'% A filtered':>14} {'% B filtered':>14} {'gap':>8}")
    for p, pa, pb, gap in diagnostics:
        marker = " ← best" if p == best_percentile else ""
        print(f"{p:>4} {pa:>13.1f}% {pb:>13.1f}% {gap:>7.1f}{marker}")

    return best_percentile, diagnostics


def compute_ndpdi(raster_a, raster_b, canton_mask,
                  group_a_label="Group A", group_b_label="Group B",
                  threshold=None, min_intensity_brut=None,
                  min_intensity_percentile=99):  
    """
    Computes the Normalized Difference Pedestrian Density Index (NDPDI)
    between two group rasters.

    NDPDI(p) = (R_A(p) - R_B(p)) / (R_A(p) + R_B(p))

    Adapted from the NDVI principle in remote sensing — normalizes the
    difference by the sum to produce a dimensionless index in [-1, +1],
    independent of absolute intensity levels.

    Parameters
    ----------
    raster_a      : np.ndarray → mean daily pedestrian density for group A
    raster_b      : np.ndarray → mean daily pedestrian density for group B
    canton_mask   : np.ndarray → boolean canton mask (True = within canton)
    group_a_label : str        → label for group A (for print output)
    group_b_label : str        → label for group B (for print output)
    threshold     : float      → minimum |NDPDI| to retain (optional)
                                 pixels below threshold are set to NaN
                                 e.g. 0.2 → only keep strong differences
    min_intensity : float      → minimum intensity threshold (optional)
                                 pixels where BOTH groups are below this value
                                 are set to NaN to remove individual activity noise
                                 if None, computed automatically as given percentile of active pixels

    Returns
    -------
    ndpdi         : np.ndarray → NDPDI values, NaN where both groups absent
                                 or outside canton
    """

    # ─── Remplacer NaN par 0 pour le calcul ───────────────────────────────────
    r_a = np.where(np.isnan(raster_a), 0, raster_a)
    r_b = np.where(np.isnan(raster_b), 0, raster_b)

    # ─── Seuil d'intensité minimale ───────────────────────────────────────────────
    if min_intensity_brut is None:
        active_vals = np.concatenate([
            r_a[r_a > 0],
            r_b[r_b > 0]
        ])
        if len(active_vals) > 0:
            min_intensity_brut = np.percentile(active_vals, min_intensity_percentile)
        else:
            min_intensity_brut = 0

    # ─── Diagnostic : symétrie du filtrage entre A et B ───────────────────────────
    n_a_active        = (r_a > 0).sum()
    n_b_active        = (r_b > 0).sum()
    n_a_filtered_out   = ((r_a > 0) & (r_a < min_intensity_brut)).sum()
    n_b_filtered_out   = ((r_b > 0) & (r_b < min_intensity_brut)).sum()

    print(f"  [diag] {group_a_label}: {n_a_filtered_out:,}/{n_a_active:,} active pixels "
        f"below threshold ({n_a_filtered_out/n_a_active*100:.1f}%)")
    print(f"  [diag] {group_b_label}: {n_b_filtered_out:,}/{n_b_active:,} active pixels "
        f"below threshold ({n_b_filtered_out/n_b_active*100:.1f}%)")

    # ─── Calcul NDPDI ─────────────────────────────────────────────────────────
    numerator   = r_a - r_b
    denominator = r_a + r_b

    # ─── Masquer les pixels où les deux groupes sont absents ──────────────────
    both_absent = denominator == 0
    ndpdi       = np.where(both_absent, np.nan, numerator / denominator)

    # ─── Masquer les pixels sous le seuil d'intensité ─────────────────────────
    # ← les deux groupes doivent être sous le seuil pour masquer
    low_intensity        = (r_a < min_intensity_brut) & (r_b < min_intensity_brut)
    ndpdi[low_intensity] = np.nan

    # ─── Sécurité : clipping canton ───────────────────────────────────────────
    ndpdi[~canton_mask] = np.nan

    # ─── Seuil NDPDI optionnel ────────────────────────────────────────────────
    if threshold is not None:
        ndpdi[np.abs(ndpdi) < threshold] = np.nan

    # ─── Stats ────────────────────────────────────────────────────────────────
    valid = ndpdi[~np.isnan(ndpdi)]

    print(f"\n── NDPDI : A: {group_a_label} vs B: {group_b_label} ──────────────────")
    print(f"  pixels valides    : {len(valid):,}")
    print(f"  pixels A > B      : {(valid > 0).sum():,}  ({(valid > 0).mean()*100:.1f}%)")
    print(f"  pixels B > A      : {(valid < 0).sum():,}  ({(valid < 0).mean()*100:.1f}%)")
    print(f"  pixels égaux (=0) : {(valid == 0).sum():,}")
    print(f"  mean NDPDI        : {valid.mean():.4f}")
    print(f"  min NDPDI         : {valid.min():.4f}")
    print(f"  max NDPDI         : {valid.max():.8f}")
    if threshold is not None:
        print(f"  threshold applied : |NDPDI| ≥ {threshold}")
    if min_intensity_brut is not None:
        print(f"  Min intensity : {min_intensity_brut:.5f}")

    return ndpdi

def plot_ndpdi(ndpdi, title, extent, canton_GE, girec,
               group_a_label="Group A", group_b_label="Group B",
               focus=None, zoom_bounds=None, margin=200,
               canton_mask=None, landmarks=None):
    """
    Plots a NDPDI raster with a diverging colormap centered on 0.
    Areas outside the canton mask are overlaid in white for visual consistency.

    Parameters
    ----------
    ndpdi         : np.ndarray   → NDPDI values in [-1, +1]
    title         : str          → figure title
    extent        : list         → [xmin, xmax, ymin, ymax]
    canton_GE     : GeoDataFrame → canton boundary
    girec         : GeoDataFrame → GIREC zones boundary
    group_a_label : str          → label for group A (positive values)
    group_b_label : str          → label for group B (negative values)
    focus         : GeoDataFrame → commune to highlight (optional)
    zoom_bounds   : tuple        → (xmin_z, ymin_z, xmax_z, ymax_z) (optional)
    margin        : int          → margin in metres (default 200)
    canton_mask   : np.ndarray   → boolean canton mask (True = within canton)
                                   if provided, areas outside are overlaid in white
                                   ensuring visual consistency with raster masking
    landmarks : dict → {label: (x, y)} in EPSG:2056, optional
                       annotates specific points of interest on the map

    """
    cmap_div = plt.cm.RdBu_r.copy()
    cmap_div.set_bad(color="whitesmoke")

    fig, ax = plt.subplots(figsize=(10, 10))
    fig.patch.set_alpha(0)
    ax.patch.set_alpha(0)  
    fig.suptitle(title, fontsize=13, fontweight="bold")

    # ─── Raster NDPDI ─────────────────────────────────────────────────────────
    im = ax.imshow(ndpdi, origin='upper', extent=extent,
                   cmap=cmap_div, vmin=-1, vmax=1, alpha=0.85,
                   zorder=1)

    # ─── Masque blanc par dessus — zones hors canton et lac ───────────────────
    if canton_mask is not None:
        from matplotlib.colors import ListedColormap
        mask_blanc = np.where(canton_mask, np.nan, 1.0).astype(float)
        cmap_blanc = ListedColormap(['white'])
        ax.imshow(mask_blanc, origin='upper', extent=extent,
                  cmap=cmap_blanc, vmin=0, vmax=1, alpha=1.0,
                  zorder=2)  # ← par dessus le raster

    # ─── Boundaries par dessus le masque blanc ────────────────────────────────
    girec.boundary.plot(ax=ax, color='gray', linewidth=0.5, alpha=0.4,
                        zorder=3)  # ← par dessus le masque
    canton_GE.boundary.plot(ax=ax, color='black', linewidth=1.5,
                            zorder=4)  # ← par dessus tout

    if focus is not None:
        focus.boundary.plot(ax=ax, color='black', linewidth=2, linestyle='--',
                            zorder=5)

    if zoom_bounds is not None:
        x0, y0, x1, y1 = zoom_bounds
        ax.set_xlim(x0 - margin, x1 + margin)
        ax.set_ylim(y0 - margin, y1 + margin)

    # ─── Landmarks annotation ──────────────────────────────────────────────

    if landmarks is not None:
        from adjustText import adjust_text
        texts = []
        for label, (x, y) in landmarks.items():
            ax.plot(x, y, marker='*', color='black', markersize=20,
                    markeredgecolor='white', markeredgewidth=0.8, zorder=6)
            t = ax.text(x, y, label, fontsize=14, color='black', fontweight='bold',
                        zorder=6,
                        path_effects=[pe.withStroke(linewidth=2, foreground="white")])
            texts.append(t)
        adjust_text(texts, ax=ax,
                    arrowprops=dict(arrowstyle='-', color='black', lw=2))


    ax.set_axis_off()

    cbar = plt.colorbar(im, ax=ax, fraction=0.03, pad=0.01)
    cbar.set_label(f"$\\delta$\n← {group_b_label} | {group_a_label} →", fontsize=14)    
    cbar.set_ticks([-1, -0.5, 0, 0.5, 1])

    plt.tight_layout()
    plt.show()


def compute_spearman_comparison(
    gdf,                # zones_girec ou carreau_200
    density_col,        # ex. "density_femme", "density_senior"
    index_col_standard, # ex. "walk_index"
    index_col_specific, # ex. "walk_index_women", "walk_index_senior"
    group_label,        # ex. "Women", "Seniors"
):
    """
    Compute Spearman correlation between a group density and two walk indices.

    Parameters
    ----------
    gdf                 : GeoDataFrame → spatial unit (zones_girec or carreau_200)
    density_col         : str → density column for the group
    index_col_standard  : str → standard walk index column
    index_col_specific  : str → group-specific walk index column
    group_label         : str → displayed group name

    Returns
    -------
    dict with results for each walk index
    """
    results = {}

    for wi_col, wi_label in [
        (index_col_standard, "Standard walk index"),
        (index_col_specific, f"{group_label} walk index"),
    ]:
        if wi_col not in gdf.columns:
            print(f"⚠ {wi_col} missing in geodataframe — skipped")
            continue

        if density_col not in gdf.columns:
            print(f"⚠ {density_col} missing in geodataframe — skipped")
            continue

        df = gdf[[density_col, wi_col]].dropna()
        df = df[df[density_col] > 0]

        if len(df) < 10:
            print(f"⚠ Not enough data for {wi_col} — skipped")
            continue

        r, p = spearmanr(df[density_col], df[wi_col])
        sig  = "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else "ns"

        results[wi_col] = {
            "label" : wi_label,
            "r"     : r,
            "p"     : p,
            "sig"   : sig,
            "n"     : len(df),
        }
        print(f"  {wi_label:<30} r={r:.3f} {sig} | n={len(df)}")

    if len(results) == 2:
        delta = results[index_col_specific]["r"] - results[index_col_standard]["r"]
        print(f"\n  Δr ({group_label.lower()} index − standard) = {delta:+.3f}")

    return results



def plot_spearman_comparison(
    results,
    scale_label,
    group_label,
    index_col_standard,
    index_col_specific,
):
    """
    Plot Spearman correlation comparison between standard and group-specific walk index.
    
    Parameters
    ----------
    results             : dict  → comparison results for one spatial scale
    scale_label         : str   → scale name (e.g. "GIREC zones", "200m grid")
    group_label         : str   → displayed group name (e.g. "Women", "Seniors")
    index_col_standard  : str   → standard walk index column name
    index_col_specific  : str   → group-specific walk index column name
    """

    if len(results) < 2:
        print(f"⚠ Not enough results for {scale_label} — skipped")
        return

    fig, ax = plt.subplots(figsize=(6, 5))

    labels = [results[k]["label"] for k in results]
    r_vals = [results[k]["r"]     for k in results]
    sigs   = [results[k]["sig"]   for k in results]

    bars = ax.bar(labels, r_vals, color=["#4C72B0", "#DD8452"],
                  edgecolor="white", alpha=0.85)

    for bar, r, sig in zip(bars, r_vals, sigs):
        ax.text(bar.get_x() + bar.get_width()/2,
                bar.get_height() + 0.005,
                f"r={r:.3f}\n{sig}", ha="center", fontsize=9)

    delta = r_vals[1] - r_vals[0]
    fig.text(0.5, -0.02, f"Δr ({group_label.lower()} index − standard) = {delta:+.3f}",
             ha="center", fontsize=8, style="italic", color="grey")

    ax.set_title(
        f"Spearman correlation — {group_label} density vs walk index ({scale_label})",
        fontweight="bold", fontsize=11
    )
    ax.set_ylim(0, max(r_vals) * 1.25)
    ax.set_ylabel("Spearman r")
    ax.grid(axis="y", alpha=0.3)
    ax.spines[["top", "right"]].set_visible(False)

    plt.tight_layout()
    plt.show()


def plot_linear_comparison(
    gdf,
    density_col,
    index_col_standard,
    index_col_specific,
    group_label,
    scale_label,
):
    """
    Scatter plot with linear regression for standard vs group-specific walk index.

    Parameters
    ----------
    gdf                 : GeoDataFrame → spatial unit (zones_girec or carreau_200)
    density_col         : str → density column for the group
    index_col_standard  : str → standard walk index column
    index_col_specific  : str → group-specific walk index column
    group_label         : str → displayed group name (e.g. "Women", "Seniors")
    scale_label         : str → scale name (e.g. "GIREC zones", "200m grid")

    Returns
    -------
    dict with R² for each walk index
    """

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    fig.suptitle(f"{group_label} pedestrian density vs walk index — {scale_label}",
                 fontweight="bold", fontsize=13)

    r2_store = {}

    for ax, (wi_col, wi_label) in zip(axes, [
        (index_col_standard, "Standard walk index"),
        (index_col_specific, f"{group_label} walk index"),
    ]):
        if wi_col not in gdf.columns:
            print(f"⚠ {wi_col} missing — skipped")
            continue

        df = gdf[[density_col, wi_col]].dropna()
        df = df[df[density_col] > 0]
        n  = len(df)

        z       = np.polyfit(df[wi_col], df[density_col], 1)
        p_trend = np.poly1d(z)
        x_line  = np.linspace(df[wi_col].min(), df[wi_col].max(), 200)

        y_pred = p_trend(df[wi_col])
        ss_res = np.sum((df[density_col] - y_pred) ** 2)
        ss_tot = np.sum((df[density_col] - df[density_col].mean()) ** 2)
        r2     = 1 - (ss_res / ss_tot)

        r2_store[wi_col] = r2

        ax.scatter(df[wi_col], df[density_col],
                   alpha=0.4, s=15, color="#DD8452")
        ax.plot(x_line, p_trend(x_line), color="black", linewidth=1.5, linestyle="--")

        ax.set_title(f"{wi_label}\nR² = {r2:.3f} | n = {n}", fontweight="bold")
        ax.set_xlabel(wi_col)
        ax.set_ylabel(f"{group_label} pedestrian density (legs·day⁻¹·user⁻¹)")
        ax.grid(alpha=0.3)
        ax.spines[["top", "right"]].set_visible(False)

    if len(r2_store) == 2:
        delta_r2 = r2_store[index_col_specific] - r2_store[index_col_standard]
        fig.text(0.5, -0.02,
                 f"ΔR² ({group_label.lower()} index − standard) = {delta_r2:+.3f}",
                 ha="center", fontsize=10, style="italic", color="grey")

    plt.tight_layout()
    plt.show()

    return r2_store

def plot_delta_map(profile, gdf, spatial_level='girec', figsize=(10, 8)):
    """
    Cartographie le delta walk_index entre un profil et le standard.
    
    profile       : str        — 'women', 'senior', etc.
    gdf           : GeoDataFrame — zones_girec ou agglo_carreau
    spatial_level : str        — label pour le titre ('girec' ou 'carreau')
    figsize       : tuple      — taille de la figure
    """
    delta_col = f'delta_{profile}'
    
    if delta_col not in gdf.columns:
        raise ValueError(f"Colonne '{delta_col}' introuvable — vérifier que le profil '{profile}' a bien été intégré")
    
    vmax = gdf[delta_col].abs().quantile(0.95)
    
    fig, ax = plt.subplots(figsize=figsize)
    
    gdf.plot(
        column=delta_col,
        ax=ax,
        cmap='RdYlGn',
        vmin=-vmax,
        vmax=vmax,
        legend=True,
        legend_kwds={
            'label': 'Delta walk_index (profile − standard)',
            'shrink': 0.6
        },
        missing_kwds={'color': 'lightgrey'}
    )
    
    ax.set_title(
        f'Delta Walk Index — {profile} profile vs standard\n'
        f'Spatial level: {spatial_level} | '
        f'Green = better for profile | Red = worse',
        fontsize=11
    )
    ax.set_axis_off()
    plt.tight_layout()
    plt.show()



def compute_quadrants(col_x, col_y, gdf,
                      x_low_percentile=25, x_high_percentile=75,
                      y_low_percentile=25, y_high_percentile=75,
                      x_normalize=False, y_normalize=False):
    """
    Calcule les quadrants avec deux seuils symétriques par variable.

    col_x              : str  — colonne X (ex. densité)
    col_y              : str  — colonne Y (ex. walk_index, desserte_score)
    x_low_percentile   : int  — seuil bas pour X (défaut 25)
    x_high_percentile  : int  — seuil haut pour X (défaut 75)
    y_low_percentile   : int  — seuil bas pour Y (défaut 25)
    y_high_percentile  : int  — seuil haut pour Y (défaut 75)
    x_normalize        : bool — normaliser X via MinMax (défaut True)
    y_normalize        : bool — normaliser Y via MinMax (défaut False)
    """
    gdf = gdf.copy()

    scaler = MinMaxScaler()

    if x_normalize:
        gdf['_x_norm'] = scaler.fit_transform(gdf[[col_x]])
    else:
        gdf['_x_norm'] = gdf[col_x]

    if y_normalize:
        gdf['_y_norm'] = scaler.fit_transform(gdf[[col_y]])
    else:
        gdf['_y_norm'] = gdf[col_y]

    x_low  = gdf['_x_norm'].quantile(x_low_percentile / 100)
    x_high = gdf['_x_norm'].quantile(x_high_percentile / 100)
    y_low  = gdf['_y_norm'].quantile(y_low_percentile / 100)
    y_high = gdf['_y_norm'].quantile(y_high_percentile / 100)

    def assign_quadrant(row):
        high_x = row['_x_norm'] >= x_high
        low_x  = row['_x_norm'] <= x_low
        high_y = row['_y_norm'] >= y_high
        low_y  = row['_y_norm'] <= y_low

        if high_x and low_y:
            return 'Critical'
        elif high_x and high_y:
            return 'Optimal'
        elif low_x and high_y:
            return 'Unexploited'
        elif low_x and low_y:
            return 'Low priority'
        else:
            return 'Neutral'

    gdf['_quadrant'] = gdf.apply(assign_quadrant, axis=1)

    return gdf


def plot_all_quadrants(col_x, col_y, gdf, spatial_level='girec',
                       profile_label='', figsize=(12, 8),
                       x_low_percentile=25, x_high_percentile=75,
                       y_low_percentile=25, y_high_percentile=75,
                       x_normalize=True, y_normalize=False,
                       x_label=None, y_label=None):
    """
    Carte globale des quadrants.
    """
    gdf = compute_quadrants(col_x, col_y, gdf,
                            x_low_percentile, x_high_percentile,
                            y_low_percentile, y_high_percentile,
                            x_normalize, y_normalize)

    color_map = QUADRANT_COLORS

    fig, ax = plt.subplots(figsize=figsize)

    for quadrant in QUADRANT_ORDER:
        color = QUADRANT_COLORS[quadrant]
        subset = gdf[gdf['_quadrant'] == quadrant]
        if len(subset) > 0:
            subset.plot(ax=ax, color=color, edgecolor='black', linewidth=0.3)

    patches = [
        mpatches.Patch(color=color, label=f'{quadrant} (n={len(gdf[gdf["_quadrant"] == quadrant])})')
        for quadrant, color in color_map.items()
        if len(gdf[gdf['_quadrant'] == quadrant]) > 0
    ]
    #ax.legend(handles=patches, loc='lower right', framealpha=0.9,
              #title='Quadrant', fontsize=9, title_fontsize=10)
    # ax.set_title(
    #     f'Priority map — {profile_label}\n'
    #     f'Spatial level: {spatial_level} | '
    #     f'X: {x_label or col_x} (p{x_low_percentile}-p{x_high_percentile}) | '
    #     f'Y: {y_label or col_y} (p{y_low_percentile}-p{y_high_percentile})',
    #     fontsize=11
    #)
    ax.set_axis_off()
    plt.tight_layout()
    plt.show()

    print(f"\n{'='*60}")
    print(f"Quadrant summary — {profile_label}")
    print(f"{'='*60}")
    print(f"X: {x_label or col_x}")
    print(f"   low  = ≤ p{x_low_percentile} | high = ≥ p{x_high_percentile} | neutral = between")
    print(f"Y: {y_label or col_y}")
    print(f"   low  = ≤ p{y_low_percentile} | high = ≥ p{y_high_percentile} | neutral = between")
    print(f"{'─'*60}")
    print(f"  Critical     : X high (≥p{x_high_percentile}) & Y low  (≤p{y_low_percentile})")
    print(f"  Optimal      : X high (≥p{x_high_percentile}) & Y high (≥p{y_high_percentile})")
    print(f"  Unexploited  : X low  (≤p{x_low_percentile}) & Y high (≥p{y_high_percentile})")
    print(f"  Low priority : X low  (≤p{x_low_percentile}) & Y low  (≤p{y_low_percentile})")
    print(f"  Neutral      : between thresholds")
    print(f"{'─'*60}")
    print(gdf['_quadrant'].value_counts().to_string())
    print(f"{'='*60}")

    return gdf


def plot_critical_zones(col_x, col_y, gdf, spatial_level='girec',
                        profile_label='', figsize=(12, 8),
                        x_low_percentile=25, x_high_percentile=75,
                        y_low_percentile=25, y_high_percentile=75,
                        x_normalize=True, y_normalize=False,
                        x_label=None, y_label=None):
    """
    Carte des zones critiques uniquement + liste des sous-secteurs.
    """
    gdf = compute_quadrants(col_x, col_y, gdf,
                            x_low_percentile, x_high_percentile,
                            y_low_percentile, y_high_percentile,
                            x_normalize, y_normalize)

    critical     = gdf[gdf['_quadrant'] == 'Critical']
    non_critical = gdf[gdf['_quadrant'] != 'Critical']

    fig, ax = plt.subplots(figsize=figsize)

    non_critical.plot(ax=ax, color='#f0f0f0', edgecolor='black', linewidth=0.3)
    critical.plot(ax=ax, color='#e3bbb0', edgecolor='black', linewidth=0.3)

    patches = [
        mpatches.Patch(color='#e3bbb0', label=f'Critical (n={len(critical)})'),
        mpatches.Patch(color='#f0f0f0', label=f'Other zones (n={len(non_critical)})')
    ]
    ax.legend(handles=patches, loc='lower right', framealpha=0.9,
              title='Quadrant', fontsize=9, title_fontsize=10)
    ax.set_title(
        f'Critical zones — {profile_label}\n'
        f'Spatial level: {spatial_level} | '
        f'X: {x_label or col_x} (p{x_low_percentile}-p{x_high_percentile}) | '
        f'Y: {y_label or col_y} (p{y_low_percentile}-p{y_high_percentile})',
        fontsize=11
    )
    ax.set_axis_off()
    plt.tight_layout()
    plt.show()

    print(f"\n{'='*50}")
    print(f"Critical zones — {profile_label}")
    print(f"X: {x_label or col_x} | p_low={x_low_percentile} | p_high={x_high_percentile}")
    print(f"Y: {y_label or col_y} | p_low={y_low_percentile} | p_high={y_high_percentile}")
    print(f"{'='*50}")
    print(critical[['NOM', 'COMMUNE','pop_residante_25', 'densite_pop_25', '_x_norm', '_y_norm']]
          .sort_values('_x_norm', ascending=False)
          .rename(columns={
              '_x_norm': x_label or col_x,
              '_y_norm': y_label or col_y
          })
          .to_string(index=False))

    return gdf

def plot_quadrant_scatter(gdf, col_x_norm='_x_norm', col_y_norm='_y_norm',
                          x_low_percentile=25, x_high_percentile=75,
                          y_low_percentile=25, y_high_percentile=75,
                          x_label='Density', y_label='Walk index',
                          title='', figsize=(8, 7),
                          x_log_scale=False, y_log_scale=False,
                          show_trend=True):
    
    color_map = QUADRANT_COLORS

    x_low  = gdf[col_x_norm].quantile(x_low_percentile / 100)
    x_high = gdf[col_x_norm].quantile(x_high_percentile / 100)
    y_low  = gdf[col_y_norm].quantile(y_low_percentile / 100)
    y_high = gdf[col_y_norm].quantile(y_high_percentile / 100)

    x_min_val = gdf[col_x_norm].min()
    x_max_val = gdf[col_x_norm].max()
    y_min_val = gdf[col_y_norm].min()
    y_max_val = gdf[col_y_norm].max()

    # ─── Print des seuils ───────────────────────────────────────────────────
    print(f"X ({x_label}) — min = {x_min_val:.2e} | P{x_low_percentile} = {x_low:.2e} | "
        f"P{x_high_percentile} = {x_high:.2e} | max = {x_max_val:.2e}")
    print(f"Y ({y_label}) — min = {y_min_val:.2e} | P{y_low_percentile} = {y_low:.2e} | "
        f"P{y_high_percentile} = {y_high:.2e} | max = {y_max_val:.2e}")

    fig, ax = plt.subplots(figsize=figsize)
    fig.patch.set_alpha(0)
    ax.patch.set_alpha(0)

    for quadrant, color in color_map.items():
        subset = gdf[gdf['_quadrant'] == quadrant]
        ax.scatter(subset[col_x_norm], subset[col_y_norm],
                  color=color, alpha=1.0, s=60, edgecolor='black',
                  linewidth=0.5)

    if show_trend:
        x = gdf[col_x_norm].values
        y = gdf[col_y_norm].values

        # ─── Filtrer les NaN avant la régression ───────────────────────────────
        valid_mask = ~(np.isnan(x) | np.isnan(y))
        x_valid = x[valid_mask]
        y_valid = y[valid_mask]

        if len(x_valid) > 1:
            coeffs = np.polyfit(x_valid, y_valid, deg=1)
            trend  = np.poly1d(coeffs)
            x_line = np.linspace(x_valid.min(), x_valid.max(), 100)
            y_pred = trend(x_valid)
            ss_res = np.sum((y_valid - y_pred) ** 2)
            ss_tot = np.sum((y_valid - y_valid.mean()) ** 2)
            r2     = 1 - (ss_res / ss_tot)
            ax.plot(x_line, trend(x_line),
                color="black", linewidth=1.5, linestyle="--",
                label=f"linear (slope={coeffs[0]:.2f}, R²={r2:.2f})")
        else:
            print("  ⚠ Not enough valid points to compute trend line")

    ax.axvline(x_low, color='gray', linestyle='--', linewidth=0.8)
    ax.axvline(x_high, color='gray', linestyle='--', linewidth=0.8)
    ax.axhline(y_low, color='gray', linestyle='--', linewidth=0.8)
    ax.axhline(y_high, color='gray', linestyle='--', linewidth=0.8)

    if x_log_scale:
        ax.set_xscale('log')
    if y_log_scale:
        ax.set_yscale('log')

    # ─── Labels des seuils de percentile (toujours entre les deux lignes) ─────────
    y_min, y_max = ax.get_ylim()
    x_min, x_max = ax.get_xlim()

    if x_log_scale:
        x_factor = 1.15
        x_low_pos, x_high_pos = x_low * x_factor, x_high / x_factor   # ← inversé
    else:
        x_offset = (x_max - x_min) * 0.015
        x_low_pos, x_high_pos = x_low + x_offset, x_high - x_offset   # ← inversé

    if y_log_scale:
        y_factor = 1.15
        y_low_pos, y_high_pos = y_low * y_factor, y_high / y_factor   # ← inversé
    else:
        y_offset = (y_max - y_min) * 0.015
        y_low_pos, y_high_pos = y_low + y_offset, y_high - y_offset   # ← inversé

    ax.text(x_low_pos, y_min, 'P25', fontsize=12, color='gray',
            ha='left', va='bottom')      # ← ha inversé : left au lieu de right
    ax.text(x_high_pos, y_min, 'P75', fontsize=12, color='gray',
            ha='right', va='bottom')     # ← ha inversé : right au lieu de left
    ax.text(x_min, y_low_pos, 'P25', fontsize=12, color='gray',
            ha='left', va='bottom')      # ← reste pareil (déjà vers le haut/intérieur)
    ax.text(x_min, y_high_pos, 'P75', fontsize=12, color='gray',
            ha='left', va='top')         # ← va inversé : top au lieu de bottom

    ax.set_xlabel(x_label, fontsize=12)
    ax.set_ylabel(y_label, fontsize=12)
    ax.tick_params(labelsize=10)
    if show_trend:
        ax.legend(fontsize=12, loc='best', framealpha=0.9)
    ax.set_title(title, fontsize=12)

    plt.tight_layout()
    plt.show()


def plot_radar_critical_zones(gdf, attributs_info, profile='standard',
                               col_x=None, col_y=None,
                               spatial_level='girec', mode='classes',
                               x_low_percentile=25, x_high_percentile=75,
                               y_low_percentile=25, y_high_percentile=75,
                               x_normalize=True, y_normalize=False,
                               zone_nom=None, zone_commune=None, figsize=(8, 8), show_title=True):
    """
    Radar chart des attributs pour les zones critiques vs moyenne cantonale.

    gdf                  : GeoDataFrame — GDF brut, les quadrants sont calculés en interne
    attributs_info       : DataFrame    — Excel des attributs
    profile              : str          — 'standard', 'women', 'senior'
    col_x                : str          — colonne X (auto si None)
    col_y                : str          — colonne Y (auto si None)
    spatial_level        : str          — label pour le titre
    mode                 : str          — 'classes' ou 'attributes'
    x_low_percentile     : int          — seuil bas X (défaut 25)
    x_high_percentile    : int          — seuil haut X (défaut 75)
    y_low_percentile     : int          — seuil bas Y (défaut 25)
    y_high_percentile    : int          — seuil haut Y (défaut 75)
    x_normalize          : bool         — normaliser X via MinMax (défaut True)
    y_normalize          : bool         — normaliser Y via MinMax (défaut False)
    zone_nom             : str          — zoom sur une zone spécifique (NOM)
    zone_commune         : str          — zoom sur une commune (COMMUNE)
    figsize              : tuple        — taille de la figure
    """
    # ── Mapping automatique col_x/col_y selon profil ──────────────────────
    profile_defaults = {
        'standard': ('density_all',   'walk_index'),
        'women':    ('density_femme', 'walk_index_women'),
        'senior':   ('density_60+',   'walk_index_senior'),
    }

    if col_x is None or col_y is None:
        if profile not in profile_defaults:
            raise ValueError(f"Profil '{profile}' inconnu — spécifier col_x et col_y manuellement")
        col_x, col_y = profile_defaults[profile]

    # ── Suffix pour les attributs ─────────────────────────────────────────
    suffix = '' if profile == 'standard' else f'_{profile}'

    # ── Prints de vérification ────────────────────────────────────────────
    print(f"{'='*50}")
    print(f"Profile  : {profile}")
    print(f"col_x    : {col_x}")
    print(f"col_y    : {col_y}")
    print(f"Suffix   : '{suffix}'")
    print(f"x_low={x_low_percentile} | x_high={x_high_percentile} | y_low={y_low_percentile} | y_high={y_high_percentile}")
    print(f"{'='*50}")

    # ── Recalcul des quadrants ─────────────────────────────────────────────
    gdf = compute_quadrants(
        col_x, col_y, gdf,
        x_low_percentile=x_low_percentile,
        x_high_percentile=x_high_percentile,
        y_low_percentile=y_low_percentile,
        y_high_percentile=y_high_percentile,
        x_normalize=x_normalize,
        y_normalize=y_normalize
    )

    n_critical = (gdf['_quadrant'] == 'Critical').sum()
    print(f"Zones critiques identifiées : {n_critical}")
    print(f"{'='*50}\n")

    attrs_df = attributs_info[attributs_info['include_in_index'] == True][['attribute', 'Class']].copy()

    # ── Sélection des zones ────────────────────────────────────────────────
    critical = gdf[gdf['_quadrant'] == 'Critical']

    if zone_nom is not None:
        subset       = gdf[gdf['NOM'] == zone_nom]
        label_subset = zone_nom
        if len(subset) == 0:
            raise ValueError(f"Zone '{zone_nom}' introuvable")
    elif zone_commune is not None:
        subset       = gdf[gdf['COMMUNE'] == zone_commune]
        label_subset = f'Commune: {zone_commune} (n={len(subset)})'
        if len(subset) == 0:
            raise ValueError(f"Commune '{zone_commune}' introuvable")
    else:
        subset       = critical
        label_subset = f'Critical zones (n={len(critical)})'

    # ── Calcul des valeurs selon le mode ──────────────────────────────────
    if mode == 'classes':
        classes      = attrs_df['Class'].unique().tolist()
        labels       = classes
        label_colors = [ATTRIBUTS_CLASS_COLORS.get(cls, 'black') for cls in classes]

        mean_subset_vals = []
        mean_canton_vals = []
        for cls in classes:
            cls_attrs = attrs_df[attrs_df['Class'] == cls]['attribute'].tolist()
            cls_cols  = [f'{a}{suffix}' for a in cls_attrs]
            mean_subset_vals.append(subset[cls_cols].mean().mean())
            mean_canton_vals.append(gdf[cls_cols].mean().mean())

    elif mode == 'attributes':
        attrs_sorted = attrs_df.sort_values('Class')
        labels       = attrs_sorted['attribute'].tolist()
        attr_cols    = [f'{a}{suffix}' for a in labels]
        label_colors = [ATTRIBUTS_CLASS_COLORS.get(row['Class'], 'black')
                        for _, row in attrs_sorted.iterrows()]

        mean_subset_vals = subset[attr_cols].mean().tolist()
        mean_canton_vals = gdf[attr_cols].mean().tolist()

    else:
        raise ValueError(f"mode '{mode}' non reconnu — utiliser 'classes' ou 'attributes'")

    # ── Print des valeurs ──────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"Mean values — {label_subset} vs Canton average")
    print(f"{'='*60}")
    print(f"{'Label':<25} {'Critical zones':>15} {'Canton avg':>12} {'Delta':>10}")
    print(f"{'-'*60}")
    for label, val_subset, val_canton in zip(labels, mean_subset_vals, mean_canton_vals):
        delta = val_subset - val_canton
        print(f"  {label:<23} {val_subset:>15.4f} {val_canton:>12.4f} {delta:>+10.4f}")

    # ── Moyennes par classe (toujours affichées, même en mode attributes) ──
    if mode == 'attributes':
        print(f"\n{'─'*60}")
        print(f"Class averages :")
        print(f"{'─'*60}")
        print(f"{'Class':<25} {'Critical zones':>15} {'Canton avg':>12} {'Delta':>10}")
        print(f"{'-'*60}")
        for cls in attrs_df['Class'].unique():
            cls_attrs       = attrs_df[attrs_df['Class'] == cls]['attribute'].tolist()
            cls_cols        = [f'{a}{suffix}' for a in cls_attrs]
            cls_subset_mean = subset[cls_cols].mean().mean()
            cls_canton_mean = gdf[cls_cols].mean().mean()
            delta           = cls_subset_mean - cls_canton_mean
            print(f"  {cls:<23} {cls_subset_mean:>15.4f} {cls_canton_mean:>12.4f} {delta:>+10.4f}")

    print(f"{'='*60}\n")

    # ── Construction radar ────────────────────────────────────────────────
    N      = len(labels)
    angles = np.linspace(0, 2 * np.pi, N, endpoint=False).tolist()
    angles += angles[:1]

    values_subset = mean_subset_vals + [mean_subset_vals[0]]
    values_canton = mean_canton_vals + [mean_canton_vals[0]]

    # ── Plot ──────────────────────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=figsize, subplot_kw=dict(polar=True))

    ax.plot(angles, values_canton, color='steelblue', linewidth=1.5,
            linestyle='--', label='Canton average')
    ax.fill(angles, values_canton, color='steelblue', alpha=0.1)

    ax.plot(angles, values_subset, color='#d73027', linewidth=2,
            label=label_subset)
    ax.fill(angles, values_subset, color='#d73027', alpha=0.2)

    ax.set_xticks(angles[:-1])
    ticklabels = ax.set_xticklabels(labels, fontsize=12, fontweight="bold")
    for ticklabel, color in zip(ticklabels, label_colors):
        ticklabel.set_color(color)

    ax.set_ylim(0, 1)
    ax.set_yticks([0.25, 0.5, 0.75, 1.0])
    ax.set_yticklabels(['0.25', '0.50', '0.75', '1.00'], fontsize=7)
    if show_title:
        ax.set_title(
            f'Attribute profile — {profile} | {label_subset}\n'
            f'Mode: {mode} | Spatial level: {spatial_level} | '
            f'col_x={col_x} | col_y={col_y}\n'
            f'x_low={x_low_percentile} | x_high={x_high_percentile} | '
            f'y_low={y_low_percentile} | y_high={y_high_percentile}',
            fontsize=9, pad=20
        )

    # ── Légende ───────────────────────────────────────────────────────────
    class_patches = [
        mpatches.Patch(color=ATTRIBUTS_CLASS_COLORS.get(cls, 'black'), label=cls)
        for cls in attrs_df['Class'].unique()
    ]
    class_patches += [
        plt.Line2D([0], [0], color='steelblue', linewidth=1.5,
                   linestyle='--', label='Canton average'),
        plt.Line2D([0], [0], color='#d73027', linewidth=2,
                   label=label_subset)
    ]
    ax.legend(handles=class_patches, loc='upper right',
              bbox_to_anchor=(1.4, 1.1), fontsize=8)

    plt.tight_layout()
    plt.show()



def plot_radar_by_area(gdf, attributs_info, group_col, group_values, 
                        group_colors, profile='standard',
                        spatial_level='girec', mode='classes', figsize=(8, 8),
                        show_title=False):
    
    suffix   = '' if profile == 'standard' else f'_{profile}'
    attrs_df = attributs_info[attributs_info['include_in_index'] == True][['attribute', 'Class']].copy()

    if mode == 'classes':
        classes      = attrs_df['Class'].unique().tolist()
        labels       = classes
        label_colors = [ATTRIBUTS_CLASS_COLORS.get(cls, 'black') for cls in classes]
    elif mode == 'attributes':
        attrs_sorted = attrs_df.sort_values('Class')
        labels       = attrs_sorted['attribute'].tolist()
        label_colors = [ATTRIBUTS_CLASS_COLORS.get(row['Class'], 'black')
                        for _, row in attrs_sorted.iterrows()]

    if mode == 'classes':
        canton_vals = []
        for cls in labels:
            cls_cols = [f'{a}{suffix}' for a in attrs_df[attrs_df['Class'] == cls]['attribute']]
            canton_vals.append(gdf[cls_cols].mean().mean())
    else:
        attr_cols   = [f'{a}{suffix}' for a in labels]
        canton_vals = gdf[attr_cols].mean().tolist()

    print(f"\n{'='*70}")
    print(f"Attribute comparison by group — {group_col} | profile: {profile}")
    print(f"{'='*70}")
    print(f"{'Label':<25} {'Canton avg':>12}", end='')
    for g in group_values:
        print(f" {g[:15]:>16}", end='')
    print()
    print(f"{'-'*70}")

    N      = len(labels)
    angles = np.linspace(0, 2 * np.pi, N, endpoint=False).tolist()
    angles += angles[:1]

    fig, ax = plt.subplots(figsize=figsize, subplot_kw=dict(polar=True))
    fig.patch.set_alpha(0)   # ← transparence
    ax.patch.set_alpha(0)    # ← transparence

    vals_canton = canton_vals + [canton_vals[0]]
    ax.plot(angles, vals_canton, color='steelblue', linewidth=1.5,
            linestyle='--', label='Canton average')
    ax.fill(angles, vals_canton, color='steelblue', alpha=0.1)

    all_group_vals = []
    for g, color in zip(group_values, group_colors):
        subset = gdf[gdf[group_col] == g]

        if mode == 'classes':
            group_vals = []
            for cls in labels:
                cls_cols = [f'{a}{suffix}' for a in attrs_df[attrs_df['Class'] == cls]['attribute']]
                group_vals.append(subset[cls_cols].mean().mean())
        else:
            group_vals = subset[attr_cols].mean().tolist()

        all_group_vals.append(group_vals)

        vals_plot = group_vals + [group_vals[0]]
        ax.plot(angles, vals_plot, color=color, linewidth=2, label=f'{g} (n={len(subset)})')
        ax.fill(angles, vals_plot, color=color, alpha=0.15)

    for i, label in enumerate(labels):
        print(f"  {label:<23} {canton_vals[i]:>12.4f}", end='')
        for group_vals in all_group_vals:
            delta = group_vals[i] - canton_vals[i]
            print(f" {group_vals[i]:>8.4f}({delta:>+6.3f})", end='')
        print()
    print(f"{'='*70}\n")

    ax.set_xticks(angles[:-1])
    ticklabels = ax.set_xticklabels(labels, fontsize=12)  # ← fontsize 12
    for ticklabel, color in zip(ticklabels, label_colors):
        ticklabel.set_color(color)
        ticklabel.set_fontweight('bold')  # ← gras

    ax.set_ylim(0, 1)
    ax.set_yticks([0.25, 0.5, 0.75, 1.0])
    ax.set_yticklabels(['0.25', '0.50', '0.75', '1.00'], fontsize=10)  # ← fontsize 12

    if show_title:  # ← titre optionnel
        ax.set_title(
            f'Attribute profile by {group_col} | profile: {profile}\nMode: {mode} | {spatial_level}',
            fontsize=12, pad=20
        )

    class_patches = [
        mpatches.Patch(color=ATTRIBUTS_CLASS_COLORS.get(cls, 'black'), label=cls)
        for cls in attrs_df['Class'].unique()
    ]
    class_patches += [
        plt.Line2D([0], [0], color='steelblue', linewidth=1.5, linestyle='--', label='Canton average')
    ]
    for g, color in zip(group_values, group_colors):
        class_patches.append(plt.Line2D([0], [0], color=color, linewidth=2, label=g))

    ax.legend(handles=class_patches, loc='upper right', 
              bbox_to_anchor=(1.5, 1.1), fontsize=8)  # ← fontsize 12
    plt.tight_layout()
    plt.show()


print(clip_percentile)
print("functions.py - All is good")