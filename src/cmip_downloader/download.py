import hashlib
import os
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Iterable

from .models import DownloadItem


ProgressCallback = Callable[[str, int, int], None]


class DownloadError(RuntimeError):
    pass


class ChecksumError(DownloadError):
    pass


def _verify_checksum(path: Path, expected: str, algorithm: str) -> None:
    try:
        digest = hashlib.new(algorithm)
    except ValueError as error:
        raise ChecksumError(f"不支持的校验算法：{algorithm}") from error
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest().lower() != expected.lower():
        raise ChecksumError(f"{path.name} 校验失败")


def _download_attempt(
    item: DownloadItem,
    part: Path,
    progress: ProgressCallback | None,
    timeout: int,
) -> None:
    existing = part.stat().st_size if part.exists() else 0
    if existing > item.size > 0:
        raise DownloadError(f"{part.name} 的临时文件大于远端文件")
    headers = {"User-Agent": "climate-data-downloader/0.1"}
    if existing:
        headers["Range"] = f"bytes={existing}-"
    request = urllib.request.Request(item.url, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        resumed = existing > 0 and getattr(response, "status", None) == 206
        mode = "ab" if resumed else "wb"
        downloaded = existing if resumed else 0
        with part.open(mode) as file:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                file.write(chunk)
                downloaded += len(chunk)
                if progress:
                    progress(item.filename, downloaded, item.size)


def download_one(
    item: DownloadItem,
    output: Path,
    progress: ProgressCallback | None = None,
    retries: int = 2,
    timeout: int = 120,
) -> Path:
    target = item.target_path(Path(output))
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if not item.size or target.stat().st_size == item.size:
            return target
        raise FileExistsError(f"目标文件已存在但大小不一致：{target}")
    part = target.with_suffix(target.suffix + ".part")
    if part.exists() and item.size and part.stat().st_size == item.size:
        try:
            if item.checksum and item.checksum_type:
                _verify_checksum(part, item.checksum, item.checksum_type)
            os.replace(part, target)
            return target
        except ChecksumError:
            part.unlink()
    for attempt in range(retries + 1):
        try:
            _download_attempt(item, part, progress, timeout)
            if item.size and part.stat().st_size != item.size:
                raise DownloadError(
                    f"{item.filename} 大小不符：{part.stat().st_size} != {item.size}"
                )
            if item.checksum and item.checksum_type:
                _verify_checksum(part, item.checksum, item.checksum_type)
            os.replace(part, target)
            return target
        except ChecksumError:
            raise
        except (OSError, DownloadError):
            if attempt >= retries:
                raise
            time.sleep(2**attempt)
    raise AssertionError("unreachable")


def download_many(
    items: Iterable[DownloadItem],
    output: Path,
    workers: int = 3,
    progress: ProgressCallback | None = None,
) -> tuple[list[Path], dict[str, Exception]]:
    completed: list[Path] = []
    failed: dict[str, Exception] = {}
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = {
            executor.submit(download_one, item, output, progress): item for item in items
        }
        for future in as_completed(futures):
            item = futures[future]
            try:
                completed.append(future.result())
            except Exception as error:
                failed[item.filename] = error
    return completed, failed
