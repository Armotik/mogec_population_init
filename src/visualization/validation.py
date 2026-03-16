"""
Fonctions de validation scientifique pour les sorties du modele.

Le but n'est pas d'"etablir une "verite terrain", mais de documenter la
coherence interne du resultat exporte :
- qualite structurelle du GeoPackage ;
- ordres de grandeur demographiques ;
- comportement horaire global ;
- adequation entre cibles config et roles realises ;
- poids des composantes non residentielles.
"""

from __future__ import annotations

import geopandas as gpd
import pandas as pd


def _hourly_columns(gdf: gpd.GeoDataFrame) -> list[str]:
    return sorted(
        [col for col in gdf.columns if col.startswith("pop_h")],
        key=lambda name: int(name.replace("pop_h", "")),
    )


def structural_quality_report(gdf: gpd.GeoDataFrame) -> pd.DataFrame:
    """
    Produit un tableau de controle simple sur la structure du fichier exporte.
    """
    hourly_cols = _hourly_columns(gdf)
    duplicate_buildings = int(gdf["building_id"].duplicated().sum()) if "building_id" in gdf.columns else -1
    null_geometries = int(gdf.geometry.isna().sum()) if hasattr(gdf, "geometry") else -1
    negative_cells = int((gdf[hourly_cols] < 0).sum().sum()) if hourly_cols else 0

    rows = [
        ("row_count", len(gdf), "Nombre total d'entites exportees."),
        ("hourly_column_count", len(hourly_cols), "Le modele attendu est une matrice 24h complete."),
        ("duplicate_building_id", duplicate_buildings, "Doit rester nul pour garantir la tracabilite."),
        ("null_geometries", null_geometries, "Doit rester nul pour les analyses spatiales."),
        ("negative_hourly_values", negative_cells, "Une population negative indique une erreur de generation."),
    ]
    return pd.DataFrame(rows, columns=["check", "value", "interpretation"])


def summarize_export_metrics(gdf: gpd.GeoDataFrame) -> pd.DataFrame:
    """
    Resume les principaux ordres de grandeur du fichier exporte.
    """
    hourly_cols = _hourly_columns(gdf)
    pop_t0 = int(gdf["pop_t0"].fillna(0).sum()) if "pop_t0" in gdf.columns else 0
    inhabited_t0 = int((gdf["pop_t0"].fillna(0) > 0).sum()) if "pop_t0" in gdf.columns else 0

    hourly_totals = gdf[hourly_cols].fillna(0).sum() if hourly_cols else pd.Series(dtype=float)
    hourly_min = int(hourly_totals.min()) if not hourly_totals.empty else 0
    hourly_max = int(hourly_totals.max()) if not hourly_totals.empty else 0
    hourly_mean = float(hourly_totals.mean()) if not hourly_totals.empty else 0.0
    hourly_std = float(hourly_totals.std()) if not hourly_totals.empty else 0.0
    peak_hour = hourly_totals.idxmax().replace("pop_h", "h") if not hourly_totals.empty else "n/a"

    nonres_accommodation = int(gdf.get("pop_nonres_accommodation", pd.Series(dtype=float)).fillna(0).sum())
    nonres_activity = int(gdf.get("pop_nonres_activity", pd.Series(dtype=float)).fillna(0).sum())
    overlap_excluded = int(
        gdf.get("accommodation_overlap_action", pd.Series(dtype=object))
        .fillna("")
        .eq("excluded_residential_overlap")
        .sum()
    )

    rows = [
        ("population_t0", pop_t0, "Population presente dans l'etat initial."),
        ("batiments_habites_t0", inhabited_t0, "Batiments portant une population strictement positive a T0."),
        ("population_horaire_min", hourly_min, "Minimum de population totale observe sur 24h."),
        ("population_horaire_max", hourly_max, "Maximum de population totale observe sur 24h."),
        ("heure_pic_global", peak_hour, "Heure ou la population totale est maximale."),
        ("population_horaire_moyenne", round(hourly_mean, 2), "Moyenne des totaux horaires."),
        ("population_horaire_ecart_type", round(hourly_std, 2), "Dispersion globale du cycle journalier."),
        ("pop_nonres_accommodation", nonres_accommodation, "Contribution touristique/hebergement a T0."),
        ("pop_nonres_activity", nonres_activity, "Contribution des activites a T0."),
        ("batiments_overlap_exclus", overlap_excluded, "Batiments exclus pour limiter le double comptage."),
    ]
    return pd.DataFrame(rows, columns=["metric", "value", "interpretation"])


def hourly_population_profile(gdf: gpd.GeoDataFrame) -> pd.DataFrame:
    """
    Retourne la serie horaire aggregatee, avec variation absolue et relative.
    """
    hourly_cols = _hourly_columns(gdf)
    if not hourly_cols:
        return pd.DataFrame(columns=["hour", "population", "delta_abs", "delta_pct"])

    populations = [float(gdf[col].fillna(0).sum()) for col in hourly_cols]
    series = pd.DataFrame(
        {
            "hour": [int(col.replace("pop_h", "")) for col in hourly_cols],
            "population": populations,
        }
    )
    series["delta_abs"] = series["population"].diff().fillna(0.0)
    series["delta_pct"] = series["population"].pct_change().replace([pd.NA, pd.NaT], 0.0).fillna(0.0) * 100.0
    return series


def role_targets_vs_realized(gdf: gpd.GeoDataFrame, config: dict) -> pd.DataFrame:
    """
    Compare la structure demographique cible du scenario avec le resultat obtenu.
    """
    pop_t0 = int(gdf["pop_t0"].fillna(0).sum()) if "pop_t0" in gdf.columns else 0
    if pop_t0 == 0:
        return pd.DataFrame(columns=["role", "target_count", "realized_count", "target_share", "realized_share", "gap_count", "gap_share_pp"])

    age_cfg = config["demographics"]["age_pyramid"]
    employment_cfg = config["demographics"]["employment"]

    target_counts = {
        "scolaire": int(round(pop_t0 * float(age_cfg["under_15"]))),
        "senior": int(round(pop_t0 * float(age_cfg["over_65"]))),
    }
    n_active = max(0, pop_t0 - target_counts["scolaire"] - target_counts["senior"])
    target_counts["actif_local"] = int(round(n_active * float(employment_cfg["travail_local_pct"])))
    target_counts["actif_navetteur"] = max(0, n_active - target_counts["actif_local"])

    realized_counts = {
        "scolaire": int(gdf.get("n_scolaire", pd.Series(dtype=float)).fillna(0).sum()),
        "senior": int(gdf.get("n_senior", pd.Series(dtype=float)).fillna(0).sum()),
        "actif_local": int(gdf.get("n_actif_local", pd.Series(dtype=float)).fillna(0).sum()),
        "actif_navetteur": int(gdf.get("n_actif_navetteur", pd.Series(dtype=float)).fillna(0).sum()),
    }

    rows = []
    for role in ["scolaire", "senior", "actif_local", "actif_navetteur"]:
        target_share = target_counts[role] / pop_t0
        realized_share = realized_counts[role] / pop_t0
        rows.append(
            {
                "role": role,
                "target_count": target_counts[role],
                "realized_count": realized_counts[role],
                "target_share": target_share,
                "realized_share": realized_share,
                "gap_count": realized_counts[role] - target_counts[role],
                "gap_share_pp": (realized_share - target_share) * 100.0,
            }
        )
    return pd.DataFrame(rows)


def non_residential_validation(gdf: gpd.GeoDataFrame) -> pd.DataFrame:
    """
    Resume les composantes non residentielles et leurs traces d'audit.
    """
    rows = []
    for col, label in [
        ("pop_nonres_accommodation", "Hebergement touristique"),
        ("pop_nonres_activity", "Activites et equipements"),
    ]:
        if col in gdf.columns:
            values = gdf[col].fillna(0)
            rows.append(
                {
                    "component": label,
                    "population": int(values.sum()),
                    "batiments_concernes": int((values > 0).sum()),
                    "part_de_pop_t0_pct": round((values.sum() / max(1.0, gdf["pop_t0"].fillna(0).sum())) * 100.0, 2),
                }
            )

    overlap_actions = (
        gdf.get("accommodation_overlap_action", pd.Series(dtype=object))
        .fillna("non_renseigne")
        .value_counts()
        .rename_axis("component")
        .reset_index(name="population")
    )
    overlap_actions["batiments_concernes"] = overlap_actions["population"]
    overlap_actions["part_de_pop_t0_pct"] = None

    result = pd.DataFrame(rows, columns=["component", "population", "batiments_concernes", "part_de_pop_t0_pct"])
    if overlap_actions.empty:
        return result
    overlap_actions["component"] = "Audit overlap - " + overlap_actions["component"].astype(str)
    return pd.concat([result, overlap_actions[result.columns]], ignore_index=True)


def temporal_variation_buildings(gdf: gpd.GeoDataFrame, top_n: int = 25) -> gpd.GeoDataFrame:
    """
    Identifie les batiments les plus variables sur le cycle de 24h.
    """
    hourly_cols = _hourly_columns(gdf)
    if not hourly_cols:
        return gdf.iloc[0:0].copy()

    result = gdf[["building_id", "usage_1", "geometry"]].copy()
    hourly_values = gdf[hourly_cols].fillna(0)
    result["min_pop"] = hourly_values.min(axis=1)
    result["max_pop"] = hourly_values.max(axis=1)
    result["amplitude"] = result["max_pop"] - result["min_pop"]
    result["mean_pop"] = hourly_values.mean(axis=1)
    result["peak_hour"] = hourly_values.idxmax(axis=1).str.replace("pop_h", "h", regex=False)
    result = result.sort_values(["amplitude", "max_pop"], ascending=False).head(top_n)
    return gpd.GeoDataFrame(result, geometry="geometry", crs=gdf.crs)


def occupied_buildings_by_usage(gdf: gpd.GeoDataFrame) -> pd.DataFrame:
    """
    Agrege les batiments occupes a T0 par type d'usage.
    """
    if "pop_t0" not in gdf.columns or "usage_1" not in gdf.columns:
        return pd.DataFrame(columns=["usage_1", "population_t0", "batiments"])

    occupied = gdf[gdf["pop_t0"].fillna(0) > 0].copy()
    result = (
        occupied.groupby("usage_1", as_index=False)
        .agg(
            population_t0=("pop_t0", "sum"),
            batiments=("building_id", "count"),
        )
        .sort_values("population_t0", ascending=False)
    )
    return result
