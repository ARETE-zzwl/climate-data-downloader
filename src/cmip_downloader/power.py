import urllib.parse
from dataclasses import dataclass

from .batch import MAX_COMBINATIONS, PlannedItem
from .models import DownloadItem


API_ROOT = "https://power.larc.nasa.gov/api/temporal"
POWER_VARIABLES = (
    "T2M",
    "T2M_MAX",
    "T2M_MIN",
    "PRECTOTCORR",
    "RH2M",
    "WS2M",
    "ALLSKY_SFC_SW_DWN",
)


@dataclass(frozen=True)
class PowerQuery:
    variable: str
    temporal: str
    start_year: int
    end_year: int
    west: float
    east: float
    south: float
    north: float

    def __post_init__(self) -> None:
        if not self.variable.strip():
            raise ValueError("NASA POWER 变量不能为空")
        if self.temporal not in {"daily", "monthly"}:
            raise ValueError("NASA POWER 仅支持日或月尺度")
        if self.start_year > self.end_year:
            raise ValueError("起始年份不能晚于结束年份")
        if not (-180 <= self.west < self.east <= 180):
            raise ValueError("经度范围必须位于 -180 到 180")
        if not (-90 <= self.south < self.north <= 90):
            raise ValueError("纬度范围必须位于 -90 到 90")
        if self.east - self.west < 2 or self.north - self.south < 2:
            raise ValueError("NASA POWER 区域接口的经纬度都必须至少跨越 2 度")


@dataclass(frozen=True)
class PowerSelection:
    variables: tuple[str, ...]
    temporals: tuple[str, ...]
    start_year: int
    end_year: int
    west: float
    east: float
    south: float
    north: float
    dataset: str = "power"

    def expand_queries(self) -> list[PowerQuery]:
        if not self.variables:
            raise ValueError("请至少选择一个 NASA POWER 变量")
        if not self.temporals:
            raise ValueError("请至少选择一个 NASA POWER 时间尺度")
        if len(self.variables) * len(self.temporals) > MAX_COMBINATIONS:
            raise ValueError("NASA POWER 请求数量超过安全上限")
        return [
            PowerQuery(
                variable,
                temporal,
                self.start_year,
                self.end_year,
                self.west,
                self.east,
                self.south,
                self.north,
            )
            for variable in self.variables
            for temporal in self.temporals
        ]


def build_download_item(query: PowerQuery) -> DownloadItem:
    if query.temporal == "daily":
        start, end = f"{query.start_year}0101", f"{query.end_year}1231"
    else:
        start, end = str(query.start_year), str(query.end_year)
    params = {
        "parameters": query.variable,
        "community": "AG",
        "longitude-min": str(query.west),
        "longitude-max": str(query.east),
        "latitude-min": str(query.south),
        "latitude-max": str(query.north),
        "start": start,
        "end": end,
        "format": "NETCDF",
    }
    url = f"{API_ROOT}/{query.temporal}/regional?{urllib.parse.urlencode(params)}"
    filename = (
        f"POWER_{query.temporal}_{query.variable}_"
        f"{query.start_year}-{query.end_year}_"
        f"{query.west:g}_{query.east:g}_{query.south:g}_{query.north:g}.nc"
    )
    return DownloadItem(url=url, filename=filename, size=0, source="nasa-power")


def plan_files(selection: PowerSelection) -> list[PlannedItem]:
    return [
        PlannedItem(selection.dataset, query, build_download_item(query))
        for query in selection.expand_queries()
    ]
