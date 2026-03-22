"""
Construction de la matrice de présence horaire.

La matrice est calculée à partir des foyers générés en amont. Chaque membre se
voit attribuer des horaires de départ et de retour paramétrables par rôle et
par contexte (semaine, week-end, vacances), avec un étalement gaussien pour
éviter des départs synchrones artificiels.
"""

import logging

import geopandas as gpd
import numpy as np
import pandas as pd

from src.core.non_residential import activity_alpha_for_hour, activity_capacity_for_rule
from src.core.randomness import build_rng
from src.core.restaurants import restaurants_ouverts_a_l_heure

logger = logging.getLogger(__name__)


def _parse_hour_slot(time_str: str, end: bool = False) -> int:
    hour_str, minute_str = time_str.split(":")
    hour = int(hour_str)
    minute = int(minute_str)
    if end and minute > 0:
        return min(23, hour)
    return hour


def _context_key(config: dict, role: str | None = None) -> str:
    day = config['scenario']['day_of_week']
    weekend_days = config['temporal_model']['calendars'].get('weekend_days', ['Samedi', 'Dimanche'])
    is_weekend = day in weekend_days
    is_holiday = bool(config['scenario'].get('is_school_holiday', False))

    if day == 'Dimanche':
        return 'sunday'
    if is_weekend:
        return 'weekend'
    # Les vacances scolaires ne doivent pas annuler les profils de travail des
    # adultes par défaut. On reserve donc le contexte `holiday` aux roles pour
    # lesquels cette information est directement pertinente.
    if is_holiday and role == 'scolaire':
        return 'holiday'
    return 'weekday'


def _resolve_role_profile(role: str, config: dict) -> dict:
    key = _context_key(config, role=role)
    role_profiles = config['temporal_model']['role_profiles'].get(role, {})
    if key in role_profiles:
        if key == 'sunday' and 'weekend' in role_profiles:
            return {**role_profiles['weekend'], **role_profiles['sunday']}
        return role_profiles[key]
    if key == 'sunday' and 'weekend' in role_profiles:
        return role_profiles['weekend']
    return role_profiles.get('weekday', {})


def _scenario_modifiers(config: dict) -> dict:
    default_context = config['temporal_model'].get('scenario_context', {})
    scenario_context = config['scenario'].get('temporal_context', {})
    merged = {**default_context, **scenario_context}
    merged.setdefault('weather_index', 1.0)
    merged.setdefault('alert_level', 0.0)
    merged['religious_day'] = bool(merged.get('religious_day', False) or config['scenario']['day_of_week'] == 'Dimanche')
    return merged


def _probability_with_context(base_probability: float, config: dict, family: str) -> float:
    modifiers = config['temporal_model'].get('modifiers', {})
    context = _scenario_modifiers(config)

    weather_index = float(context.get('weather_index', 1.0))
    alert_level = float(context.get('alert_level', 0.0))

    if family == 'restaurant':
        weather_factor = 1.0 - (1.0 - weather_index) * float(modifiers.get('restaurant_weather_sensitivity', 0.0))
        alert_factor = 1.0 - alert_level * float(modifiers.get('restaurant_alert_sensitivity', 0.0))
    elif family == 'activity':
        weather_factor = 1.0 - (1.0 - weather_index) * float(modifiers.get('activity_weather_sensitivity', 0.0))
        alert_factor = 1.0 - alert_level * float(modifiers.get('activity_alert_sensitivity', 0.0))
    else:
        weather_factor = 1.0 - (1.0 - weather_index) * float(modifiers.get('leisure_weather_sensitivity', 0.0))
        alert_factor = 1.0 - alert_level * float(modifiers.get('leisure_alert_sensitivity', 0.0))

    probability = base_probability * max(0.0, weather_factor) * max(0.0, alert_factor)
    return float(np.clip(probability, 0.0, 1.0))


def _sample_gaussian_hour(distribution: dict, rng: np.random.Generator) -> int:
    value = rng.normal(float(distribution['mean']), float(distribution['std']))
    hour = int(round(value))
    return int(np.clip(hour, int(distribution['min']), int(distribution['max'])))


def _member_schedule(member: dict, config: dict, rng: np.random.Generator) -> dict:
    role = member['role']
    profile = _resolve_role_profile(role, config)
    schedule = {
        'role': role,
        'destination_id': member['destination_id'],
        'base_destination_id': member['destination_id'],
        'enabled': bool(profile.get('enabled', True)),
        'departure_hour': None,
        'return_hour': None,
        'profile': profile,
        'escort_mode': 'none',
        'school_access_status': 'not_applicable',
        'school_distance_m': None,
        'escort_guardian_id': None,
        'escort_child_ids': [],
        'escort_stop_hours': [],
        'escort_dropoff_destinations': {},
        'escort_pickup_destinations': {},
    }

    if 'departure' in profile:
        schedule['departure_hour'] = _sample_gaussian_hour(profile['departure'], rng)
    if 'return' in profile:
        schedule['return_hour'] = _sample_gaussian_hour(profile['return'], rng)
        if schedule['departure_hour'] is not None and schedule['return_hour'] < schedule['departure_hour']:
            schedule['return_hour'] = schedule['departure_hour']

    return schedule


def _first_destination_for_hour(destinations_by_hour: dict[int, list[str]], hour: int) -> str | None:
    destinations = destinations_by_hour.get(hour, [])
    return str(destinations[0]) if destinations else None


def _register_escort_stop(schedule: dict, hour: int | None, destination_id: str, member_id: str, stop_kind: str) -> None:
    if hour is None or destination_id in {"DOMICILE", "EXTERIEUR", "None", None}:
        return

    if stop_kind == 'dropoff':
        destination_map = schedule.setdefault('escort_dropoff_destinations', {})
    else:
        destination_map = schedule.setdefault('escort_pickup_destinations', {})
    destination_map.setdefault(int(hour), []).append(str(destination_id))

    escorted_ids = schedule.setdefault('escort_child_ids', [])
    if member_id not in escorted_ids:
        escorted_ids.append(member_id)

    stop_hours = schedule.setdefault('escort_stop_hours', [])
    if int(hour) not in stop_hours:
        stop_hours.append(int(hour))


def _apply_household_constraints(
    household: dict,
    schedules: dict[str, dict],
    config: dict,
    home_centroid,
    building_lookup: pd.DataFrame,
) -> None:
    household_cfg = config['temporal_model'].get('household_dynamics', {})
    if not household_cfg.get('enable_school_escort', False):
        return

    guardian_id = household.get('guardian_member_id')
    guardian_schedule = schedules.get(guardian_id) if guardian_id else None
    walk_max_distance = float(household_cfg.get('school_walk_max_distance_m', 1200))
    pickup_overlap_hours = int(household_cfg.get('school_pickup_overlap_hours', 1))

    for member in household['members']:
        if member['role'] != 'scolaire':
            continue

        child_schedule = schedules[member['member_id']]
        if not child_schedule.get('enabled', True):
            child_schedule['school_access_status'] = 'inactive'
            continue

        school_id = child_schedule.get('destination_id')
        if school_id in {"DOMICILE", "EXTERIEUR", "None", None} or school_id not in building_lookup.index:
            child_schedule['school_access_status'] = 'outside_commune'
            continue

        school_centroid = building_lookup.loc[school_id].geometry.centroid
        distance_m = float(home_centroid.distance(school_centroid))
        child_schedule['school_distance_m'] = round(distance_m, 1)

        if distance_m <= walk_max_distance:
            child_schedule['escort_mode'] = 'walk'
            child_schedule['school_access_status'] = 'walk'
            continue

        if guardian_schedule is None:
            child_schedule['escort_mode'] = 'unverified'
            child_schedule['school_access_status'] = 'unverified_far'
            continue

        child_schedule['escort_mode'] = 'escort'
        child_schedule['school_access_status'] = 'escort'
        child_schedule['escort_guardian_id'] = guardian_id

        child_departure = child_schedule.get('departure_hour')
        child_return = child_schedule.get('return_hour')

        _register_escort_stop(guardian_schedule, child_departure, school_id, member['member_id'], 'dropoff')

        guardian_role = guardian_schedule.get('role')
        guardian_return = guardian_schedule.get('return_hour')
        pickup_possible = guardian_role in {'senior', 'inactif'}
        if not pickup_possible and child_return is not None and guardian_return is not None:
            pickup_possible = child_return >= (guardian_return - pickup_overlap_hours)
        if pickup_possible:
            _register_escort_stop(guardian_schedule, child_return, school_id, member['member_id'], 'pickup')

        if child_departure is not None:
            if guardian_schedule.get('departure_hour') is None:
                guardian_schedule['departure_hour'] = child_departure
            else:
                guardian_schedule['departure_hour'] = min(guardian_schedule['departure_hour'], child_departure)


def _sample_restaurant_destination(restaurants_by_hour: dict[int, list[str]], hour: int, rng: np.random.Generator) -> str:
    available = restaurants_by_hour.get(hour, [])
    if not available:
        return "DOMICILE"
    return str(rng.choice(available))


def _assign_presence(
    presence_matrix: dict[int, np.ndarray],
    building_index_by_id: dict[str, int],
    home_index: int,
    destination_id: str,
    hour: int,
) -> None:
    if destination_id == "DOMICILE":
        presence_matrix[home_index][hour] += 1
        return

    if destination_id in {"EXTERIEUR", "None", None}:
        return

    target_index = building_index_by_id.get(str(destination_id))
    if target_index is None:
        return

    presence_matrix[target_index][hour] += 1


def _destination_for_member_hour(
    role: str,
    schedule: dict,
    profile: dict,
    hour: int,
    rng: np.random.Generator,
    config: dict,
    restaurants_by_hour: dict[int, list[str]],
    cultes_ids: list[str],
    scenario_context: dict,
) -> str:
    escort_dropoff = _first_destination_for_hour(schedule.get('escort_dropoff_destinations', {}), hour)
    if escort_dropoff is not None:
        return escort_dropoff

    escort_pickup = _first_destination_for_hour(schedule.get('escort_pickup_destinations', {}), hour)
    if escort_pickup is not None:
        return escort_pickup

    destination = "DOMICILE"

    if role == 'scolaire':
        if schedule['enabled'] and schedule['destination_id'] not in {"DOMICILE", "EXTERIEUR"}:
            if schedule['departure_hour'] is not None and schedule['return_hour'] is not None:
                if schedule['departure_hour'] <= hour <= schedule['return_hour']:
                    destination = schedule['destination_id']

    elif role == 'actif_local':
        if schedule['enabled'] and schedule['destination_id'] not in {"DOMICILE", "EXTERIEUR"}:
            if schedule['departure_hour'] is not None and schedule['return_hour'] is not None:
                if schedule['departure_hour'] <= hour <= schedule['return_hour']:
                    destination = schedule['destination_id']

                lunch_cfg = profile.get('lunch', {})
                lunch_hours = lunch_cfg.get('hours', [])
                if hour in lunch_hours:
                    restaurant_probability = _probability_with_context(
                        float(lunch_cfg.get('at_restaurant_probability', 0.0)),
                        config,
                        'restaurant'
                    )
                    home_probability = float(lunch_cfg.get('at_home_probability', 0.0))
                    draw = rng.random()

                    if draw < restaurant_probability:
                        destination = _sample_restaurant_destination(restaurants_by_hour, hour, rng)
                    elif draw < restaurant_probability + home_probability:
                        destination = "DOMICILE"

    elif role == 'actif_navetteur':
        if schedule['enabled'] and schedule['departure_hour'] is not None and schedule['return_hour'] is not None:
            if schedule['departure_hour'] <= hour <= schedule['return_hour']:
                destination = "EXTERIEUR"

    elif role == 'senior':
        sunday_profile = config['temporal_model']['role_profiles'].get('senior', {}).get('sunday', {})
        if scenario_context.get('religious_day', False) and hour in sunday_profile.get('cult_hours', []):
            cult_probability = _probability_with_context(
                float(sunday_profile.get('cult_probability', 0.0)),
                config,
                'leisure'
            )
            if cultes_ids and rng.random() < cult_probability:
                destination = str(rng.choice(cultes_ids))
        elif hour in profile.get('market_hours', []):
            market_probability = _probability_with_context(
                float(profile.get('market_probability', 0.0)),
                config,
                'leisure'
            )
            if rng.random() < market_probability:
                destination = "EXTERIEUR"
        elif hour in profile.get('midday_restaurant_hours', []):
            restaurant_probability = _probability_with_context(
                float(profile.get('midday_restaurant_probability', 0.0)),
                config,
                'restaurant'
            )
            if rng.random() < restaurant_probability:
                destination = _sample_restaurant_destination(restaurants_by_hour, hour, rng)
        elif hour in profile.get('afternoon_out_hours', []):
            out_probability = _probability_with_context(
                float(profile.get('afternoon_out_probability', 0.0)),
                config,
                'leisure'
            )
            if rng.random() < out_probability:
                destination = "EXTERIEUR"
        elif hour in profile.get('evening_restaurant_hours', []):
            restaurant_probability = _probability_with_context(
                float(profile.get('evening_restaurant_probability', 0.0)),
                config,
                'restaurant'
            )
            if rng.random() < restaurant_probability:
                destination = _sample_restaurant_destination(restaurants_by_hour, hour, rng)

    return destination


def build_member_timelines(df_batiments: gpd.GeoDataFrame, config: dict) -> pd.DataFrame:
    """
    Reconstruit les trajectoires horaires individuelles a partir des foyers.
    """
    df = df_batiments.copy()
    rng = build_rng(config, "temporal")
    cultes_ids = df.loc[df.get('is_culte', False) == True, 'building_id'].astype(str).tolist() if 'is_culte' in df.columns else []
    restaurants_by_hour = {hour: restaurants_ouverts_a_l_heure(df, hour) for hour in range(24)}
    scenario_context = _scenario_modifiers(config)
    building_lookup = df.set_index('building_id') if 'building_id' in df.columns else pd.DataFrame()

    rows: list[dict] = []
    for idx, row in df.iterrows():
        households = row.get('households', [])
        if not households:
            continue

        for household in households:
            schedules = {
                member['member_id']: _member_schedule(member, config, rng)
                for member in household['members']
            }
            _apply_household_constraints(
                household,
                schedules,
                config,
                row.geometry.centroid,
                building_lookup,
            )

            for member in household['members']:
                schedule = schedules[member['member_id']]
                role = schedule['role']
                profile = schedule['profile']
                timeline = []
                states = []

                for hour in range(24):
                    destination = _destination_for_member_hour(
                        role=role,
                        schedule=schedule,
                        profile=profile,
                        hour=hour,
                        rng=rng,
                        config=config,
                        restaurants_by_hour=restaurants_by_hour,
                        cultes_ids=cultes_ids,
                        scenario_context=scenario_context,
                    )
                    timeline.append(destination)
                    if destination == "DOMICILE":
                        states.append("domicile")
                    elif destination in {"EXTERIEUR", "None", None}:
                        states.append("exterieur")
                    else:
                        states.append("interne")

                assigned_destination_id = schedule['destination_id']
                assigned_destination_usage = ""
                assigned_destination_centroid = None
                if assigned_destination_id not in {"DOMICILE", "EXTERIEUR", "None", None} and assigned_destination_id in building_lookup.index:
                    destination_row = building_lookup.loc[assigned_destination_id]
                    assigned_destination_usage = str(destination_row.get('usage_1', ''))
                    centroid = destination_row.geometry.centroid
                    assigned_destination_centroid = [float(centroid.x), float(centroid.y)]

                home_centroid = row.geometry.centroid
                rows.append(
                    {
                        'home_index': idx,
                        'home_building_id': row['building_id'],
                        'household_id': household.get('household_id'),
                        'member_id': member['member_id'],
                        'role': role,
                        'assigned_destination_id': assigned_destination_id,
                        'assigned_destination_usage': assigned_destination_usage,
                        'escort_mode': schedule.get('escort_mode', 'none'),
                        'school_access_status': schedule.get('school_access_status', 'not_applicable'),
                        'school_distance_m': schedule.get('school_distance_m'),
                        'escort_guardian_id': schedule.get('escort_guardian_id'),
                        'escort_child_ids': list(schedule.get('escort_child_ids', [])),
                        'escort_stop_hours': sorted(schedule.get('escort_stop_hours', [])),
                        'timeline_destinations': timeline,
                        'timeline_states': states,
                        'origin_centroid': [float(home_centroid.x), float(home_centroid.y)],
                        'assigned_destination_centroid': assigned_destination_centroid,
                    }
                )

    return pd.DataFrame(rows)


def _apply_beach_population(df: gpd.GeoDataFrame, config: dict) -> gpd.GeoDataFrame:
    beaches_cfg = config.get('non_residential_model', {}).get('beaches', {})
    if not beaches_cfg.get('enabled', False):
        return df

    scenario_cfg = config.get('scenario', {})
    tourism_cfg = scenario_cfg.get('tourisme', {})
    tau_meteo = float(tourism_cfg.get('tau_meteo', 0.0))
    hour_slots = beaches_cfg.get('hour_slots', [])
    other_hours_alpha = float(beaches_cfg.get('other_hours_alpha', 0.0))

    def alpha_for_hour(hour: int) -> float:
        for slot in hour_slots:
            if int(slot['start']) <= hour <= int(slot['end']):
                return float(slot['alpha'])
        return other_hours_alpha

    beach_mask = df.get('exogenous_zone_type').fillna("").eq('plage') if 'exogenous_zone_type' in df.columns else None
    if beach_mask is None or not beach_mask.any():
        return df

    for hour in range(24):
        alpha = alpha_for_hour(hour)
        population = (df.loc[beach_mask, 'beach_capacity'].fillna(0.0) * tau_meteo * alpha).round().astype(int)
        df.loc[beach_mask, f'pop_h{hour}'] = population

    return df


def _apply_activity_population(df: gpd.GeoDataFrame, config: dict) -> gpd.GeoDataFrame:
    """
    Ajoute une population exogène horaire aux bâtiments d'activité.

    Cette composante représente les usagers et clients présents dans les
    commerces et équipements, indépendamment des foyers résidentiels modélisés.
    Elle sert principalement à amplifier la dynamique journalière intra-communale.
    """
    activities_cfg = config.get('non_residential_model', {}).get('activities', {})
    if not activities_cfg.get('enabled', False):
        return df

    context_factor = _probability_with_context(1.0, config, 'activity')
    total_activity = {hour: np.zeros(len(df), dtype=float) for hour in range(24)}

    for rule in activities_cfg.get('rules', []):
        base_capacity = activity_capacity_for_rule(df, rule)
        if float(base_capacity.sum()) == 0.0:
            continue

        for hour in range(24):
            alpha = activity_alpha_for_hour(rule, activities_cfg, hour)
            if alpha <= 0.0:
                continue
            total_activity[hour] += base_capacity.to_numpy() * alpha * context_factor

    for hour in range(24):
        df[f'pop_h{hour}'] = df[f'pop_h{hour}'] + np.round(total_activity[hour]).astype(int)

    return df


def generer_matrice_horaire(df_batiments: gpd.GeoDataFrame, config: dict) -> gpd.GeoDataFrame:
    """
    Calcule la population présente dans chaque bâtiment pour chaque heure.

    Les colonnes `pop_h0` à `pop_h23` sont reconstruites à partir des foyers,
    des destinations probabilistes et des profils temporels définis dans la
    configuration.
    """
    jour_scenario = config['scenario'].get('day_of_week')
    if not jour_scenario:
        raise ValueError("La configuration doit définir 'scenario.day_of_week' pour générer la matrice horaire.")

    logger.info(f"Génération de la matrice horaire 24h (Scénario: {jour_scenario})...")

    df = df_batiments.copy()
    building_index_by_id = {str(row['building_id']): idx for idx, row in df.iterrows()}

    for h in range(24):
        df[f'pop_h{h}'] = 0

    presence_matrix = {idx: np.zeros(24) for idx in df.index}
    member_timelines = build_member_timelines(df, config)
    for _, member_row in member_timelines.iterrows():
        for hour, destination in enumerate(member_row['timeline_destinations']):
            _assign_presence(
                presence_matrix,
                building_index_by_id,
                int(member_row['home_index']),
                destination,
                hour,
            )

    for idx, presence in presence_matrix.items():
        for h in range(24):
            df.at[idx, f'pop_h{h}'] = int(presence[h])

    df = _apply_activity_population(df, config)
    df = _apply_beach_population(df, config)

    logger.info("Matrice horaire 24h générée avec succès.")
    return df
