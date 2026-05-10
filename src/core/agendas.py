"""
Génération des foyers, des rôles et des destinations principales.

Le modèle ne tire plus uniquement des rôles bâtiment par bâtiment. Il construit
une structure intermédiaire de foyers afin de produire des compositions
familiales plus plausibles, de garantir qu'un enfant ne vive pas seul et de
préparer des dynamiques intra-foyer pour la matrice horaire.
"""

from collections import Counter
import logging
from operator import itemgetter

import geopandas as gpd
import numpy as np
import pandas as pd

from src.core.destinations import sample_destination_building_id
from src.core.randomness import build_rng

logger = logging.getLogger(__name__)


ROLE_KEYS = ['scolaire', 'senior', 'actif_local', 'actif_navetteur', 'inactif']
ROLE_COUNT_COLUMNS = ['n_scolaire', 'n_senior', 'n_actif_local', 'n_actif_navetteur', 'n_inactif']
SCHOOL_COUNT_COLUMNS = ['n_scolaire_interne', 'n_scolaire_exterieur']
CHILD_ROLE = 'scolaire'
SENIOR_ROLE = 'senior'
LOCAL_WORKER_ROLE = 'actif_local'
COMMUTER_ROLE = 'actif_navetteur'
INACTIVE_ROLE = 'inactif'
ADULT_REFERENCE_ROLES = {LOCAL_WORKER_ROLE, COMMUTER_ROLE, SENIOR_ROLE, INACTIVE_ROLE}
HOME_DESTINATION = "DOMICILE"
OUTSIDE_DESTINATION = "EXTERIEUR"
NON_INTERNAL_DESTINATIONS = {HOME_DESTINATION, OUTSIDE_DESTINATION, 'None', None}


def _households_allowed_for_row(row) -> bool:
    if not bool(row.get('is_culte', False)):
        return True
    return bool(row.get('culte_household_allowed', False))


def _employment_targets_for_adults(adult_pool: int, config: dict) -> dict[str, int]:
    employment_cfg = config['demographics']['employment']
    local_pct = float(employment_cfg.get('travail_local_pct', 0.0))
    local_jobs_value = employment_cfg.get('total_emplois_lieu_travail')
    local_jobs = int(local_jobs_value) if local_jobs_value is not None else None

    employed_residents = adult_pool
    if local_jobs is not None and local_pct > 0.0:
        inferred_employed = int(round(local_jobs / local_pct))
        employed_residents = min(adult_pool, max(inferred_employed, local_jobs))

    if local_jobs is not None:
        n_actif_local = min(employed_residents, local_jobs)
    else:
        n_actif_local = int(round(employed_residents * local_pct))

    n_actif_navetteur = max(0, employed_residents - n_actif_local)
    n_inactif = max(0, adult_pool - employed_residents)

    return {
        'actif_local': int(n_actif_local),
        'actif_navetteur': int(n_actif_navetteur),
        'inactif': int(n_inactif),
    }


def _adult_role_weights(config: dict) -> dict[str, float]:
    age_cfg = config['demographics']['age_pyramid']

    child_share = float(age_cfg['under_15'])
    senior_share = float(age_cfg['over_65'])
    non_child_total = max(1e-9, 1.0 - child_share)
    senior_weight = senior_share / non_child_total
    employment_targets = _employment_targets_for_adults(1000, config)
    local_pct = employment_targets['actif_local'] / 1000.0
    commuter_pct = employment_targets['actif_navetteur'] / 1000.0
    inactive_pct = employment_targets['inactif'] / 1000.0
    total_adult_weight = local_pct + commuter_pct + inactive_pct
    scale = max(0.0, 1.0 - senior_weight) / max(total_adult_weight, 1e-9)

    return {
        'senior': senior_weight,
        'actif_local': local_pct * scale,
        'actif_navetteur': commuter_pct * scale,
        'inactif': inactive_pct * scale,
    }


def _sample_weighted_choice(options: dict[str, float], rng: np.random.Generator) -> str:
    labels = list(options.keys())
    weights = np.array([max(0.0, float(options[label])) for label in labels], dtype=float)
    if float(weights.sum()) == 0.0:
        weights = np.ones(len(labels), dtype=float)
    probabilities = weights / weights.sum()
    return str(rng.choice(labels, p=probabilities))


def _household_size_distribution(config: dict) -> tuple[np.ndarray, np.ndarray]:
    raw_distribution = config['demographics']['households']['size_distribution']
    sizes = np.array(sorted(int(size) for size in raw_distribution.keys()), dtype=int)
    weights = np.array([float(raw_distribution[str(size)]) for size in sizes], dtype=float)
    weights = weights / weights.sum()
    return sizes, weights


def _sample_household_sizes(population: int, dwellings: int, rng: np.random.Generator, config: dict) -> list[int]:
    if population <= 0:
        return []

    sizes, weights = _household_size_distribution(config)
    average_size = float((sizes * weights).sum())
    estimated_households = max(1, int(round(population / max(1.0, average_size))))
    if dwellings > 0:
        estimated_households = min(population, max(1, min(dwellings, estimated_households)))

    sampled_sizes = rng.choice(sizes, size=estimated_households, p=weights).astype(int).tolist()

    while sum(sampled_sizes) < population:
        sampled_sizes.append(int(rng.choice(sizes, p=weights)))

    overflow = sum(sampled_sizes) - population
    if overflow > 0:
        for index in reversed(range(len(sampled_sizes))):
            removable = min(overflow, sampled_sizes[index] - 1)
            sampled_sizes[index] -= removable
            overflow -= removable
            if overflow == 0:
                break

    sampled_sizes = [size for size in sampled_sizes if size > 0]
    return sampled_sizes


def _positive_int(value) -> int:
    if value is None:
        return 0
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return 0
    if np.isnan(numeric_value) or numeric_value <= 0:
        return 0
    return int(numeric_value)


def _sample_adult_role(rng: np.random.Generator, config: dict) -> str:
    return _sample_weighted_choice(_adult_role_weights(config), rng)


def _sample_family_guardian_role(rng: np.random.Generator, config: dict) -> str:
    guardian_cfg = config['demographics']['households'].get('family_guardian', {})
    return _sample_weighted_choice({
        LOCAL_WORKER_ROLE: float(guardian_cfg.get('actif_local_pct', 0.40)),
        COMMUTER_ROLE: float(guardian_cfg.get('actif_navetteur_pct', 0.55)),
        SENIOR_ROLE: float(guardian_cfg.get('senior_pct', 0.05)),
    }, rng)


def _build_household_roles(size: int, rng: np.random.Generator, config: dict) -> list[str]:
    household_cfg = config['demographics']['households']
    family_pct = float(household_cfg['family_household_pct'])
    single_senior_pct = float(household_cfg['single_senior_pct'])
    two_adults_pct = float(household_cfg['two_adults_if_children_pct'])

    if size == 1:
        return [SENIOR_ROLE] if rng.random() < single_senior_pct else [_sample_adult_role(rng, config)]

    is_family = size >= 2 and rng.random() < family_pct
    roles: list[str] = []

    if is_family:
        adults = 2 if size >= 3 and rng.random() < two_adults_pct else 1
        children_capacity = max(1, size - adults)
        if children_capacity == 1:
            children = 1
        else:
            children = min(children_capacity, 2 if rng.random() < 0.60 else 1)

        for _ in range(adults):
            roles.append(_sample_family_guardian_role(rng, config))
        for _ in range(children):
            roles.append(CHILD_ROLE)

        while len(roles) < size:
            roles.append(_sample_adult_role(rng, config))
    else:
        for _ in range(size):
            if rng.random() < float(config['demographics']['age_pyramid']['under_15']):
                roles.append(CHILD_ROLE)
            else:
                roles.append(_sample_adult_role(rng, config))

    if CHILD_ROLE in roles and not any(role in ADULT_REFERENCE_ROLES for role in roles):
        roles[0] = INACTIVE_ROLE

    if size == 1 and roles[0] == CHILD_ROLE:
        roles[0] = INACTIVE_ROLE

    return roles[:size]


def _role_counts(roles: list[str]) -> dict[str, int]:
    counts = Counter(roles)
    return {
        'n_scolaire': counts.get('scolaire', 0),
        'n_senior': counts.get('senior', 0),
        'n_actif_local': counts.get('actif_local', 0),
        'n_actif_navetteur': counts.get('actif_navetteur', 0),
        'n_inactif': counts.get('inactif', 0),
    }


def _target_role_counts(population: int, config: dict) -> dict[str, int]:
    age_cfg = config['demographics']['age_pyramid']

    n_scolaire = int(round(population * float(age_cfg['under_15'])))
    n_senior = int(round(population * float(age_cfg['over_65'])))
    adult_pool = max(0, population - n_scolaire - n_senior)
    employment_targets = _employment_targets_for_adults(adult_pool, config)

    return {
        'scolaire': n_scolaire,
        'senior': n_senior,
        'actif_local': employment_targets['actif_local'],
        'actif_navetteur': employment_targets['actif_navetteur'],
        'inactif': employment_targets['inactif'],
    }


def _current_role_counts(households: list[dict]) -> Counter:
    return Counter(member['role'] for household in households for member in household['members'])


def _can_convert_to_child(household: dict, member_index: int) -> bool:
    other_roles = [member['role'] for idx, member in enumerate(household['members']) if idx != member_index]
    return any(role != CHILD_ROLE for role in other_roles)


def _preferred_replacement_for_senior(current: Counter, targets: dict[str, int]) -> str:
    if current[INACTIVE_ROLE] < targets[INACTIVE_ROLE]:
        return INACTIVE_ROLE
    return COMMUTER_ROLE if current[COMMUTER_ROLE] < targets[COMMUTER_ROLE] else LOCAL_WORKER_ROLE


def _preferred_replacement_for_inactive(current: Counter, targets: dict[str, int]) -> str:
    return COMMUTER_ROLE if current[COMMUTER_ROLE] < targets[COMMUTER_ROLE] else LOCAL_WORKER_ROLE


def _fallback_for_local(current: Counter, targets: dict[str, int]) -> str:
    return INACTIVE_ROLE if current[INACTIVE_ROLE] < targets[INACTIVE_ROLE] else COMMUTER_ROLE


def _fallback_for_commuter(current: Counter, targets: dict[str, int]) -> str:
    return INACTIVE_ROLE if current[INACTIVE_ROLE] < targets[INACTIVE_ROLE] else LOCAL_WORKER_ROLE


def _rebalance_counts_to_targets(
    current: Counter,
    targets: dict[str, int],
    convert_one,
    child_predicate,
    retry_child_without_predicate: bool = False,
) -> None:
    while current[CHILD_ROLE] < targets[CHILD_ROLE]:
        converted = convert_one([SENIOR_ROLE, LOCAL_WORKER_ROLE, COMMUTER_ROLE, INACTIVE_ROLE], CHILD_ROLE, child_predicate)
        if not converted and retry_child_without_predicate:
            converted = convert_one([SENIOR_ROLE, LOCAL_WORKER_ROLE, COMMUTER_ROLE, INACTIVE_ROLE], CHILD_ROLE)
        if not converted:
            break

    while current[CHILD_ROLE] > targets[CHILD_ROLE]:
        fallback_role = INACTIVE_ROLE if targets.get(INACTIVE_ROLE, 0) > current.get(INACTIVE_ROLE, 0) else LOCAL_WORKER_ROLE
        if not convert_one([CHILD_ROLE], fallback_role):
            break

    while current[SENIOR_ROLE] < targets[SENIOR_ROLE]:
        if not convert_one([LOCAL_WORKER_ROLE, COMMUTER_ROLE, INACTIVE_ROLE], SENIOR_ROLE):
            break

    while current[SENIOR_ROLE] > targets[SENIOR_ROLE]:
        if not convert_one([SENIOR_ROLE], _preferred_replacement_for_senior(current, targets)):
            break

    while current[INACTIVE_ROLE] < targets[INACTIVE_ROLE]:
        if not convert_one([COMMUTER_ROLE, LOCAL_WORKER_ROLE], INACTIVE_ROLE):
            break

    while current[INACTIVE_ROLE] > targets[INACTIVE_ROLE]:
        if not convert_one([INACTIVE_ROLE], _preferred_replacement_for_inactive(current, targets)):
            break

    while current[LOCAL_WORKER_ROLE] < targets[LOCAL_WORKER_ROLE]:
        if not convert_one([COMMUTER_ROLE, INACTIVE_ROLE], LOCAL_WORKER_ROLE):
            break

    while current[LOCAL_WORKER_ROLE] > targets[LOCAL_WORKER_ROLE]:
        if not convert_one([LOCAL_WORKER_ROLE], _fallback_for_local(current, targets)):
            break

    while current[COMMUTER_ROLE] < targets[COMMUTER_ROLE]:
        if not convert_one([INACTIVE_ROLE, LOCAL_WORKER_ROLE], COMMUTER_ROLE):
            break

    while current[COMMUTER_ROLE] > targets[COMMUTER_ROLE]:
        if not convert_one([COMMUTER_ROLE], _fallback_for_commuter(current, targets)):
            break


def _rebalance_role_counts(households: list[dict], population: int, config: dict) -> list[dict]:
    targets = _target_role_counts(population, config)
    current = _current_role_counts(households)

    def convert_one(from_roles: list[str], to_role: str, predicate=None) -> bool:
        for household in households:
            for member_index, member in enumerate(household['members']):
                if member['role'] not in from_roles:
                    continue
                if predicate is not None and not predicate(household, member_index):
                    continue
                current[member['role']] -= 1
                member['role'] = to_role
                current[to_role] += 1
                return True
        return False

    _rebalance_counts_to_targets(current, targets, convert_one, _can_convert_to_child)

    return households


def _household_member_references(df: gpd.GeoDataFrame) -> list[tuple[int, int, int]]:
    references: list[tuple[int, int, int]] = []
    for row_index, households in df['households'].items():
        for household_index, household in enumerate(households):
            for member_index, _ in enumerate(household['members']):
                references.append((row_index, household_index, member_index))
    return references


def _member_for_reference(df: gpd.GeoDataFrame, reference: tuple[int, int, int]) -> dict:
    row_index, household_index, member_index = reference
    return df.at[row_index, 'households'][household_index]['members'][member_index]


def _household_for_reference(df: gpd.GeoDataFrame, reference: tuple[int, int, int]) -> dict:
    row_index, household_index, _ = reference
    return df.at[row_index, 'households'][household_index]


def _current_global_role_counts(df: gpd.GeoDataFrame, references: list[tuple[int, int, int]]) -> Counter:
    return Counter(_member_for_reference(df, reference)['role'] for reference in references)


def _build_global_role_converter(
    df: gpd.GeoDataFrame,
    references: list[tuple[int, int, int]],
    current: Counter,
):
    def convert_one(from_roles: list[str], to_role: str, predicate=None) -> bool:
        for reference in references:
            household = _household_for_reference(df, reference)
            member = _member_for_reference(df, reference)
            if member['role'] not in from_roles:
                continue
            member_index = reference[2]
            if predicate is not None and not predicate(household, member_index):
                continue
            current[member['role']] -= 1
            member['role'] = to_role
            current[to_role] += 1
            return True
        return False

    return convert_one


def _global_target_role_counts(df: gpd.GeoDataFrame, config: dict) -> dict[str, int]:
    if 'is_culte' not in df.columns:
        return _target_role_counts(int(df['pop_t0'].sum()), config)

    household_allowed_mask = (~df['is_culte']) | df.get('culte_household_allowed', False)
    modeled_population = int(df.loc[household_allowed_mask, 'pop_t0'].sum())
    return _target_role_counts(modeled_population, config)


def _assert_exact_global_role_counts(df: gpd.GeoDataFrame, config: dict) -> None:
    """
    Vérifie explicitement l'atteinte des cibles globales de rôles.

    Cette assertion rend visible une propriété importante du modèle : lorsque
    l'option est activée, la composition démographique finale n'est pas
    seulement "proche" de la cible, elle doit lui être exactement égale.
    """
    targets = _global_target_role_counts(df, config)
    realized = {
        'scolaire': int(df['n_scolaire'].sum()),
        'senior': int(df['n_senior'].sum()),
        'actif_local': int(df['n_actif_local'].sum()),
        'actif_navetteur': int(df['n_actif_navetteur'].sum()),
        'inactif': int(df['n_inactif'].sum()),
    }
    if realized != targets:
        raise ValueError(
            "Les cibles globales de roles ne sont pas atteintes exactement : "
            f"realise={realized}, cible={targets}."
        )


def _can_convert_reference_to_child(household: dict, member_index: int) -> bool:
    return _can_convert_to_child(household, member_index)


def _rebalance_global_households(df: gpd.GeoDataFrame, config: dict) -> gpd.GeoDataFrame:
    targets = _global_target_role_counts(df, config)
    household_references = _household_member_references(df)
    current = _current_global_role_counts(df, household_references)
    convert_one = _build_global_role_converter(df, household_references, current)

    _rebalance_counts_to_targets(
        current,
        targets,
        convert_one,
        _can_convert_reference_to_child,
        retry_child_without_predicate=True,
    )

    return df


def _household_guardian_candidates(household: dict) -> list[str]:
    return [member['member_id'] for member in household['members'] if member['role'] in ADULT_REFERENCE_ROLES]


def _assign_guardian_member_id(household: dict) -> None:
    guardian_candidates = _household_guardian_candidates(household)
    has_child = any(member['role'] == CHILD_ROLE for member in household['members'])
    household['guardian_member_id'] = guardian_candidates[0] if has_child and guardian_candidates else None


def _fallback_destination(config: dict) -> str:
    return str(config['destination_model'].get('fallback_destination', OUTSIDE_DESTINATION))


def _destination_for_role(role: str, row, df: gpd.GeoDataFrame, config: dict, rng: np.random.Generator, school_destination: str | None) -> tuple[str, str | None]:
    if role == CHILD_ROLE:
        if school_destination is None:
            school_destination = sample_destination_building_id(row, df, CHILD_ROLE, config, rng)
        return school_destination, school_destination
    if role == LOCAL_WORKER_ROLE:
        return sample_destination_building_id(row, df, LOCAL_WORKER_ROLE, config, rng), school_destination
    if role == COMMUTER_ROLE:
        return _fallback_destination(config), school_destination
    return HOME_DESTINATION, school_destination


def _assign_household_destinations(household: dict, row, df: gpd.GeoDataFrame, config: dict, rng: np.random.Generator) -> None:
    _assign_guardian_member_id(household)
    school_destination = None

    for member in household['members']:
        member['destination_id'], school_destination = _destination_for_role(
            member['role'],
            row,
            df,
            config,
            rng,
            school_destination,
        )


def _members_for_household(building_id: str, household_index: int, roles: list[str]) -> list[dict]:
    members = []
    for member_index, role in enumerate(roles, start=1):
        members.append({
            'member_id': f"{building_id}_hh{household_index}_m{member_index}",
            'role': role,
        })
    return members


def _build_households_for_row(row, df: gpd.GeoDataFrame, config: dict, rng: np.random.Generator) -> list[dict]:
    if not _households_allowed_for_row(row):
        return []

    population = int(row['pop_t0'])
    if population <= 0:
        return []
    if str(row.get('exogenous_zone_type', '')).casefold() == 'plage':
        return []

    dwellings = _positive_int(row.get('nombre_de_logements'))
    household_sizes = _sample_household_sizes(population, dwellings, rng, config)
    households: list[dict] = []

    for household_index, household_size in enumerate(household_sizes, start=1):
        roles = _build_household_roles(household_size, rng, config)
        households.append({
            'household_id': f"{row['building_id']}_hh{household_index}",
            'size': household_size,
            'members': _members_for_household(str(row['building_id']), household_index, roles),
        })

    households = _rebalance_role_counts(households, population, config)

    for household in households:
        _assign_household_destinations(household, row, df, config, rng)

    return households


def _flatten_roles(households: list[dict]) -> list[str]:
    return [member['role'] for household in households for member in household['members']]


def _major_destination(households: list[dict]) -> str | None:
    destinations = [
        member['destination_id']
        for household in households
        for member in household['members']
        if member['destination_id'] not in {HOME_DESTINATION, OUTSIDE_DESTINATION, None}
    ]
    if not destinations:
        return None
    return Counter(destinations).most_common(1)[0][0]


def _school_capacity_total(config: dict) -> int:
    return sum(
        int(school_cfg.get('capacity', 0))
        for school_cfg in config.get('infrastructures', {}).get('schools', {}).values()
        if isinstance(school_cfg, dict)
    )


def _enforce_local_school_capacity(df: gpd.GeoDataFrame, config: dict) -> gpd.GeoDataFrame:
    capacity_total = _school_capacity_total(config)
    if capacity_total <= 0:
        return df

    fallback_destination = _fallback_destination(config)
    building_by_id = df.set_index('building_id')
    school_refs: list[tuple[float, int, int, int]] = []

    for row_index, households in df['households'].items():
        origin = df.loc[row_index]
        origin_centroid = origin.geometry.centroid
        for household_index, household in enumerate(households):
            for member_index, member in enumerate(household['members']):
                if member.get('role') != CHILD_ROLE:
                    continue
                destination_id = member.get('destination_id')
                if destination_id in NON_INTERNAL_DESTINATIONS:
                    continue
                if destination_id not in building_by_id.index:
                    member['destination_id'] = fallback_destination
                    continue
                destination_centroid = building_by_id.loc[destination_id].geometry.centroid
                distance_m = float(origin_centroid.distance(destination_centroid))
                school_refs.append((distance_m, row_index, household_index, member_index))

    if len(school_refs) <= capacity_total:
        return df

    school_refs.sort(key=itemgetter(0))
    overflow = school_refs[capacity_total:]
    for _, row_index, household_index, member_index in overflow:
        df.at[row_index, 'households'][household_index]['members'][member_index]['destination_id'] = fallback_destination

    return df


def _school_assignment_counts(households: list[dict]) -> dict[str, int]:
    internal = 0
    external = 0
    for household in households:
        for member in household['members']:
            if member.get('role') != CHILD_ROLE:
                continue
            destination_id = member.get('destination_id')
            if destination_id in {OUTSIDE_DESTINATION, 'None', None}:
                external += 1
            else:
                internal += 1
    return {
        'n_scolaire_interne': internal,
        'n_scolaire_exterieur': external,
    }


def _refresh_households_for_row(row, df: gpd.GeoDataFrame, config: dict, rng: np.random.Generator) -> list[dict]:
    households = row['households']

    for household in households:
        _assign_household_destinations(household, row, df, config, rng)

    return households


def _build_households_series(df: gpd.GeoDataFrame, config: dict, rng: np.random.Generator) -> pd.Series:
    return df.apply(_build_households_for_row, axis=1, args=(df, config, rng))


def _refresh_households_series(df: gpd.GeoDataFrame, config: dict, rng: np.random.Generator) -> pd.Series:
    return df.apply(_refresh_households_for_row, axis=1, args=(df, config, rng))


def _count_mapping_row(item: dict, columns: list[str]) -> dict[str, int]:
    return {column: int(item.get(column, 0)) for column in columns}


def _expand_count_mapping(series: pd.Series, columns: list[str]) -> pd.DataFrame:
    expanded = series.apply(_count_mapping_row, args=(columns,))
    return pd.DataFrame(list(expanded), index=series.index)[columns]


def _assign_role_count_columns(df: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    counts = _expand_count_mapping(df['liste_roles'].apply(_role_counts), ROLE_COUNT_COLUMNS)
    for column in ROLE_COUNT_COLUMNS:
        df[column] = counts[column]
    return df


def _assign_school_count_columns(df: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    counts = _expand_count_mapping(df['households'].apply(_school_assignment_counts), SCHOOL_COUNT_COLUMNS)
    for column in SCHOOL_COUNT_COLUMNS:
        df[column] = counts[column]
    return df


def _finalize_household_outputs(df: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    df['liste_roles'] = df['households'].apply(_flatten_roles)
    df['n_households'] = df['households'].apply(len)
    df = _assign_role_count_columns(df)
    df = _assign_school_count_columns(df)
    df['dest_id'] = df['households'].apply(_major_destination)
    return df


def generer_agendas_agents(gdf_batiments: gpd.GeoDataFrame, config: dict) -> gpd.GeoDataFrame:
    """
    Attribue des rôles, des foyers et des lieux de destination aux agents.

    Notes
    -----
    Le résultat reste agrégé à l'échelle bâtiment, mais la structure interne
    `households` permet à la matrice horaire d'appliquer des dynamiques plus
    réalistes que dans le modèle purement individuel précédent.
    """
    logger.info("Début de la génération des agendas comportementaux par foyer...")

    df = gdf_batiments.copy()
    rng = build_rng(config, "agendas")

    df['households'] = _build_households_series(df, config, rng)
    df = _rebalance_global_households(df, config)
    rng_dest = build_rng(config, "agendas_destinations")
    df['households'] = _refresh_households_series(df, config, rng_dest)
    df = _enforce_local_school_capacity(df, config)
    df = _finalize_household_outputs(df)

    if config['demographics']['households'].get('enforce_exact_role_targets', True):
        _assert_exact_global_role_counts(df, config)

    logger.info(
        "Agendas générés : foyers, rôles et destinations ont été attribués de façon reproductible."
    )
    return df
