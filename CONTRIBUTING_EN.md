# Contributing Guide

**[中文](CONTRIBUTING.md)** | **English**

This project now prioritizes the unified download platform instead of adding more independent large scripts. Before contributing code, check whether the source can be represented by the catalog. Add adapter code only when a protocol or authentication workflow cannot be reused.

## Add A Data Source

Add an entry to `catalog/sources.json`:

```json
{
  "id": "provider_dataset",
  "name": "Readable dataset name",
  "category": "forecast",
  "provider": "Provider",
  "protocol": "http_index",
  "support_level": "downloadable",
  "endpoint": "https://example.com/data/",
  "formats": ["grib2"],
  "coverage": "time coverage",
  "defaults": {
    "file_extensions": [".grib2"],
    "max_files": 100
  }
}
```

Rules:

- `id` must be unique and use lowercase letters, digits, and underscores.
- `support_level` must be `downloadable`, `auth_required`, or `manual`.
- Sources requiring accounts or tokens must declare `required_credentials`.
- Never commit real accounts, tokens, cookies, or sessions.

## Add An Adapter

Add an adapter only when:

- Existing `http_index`, `s3_xml`, `opendap_xarray`, `icechunk_zarr`, and `manual_auth` cannot describe the source.
- The source needs special discovery, pagination, signed URLs, authentication handshakes, or export logic.

Adapters implement:

```python
class Adapter:
    def validate_config(self, request):
        return []

    def plan(self, request):
        ...
```

After adding an adapter:

- Register it in `oedk/adapters/base.py`.
- Add at least one catalog example.
- Add unit tests.

## Tests

Run before submitting:

```bash
conda activate oedk  # or use your current conda environment
python -m pytest
python -m oedk catalog validate
python -m oedk list --support downloadable
```

Use mock responses for network behavior. Unit tests should not depend on live external services.

## Documentation

User-facing changes should update:

- `README.md`
- `README_EN.md`
- `CONTRIBUTING.md`
- `CONTRIBUTING_EN.md`

## Commit Messages

Recommended examples:

- `feat: add new data source catalog entry`
- `feat: add s3 pagination support`
- `fix: handle empty http index pages`
- `docs: update catalog contribution guide`
