import unittest

from cmip_downloader.esgf import parse_search_response
from cmip_downloader.models import DataQuery


class EsgfSearchTests(unittest.TestCase):
    def test_selects_httpserver_and_overlapping_years(self):
        payload = {
            "response": {
                "numFound": 2,
                "docs": [
                    {
                        "title": "tas_day_ACCESS-CM2_historical_r1i1p1f1_gn_19500101-19991231.nc",
                        "size": 100,
                        "checksum": ["abc"],
                        "checksum_type": ["SHA256"],
                        "url": ["https://node.example/a.nc.html|application/opendap-html|OPENDAP"],
                    },
                    {
                        "title": "tas_day_ACCESS-CM2_historical_r1i1p1f1_gn_20000101-20141231.nc",
                        "size": 200,
                        "checksum": ["def"],
                        "checksum_type": ["SHA256"],
                        "url": [
                            "https://node.example/a.nc.html|application/opendap-html|OPENDAP",
                            "https://node.example/a.nc|application/netcdf|HTTPServer",
                        ],
                    },
                ],
            }
        }
        query = DataQuery("ACCESS-CM2", "historical", "r1i1p1f1", "tas", 2000, 2005, table="day")

        items, total = parse_search_response(payload, query)

        self.assertEqual(total, 2)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].url, "https://node.example/a.nc")
        self.assertEqual(items[0].checksum_type, "sha256")

    def test_filters_monthly_files_outside_requested_years(self):
        payload = {
            "response": {
                "numFound": 2,
                "docs": [
                    {
                        "title": "tas_Amon_ACCESS-CM2_historical_r1i1p1f1_gn_185001-189912.nc",
                        "size": 100,
                        "url": ["https://node.example/old.nc|application/netcdf|HTTPServer"],
                    },
                    {
                        "title": "tas_Amon_ACCESS-CM2_historical_r1i1p1f1_gn_200001-201412.nc",
                        "size": 200,
                        "url": ["https://node.example/current.nc|application/netcdf|HTTPServer"],
                    },
                ],
            }
        }
        query = DataQuery("ACCESS-CM2", "historical", "r1i1p1f1", "tas", 2000, 2005, table="Amon")

        items, _ = parse_search_response(payload, query)

        self.assertEqual([item.filename for item in items], ["tas_Amon_ACCESS-CM2_historical_r1i1p1f1_gn_200001-201412.nc"])

    def test_prefers_https_httpserver_url(self):
        payload = {
            "response": {
                "numFound": 1,
                "docs": [{
                    "title": "tas_day_model_historical_r1i1p1f1_gn_20000101-20001231.nc",
                    "size": 10,
                    "url": [
                        "http://node.example/a.nc|application/netcdf|HTTPServer",
                        "https://node.example/a.nc|application/netcdf|HTTPServer",
                    ],
                }],
            }
        }
        query = DataQuery("model", "historical", "r1i1p1f1", "tas", 2000, 2000)

        items, _ = parse_search_response(payload, query)

        self.assertEqual(items[0].url, "https://node.example/a.nc")

    def test_ignores_unsafe_remote_filename(self):
        payload = {
            "response": {
                "numFound": 1,
                "docs": [{
                    "title": "../outside.nc",
                    "size": 10,
                    "url": ["https://node.example/a.nc|application/netcdf|HTTPServer"],
                }],
            }
        }
        query = DataQuery("model", "historical", "r1i1p1f1", "tas", 2000, 2000)

        items, _ = parse_search_response(payload, query)

        self.assertEqual(items, [])


if __name__ == "__main__":
    unittest.main()
