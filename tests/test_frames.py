import pytest
from pathlib import Path
from src.visualization.temporal_heatmap import exporter_frames_24h


def test_generation_frames(config):
    fichier_export = config['data_paths']['output']['final_export']
    assert Path(fichier_export).exists(), "Le fichier final .gpkg est introuvable."

    # On définit le dossier où les 24 images vont atterrir
    dossier_sortie = Path(config['data_paths']['output']['interim_dir']) / "frames_24h"

    exporter_frames_24h(fichier_export, str(dossier_sortie))

    assert dossier_sortie.exists()
    assert len(list(dossier_sortie.glob("*.png"))) == 24

    print(f"\n[SUCCÈS] Les 24 cartes ont été générées dans : {dossier_sortie}")