import csv
import hashlib
import json
import re
from dataclasses import asdict, is_dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Iterable

from .batch import PlannedItem


_UNSAFE = re.compile(r"[^0-9A-Za-z._-]+")


def safe_component(value: object) -> str:
    cleaned = _UNSAFE.sub("_", str(value).strip()).strip("._")
    return cleaned or "unknown"


def _query_components(planned: PlannedItem) -> tuple[str, str, str, str, str]:
    query = planned.query
    if hasattr(query, "model"):
        return (
            str(query.model),
            str(query.experiment),
            str(query.member),
            str(query.table),
            str(query.variable),
        )
    if hasattr(query, "driving_model"):
        model = f"{query.domain}_{query.driving_model}_{query.rcm_name}"
        return model, str(query.experiment), str(query.ensemble), str(query.frequency), str(query.variable)
    if hasattr(query, "temporal"):
        years = f"{query.start_year}-{query.end_year}"
        return "regional", years, "default", str(query.temporal), str(query.variable)
    return "unknown", "unknown", "unknown", "unknown", "unknown"


def prepare_package(
    output: Path,
    planned_items: Iterable[PlannedItem],
    when: datetime | None = None,
) -> tuple[Path, list[PlannedItem]]:
    stamp = (when or datetime.now()).strftime("%Y%m%d_%H%M%S")
    package = Path(output) / f"climate_package_{stamp}"
    suffix = 1
    while package.exists():
        package = Path(output) / f"climate_package_{stamp}_{suffix}"
        suffix += 1
    (package / "raw").mkdir(parents=True)
    (package / "processed").mkdir()
    (package / "reports").mkdir()

    prepared: list[PlannedItem] = []
    for planned in planned_items:
        parts = (planned.dataset, *_query_components(planned))
        relative = Path("raw", *(safe_component(part) for part in parts)).as_posix()
        item = replace(planned.item, relative_dir=relative)
        prepared.append(PlannedItem(planned.dataset, planned.query, item))
    return package, prepared


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _jsonable(value):
    if is_dataclass(value):
        return {key: _jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def finalize_package(
    package: Path,
    planned_items: Iterable[PlannedItem],
    completed: Iterable[Path],
    failed: dict[str, Exception],
    filters: object,
    processing: object,
    processed: Iterable[Path] = (),
    query_failures: dict[object, Exception] | None = None,
) -> None:
    package = Path(package)
    completed_paths = {Path(path).resolve() for path in completed}
    processed_paths = [Path(path) for path in processed]
    files = []
    checksum_lines: list[str] = []
    for planned in planned_items:
        path = planned.item.target_path(package)
        downloaded = path.resolve() in completed_paths
        exists = path.exists()
        files.append(
            {
                "dataset": planned.dataset,
                "query": _jsonable(planned.query),
                "source_url": planned.item.url,
                "expected_size": planned.item.size,
                "source_checksum": planned.item.checksum,
                "source_checksum_type": planned.item.checksum_type,
                "status": (
                    "completed"
                    if downloaded and exists
                    else "removed_after_processing"
                    if downloaded
                    else "failed"
                ),
                "local_path": path.relative_to(package).as_posix(),
            }
        )
        if downloaded and exists:
            checksum_lines.append(f"{_sha256(path)}  {path.relative_to(package).as_posix()}")
    for path in processed_paths:
        if path.exists():
            checksum_lines.append(f"{_sha256(path)}  {path.relative_to(package).as_posix()}")

    manifest = {
        "created_at": datetime.now().astimezone().isoformat(),
        "filters": _jsonable(filters),
        "processing": _jsonable(processing),
        "files": files,
        "processed_files": [path.relative_to(package).as_posix() for path in processed_paths],
    }
    (package / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (package / "checksums.sha256").write_text(
        "\n".join(checksum_lines) + ("\n" if checksum_lines else ""), encoding="utf-8"
    )
    readme = (
        "气候数据下载包\n\n"
        "raw/ 保存官方源数据；processed/ 保存裁剪、重采样或时间聚合后的结果。\n"
        "manifest.json 记录筛选条件、来源 URL 和文件状态。\n"
        "checksums.sha256 可用于验证包内成功文件。\n"
        "reports/ 保存下载失败与查询失败信息。\n"
    )
    (package / "README.txt").write_text(readme, encoding="utf-8")

    query_failures = query_failures or {}
    report = {
        "completed": sum(item["status"] != "failed" for item in files),
        "failed": {name: str(error) for name, error in failed.items()},
        "query_failures": [
            {"query": _jsonable(query), "error": str(error)}
            for query, error in query_failures.items()
        ],
    }
    (package / "reports" / "download_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with (package / "reports" / "failed_items.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as file:
        writer = csv.writer(file)
        writer.writerow(["type", "item", "error"])
        for name, error in failed.items():
            writer.writerow(["download", name, str(error)])
        for query, error in query_failures.items():
            writer.writerow(["query", json.dumps(_jsonable(query), ensure_ascii=False), str(error)])
