# 🌍 Open Earth Data Kit

**统一地球系统公开数据下载工具包** · **中文** | **[English](README_EN.md)**

> 把分散的气象、海洋、气候与环境数据链接、示例脚本和下载工具，收敛成一个可扩展的 CLI 平台：统一发现数据源、生成下载计划、执行下载任务、记录状态，并为后续新增数据源提供标准化入口。

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)
![Conda](https://img.shields.io/badge/Conda-ready-44A833?style=flat-square&logo=anaconda&logoColor=white)
![Catalog](https://img.shields.io/badge/Catalog-59_sources-0EA5E9?style=flat-square)
![Backend](https://img.shields.io/badge/Backend-Python%20%7C%20IDM%20%7C%20XDM-f97316?style=flat-square)
![Status](https://img.shields.io/badge/Status-platformizing-10B981?style=flat-square)

---

## ✦ 项目定位

本项目源自公开地球系统数据资源指南，覆盖气象、海洋、气候与环境数据源。随着数据源增加，继续堆脚本会带来几个问题：

| 问题 | 平台化后的处理方式 |
|---|---|
| 每个数据源一个脚本，参数不统一 | 用 `oedk` CLI 统一入口 |
| README 里有链接，但代码无法识别 | 用 `catalog/sources.json` 结构化维护 |
| 下载状态不可追踪 | 用 SQLite 记录任务、文件和失败原因 |
| 新数据源越来越多 | 优先新增 catalog 条目，必要时新增协议适配器 |
| IDM/XDM 和 Python 下载混杂 | 抽象成可选择的下载后端 |

---

## ✦ 平台架构

```text
┌────────────────────┐
│      oedk CLI      │
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
│ SQLite Task State   │  .oedk/state.db
└────────────────────┘
```

---

## ✦ 安装

推荐使用 conda 独立环境：

```bash
conda env create -f environment.yml
conda activate oedk
```

如果你已经在当前 conda 环境中工作：

```bash
pip install -e .
```

可选功能：

```bash
pip install -e ".[yaml]"      # 兼容 YAML catalog
pip install -e ".[opendap]"   # 后续 OPeNDAP 导出能力
pip install -e ".[icechunk]"  # 后续 Icechunk/Zarr 导出能力
```

---

## ✦ 快速开始

列出可直连数据源：

```bash
oedk list --support downloadable
```

查看某个数据源：

```bash
oedk info era5_ncar_sfc
```

生成下载计划：

```bash
oedk plan gfs_aws_archive \
  --prefix gfs.20240101/00/atmos/ \
  --extensions .grib2 \
  --max-files 5
```

执行下载：

```bash
oedk download gfs_aws_archive \
  --prefix gfs.20240101/00/atmos/ \
  --extensions .grib2 \
  --max-files 5 \
  -o ./downloads/gfs
```

对目录型 HTTP 数据源，可以临时覆盖入口目录：

```bash
oedk plan ecmwf_open_ifs \
  --endpoint-url https://data.ecmwf.int/forecasts/20240601/00z/ifs/0p25/oper/ \
  --extensions .grib2 \
  --max-files 10
```

提交到外部下载器：

```bash
oedk download ecmwf_open_ifs \
  --endpoint-url https://data.ecmwf.int/forecasts/20240601/00z/ifs/0p25/oper/ \
  --backend external \
  --tool xdm \
  --extensions .grib2 \
  --max-files 10
```

查看任务：

```bash
oedk tasks list
oedk tasks show 1
```

### Zarr/Icechunk 性能说明

Planette ERA5 的月平均数据远端 chunk 通常是 `time=12, lat=721, lon=1440`。这意味着即使你只裁剪一个很小的经纬度范围，也可能需要从远端读取完整空间 chunk；小区域测试不一定比中等区域快。

建议：

- 下载较大时间段或较完整空间范围时，Zarr/Icechunk 的体验更合理。
- 用 `--workers 8` 或更高值提高并发，但不要无限调大，避免远端限速。
- 优先用 `--format zarr` 保存大数据；需要兼容传统工具时再导出 NetCDF。
- 真实下载时直接调用 conda 环境 Python，可看到实时日志：`/home/wait4x/miniconda3/envs/climate/bin/python -m oedk ...`。

---

## ✦ 当前已实现的真实下载能力

这里的“已实现”分为两类：普通文件下载由 Python/IDM/XDM 后端执行；导出型数据源由适配器直接调用 `xarray` 或 `icechunk` 导出。

| 协议 | 适配器 | 已接入 source id | 说明 |
|---|---|---|---|
| HTTP 目录 | `http_index` | `ecmwf_open_ifs`, `ecmwf_open_aifs`, `gfs_noaa_nomads`, `gefs_noaa_nomads`, `dwd_icon_open`, `aigfs_noaa_nomads`, `aigefs_noaa_nomads`, `cru_ts` | 适合页面中直接包含文件链接的目录；可用 `--endpoint-url` 指向具体日期/时次目录。 |
| S3 XML | `s3_xml` | `ecmwf_forecasts_s3`, `gfs_aws_archive`, `gefs_aws_archive`, `noaa_oar_mlwp`, `era5_ncar_sfc`, `era5_ncar_pl` | 适合公开 S3 bucket；通常需要用 `--prefix` 指向具体产品目录。 |
| OPeNDAP 导出 | `opendap_xarray` | 暂无活跃可用条目 | 适配器已实现，但 NOAA NOMADS GFS OPeNDAP 已退役；保留能力用于其他仍可用的 OPeNDAP 服务。 |
| Icechunk/Zarr 导出 | `icechunk_zarr` | `era5_planette` | 支持 Planette ERA5 变量、频率、网格、时间和区域导出 NetCDF/Zarr；支持 Dask 进度条和 `--workers` 并发参数。 |
| 外部下载 | `external` backend | 上述 HTTP/S3 文件型来源 | 生成文件 URL 后可提交给 IDM/XDM。 |

账号型和手动型数据源目前已接入 catalog，但不会伪装成可直接下载：

| 类型 | source id 示例 | 当前能力 | 下一步 |
|---|---|---|---|
| 已退役 OPeNDAP | `gfs_opendap_0p25`, `gfs_opendap_0p25_1hr`, `gfs_opendap_0p50`, `gfs_opendap_1p00` | NOAA NOMADS 返回 OpenDAP retired 页面，catalog 标记为 `manual` | 使用 GFS/GEFS HTTP 或 S3 GRIB 来源替代 |
| 账号/门户型 | `era5_land_cds`, `merra2_nasa`, `jra3q_dias`, `cmems`, `airnow` 等 | 记录凭据要求，`doctor` 可检查环境变量 | 按 API/认证方式逐步新增专用适配器 |
| 手动型 | Google Cloud Console、NOAA CLASS、部分网页门户 | 统一收录、说明访问限制 | 能自动化时再升级支持级别 |

---

## ✦ OPeNDAP 脚本说明

[sources/download_from_opendap.py](sources/download_from_opendap.py) 已改为通用 OPeNDAP 子集下载器。注意：NOAA NOMADS GFS OPeNDAP 已退役，旧示例 URL 不能再使用；脚本会在下载前检测 `.dds` 元数据并阻止退役/HTML 页面继续进入 xarray。

查看数据集变量：

```bash
python sources/download_from_opendap.py \
  --url "可用的具体 OPeNDAP 数据集 URL" \
  --list
```

下载变量、时间和区域子集：

```bash
python sources/download_from_opendap.py \
  --url "可用的具体 OPeNDAP 数据集 URL" \
  -v tmp2m \
  --time-range 2024-01-01 2024-01-02 \
  --region 100 120 20 40 \
  -o subset.nc
```

如果返回 `HTTP 301 while fetching DDS metadata` 或 `server returned HTML retirement/error HTML`，说明该 URL 不是可用的 OPeNDAP 数据集端点，应改用对应的 HTTP/S3/官方 API 数据源。

---

## ✦ 数据源目录

当前 catalog 包含 59 个数据源条目，覆盖：

| 类别 | 示例 |
|---|---|
| 数值预报 | ECMWF IFS/AIFS, GFS, GEFS, DWD ICON |
| 大模型预报 | AIGFS, AIGEFS, NOAA OAR MLWP |
| 再分析 | ERA5, ERA5-Land, FNL, JRA-3Q, MERRA-2 |
| 气候数据 | CRU TS, GPCC |
| 实况观测 | ASOS/AWOS, SYNOP, MADIS, IGRA, AMDAR |
| 卫星/雷达 | Himawari, GOES, FY-4, JPSS, GPM, NEXRAD |
| 海洋/空气质量 | Argo, HYCOM, CMEMS, AirNow, OpenAQ, CAMS |

支持级别：

| 级别 | 含义 |
|---|---|
| `downloadable` | 平台可发现文件并执行普通文件下载，或已经有明确可执行适配器。 |
| `auth_required` | 需要账号、token、API key 或申请权限。 |
| `manual` | 需要网页登录、云控制台、许可确认或特殊人工流程。 |

---

## ✦ 开发与校验

```bash
python -m pytest
python -m oedk catalog validate
python -m oedk doctor
```

新增数据源时优先修改 `catalog/sources.json`，不要直接新增独立脚本。只有现有协议无法覆盖时，才新增适配器。

更多规范见 [CONTRIBUTING.md](CONTRIBUTING.md)。

---

## ✦ Roadmap

- [ ] 为其他仍可用的 OPeNDAP 服务增加示例 catalog。
- [ ] 为 Planette ERA5 增加单位转换和数据校验。
- [ ] 为 S3 适配器增加分页、递归目录和更好的 prefix 模板。
- [ ] 为 ECMWF/NOAA 实时数据增加“自动选择最新可用时次”。
- [ ] 增加 catalog 覆盖率报告和链接健康检查。
- [ ] 在 CLI 稳定后扩展 Web/API 平台。
