import unittest

from cmip_downloader.catalog import parse_facets


class CatalogTests(unittest.TestCase):
    def test_parses_solr_alternating_facet_values(self):
        payload = {
            "facet_counts": {
                "facet_fields": {
                    "source_id": ["ACCESS-CM2", 12, "MIROC6", 7],
                    "experiment_id": ["historical", 19, "ssp245", 8],
                }
            }
        }

        facets = parse_facets(payload)

        self.assertEqual(facets["source_id"], ["ACCESS-CM2", "MIROC6"])
        self.assertEqual(facets["experiment_id"], ["historical", "ssp245"])


if __name__ == "__main__":
    unittest.main()
