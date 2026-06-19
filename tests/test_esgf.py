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


if __name__ == "__main__":
    unittest.main()
