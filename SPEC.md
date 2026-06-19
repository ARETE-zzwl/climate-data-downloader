# Spec: NEX-GDDP-CMIP6 / CMIP6 数据下载器

## Objective

为气候研究提供一个 Windows 友好的 Python 桌面图形工具，从两个公开数据源筛选、下载并按需处理 NetCDF 文件：

- NEX-GDDP-CMIP6：NASA 在 AWS Open Data 上发布的降尺度日尺度数据。
- CMIP6：通过 ESGF Search API 检索并从数据节点下载原始模式数据。

用户可以选择数据集、模式、试验/情景、成员、变量、原生频率、时间范围、经纬度范围、输出空间分辨率和输出时间尺度；下载前能看到文件数、总大小和 URL；下载支持并发、断点续传、重试、已完成文件跳过及可用时的校验和验证。区域裁剪、重采样和时间聚合在完整文件下载后执行。

## Assumptions

1. 首版是 Tkinter 桌面 GUI，同时保留命令行入口便于自动化。
2. 可选择全球或经纬度矩形范围；远端缺少稳定统一的子集服务时，先下载完整 NetCDF，再在本地裁剪。
3. NEX-GDDP-CMIP6 默认下载最新版 `v2.0`，避免同一年旧版、v1.1、v2.0 重复下载；允许用户显式选择其他版本。
4. CMIP6 “源数据”指 ESGF 上的 CMIP6 原始模式输出，默认只取 `latest=true` 的文件。
5. 不需要 AWS、ESGF 登录；遇到要求认证的数据节点时给出明确错误，不管理用户凭据。
6. “精度”按输出网格的空间分辨率理解；重采样只改变网格间距，不代表提高模式的真实物理精度。
7. “尺度”按输出时间尺度理解：保留原尺度，或聚合为日、月、年；不把低频数据插值成更高频数据。

## Tech Stack

- Python 3.10+
- Tkinter 桌面界面；下载层使用标准库（`urllib`、`concurrent.futures`、`hashlib` 等）
- xarray、NumPy、netCDF4 用于可选的空间裁剪、重采样和时间聚合
- `unittest` 作为测试框架
- `pyproject.toml` 提供可编辑安装和 `climatedl` 命令

## Commands

```powershell
# 安装
python -m pip install -e .

# 启动图形界面
climatedl

# 仅列出 NEX 文件，不下载
climatedl nex --model ACCESS-CM2 --experiment historical --member r1i1p1f1 `
  --variable pr --years 2000:2001 --dry-run

# 下载 NEX v2.0
climatedl nex --model ACCESS-CM2 --experiment historical --member r1i1p1f1 `
  --variable pr --years 2000:2001 --output D:\climate-data

# 仅列出 CMIP6 原始数据
climatedl cmip6 --model ACCESS-CM2 --experiment historical --member r1i1p1f1 `
  --table day --variable tas --years 2000:2014 --dry-run

# 下载；并发数默认 3
climatedl cmip6 --model ACCESS-CM2 --experiment historical --member r1i1p1f1 `
  --table day --variable tas --years 2000:2014 --output D:\climate-data --workers 3

# 测试
python -m unittest discover -s tests -v
```

## Project Structure

```text
climate-data-downloader/
├── pyproject.toml
├── README.md
├── SPEC.md
├── src/cmip_downloader/
│   ├── __init__.py
│   ├── __main__.py        # 默认启动 GUI；保留 CLI 自动化入口
│   ├── app.py             # Tkinter 主界面、状态与后台任务
│   ├── catalog.py         # NEX 静态目录和 ESGF 动态选项
│   ├── form.py            # 可测试的表单校验和请求转换
│   ├── models.py          # 查询条件和下载项
│   ├── nex.py             # S3 REST 清单查询及版本筛选
│   ├── esgf.py            # ESGF Search API 查询及 URL 选择
│   ├── download.py        # 断点续传、并发、重试、校验
│   └── process.py         # 裁剪、重采样和时间聚合
└── tests/
    ├── test_catalog.py
    ├── test_form.py
    ├── test_nex.py
    ├── test_esgf.py
    ├── test_download.py
    └── test_process.py
```

## Code Style

使用类型标注、不可变数据对象和小型纯函数；网络响应解析与实际网络请求分离，以便离线测试。

```python
@dataclass(frozen=True)
class DownloadItem:
    url: str
    relative_path: Path
    size: int
    checksum: str | None = None
    checksum_type: str | None = None
```

遵循 PEP 8；不引入只使用一次的抽象，不为未提出的存储后端或认证方式预留插件系统。

## Testing Strategy

- 单元测试：S3 XML、ESGF JSON、年份范围、NEX 版本去重、URL 选择和参数校验。
- 本地集成测试：用本地 HTTP 服务验证新下载、Range 断点续传、重试、校验失败和已完成文件跳过；测试不依赖公网。
- 处理测试：用小型合成 NetCDF 验证经纬度正序/倒序裁剪、0–360 经度、重采样和月/年聚合。
- CLI 测试：验证参数错误、dry-run 摘要及退出码。
- GUI 测试：状态转换和表单校验用无窗口纯逻辑测试；主窗口做启动 smoke test。
- 手工烟雾测试：对两个官方接口各做一次只查询不下载；避免在测试时拉取数百 MB 数据。

## Boundaries

- Always：写行为测试后再实现；下载前显示文件数和总大小；临时文件使用 `.part`；最终文件仅在大小和可用校验通过后落位；URL 查询参数编码；不覆盖大小不一致的成品文件。
- Ask first：地图多边形裁剪、NetCDF 合并、需要登录的 ESGF 数据、自动启动大批量下载。
- Never：把凭据写入代码；未经确认下载整套模式数据；把多段上传的 S3 ETag 当作 MD5；删除用户已有数据。

## Success Criteria

1. 两个子命令都能用给定筛选条件生成去重后的下载清单。
2. NEX 默认清单只包含 `_v2.0.nc`，年份范围两端均包含。
3. CMIP6 只选择 HTTPServer 下载地址，并按文件时间范围与目标年份求交集。
4. `--dry-run` 不写数据文件，并打印文件数、总大小及目标路径。
5. 中断后重跑能从 `.part` 文件续传；服务器不支持 Range 时安全地重新下载。
6. ESGF 提供 SHA256/MD5 时完成校验；失败文件不改名为最终文件。
7. 并发下载某一文件失败时，其余任务可完成，命令最终以非零状态报告失败列表。
8. 所有自动化测试通过，并完成两个官方接口的 dry-run 烟雾验证。
9. GUI 中数据源切换会联动可选项：NEX 固定日尺度并显示 0.25°；CMIP6 可选择 table/frequency，模式、情景、成员和变量可手动输入或从接口刷新。
10. GUI 能校验经纬度、时间和分辨率，展示任务进度/日志，运行期间不阻塞或假死。
11. 可选择全球/区域、原始/指定分辨率、原始/日/月/年尺度，以及是否保留下载的原始文件。

## Implementation Plan

1. 定义模型和解析函数 → 用离线 fixture 验证清单及筛选。
2. 实现下载与处理内核 → 用本地 HTTP 服务和合成 NetCDF 验证续传、校验、裁剪、重采样和聚合。
3. 接入 GUI、CLI 和文档 → 验证表单联动、后台任务、帮助、dry-run、退出码。
4. 运行完整测试与官方接口 smoke test → 不下载大型 NetCDF 文件。

## Explicit Non-goals

- 首版范围选择是经纬度矩形，不提供交互式地图或行政区/流域矢量多边形。
- 空间裁剪与重采样仅处理一维规则经纬度坐标；二维曲线海洋网格只下载原始文件。
- 不声称重采样能提高原始模式精度。
- 不提供模式集合统计、偏差订正或指数计算。
