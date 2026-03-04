import logging
from pathlib import Path
import geopandas as gpd
import matplotlib.pyplot as plt
import contextily as ctx

logger = logging.getLogger(__name__)


def exporter_frames_24h(gpkg_path: str, output_dir: str):
    """
    Génère et sauvegarde 24 cartes de chaleur (une par heure)
    pour visualiser la répartition de la population.
    """
    logger.info("Chargement des données pour l'export des 24 frames...")
    gdf = gpd.read_file(gpkg_path)

    # Définition de l'échelle absolue pour que le rouge vaille toujours la même densité
    colonnes_heures = [f'pop_h{h}' for h in range(24)]
    pop_max_absolue = gdf[colonnes_heures].max().max()

    # Création du dossier de destination
    dossier_frames = Path(output_dir)
    dossier_frames.mkdir(parents=True, exist_ok=True)

    logger.info(f"Génération des 24 cartes dans le dossier : {dossier_frames}")

    for h in range(24):
        fig, ax = plt.subplots(figsize=(12, 10))
        col_name = f'pop_h{h}'

        # A. Fond des bâtiments (gris)
        gdf.plot(ax=ax, color='lightgrey', alpha=0.5)

        # B. Bâtiments occupés
        gdf_occupes = gdf[gdf[col_name] > 0]

        if not gdf_occupes.empty:
            gdf_occupes.plot(
                ax=ax,
                column=col_name,
                cmap='YlOrRd',
                vmin=0,
                vmax=pop_max_absolue,
                legend=True,
                legend_kwds={'label': "Nombre d'agents", 'shrink': 0.7},
                alpha=0.9
            )

        # C. Fond de carte contextuel (Positron pour bien faire ressortir les couleurs)
        try:
            ctx.add_basemap(ax, crs=gdf.crs.to_string(), source=ctx.providers.CartoDB.Positron, zoom=15)
        except Exception as e:
            logger.warning(f"Impossible d'ajouter le fond de carte à t={h} : {e}")

        # D. Finitions
        ax.set_title(f"Répartition de la population à {h:02d}h00", fontsize=16, fontweight='bold')
        ax.axis('off')

        # Sauvegarde
        nom_fichier = f"heatmap_t{h:02d}.png"
        chemin_sauvegarde = dossier_frames / nom_fichier

        fig.savefig(chemin_sauvegarde, dpi=200, bbox_inches='tight')
        plt.close(fig)
        logger.info(f"Frame générée : {nom_fichier}")

    logger.info("Export des 24 frames terminé avec succès.")
    return dossier_frames