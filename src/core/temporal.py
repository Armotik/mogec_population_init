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
HOME_DESTINATION = "DOMICILE"
OUTSIDE_DESTINATIONS = {"EXTERIEUR", "None", None}
NON_INTERNAL_DESTINATIONS = {HOME_DESTINATION, *OUTSIDE_DESTINATIONS}
SCHOOL_ROLE = "scolaire"
LOCAL_WORKER_ROLE = "actif_local"
COMMUTER_ROLE = "actif_navetteur"
SENIOR_ROLE = "senior"
INACTIVE_ROLE = "inactif"


def _escort_scoring_config(config: dict) -> dict:
    household_cfg = config.get('temporal_model', {}).get('household_dynamics', {})
    scoring_cfg = household_cfg.get('escort_scoring', {})
    role_weights = scoring_cfg.get('role_weights', {})
    proximity_cfg = scoring_cfg.get('proximity', {})
    pickup_cfg = scoring_cfg.get('pickup', {})
    departure_cfg = scoring_cfg.get('departure_alignment', {})

    return {
        'role_weights': {
            SENIOR_ROLE: float(role_weights.get(SENIOR_ROLE, 16.0)),
            INACTIVE_ROLE: float(role_weights.get(INACTIVE_ROLE, 14.0)),
            LOCAL_WORKER_ROLE: float(role_weights.get(LOCAL_WORKER_ROLE, 12.0)),
            COMMUTER_ROLE: float(role_weights.get(COMMUTER_ROLE, 8.0)),
        },
        'proximity': {
            'max_score': float(proximity_cfg.get('max_score', 10.0)),
            'distance_scale_m': float(proximity_cfg.get('distance_scale_m', 250.0)),
        },
        'pickup': {
            'bonus_if_possible': float(pickup_cfg.get('bonus_if_possible', 20.0)),
            'bonus_if_not_possible': float(pickup_cfg.get('bonus_if_not_possible', 5.0)),
        },
        'departure_alignment': {
            'bonus_if_no_departure': float(departure_cfg.get('bonus_if_no_departure', 4.0)),
            'max_bonus_if_departure_after_child': float(
                departure_cfg.get('max_bonus_if_departure_after_child', 6.0)
            ),
        },
    }


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


def _base_member_schedule(role: str, member: dict, profile: dict) -> dict:
    return {
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
        'school_lunch_home_hours': [],
        'school_presence_hours': [],
    }


def _school_hour_probability(values: dict, hour: int, fallback: float = 0.0) -> float:
    probability = values.get(hour)
    if probability is None:
        probability = values.get(str(hour), fallback)
    return float(np.clip(probability, 0.0, 1.0))


def _is_non_internal_destination(destination_id: str | None) -> bool:
    return destination_id in NON_INTERNAL_DESTINATIONS


def _is_outside_destination(destination_id: str | None) -> bool:
    return destination_id in OUTSIDE_DESTINATIONS


def _sample_school_lunch_home_hours(profile: dict, rng: np.random.Generator) -> list[int]:
    lunch_cfg = profile.get('lunch', {})
    lunch_hours = [int(hour) for hour in lunch_cfg.get('hours', [])]
    sampled_hours = []
    hourly_probabilities = lunch_cfg.get('at_home_probability_by_hour', {})
    default_probability = float(lunch_cfg.get('at_home_probability', 0.0))

    for hour in lunch_hours:
        probability = _school_hour_probability(hourly_probabilities, hour, fallback=default_probability)
        if rng.random() < probability:
            sampled_hours.append(int(hour))
    return sorted(set(sampled_hours))


def _sample_school_presence_hours(schedule: dict, profile: dict, rng: np.random.Generator) -> list[int]:
    if (
        not schedule['enabled']
        or _is_non_internal_destination(schedule['destination_id'])
        or schedule['departure_hour'] is None
        or schedule['return_hour'] is None
    ):
        return []

    attendance_probability_by_hour = profile.get('attendance_probability_by_hour', {})
    school_presence_hours = []
    for hour in range(int(schedule['departure_hour']), int(schedule['return_hour']) + 1):
        if hour in schedule.get('school_lunch_home_hours', []):
            continue
        probability = _school_hour_probability(attendance_probability_by_hour, hour, fallback=1.0)
        if rng.random() < probability:
            school_presence_hours.append(int(hour))
    return school_presence_hours


def _member_schedule(member: dict, config: dict, rng: np.random.Generator) -> dict:
    role = member['role']
    profile = _resolve_role_profile(role, config)
    schedule = _base_member_schedule(role, member, profile)

    schedule['departure_hour'] = _sample_schedule_hour(profile, 'departure', rng)
    schedule['return_hour'] = _sample_schedule_hour(profile, 'return', rng)
    _normalize_schedule_time_bounds(schedule)

    if role == SCHOOL_ROLE:
        schedule['school_lunch_home_hours'] = _sample_school_lunch_home_hours(profile, rng)
        schedule['school_presence_hours'] = _sample_school_presence_hours(schedule, profile, rng)

    return schedule


def _sample_schedule_hour(profile: dict, key: str, rng: np.random.Generator) -> int | None:
    if key not in profile:
        return None
    return _sample_gaussian_hour(profile[key], rng)


def _normalize_schedule_time_bounds(schedule: dict) -> None:
    departure_hour = schedule.get('departure_hour')
    return_hour = schedule.get('return_hour')
    if departure_hour is None or return_hour is None:
        return
    if return_hour < departure_hour:
        schedule['return_hour'] = departure_hour


def _first_destination_for_hour(destinations_by_hour: dict[int, list[str]], hour: int) -> str | None:
    destinations = destinations_by_hour.get(hour, [])
    return str(destinations[0]) if destinations else None


def _register_escort_stop(schedule: dict, hour: int | None, destination_id: str, member_id: str, stop_kind: str) -> None:
    if hour is None or _is_non_internal_destination(destination_id):
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


def _guardian_can_dropoff_child(guardian_schedule: dict, child_departure: int | None) -> bool:
    guardian_role = guardian_schedule.get('role')
    if guardian_role in {SENIOR_ROLE, INACTIVE_ROLE}:
        return True
    if child_departure is None:
        return False
    guardian_departure = guardian_schedule.get('departure_hour')
    if guardian_departure is None:
        return True
    return guardian_departure >= child_departure


def _guardian_can_pickup_child(
    guardian_schedule: dict,
    child_departure: int | None,
    child_return: int | None,
    pickup_overlap_hours: int,
) -> bool:
    guardian_role = guardian_schedule.get('role')
    if guardian_role in {SENIOR_ROLE, INACTIVE_ROLE}:
        return child_return is not None

    guardian_departure = guardian_schedule.get('departure_hour')
    guardian_return = guardian_schedule.get('return_hour')
    if child_return is None or guardian_departure is None or guardian_return is None:
        return False

    work_start = min(guardian_departure, guardian_return)
    work_end = max(guardian_departure, guardian_return)
    earliest_pickup_hour = max(work_start, work_end - max(0, int(pickup_overlap_hours)))
    if child_return < earliest_pickup_hour:
        return False

    if child_departure is not None and child_return < child_departure:
        return False

    return True


def _sync_guardian_departure_with_child(guardian_schedule: dict, child_departure: int | None) -> None:
    if child_departure is None:
        return
    guardian_departure = guardian_schedule.get('departure_hour')
    if guardian_departure is None:
        guardian_schedule['departure_hour'] = child_departure
        return
    guardian_schedule['departure_hour'] = min(guardian_departure, child_departure)


def _sync_guardian_return_with_child_pickup(guardian_schedule: dict, child_return: int | None) -> None:
    if child_return is None:
        return
    if guardian_schedule.get('role') in {SENIOR_ROLE, INACTIVE_ROLE}:
        return

    guardian_departure = guardian_schedule.get('departure_hour')
    guardian_return = guardian_schedule.get('return_hour')
    if guardian_return is None:
        return
    if guardian_departure is not None and child_return < guardian_departure:
        return

    guardian_schedule['return_hour'] = min(guardian_return, child_return)


def _guardian_school_proximity_score(
    guardian_schedule: dict,
    school_id: str,
    building_lookup: pd.DataFrame,
    scoring_cfg: dict,
) -> float:
    destination_id = guardian_schedule.get('base_destination_id', guardian_schedule.get('destination_id'))
    destination_id_str = str(destination_id) if destination_id is not None else None
    if _is_non_internal_destination(destination_id):
        return 0.0
    if destination_id_str not in building_lookup.index or school_id not in building_lookup.index:
        return 0.0

    school_centroid = building_lookup.loc[school_id].geometry.centroid
    destination_centroid = building_lookup.loc[destination_id_str].geometry.centroid
    distance_m = float(school_centroid.distance(destination_centroid))
    max_score = float(scoring_cfg['proximity']['max_score'])
    scale_m = max(1e-6, float(scoring_cfg['proximity']['distance_scale_m']))
    return max(0.0, max_score - (distance_m / scale_m))


def _guardian_feasibility_score(
    member: dict,
    guardian_schedule: dict,
    school_id: str,
    child_departure: int | None,
    child_return: int | None,
    pickup_overlap_hours: int,
    building_lookup: pd.DataFrame,
    scoring_cfg: dict,
) -> float | None:
    if member.get('role') not in {LOCAL_WORKER_ROLE, COMMUTER_ROLE, SENIOR_ROLE, INACTIVE_ROLE}:
        return None
    if not _guardian_can_dropoff_child(guardian_schedule, child_departure):
        return None

    can_pickup = _guardian_can_pickup_child(
        guardian_schedule,
        child_departure,
        child_return,
        pickup_overlap_hours,
    )
    role_score = float(scoring_cfg['role_weights'].get(member.get('role'), 0.0))
    score = role_score + _guardian_school_proximity_score(
        guardian_schedule,
        school_id,
        building_lookup,
        scoring_cfg,
    )
    score += (
        float(scoring_cfg['pickup']['bonus_if_possible'])
        if can_pickup
        else float(scoring_cfg['pickup']['bonus_if_not_possible'])
    )

    guardian_departure = guardian_schedule.get('departure_hour')
    if child_departure is not None:
        if guardian_departure is None:
            score += float(scoring_cfg['departure_alignment']['bonus_if_no_departure'])
        else:
            score += min(
                float(scoring_cfg['departure_alignment']['max_bonus_if_departure_after_child']),
                max(0.0, float(guardian_departure - child_departure)),
            )

    return score


def _select_guardian_for_child(
    household: dict,
    schedules: dict[str, dict],
    school_id: str,
    child_departure: int | None,
    child_return: int | None,
    pickup_overlap_hours: int,
    building_lookup: pd.DataFrame,
    scoring_cfg: dict,
) -> tuple[str | None, dict | None]:
    best_guardian_id = None
    best_score = None

    for member in household.get('members', []):
        member_id = member.get('member_id')
        if member_id not in schedules:
            continue
        guardian_schedule = schedules[member_id]
        score = _guardian_feasibility_score(
            member,
            guardian_schedule,
            school_id,
            child_departure,
            child_return,
            pickup_overlap_hours,
            building_lookup,
            scoring_cfg,
        )
        if score is None:
            continue
        if best_score is None or score > best_score:
            best_score = score
            best_guardian_id = member_id

    if best_guardian_id is None:
        return None, None
    return str(best_guardian_id), schedules[best_guardian_id]


def _school_id_for_child_schedule(child_schedule: dict, building_lookup: pd.DataFrame) -> str | None:
    school_id = child_schedule.get('destination_id')
    school_id_str = str(school_id) if school_id is not None else None
    if _is_non_internal_destination(school_id) or school_id_str not in building_lookup.index:
        return None
    return school_id_str


def _school_distance(home_centroid, school_id: str, building_lookup: pd.DataFrame) -> float:
    school_centroid = building_lookup.loc[school_id].geometry.centroid
    return float(home_centroid.distance(school_centroid))


def _apply_child_school_constraint(
    member: dict,
    household: dict,
    schedules: dict[str, dict],
    child_schedule: dict,
    walk_max_distance: float,
    pickup_overlap_hours: int,
    home_centroid,
    building_lookup: pd.DataFrame,
    scoring_cfg: dict,
) -> None:
    if not child_schedule.get('enabled', True):
        child_schedule['school_access_status'] = 'inactive'
        return

    school_id = _school_id_for_child_schedule(child_schedule, building_lookup)
    if school_id is None:
        child_schedule['school_access_status'] = 'outside_commune'
        return

    distance_m = _school_distance(home_centroid, school_id, building_lookup)
    child_schedule['school_distance_m'] = round(distance_m, 1)

    if distance_m <= walk_max_distance:
        child_schedule['escort_mode'] = 'walk'
        child_schedule['school_access_status'] = 'walk'
        return

    child_departure = child_schedule.get('departure_hour')
    child_return = child_schedule.get('return_hour')
    guardian_id, guardian_schedule = _select_guardian_for_child(
        household=household,
        schedules=schedules,
        school_id=school_id,
        child_departure=child_departure,
        child_return=child_return,
        pickup_overlap_hours=pickup_overlap_hours,
        building_lookup=building_lookup,
        scoring_cfg=scoring_cfg,
    )

    if guardian_schedule is None or guardian_id is None:
        child_schedule['escort_mode'] = 'unverified'
        child_schedule['school_access_status'] = 'unverified_far_no_guardian'
        return

    child_schedule['escort_mode'] = 'escort'
    child_schedule['school_access_status'] = 'escort'
    child_schedule['escort_guardian_id'] = guardian_id

    _register_escort_stop(guardian_schedule, child_departure, school_id, member['member_id'], 'dropoff')
    if _guardian_can_pickup_child(guardian_schedule, child_departure, child_return, pickup_overlap_hours):
        _register_escort_stop(guardian_schedule, child_return, school_id, member['member_id'], 'pickup')
        _sync_guardian_return_with_child_pickup(guardian_schedule, child_return)
    else:
        child_schedule['school_access_status'] = 'escort_dropoff_only'
    _sync_guardian_departure_with_child(guardian_schedule, child_departure)


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

    walk_max_distance = float(household_cfg.get('school_walk_max_distance_m', 1200))
    pickup_overlap_hours = int(household_cfg.get('school_pickup_overlap_hours', 1))
    scoring_cfg = _escort_scoring_config(config)

    for member in household['members']:
        if member['role'] != SCHOOL_ROLE:
            continue

        child_schedule = schedules[member['member_id']]
        _apply_child_school_constraint(
            member,
            household,
            schedules,
            child_schedule,
            walk_max_distance,
            pickup_overlap_hours,
            home_centroid,
            building_lookup,
            scoring_cfg,
        )


def _sample_restaurant_destination(restaurants_by_hour: dict[int, list[str]], hour: int, rng: np.random.Generator) -> str:
    available = restaurants_by_hour.get(hour, [])
    if not available:
        return HOME_DESTINATION
    return str(rng.choice(available))


def _assign_presence(
    presence_matrix: dict[int, np.ndarray],
    building_index_by_id: dict[str, int],
    home_index: int,
    destination_id: str,
    hour: int,
) -> None:
    if destination_id == HOME_DESTINATION:
        presence_matrix[home_index][hour] += 1
        return

    if destination_id in OUTSIDE_DESTINATIONS:
        return

    target_index = building_index_by_id.get(str(destination_id))
    if target_index is None:
        return

    presence_matrix[target_index][hour] += 1


def _school_destination_for_hour(schedule: dict, hour: int) -> str:
    if not schedule.get('enabled', True):
        return HOME_DESTINATION

    destination_id = schedule.get('destination_id')
    if _is_outside_destination(destination_id):
        departure_hour = schedule.get('departure_hour')
        return_hour = schedule.get('return_hour')
        if departure_hour is None or return_hour is None:
            return HOME_DESTINATION
        if departure_hour <= hour <= return_hour:
            return "EXTERIEUR"
        return HOME_DESTINATION

    if not _is_non_internal_destination(destination_id):
        if hour in schedule.get('school_presence_hours', []):
            return destination_id
    return HOME_DESTINATION


def _actif_local_destination_for_hour(
    schedule: dict,
    profile: dict,
    hour: int,
    rng: np.random.Generator,
    config: dict,
    restaurants_by_hour: dict[int, list[str]],
) -> str:
    destination = HOME_DESTINATION
    if not schedule['enabled'] or _is_non_internal_destination(schedule['destination_id']):
        return destination
    if schedule['departure_hour'] is None or schedule['return_hour'] is None:
        return destination

    if schedule['departure_hour'] <= hour <= schedule['return_hour']:
        destination = schedule['destination_id']

    lunch_cfg = profile.get('lunch', {})
    lunch_hours = lunch_cfg.get('hours', [])
    if hour not in lunch_hours:
        return destination

    restaurant_probability = _probability_with_context(
        float(lunch_cfg.get('at_restaurant_probability', 0.0)),
        config,
        'restaurant'
    )
    home_probability = float(lunch_cfg.get('at_home_probability', 0.0))
    draw = rng.random()

    if draw < restaurant_probability:
        return _sample_restaurant_destination(restaurants_by_hour, hour, rng)
    if draw < restaurant_probability + home_probability:
        return HOME_DESTINATION
    return destination


def _actif_navetteur_destination_for_hour(schedule: dict, hour: int) -> str:
    if schedule['enabled'] and schedule['departure_hour'] is not None and schedule['return_hour'] is not None:
        if schedule['departure_hour'] <= hour <= schedule['return_hour']:
            return "EXTERIEUR"
    return HOME_DESTINATION


def _senior_cult_destination(
    hour: int,
    rng: np.random.Generator,
    config: dict,
    cultes_ids: list[str],
    scenario_context: dict,
) -> str | None:
    sunday_profile = config['temporal_model']['role_profiles'].get(SENIOR_ROLE, {}).get('sunday', {})
    if not scenario_context.get('religious_day', False):
        return None
    if hour not in sunday_profile.get('cult_hours', []):
        return None
    cult_probability = _probability_with_context(
        float(sunday_profile.get('cult_probability', 0.0)),
        config,
        'leisure'
    )
    if cultes_ids and rng.random() < cult_probability:
        return str(rng.choice(cultes_ids))
    return None


def _senior_profile_destination(
    profile: dict,
    hour: int,
    rng: np.random.Generator,
    config: dict,
    restaurants_by_hour: dict[int, list[str]],
) -> str | None:
    if hour in profile.get('market_hours', []):
        market_probability = _probability_with_context(
            float(profile.get('market_probability', 0.0)),
            config,
            'leisure'
        )
        if rng.random() < market_probability:
            return "EXTERIEUR"

    if hour in profile.get('midday_restaurant_hours', []):
        restaurant_probability = _probability_with_context(
            float(profile.get('midday_restaurant_probability', 0.0)),
            config,
            'restaurant'
        )
        if rng.random() < restaurant_probability:
            return _sample_restaurant_destination(restaurants_by_hour, hour, rng)

    if hour in profile.get('afternoon_out_hours', []):
        out_probability = _probability_with_context(
            float(profile.get('afternoon_out_probability', 0.0)),
            config,
            'leisure'
        )
        if rng.random() < out_probability:
            return "EXTERIEUR"

    if hour in profile.get('evening_restaurant_hours', []):
        restaurant_probability = _probability_with_context(
            float(profile.get('evening_restaurant_probability', 0.0)),
            config,
            'restaurant'
        )
        if rng.random() < restaurant_probability:
            return _sample_restaurant_destination(restaurants_by_hour, hour, rng)

    return None


def _senior_destination_for_hour(
    profile: dict,
    hour: int,
    rng: np.random.Generator,
    config: dict,
    cultes_ids: list[str],
    restaurants_by_hour: dict[int, list[str]],
    scenario_context: dict,
) -> str:
    cult_destination = _senior_cult_destination(hour, rng, config, cultes_ids, scenario_context)
    if cult_destination is not None:
        return cult_destination
    profile_destination = _senior_profile_destination(profile, hour, rng, config, restaurants_by_hour)
    if profile_destination is not None:
        return profile_destination
    return HOME_DESTINATION


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

    if role == SCHOOL_ROLE:
        return _school_destination_for_hour(schedule, hour)
    if role == LOCAL_WORKER_ROLE:
        return _actif_local_destination_for_hour(schedule, profile, hour, rng, config, restaurants_by_hour)
    if role == COMMUTER_ROLE:
        return _actif_navetteur_destination_for_hour(schedule, hour)
    if role == SENIOR_ROLE:
        return _senior_destination_for_hour(profile, hour, rng, config, cultes_ids, restaurants_by_hour, scenario_context)
    return HOME_DESTINATION


def _cult_building_ids(df: gpd.GeoDataFrame) -> list[str]:
    if 'is_culte' not in df.columns:
        return []
    return df.loc[df['is_culte'] == True, 'building_id'].astype(str).tolist()


def _restaurant_destinations_by_hour(df: gpd.GeoDataFrame) -> dict[int, list[str]]:
    return {hour: restaurants_ouverts_a_l_heure(df, hour) for hour in range(24)}


def _building_lookup(df: gpd.GeoDataFrame) -> pd.DataFrame:
    if 'building_id' not in df.columns:
        return pd.DataFrame()
    lookup = df.copy()
    lookup['building_id'] = lookup['building_id'].astype(str)
    return lookup.set_index('building_id')


def _household_schedules(household: dict, config: dict, rng: np.random.Generator) -> dict[str, dict]:
    return {
        member['member_id']: _member_schedule(member, config, rng)
        for member in household['members']
    }


def _state_for_destination(destination: str | None) -> str:
    if destination == HOME_DESTINATION:
        return "domicile"
    if _is_outside_destination(destination):
        return "exterieur"
    return "interne"


def _member_timeline(
    schedule: dict,
    rng: np.random.Generator,
    config: dict,
    restaurants_by_hour: dict[int, list[str]],
    cultes_ids: list[str],
    scenario_context: dict,
) -> tuple[list[str], list[str]]:
    role = schedule['role']
    profile = schedule['profile']
    destinations: list[str] = []
    states: list[str] = []

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
        destinations.append(destination)
        states.append(_state_for_destination(destination))

    return destinations, states


def _assigned_destination_details(assigned_destination_id: str | None, building_lookup: pd.DataFrame) -> tuple[str, list[float] | None]:
    if _is_non_internal_destination(assigned_destination_id) or assigned_destination_id not in building_lookup.index:
        return "", None

    destination_row = building_lookup.loc[assigned_destination_id]
    centroid = destination_row.geometry.centroid
    return str(destination_row.get('usage_1', '')), [float(centroid.x), float(centroid.y)]


def _member_timeline_row(
    row,
    home_index: int,
    household: dict,
    member: dict,
    schedule: dict,
    timeline: list[str],
    states: list[str],
    building_lookup: pd.DataFrame,
) -> dict:
    assigned_destination_id = schedule['destination_id']
    assigned_destination_usage, assigned_destination_centroid = _assigned_destination_details(
        assigned_destination_id,
        building_lookup,
    )
    home_centroid = row.geometry.centroid
    return {
        'home_index': home_index,
        'home_building_id': row['building_id'],
        'household_id': household.get('household_id'),
        'member_id': member['member_id'],
        'role': schedule['role'],
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


def _timeline_rows_for_household(
    row,
    home_index: int,
    household: dict,
    config: dict,
    rng: np.random.Generator,
    building_lookup: pd.DataFrame,
    restaurants_by_hour: dict[int, list[str]],
    cultes_ids: list[str],
    scenario_context: dict,
) -> list[dict]:
    schedules = _household_schedules(household, config, rng)
    _apply_household_constraints(
        household,
        schedules,
        config,
        row.geometry.centroid,
        building_lookup,
    )

    rows: list[dict] = []
    for member in household['members']:
        schedule = schedules[member['member_id']]
        timeline, states = _member_timeline(
            schedule,
            rng,
            config,
            restaurants_by_hour,
            cultes_ids,
            scenario_context,
        )
        rows.append(
            _member_timeline_row(
                row,
                home_index,
                household,
                member,
                schedule,
                timeline,
                states,
                building_lookup,
            )
        )
    return rows


def build_member_timelines(df_batiments: gpd.GeoDataFrame, config: dict) -> pd.DataFrame:
    """
    Reconstruit les trajectoires horaires individuelles a partir des foyers.
    """
    df = df_batiments.copy()
    rng = build_rng(config, "temporal")
    cultes_ids = _cult_building_ids(df)
    restaurants_by_hour = _restaurant_destinations_by_hour(df)
    scenario_context = _scenario_modifiers(config)
    building_lookup = _building_lookup(df)

    rows: list[dict] = []
    for idx, row in df.iterrows():
        households = row.get('households', [])
        if not households:
            continue

        for household in households:
            rows.extend(
                _timeline_rows_for_household(
                    row,
                    idx,
                    household,
                    config,
                    rng,
                    building_lookup,
                    restaurants_by_hour,
                    cultes_ids,
                    scenario_context,
                )
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


def _initialize_hourly_population_columns(df: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    for hour in range(24):
        df[f'pop_h{hour}'] = 0
    return df


def _empty_presence_matrix(df: gpd.GeoDataFrame) -> dict[int, np.ndarray]:
    return {idx: np.zeros(24) for idx in df.index}


def _apply_member_timelines_to_presence(
    presence_matrix: dict[int, np.ndarray],
    member_timelines: pd.DataFrame,
    building_index_by_id: dict[str, int],
) -> None:
    for _, member_row in member_timelines.iterrows():
        for hour, destination in enumerate(member_row['timeline_destinations']):
            _assign_presence(
                presence_matrix,
                building_index_by_id,
                int(member_row['home_index']),
                destination,
                hour,
            )


def _write_presence_matrix(df: gpd.GeoDataFrame, presence_matrix: dict[int, np.ndarray]) -> gpd.GeoDataFrame:
    for idx, presence in presence_matrix.items():
        for hour in range(24):
            df.at[idx, f'pop_h{hour}'] = int(presence[hour])
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
    df = _initialize_hourly_population_columns(df)
    presence_matrix = _empty_presence_matrix(df)
    member_timelines = build_member_timelines(df, config)
    _apply_member_timelines_to_presence(presence_matrix, member_timelines, building_index_by_id)
    df = _write_presence_matrix(df, presence_matrix)
    df = _apply_activity_population(df, config)
    df = _apply_beach_population(df, config)

    logger.info("Matrice horaire 24h générée avec succès.")
    return df
