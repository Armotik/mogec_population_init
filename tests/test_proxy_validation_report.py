from src.visualization.proxy_validation_report import proxy_metadata_table


def test_proxy_metadata_table_exposes_sources_and_reference_curve():
    config = {
        "proxy_validation": {
            "temporal_proxies": [
                {
                    "proxy_id": "proxy_test",
                    "label": "Proxy test",
                    "metric": "role_state_share",
                    "role": "actif_navetteur",
                    "state": "exterieur",
                    "comparison_normalization": "none",
                    "reference_curve": [0.0] * 24,
                    "evidence": {
                        "formula": "Part_proxy(t)",
                        "source_name": "Source test",
                        "source_url": "https://example.org/source",
                        "source_url_secondary": "https://example.org/source-2",
                        "confidence": "medium",
                        "temporal_scope": "Jour type",
                        "spatial_scope": "Zone test",
                    },
                }
            ]
        }
    }

    table = proxy_metadata_table(config)

    assert len(table) == 1
    assert table.iloc[0]["proxy_id"] == "proxy_test"
    assert table.iloc[0]["source_name"] == "Source test"
    assert table.iloc[0]["source_url"] == "https://example.org/source"
    assert "h0:0.00" in table.iloc[0]["reference_curve"]
