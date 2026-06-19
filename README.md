# 气候数据下载器

面向 Windows 的图形化气候数据下载与整理工具，支持 NEX-GDDP-CMIP6、CMIP6、CORDEX 和 NASA POWER；ERA5 / ERA5-Land 已预留入口。

## 主要功能

- 可搜索多选：模式、情景/试验、成员、变量、table/频率，以及 CORDEX 区域域和 RCM 均可勾选多项。
- 批量检索：自动展开筛选组合、并行查询、跨组合去重；单次最多 500 个组合，防止误发海量请求。
- 自由范围：年份、全球或矩形经纬度、输出网格间距、日/月/年尺度和聚合方式。
- 稳健下载：下载前预览，并发、重试、断点续传，以及源站提供的 MD5/SHA 校验。
- 自动整理：每次任务生成独立数据包，含分层原始/处理数据、来源清单、SHA256 和失败报告。

## 数据源

- **NEX-GDDP-CMIP6**：NASA 官方数据，使用 AWS Open Data 公共镜像，无需账户。
- **CMIP6**：通过 LLNL ESGF 官方联邦检索获得原始模式文件。
- **CORDEX**：通过 DKRZ ESGF 官方索引检索 WCRP 区域气候模式数据。
- **NASA POWER**：NASA LaRC 官方区域 API，无需 API key。区域接口要求经纬度各至少跨越 2°；多选变量会拆成多个请求再统一打包。
- **ERA5 / ERA5-Land**：当前只保留界面和适配器位置。正式启用需要用户自己的 Copernicus CDS 账户、许可确认和 API key；本版本不读取或保存凭据。

## Windows 快速开始

1. 安装 Python 3.10 或更高版本，并勾选 “Add Python to PATH”。
2. 双击 `安装气候数据下载器.bat`。
3. 双击 `启动气候数据下载器.bat`。

也可在 PowerShell 中运行：

```powershell
cd D:\work\climate-data-downloader
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m cmip_downloader
```

## 使用流程

1. 选择数据源，点击各筛选按钮，在搜索窗口中勾选一个或多个值。
2. 需要完整候选列表时点击“刷新官方可选项”。
3. 在“范围与输出”页设置年份、区域、空间分辨率、时间尺度和输出目录。
4. 点击“查询清单”，核对文件、组合和大小。
5. 点击“下载并整理”。任务结束后，界面日志会显示数据包路径。

数据包结构：

```text
climate_package_YYYYMMDD_HHMMSS/
├── README.txt
├── manifest.json
├── checksums.sha256
├── raw/{dataset}/{model}/{experiment}/{member}/{table}/{variable}/
├── processed/{dataset}/{model}/{experiment}/{member}/{table}/{variable}/
└── reports/
    ├── download_report.json
    └── failed_items.csv
```

`manifest.json` 保存筛选条件、处理参数、官方来源 URL、期望大小、源站校验值和本地相对路径。`checksums.sha256` 可重新验证成功文件。部分组合或文件失败时，成功数据不会被删除。

## 精度说明

空间重采样只改变网格间距，不会提高源数据的真实物理精度。区域裁剪在完整文件下载后本地执行，因此磁盘应能容纳原始文件和处理结果。常见的一维规则经纬网格支持裁剪和重采样；二维曲线网格仍可下载，但本地空间处理会明确提示不支持。

## 命令行兼容入口

原有 NEX / CMIP6 单组合命令仍保留：

```powershell
climatedl nex --model ACCESS-CM2 --experiment historical --member r1i1p1f1 `
  --variable pr --years 2000:2001 --dry-run
```

多源、多选和数据包整理以图形界面为主。

## 测试

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## 官方入口

- [NASA NEX-GDDP-CMIP6](https://www.nccs.nasa.gov/services/data-collections/land-based-products/nex-gddp-cmip6)
- [AWS Open Data: NEX-GDDP-CMIP6](https://registry.opendata.aws/nex-gddp-cmip6/)
- [ESGF CMIP6](https://esgf-node.llnl.gov/search/cmip6/)
- [DKRZ ESGF](https://esgf-data.dkrz.de/search/cordex-dkrz/)
- [NASA POWER API](https://power.larc.nasa.gov/docs/services/api/)
- [Copernicus Climate Data Store](https://cds.climate.copernicus.eu/)
