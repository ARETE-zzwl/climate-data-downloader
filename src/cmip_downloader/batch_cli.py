from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import cordex, esgf, nex, noaa
from .batch import BatchSelection, PlannedItem, fetch_batch
from .tasks import create_task, run_task
from .power import PowerSelection, plan_files
from .process import ProcessOptions


@dataclass(frozen=True)
class BatchJob:
    dataset: str
    selection: object
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
class BatchRunResult:
    exit_code: int
    planned_count: int
    completed_count: int = 0
    failed_count: int = 0
    processed_count: int = 0
    package: Path | None = None


def _tuple(data: dict[str, Any], key: str, *aliases: str) -> tuple[str, ...]:
    for name in (key, *aliases):
        if name in data:
            value = data[name]
            break
    else:
        return ()
    if isinstance(value, str):
        return (value,)
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{key} 必须是字符串或字符串数组")
    return tuple(str(item) for item in value)


def _years(data: dict[str, Any]) -> tuple[int, int]:
    if "years" in data:
        years = data["years"]
        if not isinstance(years, (list, tuple)) or len(years) != 2:
            raise ValueError("years 必须是 [起始年, 结束年]")
        return int(years[0]), int(years[1])
    if "start_year" not in data or "end_year" not in data:
        raise ValueError("必须提供 years 或 start_year/end_year")
    return int(data["start_year"]), int(data["end_year"])


def _bbox(value: object) -> tuple[float, float, float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise ValueError("bbox 必须是 [west, east, south, north]")
    return tuple(float(item) for item in value)  # type: ignore[return-value]


def _process_options(data: dict[str, Any], dataset: str) -> ProcessOptions:
    processing = data.get("processing", {})
    if not isinstance(processing, dict):
        raise ValueError("processing 必须是对象")
    bbox = None
    if "bbox" in processing:
        bbox = _bbox(processing["bbox"])
    elif dataset != "power" and "bbox" in data:
        bbox = _bbox(data["bbox"])
    resolution = processing.get("spatial_resolution")
    return ProcessOptions(
        bbox=bbox,
        spatial_resolution=None if resolution in (None, "original") else float(resolution),
        temporal_scale=str(processing.get("temporal_scale", "original")),
        aggregation=str(processing.get("aggregation", "mean")),
    )


def load_batch_job(
    config_path: Path,
    output_override: Path | None = None,
    workers_override: int | None = None,
) -> BatchJob:
    data = json.loads(Path(config_path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("批量配置必须是 JSON 对象")
    dataset = str(data.get("dataset", "")).lower()
    start_year, end_year = _years(data)
    output = Path(output_override or data.get("output", "downloads")).expanduser()
    workers = int(workers_override or data.get("workers", 3))
    if not 1 <= workers <= 16:
        raise ValueError("workers 必须位于 1 到 16 之间")
    keep_raw = bool(data.get("keep_raw", True))
    process = _process_options(data, dataset)

    if dataset in {"nex", "cmip6"}:
        selection = BatchSelection(
            dataset=dataset,
            models=_tuple(data, "models", "model"),
            experiments=_tuple(data, "experiments", "experiment"),
            members=_tuple(data, "members", "member"),
            variables=_tuple(data, "variables", "variable"),
            tables=_tuple(data, "tables", "table") or ("day",),
            start_year=start_year,
            end_year=end_year,
            version=str(data.get("version", "v2.0")),
        )
        selection.expand_queries()
    elif dataset == "cordex":
        selection = cordex.CordexSelection(
            domains=_tuple(data, "domains", "domain"),
            driving_models=_tuple(data, "driving_models", "models", "model"),
            experiments=_tuple(data, "experiments", "experiment"),
            ensembles=_tuple(data, "ensembles", "members", "member"),
            rcm_names=_tuple(data, "rcm_names", "rcms", "rcm") or ("不限",),
            variables=_tuple(data, "variables", "variable"),
            frequencies=_tuple(data, "frequencies", "tables", "table"),
            start_year=start_year,
            end_year=end_year,
        )
        selection.expand_queries()
    elif dataset in noaa.VARIABLES:
        selection = noaa.NoaaSelection(dataset, _tuple(data, "variables", "variable"), start_year, end_year)
        selection.expand_queries()
    elif dataset == "power":
        if "bbox" not in data:
            raise ValueError("NASA POWER 批量任务必须提供 bbox")
        west, east, south, north = _bbox(data["bbox"])
        selection = PowerSelection(
            variables=_tuple(data, "variables", "variable"),
            temporals=_tuple(data, "temporals", "temporal", "tables", "table"),
            start_year=start_year,
            end_year=end_year,
            west=west,
            east=east,
            south=south,
            north=north,
        )
        selection.expand_queries()
    else:
        raise ValueError("dataset 必须是 nex、cmip6、cordex、power、noaa_cpc 或 noaa_ncep")
    return BatchJob(dataset, selection, process, output, workers, keep_raw)


def fetch_planned_items(job: BatchJob) -> tuple[list[PlannedItem], dict[object, Exception]]:
    if job.dataset == "nex":
        return fetch_batch(job.selection, nex.fetch_files, workers=job.workers)
    if job.dataset == "cmip6":
        return fetch_batch(job.selection, esgf.fetch_files, workers=job.workers)
    if job.dataset == "cordex":
        return cordex.fetch_batch(job.selection, workers=job.workers)
    if job.dataset == "power":
        return plan_files(job.selection), {}
    if job.dataset in noaa.VARIABLES:
        return fetch_batch(job.selection, noaa.fetch_files, workers=job.workers)
    raise ValueError(f"不支持的数据源：{job.dataset}")


def run_batch_job(job: BatchJob, dry_run: bool = False) -> BatchRunResult:
    planned, query_failures = fetch_planned_items(job)
    if dry_run:
        return BatchRunResult(
            exit_code=1 if query_failures else 0,
            planned_count=len(planned),
            failed_count=len(query_failures),
        )
    if not planned:
        return BatchRunResult(1, 0, failed_count=len(query_failures))
    package = create_task(job.output, planned, job.selection, job.process, job.keep_raw, query_failures)
    package, completed, failed, processed, process_failed = run_task(package, job.workers)
    failed_count = len(failed) + len(process_failed) + len(query_failures)
    return BatchRunResult(
        exit_code=1 if failed_count else 0,
        planned_count=len(planned),
        completed_count=len(completed),
        failed_count=failed_count,
        processed_count=len(processed),
        package=package,
    )
