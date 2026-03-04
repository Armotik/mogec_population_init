

def test_get_study_area_boundary(boundary_poly, config):
    """Vérifie que le polygone de la commune est bien chargé et projeté."""
    target_crs = config['project']['crs_epsg']

    assert not boundary_poly.empty
    assert boundary_poly.crs.to_epsg() == target_crs
    # Vérifie que c'est bien un polygone (ou multipolygone)
    assert boundary_poly.geometry.iloc[0].geom_type in ['Polygon', 'MultiPolygon']


def test_load_bd_topo_with_mask(bati_raw, config):
    """Vérifie que le chargement via le masque (avec buffer) fonctionne."""
    buffer_m = config['study_area'].get('buffer_m', 0)

    assert len(bati_raw) > 0
    print(f"\n[Loader] {len(bati_raw)} bâtiments extraits (Buffer: {buffer_m}m).")