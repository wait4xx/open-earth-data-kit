from oedk.cli import main


def test_list_command_runs(capsys):
    assert main(["list", "--support", "downloadable"]) == 0

    out = capsys.readouterr().out
    assert "era5_planette" in out


def test_info_command_runs(capsys):
    assert main(["info", "era5_planette"]) == 0

    out = capsys.readouterr().out
    assert "Planette ERA5" in out


def test_catalog_validate_runs(capsys):
    assert main(["catalog", "validate"]) == 0

    out = capsys.readouterr().out
    assert "catalog ok" in out
