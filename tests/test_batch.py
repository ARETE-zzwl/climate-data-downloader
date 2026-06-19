import unittest

from cmip_downloader.batch import BatchSelection, merge_query_results
from cmip_downloader.models import DownloadItem


class BatchSelectionTests(unittest.TestCase):
    def test_expands_selected_dimensions_as_cartesian_product(self):
        selection = BatchSelection(
            dataset="cmip6",
            models=("ACCESS-CM2", "MIROC6"),
            experiments=("historical", "ssp245"),
            members=("r1i1p1f1",),
            variables=("tas", "pr"),
            tables=("day",),
            start_year=2000,
            end_year=2005,
        )

        queries = selection.expand_queries()

        self.assertEqual(len(queries), 8)
        self.assertEqual(
            {(query.model, query.experiment, query.variable) for query in queries},
            {
                (model, experiment, variable)
                for model in selection.models
                for experiment in selection.experiments
                for variable in selection.variables
            },
        )

    def test_nex_forces_daily_table(self):
        selection = BatchSelection(
            dataset="nex",
            models=("ACCESS-CM2",),
            experiments=("historical",),
            members=("r1i1p1f1",),
            variables=("pr",),
            tables=("Amon", "day"),
            start_year=2000,
            end_year=2001,
        )

        queries = selection.expand_queries()

        self.assertEqual(len(queries), 1)
        self.assertEqual(queries[0].table, "day")

    def test_rejects_more_than_500_combinations(self):
        selection = BatchSelection(
            dataset="cmip6",
            models=tuple(f"model-{index}" for index in range(10)),
            experiments=tuple(f"experiment-{index}" for index in range(10)),
            members=("r1",),
            variables=tuple(f"variable-{index}" for index in range(6)),
            tables=("day",),
            start_year=2000,
            end_year=2001,
        )

        with self.assertRaisesRegex(ValueError, "500"):
            selection.expand_queries()

    def test_rejects_empty_selected_dimension(self):
        selection = BatchSelection(
            dataset="cmip6",
            models=(),
            experiments=("historical",),
            members=("r1i1p1f1",),
            variables=("tas",),
            tables=("day",),
            start_year=2000,
            end_year=2001,
        )

        with self.assertRaisesRegex(ValueError, "模式"):
            selection.expand_queries()


class BatchResultTests(unittest.TestCase):
    def test_deduplicates_same_remote_file_across_queries(self):
        selection = BatchSelection(
            dataset="cmip6",
            models=("ACCESS-CM2",),
            experiments=("historical",),
            members=("r1i1p1f1",),
            variables=("tas",),
            tables=("day",),
            start_year=2000,
            end_year=2001,
        )
        query = selection.expand_queries()[0]
        item = DownloadItem("https://example.test/tas.nc", "tas.nc", 12, "abc", "sha256", "cmip6")

        merged = merge_query_results("cmip6", [(query, [item]), (query, [item])])

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0].query, query)
        self.assertEqual(merged[0].item, item)


if __name__ == "__main__":
    unittest.main()
