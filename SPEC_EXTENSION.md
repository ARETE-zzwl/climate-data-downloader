# Spec: 多源、多选与数据包整理扩展（已确认）

## Objective

在现有 NEX-GDDP-CMIP6 / CMIP6 桌面工具上增加三类能力：

1. 模式、情景/试验、成员、变量、频率等分类筛选支持多选勾选。
2. 一次查询多个组合，统一预览文件数、总大小和无效组合，不重复下载相同文件。
3. 每次任务输出一个自描述数据包，包含分层数据、清单、校验值和下载/处理报告。

## Assumptions

1. 用户所说的 `cinp6` 指 `CMIP6`。
2. 多选控件使用“按钮 + 可搜索勾选窗口”，避免上千个 CMIP6 候选值直接铺在主界面。
3. 模式、情景/试验、成员、变量、table/频率均可多选；年份和空间范围仍是整个任务共享条件。
4. 多选生成笛卡尔组合，但查询前显示组合数；超过 500 个组合时要求缩小范围，避免误发海量 ESGF 查询。
5. 数据包是目录，不默认压缩为 ZIP；气候数据可能很大，重复压缩既慢又通常收益有限。

## Data Sources

本次增加两个无需账户的数据源：

- CORDEX：WCRP 区域气候降尺度数据，通过 ESGF 官方联邦检索；可复用现有可靠下载、校验和断点续传能力。
- NASA POWER：NASA 官方气象与太阳能数据 API，适合按点/矩形区域、变量和日/月尺度下载，无需 API 密钥。

预留但本次不实际提交下载任务：

- ERA5 / ERA5-Land：界面显示正式预留入口和配置说明。Copernicus CDS 官方再分析数据需要用户自己的 CDS 账户、同意数据许可并配置 API key；本次不增加凭据输入、保存或下载提交逻辑。

## Tech Stack

- 保持 Python 3.10+、Tkinter、xarray、NumPy、SciPy、netCDF4。
- 新增数据源使用独立适配器；无凭据源不增加第三方运行依赖。
- ERA5 预留位不增加 `cdsapi` 依赖；后续启用时再加入官方依赖和本机凭据检测。

## Commands

```powershell
# 运行 GUI
.\.venv\Scripts\python.exe -m cmip_downloader

# 测试
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Project Structure

```text
src/cmip_downloader/
├── multi_select.py     # 可搜索多选勾选窗口
├── batch.py            # 多选组合展开、去重和批量查询
├── package.py          # 数据包目录、清单、校验和报告
├── cordex.py           # CORDEX ESGF 目录与文件查询
├── power.py            # NASA POWER 请求与 NetCDF 下载项
└── era5.py             # 预留能力描述，不处理凭据或提交请求
tests/
├── test_batch.py
├── test_package.py
├── test_cordex.py
└── test_power.py
```

## Code Style

多选 UI 只管理字符串列表；组合展开和数据包生成保持为无界面的纯逻辑，便于离线测试。

```python
@dataclass(frozen=True)
class BatchSelection:
    models: tuple[str, ...]
    experiments: tuple[str, ...]
    members: tuple[str, ...]
    variables: tuple[str, ...]
    tables: tuple[str, ...]
```

## Package Layout

```text
climate_package_YYYYMMDD_HHMMSS/
├── README.txt
├── manifest.json
├── checksums.sha256
├── raw/
│   └── {dataset}/{model}/{experiment}/{member}/{table}/{variable}/files.nc
├── processed/
│   └── {dataset}/{model}/{experiment}/{member}/{table}/{variable}/files_processed.nc
└── reports/
    ├── download_report.json
    └── failed_items.csv
```

`manifest.json` 记录筛选条件、来源 URL、文件大小、校验状态、处理参数和本地相对路径。已下载成功的数据即使部分组合失败也会被整理并写入报告。

## Testing Strategy

- 多选组合展开、组合上限、跨组合文件去重。
- 目录名净化，阻止远端元数据形成路径穿越。
- 临时目录内验证分层移动、清单、SHA256 和失败报告。
- 新数据源使用官方响应 fixture 做离线解析测试，再各下载一个小文件做 smoke test。
- GUI 验证搜索、全选、清空、勾选状态保存以及后台任务不阻塞。

## Boundaries

- Always：下载前显示组合数、文件数和总大小；路径只使用净化后的元数据；包内使用相对路径；不重复存储同一文件。
- Ask first：需要账户/API key 的数据源；自动 ZIP；超过 500 个筛选组合；改变现有原始数据。
- Never：保存或提交 CDS/API 凭据；因某个组合失败而删除其他成功文件；把插值后的网格称为更高真实精度。

## Success Criteria

1. CMIP6 的模式、情景、成员、变量和 table 可在可搜索窗口中多选勾选。
2. NEX 的模式、情景和变量可多选，成员和版本仍按实际目录约束。
3. 查询结果标明所属组合并按 URL/校验值去重。
4. 下载完成后自动生成上述数据包结构，清单能定位每个文件及其来源。
5. 包内 SHA256 可重新验证；失败项独立列出。
6. 新数据源至少各通过一次官方小文件端到端测试。
7. 现有 20 项测试及新增测试全部通过。

## Confirmed Decision

- CORDEX 与 NASA POWER 做成完整可用数据源。
- ERA5 / ERA5-Land 保留界面与适配器位置，等待后续单独配置 CDS 账户与 API key。
