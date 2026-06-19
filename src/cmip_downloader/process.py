from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProcessOptions:
    bbox: tuple[float, float, float, float] | None = None
    spatial_resolution: float | None = None
    temporal_scale: str = "original"
    aggregation: str = "mean"

    def __post_init__(self) -> None:
        if self.bbox:
            west, east, south, north = self.bbox
            if west >= east or south >= north:
                raise ValueError("经纬度范围的最小值必须小于最大值")
            if not (-180 <= west <= 360 and -180 <= east <= 360):
                raise ValueError("经度必须位于 -180 到 360 之间")
            if not (-90 <= south <= 90 and -90 <= north <= 90):
                raise ValueError("纬度必须位于 -90 到 90 之间")
        if self.spatial_resolution is not None and not 0 < self.spatial_resolution <= 180:
            raise ValueError("空间分辨率必须大于 0 且不超过 180°")
        if self.temporal_scale not in {"original", "daily", "monthly", "annual"}:
            raise ValueError("不支持的时间尺度")
        if self.aggregation not in {"mean", "sum", "min", "max"}:
            raise ValueError("不支持的聚合方式")


def _coordinate_name(dataset, candidates: tuple[str, ...]) -> str:
    for name in candidates:
        if name in dataset.coords:
            return name
    raise ValueError(f"找不到坐标：{', '.join(candidates)}")


def _converted_bbox(dataset, lon_name: str, bbox):
    west, east, south, north = bbox
    longitude = dataset[lon_name]
    if float(longitude.min()) >= 0 and west < 0:
        west, east = west % 360, east % 360
        if west >= east:
            raise ValueError("当前版本不支持跨日期变更线的经度范围")
    return west, east, south, north


def _spatial_subset(dataset, options: ProcessOptions):
    import numpy as np

    lat_name = _coordinate_name(dataset, ("lat", "latitude", "y"))
    lon_name = _coordinate_name(dataset, ("lon", "longitude", "x"))
    dataset = dataset.sortby([lat_name, lon_name])
    if options.bbox:
        west, east, south, north = _converted_bbox(dataset, lon_name, options.bbox)
    else:
        west, east = float(dataset[lon_name].min()), float(dataset[lon_name].max())
        south, north = float(dataset[lat_name].min()), float(dataset[lat_name].max())

    if options.spatial_resolution:
        step = options.spatial_resolution
        target_lon = np.arange(west, east + step * 0.5, step)
        target_lat = np.arange(south, north + step * 0.5, step)
        return dataset.interp({lon_name: target_lon, lat_name: target_lat})
    if options.bbox:
        return dataset.sel({lon_name: slice(west, east), lat_name: slice(south, north)})
    return dataset


def _temporal_aggregate(dataset, options: ProcessOptions):
    if options.temporal_scale == "original" or "time" not in dataset.coords:
        return dataset
    rules = {"daily": "1D", "monthly": "MS", "annual": "YS"}
    resampler = dataset.resample(time=rules[options.temporal_scale])
    return getattr(resampler, options.aggregation)()


def process_netcdf(source: Path, output: Path, options: ProcessOptions) -> Path:
    try:
        import xarray as xr
    except ImportError as error:
        raise RuntimeError("数据处理需要安装 xarray、NumPy 和 netCDF4") from error

    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with xr.open_dataset(source) as dataset:
        result = _spatial_subset(dataset, options)
        result = _temporal_aggregate(result, options)
        result.attrs["processing_note"] = (
            "Processed by climate-data-downloader; resampling changes grid spacing, "
            "not the physical accuracy of the source model."
        )
        result.to_netcdf(output)
    return output
