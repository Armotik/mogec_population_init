"""
Intégration progressive des populations non résidentielles.

Le module ajoute des composantes optionnelles au `pop_t0` résidentiel :
- hébergements touristiques, via une capacité en lits ;
- commerces et équipements structurants, via des règles surfaciques ;
- zones de plage, injectées comme entités exogènes avec dynamique horaire.
"""

import logging
from pathlib import Path

import geopandas as gpd
import pandas as pd

logger = logging.getLogger(__name__)
ACCOMMODATION_OPTIONAL_COLUMNS = [
    'source_types',
    'offer_names',
    'building_usage_1',
    'overlap_risk',
    'recommended_action',
]
ACCOMMODATION_DROP_COLUMNS = [
    'capacity_lits',
    'source_types',
    'offer_names',
    'building_usage_1',
    'overlap_risk',
    'recommended_action',
]
BEACH_DEFAULT_COLUMNS = [
    ('dest_id', None),
    ('prob_senior', 0.0),
    ('prob_enfant', 0.0),
    ('prob_pauvrete', 0.0),
    ('n_scolaire', 0),
    ('n_scolaire_interne', 0),
    ('n_scolaire_exterieur', 0),
    ('n_senior', 0),
    ('n_actif_local', 0),
    ('n_actif_navetteur', 0),
    ('n_inactif', 0),
    ('n_households', 0),
    ('is_restaurant', False),
    ('nom_resto', "None"),
    ('horaires_osm', "None"),
    ('horaires_source', "none"),
    ('restaurant_service_slots', ""),
    ('is_culte', False),
    ('nom_culte', "None"),
]


def _round_population(values: pd.Series) -> pd.Series:
    return values.fillna(0.0).round().astype(int)


def _ensure_columns(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    df = gdf.copy()
    for column, default in [
        ('pop_nonres_accommodation', 0),
        ('pop_nonres_activity', 0),
        ('activity_capacity_base', 0.0),
        ('accommodation_capacity_raw', 0),
        ('accommodation_capacity_retained', 0),
        ('accommodation_source_types', ''),
        ('accommodation_offer_names', ''),
        ('accommodation_overlap_risk', 'none'),
        ('accommodation_overlap_action', 'none'),
        ('exogenous_zone_type', None),
        ('beach_capacity', 0.0),
    ]:
        if column not in df.columns:
            df[column] = default
    return df


def _usage_mask(df: gpd.GeoDataFrame, patterns: list[str]) -> pd.Series:
    if not patterns:
        return pd.Series(False, index=df.index)
    return df['usage_1'].fillna("").apply(
        lambda usage: any(pattern.casefold() in str(usage).casefold() for pattern in patterns)
    )


def _zero_capacity_series(df: gpd.GeoDataFrame) -> pd.Series:
    return pd.Series(0.0, index=df.index)


def activity_capacity_for_rule(df: gpd.GeoDataFrame, rule: dict) -> pd.Series:
    """
    Calcule la capacité théorique d'une règle d'activité avant modulation horaire.

    La grandeur obtenue correspond à une population potentielle de référence,
    dérivée de la surface bâtie puis pondérée par un ratio d'usagers.
    """
    mask = _usage_mask(df, rule.get('usage_any_of', []))
    sqm_per_person = float(rule.get('sqm_per_person', 30.0))
    client_ratio = float(rule.get('client_ratio', 0.0))
    capacity = _zero_capacity_series(df)
    if not mask.any():
        return capacity

    surface = df.loc[mask, 'surface_sol'].fillna(df.loc[mask].geometry.area)
    capacity.loc[mask] = (surface / max(1.0, sqm_per_person)) * (1.0 + client_ratio)
    return capacity


def _activity_alpha_from_slots(profile_cfg: dict, hour: int) -> float:
    for slot in profile_cfg.get('hour_slots', []):
        if int(slot['start']) <= hour <= int(slot['end']):
            return float(slot['alpha'])
    return float(profile_cfg.get('other_hours_alpha', 0.0))


def activity_alpha_for_hour(rule: dict, activities_cfg: dict, hour: int) -> float:
    """
    Résout l'alpha horaire d'une règle d'activité à partir d'un profil nommé.
    """
    profile_name = rule.get('hourly_profile')
    if not profile_name:
        return float(rule.get('alpha_t0', 0.0))
    profile_cfg = activities_cfg.get('profiles', {}).get(profile_name, {})
    return _activity_alpha_from_slots(profile_cfg, hour)


def _load_capacity_table(path_str: str | None) -> pd.DataFrame | None:
    if not path_str:
        return None
    path = Path(path_str)
    if not path.exists():
        logger.warning(f"Table de capacité introuvable : {path}")
        return None
    return pd.read_csv(path)


def _split_source_types(value: object) -> set[str]:
    if pd.isna(value) or value in [None, ""]:
        return set()
    return {part.strip() for part in str(value).split("|") if part.strip()}


def _is_residential_usage(usage: object, accommodation_cfg: dict) -> bool:
    patterns = accommodation_cfg.get('double_count_prevention', {}).get('residential_usage_any_of', ['Résidentiel'])
    usage_text = str(usage or "").casefold()
    return any(pattern.casefold() in usage_text for pattern in patterns)


def _classify_overlap_risk(row: pd.Series, accommodation_cfg: dict) -> tuple[str, str]:
    source_types = _split_source_types(row.get('accommodation_source_types', ''))
    if not source_types:
        return 'none', 'no_accommodation_source'

    if not _is_residential_usage(row.get('usage_1', ''), accommodation_cfg):
        return 'low', 'added_non_residential_building'

    prevention_cfg = accommodation_cfg.get('double_count_prevention', {})
    exclude_source_types = set(prevention_cfg.get('exclude_source_types_on_residential', ['locative']))
    warn_source_types = set(prevention_cfg.get('warn_source_types_on_residential', ['residence']))

    if source_types & exclude_source_types:
        return 'high', 'excluded_residential_overlap'
    if source_types & warn_source_types:
        return 'medium', 'retained_with_warning'
    return 'low', 'added_residential_additive_source'


def _accommodation_columns_to_keep(table: pd.DataFrame, join_key: str, capacity_column: str) -> list[str]:
    columns = [join_key, capacity_column]
    for optional_col in ACCOMMODATION_OPTIONAL_COLUMNS:
        if optional_col in table.columns:
            columns.append(optional_col)
    return columns


def _prepare_accommodation_table(accommodation_cfg: dict) -> pd.DataFrame | None:
    table = _load_capacity_table(accommodation_cfg.get('capacity_table'))
    if table is None or table.empty:
        return None

    join_key = accommodation_cfg.get('join_key', 'building_id')
    capacity_column = accommodation_cfg.get('capacity_column', 'capacity_lits')
    columns = _accommodation_columns_to_keep(table, join_key, capacity_column)
    return table[columns].copy().rename(columns={capacity_column: 'capacity_lits'})


def _merge_accommodation_table(df: gpd.GeoDataFrame, table: pd.DataFrame, accommodation_cfg: dict) -> gpd.GeoDataFrame:
    join_key = accommodation_cfg.get('join_key', 'building_id')
    df = df.merge(table, on=join_key, how='left')
    df['accommodation_capacity_raw'] = df['capacity_lits'].fillna(0.0)
    if 'source_types' in df.columns:
        df['accommodation_source_types'] = df['source_types'].fillna("")
    if 'offer_names' in df.columns:
        df['accommodation_offer_names'] = df['offer_names'].fillna("")
    return df


def _classify_accommodation_overlap(df: gpd.GeoDataFrame, accommodation_cfg: dict) -> gpd.GeoDataFrame:
    classifications = df.apply(lambda row: _classify_overlap_risk(row, accommodation_cfg), axis=1)
    df['accommodation_overlap_risk'] = classifications.apply(lambda item: item[0])
    df['accommodation_overlap_action'] = classifications.apply(lambda item: item[1])
    return df


def _retained_accommodation_capacity(df: gpd.GeoDataFrame, accommodation_cfg: dict) -> pd.Series:
    retained_capacity = df['accommodation_capacity_raw'].copy()
    prevention_cfg = accommodation_cfg.get('double_count_prevention', {})
    if not prevention_cfg.get('enabled', False):
        return retained_capacity

    exclude_mask = df['accommodation_overlap_action'] == 'excluded_residential_overlap'
    retained_capacity.loc[exclude_mask] = 0.0
    logger.info(
        "Prévention du double comptage : %s bâtiments d'hébergement résidentiels exclus du surplus touristique.",
        int(exclude_mask.sum()),
    )
    return retained_capacity


def _apply_accommodation_population(df: gpd.GeoDataFrame, accommodation_cfg: dict) -> gpd.GeoDataFrame:
    table = _prepare_accommodation_table(accommodation_cfg)
    if table is None:
        return df

    df = _merge_accommodation_table(df, table, accommodation_cfg)
    df = _classify_accommodation_overlap(df, accommodation_cfg)
    df['accommodation_capacity_retained'] = _retained_accommodation_capacity(df, accommodation_cfg)

    tau_occupation = float(accommodation_cfg.get('tau_occupation', 0.0))
    alpha_tourist_t0 = float(accommodation_cfg.get('alpha_tourist_t0', 1.0))
    df['pop_nonres_accommodation'] = _round_population(
        df['accommodation_capacity_retained'].fillna(0.0) * tau_occupation * alpha_tourist_t0
    )
    df['pop_t0'] = df['pop_t0'] + df['pop_nonres_accommodation']
    drop_cols = [column for column in ACCOMMODATION_DROP_COLUMNS if column in df.columns]
    return df.drop(columns=drop_cols)


def _activity_population_for_rules(df: gpd.GeoDataFrame, rules: list[dict]) -> tuple[pd.Series, pd.Series]:
    total_population = _zero_capacity_series(df)
    total_capacity = _zero_capacity_series(df)

    for rule in rules:
        base_capacity = activity_capacity_for_rule(df, rule)
        alpha_t0 = float(rule.get('alpha_t0', 0.0))
        total_population += base_capacity * alpha_t0
        total_capacity += base_capacity

    return total_population, total_capacity


def _apply_activity_population_at_t0(df: gpd.GeoDataFrame, activities_cfg: dict) -> gpd.GeoDataFrame:
    total_activity, total_capacity = _activity_population_for_rules(df, activities_cfg.get('rules', []))
    df['activity_capacity_base'] = df['activity_capacity_base'] + total_capacity
    df['pop_nonres_activity'] = _round_population(total_activity)
    df['pop_t0'] = df['pop_t0'] + df['pop_nonres_activity']
    return df


def integrer_population_non_residentielle(gdf: gpd.GeoDataFrame, config: dict) -> gpd.GeoDataFrame:
    """
    Ajoute au `pop_t0` les composantes non résidentielles configurées.
    """
    df = _ensure_columns(gdf)
    model_cfg = config.get('non_residential_model', {})

    # A. Hébergements touristiques
    accommodation_cfg = model_cfg.get('accommodation', {})
    if accommodation_cfg.get('enabled', False):
        df = _apply_accommodation_population(df, accommodation_cfg)

    # B. Commerces et équipements structurants
    activities_cfg = model_cfg.get('activities', {})
    if activities_cfg.get('enabled', False):
        df = _apply_activity_population_at_t0(df, activities_cfg)

    return df


def _load_beach_zones(beaches_cfg: dict, target_crs) -> gpd.GeoDataFrame | None:
    path_str = beaches_cfg.get('zones_path')
    if not path_str:
        return None

    path = Path(path_str)
    if not path.exists():
        logger.warning(f"Fichier de zones de plage introuvable : {path}")
        return None

    layer = beaches_cfg.get('zones_layer')
    beaches = gpd.read_file(path, layer=layer) if layer else gpd.read_file(path)
    return beaches.to_crs(target_crs)


def _ensure_beach_zone_ids(beaches: gpd.GeoDataFrame, zone_id_column: str) -> gpd.GeoDataFrame:
    if zone_id_column in beaches.columns:
        return beaches
    beaches = beaches.copy()
    beaches[zone_id_column] = [f"plage_{index}" for index in range(len(beaches))]
    return beaches


def _build_beach_rows(beaches: gpd.GeoDataFrame, config: dict, beaches_cfg: dict) -> gpd.GeoDataFrame:
    zone_id_column = beaches_cfg.get('zone_id_column', 'zone_id')
    density = float(beaches_cfg.get('sqm_per_person', 5.0))

    beaches = _ensure_beach_zone_ids(beaches, zone_id_column).copy()
    beaches['building_id'] = beaches[zone_id_column].apply(
        lambda value: f"{config['project']['building_id']['prefix']}_PLAGE_{value}"
    )
    beaches['building_id_source'] = 'beach_zone'
    beaches['usage_1'] = 'Plage'
    beaches['nature'] = 'Zone de plage'
    beaches['hauteur'] = 0.0
    beaches['surface_sol'] = beaches.geometry.area
    beaches['pop_t0'] = 0
    beaches['pop_nonres_accommodation'] = 0
    beaches['pop_nonres_activity'] = 0
    beaches['exogenous_zone_type'] = 'plage'
    beaches['beach_capacity'] = beaches['surface_sol'] / max(1.0, density)

    for column, default in BEACH_DEFAULT_COLUMNS:
        beaches[column] = default

    beaches['households'] = [[] for _ in range(len(beaches))]
    beaches['liste_roles'] = [[] for _ in range(len(beaches))]
    return beaches


def _concat_beach_rows(gdf: gpd.GeoDataFrame, beaches: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    common_columns = list(dict.fromkeys(list(gdf.columns) + list(beaches.columns)))
    return pd.concat(
        [gdf.reindex(columns=common_columns), beaches.reindex(columns=common_columns)],
        ignore_index=True
    )


def ajouter_zones_plage_exogenes(gdf: gpd.GeoDataFrame, config: dict) -> gpd.GeoDataFrame:
    """
    Ajoute au GeoDataFrame des zones de plage optionnelles.

    Les plages sont considérées comme des entités exogènes : elles n'hébergent
    pas de foyers, mais reçoivent une population horaire calculée directement
    dans la matrice temporelle.
    """
    beaches_cfg = config.get('non_residential_model', {}).get('beaches', {})
    if not beaches_cfg.get('enabled', False):
        return _ensure_columns(gdf)

    beaches = _load_beach_zones(beaches_cfg, gdf.crs)
    if beaches is None:
        return _ensure_columns(gdf)

    beaches = _build_beach_rows(beaches, config, beaches_cfg)
    return _concat_beach_rows(_ensure_columns(gdf), beaches)
