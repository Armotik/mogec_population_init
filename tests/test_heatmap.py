import pytest
from pathlib import Path
from src.visualization.heatmap import generer_heatmap_batz


def test_generer_heatmap(config):
    """Test qui génère la carte de chaleur post-export."""
    path_export = config['data_paths']['output']['final_export']
    path_heatmap = Path(config['data_paths']['output']['interim_dir']) / "heatmap_batz.png"

    assert Path(path_export).exists()

    path_generee = generer_heatmap_batz(path_export, path_heatmap)

    assert path_generee.exists()
    print(f"\n[Heatmap OK] La carte est générée ici : {path_generee}")