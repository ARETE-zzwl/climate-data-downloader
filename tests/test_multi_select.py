import unittest

from cmip_downloader.multi_select import filter_values, selection_summary


class MultiSelectHelpersTests(unittest.TestCase):
    def test_filters_values_case_insensitively(self):
        values = ["ACCESS-CM2", "MIROC6", "ACCESS-ESM1-5"]

        result = filter_values(values, "access")

        self.assertEqual(result, ["ACCESS-CM2", "ACCESS-ESM1-5"])

    def test_summary_shows_single_value_or_count(self):
        self.assertEqual(selection_summary(["historical"]), "historical")
        self.assertEqual(selection_summary(["historical", "ssp245"]), "已选 2 项")
        self.assertEqual(selection_summary([]), "请选择…")


if __name__ == "__main__":
    unittest.main()
