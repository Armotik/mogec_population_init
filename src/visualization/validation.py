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

from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd


def _hourly_columns(gdf: gpd.GeoDataFrame) -> list[str]:
    return sorted(
        [col for col in gdf.columns if col.startswith("pop_h")],
        key=lambda name: int(name.replace("pop_h", "")),
    )


def _reference_hour_from_config(config: dict) -> int:
    return int(config.get("scenario", {}).get("reference_hour", 0))


def _reference_hour_from_gdf(gdf: gpd.GeoDataFrame) -> int:
    if "reference_hour" in gdf.columns and not gdf["reference_hour"].dropna().empty:
        return int(gdf["reference_hour"].dropna().iloc[0])
    return 0


def _hour_column_name(hour: int) -> str:
    return f"pop_h{int(hour)}"


def _status_for_threshold(value: float, pass_threshold: float, warn_threshold: float) -> str:
    if value <= pass_threshold:
        return "pass"
    if value <= warn_threshold:
        return "warn"
    return "fail"


def _status_color(status: str) -> str:
    return {
        "pass": "#1d8348",
        "warn": "#b9770e",
        "fail": "#b03a2e",
    }.get(status, "#475569")


def _evidence_is_complete(evidence: dict) -> bool:
    required = ["formula", "source_name", "extraction_date", "confidence"]
    has_required_fields = all(str(evidence.get(field, "")).strip() for field in required)
    has_traceable_source = any(str(evidence.get(field, "")).strip() for field in ["source_url", "source_file"])
    return has_required_fields and has_traceable_source


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


def evidence_traceability_report(config: dict) -> pd.DataFrame:
    """
    Controle la tracabilite minimale des briques non residentielles activees.
    """
    labels = {
        "accommodation": "Hebergement touristique",
        "activities": "Activites et equipements",
        "beaches": "Plages exogenes",
    }
    rows = []

    for section_name, label in labels.items():
        section = config.get("non_residential_model", {}).get(section_name, {})
        enabled = bool(section.get("enabled", False))
        evidence = section.get("evidence", {}) if enabled else {}
        is_complete = _evidence_is_complete(evidence) if enabled else True
        source = evidence.get("source_name") or evidence.get("source_file") or evidence.get("source_url") or "n/a"
        rows.append(
            {
                "section": section_name,
                "label": label,
                "enabled": enabled,
                "status": "pass" if is_complete else "fail",
                "confidence": evidence.get("confidence", "n/a") if enabled else "n/a",
                "source": source,
                "extraction_date": evidence.get("extraction_date", "n/a") if enabled else "n/a",
                "has_formula": bool(str(evidence.get("formula", "")).strip()) if enabled else False,
                "has_traceable_source": bool(
                    str(evidence.get("source_file", "")).strip() or str(evidence.get("source_url", "")).strip()
                )
                if enabled
                else False,
            }
        )

    return pd.DataFrame(rows)


def summarize_export_metrics(gdf: gpd.GeoDataFrame) -> pd.DataFrame:
    """
    Resume les principaux ordres de grandeur du fichier exporte.
    """
    hourly_cols = _hourly_columns(gdf)
    reference_hour = _reference_hour_from_gdf(gdf)
    reference_column = _hour_column_name(reference_hour)
    pop_t0 = int(gdf["pop_t0"].fillna(0).sum()) if "pop_t0" in gdf.columns else 0
    inhabited_t0 = int((gdf["pop_t0"].fillna(0) > 0).sum()) if "pop_t0" in gdf.columns else 0

    hourly_totals = gdf[hourly_cols].fillna(0).sum() if hourly_cols else pd.Series(dtype=float)
    hourly_min = int(hourly_totals.min()) if not hourly_totals.empty else 0
    hourly_max = int(hourly_totals.max()) if not hourly_totals.empty else 0
    hourly_mean = float(hourly_totals.mean()) if not hourly_totals.empty else 0.0
    hourly_std = float(hourly_totals.std()) if not hourly_totals.empty else 0.0
    peak_hour = hourly_totals.idxmax().replace("pop_h", "h") if not hourly_totals.empty else "n/a"
    reference_population = int(gdf[reference_column].fillna(0).sum()) if reference_column in gdf.columns else 0
    t0_reference_gap = pop_t0 - reference_population

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
        ("heure_reference_scenario", f"h{reference_hour}", "Heure reelle correspondant a T0 dans le scenario."),
        ("population_heure_reference", reference_population, "Population totale observee a l'heure de reference du scenario."),
        ("ecart_pop_t0_vs_heure_reference", t0_reference_gap, "Doit rester proche de zero si T0 est bien aligne sur l'heure de reference."),
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
    adult_pool = max(0, pop_t0 - target_counts["scolaire"] - target_counts["senior"])
    local_pct = float(employment_cfg.get("travail_local_pct", 0.0))
    local_jobs_value = employment_cfg.get("total_emplois_lieu_travail")
    local_jobs = int(local_jobs_value) if local_jobs_value is not None else None

    employed_residents = adult_pool
    if local_jobs is not None and local_pct > 0.0:
        inferred_employed = int(round(local_jobs / local_pct))
        employed_residents = min(adult_pool, max(inferred_employed, local_jobs))

    target_counts["actif_local"] = min(employed_residents, local_jobs) if local_jobs is not None else int(round(employed_residents * local_pct))
    target_counts["actif_navetteur"] = max(0, employed_residents - target_counts["actif_local"])
    target_counts["inactif"] = max(0, adult_pool - employed_residents)

    realized_counts = {
        "scolaire": int(gdf.get("n_scolaire", pd.Series(dtype=float)).fillna(0).sum()),
        "senior": int(gdf.get("n_senior", pd.Series(dtype=float)).fillna(0).sum()),
        "actif_local": int(gdf.get("n_actif_local", pd.Series(dtype=float)).fillna(0).sum()),
        "actif_navetteur": int(gdf.get("n_actif_navetteur", pd.Series(dtype=float)).fillna(0).sum()),
        "inactif": int(gdf.get("n_inactif", pd.Series(dtype=float)).fillna(0).sum()),
    }

    rows = []
    for role in ["scolaire", "senior", "actif_local", "actif_navetteur", "inactif"]:
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


def external_proxy_validation(gdf: gpd.GeoDataFrame, config: dict) -> pd.DataFrame:
    """
    Compare le modele a quelques proxys publics disponibles dans la configuration.
    """
    rows = []
    local_jobs_value = config.get("demographics", {}).get("employment", {}).get("total_emplois_lieu_travail")
    if local_jobs_value is not None:
        reference_value = int(local_jobs_value)
        modeled_value = int(gdf.get("n_actif_local", pd.Series(dtype=float)).fillna(0).sum())
        gap_value = modeled_value - reference_value
        rows.append(
            {
                "proxy": "emplois_locaux",
                "reference_value": reference_value,
                "modeled_value": modeled_value,
                "gap_value": gap_value,
                "status": "pass" if abs(gap_value) <= max(10, int(reference_value * 0.05)) else "warn",
                "interpretation": "Le nombre d'actifs locaux residents ne devrait pas depasser fortement les emplois de la commune.",
            }
        )

    school_capacity = sum(
        int(school_cfg.get("capacity", 0))
        for school_cfg in config.get("infrastructures", {}).get("schools", {}).values()
        if isinstance(school_cfg, dict)
    )
    if school_capacity > 0:
        modeled_scolaire = int(gdf.get("n_scolaire_interne", pd.Series(dtype=float)).fillna(0).sum())
        is_school_holiday = bool(config.get("scenario", {}).get("is_school_holiday", False))
        rows.append(
            {
                "proxy": "scolaires_affectes_interne",
                "reference_value": school_capacity,
                "modeled_value": modeled_scolaire,
                "gap_value": modeled_scolaire - school_capacity,
                "status": "info" if is_school_holiday else ("pass" if modeled_scolaire <= school_capacity else "warn"),
                "interpretation": (
                    "Scenario en vacances scolaires : le proxy de capacite interne est peu discriminant, car les scolaires ne sont pas censes frequenter l'ecole."
                    if is_school_holiday
                    else "Les scolaires affectes a des destinations internes ne devraient pas depasser la capacite scolaire locale."
                ),
            }
        )

    retained_capacity = int(gdf.get("accommodation_capacity_retained", pd.Series(dtype=float)).fillna(0).sum())
    if retained_capacity > 0:
        modeled_accommodation = int(gdf.get("pop_nonres_accommodation", pd.Series(dtype=float)).fillna(0).sum())
        rows.append(
            {
                "proxy": "hebergement_touristique",
                "reference_value": retained_capacity,
                "modeled_value": modeled_accommodation,
                "gap_value": modeled_accommodation - retained_capacity,
                "status": "pass" if modeled_accommodation <= retained_capacity else "fail",
                "interpretation": "La population touristique modelisee a T0 doit rester sous la capacite retenue.",
            }
        )

    return pd.DataFrame(rows, columns=["proxy", "reference_value", "modeled_value", "gap_value", "status", "interpretation"])


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


def scientific_methodology_checklist(gdf: gpd.GeoDataFrame, config: dict) -> pd.DataFrame:
    """
    Assemble une checklist distinguant coherence interne et verifications externes.
    """
    quality = structural_quality_report(gdf).set_index("check")
    roles = role_targets_vs_realized(gdf, config)
    evidence = evidence_traceability_report(config)
    hourly = hourly_population_profile(gdf)
    reference_hour = _reference_hour_from_config(config)
    reference_column = _hour_column_name(reference_hour)

    pop_t0 = int(gdf["pop_t0"].fillna(0).sum()) if "pop_t0" in gdf.columns else 0
    reference_population = int(gdf[reference_column].fillna(0).sum()) if reference_column in gdf.columns else 0
    t0_reference_gap = pop_t0 - reference_population
    realized_total = (
        int(gdf.get("n_scolaire", pd.Series(dtype=float)).fillna(0).sum())
        + int(gdf.get("n_senior", pd.Series(dtype=float)).fillna(0).sum())
        + int(gdf.get("n_actif_local", pd.Series(dtype=float)).fillna(0).sum())
        + int(gdf.get("n_actif_navetteur", pd.Series(dtype=float)).fillna(0).sum())
        + int(gdf.get("n_inactif", pd.Series(dtype=float)).fillna(0).sum())
    )
    role_balance_gap = abs(realized_total - pop_t0)
    role_gap_share = (role_balance_gap / max(pop_t0, 1)) * 100.0
    max_role_gap_pp = float(roles["gap_share_pp"].abs().max()) if not roles.empty else 0.0
    temporal_unique_hours = int(hourly["population"].nunique()) if not hourly.empty else 0
    enabled_evidence = evidence[evidence["enabled"]]
    missing_evidence = int((enabled_evidence["status"] != "pass").sum()) if not enabled_evidence.empty else 0
    hourly_column_count = int(quality.loc["hourly_column_count", "value"]) if "hourly_column_count" in quality.index else -1
    duplicate_building_count = int(quality.loc["duplicate_building_id", "value"]) if "duplicate_building_id" in quality.index else -1
    negative_hourly_values = int(quality.loc["negative_hourly_values", "value"]) if "negative_hourly_values" in quality.index else -1

    rows = [
        {
            "dimension": "Structure export",
            "question": "Le fichier final est-il exploitable tel quel ?",
            "indicator": "24 colonnes horaires presentes",
            "observed_value": hourly_column_count,
            "status": "pass" if hourly_column_count == 24 else "fail",
            "interpretation": "Une matrice incomplete empeche une lecture journaliere complete.",
            "next_step": "Corriger la generation de pop_h0 a pop_h23 si besoin.",
        },
        {
            "dimension": "Traçabilite",
            "question": "Peut-on suivre chaque entite sans ambiguite ?",
            "indicator": "Nombre de building_id dupliques",
            "observed_value": duplicate_building_count,
            "status": "pass" if duplicate_building_count == 0 else "fail",
            "interpretation": "Des doublons cassent la comparaison inter-etapes et inter-scenarios.",
            "next_step": "Verifier la creation des identifiants stables avant export.",
        },
        {
            "dimension": "Bornes numeriques",
            "question": "Le modele produit-il des valeurs physiquement plausibles ?",
            "indicator": "Nombre de valeurs horaires negatives",
            "observed_value": negative_hourly_values,
            "status": "pass" if negative_hourly_values == 0 else "fail",
            "interpretation": "Une population negative signale un defaut de logique ou d'arrondi.",
            "next_step": "Auditer la generation des agendas et les reallocations non residentielles.",
        },
        {
            "dimension": "Demographie",
            "question": "Les roles reconstruisent-ils bien la population initiale ?",
            "indicator": "Ecart roles vs pop_t0 (%)",
            "observed_value": round(role_gap_share, 2),
            "status": _status_for_threshold(role_gap_share, pass_threshold=0.0, warn_threshold=1.0),
            "interpretation": "Le total des roles doit idealement retomber sur la masse a T0.",
            "next_step": "Verifier le profilage des foyers et les cibles imposees.",
        },
        {
            "dimension": "Alignement temporel",
            "question": "T0 correspond-il bien a l'heure de reference du scenario ?",
            "indicator": f"Ecart pop_t0 vs h{reference_hour:02d}",
            "observed_value": int(t0_reference_gap),
            "status": "pass" if t0_reference_gap == 0 else _status_for_threshold(abs(float(t0_reference_gap)), 5.0, 25.0),
            "interpretation": "Un ecart important signale un decalage entre l'etat initial et la matrice horaire.",
            "next_step": "Verifier les hypotheses de T0 et la coherence de pop_h avec scenario.reference_hour.",
        },
        {
            "dimension": "Calibration",
            "question": "Les roles realises restent-ils proches des cibles du scenario ?",
            "indicator": "Ecart max role cible/realise (points de %)",
            "observed_value": round(max_role_gap_pp, 2),
            "status": _status_for_threshold(max_role_gap_pp, pass_threshold=1.0, warn_threshold=3.0),
            "interpretation": "Un ecart eleve n'invalide pas le modele, mais reduit sa credibilite parametrique.",
            "next_step": "Comparer les hypotheses du YAML et le resultat obtenu par role.",
        },
        {
            "dimension": "Cycle journalier",
            "question": "Observe-t-on une variation temporelle exploitable ?",
            "indicator": "Nombre de totaux horaires distincts",
            "observed_value": temporal_unique_hours,
            "status": "pass" if temporal_unique_hours > 1 else "warn",
            "interpretation": "Un cycle complet ne doit pas etre totalement plat.",
            "next_step": "Revoir les profils temporels si la serie reste uniforme.",
        },
        {
            "dimension": "Preuves",
            "question": "Les briques sensibles actives sont-elles documentees ?",
            "indicator": "Modules actives sans evidence complete",
            "observed_value": missing_evidence,
            "status": "pass" if missing_evidence == 0 else "fail",
            "interpretation": "Sans trace de source, la methode reste peu defendable scientifiquement.",
            "next_step": "Completer les blocs evidence des sections non residentielles actives.",
        },
        {
            "dimension": "Veracite externe",
            "question": "La simulation a-t-elle ete confrontee a une reference independante ?",
            "indicator": "Statut de confrontation externe",
            "observed_value": "a conduire",
            "status": "warn",
            "interpretation": "La coherence interne ne prouve pas a elle seule la verite empirique.",
            "next_step": "Comparer aux totaux INSEE, capacites scolaires, hebergement et observations locales.",
        },
    ]
    return pd.DataFrame(rows)


def plot_scientific_validation_dashboard(
    gdf: gpd.GeoDataFrame,
    config: dict,
    output_path: str | Path,
) -> Path:
    """
    Genere un tableau de bord PNG pour lire la robustesse scientifique du scenario.
    """
    metrics = summarize_export_metrics(gdf).set_index("metric")
    hourly = hourly_population_profile(gdf)
    roles = role_targets_vs_realized(gdf, config)
    nonres = non_residential_validation(gdf)
    occupied = occupied_buildings_by_usage(gdf).head(8)
    checklist = scientific_methodology_checklist(gdf, config)
    evidence = evidence_traceability_report(config)
    reference_hour = _reference_hour_from_config(config)

    fig = plt.figure(figsize=(18, 20), constrained_layout=True)
    grid = fig.add_gridspec(4, 2, height_ratios=[0.9, 1.4, 1.1, 1.2])
    ax_cards = fig.add_subplot(grid[0, :])
    ax_hourly = fig.add_subplot(grid[1, 0])
    ax_roles = fig.add_subplot(grid[1, 1])
    ax_usage = fig.add_subplot(grid[2, 0])
    ax_nonres = fig.add_subplot(grid[2, 1])
    ax_checklist = fig.add_subplot(grid[3, 0])
    ax_evidence = fig.add_subplot(grid[3, 1])

    fig.suptitle("Validation scientifique du scenario MOGEC", fontsize=20, fontweight="bold", y=0.995)

    ax_cards.axis("off")
    nonres_total = int(metrics.loc["pop_nonres_accommodation", "value"]) + int(metrics.loc["pop_nonres_activity", "value"])
    card_items = [
        (f"Population T0 (h{reference_hour:02d})", f"{int(metrics.loc['population_t0', 'value']):,}".replace(",", " "), "base exportee"),
        ("Heure reference", str(metrics.loc["heure_reference_scenario", "value"]), f"{int(metrics.loc['population_heure_reference', 'value']):,}".replace(",", " ") + " agents"),
        ("Non residentiel", f"{nonres_total:,}".replace(",", " "), "agents a T0"),
        ("Overlap exclus", str(int(metrics.loc["batiments_overlap_exclus", "value"])), "batiments corriges"),
    ]
    x_card_positions = [0.02, 0.27, 0.52, 0.77]
    for (title, value, subtitle), x in zip(card_items, x_card_positions, strict=False):
        ax_cards.text(x, 0.72, title, transform=ax_cards.transAxes, fontsize=11, color="#475569", fontweight="bold")
        ax_cards.text(x, 0.33, value, transform=ax_cards.transAxes, fontsize=24, color="#0f172a", fontweight="bold")
        ax_cards.text(x, 0.10, subtitle, transform=ax_cards.transAxes, fontsize=10, color="#64748b")

    if not hourly.empty:
        ax_hourly.plot(hourly["hour"], hourly["population"], color="#1f4e79", linewidth=2.6, marker="o")
        ax_hourly.fill_between(hourly["hour"], hourly["population"], color="#9ecae1", alpha=0.35)
        max_row = hourly.loc[hourly["population"].idxmax()]
        min_row = hourly.loc[hourly["population"].idxmin()]
        reference_row = hourly[hourly["hour"] == reference_hour].iloc[0] if (hourly["hour"] == reference_hour).any() else None
        ax_hourly.scatter(
            [max_row["hour"], min_row["hour"]],
            [max_row["population"], min_row["population"]],
            color=["#1d8348", "#b03a2e"],
            zorder=5,
        )
        if reference_row is not None:
            ax_hourly.scatter([reference_row["hour"]], [reference_row["population"]], color="#0f172a", s=80, marker="D", zorder=6)
        ax_hourly.annotate(
            f"Pic h{int(max_row['hour']):02d}: {int(max_row['population'])}",
            xy=(max_row["hour"], max_row["population"]),
            xytext=(8, 10),
            textcoords="offset points",
            fontsize=10,
            color="#1d8348",
            fontweight="bold",
        )
        ax_hourly.annotate(
            f"Creux h{int(min_row['hour']):02d}: {int(min_row['population'])}",
            xy=(min_row["hour"], min_row["population"]),
            xytext=(8, -18),
            textcoords="offset points",
            fontsize=10,
            color="#b03a2e",
            fontweight="bold",
        )
        if reference_row is not None:
            ax_hourly.annotate(
                f"T0 h{reference_hour:02d}: {int(reference_row['population'])}",
                xy=(reference_row["hour"], reference_row["population"]),
                xytext=(10, -30),
                textcoords="offset points",
                fontsize=10,
                color="#0f172a",
                fontweight="bold",
            )
        amplitude = int(max_row["population"] - min_row["population"])
        ax_hourly.text(
            0.02,
            0.95,
            f"Amplitude journaliere: {amplitude} agents\nEcart T0/h{reference_hour:02d}: {int(metrics.loc['ecart_pop_t0_vs_heure_reference', 'value'])}",
            transform=ax_hourly.transAxes,
            va="top",
            fontsize=10,
            bbox={"boxstyle": "round,pad=0.3", "facecolor": "white", "edgecolor": "#cbd5e1"},
        )
    ax_hourly.set_title("Cycle journalier total", fontsize=13, fontweight="bold")
    ax_hourly.set_xlabel("Heure")
    ax_hourly.set_ylabel("Population presente")
    ax_hourly.set_xticks(range(0, 24, 2))
    ax_hourly.grid(True, linestyle="--", alpha=0.35)

    if not roles.empty:
        ordered_roles = roles["role"].tolist()
        x_role_positions = range(len(ordered_roles))
        ax_roles.bar(
            [x - 0.18 for x in x_role_positions],
            roles["target_count"],
            width=0.36,
            color="#cbd5e1",
            label="Cible scenario",
        )
        ax_roles.bar(
            [x + 0.18 for x in x_role_positions],
            roles["realized_count"],
            width=0.36,
            color="#2563eb",
            label="Realise",
        )
        for idx, row in roles.reset_index(drop=True).iterrows():
            color = _status_color(_status_for_threshold(abs(float(row["gap_share_pp"])), 1.0, 3.0))
            ax_roles.text(
                idx + 0.18,
                float(row["realized_count"]) + max(2.0, float(roles["realized_count"].max()) * 0.02),
                f"{row['gap_share_pp']:+.1f} pp",
                ha="center",
                fontsize=9,
                color=color,
                fontweight="bold",
            )
        ax_roles.set_xticks(list(x_role_positions), labels=ordered_roles, rotation=15)
        ax_roles.legend(frameon=False)
    ax_roles.set_title("Cibles demographiques vs realise", fontsize=13, fontweight="bold")
    ax_roles.set_ylabel("Effectifs")
    ax_roles.grid(True, axis="y", linestyle="--", alpha=0.35)

    ax_usage.set_title(f"Usages les plus occupes a T0 (h{reference_hour:02d})", fontsize=13, fontweight="bold")
    if not occupied.empty:
        usage_data = occupied.sort_values("population_t0", ascending=True)
        ax_usage.barh(usage_data["usage_1"], usage_data["population_t0"], color="#5b8e7d")
        ax_usage.set_xlabel("Population a T0")
    else:
        ax_usage.text(0.02, 0.85, "Aucune information d'usage exploitable.", transform=ax_usage.transAxes)
    ax_usage.grid(True, axis="x", linestyle="--", alpha=0.35)

    ax_nonres.set_title("Composantes non residentielles", fontsize=13, fontweight="bold")
    nonres_plot = nonres[~nonres["component"].astype(str).str.startswith("Audit overlap")].copy()
    if not nonres_plot.empty:
        nonres_plot = nonres_plot.sort_values("population", ascending=True)
        colors = ["#d97706", "#8b5cf6", "#0ea5e9"]
        bars = ax_nonres.barh(nonres_plot["component"], nonres_plot["population"], color=colors[: len(nonres_plot)])
        for bar, share in zip(bars, nonres_plot["part_de_pop_t0_pct"], strict=False):
            if share is None or pd.isna(share):
                continue
            ax_nonres.text(bar.get_width() + 2, bar.get_y() + bar.get_height() / 2, f"{share:.1f} %", va="center", fontsize=9)
        ax_nonres.set_xlabel("Population")
    else:
        ax_nonres.text(0.02, 0.85, "Aucune composante non residentielle active.", transform=ax_nonres.transAxes)
    ax_nonres.grid(True, axis="x", linestyle="--", alpha=0.35)

    ax_checklist.axis("off")
    ax_checklist.set_title("Checklist methodologique", fontsize=13, fontweight="bold", loc="left")
    for idx, row in checklist.iterrows():
        y = 0.95 - idx * 0.115
        if y < 0.05:
            break
        status = str(row["status"]).upper()
        color = _status_color(str(row["status"]))
        ax_checklist.text(0.01, y, status, color=color, fontweight="bold", fontsize=10, transform=ax_checklist.transAxes)
        ax_checklist.text(0.16, y, str(row["dimension"]), fontweight="bold", fontsize=10, transform=ax_checklist.transAxes)
        ax_checklist.text(0.16, y - 0.04, f"{row['indicator']}: {row['observed_value']}", fontsize=9, color="#334155", transform=ax_checklist.transAxes)
        ax_checklist.text(0.16, y - 0.075, str(row["next_step"]), fontsize=8.7, color="#64748b", transform=ax_checklist.transAxes)

    ax_evidence.axis("off")
    ax_evidence.set_title("Traçabilite des preuves", fontsize=13, fontweight="bold", loc="left")
    enabled_evidence = evidence[evidence["enabled"]].reset_index(drop=True)
    if enabled_evidence.empty:
        ax_evidence.text(0.02, 0.88, "Aucune brique non residentielle active.", transform=ax_evidence.transAxes)
    else:
        for idx, row in enabled_evidence.iterrows():
            y = 0.92 - idx * 0.23
            color = _status_color(str(row["status"]))
            ax_evidence.text(0.02, y, str(row["label"]), fontsize=10.5, fontweight="bold", transform=ax_evidence.transAxes)
            ax_evidence.text(0.02, y - 0.05, f"Statut: {str(row['status']).upper()} | Confiance: {row['confidence']}", color=color, fontsize=9.5, transform=ax_evidence.transAxes)
            ax_evidence.text(0.02, y - 0.10, f"Source: {row['source']}", fontsize=9, color="#334155", transform=ax_evidence.transAxes)
            ax_evidence.text(0.02, y - 0.15, f"Extraction/verif.: {row['extraction_date']}", fontsize=9, color="#64748b", transform=ax_evidence.transAxes)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)
    return output_path
