import hashlib
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch, MagicMock

from cmip_downloader.download import ChecksumError, DownloadError, DownloadPaused, download_one, download_many
from cmip_downloader.models import DownloadItem


CONTENT = b"climate-data-" * 64


class RangeHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        start = 0
        if self.headers.get("Range"):
            start = int(self.headers["Range"].split("=")[1].split("-")[0])
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{len(CONTENT)-1}/{len(CONTENT)}")
        else:
            self.send_response(200)
        body = CONTENT[start:]
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


class DownloadTests(unittest.TestCase):
    def test_pause_in_flight_stops_next_file_and_can_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            stop = threading.Event()
            items = [DownloadItem(self.url, name, len(CONTENT), source='cmip6')
                     for name in ('first.nc', 'second.nc')]
            def progress(name, size, total):
                if size:
                    stop.set()
            completed, failed = download_many(items, output, workers=1, progress=progress, stop_event=stop)
            self.assertFalse(completed)
            self.assertIsInstance(failed['first.nc'], DownloadPaused)
            self.assertFalse((output / 'cmip6' / 'second.nc.part').exists())
            completed, failed = download_many(items, output, workers=1)
            self.assertEqual(len(completed), 2)
            self.assertFalse(failed)
            self.assertTrue(all(path.read_bytes() == CONTENT for path in completed))

    def test_pause_preserves_partial_file_for_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            target = output / 'cmip6' / 'data.nc'
            target.parent.mkdir()
            partial = target.with_suffix('.nc.part')
            partial.write_bytes(CONTENT[:100])
            stop = threading.Event()
            stop.set()
            item = DownloadItem(self.url, 'data.nc', len(CONTENT), source='cmip6')
            with self.assertRaises(DownloadPaused):
                download_one(item, output, stop_event=stop)
            self.assertEqual(partial.read_bytes(), CONTENT[:100])
            download_one(item, output)
            self.assertEqual(target.read_bytes(), CONTENT)

    def test_rejects_wrong_range_before_appending(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            target = output / 'cmip6' / 'data.nc'
            target.parent.mkdir()
            partial = target.with_suffix('.nc.part')
            partial.write_bytes(CONTENT[:100])
            response = MagicMock()
            response.__enter__.return_value = response
            response.status = 206
            response.headers = {'Content-Range': f'bytes 0-{len(CONTENT)-1}/{len(CONTENT)}'}
            item = DownloadItem(self.url, 'data.nc', len(CONTENT), source='cmip6')
            with patch('cmip_downloader.download.urllib.request.urlopen', return_value=response):
                with self.assertRaisesRegex(DownloadError, 'Range'):
                    download_one(item, output, retries=0)
            self.assertEqual(partial.read_bytes(), CONTENT[:100])

    def test_existing_file_is_checksummed_and_reports_progress(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            target = output / 'cmip6' / 'data.nc'
            target.parent.mkdir()
            target.write_bytes(CONTENT)
            events = []
            item = DownloadItem(self.url, 'data.nc', len(CONTENT),
                                hashlib.sha256(CONTENT).hexdigest(), 'sha256', 'cmip6')
            download_one(item, output, progress=lambda *e: events.append(e))
            self.assertEqual(events[-1][1], len(CONTENT))
            target.write_bytes(b'x' * len(CONTENT))
            with self.assertRaises(ChecksumError):
                download_one(item, output)

    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), RangeHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}/data.nc"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_resumes_partial_file_and_verifies_sha256(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            target = output / "cmip6" / "data.nc"
            target.parent.mkdir(parents=True)
            target.with_suffix(".nc.part").write_bytes(CONTENT[:100])
            item = DownloadItem(
                self.url,
                "data.nc",
                len(CONTENT),
                hashlib.sha256(CONTENT).hexdigest(),
                "sha256",
                "cmip6",
            )

            result = download_one(item, output)

            self.assertEqual(result, target)
            self.assertEqual(target.read_bytes(), CONTENT)
            self.assertFalse(target.with_suffix(".nc.part").exists())

    def test_checksum_failure_keeps_part_file(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            item = DownloadItem(self.url, "bad.nc", len(CONTENT), "wrong", "sha256", "cmip6")

            with self.assertRaises(ChecksumError):
                download_one(item, output, retries=0)

            target = output / "cmip6" / "bad.nc"
            self.assertFalse(target.exists())
            self.assertTrue(target.with_suffix(".nc.part").exists())

    def test_next_run_replaces_complete_but_corrupt_part(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            target = output / "cmip6" / "data.nc"
            target.parent.mkdir(parents=True)
            target.with_suffix(".nc.part").write_bytes(b"x" * len(CONTENT))
            item = DownloadItem(
                self.url, "data.nc", len(CONTENT), hashlib.sha256(CONTENT).hexdigest(), "sha256", "cmip6"
            )

            download_one(item, output)

            self.assertEqual(target.read_bytes(), CONTENT)

    def test_promotes_complete_part_when_no_checksum_is_available(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            target = output / "nex-gddp-cmip6" / "data.nc"
            target.parent.mkdir(parents=True)
            target.with_suffix(".nc.part").write_bytes(CONTENT)
            item = DownloadItem(self.url, "data.nc", len(CONTENT), source="nex-gddp-cmip6")

            download_one(item, output)

            self.assertEqual(target.read_bytes(), CONTENT)

    def test_reports_progress_before_first_network_chunk(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            item = DownloadItem(self.url, "data.nc", len(CONTENT), source="cmip6")
            events = []

            download_one(item, output, progress=lambda *event: events.append(event))

            self.assertGreaterEqual(len(events), 2)
            self.assertEqual(events[0], ("data.nc", 0, len(CONTENT)))
            self.assertEqual(events[-1], ("data.nc", len(CONTENT), len(CONTENT)))


if __name__ == "__main__":
    unittest.main()
