"""
Preparation des sources externes pour le pipeline MOGEC.

Ce module transforme les jeux telecharges (tourisme institutionnel, plages,
capacites Insee) en tables intermediaires directement branchables sur le
pipeline :
- un CSV restaurant compatible avec `src.core.restaurants` ;
- un CSV de capacite d'hebergement joint par `building_id` ;
- un GeoPackage de plages bufferisees, compatible avec la brique temporelle.

L'objectif n'est pas seulement de filtrer Batz-sur-Mer, mais de produire un
referentiel de travail stable, auditable et re-executable.
"""

from __future__ import annotations

import logging
from pathlib import Path

import geopandas as gpd
import pandas as pd

from src.core.geometry import filter_buildings_by_area
from src.core.identifiers import assign_building_ids
from src.io.loaders import load_geopackage_with_mask, load_study_area_boundary

logger = logging.getLogger(__name__)
EMPTY_TOURISM_COLUMNS = ["dataset_type", "offer_name", "geometry"]
ACCOMMODATION_DATASET_TYPES = ["hotel", "camping", "residence", "collective", "locative"]
EMPTY_CAPACITY_COLUMNS = ["building_id", "capacity_lits"]


TOURISM_SPECS = {
    "restaurants": {
        "path_key": "tourism_restaurants",
        "dataset_type": "restaurant",
        "name_col": "Nom de l'offre touristique",
        "commune_col": "Commune",
        "insee_col": "Code Insee de la Commune",
        "lat_col": "latitude",
        "lon_col": "longitude",
        "address_cols": ["Adresse1", "Adresse2", "Adresse3"],
        "website_col": "Url du site web",
        "opening_col": "Horaires d'ouvertures",
        "capacity_cols": {"capacity_covers": "Nombre max couverts"},
    },
    "hotels": {
        "path_key": "tourism_hotels",
        "dataset_type": "hotel",
        "name_col": "Nom de l'offre touristique",
        "commune_col": "Nom de la commune",
        "insee_col": "Code Insee de la Commune",
        "lat_col": "Latitude",
        "lon_col": "Longitude",
        "address_cols": ["Adresse1", "Adresse partie 1 suite", "Adresse partie 2", "Adresse partie 3"],
        "website_col": "Url du site web",
        "opening_col": "Horaires d'ouvertures",
        "capacity_cols": {"capacity_rooms": "Nombre chambres"},
    },
    "campings": {
        "path_key": "tourism_campings",
        "dataset_type": "camping",
        "name_col": "Nom de l'offre touristique",
        "commune_col": "Nom de la commune",
        "insee_col": "Code Insee de la Commune",
        "lat_col": "Latitude",
        "lon_col": "Longitude",
        "address_cols": ["Adresse1", "Adresse partie 1 suite", "Adresse partie 2", "Adresse partie 3"],
        "website_col": "Url du site web",
        "opening_col": "Période/horaires par jour/précisions ouverture/précision fermeture",
        "capacity_cols": {
            "capacity_pitches": "Nombre emplacements pour les campings",
            "capacity_pitches_locative": "Nombre emplacements équipés avec locatif pour les campings",
            "capacity_pitches_bare": "Nombre emplacements nus pour les campings",
        },
    },
    "residences": {
        "path_key": "tourism_residences",
        "dataset_type": "residence",
        "name_col": "Nom de l'offre touristique",
        "commune_col": "Commune",
        "insee_col": "Code Insee de la Commune",
        "lat_col": "Latitude",
        "lon_col": "Longitude",
        "address_cols": ["Adresse1", "Adresse partie 1 suite", "Adresse partie 2", "Adresse partie 3"],
        "website_col": "Url du site web",
        "opening_col": "Horaires d'ouvertures",
        "capacity_cols": {},
    },
    "collectifs": {
        "path_key": "tourism_collective",
        "dataset_type": "collective",
        "name_col": "Nom de l'offre touristique",
        "commune_col": "Nom de la commune",
        "insee_col": "Code Insee de la Commune",
        "lat_col": "Latitude",
        "lon_col": "Longitude",
        "address_cols": ["Adresse1", "Adresse partie 1 suite", "Adresse partie 2", "Adresse partie 3"],
        "website_col": "Url du site web",
        "opening_col": "Horaires d'ouvertures",
        "capacity_cols": {
            "capacity_beds": "Nombre lits",
            "capacity_persons": "Nombre personnes",
            "capacity_rooms": "Nombre chambres",
        },
    },
    "locatifs": {
        "path_key": "tourism_locative",
        "dataset_type": "locative",
        "name_col": "Nom de l'offre touristique",
        "commune_col": "Nom de la commune",
        "insee_col": "Code Insee de la Commune",
        "lat_col": "Latitude",
        "lon_col": "Longitude",
        "address_cols": ["Adresse1", "Adresse partie 1 suite", "Adresse partie 2", "Adresse partie 3"],
        "website_col": "Url du site web",
        "opening_col": "Horaires d'ouvertures",
        "capacity_cols": {
            "capacity_persons": "Nombre personnes",
            "capacity_rooms": "Nombre chambres",
            "capacity_units": "Nombre total d'hébergements / logements",
        },
    },
}


def _normalise_text(value: object) -> str:
    return str(value).strip() if pd.notna(value) else ""


def _normalise_commune_key(value: object) -> str:
    text = _normalise_text(value).casefold()
    return text.replace("-", " ").replace("'", " ")


def _join_address(row: pd.Series, address_cols: list[str]) -> str:
    parts = [_normalise_text(row.get(column)) for column in address_cols]
    return ", ".join(part for part in parts if part)


def _get_commune_filters(config: dict) -> tuple[str, str]:
    study_area = config["study_area"]
    commune_name = study_area.get("boundary_name_value") or study_area["commune_name"].split(",")[0].strip()
    commune_insee = str(study_area.get("commune_insee", "")).strip()
    return _normalise_commune_key(commune_name), commune_insee


def _read_tourism_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, sep=";")


def _empty_tourism_gdf() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(columns=EMPTY_TOURISM_COLUMNS, geometry="geometry", crs="EPSG:4326")


def _empty_capacity_table() -> pd.DataFrame:
    return pd.DataFrame(columns=EMPTY_CAPACITY_COLUMNS)


def _filter_to_commune(df: pd.DataFrame, commune_col: str, insee_col: str, config: dict) -> pd.DataFrame:
    commune_name, commune_insee = _get_commune_filters(config)
    commune_mask = df[commune_col].fillna("").apply(_normalise_commune_key) == commune_name
    if commune_insee:
        insee_mask = df[insee_col].fillna("").astype(str).str.strip() == commune_insee
        mask = commune_mask | insee_mask
    else:
        mask = commune_mask
    return df.loc[mask].copy()


def _to_numeric(series: pd.Series | None) -> pd.Series:
    if series is None:
        return pd.Series(dtype=float)
    return pd.to_numeric(series, errors="coerce")


def _harmonise_tourism_dataset(dataset_name: str, path: Path, config: dict) -> gpd.GeoDataFrame:
    spec = TOURISM_SPECS[dataset_name]
    df = _read_tourism_csv(path)
    df = _filter_to_commune(df, spec["commune_col"], spec["insee_col"], config)

    if df.empty:
        return _empty_tourism_gdf()

    result = pd.DataFrame(
        {
            "dataset_name": dataset_name,
            "dataset_type": spec["dataset_type"],
            "offer_name": df[spec["name_col"]].fillna(""),
            "commune_name": df[spec["commune_col"]].fillna(""),
            "commune_insee": df[spec["insee_col"]].astype(str).str.strip(),
            "latitude": pd.to_numeric(df[spec["lat_col"]], errors="coerce"),
            "longitude": pd.to_numeric(df[spec["lon_col"]], errors="coerce"),
            "address": df.apply(lambda row: _join_address(row, spec["address_cols"]), axis=1),
            "website": df.get(spec["website_col"], pd.Series(index=df.index, dtype=object)).fillna(""),
            "opening_hours_raw": df.get(spec["opening_col"], pd.Series(index=df.index, dtype=object)).fillna(""),
            "source_path": str(path),
        }
    )

    for target_col, source_col in spec["capacity_cols"].items():
        result[target_col] = _to_numeric(df.get(source_col))

    for target_col in [
        "capacity_covers",
        "capacity_rooms",
        "capacity_beds",
        "capacity_persons",
        "capacity_units",
        "capacity_pitches",
        "capacity_pitches_locative",
        "capacity_pitches_bare",
    ]:
        if target_col not in result.columns:
            result[target_col] = pd.NA

    geometry = gpd.points_from_xy(result["longitude"], result["latitude"], crs="EPSG:4326")
    return gpd.GeoDataFrame(result, geometry=geometry, crs="EPSG:4326")


def load_and_harmonise_tourism_offers(config: dict) -> gpd.GeoDataFrame:
    """
    Charge les flux touristiques telecharges puis les harmonise dans un schema commun.

    Le resultat sert de table pivot pour les restaurants et les hebergements.
    """
    logger.info("Preparation des offres touristiques institutionnelles...")
    input_paths = config["data_paths"]["input"]
    frames: list[gpd.GeoDataFrame] = []

    for dataset_name, spec in TOURISM_SPECS.items():
        path = Path(input_paths[spec["path_key"]])
        if not path.exists():
            logger.warning("Source touristique absente: %s", path)
            continue
        frames.append(_harmonise_tourism_dataset(dataset_name, path, config))

    if not frames:
        return _empty_tourism_gdf()

    tourism = pd.concat(frames, ignore_index=True)
    tourism = gpd.GeoDataFrame(tourism, geometry="geometry", crs="EPSG:4326")
    tourism = tourism.dropna(subset=["latitude", "longitude"]).copy()
    tourism = tourism.to_crs(epsg=config["project"]["crs_epsg"])
    logger.info("%s offres touristiques harmonisees pour la commune d'etude.", len(tourism))
    return tourism


def prepare_restaurants_table(tourism_gdf: gpd.GeoDataFrame) -> pd.DataFrame:
    """
    Construit un CSV restaurant compatible avec `src.core.restaurants`.
    """
    restaurants = tourism_gdf[tourism_gdf["dataset_type"] == "restaurant"].copy()
    restaurants = restaurants.to_crs(epsg=4326)
    restaurants["lat"] = restaurants.geometry.y
    restaurants["lon"] = restaurants.geometry.x
    restaurants["nom"] = restaurants["offer_name"]
    restaurants["opening_hours_brut"] = restaurants["opening_hours_raw"].fillna("")
    restaurants["horaire_ouverture"] = pd.NA
    restaurants["horaire_fermeture"] = pd.NA
    restaurants["source_dataset"] = restaurants["dataset_name"]

    return restaurants[
        [
            "nom",
            "lat",
            "lon",
            "opening_hours_brut",
            "horaire_ouverture",
            "horaire_fermeture",
            "commune_name",
            "commune_insee",
            "address",
            "website",
            "source_dataset",
        ]
    ].rename(columns={"commune_name": "commune", "commune_insee": "code_insee"})


def _capacity_rules(config: dict) -> dict:
    return config.get("external_preparation", {}).get("accommodation", {}).get("capacity_rules", {})


def _double_count_cfg(config: dict) -> dict:
    return config.get("non_residential_model", {}).get("accommodation", {}).get("double_count_prevention", {})


def _split_source_types(source_types: str) -> set[str]:
    if not source_types or pd.isna(source_types):
        return set()
    return {part.strip() for part in str(source_types).split("|") if part.strip()}


def _is_residential_usage(usage: object, config: dict) -> bool:
    patterns = _double_count_cfg(config).get("residential_usage_any_of", ["Résidentiel"])
    usage_text = str(usage or "").casefold()
    return any(pattern.casefold() in usage_text for pattern in patterns)


def classify_accommodation_overlap_risk(source_types: str, building_usage: object, config: dict) -> tuple[str, str]:
    """
    Qualifie le risque de double comptage entre population residente et touristique.

    La logique retenue est volontairement conservative :
    - les locatifs touristiques sur bati residentiel sont exclus du surplus
      touristique car ils recouvrent potentiellement des residences deja
      representees dans le downscaling residentiel et dans le scenario RS ;
    - les residences de tourisme sur bati residentiel sont signalees comme
      risque moyen pour revue manuelle ;
    - hotels, campings et hebergements collectifs sont consideres additifs.
    """
    source_set = _split_source_types(source_types)
    cfg = _double_count_cfg(config)
    exclude_on_residential = set(cfg.get("exclude_source_types_on_residential", ["locative"]))
    warn_on_residential = set(cfg.get("warn_source_types_on_residential", ["residence"]))

    if not source_set:
        return "unknown", "missing_source_type"

    if not _is_residential_usage(building_usage, config):
        return "low", "non_residential_building_additive"

    if source_set & exclude_on_residential:
        return "high", "exclude_from_addition"

    if source_set & warn_on_residential:
        return "medium", "review_before_addition"

    return "low", "residential_building_but_additive_source"


def _derive_capacity_lits(row: pd.Series, config: dict) -> tuple[float, str]:
    """
    Derive une capacite en lits a partir de la meilleure information disponible.

    La methode est conservee pour audit, car toutes les sources ne fournissent
    pas directement le meme niveau d'information.
    """
    rules = _capacity_rules(config)
    dataset_type = row["dataset_type"]

    beds = row.get("capacity_beds")
    if pd.notna(beds):
        return float(beds), "direct_beds"

    persons = row.get("capacity_persons")
    if pd.notna(persons):
        return float(persons), "persons_as_beds"

    rooms = row.get("capacity_rooms")
    if pd.notna(rooms):
        if dataset_type == "hotel":
            factor = float(rules.get("hotel_beds_per_room", 2.0))
        else:
            factor = float(rules.get("residence_beds_per_room", 2.0))
        return float(rooms) * factor, f"rooms_x_{factor:g}"

    pitches = row.get("capacity_pitches")
    if pd.notna(pitches):
        factor = float(rules.get("camping_persons_per_pitch", 2.5))
        return float(pitches) * factor, f"pitches_x_{factor:g}"

    return 0.0, "missing_capacity"


def _derive_accommodation_capacities(accommodation: pd.DataFrame, config: dict) -> pd.DataFrame:
    if accommodation.empty:
        return accommodation

    accommodation = accommodation.copy()
    accommodation["capacity_lits"] = 0.0
    accommodation["capacity_method"] = "missing_capacity"
    for index, row in accommodation.iterrows():
        capacity, method = _derive_capacity_lits(row, config)
        accommodation.at[index, "capacity_lits"] = capacity
        accommodation.at[index, "capacity_method"] = method
    return accommodation[accommodation["capacity_lits"] > 0].copy()


def _load_buildings_for_matching(config: dict) -> gpd.GeoDataFrame:
    boundary = load_study_area_boundary(config, strict=True)
    bati = load_geopackage_with_mask(
        config["data_paths"]["input"]["bd_topo"],
        config["data_paths"]["input"]["bd_topo_layer"],
        boundary,
    )
    bati = filter_buildings_by_area(bati, config["filtering"]["min_building_area_m2"])
    bati = assign_building_ids(bati, config)
    return bati


def _select_candidate_building(
    buildings: gpd.GeoDataFrame,
    poi_geometry,
    max_distance_m: float,
    preferred_usage: list[str],
) -> pd.Series | None:
    intersecting = buildings[buildings.geometry.intersects(poi_geometry)].copy()
    if intersecting.empty:
        distances = buildings.geometry.distance(poi_geometry)
        candidates = buildings[distances <= max_distance_m].copy()
        if candidates.empty:
            return None
        candidates["distance_to_poi"] = distances.loc[candidates.index]
    else:
        candidates = intersecting.copy()
        candidates["distance_to_poi"] = 0.0

    if preferred_usage:
        preferred_mask = candidates["usage_1"].fillna("").apply(
            lambda usage: any(pattern.casefold() in str(usage).casefold() for pattern in preferred_usage)
        )
        preferred_candidates = candidates[preferred_mask].copy()
        if not preferred_candidates.empty:
            candidates = preferred_candidates

    best = candidates.sort_values("distance_to_poi").iloc[0]
    return best


def _matched_accommodation_rows(
    accommodation: pd.DataFrame,
    buildings: gpd.GeoDataFrame,
    max_distance_m: float,
    preferred_usage: list[str],
) -> list[dict]:
    matched_rows: list[dict] = []
    for _, row in accommodation.iterrows():
        best_building = _select_candidate_building(buildings, row.geometry, max_distance_m, preferred_usage)
        if best_building is None:
            continue
        matched_rows.append(
            {
                "building_id": str(best_building["building_id"]),
                "building_usage_1": best_building.get("usage_1", ""),
                "offer_name": row["offer_name"],
                "dataset_type": row["dataset_type"],
                "capacity_lits": float(row["capacity_lits"]),
                "capacity_method": row["capacity_method"],
                "commune_name": row["commune_name"],
                "commune_insee": row["commune_insee"],
                "address": row["address"],
                "website": row["website"],
            }
        )
    return matched_rows


def _aggregate_matched_accommodation(matched: pd.DataFrame) -> pd.DataFrame:
    aggregated = (
        matched.groupby("building_id", as_index=False)
        .agg(
            building_usage_1=("building_usage_1", "first"),
            capacity_lits=("capacity_lits", "sum"),
            offer_count=("offer_name", "count"),
            offer_names=("offer_name", lambda values: " | ".join(sorted(set(values)))),
            source_types=("dataset_type", lambda values: " | ".join(sorted(set(values)))),
            capacity_methods=("capacity_method", lambda values: " | ".join(sorted(set(values)))),
        )
    )
    aggregated["capacity_lits"] = aggregated["capacity_lits"].round().astype(int)
    return aggregated


def prepare_accommodation_capacity_table(tourism_gdf: gpd.GeoDataFrame, config: dict) -> pd.DataFrame:
    """
    Construit une table de capacite d'hebergement jointe au bati par `building_id`.
    """
    logger.info("Preparation de la table de capacite d'hebergement...")
    accommodation = tourism_gdf[tourism_gdf["dataset_type"].isin(ACCOMMODATION_DATASET_TYPES)].copy()
    if accommodation.empty:
        return _empty_capacity_table()

    accommodation = _derive_accommodation_capacities(accommodation, config)
    if accommodation.empty:
        return _empty_capacity_table()

    buildings = _load_buildings_for_matching(config)
    matching_cfg = config.get("external_preparation", {}).get("accommodation", {})
    max_distance_m = float(matching_cfg.get("match_max_distance_m", 120.0))
    preferred_usage = matching_cfg.get("preferred_usage_any_of", [])

    matched_rows = _matched_accommodation_rows(accommodation, buildings, max_distance_m, preferred_usage)
    matched = pd.DataFrame(matched_rows)
    if matched.empty:
        return _empty_capacity_table()

    aggregated = _aggregate_matched_accommodation(matched)
    logger.info("%s batiments d'hebergement prepares avec capacite.", len(aggregated))
    return aggregated


def _load_official_capacity_summary(config: dict) -> pd.DataFrame:
    path = Path(config["data_paths"]["input"]["tourism_capacity_insee"])
    if path.suffix.lower() == ".zip":
        path = path.parent / path.stem / "DS_TOUR_CAP_2026_data.csv"
    df = pd.read_csv(path, sep=";", low_memory=False, dtype={"GEO": str})
    _, commune_insee = _get_commune_filters(config)
    df = df[df["GEO"] == commune_insee].copy()
    df = df[df["FREQ"] == "A"].copy()
    df = df[df["UNIT_LOC_RANKING"] == "_T"].copy()
    df = df[df["L_STAY"] == "_T"].copy()
    df = df[df["TOUR_MEASURE"].isin(["UNIT_LOC", "PLACE", "BEDPLACE"])].copy()
    return df


def prepare_accommodation_summary(
    tourism_gdf: gpd.GeoDataFrame,
    accommodation_capacity: pd.DataFrame,
    config: dict,
) -> pd.DataFrame:
    """
    Produit un tableau de comparaison entre l'offre preparee et les totaux Insee.
    """
    local_summary = (
        tourism_gdf[tourism_gdf["dataset_type"].isin(["hotel", "camping", "residence", "collective", "locative"])]
        .groupby("dataset_type", as_index=False)
        .size()
        .rename(columns={"size": "n_offers"})
    )

    local_capacity = (
        accommodation_capacity.assign(dataset_type="matched_buildings")
        .groupby("dataset_type", as_index=False)["capacity_lits"]
        .sum()
    )

    official = _load_official_capacity_summary(config)
    official_summary = official.groupby(["ACTIVITY", "TOUR_MEASURE"], as_index=False)["OBS_VALUE"].sum()
    official_summary["dataset_type"] = "insee_reference"

    return pd.concat(
        [
            local_summary,
            local_capacity,
            official_summary.rename(columns={"ACTIVITY": "activity_code", "TOUR_MEASURE": "tour_measure", "OBS_VALUE": "official_value"}),
        ],
        ignore_index=True,
        sort=False,
    )


def _official_value(official_summary: pd.DataFrame, activity_code: str, tour_measure: str) -> float | None:
    mask = official_summary["ACTIVITY"].eq(activity_code) & official_summary["TOUR_MEASURE"].eq(tour_measure)
    if not mask.any():
        return None
    value = official_summary.loc[mask, "OBS_VALUE"].sum()
    return float(value)


def _calibration_row(
    parameter_name: str,
    dataset_type: str,
    current_value: float,
    recommended_value: float,
    local_reference: float,
    official_reference: float,
    official_activity_code: str,
    official_measure: str,
    method_note: str,
) -> dict:
    return {
        "parameter_name": parameter_name,
        "dataset_type": dataset_type,
        "current_value": current_value,
        "recommended_value": recommended_value,
        "local_reference": local_reference,
        "official_reference": official_reference,
        "official_activity_code": official_activity_code,
        "official_measure": official_measure,
        "method_note": method_note,
    }


def prepare_accommodation_calibration(tourism_gdf: gpd.GeoDataFrame, config: dict) -> pd.DataFrame:
    """
    Produit des recommandations de calibration a partir des references Insee.

    Les coefficients proposes servent a rapprocher les capacites derivees des
    sources locales des totaux officiels communaux. Ils doivent ensuite etre
    discutes dans le memoire avant activation definitive.
    """
    official = _load_official_capacity_summary(config)
    rules = _capacity_rules(config)
    rows: list[dict] = []

    hotel_rooms = pd.to_numeric(
        tourism_gdf.loc[tourism_gdf["dataset_type"] == "hotel", "capacity_rooms"],
        errors="coerce",
    ).fillna(0.0).sum()
    hotel_official = _official_value(official, "I551", "PLACE")
    if hotel_rooms > 0 and hotel_official is not None:
        rows.append(
            _calibration_row(
                "hotel_beds_per_room",
                "hotel",
                float(rules.get("hotel_beds_per_room", 2.0)),
                round(hotel_official / hotel_rooms, 3),
                float(hotel_rooms),
                hotel_official,
                "I551",
                "PLACE",
                "Rapport entre les places Insee hotelieres et le nombre local de chambres declarees.",
            )
        )

    camping_pitches = pd.to_numeric(
        tourism_gdf.loc[tourism_gdf["dataset_type"] == "camping", "capacity_pitches"],
        errors="coerce",
    ).fillna(0.0).sum()
    camping_official = _official_value(official, "I553", "PLACE")
    if camping_pitches > 0 and camping_official is not None:
        rows.append(
            _calibration_row(
                "camping_persons_per_pitch",
                "camping",
                float(rules.get("camping_persons_per_pitch", 2.5)),
                round(camping_official / camping_pitches, 3),
                float(camping_pitches),
                camping_official,
                "I553",
                "PLACE",
                "Rapport entre les places Insee de camping et le nombre local d'emplacements declares.",
            )
        )

    short_stay_local = (
        pd.to_numeric(
            tourism_gdf.loc[tourism_gdf["dataset_type"].isin(["collective", "locative"]), "capacity_persons"],
            errors="coerce",
        ).fillna(0.0).sum()
    )
    short_stay_official = _official_value(official, "I552", "PLACE")
    if short_stay_local > 0 and short_stay_official is not None:
        rows.append(
            _calibration_row(
                "short_stay_persons_proxy",
                "collective_locative",
                1.0,
                round(short_stay_official / short_stay_local, 3),
                float(short_stay_local),
                short_stay_official,
                "I552",
                "PLACE",
                "Comparaison de controle entre la somme locale des capacites en personnes et le total Insee des hebergements de courte duree.",
            )
        )

    return pd.DataFrame(rows)


def prepare_accommodation_overlap_audit(accommodation_capacity: pd.DataFrame, config: dict) -> pd.DataFrame:
    """
    Produit un audit explicite du risque de double comptage residentiel/touristique.
    """
    if accommodation_capacity.empty:
        return pd.DataFrame(
            columns=[
                "building_id",
                "building_usage_1",
                "source_types",
                "capacity_lits",
                "overlap_risk",
                "recommended_action",
            ]
        )

    audit = accommodation_capacity.copy()
    classifications = audit.apply(
        lambda row: classify_accommodation_overlap_risk(row.get("source_types", ""), row.get("building_usage_1", ""), config),
        axis=1,
    )
    audit["overlap_risk"] = classifications.apply(lambda item: item[0])
    audit["recommended_action"] = classifications.apply(lambda item: item[1])
    return audit[
        [
            "building_id",
            "building_usage_1",
            "source_types",
            "offer_names",
            "capacity_lits",
            "capacity_methods",
            "overlap_risk",
            "recommended_action",
        ]
    ].sort_values(["overlap_risk", "capacity_lits"], ascending=[True, False])


def prepare_beach_polygons(config: dict) -> gpd.GeoDataFrame:
    """
    Filtre les plages de la commune puis bufferise les lignes en polygones.
    """
    beaches_path = Path(config["data_paths"]["input"]["beaches_raw"])
    beaches = gpd.read_file(beaches_path)
    beaches = beaches.to_crs(epsg=config["project"]["crs_epsg"])

    commune_name, _ = _get_commune_filters(config)
    beaches = beaches[beaches["commune"].fillna("").apply(_normalise_commune_key) == commune_name].copy()

    buffer_m = float(config.get("external_preparation", {}).get("beaches", {}).get("line_buffer_m", 15.0))
    beaches["geometry"] = beaches.geometry.buffer(buffer_m, cap_style=2, join_style=2)

    boundary = load_study_area_boundary(config, strict=True)
    beaches = gpd.clip(beaches, boundary)
    beaches = beaches.reset_index(drop=True)
    beaches["zone_id"] = beaches["id"].astype(str)
    beaches["zone_name"] = beaches["nom"]
    beaches["source_type"] = "ddtm44_beach_lines_buffered"
    return beaches[["zone_id", "zone_name", "commune", "source_type", "geometry"]]


def _write_dataframe(df: pd.DataFrame, path: Path, sep: str = ",") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, sep=sep, index=False)
    return path


def _write_geodataframe(gdf: gpd.GeoDataFrame, path: Path, layer: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(path, layer=layer, driver="GPKG")
    return path


def prepare_external_sources(config: dict) -> dict[str, Path]:
    """
    Execute l'ensemble de la preparation externe et ecrit les tables resultat.
    """
    output_dir = Path(config.get("external_preparation", {}).get("output_dir", "data/02_interim/external"))
    output_dir.mkdir(parents=True, exist_ok=True)

    tourism = load_and_harmonise_tourism_offers(config)
    tourism_path = _write_geodataframe(tourism, output_dir / "batz_tourism_offers.gpkg", "tourism_offers")

    restaurants = prepare_restaurants_table(tourism)
    restaurants_path = _write_dataframe(restaurants, output_dir / "batz_restaurants_prepared.csv", sep=";")

    accommodation_capacity = prepare_accommodation_capacity_table(tourism, config)
    accommodation_path = _write_dataframe(accommodation_capacity, output_dir / "batz_accommodation_capacity.csv")

    accommodation_summary = prepare_accommodation_summary(tourism, accommodation_capacity, config)
    accommodation_summary_path = _write_dataframe(accommodation_summary, output_dir / "batz_accommodation_summary.csv")

    accommodation_calibration = prepare_accommodation_calibration(tourism, config)
    accommodation_calibration_path = _write_dataframe(accommodation_calibration, output_dir / "batz_accommodation_calibration.csv")

    accommodation_overlap = prepare_accommodation_overlap_audit(accommodation_capacity, config)
    accommodation_overlap_path = _write_dataframe(accommodation_overlap, output_dir / "batz_accommodation_overlap_audit.csv")

    beaches = prepare_beach_polygons(config)
    beaches_path = _write_geodataframe(beaches, output_dir / "batz_beaches.gpkg", "beaches")

    logger.info("Preparation externe terminee dans %s", output_dir)
    return {
        "tourism_offers": tourism_path,
        "restaurants": restaurants_path,
        "accommodation_capacity": accommodation_path,
        "accommodation_summary": accommodation_summary_path,
        "accommodation_calibration": accommodation_calibration_path,
        "accommodation_overlap_audit": accommodation_overlap_path,
        "beaches": beaches_path,
    }
