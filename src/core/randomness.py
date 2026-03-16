"""
Outils de reproductibilité pour les briques stochastiques.

Le projet utilise des tirages aléatoires pour les rôles, les agendas et
l'imputation de certains attributs. Ce module garantit qu'un même scénario et
un même seed produiront exactement les mêmes sorties.
"""

import hashlib
import logging

import numpy as np

logger = logging.getLogger(__name__)

# Seed de secours utilisé uniquement pour des configurations unitaires minimales.
# En production, la reproductibilité doit rester pilotée par `project.random_seed`.
DEFAULT_RANDOM_SEED = 0


def build_rng(config: dict, salt: str) -> np.random.Generator:
    """
    Construit un générateur pseudo-aléatoire déterministe pour une brique donnée.

    Le seed projet est dérivé par "salt" pour que deux fonctions restent stables
    même si l'une consomme plus de tirages aléatoires que l'autre.

    Parameters
    ----------
    config:
        Configuration projet contenant idéalement `project.random_seed`.
        Si ce champ est absent dans un test unitaire minimal, un seed de secours
        déterministe est utilisé pour conserver une exécution stable.
    salt:
        Libellé stable identifiant la brique appelante.
    """
    project_cfg = config.get('project', {})
    if 'random_seed' not in project_cfg:
        logger.debug(
            "Aucun `project.random_seed` fourni; utilisation du seed déterministe "
            "de secours %s pour la brique %s.",
            DEFAULT_RANDOM_SEED,
            salt,
        )
    base_seed = int(project_cfg.get('random_seed', DEFAULT_RANDOM_SEED))
    digest = hashlib.sha256(f"{base_seed}:{salt}".encode("utf-8")).digest()
    derived_seed = int.from_bytes(digest[:8], byteorder="big", signed=False)
    return np.random.default_rng(derived_seed)
