# =========================
# Analyse des répondants Genève depuis OPAL
# =========================

# --- 1. Chargement des packages ---
library(opalr)
library(jsonlite)
library(dplyr)
library(sf)
library(arrow)

# --- 2. Connexion à OPAL et chargement des données ---
token_file <- "..."
opal_token <- readLines(token_file, warn = FALSE)
opal_url   <- "..."

output_dir_wave1_mobility <- "/Volumes/T7_lin_win/PANEL_LEMANIQUE/WAVE1_MOBILITY/OUTPUT/"
output_dir_wave_rythme_R  <- "/Volumes/T7_lin_win/PANEL_LEMANIQUE/WAVE_RYTHM/OUTPUT_R/"

o <- opal.login(token = opal_token, url = opal_url)

df_wave1  <- opal.table_get(o, "Panel_Lemanique", "wave1")
df_rythme <- opal.table_get(o, "Panel_Lemanique", "rythme")

colnames(df_wave1)
colnames(df_rythme)

# --- 3. Extraction des coordonnées des répondants Wave1 ---
extract_coords <- function(x) {
  if (is.na(x) || x == "") return(c(NA, NA))
  parsed <- tryCatch(fromJSON(x), error = function(e) NULL)
  if (is.null(parsed)) return(c(NA, NA))
  if (is.list(parsed) && length(parsed) > 0) {
    return(c(parsed[[1]]$lat, parsed[[1]]$lng))
  }
  return(c(NA, NA))
}

coords <- t(sapply(df_wave1$Q14, extract_coords))

df_clean_wave1 <- df_wave1 %>%
  mutate(lat = coords[,1], lon = coords[,2])

# --- 4. Filtrer les répondants géolocalisés ---
df_geo_wave1 <- df_clean_wave1 %>%
  filter(!is.na(lat) & !is.na(lon))

cat("Total répondants wave1:         ", nrow(df_clean_wave1), "\n")
cat("  dont géolocalisés:            ", nrow(df_geo_wave1), "\n")
cat("  dont non géolocalisés:        ", nrow(df_clean_wave1) - nrow(df_geo_wave1), "\n")

# --- 5. Conversion en objet spatial SF ---
points_sf_wave1 <- st_as_sf(df_geo_wave1, coords = c("lon", "lat"), crs = 4326)

# --- 6. Chargement du polygone du canton de Genève ---
canton_file <- "Data/input/network_agreg/CANTON_GE/CANTON_POLYGON.shp"
canton <- st_read(canton_file)

# --- 7. Reprojection et intersection spatiale ---
points_sf_wave1     <- st_transform(points_sf_wave1, st_crs(canton))
geneve_points_wave1 <- st_intersection(points_sf_wave1, canton)

cat("Points dans Genève:", nrow(geneve_points_wave1), "/", nrow(df_geo_wave1), "\n")

# --- 8. Exports wave1 ---
if (!dir.exists(output_dir_wave1_mobility)) {
  dir.create(output_dir_wave1_mobility, recursive = TRUE)
}

# Tous les répondants géolocalisés (toutes colonnes)
gpkg_file_all <- file.path(output_dir_wave1_mobility, "respondants_all_wave1.gpkg")
st_write(points_sf_wave1, gpkg_file_all, delete_dsn = TRUE)
cat("GeoPackage exporté (tous):", gpkg_file_all, "\n")

write.csv(st_drop_geometry(points_sf_wave1),
          file.path(output_dir_wave1_mobility, "respondants_all_wave1.csv"), row.names = FALSE)
write_parquet(st_drop_geometry(points_sf_wave1),
              file.path(output_dir_wave1_mobility, "respondants_all_wave1.parquet"))
cat("CSV + Parquet exportés (tous répondants)\n")

# Répondants Genève uniquement (toutes colonnes)
geneve_points_wave1 <- geneve_points_wave1 %>%
  select(-any_of("FID")) 

gpkg_file_ge <- file.path(output_dir_wave1_mobility, "respondants_geneve_wave1.gpkg")
st_write(geneve_points_wave1, gpkg_file_ge, delete_dsn = TRUE)
cat("GeoPackage exporté (Genève):", gpkg_file_ge, "\n")

coords_matrix <- st_coordinates(geneve_points_wave1)
geneve_csv <- geneve_points_wave1 %>%
  mutate(X = coords_matrix[,1], Y = coords_matrix[,2]) %>%
  st_drop_geometry()
write.csv(geneve_csv,
          file.path(output_dir_wave1_mobility, "respondants_geneve_wave1.csv"), row.names = FALSE)
write_parquet(st_drop_geometry(geneve_points_wave1),
              file.path(output_dir_wave1_mobility, "respondants_geneve_wave1.parquet"))
cat("CSV + Parquet exportés (Genève)\n")
cat("\n Tous les exports wave1 sont terminés avec succès.\n")


# ------------------------------------------------------------------- #


# --- 11. Export de tous les répondants rythme (niveau répondant) ---

df_rythme_all <- df_rythme %>%
  mutate(
    lat_insecure    = P2_Q12a_Latitude,
    lon_insecure    = P2_Q12a_Longitude,
    justif_insecure = P2_Q12b_R,
    lat_secure      = P2_Q13a_Latitude,
    lon_secure      = P2_Q13a_Longitude,
    justif_secure   = P2_Q13b_R,
    has_insecurity  = !is.na(P2_Q12a_Latitude),
    has_security    = !is.na(P2_Q13a_Latitude),
    across(where(~ inherits(., "haven_labelled")), ~ as.character(.))
  )

cat("Total répondants rythme:", nrow(df_rythme_all), "\n")
cat("  avec spot insécurité:", sum(df_rythme_all$has_insecurity), "\n")
cat("  avec spot sécurité:  ", sum(df_rythme_all$has_security), "\n")

csv_file_rythme_all     <- file.path(output_dir_wave_rythme_R, "respondants_rythme_all.csv")
parquet_file_rythme_all <- file.path(output_dir_wave_rythme_R, "respondants_rythme_all.parquet")
write.csv(df_rythme_all, csv_file_rythme_all, row.names = FALSE)
write_parquet(df_rythme_all, parquet_file_rythme_all)
cat("Exports répondants rythme (tous) terminés.\n\n")

# --- 12. Extraction des points sécurité/insécurité depuis df_rythme_all ---

prepare_spots <- function(df, lat_col, lon_col, spot_label) {
  
  justif_to_drop <- if (spot_label == "insecurity") "justif_secure" else "justif_insecure"
  
  df %>%
    filter(.data[[paste0("has_", spot_label)]]) %>%
    rename(lat = all_of(lat_col), lon = all_of(lon_col)) %>%
    select(-any_of(c("lat_insecure", "lon_insecure", "has_insecurity",
                     "lat_secure",   "lon_secure",   "has_security",
                     justif_to_drop))) %>%
    mutate(
      spot_type = spot_label,
      lat = as.numeric(as.character(lat)),
      lon = as.numeric(as.character(lon))
    ) %>%
    st_as_sf(coords = c("lon", "lat"), crs = 4326) %>%
    st_transform(st_crs(canton)) %>%
    st_intersection(canton) %>%
    select(-any_of("FID")) %>%
    mutate(across(where(~ inherits(., "haven_labelled")), ~ as.character(.)))
}

spots_insecurity <- prepare_spots(df_rythme_all, "lat_insecure", "lon_insecure", "insecurity")
spots_security   <- prepare_spots(df_rythme_all, "lat_secure",   "lon_secure",   "security")

cat("Points d'insécurité dans Genève:", nrow(spots_insecurity), "/", sum(df_rythme_all$has_insecurity), "\n")
cat("Points de sécurité dans Genève: ", nrow(spots_security),   "/", sum(df_rythme_all$has_security),   "\n")

# --- 13. Fonction d'export (GPKG + CSV + Parquet) ---
export_spots <- function(sf_obj, label, output_path) {

  gpkg_file <- file.path(output_path, paste0("spots_", label, ".gpkg"))
  st_write(sf_obj, gpkg_file, delete_dsn = TRUE)
  cat("GeoPackage exporté:", gpkg_file, "\n")

  coords_matrix <- st_coordinates(sf_obj)
  csv_df <- sf_obj %>%
    mutate(X = coords_matrix[, 1], Y = coords_matrix[, 2]) %>%
    st_drop_geometry()
  csv_file <- file.path(output_path, paste0("spots_", label, ".csv"))
  write.csv(csv_df, csv_file, row.names = FALSE)
  cat("CSV exporté:        ", csv_file, "\n")

  parquet_file <- file.path(output_path, paste0("spots_", label, ".parquet"))
  write_parquet(st_drop_geometry(sf_obj), parquet_file)
  cat("Parquet exporté:    ", parquet_file, "\n\n")
}

# --- 14. Exports ---
export_spots(spots_insecurity, "insecurity", output_dir_wave_rythme_R)
export_spots(spots_security,   "security",   output_dir_wave_rythme_R)

cat("\n Tous les exports sont terminés avec succès.\n")

# --- 15. Déconnexion d'OPAL ---
opal.logout(o)
cat("Session OPAL terminée.\n")