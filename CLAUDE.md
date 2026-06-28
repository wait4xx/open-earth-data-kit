# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`open-earth-data-kit` is a zero-dependency Python CLI (`oedk`) for discovering, planning, and executing downloads of public Earth-system data (meteorology, oceanography, climate, environment). It turns what used to be per-source scripts into a catalog-driven platform.

## Commands

```bash
# Setup
conda env create -f environment.yml && conda activate oedk   # or: pip install -e .
pip install -e ".[icechunk]"   # optional: enables Icechunk/Zarr (era5_planette)
pip install -e ".[opendap]"    # optional: enables OPeNDAP/xarray export
pip install -e ".[yaml]"       # optional: YAML catalog support

# Test & validate
python -m pytest                              # all tests
python -m pytest tests/test_catalog.py -k "valid"   # single test
python -m oedk catalog validate     # check sources.json integrity
python -m oedk doctor               # check local env / credentials

# CLI usage (entry point: oedk.cli:main)
oedk list --support downloadable
oedk info <source_id>
oedk plan <source_id> --prefix ... --extensions .grib2 --max-files 5
oedk download <source_id> ... -o ./downloads
oedk tasks list / oedk tasks show <id>
```

All commands in this project run under the `climate` conda env interpreter (`/home/wait4x/miniconda3/envs/climate/bin/python`); the base env does not have pytest.

There is no lint/typecheck tooling configured; `pyproject.toml` only sets pytest paths. The core package runs on Python ≥3.10.

## Architecture

The flow for every download is: **CLI → Catalog → Adapter → Backend → State**, each layer a swappable abstraction.

```
oedk/cli.py        argparse dispatcher; plan/download/tasks/catalog/doctor commands
catalog/sources.json         structured metadata for all 59 data sources (the source of truth)
oedk/models.py     frozen dataclasses: DataSource, DownloadRequest, DownloadPlan, PlannedFile
oedk/catalog.py    loads JSON or YAML catalog files, validates, finds by id
oedk/adapters/     protocol-specific discovery/export (the Adapter interface)
oedk/backends.py   PythonDownloadBackend (stdlib urllib, resumable) + ExternalToolBackend (IDM/XDM)
oedk/state.py      SQLite StateStore at .oedk/state.db
```

**The Adapter interface** (`adapters/base.py`) is the central extension point. Every adapter implements `plan(request) -> DownloadPlan` (required). Export-oriented adapters also implement `execute(plan, store, task_id)` (optional). Adapters are registered by name in `adapter_for()` in `adapters/base.py` and instantiated lazily (imported only when used).

Five adapters exist: `http_index` (scrape `<a href>` from directory pages), `s3_xml` (ListObjectsV2 XML parsing), `opendap_xarray` (export via xarray), `icechunk_zarr` (export Planette ERA5 via icechunk/xarray), `manual_auth` (records credential requirements only).

**The "virtual" file convention** (`PlannedFile.metadata["virtual"]`) distinguishes two download kinds. Regular files are fetched by a Backend. Virtual files are placeholders for export datasets that the adapter must materialize itself — `cmd_download` checks this flag and calls `adapter.execute()` instead of a backend.

**Catalog-first principle.** New data sources go into `catalog/sources.json`, not new scripts. A `DataSource` maps `protocol` → adapter name (`adapter` field defaults to the protocol value if omitted). Add a new adapter only when no existing protocol can express the source. The `sources/` directory holds legacy standalone scripts that predate the platform — they are reference implementations, not the canonical path.

## Key design constraints

- **Zero core runtime dependencies.** `pyproject.toml` lists `dependencies = []`. All heavy libraries (xarray, icechunk, zarr, netCDF4, dask, PyYAML) are optional extras, imported lazily inside the adapter methods that need them. Do not add imports to module top level.
- **Tests must not hit the network.** Use mocks; `tests/` covers catalog validation, CLI smoke commands, and state store.
- **Bilingual docs must stay in sync.** `README.md`/`README_EN.md` and `CONTRIBUTING.md`/`CONTRIBUTING_EN.md` are parallel translations — update both when changing user-facing behavior.
- **Catalog validation rules** (`catalog.validate_sources`): source ids must be unique; `downloadable` sources must not list `required_credentials`; adapter field must not be empty. The test suite asserts the catalog passes these.

## Conventions

- Support levels: `downloadable`, `auth_required`, `manual`.
- Commit message style: conventional commits (`feat:`, `fix:`, `docs:`).
- State DB and downloads are gitignored (`.oedk/`, `downloads/`).
