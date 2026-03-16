"""
Point d'entrée CLI du projet MOGEC.

Ce script ne porte aucune logique métier : il se contente de lire les
arguments de ligne de commande, de déléguer l'exécution au pipeline applicatif
et d'afficher un message synthétique de début/fin de traitement.
"""

import logging
import argparse

from src.pipeline import run_pipeline_to_export

logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')


def main():
    """
    Lance le pipeline complet à partir d'un fichier de configuration YAML.

    La commande attendue est typiquement :
    `python main.py --config config.yaml`
    """
    print("=== DÉMARRAGE DU PIPELINE MOGEC - BATZ-SUR-MER ===")
    parser = argparse.ArgumentParser(description="Pipeline de génération spatio-temporelle MOGEC")
    parser.add_argument("--config", default="config.yaml", help="Chemin vers le fichier de configuration YAML")
    args = parser.parse_args()

    fichier_final = run_pipeline_to_export(args.config)

    print(f"=== PIPELINE TERMINÉ. Fichier prêt : {fichier_final} ===")


if __name__ == "__main__":
    main()
