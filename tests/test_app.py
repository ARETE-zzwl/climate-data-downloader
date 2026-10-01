import tempfile
import unittest
from pathlib import Path
from tkinter import Tk, TclError
from unittest.mock import patch

from cmip_downloader.app import ClimateDownloaderApp, DATASETS
from cmip_downloader.batch import PlannedItem
from cmip_downloader.models import DataQuery, DownloadItem
from cmip_downloader.tasks import create_task
from cmip_downloader.process import ProcessOptions


class AppTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = Tk()
        except TclError as error:
            self.skipTest(str(error))
        self.root.withdraw()
        self.app = ClimateDownloaderApp(self.root)

    def tearDown(self):
        if hasattr(self, 'root'):
            self.root.destroy()

    def test_noaa_selection_reaches_valid_download_request(self):
        with tempfile.TemporaryDirectory() as directory:
            for label, dataset in DATASETS.items():
                if not dataset.startswith('noaa_'):
                    continue
                self.app.dataset.set(label)
                self.app._dataset_changed()
                self.app.start_year.set('2020')
                self.app.end_year.set('2020')
                self.app.output.set(directory)
                request = self.app._validated_request()
                self.assertEqual(request.dataset, dataset)
                self.assertEqual(len(request.selection.expand_queries()), 1)

    def test_resume_uses_saved_package_and_pause_signals_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            query = DataQuery('Model', 'ssp126', 'member', 'pr', 2020, 2020)
            package = create_task(Path(directory), [PlannedItem('nex', query,
                                  DownloadItem('https://example.org/data.nc', 'data.nc', 4))],
                                  {}, ProcessOptions(), True)
            with patch('cmip_downloader.app.filedialog.askdirectory', return_value=str(package)), \
                 patch('cmip_downloader.app.messagebox.askyesno', return_value=True), \
                 patch.object(self.app, '_start_worker') as start:
                self.app._resume_task()
                self.assertEqual(start.call_args.args[0], 'download')
                self.assertEqual(self.app.active_package, package)
                self.assertFalse(self.app.stop_event.is_set())
                self.app._pause_task()
                self.assertTrue(self.app.stop_event.is_set())

    def test_query_failures_do_not_show_full_success(self):
        with tempfile.TemporaryDirectory() as directory:
            query = DataQuery('Model', 'ssp126', 'member', 'pr', 2020, 2020)
            package = create_task(Path(directory), [PlannedItem('nex', query,
                                  DownloadItem('https://example.org/data.nc', 'data.nc', 4))],
                                  {}, ProcessOptions(), True, {'missing': ValueError('offline')})
            with patch('cmip_downloader.app.messagebox.showwarning') as warning, \
                 patch('cmip_downloader.app.messagebox.showinfo') as info:
                self.app._download_ready(package, [], {}, [], {})
                warning.assert_called_once()
                info.assert_not_called()
