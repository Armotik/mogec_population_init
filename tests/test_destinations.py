from src.core.destinations import sample_destination_building_id
from src.core.profiling import generer_profils_batiments
from src.core.agendas import generer_agendas_agents
from src.core.randomness import build_rng


def test_destination_sampling_returns_stable_building_id(config, bati_nettoye):
    df = generer_profils_batiments(bati_nettoye)
    df = generer_agendas_agents(df, config)

    origin = df[df['n_actif_local'] > 0].iloc[0]
    rng_a = build_rng(config, "destinations_test")
    rng_b = build_rng(config, "destinations_test")

    destination_a = sample_destination_building_id(origin, df, 'actif_local', config, rng_a)
    destination_b = sample_destination_building_id(origin, df, 'actif_local', config, rng_b)

    assert isinstance(destination_a, str)
    assert destination_a == destination_b
    assert destination_a == config['destination_model']['fallback_destination'] or destination_a in df['building_id'].tolist()
