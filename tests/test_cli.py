import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from cmip_downloader import __main__ as cli
from cmip_downloader.batch_cli import BatchRunResult


class CliEntryPointTests(unittest.TestCase):
    def test_help_argument_prints_cli_help_without_launching_gui(self):
        with patch.object(sys, "argv", ["cmip_downloader", "--help"]):
            with patch.object(cli, "launch") as launch:
                with redirect_stdout(StringIO()):
                    with self.assertRaises(SystemExit) as raised:
                        cli.main()

        self.assertEqual(raised.exception.code, 0)
        launch.assert_not_called()

    def test_no_arguments_launches_gui(self):
        with patch.object(sys, "argv", ["cmip_downloader"]):
            with patch.object(cli, "launch") as launch:
                self.assertEqual(cli.main(), 0)

        launch.assert_called_once_with()

    def test_batch_command_runs_configured_batch_job(self):
        with tempfile.TemporaryDirectory() as temp:
            config = Path(temp) / "batch.json"
            config.write_text(
                '{"dataset":"power","variables":["T2M"],"temporals":["daily"],'
                '"years":[2020,2020],"bbox":[116,118,38,40]}',
                encoding="utf-8",
            )
            with patch.object(sys, "argv", ["cmip_downloader", "batch", "--config", str(config), "--dry-run"]):
                with patch.object(cli, "run_batch_job") as run_batch_job:
                    run_batch_job.return_value = BatchRunResult(exit_code=0, planned_count=1)
                    with redirect_stdout(StringIO()):
                        exit_code = cli.main()

        self.assertEqual(exit_code, 0)
        run_batch_job.assert_called_once()


if __name__ == "__main__":
    unittest.main()
