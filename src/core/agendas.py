import pandas as pd
import numpy as np
import geopandas as gpd
import logging

logger = logging.getLogger(__name__)


def generer_agendas_agents(gdf_batiments: gpd.GeoDataFrame, config: dict) -> gpd.GeoDataFrame:
    """
    Attribue des rôles et des lieux de destination aux agents
    en fonction des statistiques INSEE et des capacités locales.
    """
    logger.info("Début de la génération des agendas comportementaux...")

    df = gdf_batiments.copy()

    # 1. Identification des pôles de destination (Cibles)
    # On identifie les écoles via l'usage et les noms dans la config
    ecoles = df[df['usage_1'].str.contains('Enseignement', na=False, case=False)].copy()
    commerces = df[df['usage_1'].str.contains('Commercial|Tertiaire', na=False, case=False)].copy()
    industries = df[df['usage_1'].str.contains('Industriel', na=False, case=False)].copy()

    # 2. Attribution des rôles aux agents (Distribution Insee)
    # On va itérer sur chaque ligne (bâtiment) pour traiter les 'pop_t0' agents qu'il contient
    def definir_roles(row):
        n_agents = int(row['pop_t0'])
        if n_agents == 0: return []

        roles = []
        for _ in range(n_agents):
            rand = np.random.rand()
            # Seuil Enfants (Insee: 9.7%)
            if rand < config['demographics']['age_pyramid']['under_15']:
                roles.append('scolaire')
            # Seuil Seniors (Insee: 42.4%)
            elif rand > (1 - config['demographics']['age_pyramid']['over_65']):
                roles.append('senior')
            else:
                # Parmi les actifs, on sépare Navetteurs (61.4%) et Locaux (38.6%)
                if np.random.rand() < config['demographics']['employment']['navetteurs_ext_pct']:
                    roles.append('actif_navetteur')
                else:
                    roles.append('actif_local')
        return roles

    df['liste_roles'] = df.apply(definir_roles, axis=1)

    # 3. Assignation des lieux de destination
    # Pour simplifier l'export GAMA, on calcule une 'destination_principale' par bâtiment
    # Dans GAMA, on pourra affiner agent par agent.

    def assigner_destination(row):
        roles = row['liste_roles']
        if not roles: return None

        # Logique de destination par défaut pour le groupe
        role_majoritaire = max(set(roles), key=roles.count) if roles else None

        if role_majoritaire == 'scolaire':
            # On assigne l'école la plus proche
            return ecoles.geometry.centroid.distance(
                row.geometry.centroid).idxmin() if not ecoles.empty else "EXTERIEUR"

        elif role_majoritaire == 'actif_local':
            # On assigne un commerce ou une industrie proche
            targets = pd.concat([commerces, industries])
            return targets.geometry.centroid.distance(
                row.geometry.centroid).idxmin() if not targets.empty else "EXTERIEUR"

        elif role_majoritaire == 'actif_navetteur':
            return "EXTERIEUR"  # Sortie de carte

        else:
            return "DOMICILE"  # Les seniors restent majoritairement proches

    df['dest_id'] = df.apply(assigner_destination, axis=1)

    logger.info(
        f"Agendas générés. Répartition cible : {config['demographics']['age_pyramid']['over_65'] * 100}% seniors.")
    return df