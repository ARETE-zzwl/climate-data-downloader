import unittest
from urllib.parse import parse_qs, urlparse

from cmip_downloader.cordex import CordexQuery, CordexSelection, build_search_url, parse_search_response


class CordexTests(unittest.TestCase):
    def setUp(self):
        self.query = CordexQuery(
            domain="EUR-11",
            driving_model="CNRM-CERFACS-CNRM-CM5",
            experiment="historical",
            ensemble="r1i1p1",
            rcm_name="ALADIN63",
            variable="tas",
            frequency="day",
            start_year=2000,
            end_year=2001,
        )

    def test_builds_official_esgf_search(self):
        parsed = urlparse(build_search_url(self.query))
        params = parse_qs(parsed.query)

        self.assertEqual(parsed.netloc, "esgf-data.dkrz.de")
        self.assertEqual(params["project"], ["CORDEX"])
        self.assertEqual(params["domain"], ["EUR-11"])
        self.assertEqual(params["rcm_name"], ["ALADIN63"])

    def test_parses_files_and_filters_outside_years(self):
        payload = {
            "response": {
                "numFound": 2,
                "docs": [
                    {
                        "title": "tas_EUR-11_model_historical_r1i1p1_rcm_v1_day_20000101-20001231.nc",
                        "url": ["https://example.test/data.nc|application/netcdf|HTTPServer"],
                        "size": 123,
                        "checksum": ["abc"],
                        "checksum_type": ["SHA256"],
                    },
                    {
                        "title": "tas_EUR-11_model_historical_r1i1p1_rcm_v1_day_19900101-19901231.nc",
                        "url": ["https://example.test/old.nc|application/netcdf|HTTPServer"],
                        "size": 50,
                    },
                ],
            }
        }

        items, total = parse_search_response(payload, self.query)

        self.assertEqual(total, 2)
        self.assertEqual([item.filename for item in items], [payload["response"]["docs"][0]["title"]])
        self.assertEqual(items[0].source, "cordex")

    def test_expands_all_cordex_dimensions(self):
        selection = CordexSelection(
            domains=("EUR-11",),
            driving_models=("model-a", "model-b"),
            experiments=("historical", "rcp45"),
            ensembles=("r1i1p1",),
            rcm_names=("rcm",),
            variables=("tas", "pr"),
            frequencies=("day",),
            start_year=2000,
            end_year=2001,
        )

        self.assertEqual(len(selection.expand_queries()), 8)

    def test_can_query_records_without_rcm_facet(self):
        query = CordexQuery(
            "SEA-22", "MOHC-HadGEM2-ES", "rcp26", "r0i0p0", "不限",
            "areacella", "fx", 2000, 2000,
        )

        params = parse_qs(urlparse(build_search_url(query)).query)

        self.assertNotIn("rcm_name", params)


if __name__ == "__main__":
    unittest.main()
