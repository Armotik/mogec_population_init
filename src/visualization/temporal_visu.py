"""
Graphique de synthèse du cycle journalier.

Le module fournit une visualisation non spatiale, utile pour vérifier la
"respiration urbaine" du modèle sans ouvrir de SIG.
"""

import logging
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd

logger = logging.getLogger(__name__)


def plot_respiration_urbaine(df_horaire: gpd.GeoDataFrame, output_path: str):
    """
    Génère un graphique linéaire montrant l'évolution de la population
    présente dans les bâtiments de la commune de t=0 à t=23.

    Parameters
    ----------
    df_horaire:
        GeoDataFrame final contenant les colonnes `pop_h*`.
    output_path:
        Chemin de l'image PNG à générer.
    """
    logger.info("Generation du graphique de respiration urbaine...")

    colonnes_heures = [f"pop_h{h}" for h in range(24) if f"pop_h{h}" in df_horaire.columns]
    if not colonnes_heures:
        raise ValueError("Aucune colonne pop_h* n'a ete trouvee pour la visualisation temporelle.")

    population_totale_par_heure = df_horaire[colonnes_heures].sum()
    serie = pd.DataFrame(
        {
            "hour": [int(col.replace("pop_h", "")) for col in colonnes_heures],
            "population": population_totale_par_heure.values.astype(float),
        }
    )

    fig, ax = plt.subplots(figsize=(12, 7))
    ax.set_facecolor("#f8fafc")
    ax.plot(serie["hour"], serie["population"], marker="o", linestyle="-", color="#1f4e79", linewidth=2.7)
    ax.fill_between(serie["hour"], serie["population"], color="#93c5fd", alpha=0.28)

    pic = serie.loc[serie["population"].idxmax()]
    creux = serie.loc[serie["population"].idxmin()]
    amplitude = int(pic["population"] - creux["population"])
    moyenne = float(serie["population"].mean())
    variation_pct = (amplitude / max(moyenne, 1.0)) * 100.0

    ax.scatter([pic["hour"]], [pic["population"]], color="#1d8348", s=80, zorder=5)
    ax.scatter([creux["hour"]], [creux["population"]], color="#b03a2e", s=80, zorder=5)
    ax.annotate(
        f"Pic h{int(pic['hour']):02d}: {int(pic['population'])}",
        xy=(pic["hour"], pic["population"]),
        xytext=(10, 12),
        textcoords="offset points",
        fontsize=10,
        color="#1d8348",
        fontweight="bold",
    )
    ax.annotate(
        f"Creux h{int(creux['hour']):02d}: {int(creux['population'])}",
        xy=(creux["hour"], creux["population"]),
        xytext=(10, -18),
        textcoords="offset points",
        fontsize=10,
        color="#b03a2e",
        fontweight="bold",
    )

    texte_explicatif = (
        f"Amplitude: {amplitude} agents\n"
        f"Moyenne journaliere: {moyenne:.0f}\n"
        f"Variation relative: {variation_pct:.1f} %"
    )
    ax.text(
        0.02,
        0.95,
        texte_explicatif,
        transform=ax.transAxes,
        fontsize=10,
        verticalalignment="top",
        bbox={"boxstyle": "round,pad=0.35", "facecolor": "white", "edgecolor": "#cbd5e1", "alpha": 0.95},
    )

    ax.set_title("Cycle journalier de population presente", fontsize=15, fontweight="bold", pad=14)
    ax.set_xlabel("Heure de la journee", fontsize=12)
    ax.set_ylabel("Population presente dans la commune", fontsize=12)
    ax.set_xticks(range(0, 24, 2))
    ax.grid(True, linestyle="--", alpha=0.45)

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)

    logger.info(f"Graphique sauvegarde : {path}")
    return path
