# 气候数据下载器

## 0.2.0 更新

- 新增 NOAA CPC 全球陆地逐日降水（0.5°，1979 年起）和 NCEP/NCAR 逐日再分析（2.5°，1948 年起，`air` / `slp`），支持 GUI 和批量 JSON。
- 下载前保存 `task.json`；新增“暂停”“恢复任务”，可在重启后继续原数据包。旧版无 `task.json` 的包需要单独恢复。
- 新增系统代理/直连切换、流式读取、重试日志、下载速度和长时间等待提示。
- 进度消息按文件合并，界面日志限制约 1000 行；下载线程仅维护有限并发任务，避免队列随数据块增长。
- 下载前检查已知文件所需磁盘空间；恢复任务加文件锁；新增 SHA256 校验命令。

详细使用方法、数据含义与限制见 [0.2.0 使用说明](docs/升级说明_0.2.0.md)。

```powershell
# 约 7 MB 的官方 NCEP 样本，下载后区域裁剪并聚合为月均
.\.venv\Scripts\python.exe -m cmip_downloader batch --config examples\noaa_ncep_small.json --direct
# 恢复此前 0.2.0 创建的数据包
.\.venv\Scripts\python.exe -m cmip_downloader resume --package "D:\data\climate_package_时间戳" --direct
# 检查下载包（全部文件读取一遍，耗时取决于磁盘）
.\.venv\Scripts\python.exe -m cmip_downloader verify --package "D:\data\climate_package_时间戳"
```

源码运行/测试前设置 `$env:PYTHONPATH='src'`，确保加载当前源码，而不是虚拟环境中旧版安装副本。

面向 Windows 的图形化气候数据下载与整理工具，支持 NEX-GDDP-CMIP6、CMIP6、CORDEX、NASA POWER、NOAA CPC 和 NCEP/NCAR；ERA5 / ERA5-Land 当前保留入口，后续可接入用户自己的 Copernicus CDS 凭据。

## 当前可交付形态

### 1. 免 Python 便携包（推荐销售给普通用户）

运行：

```powershell
.\Build_Portable_App.ps1
```

生成：

```text
release\ClimateDataDownloader_0.2.0_portable_YYYYMMDD_HHMMSS.zip
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
release\ClimateDataDownloader_0.2.0_windows_YYYYMMDD_HHMMSS.zip
```

用户需要先安装 Python 3.10+，再双击安装脚本。

## 主要功能

- 图形化多选筛选：模式、情景/试验、成员、变量、table/频率、CORDEX 区域域、RCM 等。
- 批量组合查询：自动展开多选组合，支持 dry-run 预览清单。
- 多源下载：NEX-GDDP-CMIP6、CMIP6、CORDEX、NASA POWER、NOAA CPC、NCEP/NCAR。
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
- `examples\noaa_ncep_small.json`
- `examples\noaa_cpc.json`

## 数据源是否官方

下载入口使用官方或官方公开镜像：

- NEX-GDDP-CMIP6：NASA NEX 数据集，下载使用 AWS Open Data 公共镜像。
- CMIP6：LLNL ESGF 官方联合检索。
- CORDEX：DKRZ ESGF 官方索引。
- NASA POWER：NASA POWER 官方 API。
- NOAA CPC / NCEP/NCAR：NOAA PSL 官方 NetCDF 下载站。
- ERA5 / ERA5-Land：当前仅预留入口，正式下载需要用户自己的 Copernicus CDS 账号和授权。

软件本身是下载与整理工具，不声称拥有第三方数据版权。商业销售时应明确数据来源、引用要求和许可证边界。

## 数据包结构

```text
climate_package_YYYYMMDD_HHMMSS/
├─ task.json
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
- [测试报告 2026-10-02（0.2.0）](docs/测试报告_2026-10-02.md)
- [测试报告 2026-08-04](docs/测试报告_2026-08-04.md)

## 官方入口

- [NASA NEX-GDDP-CMIP6](https://www.nccs.nasa.gov/services/data-collections/land-based-products/nex-gddp-cmip6)
- [AWS Open Data: NEX-GDDP-CMIP6](https://registry.opendata.aws/nex-gddp-cmip6/)
- [ESGF CMIP6](https://esgf-node.llnl.gov/search/cmip6/)
- [DKRZ ESGF CORDEX](https://esgf-data.dkrz.de/search/cordex-dkrz/)
- [NASA POWER API](https://power.larc.nasa.gov/docs/services/api/)
- [Copernicus Climate Data Store](https://cds.climate.copernicus.eu/)
