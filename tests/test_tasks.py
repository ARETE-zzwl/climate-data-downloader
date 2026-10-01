import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from cmip_downloader.batch import PlannedItem
from cmip_downloader.models import DataQuery, DownloadItem
from cmip_downloader.process import ProcessOptions
from cmip_downloader.tasks import create_task, load_task, run_task, verify_package, _package_lock


class TaskTests(unittest.TestCase):
    def plan(self):
        return [PlannedItem('nex', DataQuery('Model', 'ssp126', 'member', 'pr', 2020, 2020),
                            DownloadItem('https://example.org/data.nc', 'data.nc', 4))]

    def test_plan_exists_before_download_and_resume_reuses_package(self):
        with tempfile.TemporaryDirectory() as directory:
            package = create_task(Path(directory), self.plan(), {'dataset': 'nex'}, ProcessOptions(), True)
            task = load_task(package)
            target = task['planned'][0].item.target_path(package)
            target.parent.mkdir(parents=True)
            target.write_bytes(b'data')
            with patch('cmip_downloader.download.urllib.request.urlopen', side_effect=AssertionError('redownload')):
                result = run_task(package)
            self.assertEqual(len(result[1]), 1)
            self.assertEqual(result[2], {})
            self.assertEqual(len(list(Path(directory).glob('climate_package_*'))), 1)
            self.assertTrue((package / 'checksums.sha256').exists())

    def test_saved_pause_can_be_loaded_without_network(self):
        with tempfile.TemporaryDirectory() as directory:
            package = create_task(Path(directory), self.plan(), {}, ProcessOptions(), True)
            stop = threading.Event()
            stop.set()
            run_task(package, stop_event=stop)
            state = json.loads((package / 'task.json').read_text(encoding='utf-8'))
            self.assertEqual(state['state'], 'paused')
            self.assertEqual(len(load_task(package)['planned']), 1)

    def test_rejects_escaping_saved_path(self):
        with tempfile.TemporaryDirectory() as directory:
            package = create_task(Path(directory), self.plan(), {}, ProcessOptions(), True)
            path = package / 'task.json'
            data = json.loads(path.read_text(encoding='utf-8'))
            data['items'][0]['item']['relative_dir'] = '../../outside'
            path.write_text(json.dumps(data), encoding='utf-8')
            with self.assertRaises(ValueError):
                load_task(package)

    def test_disk_check_preserves_existing_data(self):
        with tempfile.TemporaryDirectory() as directory:
            package = create_task(Path(directory), self.plan(), {}, ProcessOptions(), True)
            with patch('cmip_downloader.tasks.shutil.disk_usage') as usage:
                usage.return_value.free = 0
                with self.assertRaisesRegex(OSError, '空间'):
                    run_task(package)
            self.assertTrue((package / 'task.json').exists())

    def test_second_writer_is_rejected_and_lock_is_released(self):
        with tempfile.TemporaryDirectory() as directory:
            package = create_task(Path(directory), self.plan(), {}, ProcessOptions(), True)
            with _package_lock(package):
                with self.assertRaisesRegex(ValueError, '运行'):
                    run_task(package)
            with _package_lock(package):
                pass

    def test_verify_detects_corruption(self):
        with tempfile.TemporaryDirectory() as directory:
            package = create_task(Path(directory), self.plan(), {}, ProcessOptions(), True)
            target = load_task(package)['planned'][0].item.target_path(package)
            target.parent.mkdir(parents=True)
            target.write_bytes(b'data')
            run_task(package)
            self.assertEqual(verify_package(package), 1)
            target.write_bytes(b'evil')
            with self.assertRaisesRegex(ValueError, 'SHA256'):
                verify_package(package)

    def test_processed_only_completed_task_does_not_redownload(self):
        with tempfile.TemporaryDirectory() as directory:
            package = create_task(Path(directory), self.plan(), {},
                                  ProcessOptions(temporal_scale='monthly'), False)
            target = load_task(package)['planned'][0].item.target_path(package)
            target.parent.mkdir(parents=True)
            target.write_bytes(b'data')

            def process(source, output, options):
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(b'processed')
                return output

            with patch('cmip_downloader.tasks.process_netcdf', side_effect=process):
                run_task(package)
            self.assertFalse(target.exists())
            self.assertEqual(verify_package(package), 1)
            with patch('cmip_downloader.tasks.download_many', side_effect=AssertionError('redownload')):
                result = run_task(package)
            self.assertEqual(len(result[3]), 1)
            self.assertTrue(result[3][0].exists())
