import hashlib
import os
import re
import ssl
import time
import urllib.request
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path
from threading import Event
from typing import Callable, Iterable

import certifi

from .models import DownloadItem
from .network import open_url


ProgressCallback = Callable[[str, int, int], None]
DOWNLOAD_CHUNK_SIZE = 64 * 1024


class DownloadError(RuntimeError):
    pass


class ChecksumError(DownloadError):
    pass


class DownloadPaused(DownloadError):
    pass


def _check_pause(stop_event):
    if stop_event is not None and stop_event.is_set():
        raise DownloadPaused('已暂停，临时文件保留，可恢复任务')


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
    stop_event: Event | None = None,
) -> None:
    _check_pause(stop_event)
    existing = part.stat().st_size if part.exists() else 0
    if existing > item.size > 0:
        raise DownloadError(f"{part.name} 的临时文件大于远端文件")
    headers = {"User-Agent": "climate-data-downloader/0.1"}
    if existing:
        headers["Range"] = f"bytes={existing}-"
    if progress:
        progress(item.filename, existing, item.size)
    request = urllib.request.Request(item.url, headers=headers)
    context = ssl.create_default_context(cafile=certifi.where()) if item.url.startswith("https://") else None
    with open_url(request, timeout=timeout, context=context) as response:
        resumed = existing > 0 and getattr(response, "status", None) == 206
        if getattr(response, 'status', None) == 206:
            match = re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)', response.headers.get('Content-Range', ''))
            if not match or int(match[1]) != existing or (item.size and int(match[3]) != item.size):
                raise DownloadError('服务器 Content-Range 与续传位置/文件大小不一致')
        mode = "ab" if resumed else "wb"
        downloaded = existing if resumed else 0
        if progress:
            progress(item.filename, downloaded, item.size)
        length = response.headers.get('Content-Length')
        expected = downloaded + int(length) if length else item.size
        with part.open(mode) as file:
            while True:
                _check_pause(stop_event)
                chunk = response.read1(DOWNLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                file.write(chunk)
                downloaded += len(chunk)
                if progress:
                    progress(item.filename, downloaded, item.size)
        if expected and downloaded != expected:
            raise DownloadError(f'响应不完整：{downloaded} != {expected}')


def download_one(
    item: DownloadItem,
    output: Path,
    progress: ProgressCallback | None = None,
    retries: int = 2,
    timeout: int = 30,
    stop_event: Event | None = None,
    status: Callable[[str], None] | None = None,
) -> Path:
    _check_pause(stop_event)
    target = item.target_path(Path(output))
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if not item.size or target.stat().st_size == item.size:
            if item.checksum and item.checksum_type:
                _verify_checksum(target, item.checksum, item.checksum_type)
            if progress:
                progress(item.filename, target.stat().st_size, item.size)
            return target
        raise FileExistsError(f"目标文件已存在但大小不一致：{target}")
    part = target.with_suffix(target.suffix + ".part")
    if part.exists() and item.size and part.stat().st_size == item.size:
        try:
            if item.checksum and item.checksum_type:
                _verify_checksum(part, item.checksum, item.checksum_type)
            os.replace(part, target)
            if progress:
                progress(item.filename, item.size, item.size)
            return target
        except ChecksumError:
            part.unlink()
    for attempt in range(retries + 1):
        try:
            if status:
                status(f'连接 {item.filename}（尝试 {attempt + 1}/{retries + 1}）')
            _download_attempt(item, part, progress, timeout, stop_event)
            if item.size and part.stat().st_size != item.size:
                raise DownloadError(
                    f"{item.filename} 大小不符：{part.stat().st_size} != {item.size}"
                )
            if item.checksum and item.checksum_type:
                _verify_checksum(part, item.checksum, item.checksum_type)
            os.replace(part, target)
            if status:
                status(f'完成 {item.filename}')
            return target
        except (ChecksumError, DownloadPaused):
            raise
        except (OSError, DownloadError) as error:
            if status:
                status(f'{item.filename}：{error}' + ('；将重试' if attempt < retries else '；已保留临时文件'))
            if attempt >= retries:
                raise
            if stop_event is not None:
                stop_event.wait(2**attempt)
                _check_pause(stop_event)
            else:
                time.sleep(2**attempt)
    raise AssertionError("unreachable")


def download_many(
    items: Iterable[DownloadItem],
    output: Path,
    workers: int = 3,
    progress: ProgressCallback | None = None,
    stop_event: Event | None = None,
    status: Callable[[str], None] | None = None,
) -> tuple[list[Path], dict[str, Exception]]:
    completed: list[Path] = []
    failed: dict[str, Exception] = {}
    pending = iter(items)
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = {}

        def submit_next():
            if stop_event is not None and stop_event.is_set():
                return
            item = next(pending, None)
            if item is not None:
                key = (Path(item.relative_dir) / item.filename).as_posix() if item.relative_dir else item.filename
                callback = (lambda _name, size, total, key=key: progress(key, size, total)) if progress else None
                future = executor.submit(download_one, item, output, callback,
                                         stop_event=stop_event, status=status)
                futures[future] = item

        for _ in range(max(1, workers)):
            submit_next()
        while futures:
            done, _ = wait(futures, return_when=FIRST_COMPLETED)
            for future in done:
                item = futures.pop(future)
                try:
                    completed.append(future.result())
                except Exception as error:
                    key = (Path(item.relative_dir) / item.filename).as_posix() if item.relative_dir else item.filename
                    failed[key] = error
                submit_next()
    return completed, failed
