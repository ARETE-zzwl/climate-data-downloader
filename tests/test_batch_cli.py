import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cmip_downloader.batch import PlannedItem
from cmip_downloader.batch_cli import load_batch_job, run_batch_job
from cmip_downloader.models import DownloadItem


class BatchCliConfigTests(unittest.TestCase):
    def test_packaged_example_configs_are_valid(self):
        for config in Path("examples").glob("*.json"):
            with self.subTest(config=config):
                job = load_batch_job(config)
                self.assertGreater(len(job.selection.expand_queries()), 0)

    def test_loads_nex_multi_select_config(self):
        with tempfile.TemporaryDirectory() as temp:
            config = Path(temp) / "batch.json"
            output = Path(temp) / "out"
            config.write_text(
                json.dumps(
                    {
                        "dataset": "nex",
                        "models": ["ACCESS-CM2"],
                        "experiments": ["ssp126", "ssp245"],
                        "members": ["r1i1p1f1"],
                        "variables": ["tas", "pr"],
                        "years": [2025, 2026],
                        "output": str(output),
                    }
                ),
                encoding="utf-8",
            )

            job = load_batch_job(config)

        self.assertEqual(job.dataset, "nex")
        self.assertEqual(len(job.selection.expand_queries()), 4)
        self.assertEqual(job.output, output)

    def test_loads_power_config_with_multiple_variables(self):
        with tempfile.TemporaryDirectory() as temp:
            config = Path(temp) / "power.json"
            config.write_text(
                json.dumps(
                    {
                        "dataset": "power",
                        "variables": ["T2M", "RH2M"],
                        "temporals": ["daily"],
                        "years": [2020, 2020],
                        "bbox": [116, 118, 38, 40],
                    }
                ),
                encoding="utf-8",
            )

            job = load_batch_job(config)

        self.assertEqual(job.dataset, "power")
        self.assertEqual(len(job.selection.expand_queries()), 2)

    def test_rejects_missing_years_with_user_facing_error(self):
        with tempfile.TemporaryDirectory() as temp:
            config = Path(temp) / "batch.json"
            config.write_text(
                json.dumps(
                    {
                        "dataset": "nex",
                        "models": ["ACCESS-CM2"],
                        "experiments": ["ssp126"],
                        "members": ["r1i1p1f1"],
                        "variables": ["tas"],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "years"):
                load_batch_job(config)

    def test_rejects_power_config_without_bbox(self):
        with tempfile.TemporaryDirectory() as temp:
            config = Path(temp) / "power.json"
            config.write_text(
                json.dumps(
                    {
                        "dataset": "power",
                        "variables": ["T2M"],
                        "temporals": ["daily"],
                        "years": [2020, 2020],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "bbox"):
                load_batch_job(config)

    def test_dry_run_reports_planned_items_without_downloading(self):
        planned = [
            PlannedItem(
                "power",
                object(),
                DownloadItem(
                    url="https://example.invalid/file.nc",
                    filename="file.nc",
                    size=123,
                    source="test",
                ),
            )
        ]
        with tempfile.TemporaryDirectory() as temp:
            config = Path(temp) / "power.json"
            config.write_text(
                json.dumps(
                    {
                        "dataset": "power",
                        "variables": ["T2M"],
                        "temporals": ["daily"],
                        "years": [2020, 2020],
                        "bbox": [116, 118, 38, 40],
                    }
                ),
                encoding="utf-8",
            )
            job = load_batch_job(config)
            with patch("cmip_downloader.batch_cli.fetch_planned_items", return_value=(planned, {})):
                with patch("cmip_downloader.batch_cli.download_many") as download_many:
                    result = run_batch_job(job, dry_run=True)

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.planned_count, 1)
        self.assertIsNone(result.package)
        download_many.assert_not_called()


if __name__ == "__main__":
    unittest.main()
