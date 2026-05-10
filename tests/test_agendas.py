import geopandas as gpd
from copy import deepcopy
from shapely.geometry import Polygon

from src.core.agendas import generer_agendas_agents
from src.core.cultes import integrer_lieux_culte


def test_coherence_agendas(config, bati_popule):
    subset = bati_popule[bati_popule['pop_t0'] > 0].sort_values('building_id').head(140).copy()
    if subset.empty:
        subset = bati_popule.sort_values('building_id').head(140).copy()

    # Appel de la fonction de génération d'agendas
    df_agenda = generer_agendas_agents(subset, config)

    # Extraction de tous les rôles pour analyse statistique
    tous_les_roles = [role for liste in df_agenda['liste_roles'] for role in liste]
    total_agents = len(tous_les_roles)

    n_scolaires = tous_les_roles.count('scolaire')
    n_seniors = tous_les_roles.count('senior')
    n_navetteurs = tous_les_roles.count('actif_navetteur')
    n_locaux = tous_les_roles.count('actif_local')
    n_inactifs = tous_les_roles.count('inactif')
    n_scolaires_internes = int(df_agenda['n_scolaire_interne'].sum())

    print(f"\n" + "=" * 30)
    print(f" BILAN DES AGENDAS (N={total_agents})")
    print(f"=" * 30)
    print(f" Scolaires   : {n_scolaires} ({n_scolaires / total_agents:.1%})")
    print(f" Seniors     : {n_seniors} ({n_seniors / total_agents:.1%})")
    print(f" Navetteurs  : {n_navetteurs} ({n_navetteurs / total_agents:.1%})")
    print(f" Actifs Loc. : {n_locaux} ({n_locaux / total_agents:.1%})")
    print(f" Inactifs    : {n_inactifs} ({n_inactifs / total_agents:.1%})")
    print(f" Scol. int.  : {n_scolaires_internes}")

    # Vérifications basées sur tes données INSEE
    # Enfants (Cible ~9.7%)
    assert 0.07 <= (n_scolaires / total_agents) <= 0.13
    # Seniors (Cible ~42.4%)
    assert 0.35 <= (n_seniors / total_agents) <= 0.50
    # Vérification des destinations
    assert 'building_id' in df_agenda.columns
    assert 'n_households' in df_agenda.columns
    assert 'dest_id' in df_agenda.columns
    assert 'n_scolaire_interne' in df_agenda.columns
    assert 'n_scolaire_exterieur' in df_agenda.columns
    assert df_agenda['dest_id'].notnull().any()

    capacite_scolaire = sum(
        int(school_cfg.get('capacity', 0))
        for school_cfg in config.get('infrastructures', {}).get('schools', {}).values()
        if isinstance(school_cfg, dict)
    )
    assert n_scolaires_internes <= capacite_scolaire

    if config['demographics']['households'].get('enforce_exact_role_targets', True):
        pop_totale = int(df_agenda['pop_t0'].sum())
        cible_scolaire = int(round(pop_totale * config['demographics']['age_pyramid']['under_15']))
        cible_senior = int(round(pop_totale * config['demographics']['age_pyramid']['over_65']))
        adultes = pop_totale - cible_scolaire - cible_senior
        local_pct = float(config['demographics']['employment']['travail_local_pct'])
        emplois_locaux = int(config['demographics']['employment']['total_emplois_lieu_travail'])
        actifs_estimes = min(adultes, max(int(round(emplois_locaux / local_pct)), emplois_locaux))
        cible_local = min(actifs_estimes, emplois_locaux)
        cible_navetteur = actifs_estimes - cible_local
        cible_inactif = adultes - actifs_estimes

        assert n_scolaires == cible_scolaire
        assert n_seniors == cible_senior
        assert n_locaux == cible_local
        assert n_navetteurs == cible_navetteur
        assert n_inactifs == cible_inactif


def test_interdit_menages_dans_batiments_culte_sans_exception(config):
    cfg = deepcopy(config)
    gdf = gpd.GeoDataFrame(
        {
            'building_id': ['CULTE_1', 'HOME_1', 'SCHOOL_1', 'WORK_1'],
            'usage_1': ['Résidentiel', 'Résidentiel', 'Enseignement', 'Commercial et services'],
            'nature': ['Eglise', 'Maison', 'Ecole', 'Commerce'],
            'surface_sol': [200.0, 150.0, 300.0, 500.0],
            'pop_t0': [6, 12, 0, 0],
            'is_culte': [True, False, False, False],
            'culte_household_allowed': [False, True, True, True],
        },
        geometry=[
            Polygon([(0, 0), (0, 10), (10, 10), (10, 0)]),
            Polygon([(30, 0), (30, 10), (40, 10), (40, 0)]),
            Polygon([(300, 0), (300, 10), (310, 10), (310, 0)]),
            Polygon([(500, 0), (500, 10), (510, 10), (510, 0)]),
        ],
        crs='EPSG:2154',
    )

    df_agenda = generer_agendas_agents(gdf, cfg)
    culte_row = df_agenda.loc[df_agenda['building_id'] == 'CULTE_1'].iloc[0]
    home_row = df_agenda.loc[df_agenda['building_id'] == 'HOME_1'].iloc[0]

    assert culte_row['is_culte'] == True
    assert culte_row['n_households'] == 0
    assert culte_row['households'] == []
    assert home_row['n_households'] > 0


def test_presbytere_autorise_par_exception_configurable(config):
    cfg = deepcopy(config)
    cfg['demographics']['households']['culte_residential_exceptions_any_of'] = ['presbytère']

    gdf = gpd.GeoDataFrame(
        {
            'building_id': ['PRESBYTERE', 'SCHOOL_1', 'WORK_1'],
            'usage_1': ['Religieux', 'Enseignement', 'Commercial et services'],
            'nature': ['Presbytère', 'Ecole', 'Commerce'],
            'surface_sol': [200.0, 300.0, 500.0],
            'pop_t0': [8, 0, 0],
        },
        geometry=[
            Polygon([(0, 0), (0, 10), (10, 10), (10, 0)]),
            Polygon([(300, 0), (300, 10), (310, 10), (310, 0)]),
            Polygon([(500, 0), (500, 10), (510, 10), (510, 0)]),
        ],
        crs='EPSG:2154',
    )

    gdf = integrer_lieux_culte(gdf, cfg)
    df_agenda = generer_agendas_agents(gdf, cfg)
    presby_row = df_agenda.loc[df_agenda['building_id'] == 'PRESBYTERE'].iloc[0]

    assert presby_row['is_culte'] == True
    assert presby_row['culte_household_allowed'] == True
    assert presby_row['n_households'] > 0


def test_agendas_conservent_population_modelee_hors_culte_interdit(config):
    gdf = gpd.GeoDataFrame(
        {
            'building_id': ['CULTE_0', 'HOME_12', 'SCHOOL_1', 'WORK_1'],
            'usage_1': ['Religieux', 'Résidentiel', 'Enseignement', 'Commercial et services'],
            'nature': ['Eglise', 'Maison', 'Ecole', 'Commerce'],
            'surface_sol': [220.0, 160.0, 280.0, 420.0],
            'pop_t0': [0, 12, 0, 0],
            'is_culte': [True, False, False, False],
            'culte_household_allowed': [False, True, True, True],
        },
        geometry=[
            Polygon([(0, 0), (0, 10), (10, 10), (10, 0)]),
            Polygon([(30, 0), (30, 10), (40, 10), (40, 0)]),
            Polygon([(300, 0), (300, 10), (310, 10), (310, 0)]),
            Polygon([(500, 0), (500, 10), (510, 10), (510, 0)]),
        ],
        crs='EPSG:2154',
    )

    df_agenda = generer_agendas_agents(gdf, config)
    total_members = int(sum(len(roles) for roles in df_agenda['liste_roles']))
    pop_modelee = int(df_agenda['pop_t0'].sum())

    assert total_members == pop_modelee
