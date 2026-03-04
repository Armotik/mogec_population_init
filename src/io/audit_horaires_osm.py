import osmnx as ox
import pandas as pd
import logging
from pathlib import Path

# Configuration du logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def auditer_horaires_osmnx(commune_name="Batz-sur-Mer, France",
                           output_csv_path="data/01_raw/audit_restaurants_batz.csv"):
    """
    Télécharge les lieux de restauration via OSMnx (plus robuste que l'API brute)
    et évalue la complétude des horaires d'ouverture.
    """
    logger.info(f"Requête OSMnx pour {commune_name} (gestion auto des timeouts/cache)...")

    # On définit les tags qui nous intéressent
    tags = {'amenity': ['restaurant', 'cafe', 'bar', 'fast_food']}

    try:
        # features_from_place télécharge les données et renvoie directement un GeoDataFrame
        gdf = ox.features_from_place(commune_name, tags=tags)
    except Exception as e:
        logger.error(f"Échec de la récupération des données : {e}")
        return None

    logger.info(f"{len(gdf)} établissements trouvés.")

    # Nettoyage et préparation du DataFrame
    lignes = []

    # OSMnx renvoie un index multiple (element_type, osmid). On itère dessus.
    for index, row in gdf.iterrows():
        element_type, osmid = index

        nom = row.get('name', 'Inconnu')
        if pd.isna(nom): nom = 'Inconnu'

        type_amenity = row.get('amenity', 'Inconnu')

        # Vérification de la présence de la colonne opening_hours
        horaires = row.get('opening_hours', None) if 'opening_hours' in gdf.columns else None
        if pd.isna(horaires): horaires = None

        statut_donnee = "Exacte (OSM)" if horaires else "À imputer (Profil Type)"

        # Récupération des coordonnées (centroid pour les polygones, géométrie pour les points)
        centroid = row.geometry.centroid
        lat, lon = centroid.y, centroid.x

        lignes.append({
            'osm_id': f"{element_type}/{osmid}",
            'nom': nom,
            'type': type_amenity,
            'opening_hours_brut': horaires,
            'statut_donnee': statut_donnee,
            'lat': lat,
            'lon': lon
        })

    df = pd.DataFrame(lignes)

    # Statistiques de complétude pour ton rapport
    taux_completude = (df['opening_hours_brut'].notna().sum() / len(df)) * 100
    logger.info(f"Taux de complétude du tag 'opening_hours' : {taux_completude:.1f}%")

    if taux_completude < 30:
        logger.warning(
            "La donnée est insuffisante pour une modélisation purement déterministe. Modèle probabiliste (imputation) recommandé.")

    racine_projet = Path(__file__).resolve().parents[2]
    chemin_absolu = racine_projet / output_csv_path

    # Sauvegarde
    chemin_absolu.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(chemin_absolu, index=False, sep=';', encoding='utf-8')

    logger.info(f"Audit sauvegardé dans : {chemin_absolu}")
    return df


if __name__ == "__main__":
    df_resultat = auditer_horaires_osmnx()

    if df_resultat is not None:
        print("\n--- APERÇU DES DONNÉES OSM ---")
        print(df_resultat[['nom', 'type', 'opening_hours_brut', 'statut_donnee']].head(10))