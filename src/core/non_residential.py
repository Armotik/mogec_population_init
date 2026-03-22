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


def activity_capacity_for_rule(df: gpd.GeoDataFrame, rule: dict) -> pd.Series:
    """
    Calcule la capacité théorique d'une règle d'activité avant modulation horaire.

    La grandeur obtenue correspond à une population potentielle de référence,
    dérivée de la surface bâtie puis pondérée par un ratio d'usagers.
    """
    mask = _usage_mask(df, rule.get('usage_any_of', []))
    sqm_per_person = float(rule.get('sqm_per_person', 30.0))
    client_ratio = float(rule.get('client_ratio', 0.0))
    capacity = pd.Series(0.0, index=df.index)
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


def integrer_population_non_residentielle(gdf: gpd.GeoDataFrame, config: dict) -> gpd.GeoDataFrame:
    """
    Ajoute au `pop_t0` les composantes non résidentielles configurées.
    """
    df = _ensure_columns(gdf)
    model_cfg = config.get('non_residential_model', {})

    # A. Hébergements touristiques
    accommodation_cfg = model_cfg.get('accommodation', {})
    if accommodation_cfg.get('enabled', False):
        table = _load_capacity_table(accommodation_cfg.get('capacity_table'))
        if table is not None and not table.empty:
            join_key = accommodation_cfg.get('join_key', 'building_id')
            capacity_column = accommodation_cfg.get('capacity_column', 'capacity_lits')
            cols_to_keep = [join_key, capacity_column]
            for optional_col in ['source_types', 'offer_names', 'building_usage_1', 'overlap_risk', 'recommended_action']:
                if optional_col in table.columns:
                    cols_to_keep.append(optional_col)
            table = table[cols_to_keep].copy()
            table = table.rename(columns={capacity_column: 'capacity_lits'})
            df = df.merge(table, on=join_key, how='left')
            df['accommodation_capacity_raw'] = df['capacity_lits'].fillna(0.0)
            if 'source_types' in df.columns:
                df['accommodation_source_types'] = df['source_types'].fillna("")
            if 'offer_names' in df.columns:
                df['accommodation_offer_names'] = df['offer_names'].fillna("")

            classifications = df.apply(lambda row: _classify_overlap_risk(row, accommodation_cfg), axis=1)
            df['accommodation_overlap_risk'] = classifications.apply(lambda item: item[0])
            df['accommodation_overlap_action'] = classifications.apply(lambda item: item[1])

            retained_capacity = df['accommodation_capacity_raw'].copy()
            prevention_cfg = accommodation_cfg.get('double_count_prevention', {})
            if prevention_cfg.get('enabled', False):
                exclude_mask = df['accommodation_overlap_action'] == 'excluded_residential_overlap'
                retained_capacity.loc[exclude_mask] = 0.0
                logger.info(
                    "Prévention du double comptage : %s bâtiments d'hébergement résidentiels exclus du surplus touristique.",
                    int(exclude_mask.sum()),
                )

            df['accommodation_capacity_retained'] = retained_capacity
            tau_occupation = float(accommodation_cfg.get('tau_occupation', 0.0))
            alpha_tourist_t0 = float(accommodation_cfg.get('alpha_tourist_t0', 1.0))
            df['pop_nonres_accommodation'] = _round_population(
                df['accommodation_capacity_retained'].fillna(0.0) * tau_occupation * alpha_tourist_t0
            )
            df['pop_t0'] = df['pop_t0'] + df['pop_nonres_accommodation']
            drop_cols = [column for column in ['capacity_lits', 'source_types', 'offer_names', 'building_usage_1', 'overlap_risk', 'recommended_action'] if column in df.columns]
            df = df.drop(columns=drop_cols)

    # B. Commerces et équipements structurants
    activities_cfg = model_cfg.get('activities', {})
    if activities_cfg.get('enabled', False):
        total_activity = pd.Series(0.0, index=df.index)
        for rule in activities_cfg.get('rules', []):
            base_capacity = activity_capacity_for_rule(df, rule)
            alpha_t0 = float(rule.get('alpha_t0', 0.0))
            total_activity += base_capacity * alpha_t0
            df['activity_capacity_base'] = df['activity_capacity_base'] + base_capacity
        df['pop_nonres_activity'] = _round_population(total_activity)
        df['pop_t0'] = df['pop_t0'] + df['pop_nonres_activity']

    return df


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

    path_str = beaches_cfg.get('zones_path')
    if not path_str:
        return _ensure_columns(gdf)

    path = Path(path_str)
    if not path.exists():
        logger.warning(f"Fichier de zones de plage introuvable : {path}")
        return _ensure_columns(gdf)

    layer = beaches_cfg.get('zones_layer')
    beaches = gpd.read_file(path, layer=layer) if layer else gpd.read_file(path)
    beaches = beaches.to_crs(gdf.crs)

    zone_id_column = beaches_cfg.get('zone_id_column', 'zone_id')
    if zone_id_column not in beaches.columns:
        beaches[zone_id_column] = [f"plage_{index}" for index in range(len(beaches))]

    density = float(beaches_cfg.get('sqm_per_person', 5.0))
    beaches['building_id'] = beaches[zone_id_column].apply(lambda value: f"{config['project']['building_id']['prefix']}_PLAGE_{value}")
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

    for column, default in [
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
    ]:
        beaches[column] = default

    beaches['households'] = [[] for _ in range(len(beaches))]
    beaches['liste_roles'] = [[] for _ in range(len(beaches))]

    common_columns = list(dict.fromkeys(list(gdf.columns) + list(beaches.columns)))
    return pd.concat(
        [gdf.reindex(columns=common_columns), beaches.reindex(columns=common_columns)],
        ignore_index=True
    )
