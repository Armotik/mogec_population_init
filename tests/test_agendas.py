from src.core.agendas import generer_agendas_agents


def test_coherence_agendas(config, bati_popule):
    # Appel de la fonction de génération d'agendas
    df_agenda = generer_agendas_agents(bati_popule, config)

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
