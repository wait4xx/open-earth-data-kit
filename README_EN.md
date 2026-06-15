# 🌍 Open Earth Data Kit

**Unified Open Earth Data Access Toolkit** · **[中文](README.md)** | **English**

> Turn scattered meteorological, oceanographic, climate and environmental data links, examples, and one-off scripts into an extensible CLI platform for source discovery, download planning, task execution, and state tracking.

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)
![Conda](https://img.shields.io/badge/Conda-ready-44A833?style=flat-square&logo=anaconda&logoColor=white)
![Catalog](https://img.shields.io/badge/Catalog-59_sources-0EA5E9?style=flat-square)
![Backend](https://img.shields.io/badge/Backend-Python%20%7C%20IDM%20%7C%20XDM-f97316?style=flat-square)
![Status](https://img.shields.io/badge/Status-platformizing-10B981?style=flat-square)

---

## ✦ What This Project Is

This project grew out of a public Earth-system data guide covering meteorological, oceanographic, climate and environmental data sources. As more data sources are added, independent scripts become hard to maintain.

| Problem | Platform Approach |
|---|---|
| One script per source, inconsistent parameters | A single `meteo` CLI |
| Links exist only in README | Structured `catalog/sources.json` |
| No task audit trail | SQLite task and file state |
| Growing source coverage | Add catalog entries first, adapters only when needed |
| Python/IDM/XDM logic mixed together | Selectable download backends |

---

## ✦ Architecture

```text
┌────────────────────┐
│      meteo CLI      │
│ list/info/plan/...  │
└─────────┬──────────┘
          │
┌─────────▼──────────┐
│  Data Source Catalog│  catalog/sources.json
│  id/provider/rules  │
└─────────┬──────────┘
          │
┌─────────▼──────────┐
│ Protocol Adapters   │  http_index / s3_xml / opendap / zarr / manual
└─────────┬──────────┘
          │
┌─────────▼──────────┐
│ Download Backends   │  Python downloader / IDM / XDM
└─────────┬──────────┘
          │
┌─────────▼──────────┐
│ SQLite Task State   │  .meteo-download/state.db
└────────────────────┘
```

---

## ✦ Installation

Recommended conda environment:

```bash
conda env create -f environment.yml
conda activate meteo-download
```

If you are already working inside your current conda environment:

```bash
pip install -e .
```

Optional extras:

```bash
pip install -e ".[yaml]"
pip install -e ".[opendap]"
pip install -e ".[icechunk]"
```

---

## ✦ Quick Start

List directly downloadable sources:

```bash
meteo list --support downloadable
```

Show source details:

```bash
meteo info era5_ncar_sfc
```

Create a plan:

```bash
meteo plan gfs_aws_archive \
  --prefix gfs.20240101/00/atmos/ \
  --extensions .grib2 \
  --max-files 5
```

Download:

```bash
meteo download gfs_aws_archive \
  --prefix gfs.20240101/00/atmos/ \
  --extensions .grib2 \
  --max-files 5 \
  -o ./downloads/gfs
```

Override a directory endpoint for HTTP sources:

```bash
meteo plan ecmwf_open_ifs \
  --endpoint-url https://data.ecmwf.int/forecasts/20240601/00z/ifs/0p25/oper/ \
  --extensions .grib2 \
  --max-files 10
```

Submit files to an external downloader:

```bash
meteo download ecmwf_open_ifs \
  --endpoint-url https://data.ecmwf.int/forecasts/20240601/00z/ifs/0p25/oper/ \
  --backend external \
  --tool xdm \
  --extensions .grib2 \
  --max-files 10
```

Inspect tasks:

```bash
meteo tasks list
meteo tasks show 1
```

### Zarr/Icechunk Performance Notes

Planette ERA5 monthly data commonly uses remote chunks like `time=12, lat=721, lon=1440`. A tiny spatial subset can still trigger a full spatial chunk read, so small-area tests are not necessarily fast.

Recommendations:

- Zarr/Icechunk is more useful for larger time ranges or broader spatial domains.
- Use `--workers 8` or higher for more concurrency, but avoid unbounded values because remote services may throttle.
- Prefer `--format zarr` for large outputs; use NetCDF when downstream tools require it.
- For real-time logs in conda, call the environment Python directly: `/home/wait4x/miniconda3/envs/climate/bin/python -m meteo_download ...`.

---

## ✦ Implemented Download Capabilities

“Implemented” has two meanings here: regular files are handled by Python/IDM/XDM backends, while export-oriented datasets are executed by protocol adapters through `xarray` or `icechunk`.

| Protocol | Adapter | Source IDs | Notes |
|---|---|---|---|
| HTTP index | `http_index` | `ecmwf_open_ifs`, `ecmwf_open_aifs`, `gfs_noaa_nomads`, `gefs_noaa_nomads`, `dwd_icon_open`, `aigfs_noaa_nomads`, `aigefs_noaa_nomads`, `cru_ts` | Works for pages that directly expose file links. Use `--endpoint-url` for concrete date/cycle directories. |
| S3 XML | `s3_xml` | `ecmwf_forecasts_s3`, `gfs_aws_archive`, `gefs_aws_archive`, `noaa_oar_mlwp`, `era5_ncar_sfc`, `era5_ncar_pl` | Works with public S3 buckets. Use `--prefix` for product directories. |
| OPeNDAP export | `opendap_xarray` | No active catalog entry yet | The adapter is implemented, but NOAA NOMADS GFS OPeNDAP has been retired. The adapter remains available for other active OPeNDAP services. |
| Icechunk/Zarr export | `icechunk_zarr` | `era5_planette` | Exports Planette ERA5 variables/frequencies/grids/time/regions to NetCDF or Zarr. Supports Dask progress and `--workers`. |
| External backend | `external` | Same HTTP/S3 file-based sources | Submits planned file URLs to IDM or XDM. |

Authenticated and manual sources are cataloged but not presented as direct downloads:

| Type | Example Source IDs | Current Capability | Next Step |
|---|---|---|---|
| Retired OPeNDAP | `gfs_opendap_0p25`, `gfs_opendap_0p25_1hr`, `gfs_opendap_0p50`, `gfs_opendap_1p00` | NOAA NOMADS returns an OpenDAP retired page; catalog entries are marked `manual` | Use GFS/GEFS HTTP or S3 GRIB sources instead |
| Auth/API sources | `era5_land_cds`, `merra2_nasa`, `jra3q_dias`, `cmems`, `airnow` | Records credential requirements and supports environment checks | Add API-specific adapters |
| Manual portals | Google Cloud Console, NOAA CLASS, selected web portals | Cataloged with access notes | Upgrade when automation is practical |

---

## ✦ OPeNDAP Script

[sources/download_from_opendap.py](sources/download_from_opendap.py) is now a generic OPeNDAP subset downloader. NOAA NOMADS GFS OPeNDAP has been retired, so the old example URLs no longer work. The script checks `.dds` metadata first and stops early when the server returns retired/error HTML instead of real OPeNDAP metadata.

List dataset variables:

```bash
python sources/download_from_opendap.py \
  --url "concrete active OPeNDAP dataset URL" \
  --list
```

Download a variable/time/region subset:

```bash
python sources/download_from_opendap.py \
  --url "concrete active OPeNDAP dataset URL" \
  -v tmp2m \
  --time-range 2024-01-01 2024-01-02 \
  --region 100 120 20 40 \
  -o subset.nc
```

If the script reports `HTTP 301 while fetching DDS metadata` or `server returned HTML retirement/error HTML`, the URL is not a usable OPeNDAP dataset endpoint. Use the corresponding HTTP/S3/API source instead.

---

## ✦ Catalog Coverage

The catalog currently contains 59 source entries:

| Category | Examples |
|---|---|
| Forecast | ECMWF IFS/AIFS, GFS, GEFS, DWD ICON |
| AI forecast | AIGFS, AIGEFS, NOAA OAR MLWP |
| Reanalysis | ERA5, ERA5-Land, FNL, JRA-3Q, MERRA-2 |
| Climate | CRU TS, GPCC |
| Observations | ASOS/AWOS, SYNOP, MADIS, IGRA, AMDAR |
| Satellite/Radar | Himawari, GOES, FY-4, JPSS, GPM, NEXRAD |
| Ocean/Air Quality | Argo, HYCOM, CMEMS, AirNow, OpenAQ, CAMS |

Support levels:

| Level | Meaning |
|---|---|
| `downloadable` | The platform can discover files and execute regular file downloads, or has a clear executable adapter path. |
| `auth_required` | Requires account, token, API key, or access approval. |
| `manual` | Requires login portals, cloud consoles, license confirmation, or special manual workflows. |

---

## ✦ Development

```bash
python -m pytest
python -m meteo_download catalog validate
python -m meteo_download doctor
```

Add new data sources to `catalog/sources.json` first. Add a new adapter only when the existing protocols cannot cover the source.

See [CONTRIBUTING_EN.md](CONTRIBUTING_EN.md).

---

## ✦ Roadmap

- [ ] Add catalog examples for other active OPeNDAP services.
- [ ] Add unit conversion and validation for Planette ERA5.
- [ ] Add pagination, recursive discovery, and prefix templates to the S3 adapter.
- [ ] Add automatic latest-cycle selection for ECMWF/NOAA live data.
- [ ] Add catalog coverage reports and link health checks.
- [ ] Reuse the CLI core for future Web/API surfaces.
