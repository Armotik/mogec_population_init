"""
Visualisation statique de la population à une heure donnée.

Le cas d'usage principal de ce module est la production d'une carte de densité
sur `pop_h0`, utile pour un contrôle visuel rapide du résultat exporté.
"""

import logging
from pathlib import Path

import geopandas as gpd
import matplotlib.colors as colors
import matplotlib.pyplot as plt
import contextily as ctx
from contextily import add_basemap

logger = logging.getLogger(__name__)


def generer_heatmap_batz(gpkg_path: str, output_path: str):
    """
    Génère une carte de chaleur (heatmap) de la population ventilée à t=0.

    Parameters
    ----------
    gpkg_path:
        Chemin du GeoPackage exporté.
    output_path:
        Chemin de l'image PNG à produire.
    """
    path = Path(gpkg_path)
    if not path.exists():
        raise FileNotFoundError(f"Fichier export introuvable : {gpkg_path}")

    logger.info(f"Chargement des donnees finales depuis {path.name}...")
    gdf = gpd.read_file(path)
    reference_hour = int(gdf["reference_hour"].dropna().iloc[0]) if "reference_hour" in gdf.columns and not gdf["reference_hour"].dropna().empty else 0
    population_column = f"pop_h{reference_hour}"
    if population_column not in gdf.columns:
        population_column = "pop_h0"
        reference_hour = 0

    gdf_pop = gdf[gdf[population_column] > 0].copy()
    if gdf_pop.empty:
        raise ValueError(f"Aucun batiment occupe a h{reference_hour:02d} n'a ete trouve pour la heatmap.")

    safe_area = gdf_pop.geometry.area.clip(lower=1.0)
    gdf_pop["densite_visu"] = (gdf_pop[population_column] / safe_area) * 1000.0

    logger.info("Generation de la heatmap...")

    fig, ax = plt.subplots(figsize=(14, 11))
    ax.set_facecolor("#f8fafc")

    gdf.plot(
        ax=ax,
        color="#d6d3d1",
        edgecolor="#f8fafc",
        linewidth=0.15,
        alpha=0.55,
        zorder=1,
    )

    lower_bound = max(float(gdf_pop["densite_visu"].quantile(0.05)), 0.1)
    upper_bound = max(float(gdf_pop["densite_visu"].quantile(0.98)), lower_bound * 1.5)

    gdf_pop.plot(
        ax=ax,
        column="densite_visu",
        cmap="YlOrRd",
        norm=colors.LogNorm(vmin=lower_bound, vmax=upper_bound),
        legend=True,
        legend_kwds={
            "label": f"Densite relative a h{reference_hour:02d} (agents / 1000 m², echelle log)",
            "orientation": "vertical",
            "shrink": 0.78,
        },
        alpha=0.92,
        edgecolor="#7f1d1d",
        linewidth=0.12,
        zorder=3,
    )

    try:
        add_basemap(ax, crs=gdf_pop.crs.to_string(), source=ctx.providers.CartoDB.PositronNoLabels, zoom=15, alpha=0.7)
        logger.info("Fond de carte contextuel ajoute.")
    except Exception as e:
        logger.warning(f"Impossible d'ajouter le fond de carte : {e}. La carte sera generee sur fond clair.")

    total_population = int(gdf_pop[population_column].sum())
    occupied_buildings = int((gdf[population_column].fillna(0) > 0).sum())
    ax.text(
        0.02,
        0.02,
        f"T0 = h{reference_hour:02d}: {total_population} agents | {occupied_buildings} batiments occupes",
        transform=ax.transAxes,
        fontsize=10,
        color="#0f172a",
        bbox={"boxstyle": "round,pad=0.35", "facecolor": "white", "edgecolor": "#cbd5e1", "alpha": 0.95},
        zorder=10,
    )
    ax.set_title(f"Batz-sur-Mer : densite de population a T0 (h{reference_hour:02d})", fontsize=17, fontweight="bold", pad=14)
    ax.axis("off")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    logger.info(f"Heatmap sauvegardee avec succes : {output_path}")
    return output_path
