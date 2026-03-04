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

    print(f"\n" + "=" * 30)
    print(f" BILAN DES AGENDAS (N={total_agents})")
    print(f"=" * 30)
    print(f" Scolaires   : {n_scolaires} ({n_scolaires / total_agents:.1%})")
    print(f" Seniors     : {n_seniors} ({n_seniors / total_agents:.1%})")
    print(f" Navetteurs  : {n_navetteurs} ({n_navetteurs / total_agents:.1%})")
    print(f" Actifs Loc. : {n_locaux} ({n_locaux / total_agents:.1%})")

    # Vérifications basées sur tes données INSEE
    # Enfants (Cible ~9.7%)
    assert 0.07 <= (n_scolaires / total_agents) <= 0.13
    # Seniors (Cible ~42.4%)
    assert 0.35 <= (n_seniors / total_agents) <= 0.50
    # Vérification des destinations
    assert 'dest_id' in df_agenda.columns
    assert df_agenda['dest_id'].notnull().any()