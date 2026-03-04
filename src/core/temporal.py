import logging
import pandas as pd
import numpy as np
import geopandas as gpd
import random

logger = logging.getLogger(__name__)


def generer_matrice_horaire(df_batiments: gpd.GeoDataFrame, config: dict) -> gpd.GeoDataFrame:
    """
    Calcule la population présente dans chaque bâtiment pour chaque heure (t=0 à t=23).
    Intègre les navetteurs, la pause méridienne, les restaurants et les lieux de culte.
    """
    jour_scenario = config['scenario'].get('day_of_week', 'Dimanche')
    logger.info(f"Génération de la matrice horaire 24h (Scénario: {jour_scenario})...")

    df = df_batiments.copy()

    # 1. Initialisation des 24 colonnes à 0
    for h in range(24):
        df[f'pop_h{h}'] = 0

    presence_matrix = {idx: np.zeros(24) for idx in df.index}

    # 2. Identification des cibles spécifiques
    commerces_ids = df[df['is_restaurant'] == True].index.tolist() if 'is_restaurant' in df.columns else []
    cultes_ids = df[df['is_culte'] == True].index.tolist() if 'is_culte' in df.columns else []

    # 3. Remplissage de la matrice agent par agent
    for idx, row in df.iterrows():
        roles = row.get('liste_roles', [])
        dest_id = row.get('dest_id', 'DOMICILE')

        if not isinstance(roles, list):
            continue

        for role in roles:
            # Pré-tirage des destinations aléatoires pour la journée de cet agent
            resto_midi_id = random.choice(commerces_ids) if commerces_ids else "DOMICILE"
            resto_soir_id = random.choice(commerces_ids) if commerces_ids else "DOMICILE"
            culte_id = random.choice(cultes_ids) if cultes_ids else "DOMICILE"

            for h in range(24):
                lieu_actuel = "DOMICILE"  # État par défaut la nuit et le soir

                # --- A. ROUTINE SCOLAIRE ---
                if role == 'scolaire':
                    if jour_scenario not in ['Samedi', 'Dimanche'] and not config['scenario'].get('is_school_holiday',
                                                                                                  False):
                        if (8 <= h <= 11) or (14 <= h <= 16):
                            lieu_actuel = dest_id

                # --- B. ROUTINE ACTIF LOCAL ---
                elif role == 'actif_local':
                    if jour_scenario not in ['Samedi', 'Dimanche']:
                        if (8 <= h <= 11) or (14 <= h <= 17):
                            lieu_actuel = dest_id  # Au travail
                        elif h in [12, 13]:
                            # 20% de chance d'aller au resto le midi, sinon domicile
                            lieu_actuel = resto_midi_id if random.random() < 0.20 else "DOMICILE"

                # --- C. ROUTINE ACTIF NAVETTEUR ---
                elif role == 'actif_navetteur':
                    if jour_scenario not in ['Samedi', 'Dimanche']:
                        if 8 <= h <= 18:
                            lieu_actuel = "EXTERIEUR"  # Hors carte

                # --- D. ROUTINE SENIOR ---
                elif role == 'senior':
                    if jour_scenario == 'Dimanche' and h in [10, 11]:
                        # 15% de chance d'aller à la messe le dimanche matin
                        lieu_actuel = culte_id if random.random() < 0.15 else "DOMICILE"
                    elif h in [10, 11] and jour_scenario != 'Dimanche':
                        lieu_actuel = "EXTERIEUR"  # Marché / Courses hors domicile
                    elif h in [12, 13]:
                        # 10% de chance d'aller au resto le midi
                        lieu_actuel = resto_midi_id if random.random() < 0.10 else "DOMICILE"
                    elif h in [15, 16]:
                        lieu_actuel = "EXTERIEUR"  # Balade l'après-midi
                    elif h in [19, 20]:
                        # 5% de chance de sortir dîner le soir
                        lieu_actuel = resto_soir_id if random.random() < 0.05 else "DOMICILE"

                # --- 4. ASSIGNATION SPATIALE ---
                if lieu_actuel == "DOMICILE":
                    presence_matrix[idx][h] += 1
                elif lieu_actuel not in ["EXTERIEUR", "None", None]:
                    if lieu_actuel in presence_matrix:
                        presence_matrix[lieu_actuel][h] += 1

    # 5. Écriture des résultats agglomérés dans le GeoDataFrame
    for idx, presence in presence_matrix.items():
        for h in range(24):
            df.at[idx, f'pop_h{h}'] = int(presence[h])

    logger.info("Matrice horaire 24h générée avec succès.")
    return df