"""Persist a concrete download plan before any network transfers start."""

from dataclasses import asdict
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
from threading import Event
from urllib.parse import urlparse

from .batch import PlannedItem
from .download import download_many
from .models import DownloadItem
from .package import _jsonable, finalize_package, prepare_package
from .package import _sha256
from .process import ProcessOptions, process_netcdf


def _save(package, data):
    temporary = package / 'task.json.tmp'
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temporary, package / 'task.json')


def create_task(output, planned, filters, processing, keep_raw, query_failures=None):
    if not planned:
        raise ValueError('没有可下载文件，请先查询清单')
    package, prepared = prepare_package(output, planned)
    _save(package, {
        'schema_version': 1, 'state': 'ready',
        'filters': _jsonable(filters), 'processing': asdict(processing),
        'keep_raw': keep_raw,
        'query_failures': {str(key): str(value) for key, value in (query_failures or {}).items()},
        'items': [{'dataset': p.dataset, 'query': _jsonable(p.query), 'item': asdict(p.item)}
                  for p in prepared],
    })
    return package


def load_task(package):
    package = Path(package).resolve()
    path = package / 'task.json'
    if not path.exists():
        raise ValueError('此目录没有 task.json；旧版任务需要单独恢复，不能直接续传')
    if path.stat().st_size > 20 * 1024 * 1024:
        raise ValueError('任务清单过大')
    data = json.loads(path.read_text(encoding='utf-8'))
    if data.get('schema_version') != 1:
        raise ValueError('不支持的任务清单版本')
    planned, targets = [], set()
    for row in data['items']:
        item = DownloadItem(**row['item'])
        target = item.target_path(package).resolve()
        if not target.is_relative_to(package / 'raw') or target in targets:
            raise ValueError('任务文件路径越界或重复')
        if urlparse(item.url).scheme not in {'https', 'http'} or item.size < 0:
            raise ValueError('任务下载地址或大小无效')
        targets.add(target)
        planned.append(PlannedItem(row['dataset'], row['query'], item))
    if not planned or len(planned) > 100000:
        raise ValueError('任务文件数无效')
    return {'data': data, 'planned': planned, 'process': ProcessOptions(**data['processing'])}


def verify_package(package):
    package = Path(package).resolve()
    lines = (package / 'checksums.sha256').read_text(encoding='utf-8').splitlines()
    checked = 0
    for line in lines:
        expected, relative = line.split('  ', 1)
        path = (package / relative).resolve()
        if not path.is_relative_to(package) or not path.is_file():
            raise ValueError(f'校验文件缺失或路径无效：{relative}')
        if _sha256(path) != expected:
            raise ValueError(f'SHA256 不匹配：{relative}')
        checked += 1
    if not checked:
        raise ValueError('校验清单为空，不能确认数据完整性')
    return checked


@contextmanager
def _package_lock(package):
    # Kernel lock is released even if the process dies; no stale lock cleanup required.
    with (Path(package) / '.task.lock').open('a+b') as lock:
        lock.seek(0, 2)
        if lock.tell() == 0:
            lock.write(b'0')
            lock.flush()
        lock.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise ValueError('该数据包已有任务在运行，请先暂停或关闭另一实例') from error
        try:
            yield
        finally:
            lock.seek(0)
            if os.name == 'nt':
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock, fcntl.LOCK_UN)


def run_task(package, workers=3, progress=None, stop_event=None, status=None):
    with _package_lock(package):
        return _run_task(package, workers, progress, stop_event, status)


def _run_task(package, workers=3, progress=None, stop_event=None, status=None):
    package = Path(package).resolve()
    task = load_task(package)
    data, prepared, options = task['data'], task['planned'], task['process']
    stop_event = stop_event or Event()
    if not 1 <= workers <= 16:
        raise ValueError('并发数必须位于 1 到 16 之间')
    if data['state'] == 'completed':
        if status:
            status('任务已完成，正在验证已有文件…')
        verify_package(package)
        manifest = json.loads((package / 'manifest.json').read_text(encoding='utf-8'))
        return (package, [p.item.target_path(package) for p in prepared], {},
                [package / p for p in manifest['processed_files']], {})
    remaining = 0
    for plan in prepared:
        target = plan.item.target_path(package)
        partial = target.with_suffix(target.suffix + '.part')
        if not target.exists():
            remaining += max(0, plan.item.size - (partial.stat().st_size if partial.exists() else 0))
    if shutil.disk_usage(package).free < remaining + 64 * 1024 * 1024:
        raise OSError('磁盘剩余空间不足以下载原始文件，请更换磁盘或释放空间')
    data['state'] = 'running'
    _save(package, data)
    try:
        completed, failed = download_many([p.item for p in prepared], package, workers,
                                          progress, stop_event=stop_event, status=status)
        processed, process_failed = [], {}
        needs_processing = (options.bbox is not None or options.spatial_resolution is not None
                            or options.temporal_scale != 'original')
        if needs_processing and not stop_event.is_set():
            for index, source in enumerate(completed, 1):
                if stop_event.is_set():
                    break
                if status:
                    status(f'处理 {index}/{len(completed)}：{source.name}')
                relative = source.relative_to(package)
                target = package / 'processed' / Path(*relative.parts[1:]).parent / f'{source.stem}_processed.nc'
                try:
                    processed.append(process_netcdf(source, target, options))
                except Exception as error:
                    process_failed[source.name] = error
        if stop_event.is_set():
            data['state'] = 'paused'
        else:
            if status:
                status('正在生成报告与 SHA256 校验清单…')
            query_failures = data.get('query_failures', {})
            # Delete raw only after the entire processing phase succeeds. Interrupted jobs retain inputs.
            if needs_processing and not data['keep_raw'] and not failed and not process_failed and not query_failures:
                for source in completed:
                    source.unlink()
            finalize_package(package, prepared, completed, {**failed, **process_failed},
                             data['filters'], options, processed, query_failures)
            data['state'] = 'partial' if failed or process_failed or query_failures else 'completed'
        _save(package, data)
        return package, completed, failed, processed, process_failed
    except Exception:
        data['state'] = 'interrupted'
        _save(package, data)
        raise
