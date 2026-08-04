# 气候数据下载器

面向 Windows 的图形化气候数据下载与整理工具，支持 NEX-GDDP-CMIP6、CMIP6、CORDEX 和 NASA POWER；ERA5 / ERA5-Land 当前保留入口，后续可接入用户自己的 Copernicus CDS 凭据。

## 当前可交付形态

### 1. 免 Python 便携包（推荐销售给普通用户）

运行：

```powershell
.\Build_Portable_App.ps1
```

生成：

```text
release\ClimateDataDownloader_0.1.0_portable_YYYYMMDD_HHMMSS.zip
```

用户解压后直接双击：

```text
ClimateDataDownloader.exe
```

命令行和批量任务入口：

```text
ClimateDataDownloaderCLI.exe
```

说明：该包已内置 Python 运行时和依赖库，用户电脑不需要安装 Python。当前生成的是“便携 ZIP 包”，不是带向导的安装器；代码签名参数已经预留，提供证书后可签名。

### 2. 源码安装包（仍要求用户安装 Python 3.10+）

运行：

```powershell
.\Build_Release_Package.ps1
```

生成：

```text
release\ClimateDataDownloader_0.1.0_windows_YYYYMMDD_HHMMSS.zip
```

用户需要先安装 Python 3.10+，再双击安装脚本。

## 主要功能

- 图形化多选筛选：模式、情景/试验、成员、变量、table/频率、CORDEX 区域域、RCM 等。
- 批量组合查询：自动展开多选组合，支持 dry-run 预览清单。
- 多源下载：NEX-GDDP-CMIP6、CMIP6、CORDEX、NASA POWER。
- 数据整理：每次任务生成独立数据包，包含原始数据、处理数据、manifest、SHA256、失败报告。
- 后处理：经纬度裁剪、空间重采样、日/月/年尺度转换和聚合。
- 批量 JSON：适合给高级用户或售后场景批量下载固定方案。

## 批量下载示例

免 Python 便携包中：

```powershell
.\ClimateDataDownloaderCLI.exe batch --config .\examples\power_batch_small.json --dry-run
.\ClimateDataDownloaderCLI.exe batch --config .\examples\power_batch_small.json --output .\downloads\power_batch_small
```

源码开发环境中：

```powershell
.\.venv\Scripts\python.exe -m cmip_downloader batch --config .\examples\nex_batch_dry_run.json --dry-run
```

示例配置见：

- `examples\power_batch_small.json`
- `examples\nex_batch_dry_run.json`

## 数据源是否官方

下载入口使用官方或官方公开镜像：

- NEX-GDDP-CMIP6：NASA NEX 数据集，下载使用 AWS Open Data 公共镜像。
- CMIP6：LLNL ESGF 官方联合检索。
- CORDEX：DKRZ ESGF 官方索引。
- NASA POWER：NASA POWER 官方 API。
- ERA5 / ERA5-Land：当前仅预留入口，正式下载需要用户自己的 Copernicus CDS 账号和授权。

软件本身是下载与整理工具，不声称拥有第三方数据版权。商业销售时应明确数据来源、引用要求和许可证边界。

## 数据包结构

```text
climate_package_YYYYMMDD_HHMMSS/
├─ README.txt
├─ manifest.json
├─ checksums.sha256
├─ raw/{dataset}/{model}/{experiment}/{member}/{table}/{variable}/
├─ processed/{dataset}/{model}/{experiment}/{member}/{table}/{variable}/
└─ reports/
   ├─ download_report.json
   └─ failed_items.csv
```

## 测试

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m compileall -q src tests
.\.venv\Scripts\python.exe -m pip check
```

## 文档

- [功能说明](docs/功能说明.md)
- [安装使用说明](docs/安装使用说明.md)
- [销售发布检查清单](docs/销售发布检查清单.md)
- [测试报告 2026-08-04](docs/测试报告_2026-08-04.md)

## 官方入口

- [NASA NEX-GDDP-CMIP6](https://www.nccs.nasa.gov/services/data-collections/land-based-products/nex-gddp-cmip6)
- [AWS Open Data: NEX-GDDP-CMIP6](https://registry.opendata.aws/nex-gddp-cmip6/)
- [ESGF CMIP6](https://esgf-node.llnl.gov/search/cmip6/)
- [DKRZ ESGF CORDEX](https://esgf-data.dkrz.de/search/cordex-dkrz/)
- [NASA POWER API](https://power.larc.nasa.gov/docs/services/api/)
- [Copernicus Climate Data Store](https://cds.climate.copernicus.eu/)
