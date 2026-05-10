"""
Validation structurée de la configuration scientifique MOGEC.

Le projet reste sur une validation Python légère, sans dépendance externe de
type JSON Schema ou Pydantic, mais avec des garanties explicites :
- présence des grandes sections attendues ;
- types et bornes des champs sensibles ;
- clés autorisées sur les blocs stables ;
- complétude minimale des blocs `evidence`.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

SUPPORTED_PROXY_METRICS = {
    'member_state_share',
    'member_state_count',
    'role_state_share',
    'role_state_count',
    'role_internal_assigned_state_share',
    'role_internal_assigned_state_count',
    'building_usage_share',
    'building_usage_count',
}
SUPPORTED_PROXY_STATES = {'domicile', 'interne', 'exterieur'}
STATE_BASED_PROXY_METRICS = {
    'member_state_share',
    'member_state_count',
    'role_state_share',
    'role_state_count',
    'role_internal_assigned_state_share',
    'role_internal_assigned_state_count',
}
ROLE_BASED_PROXY_METRICS = {
    'role_state_share',
    'role_state_count',
    'role_internal_assigned_state_share',
    'role_internal_assigned_state_count',
}
BUILDING_USAGE_PROXY_METRICS = {'building_usage_share', 'building_usage_count'}

ALLOWED_TOP_LEVEL_KEYS = {
    'project',
    'study_area',
    'data_paths',
    'external_preparation',
    'visualization',
    'filtering',
    'demographics',
    'destination_model',
    'temporal_model',
    'poi_matching',
    'non_residential_model',
    'infrastructures',
    'scenario',
    'proxy_validation',
}
REQUIRED_TOP_LEVEL_KEYS = ALLOWED_TOP_LEVEL_KEYS
WEEKDAY_NAMES = {'Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche'}
SCENARIO_SEASONS = {'winter', 'spring', 'summer', 'autumn'}


def _ensure_mapping(value, label: str) -> dict:
    if not isinstance(value, Mapping):
        raise ValueError(f"`{label}` doit etre un dictionnaire.")
    return dict(value)


def _ensure_allowed_keys(section: Mapping, label: str, allowed: set[str], required: set[str] | None = None) -> None:
    keys = set(section.keys())
    unknown = sorted(keys - allowed)
    if unknown:
        raise ValueError(f"`{label}` contient des cles non supportees: {unknown}.")
    if required:
        missing = sorted(required - keys)
        if missing:
            raise ValueError(f"`{label}` doit definir les cles requises: {missing}.")


def _ensure_string(value, label: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError(f"`{label}` doit etre une chaine.")
    if not allow_empty and not value.strip():
        raise ValueError(f"`{label}` ne doit pas etre vide.")
    return value


def _ensure_bool(value, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"`{label}` doit etre un booleen.")
    return value


def _ensure_number(value, label: str, *, minimum: float | None = None, maximum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"`{label}` doit etre numerique.")
    number = float(value)
    if minimum is not None and number < minimum:
        raise ValueError(f"`{label}` doit etre >= {minimum}.")
    if maximum is not None and number > maximum:
        raise ValueError(f"`{label}` doit etre <= {maximum}.")
    return number


def _ensure_probability(value, label: str) -> float:
    return _ensure_number(value, label, minimum=0.0, maximum=1.0)


def _ensure_int(value, label: str, *, minimum: int | None = None, maximum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"`{label}` doit etre un entier.")
    if minimum is not None and value < minimum:
        raise ValueError(f"`{label}` doit etre >= {minimum}.")
    if maximum is not None and value > maximum:
        raise ValueError(f"`{label}` doit etre <= {maximum}.")
    return value


def _ensure_list(value, label: str, *, min_length: int = 0) -> list:
    if not isinstance(value, list):
        raise ValueError(f"`{label}` doit etre une liste.")
    if len(value) < min_length:
        raise ValueError(f"`{label}` doit contenir au moins {min_length} element(s).")
    return value


def _ensure_list_of_strings(value, label: str, *, min_length: int = 0) -> list[str]:
    items = _ensure_list(value, label, min_length=min_length)
    normalized: list[str] = []
    for index, item in enumerate(items):
        normalized.append(_ensure_string(item, f"{label}[{index}]"))
    return normalized


def _ensure_probability_distribution(mapping: Mapping, label: str, *, tolerance: float = 0.02) -> None:
    total = 0.0
    for key, value in mapping.items():
        total += _ensure_probability(value, f"{label}.{key}")
    if abs(total - 1.0) > tolerance:
        raise ValueError(f"`{label}` doit sommer a 1.0 +/- {tolerance}. Valeur actuelle: {total:.4f}.")


def _evidence_is_complete(evidence: dict) -> bool:
    required = ['formula', 'source_name', 'extraction_date', 'confidence']
    has_required_fields = all(str(evidence.get(field, '')).strip() for field in required)
    has_traceable_source = any(str(evidence.get(field, '')).strip() for field in ['source_url', 'source_file'])
    return has_required_fields and has_traceable_source


def _validate_project_section(project: dict) -> None:
    _ensure_allowed_keys(project, 'project', {'name', 'crs_epsg', 'random_seed', 'building_id'}, {'name', 'crs_epsg', 'random_seed', 'building_id'})
    _ensure_string(project['name'], 'project.name')
    _ensure_int(project['crs_epsg'], 'project.crs_epsg', minimum=1)
    _ensure_int(project['random_seed'], 'project.random_seed', minimum=0)
    building_id = _ensure_mapping(project['building_id'], 'project.building_id')
    _ensure_allowed_keys(building_id, 'project.building_id', {'prefix', 'source_priority'}, {'prefix', 'source_priority'})
    _ensure_string(building_id['prefix'], 'project.building_id.prefix')
    _ensure_list_of_strings(building_id['source_priority'], 'project.building_id.source_priority', min_length=1)


def _validate_study_area_section(study_area: dict) -> None:
    allowed = {
        'commune_name',
        'commune_insee',
        'boundary_path',
        'boundary_layer',
        'boundary_name_field',
        'boundary_name_value',
        'department_code',
        'buffer_m',
        'allow_network_fallback',
    }
    required = allowed - {'allow_network_fallback'}
    _ensure_allowed_keys(study_area, 'study_area', allowed, required)
    for key in required - {'buffer_m'}:
        _ensure_string(study_area[key], f'study_area.{key}')
    _ensure_number(study_area['buffer_m'], 'study_area.buffer_m', minimum=0.0)
    if 'allow_network_fallback' in study_area:
        _ensure_bool(study_area['allow_network_fallback'], 'study_area.allow_network_fallback')


def _validate_data_paths_section(data_paths: dict) -> None:
    _ensure_allowed_keys(data_paths, 'data_paths', {'input', 'output'}, {'input', 'output'})
    input_cfg = _ensure_mapping(data_paths['input'], 'data_paths.input')
    output_cfg = _ensure_mapping(data_paths['output'], 'data_paths.output')
    required_input = {
        'bd_topo',
        'bd_topo_layer',
        'bdnb',
        'filosofi',
        'schools_csv',
        'tourism_restaurants',
        'tourism_hotels',
        'tourism_campings',
        'tourism_residences',
        'tourism_collective',
        'tourism_locative',
        'beaches_raw',
        'tourism_capacity_insee',
        'audit_restaurants',
    }
    _ensure_allowed_keys(input_cfg, 'data_paths.input', required_input, required_input)
    for key in required_input:
        _ensure_string(input_cfg[key], f'data_paths.input.{key}')
    _ensure_allowed_keys(output_cfg, 'data_paths.output', {'interim_dir', 'final_export'}, {'interim_dir', 'final_export'})
    _ensure_string(output_cfg['interim_dir'], 'data_paths.output.interim_dir')
    _ensure_string(output_cfg['final_export'], 'data_paths.output.final_export')


def _validate_filtering_section(filtering: dict) -> None:
    _ensure_allowed_keys(filtering, 'filtering', {'min_building_area_m2', 'fallback_sqm_per_dwelling'}, {'min_building_area_m2', 'fallback_sqm_per_dwelling'})
    _ensure_number(filtering['min_building_area_m2'], 'filtering.min_building_area_m2', minimum=0.0)
    _ensure_number(filtering['fallback_sqm_per_dwelling'], 'filtering.fallback_sqm_per_dwelling', minimum=1.0)


def _validate_demographics_section(demographics: dict) -> None:
    _ensure_allowed_keys(demographics, 'demographics', {'age_pyramid', 'employment', 'households'}, {'age_pyramid', 'employment', 'households'})
    age_pyramid = _ensure_mapping(demographics['age_pyramid'], 'demographics.age_pyramid')
    _ensure_allowed_keys(age_pyramid, 'demographics.age_pyramid', {'under_15', 'from_15_to_64', 'over_65'}, {'under_15', 'from_15_to_64', 'over_65'})
    _ensure_probability_distribution(age_pyramid, 'demographics.age_pyramid')

    employment = _ensure_mapping(demographics['employment'], 'demographics.employment')
    _ensure_allowed_keys(employment, 'demographics.employment', {'total_emplois_lieu_travail', 'travail_local_pct', 'navetteurs_ext_pct'}, {'total_emplois_lieu_travail', 'travail_local_pct', 'navetteurs_ext_pct'})
    _ensure_int(employment['total_emplois_lieu_travail'], 'demographics.employment.total_emplois_lieu_travail', minimum=0)
    _ensure_probability(employment['travail_local_pct'], 'demographics.employment.travail_local_pct')
    _ensure_probability(employment['navetteurs_ext_pct'], 'demographics.employment.navetteurs_ext_pct')
    if abs(float(employment['travail_local_pct']) + float(employment['navetteurs_ext_pct']) - 1.0) > 0.02:
        raise ValueError("`demographics.employment.travail_local_pct + navetteurs_ext_pct` doit etre proche de 1.0.")

    households = _ensure_mapping(demographics['households'], 'demographics.households')
    _ensure_allowed_keys(
        households,
        'demographics.households',
        {
            'enforce_exact_role_targets',
            'size_distribution',
            'family_household_pct',
            'child_household_adult_min',
            'two_adults_if_children_pct',
            'single_senior_pct',
            'family_guardian',
        },
        {
            'enforce_exact_role_targets',
            'size_distribution',
            'family_household_pct',
            'child_household_adult_min',
            'two_adults_if_children_pct',
            'single_senior_pct',
            'family_guardian',
        },
    )
    _ensure_bool(households['enforce_exact_role_targets'], 'demographics.households.enforce_exact_role_targets')
    size_distribution = _ensure_mapping(households['size_distribution'], 'demographics.households.size_distribution')
    _ensure_probability_distribution(size_distribution, 'demographics.households.size_distribution', tolerance=0.05)
    _ensure_probability(households['family_household_pct'], 'demographics.households.family_household_pct')
    _ensure_int(households['child_household_adult_min'], 'demographics.households.child_household_adult_min', minimum=1)
    _ensure_probability(households['two_adults_if_children_pct'], 'demographics.households.two_adults_if_children_pct')
    _ensure_probability(households['single_senior_pct'], 'demographics.households.single_senior_pct')
    family_guardian = _ensure_mapping(households['family_guardian'], 'demographics.households.family_guardian')
    _ensure_allowed_keys(family_guardian, 'demographics.households.family_guardian', {'actif_local_pct', 'actif_navetteur_pct', 'senior_pct'}, {'actif_local_pct', 'actif_navetteur_pct', 'senior_pct'})
    _ensure_probability_distribution(family_guardian, 'demographics.households.family_guardian', tolerance=0.05)


def _validate_destination_model_section(destination_model: dict) -> None:
    _ensure_allowed_keys(destination_model, 'destination_model', {'fallback_destination', 'default_max_distance_m', 'min_distance_m', 'distance_decay', 'role_pools'}, {'fallback_destination', 'default_max_distance_m', 'min_distance_m', 'distance_decay', 'role_pools'})
    _ensure_string(destination_model['fallback_destination'], 'destination_model.fallback_destination')
    _ensure_number(destination_model['default_max_distance_m'], 'destination_model.default_max_distance_m', minimum=0.0)
    _ensure_number(destination_model['min_distance_m'], 'destination_model.min_distance_m', minimum=0.0)
    _ensure_number(destination_model['distance_decay'], 'destination_model.distance_decay', minimum=0.0)
    role_pools = _ensure_mapping(destination_model['role_pools'], 'destination_model.role_pools')
    for role in ['scolaire', 'actif_local']:
        pool = _ensure_mapping(role_pools.get(role), f'destination_model.role_pools.{role}')
        _ensure_list_of_strings(pool.get('usage_any_of'), f'destination_model.role_pools.{role}.usage_any_of', min_length=1)
        _ensure_number(pool.get('max_distance_m'), f'destination_model.role_pools.{role}.max_distance_m', minimum=0.0)
        _ensure_number(pool.get('distance_decay'), f'destination_model.role_pools.{role}.distance_decay', minimum=0.0)


def _validate_hour_probability_mapping(mapping: dict, label: str) -> None:
    if not isinstance(mapping, dict):
        raise ValueError(f"`{label}` doit etre un dictionnaire heure -> probabilite.")
    for raw_hour, raw_probability in mapping.items():
        hour = int(raw_hour)
        probability = float(raw_probability)
        if hour < 0 or hour > 23:
            raise ValueError(f"`{label}` contient une heure invalide: {hour}.")
        if probability < 0.0 or probability > 1.0:
            raise ValueError(f"`{label}` contient une probabilite hors [0,1]: {probability}.")


def _validate_temporal_model_section(temporal_model: dict) -> None:
    _ensure_allowed_keys(
        temporal_model,
        'temporal_model',
        {'calendars', 'scenario_context', 'modifiers', 'household_dynamics', 'role_profiles'},
        {'calendars', 'scenario_context', 'modifiers', 'household_dynamics', 'role_profiles'},
    )
    calendars = _ensure_mapping(temporal_model['calendars'], 'temporal_model.calendars')
    _ensure_allowed_keys(calendars, 'temporal_model.calendars', {'weekend_days'}, {'weekend_days'})
    weekend_days = set(_ensure_list_of_strings(calendars['weekend_days'], 'temporal_model.calendars.weekend_days', min_length=1))
    if not weekend_days.issubset(WEEKDAY_NAMES):
        raise ValueError("`temporal_model.calendars.weekend_days` contient un jour inconnu.")

    scenario_context = _ensure_mapping(temporal_model['scenario_context'], 'temporal_model.scenario_context')
    _ensure_allowed_keys(scenario_context, 'temporal_model.scenario_context', {'season', 'weather_index', 'alert_level', 'religious_day'}, {'season', 'weather_index', 'alert_level', 'religious_day'})
    if scenario_context['season'] not in SCENARIO_SEASONS:
        raise ValueError(f"`temporal_model.scenario_context.season` doit etre dans {sorted(SCENARIO_SEASONS)}.")
    _ensure_probability(scenario_context['weather_index'], 'temporal_model.scenario_context.weather_index')
    _ensure_probability(scenario_context['alert_level'], 'temporal_model.scenario_context.alert_level')
    _ensure_bool(scenario_context['religious_day'], 'temporal_model.scenario_context.religious_day')

    modifiers = _ensure_mapping(temporal_model['modifiers'], 'temporal_model.modifiers')
    _ensure_allowed_keys(
        modifiers,
        'temporal_model.modifiers',
        {
            'leisure_weather_sensitivity',
            'leisure_alert_sensitivity',
            'restaurant_weather_sensitivity',
            'restaurant_alert_sensitivity',
            'activity_weather_sensitivity',
            'activity_alert_sensitivity',
        },
        {
            'leisure_weather_sensitivity',
            'leisure_alert_sensitivity',
            'restaurant_weather_sensitivity',
            'restaurant_alert_sensitivity',
            'activity_weather_sensitivity',
            'activity_alert_sensitivity',
        },
    )
    for key, value in modifiers.items():
        _ensure_probability(value, f'temporal_model.modifiers.{key}')

    household_dynamics = _ensure_mapping(temporal_model['household_dynamics'], 'temporal_model.household_dynamics')
    _ensure_allowed_keys(
        household_dynamics,
        'temporal_model.household_dynamics',
        {'enable_school_escort', 'school_walk_max_distance_m', 'school_pickup_overlap_hours', 'escort_scoring'},
        {'enable_school_escort', 'school_walk_max_distance_m', 'school_pickup_overlap_hours'},
    )
    _ensure_bool(household_dynamics['enable_school_escort'], 'temporal_model.household_dynamics.enable_school_escort')
    _ensure_number(household_dynamics['school_walk_max_distance_m'], 'temporal_model.household_dynamics.school_walk_max_distance_m', minimum=0.0)
    _ensure_int(household_dynamics['school_pickup_overlap_hours'], 'temporal_model.household_dynamics.school_pickup_overlap_hours', minimum=0)
    if 'escort_scoring' in household_dynamics:
        escort_scoring = _ensure_mapping(household_dynamics['escort_scoring'], 'temporal_model.household_dynamics.escort_scoring')
        _ensure_allowed_keys(
            escort_scoring,
            'temporal_model.household_dynamics.escort_scoring',
            {'role_weights', 'proximity', 'pickup', 'departure_alignment'},
            {'role_weights', 'proximity', 'pickup', 'departure_alignment'},
        )

        role_weights = _ensure_mapping(
            escort_scoring['role_weights'],
            'temporal_model.household_dynamics.escort_scoring.role_weights',
        )
        _ensure_allowed_keys(
            role_weights,
            'temporal_model.household_dynamics.escort_scoring.role_weights',
            {'senior', 'inactif', 'actif_local', 'actif_navetteur'},
            {'senior', 'inactif', 'actif_local', 'actif_navetteur'},
        )
        for key, value in role_weights.items():
            _ensure_number(
                value,
                f'temporal_model.household_dynamics.escort_scoring.role_weights.{key}',
                minimum=0.0,
            )

        proximity = _ensure_mapping(
            escort_scoring['proximity'],
            'temporal_model.household_dynamics.escort_scoring.proximity',
        )
        _ensure_allowed_keys(
            proximity,
            'temporal_model.household_dynamics.escort_scoring.proximity',
            {'max_score', 'distance_scale_m'},
            {'max_score', 'distance_scale_m'},
        )
        _ensure_number(
            proximity['max_score'],
            'temporal_model.household_dynamics.escort_scoring.proximity.max_score',
            minimum=0.0,
        )
        _ensure_number(
            proximity['distance_scale_m'],
            'temporal_model.household_dynamics.escort_scoring.proximity.distance_scale_m',
            minimum=1e-6,
        )

        pickup = _ensure_mapping(
            escort_scoring['pickup'],
            'temporal_model.household_dynamics.escort_scoring.pickup',
        )
        _ensure_allowed_keys(
            pickup,
            'temporal_model.household_dynamics.escort_scoring.pickup',
            {'bonus_if_possible', 'bonus_if_not_possible'},
            {'bonus_if_possible', 'bonus_if_not_possible'},
        )
        _ensure_number(
            pickup['bonus_if_possible'],
            'temporal_model.household_dynamics.escort_scoring.pickup.bonus_if_possible',
            minimum=0.0,
        )
        _ensure_number(
            pickup['bonus_if_not_possible'],
            'temporal_model.household_dynamics.escort_scoring.pickup.bonus_if_not_possible',
            minimum=0.0,
        )

        departure_alignment = _ensure_mapping(
            escort_scoring['departure_alignment'],
            'temporal_model.household_dynamics.escort_scoring.departure_alignment',
        )
        _ensure_allowed_keys(
            departure_alignment,
            'temporal_model.household_dynamics.escort_scoring.departure_alignment',
            {'bonus_if_no_departure', 'max_bonus_if_departure_after_child'},
            {'bonus_if_no_departure', 'max_bonus_if_departure_after_child'},
        )
        _ensure_number(
            departure_alignment['bonus_if_no_departure'],
            'temporal_model.household_dynamics.escort_scoring.departure_alignment.bonus_if_no_departure',
            minimum=0.0,
        )
        _ensure_number(
            departure_alignment['max_bonus_if_departure_after_child'],
            'temporal_model.household_dynamics.escort_scoring.departure_alignment.max_bonus_if_departure_after_child',
            minimum=0.0,
        )

    role_profiles = _ensure_mapping(temporal_model['role_profiles'], 'temporal_model.role_profiles')
    for role in ['scolaire', 'actif_local', 'actif_navetteur', 'senior']:
        if role not in role_profiles:
            raise ValueError(f"`temporal_model.role_profiles` doit definir `{role}`.")


def _validate_poi_matching_section(poi_matching: dict) -> None:
    restaurants = _ensure_mapping(poi_matching.get('restaurants'), 'poi_matching.restaurants')
    _ensure_allowed_keys(
        restaurants,
        'poi_matching.restaurants',
        {'max_distance_m', 'preferred_usage_any_of', 'allow_fallback_any_usage', 'concat_multiple_names', 'evidence'},
        {'max_distance_m', 'preferred_usage_any_of', 'allow_fallback_any_usage', 'concat_multiple_names', 'evidence'},
    )
    _ensure_number(restaurants['max_distance_m'], 'poi_matching.restaurants.max_distance_m', minimum=0.0)
    _ensure_list_of_strings(restaurants['preferred_usage_any_of'], 'poi_matching.restaurants.preferred_usage_any_of', min_length=1)
    _ensure_bool(restaurants['allow_fallback_any_usage'], 'poi_matching.restaurants.allow_fallback_any_usage')
    _ensure_bool(restaurants['concat_multiple_names'], 'poi_matching.restaurants.concat_multiple_names')


def _validate_non_residential_section(non_residential_model: dict) -> None:
    _ensure_allowed_keys(non_residential_model, 'non_residential_model', {'accommodation', 'activities', 'beaches'}, {'accommodation', 'activities', 'beaches'})
    for section_name in ['accommodation', 'activities', 'beaches']:
        section = _ensure_mapping(non_residential_model[section_name], f'non_residential_model.{section_name}')
        if 'enabled' in section:
            _ensure_bool(section['enabled'], f'non_residential_model.{section_name}.enabled')


def _validate_infrastructures_section(infrastructures: dict) -> None:
    _ensure_allowed_keys(infrastructures, 'infrastructures', {'schools', 'school_matching', 'schedules'}, {'schools', 'school_matching', 'schedules'})
    schools = _ensure_mapping(infrastructures['schools'], 'infrastructures.schools')
    if not schools:
        raise ValueError("`infrastructures.schools` ne doit pas etre vide.")
    for school_key, school_cfg in schools.items():
        school = _ensure_mapping(school_cfg, f'infrastructures.schools.{school_key}')
        _ensure_allowed_keys(school, f'infrastructures.schools.{school_key}', {'capacity', 'name', 'latitude', 'longitude'}, {'capacity', 'name', 'latitude', 'longitude'})
        _ensure_number(school['capacity'], f'infrastructures.schools.{school_key}.capacity', minimum=0.0)
        _ensure_string(school['name'], f'infrastructures.schools.{school_key}.name')
        _ensure_number(school['latitude'], f'infrastructures.schools.{school_key}.latitude', minimum=-90.0, maximum=90.0)
        _ensure_number(school['longitude'], f'infrastructures.schools.{school_key}.longitude', minimum=-180.0, maximum=180.0)


def _validate_scenario_section(scenario: dict) -> None:
    _ensure_allowed_keys(
        scenario,
        'scenario',
        {'name', 'day_of_week', 'is_school_holiday', 'reference_hour', 'residences', 'commerce', 'tourisme', 'temporal_context'},
        {'name', 'day_of_week', 'is_school_holiday', 'reference_hour', 'residences', 'commerce', 'tourisme', 'temporal_context'},
    )
    _ensure_string(scenario['name'], 'scenario.name')
    if _ensure_string(scenario['day_of_week'], 'scenario.day_of_week') not in WEEKDAY_NAMES:
        raise ValueError("`scenario.day_of_week` doit correspondre a un jour francais valide.")
    _ensure_bool(scenario['is_school_holiday'], 'scenario.is_school_holiday')
    _ensure_int(scenario['reference_hour'], 'scenario.reference_hour', minimum=0, maximum=23)

    residences = _ensure_mapping(scenario['residences'], 'scenario.residences')
    _ensure_allowed_keys(residences, 'scenario.residences', {'r_rp', 'r_rs', 'tau_saison', 'alpha_domicile'}, {'r_rp', 'r_rs', 'tau_saison', 'alpha_domicile'})
    for key in residences:
        _ensure_probability(residences[key], f'scenario.residences.{key}')

    commerce = _ensure_mapping(scenario['commerce'], 'scenario.commerce')
    _ensure_allowed_keys(commerce, 'scenario.commerce', {'sqm_per_employee', 'client_employee_ratio', 'alpha_commerce'}, {'sqm_per_employee', 'client_employee_ratio', 'alpha_commerce'})
    _ensure_number(commerce['sqm_per_employee'], 'scenario.commerce.sqm_per_employee', minimum=1.0)
    _ensure_number(commerce['client_employee_ratio'], 'scenario.commerce.client_employee_ratio', minimum=0.0)
    _ensure_probability(commerce['alpha_commerce'], 'scenario.commerce.alpha_commerce')

    tourisme = _ensure_mapping(scenario['tourisme'], 'scenario.tourisme')
    _ensure_allowed_keys(tourisme, 'scenario.tourisme', {'tau_meteo', 'alpha_plage', 'tau_occupation_lits'}, {'tau_meteo', 'alpha_plage', 'tau_occupation_lits'})
    for key in tourisme:
        _ensure_probability(tourisme[key], f'scenario.tourisme.{key}')

    temporal_context = _ensure_mapping(scenario['temporal_context'], 'scenario.temporal_context')
    _ensure_allowed_keys(temporal_context, 'scenario.temporal_context', {'season', 'weather_index', 'alert_level', 'religious_day'}, {'season', 'weather_index', 'alert_level', 'religious_day'})
    if temporal_context['season'] not in SCENARIO_SEASONS:
        raise ValueError(f"`scenario.temporal_context.season` doit etre dans {sorted(SCENARIO_SEASONS)}.")
    _ensure_probability(temporal_context['weather_index'], 'scenario.temporal_context.weather_index')
    _ensure_probability(temporal_context['alert_level'], 'scenario.temporal_context.alert_level')
    _ensure_bool(temporal_context['religious_day'], 'scenario.temporal_context.religious_day')


def _validate_reference_curve(reference_curve, proxy_id: str) -> None:
    if isinstance(reference_curve, (list, tuple)):
        if len(reference_curve) != 24:
            raise ValueError(
                f"Le proxy temporel '{proxy_id}' doit fournir `reference_curve` avec 24 valeurs."
            )
        for index, value in enumerate(reference_curve):
            float(value)
            if float(value) < 0.0:
                raise ValueError(f"Le proxy temporel '{proxy_id}' contient une valeur negative a l'heure {index}.")
        return

    if not isinstance(reference_curve, dict):
        raise ValueError(
            f"Le proxy temporel '{proxy_id}' doit fournir `reference_curve` comme liste de 24 valeurs ou dictionnaire heure -> valeur."
        )

    normalized_hours = set()
    for raw_hour, raw_value in reference_curve.items():
        hour = int(raw_hour)
        if hour < 0 or hour > 23:
            raise ValueError(
                f"Le proxy temporel '{proxy_id}' contient une heure invalide dans `reference_curve`: {hour}."
            )
        if float(raw_value) < 0.0:
            raise ValueError(f"Le proxy temporel '{proxy_id}' contient une valeur negative dans `reference_curve` a l'heure {hour}.")
        normalized_hours.add(hour)

    if normalized_hours != set(range(24)):
        raise ValueError(
            f"Le proxy temporel '{proxy_id}' doit couvrir exactement les heures 0 a 23 dans `reference_curve`."
        )


def _validate_temporal_proxy_definition(proxy_cfg: dict) -> None:
    proxy_id = str(proxy_cfg.get('proxy_id', '')).strip()
    if not proxy_id:
        raise ValueError("Chaque proxy temporel actif doit definir `proxy_id`.")

    _ensure_allowed_keys(
        proxy_cfg,
        f'proxy_validation.temporal_proxies[{proxy_id}]',
        {
            'proxy_id',
            'label',
            'metric',
            'role',
            'state',
            'usage_any_of',
            'comparison_normalization',
            'reference_curve',
            'applicability',
            'thresholds',
            'evidence',
            'enabled',
        },
        {'proxy_id', 'metric', 'comparison_normalization', 'reference_curve', 'thresholds', 'evidence'},
    )

    metric = str(proxy_cfg.get('metric', '')).strip()
    if metric not in SUPPORTED_PROXY_METRICS:
        raise ValueError(
            f"Le proxy temporel '{proxy_id}' utilise un type non supporte: {metric}."
        )

    _validate_reference_curve(proxy_cfg.get('reference_curve'), proxy_id)

    comparison_normalization = str(proxy_cfg.get('comparison_normalization', 'max'))
    if comparison_normalization not in {'none', 'max', 'sum'}:
        raise ValueError(
            f"Le proxy temporel '{proxy_id}' utilise une normalisation inconnue: {comparison_normalization}."
        )

    if metric in STATE_BASED_PROXY_METRICS:
        state = str(proxy_cfg.get('state', '')).strip()
        if state not in SUPPORTED_PROXY_STATES:
            raise ValueError(
                f"Le proxy temporel '{proxy_id}' doit definir `state` parmi {sorted(SUPPORTED_PROXY_STATES)}."
            )

    if metric in ROLE_BASED_PROXY_METRICS and not str(proxy_cfg.get('role', '')).strip():
        raise ValueError(f"Le proxy temporel '{proxy_id}' doit definir `role`.")

    if metric in BUILDING_USAGE_PROXY_METRICS:
        usage_any_of = proxy_cfg.get('usage_any_of', [])
        if not isinstance(usage_any_of, list) or not usage_any_of:
            raise ValueError(
                f"Le proxy temporel '{proxy_id}' doit definir `usage_any_of` comme liste non vide."
            )

    thresholds = _ensure_mapping(proxy_cfg.get('thresholds'), f'proxy_validation.temporal_proxies[{proxy_id}].thresholds')
    _ensure_allowed_keys(
        thresholds,
        f'proxy_validation.temporal_proxies[{proxy_id}].thresholds',
        {
            'correlation_pass_min',
            'correlation_warn_min',
            'rmse_pass_max',
            'rmse_warn_max',
            'peak_gap_pass_max_hours',
            'peak_gap_warn_max_hours',
        },
        {
            'correlation_pass_min',
            'correlation_warn_min',
            'rmse_pass_max',
            'rmse_warn_max',
            'peak_gap_pass_max_hours',
            'peak_gap_warn_max_hours',
        },
    )
    _ensure_probability(thresholds['correlation_pass_min'], f'proxy_validation.temporal_proxies[{proxy_id}].thresholds.correlation_pass_min')
    _ensure_probability(thresholds['correlation_warn_min'], f'proxy_validation.temporal_proxies[{proxy_id}].thresholds.correlation_warn_min')
    if float(thresholds['correlation_warn_min']) > float(thresholds['correlation_pass_min']):
        raise ValueError(f"Le proxy temporel '{proxy_id}' doit avoir `correlation_warn_min <= correlation_pass_min`.")
    _ensure_number(thresholds['rmse_pass_max'], f'proxy_validation.temporal_proxies[{proxy_id}].thresholds.rmse_pass_max', minimum=0.0)
    _ensure_number(thresholds['rmse_warn_max'], f'proxy_validation.temporal_proxies[{proxy_id}].thresholds.rmse_warn_max', minimum=0.0)
    if float(thresholds['rmse_warn_max']) < float(thresholds['rmse_pass_max']):
        raise ValueError(f"Le proxy temporel '{proxy_id}' doit avoir `rmse_warn_max >= rmse_pass_max`.")
    _ensure_int(thresholds['peak_gap_pass_max_hours'], f'proxy_validation.temporal_proxies[{proxy_id}].thresholds.peak_gap_pass_max_hours', minimum=0)
    _ensure_int(thresholds['peak_gap_warn_max_hours'], f'proxy_validation.temporal_proxies[{proxy_id}].thresholds.peak_gap_warn_max_hours', minimum=0)
    if int(thresholds['peak_gap_warn_max_hours']) < int(thresholds['peak_gap_pass_max_hours']):
        raise ValueError(f"Le proxy temporel '{proxy_id}' doit avoir `peak_gap_warn_max_hours >= peak_gap_pass_max_hours`.")

    evidence = proxy_cfg.get('evidence', {})
    if not _evidence_is_complete(evidence):
        raise ValueError(
            f"Le proxy temporel '{proxy_id}' est active sans bloc `evidence` complet."
        )


def _validate_proxy_validation_section(proxy_validation: dict, require_complete: bool) -> None:
    _ensure_allowed_keys(proxy_validation, 'proxy_validation', {'scenario_sets', 'temporal_proxies'})

    if require_complete and 'scenario_sets' not in proxy_validation:
        raise ValueError("`proxy_validation` doit definir `scenario_sets` dans une configuration complete.")
    if require_complete and 'temporal_proxies' not in proxy_validation:
        raise ValueError("`proxy_validation` doit definir `temporal_proxies` dans une configuration complete.")

    if 'scenario_sets' in proxy_validation:
        scenario_sets = _ensure_mapping(proxy_validation['scenario_sets'], 'proxy_validation.scenario_sets')
        if require_complete and not scenario_sets:
            raise ValueError("`proxy_validation.scenario_sets` ne doit pas etre vide.")
        for set_name, entries in scenario_sets.items():
            specs = _ensure_list(entries, f'proxy_validation.scenario_sets.{set_name}', min_length=1)
            for index, spec in enumerate(specs):
                if isinstance(spec, str):
                    _ensure_string(spec, f'proxy_validation.scenario_sets.{set_name}[{index}]')
                    continue
                spec_mapping = _ensure_mapping(spec, f'proxy_validation.scenario_sets.{set_name}[{index}]')
                _ensure_allowed_keys(spec_mapping, f'proxy_validation.scenario_sets.{set_name}[{index}]', {'config_path', 'label'}, {'config_path'})
                _ensure_string(spec_mapping['config_path'], f'proxy_validation.scenario_sets.{set_name}[{index}].config_path')
                if 'label' in spec_mapping:
                    _ensure_string(spec_mapping['label'], f'proxy_validation.scenario_sets.{set_name}[{index}].label')

    if 'temporal_proxies' in proxy_validation:
        temporal_proxies = _ensure_list(proxy_validation['temporal_proxies'], 'proxy_validation.temporal_proxies', min_length=1)
        for proxy_cfg in temporal_proxies:
            if not isinstance(proxy_cfg, Mapping):
                raise ValueError("Chaque entree de `proxy_validation.temporal_proxies` doit etre un dictionnaire.")
            if not proxy_cfg.get('enabled', True):
                continue
            _validate_temporal_proxy_definition(dict(proxy_cfg))


def _validate_school_temporal_profiles(config: dict) -> None:
    role_profiles = config.get('temporal_model', {}).get('role_profiles', {})
    school_profiles = role_profiles.get('scolaire', {})

    for context_name, profile in school_profiles.items():
        if not isinstance(profile, dict):
            continue
        attendance_mapping = profile.get('attendance_probability_by_hour')
        if attendance_mapping is not None:
            _validate_hour_probability_mapping(
                attendance_mapping,
                f"temporal_model.role_profiles.scolaire.{context_name}.attendance_probability_by_hour",
            )

        lunch_cfg = profile.get('lunch')
        if isinstance(lunch_cfg, dict) and 'at_home_probability_by_hour' in lunch_cfg:
            _validate_hour_probability_mapping(
                lunch_cfg['at_home_probability_by_hour'],
                f"temporal_model.role_profiles.scolaire.{context_name}.lunch.at_home_probability_by_hour",
            )


def _validate_config_schema(config: dict, require_complete: bool) -> None:
    if not isinstance(config, Mapping):
        raise ValueError("La configuration chargee doit etre un dictionnaire YAML.")

    keys = set(config.keys())
    unknown = sorted(keys - ALLOWED_TOP_LEVEL_KEYS)
    if unknown:
        raise ValueError(f"La configuration contient des sections top-level non supportees: {unknown}.")

    if require_complete:
        missing = sorted(REQUIRED_TOP_LEVEL_KEYS - keys)
        if missing:
            raise ValueError(f"La configuration complete doit definir les sections top-level: {missing}.")

    if 'project' in config:
        _validate_project_section(_ensure_mapping(config['project'], 'project'))
    if 'study_area' in config:
        _validate_study_area_section(_ensure_mapping(config['study_area'], 'study_area'))
    if 'data_paths' in config:
        _validate_data_paths_section(_ensure_mapping(config['data_paths'], 'data_paths'))
    if 'filtering' in config:
        _validate_filtering_section(_ensure_mapping(config['filtering'], 'filtering'))
    if 'demographics' in config:
        _validate_demographics_section(_ensure_mapping(config['demographics'], 'demographics'))
    if 'destination_model' in config:
        _validate_destination_model_section(_ensure_mapping(config['destination_model'], 'destination_model'))
    if 'temporal_model' in config:
        _validate_temporal_model_section(_ensure_mapping(config['temporal_model'], 'temporal_model'))
    if 'poi_matching' in config:
        _validate_poi_matching_section(_ensure_mapping(config['poi_matching'], 'poi_matching'))
    if 'non_residential_model' in config:
        _validate_non_residential_section(_ensure_mapping(config['non_residential_model'], 'non_residential_model'))
    if 'infrastructures' in config:
        _validate_infrastructures_section(_ensure_mapping(config['infrastructures'], 'infrastructures'))
    if 'scenario' in config:
        _validate_scenario_section(_ensure_mapping(config['scenario'], 'scenario'))
    if 'proxy_validation' in config:
        _validate_proxy_validation_section(_ensure_mapping(config['proxy_validation'], 'proxy_validation'), require_complete=require_complete)


def validate_config_for_evidence(config: dict, require_complete: bool = False) -> None:
    _validate_config_schema(config, require_complete=require_complete)

    non_residential_cfg = config.get('non_residential_model', {})
    for section_name in ['accommodation', 'activities', 'beaches']:
        section = non_residential_cfg.get(section_name, {})
        if not section.get('enabled', False):
            continue
        evidence = section.get('evidence', {})
        if not _evidence_is_complete(evidence):
            raise ValueError(
                f"La section non résidentielle '{section_name}' est activée sans bloc 'evidence' complet dans config.yaml."
            )

    proxy_cfg = config.get('proxy_validation', {})
    for temporal_proxy in proxy_cfg.get('temporal_proxies', []):
        if not temporal_proxy.get('enabled', True):
            continue
        _validate_temporal_proxy_definition(temporal_proxy)

    _validate_school_temporal_profiles(config)


def _is_local_path(value: object) -> bool:
    if not isinstance(value, str):
        return False
    stripped = value.strip()
    if not stripped:
        return False
    return "://" not in stripped


def validate_config_path_existence(config: dict) -> None:
    missing_inputs: list[str] = []
    invalid_outputs: list[str] = []

    study_area = config.get('study_area', {})
    allow_network_fallback = bool(study_area.get('allow_network_fallback', False))
    boundary_path = study_area.get('boundary_path')
    if _is_local_path(boundary_path):
        boundary_candidate = Path(str(boundary_path)).expanduser()
        if not boundary_candidate.exists() and not allow_network_fallback:
            missing_inputs.append(f"study_area.boundary_path -> {boundary_candidate}")

    data_input = config.get('data_paths', {}).get('input', {})
    for key, value in data_input.items():
        if key.endswith('_layer') or not _is_local_path(value):
            continue
        candidate = Path(str(value)).expanduser()
        if not candidate.exists():
            missing_inputs.append(f"data_paths.input.{key} -> {candidate}")

    output_cfg = config.get('data_paths', {}).get('output', {})
    interim_dir = output_cfg.get('interim_dir')
    if _is_local_path(interim_dir):
        interim_candidate = Path(str(interim_dir)).expanduser()
        if interim_candidate.exists() and not interim_candidate.is_dir():
            invalid_outputs.append(f"data_paths.output.interim_dir -> {interim_candidate} (n'est pas un dossier)")
    final_export = output_cfg.get('final_export')
    if _is_local_path(final_export):
        parent = Path(str(final_export)).expanduser().parent
        if not parent.exists():
            invalid_outputs.append(f"data_paths.output.final_export.parent -> {parent} (dossier parent absent)")
        elif not parent.is_dir():
            invalid_outputs.append(f"data_paths.output.final_export.parent -> {parent} (n'est pas un dossier)")

    if missing_inputs:
        raise ValueError(
            "Configuration invalide: chemins d'entree introuvables.\n" + "\n".join(missing_inputs)
        )
    if invalid_outputs:
        raise ValueError(
            "Configuration invalide: chemins de sortie invalides.\n" + "\n".join(invalid_outputs)
        )
