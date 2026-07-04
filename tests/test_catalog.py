from oedk.catalog import load_sources, validate_sources
from oedk.models import DataSource, Protocol, SupportLevel


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


def test_validate_sources_flags_unknown_adapter():
    src = DataSource(
        id="test_bad_adapter",
        name="Test",
        category="test",
        provider="test",
        protocol=Protocol.HTTP_INDEX,
        support_level=SupportLevel.DOWNLOADABLE,
        endpoint="https://example.com/",
        adapter="nonexistent_adapter",
    )

    errors = validate_sources([src])

    assert any("test_bad_adapter" in e for e in errors)
