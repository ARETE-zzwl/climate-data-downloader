import hashlib
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from cmip_downloader.batch import PlannedItem
from cmip_downloader.models import DataQuery, DownloadItem
from cmip_downloader.package import finalize_package, prepare_package


class PackageTests(unittest.TestCase):
    def test_prepares_hierarchy_and_writes_manifest_checksums_and_failures(self):
        query = DataQuery("Model/A", "historical", "r1i1p1f1", "tas", 2000, 2001)
        plans = [
            PlannedItem(
                "cmip6",
                query,
                DownloadItem("https://example.test/tas.nc", "tas.nc", 4, source="cmip6"),
            )
        ]
        with tempfile.TemporaryDirectory() as directory:
            package, prepared = prepare_package(
                Path(directory), plans, datetime(2024, 1, 2, 3, 4, 5)
            )
            target = prepared[0].item.target_path(package)
            target.parent.mkdir(parents=True)
            target.write_bytes(b"data")

            finalize_package(
                package,
                prepared,
                completed=[target],
                failed={"missing.nc": RuntimeError("network")},
                filters={"dataset": "cmip6"},
                processing={"temporal_scale": "original"},
            )

            expected = package / "raw" / "cmip6" / "Model_A" / "historical" / "r1i1p1f1" / "day" / "tas" / "tas.nc"
            self.assertEqual(target, expected)
            manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["files"][0]["status"], "completed")
            self.assertEqual(manifest["files"][0]["local_path"], expected.relative_to(package).as_posix())
            checksum = hashlib.sha256(b"data").hexdigest()
            self.assertIn(checksum, (package / "checksums.sha256").read_text(encoding="utf-8"))
            self.assertIn("missing.nc", (package / "reports" / "failed_items.csv").read_text(encoding="utf-8"))

    def test_rejects_parent_path_in_remote_metadata(self):
        query = DataQuery("..", "historical", "member", "tas", 2000, 2001)
        plan = PlannedItem("cmip6", query, DownloadItem("url", "x.nc", 1))

        with tempfile.TemporaryDirectory() as directory:
            package, prepared = prepare_package(Path(directory), [plan])

            self.assertNotIn("..", prepared[0].item.relative_dir.split("/"))
            self.assertTrue(package.is_dir())


if __name__ == "__main__":
    unittest.main()
