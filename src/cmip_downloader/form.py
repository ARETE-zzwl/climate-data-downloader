from dataclasses import dataclass
from pathlib import Path

from .models import DataQuery
from .process import ProcessOptions


@dataclass(frozen=True)
class DownloadRequest:
    dataset: str
    query: DataQuery
    process: ProcessOptions
    output: Path
    workers: int
    keep_raw: bool

    @property
    def needs_processing(self) -> bool:
        return (
            self.process.bbox is not None
            or self.process.spatial_resolution is not None
            or self.process.temporal_scale != "original"
        )


@dataclass(frozen=True)
class FormData:
    dataset: str
    model: str
    experiment: str
    member: str
    variable: str
    table: str
    version: str
    start_year: str
    end_year: str
    global_area: bool
    west: str
    east: str
    south: str
    north: str
    resolution: str
    temporal_scale: str
    aggregation: str
    output: str
    workers: str
    keep_raw: bool

    @classmethod
    def basic(cls, output: str) -> "FormData":
        return cls(
            dataset="nex",
            model="ACCESS-CM2",
            experiment="historical",
            member="r1i1p1f1",
            variable="pr",
            table="day",
            version="v2.0",
            start_year="2000",
            end_year="2014",
            global_area=True,
            west="-180",
            east="180",
            south="-90",
            north="90",
            resolution="original",
            temporal_scale="original",
            aggregation="mean",
            output=output,
            workers="3",
            keep_raw=True,
        )

    def to_request(self) -> DownloadRequest:
        try:
            start_year, end_year = int(self.start_year), int(self.end_year)
        except ValueError as error:
            raise ValueError("年份必须是整数") from error
        try:
            workers = int(self.workers)
        except ValueError as error:
            raise ValueError("并发数必须是整数") from error
        if not 1 <= workers <= 16:
            raise ValueError("并发数必须位于 1 到 16 之间")
        if self.dataset not in {"nex", "cmip6"}:
            raise ValueError("不支持的数据源")

        bbox = None
        if not self.global_area:
            try:
                bbox = tuple(float(value) for value in (self.west, self.east, self.south, self.north))
            except ValueError as error:
                raise ValueError("经纬度必须是数字") from error
        try:
            resolution = None if self.resolution == "original" else float(self.resolution)
        except ValueError as error:
            raise ValueError("空间分辨率必须是数字") from error

        output = Path(self.output).expanduser()
        existing_parent = output if output.exists() else output.parent
        if not existing_parent.exists():
            raise ValueError("输出目录的上级目录不存在")

        query = DataQuery(
            self.model,
            self.experiment,
            self.member,
            self.variable,
            start_year,
            end_year,
            table="day" if self.dataset == "nex" else self.table,
            version=self.version,
        )
        process = ProcessOptions(
            bbox=bbox,
            spatial_resolution=resolution,
            temporal_scale=self.temporal_scale,
            aggregation=self.aggregation,
        )
        return DownloadRequest(
            self.dataset, query, process, output, workers, self.keep_raw
        )
