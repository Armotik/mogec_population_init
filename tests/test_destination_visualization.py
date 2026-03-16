from pathlib import Path

import geopandas as gpd
from shapely.geometry import Polygon

from src.visualization.destination_flows import plot_destination_flows


def test_plot_destination_flows_creates_png(tmp_path):
    gdf = gpd.GeoDataFrame(
        {
            "building_id": ["B1", "B2", "B3"],
            "usage_1": ["Résidentiel", "Enseignement", "Commercial et services"],
            "households": [
                [
                    {
                        "household_id": "B1_hh1",
                        "members": [
                            {"member_id": "m1", "role": "scolaire", "destination_id": "B2"},
                            {"member_id": "m2", "role": "actif_local", "destination_id": "B3"},
                        ],
                    }
                ],
                [],
                [],
            ],
        },
        geometry=[
            Polygon([(0, 0), (0, 20), (20, 20), (20, 0)]),
            Polygon([(100, 0), (100, 20), (120, 20), (120, 0)]),
            Polygon([(0, 100), (0, 120), (20, 120), (20, 100)]),
        ],
        crs="EPSG:2154",
    )

    config = {
        "visualization": {
            "destination_flows": {
                "min_flow_count": 1,
                "top_destination_types": 4,
            }
        }
    }
    output = tmp_path / "flows.png"

    path = plot_destination_flows(gdf, str(output), config)

    assert path == output
    assert output.exists()
    assert output.stat().st_size > 0
