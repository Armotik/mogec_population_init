import pytest
from src.core.agendas import generer_agendas_agents
from src.core.restaurants import integrer_restaurants_aux_batiments
from src.core.cultes import integrer_lieux_culte
from src.core.temporal import generer_matrice_horaire


def test_matrice_horaire_complete(config, bati_popule):
    # 1. Préparation de la donnée avec tous les attributs (Agendas, Restos, Cultes)
    config['data_paths']['input']['audit_restaurants'] = "data/01_raw/audit_restaurants_batz.csv"
    config['scenario']['day_of_week'] = "Dimanche"  # On force le dimanche pour tester l'église

    df = generer_agendas_agents(bati_popule, config)
    df = integrer_restaurants_aux_batiments(df, config)
    df = integrer_lieux_culte(df, config)

    # 2. Génération de la matrice 24h
    df_horaire = generer_matrice_horaire(df, config)

    # 3. Vérifications de base
    for h in range(24):
        assert f'pop_h{h}' in df_horaire.columns

    pop_totale_nuit = df_horaire['pop_h3'].sum()
    pop_totale_jour = df_horaire['pop_h15'].sum()

    print("\n" + "=" * 40)
    print(" VALIDATION DU CYCLE 24H (SCÉNARIO DIMANCHE)")
    print("=" * 40)
    print(f"Population Nuit (03h) : {pop_totale_nuit}")
    print(f"Population Jour (15h) : {pop_totale_jour}")

    # 4. Vérification des Lieux de Culte (Dimanche 10h)
    if 'is_culte' in df_horaire.columns and df_horaire['is_culte'].sum() > 0:
        batiments_cultes = df_horaire[df_horaire['is_culte'] == True]

        pop_culte_10h = batiments_cultes['pop_h10'].sum()
        pop_culte_03h = batiments_cultes['pop_h3'].sum()

        # On récupère le nombre de personnes qui "habitent" dans l'église (ex: Presbytère)
        pop_base_culte = batiments_cultes['pop_t0'].sum() if 'pop_t0' in batiments_cultes.columns else 0

        print(f"Agents à l'Église à 10h : {pop_culte_10h}")
        print(f"Agents à l'Église à 03h (Résidents permanents) : {pop_culte_03h}")

        assert pop_culte_10h > pop_base_culte, "L'église devrait attirer des fidèles le dimanche à 10h."
        # Le test vérifie maintenant que la nuit, la population redescend à son niveau de base (résidents)
        assert pop_culte_03h == pop_base_culte, f"La nuit, l'église ne devrait contenir que ses résidents ({pop_base_culte})."

    # 5. Vérification des Restaurants (Midi)
    if 'is_restaurant' in df_horaire.columns and df_horaire['is_restaurant'].sum() > 0:
        batiments_restos = df_horaire[df_horaire['is_restaurant'] == True]
        pop_restos_13h = batiments_restos['pop_h13'].sum()
        pop_restos_16h = batiments_restos['pop_h16'].sum()

        print(f"Agents aux Restaurants à 13h : {pop_restos_13h}")
        print(f"Agents aux Restaurants à 16h : {pop_restos_16h}")

        assert pop_restos_13h > pop_restos_16h, "Il devrait y avoir plus de monde au restaurant à 13h qu'à 16h."