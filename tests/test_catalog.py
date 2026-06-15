from meteo_download.catalog import load_sources, validate_sources


def test_catalog_is_valid():
    sources = load_sources()

    assert len(sources) >= 50
    assert validate_sources(sources) == []


def test_catalog_has_expected_core_sources():
    ids = {source.id for source in load_sources()}

    assert "era5_planette" in ids
    assert "era5_ncar_sfc" in ids
    assert "ecmwf_open_ifs" in ids
    assert "gfs_opendap_0p25" in ids
    assert "noaa_oar_mlwp" in ids
