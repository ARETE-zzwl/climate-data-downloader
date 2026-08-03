import sys
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

from cmip_downloader import __main__ as cli


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


if __name__ == "__main__":
    unittest.main()
