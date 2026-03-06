import logging
from pathlib import Path
import geopandas as gpd
import matplotlib.pyplot as plt
from contextily import add_basemap
import matplotlib.colors as colors
import contextily as ctx

logger = logging.getLogger(__name__)


def generer_heatmap_batz(gpkg_path: str, output_path: str):
    """
    Génère une carte de chaleur (heatmap) de la population ventilée à t=0.
    """
    path = Path(gpkg_path)
    if not path.exists():
        raise FileNotFoundError(f"Fichier export introuvable : {gpkg_path}")

    logger.info(f"Chargement des données finales depuis {path.name}...")
    # On ne charge que les bâtiments habités pour la clarté de la carte
    gdf = gpd.read_file(path)
    gdf_pop = gdf[gdf['pop_h0'] > 0].copy()

    # Calcul de la densité pour la couleur (agents / m2 de sol)
    # L'unité est petite, on multiplie pour avoir une échelle lisible
    gdf_pop['densite_visu'] = (gdf_pop['pop_h0'] / gdf_pop.geometry.area) * 1000

    logger.info("Génération de la heatmap...")

    # Création de la figure
    fig, ax = plt.subplots(figsize=(12, 10))

    # Paramétrage de la carte
    # On utilise une échelle logarithmique car les densités varient énormément
    plot = gdf_pop.plot(
        ax=ax,
        column='densite_visu',
        cmap='OrRd',  # Rouge/Orange
        norm=colors.LogNorm(vmin=gdf_pop['densite_visu'].min(), vmax=gdf_pop['densite_visu'].max()),
        legend=True,
        legend_kwds={'label': "Densité relative (LogScale)", 'orientation': "vertical", 'shrink': 0.8},
        alpha=0.8
    )

    # Ajout d'un fond de carte (OpenStreetMap) pour se repérer
    # Contextily s'occupe de la reprojection automatique en WebMercator
    try:
        add_basemap(ax, crs=gdf_pop.crs.to_string(), source=ctx.providers.Esri.WorldImagery, zoom=15)
        logger.info("Fond de carte OSM ajouté.")
    except Exception as e:
        logger.warning(f"Impossible d'ajouter le fond de carte : {e}. La carte sera générée sur fond blanc.")

    # Finition
    ax.set_title("Batz-sur-Mer (Xynthia t=0) : Carte de densité de la population", fontsize=16)
    ax.axis('off')  # On cache les axes (Lambert93) pour un rendu "pro"

    # Sauvegarde
    fig.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close(fig)
    logger.info(f"Heatmap sauvegardée avec succès : {output_path}")
    return output_path