from src.core.agendas import generer_agendas_agents
from src.core.profiling import generer_profils_batiments
from src.core.restaurants import integrer_restaurants_aux_batiments
from src.core.cultes import integrer_lieux_culte
from src.core.temporal import generer_matrice_horaire
from src.pipeline import run_pipeline


def test_pipeline_is_strictly_reproducible(config):
    run_a = run_pipeline(config)
    run_b = run_pipeline(config)

    colonnes = [
        'building_id', 'pop_t0', 'dest_id', 'n_scolaire', 'n_senior', 'n_actif_local',
        'n_actif_navetteur', 'is_restaurant', 'is_culte'
    ] + [f'pop_h{hour}' for hour in range(24)]

    for colonne in colonnes:
        assert run_a[colonne].equals(run_b[colonne]), f"Colonne non reproductible : {colonne}"


def test_briques_stochastiques_restent_stables(config, bati_nettoye):
    base = generer_profils_batiments(bati_nettoye)

    agendas_a = generer_agendas_agents(base, config)
    agendas_b = generer_agendas_agents(base, config)
    assert agendas_a['liste_roles'].equals(agendas_b['liste_roles'])
    assert agendas_a['dest_id'].equals(agendas_b['dest_id'])
    assert agendas_a['n_households'].equals(agendas_b['n_households'])

    enriched_a = integrer_lieux_culte(integrer_restaurants_aux_batiments(agendas_a, config), config)
    enriched_b = integrer_lieux_culte(integrer_restaurants_aux_batiments(agendas_b, config), config)

    temporal_a = generer_matrice_horaire(enriched_a, config)
    temporal_b = generer_matrice_horaire(enriched_b, config)

    for hour in range(24):
        colonne = f'pop_h{hour}'
        assert temporal_a[colonne].equals(temporal_b[colonne]), f"Matrice non reproductible pour {colonne}"
