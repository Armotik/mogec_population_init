import logging
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
import geopandas as gpd

logger = logging.getLogger(__name__)


def plot_respiration_urbaine(df_horaire: gpd.GeoDataFrame, output_path: str):
    """
    Génère un graphique linéaire montrant l'évolution de la population
    présente dans les bâtiments de la commune de t=0 à t=23.
    """
    logger.info("Génération du graphique de respiration urbaine...")

    # Extraction des 24 colonnes horaires
    colonnes_heures = [f'pop_h{h}' for h in range(24)]

    # Somme de la population de tous les bâtiments pour chaque heure
    population_totale_par_heure = df_horaire[colonnes_heures].sum()

    # Création du graphique
    fig, ax = plt.subplots(figsize=(10, 6))

    # Tracé de la courbe
    ax.plot(range(24), population_totale_par_heure, marker='o', linestyle='-', color='#1f77b4', linewidth=2)

    # Habillage du graphique
    ax.set_title("Respiration Urbaine de Batz-sur-Mer (Cycle de 24h)", fontsize=14, pad=15)
    ax.set_xlabel("Heure de la journée (t)", fontsize=12)
    ax.set_ylabel("Population présente dans la commune", fontsize=12)
    ax.set_xticks(range(0, 24, 2))  # Afficher une heure sur deux
    ax.grid(True, linestyle='--', alpha=0.7)

    # Ajout d'annotations pour les phases clés
    pop_nuit = population_totale_par_heure['pop_h3']
    pop_jour = population_totale_par_heure['pop_h14']
    navetteurs = pop_nuit - pop_jour

    ax.annotate(f'Nuit (Max): {int(pop_nuit)}', xy=(3, pop_nuit), xytext=(3, pop_nuit + 100),
                arrowprops=dict(facecolor='black', shrink=0.05, width=1, headwidth=5), ha='center')

    ax.annotate(f'Jour (Min): {int(pop_jour)}', xy=(14, pop_jour), xytext=(14, pop_jour - 200),
                arrowprops=dict(facecolor='black', shrink=0.05, width=1, headwidth=5), ha='center')

    # Zone de texte explicative
    texte_explicatif = f"Baisse diurne : -{int(navetteurs)} agents\n(Départ des navetteurs vers l'extérieur)"
    ax.text(0.05, 0.05, texte_explicatif, transform=ax.transAxes, fontsize=10,
            verticalalignment='bottom', bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))

    # Sauvegarde
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=300, bbox_inches='tight')
    plt.close(fig)

    logger.info(f"Graphique sauvegardé : {path}")
    return path