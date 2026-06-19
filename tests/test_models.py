import unittest

from cmip_downloader.models import DataQuery


class DataQueryTests(unittest.TestCase):
    def test_rejects_reversed_year_range(self):
        with self.assertRaisesRegex(ValueError, "起始年份"):
            DataQuery(
                model="ACCESS-CM2",
                experiment="historical",
                member="r1i1p1f1",
                variable="pr",
                start_year=2001,
                end_year=2000,
            )

    def test_rejects_incomplete_required_filter(self):
        with self.assertRaisesRegex(ValueError, "模式"):
            DataQuery(
                model="",
                experiment="historical",
                member="r1i1p1f1",
                variable="pr",
                start_year=2000,
                end_year=2001,
            )


if __name__ == "__main__":
    unittest.main()

