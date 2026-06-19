import hashlib
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from cmip_downloader.download import ChecksumError, download_one
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


if __name__ == "__main__":
    unittest.main()
