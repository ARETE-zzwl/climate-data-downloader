import unittest
from urllib.parse import parse_qs, urlparse

from cmip_downloader.power import PowerQuery, PowerSelection, build_download_item


class PowerTests(unittest.TestCase):
    def test_builds_official_daily_regional_netcdf_request(self):
        query = PowerQuery(
            variable="T2M",
            temporal="daily",
            start_year=2020,
            end_year=2020,
            west=116,
            east=118,
            south=38,
            north=40,
        )

        item = build_download_item(query)
        parsed = urlparse(item.url)
        params = parse_qs(parsed.query)

        self.assertEqual(parsed.netloc, "power.larc.nasa.gov")
        self.assertEqual(parsed.path, "/api/temporal/daily/regional")
        self.assertEqual(params["parameters"], ["T2M"])
        self.assertEqual(params["format"], ["NETCDF"])
        self.assertEqual(item.source, "nasa-power")

    def test_rejects_area_smaller_than_regional_api_minimum(self):
        with self.assertRaisesRegex(ValueError, "至少跨越 2 度"):
            PowerQuery("T2M", "daily", 2020, 2020, 116, 117, 39, 40)

    def test_expands_one_request_per_variable(self):
        selection = PowerSelection(
            variables=("T2M", "PRECTOTCORR"),
            temporals=("daily",),
            start_year=2020,
            end_year=2020,
            west=116,
            east=118,
            south=38,
            north=40,
        )

        self.assertEqual(len(selection.expand_queries()), 2)


if __name__ == "__main__":
    unittest.main()
