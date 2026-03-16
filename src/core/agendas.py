"""
Génération des foyers, des rôles et des destinations principales.

Le modèle ne tire plus uniquement des rôles bâtiment par bâtiment. Il construit
une structure intermédiaire de foyers afin de produire des compositions
familiales plus plausibles, de garantir qu'un enfant ne vive pas seul et de
préparer des dynamiques intra-foyer pour la matrice horaire.
"""

from collections import Counter
import logging

import geopandas as gpd
import numpy as np

from src.core.destinations import sample_destination_building_id
from src.core.randomness import build_rng

logger = logging.getLogger(__name__)


def _adult_role_weights(config: dict) -> dict[str, float]:
    age_cfg = config['demographics']['age_pyramid']
    employment_cfg = config['demographics']['employment']

    child_share = float(age_cfg['under_15'])
    senior_share = float(age_cfg['over_65'])
    non_child_total = max(1e-9, 1.0 - child_share)
    senior_weight = senior_share / non_child_total
    active_weight = max(0.0, 1.0 - senior_weight)

    local_pct = float(employment_cfg['travail_local_pct'])
    commuter_pct = float(employment_cfg['navetteurs_ext_pct'])

    return {
        'senior': senior_weight,
        'actif_local': active_weight * local_pct,
        'actif_navetteur': active_weight * commuter_pct,
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


def _sample_adult_role(rng: np.random.Generator, config: dict) -> str:
    return _sample_weighted_choice(_adult_role_weights(config), rng)


def _sample_family_guardian_role(rng: np.random.Generator, config: dict) -> str:
    guardian_cfg = config['demographics']['households'].get('family_guardian', {})
    return _sample_weighted_choice({
        'actif_local': float(guardian_cfg.get('actif_local_pct', 0.40)),
        'actif_navetteur': float(guardian_cfg.get('actif_navetteur_pct', 0.55)),
        'senior': float(guardian_cfg.get('senior_pct', 0.05)),
    }, rng)


def _build_household_roles(size: int, rng: np.random.Generator, config: dict) -> list[str]:
    household_cfg = config['demographics']['households']
    family_pct = float(household_cfg['family_household_pct'])
    single_senior_pct = float(household_cfg['single_senior_pct'])
    two_adults_pct = float(household_cfg['two_adults_if_children_pct'])

    if size == 1:
        return ['senior'] if rng.random() < single_senior_pct else [_sample_adult_role(rng, config)]

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
            roles.append('scolaire')

        while len(roles) < size:
            roles.append(_sample_adult_role(rng, config))
    else:
        for _ in range(size):
            if rng.random() < float(config['demographics']['age_pyramid']['under_15']):
                roles.append('scolaire')
            else:
                roles.append(_sample_adult_role(rng, config))

    if 'scolaire' in roles and not any(role in {'actif_local', 'actif_navetteur', 'senior'} for role in roles):
        roles[0] = 'actif_local'

    if size == 1 and roles[0] == 'scolaire':
        roles[0] = 'actif_local'

    return roles[:size]


def _role_counts(roles: list[str]) -> dict[str, int]:
    counts = Counter(roles)
    return {
        'n_scolaire': counts.get('scolaire', 0),
        'n_senior': counts.get('senior', 0),
        'n_actif_local': counts.get('actif_local', 0),
        'n_actif_navetteur': counts.get('actif_navetteur', 0),
    }


def _target_role_counts(population: int, config: dict) -> dict[str, int]:
    age_cfg = config['demographics']['age_pyramid']
    employment_cfg = config['demographics']['employment']

    n_scolaire = int(round(population * float(age_cfg['under_15'])))
    n_senior = int(round(population * float(age_cfg['over_65'])))
    n_active = max(0, population - n_scolaire - n_senior)
    n_actif_local = int(round(n_active * float(employment_cfg['travail_local_pct'])))
    n_actif_navetteur = max(0, n_active - n_actif_local)

    return {
        'scolaire': n_scolaire,
        'senior': n_senior,
        'actif_local': n_actif_local,
        'actif_navetteur': n_actif_navetteur,
    }


def _current_role_counts(households: list[dict]) -> Counter:
    return Counter(member['role'] for household in households for member in household['members'])


def _can_convert_to_child(household: dict, member_index: int) -> bool:
    other_roles = [member['role'] for idx, member in enumerate(household['members']) if idx != member_index]
    return any(role != 'scolaire' for role in other_roles)


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

    while current['scolaire'] < targets['scolaire']:
        if not convert_one(['senior', 'actif_local', 'actif_navetteur'], 'scolaire', _can_convert_to_child):
            break

    while current['scolaire'] > targets['scolaire']:
        if not convert_one(['scolaire'], 'actif_local'):
            break

    while current['senior'] < targets['senior']:
        if not convert_one(['actif_local', 'actif_navetteur'], 'senior'):
            break

    while current['senior'] > targets['senior']:
        preferred_target = 'actif_navetteur' if current['actif_navetteur'] < targets['actif_navetteur'] else 'actif_local'
        if not convert_one(['senior'], preferred_target):
            break

    while current['actif_local'] < targets['actif_local']:
        if not convert_one(['actif_navetteur'], 'actif_local'):
            break

    while current['actif_local'] > targets['actif_local']:
        if not convert_one(['actif_local'], 'actif_navetteur'):
            break

    return households


def _global_target_role_counts(df: gpd.GeoDataFrame, config: dict) -> dict[str, int]:
    return _target_role_counts(int(df['pop_t0'].sum()), config)


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
    household_references = []

    for row_index, households in df['households'].items():
        for household_index, household in enumerate(households):
            for member_index, member in enumerate(household['members']):
                household_references.append((row_index, household_index, member_index))

    current = Counter(
        df.at[row_index, 'households'][household_index]['members'][member_index]['role']
        for row_index, household_index, member_index in household_references
    )

    def convert_one(from_roles: list[str], to_role: str, predicate=None) -> bool:
        for row_index, household_index, member_index in household_references:
            household = df.at[row_index, 'households'][household_index]
            member = household['members'][member_index]
            if member['role'] not in from_roles:
                continue
            if predicate is not None and not predicate(household, member_index):
                continue
            current[member['role']] -= 1
            member['role'] = to_role
            current[to_role] += 1
            return True
        return False

    while current['scolaire'] < targets['scolaire']:
        if not convert_one(['senior', 'actif_local', 'actif_navetteur'], 'scolaire', _can_convert_reference_to_child):
            if not convert_one(['senior', 'actif_local', 'actif_navetteur'], 'scolaire'):
                break

    while current['scolaire'] > targets['scolaire']:
        if not convert_one(['scolaire'], 'actif_local'):
            break

    while current['senior'] < targets['senior']:
        if not convert_one(['actif_local', 'actif_navetteur'], 'senior'):
            break

    while current['senior'] > targets['senior']:
        preferred_target = 'actif_navetteur' if current['actif_navetteur'] < targets['actif_navetteur'] else 'actif_local'
        if not convert_one(['senior'], preferred_target):
            break

    while current['actif_local'] < targets['actif_local']:
        if not convert_one(['actif_navetteur'], 'actif_local'):
            break

    while current['actif_local'] > targets['actif_local']:
        if not convert_one(['actif_local'], 'actif_navetteur'):
            break

    return df


def _build_households_for_row(row, df: gpd.GeoDataFrame, config: dict, rng: np.random.Generator) -> list[dict]:
    population = int(row['pop_t0'])
    if population <= 0:
        return []
    if str(row.get('exogenous_zone_type', '')).casefold() == 'plage':
        return []

    dwellings_value = row.get('nombre_de_logements')
    dwellings = int(dwellings_value) if dwellings_value is not None and not np.isnan(dwellings_value) and dwellings_value > 0 else 0
    household_sizes = _sample_household_sizes(population, dwellings, rng, config)
    households: list[dict] = []

    for household_index, household_size in enumerate(household_sizes, start=1):
        roles = _build_household_roles(household_size, rng, config)
        members = []

        for member_index, role in enumerate(roles, start=1):
            member_id = f"{row['building_id']}_hh{household_index}_m{member_index}"
            members.append({
                'member_id': member_id,
                'role': role,
            })

        households.append({
            'household_id': f"{row['building_id']}_hh{household_index}",
            'size': household_size,
            'members': members,
        })

    households = _rebalance_role_counts(households, population, config)

    for household in households:
        school_destination = None
        guardian_candidates = [member['member_id'] for member in household['members'] if member['role'] in {'actif_local', 'actif_navetteur', 'senior'}]
        household['guardian_member_id'] = guardian_candidates[0] if any(member['role'] == 'scolaire' for member in household['members']) and guardian_candidates else None

        for member in household['members']:
            role = member['role']
            if role == 'scolaire':
                if school_destination is None:
                    school_destination = sample_destination_building_id(row, df, 'scolaire', config, rng)
                member['destination_id'] = school_destination
            elif role == 'actif_local':
                member['destination_id'] = sample_destination_building_id(row, df, 'actif_local', config, rng)
            elif role == 'actif_navetteur':
                member['destination_id'] = config['destination_model'].get('fallback_destination', 'EXTERIEUR')
            else:
                member['destination_id'] = "DOMICILE"

    return households


def _flatten_roles(households: list[dict]) -> list[str]:
    return [member['role'] for household in households for member in household['members']]


def _major_destination(households: list[dict]) -> str | None:
    destinations = [
        member['destination_id']
        for household in households
        for member in household['members']
        if member['destination_id'] not in {"DOMICILE", "EXTERIEUR", None}
    ]
    if not destinations:
        return None
    return Counter(destinations).most_common(1)[0][0]


def _refresh_households_for_row(row, df: gpd.GeoDataFrame, config: dict, rng: np.random.Generator) -> list[dict]:
    households = row['households']

    for household in households:
        school_destination = None
        guardian_candidates = [member['member_id'] for member in household['members'] if member['role'] in {'actif_local', 'actif_navetteur', 'senior'}]
        household['guardian_member_id'] = guardian_candidates[0] if any(member['role'] == 'scolaire' for member in household['members']) and guardian_candidates else None

        for member in household['members']:
            if member['role'] == 'scolaire':
                if school_destination is None:
                    school_destination = sample_destination_building_id(row, df, 'scolaire', config, rng)
                member['destination_id'] = school_destination
            elif member['role'] == 'actif_local':
                member['destination_id'] = sample_destination_building_id(row, df, 'actif_local', config, rng)
            elif member['role'] == 'actif_navetteur':
                member['destination_id'] = config['destination_model'].get('fallback_destination', 'EXTERIEUR')
            else:
                member['destination_id'] = "DOMICILE"

    return households


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

    df['households'] = df.apply(lambda row: _build_households_for_row(row, df, config, rng), axis=1)
    df = _rebalance_global_households(df, config)
    rng_dest = build_rng(config, "agendas_destinations")
    df['households'] = df.apply(lambda row: _refresh_households_for_row(row, df, config, rng_dest), axis=1)

    df['liste_roles'] = df['households'].apply(_flatten_roles)
    df['n_households'] = df['households'].apply(len)

    counts = df['liste_roles'].apply(_role_counts)
    for column in ['n_scolaire', 'n_senior', 'n_actif_local', 'n_actif_navetteur']:
        df[column] = counts.apply(lambda item: item[column])

    df['dest_id'] = df['households'].apply(_major_destination)

    if config['demographics']['households'].get('enforce_exact_role_targets', True):
        _assert_exact_global_role_counts(df, config)

    logger.info(
        "Agendas générés : foyers, rôles et destinations ont été attribués de façon reproductible."
    )
    return df
