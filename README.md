# 气候数据下载器

一个带图形界面的 NEX-GDDP-CMIP6 / CMIP6 下载与预处理工具。适合按模式、情景、变量、成员、时间和空间范围准备 NetCDF 研究数据。

## 能做什么

- NEX-GDDP-CMIP6：从 NASA 的 AWS Open Data 公共桶下载，无需 AWS 账号。
- CMIP6 原始数据：通过 ESGF Search API 检索，自动选择 HTTPServer 文件地址。
- 自由筛选：模式、情景/试验、成员、变量、table/频率、起止年份。
- 空间处理：全球或矩形经纬度范围；保留原始网格或重采样为指定经纬度间隔。
- 时间处理：保留原尺度，或聚合为日、月、年，并可选择平均、求和、最小、最大。
- 稳健下载：下载前预览文件数和大小，并发、断点续传、重试、SHA256/MD5 校验。
- 下载和处理在后台执行，界面会显示进度和日志。

## Windows 快速开始

1. 安装 Python 3.10 或更高版本，并在安装时勾选“Add Python to PATH”。
2. 双击 `安装气候数据下载器.bat`，等待依赖安装完成。
3. 双击 `启动气候数据下载器.bat`。

也可以在 PowerShell 中运行：

```powershell
cd D:\work\climate-data-downloader
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m cmip_downloader
```

## 使用流程

1. 在“数据筛选”页选择数据源、模式、情景、成员、变量和年份。
2. CMIP6 可点击“刷新可选项”从 ESGF 获取最新候选值；下拉框也都允许手动输入。
3. 在“范围与输出”页选择全球或矩形经纬度、空间分辨率、时间尺度和输出目录。
4. 点击“查询清单”，先确认文件数和预计大小。
5. 点击“开始下载”，确认后执行下载和可选处理。

下载后的目录：

```text
输出目录/
├── nex-gddp-cmip6/   # NEX 原始文件
├── cmip6/             # CMIP6 原始文件
└── processed/         # 裁剪、重采样或聚合后的文件
```

## 字段说明

- 空间分辨率：单位为经纬度“度”。“0.25”表示约 0.25° 网格间距。插值只能改变网格间距，不能提高源数据的真实物理精度。
- 时间尺度：从高频向日/月/年聚合；不会把月数据伪造为日数据。
- 聚合方式：温度通常使用平均值，月最高温可能使用最大值。降水率是否求和取决于源变量单位和研究定义，请先核对 NetCDF 元数据。
- NEX 版本：默认 `v2.0`。公共桶还保留旧版和 v1.1，工具不会把三个版本混在同一清单中。
- CMIP6 table：例如 `day`、`Amon`、`Omon`；它和变量必须是 ESGF 中实际存在的组合。

区域裁剪在完整文件下载后本地执行，因此磁盘应至少能容纳原始文件和处理结果。取消“保留原始文件”只会在处理成功后删除对应原始文件。

首版空间裁剪和重采样支持常见的一维规则经纬度坐标。部分海洋模式使用二维曲线网格，这类文件仍可下载和保留原始数据，但本地空间处理会给出明确提示。

## 命令行用法

图形界面之外也保留了适合脚本的查询/下载入口：

```powershell
climatedl nex --model ACCESS-CM2 --experiment historical --member r1i1p1f1 `
  --variable pr --years 2000:2001 --dry-run

climatedl cmip6 --model ACCESS-CM2 --experiment historical --member r6i1p1f1 `
  --table day --variable tas --years 2000:2014 --dry-run
```

## 测试

```powershell
$env:PYTHONPATH="src"
python -m unittest discover -s tests -v
```

测试不下载大型气候文件；下载测试使用本地 HTTP 服务，处理测试使用小型合成 NetCDF。

## 数据入口

- NEX-GDDP-CMIP6 AWS Open Data：https://registry.opendata.aws/nex-gddp-cmip6/
- ESGF Search：https://esgf-node.llnl.gov/search/cmip6/
