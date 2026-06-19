import tempfile
import unittest
from pathlib import Path

from cmip_downloader.form import BatchFormData, FormData


class FormDataTests(unittest.TestCase):
    def test_builds_nex_query_and_processing_options(self):
        with tempfile.TemporaryDirectory() as directory:
            form = FormData(
                dataset="nex",
                model="ACCESS-CM2",
                experiment="ssp245",
                member="r1i1p1f1",
                variable="tasmax",
                table="day",
                version="v2.0",
                start_year="2030",
                end_year="2040",
                global_area=False,
                west="100",
                east="110",
                south="20",
                north="30",
                resolution="0.25",
                temporal_scale="monthly",
                aggregation="max",
                output=directory,
                workers="4",
                keep_raw=False,
            )

            request = form.to_request()

            self.assertEqual(request.query.start_year, 2030)
            self.assertEqual(request.process.bbox, (100.0, 110.0, 20.0, 30.0))
            self.assertEqual(request.process.spatial_resolution, 0.25)
            self.assertEqual(request.process.temporal_scale, "monthly")
            self.assertEqual(request.output, Path(directory))
            self.assertEqual(request.workers, 4)

    def test_global_original_selection_needs_no_postprocessing(self):
        with tempfile.TemporaryDirectory() as directory:
            form = FormData.basic(output=directory)

            request = form.to_request()

            self.assertFalse(request.needs_processing)

    def test_rejects_nonexistent_output_folder_parent(self):
        form = FormData.basic(output="Z:/folder/that/does/not/exist/output")

        with self.assertRaisesRegex(ValueError, "输出目录"):
            form.to_request()


class BatchFormDataTests(unittest.TestCase):
    def test_builds_multi_select_download_request(self):
        with tempfile.TemporaryDirectory() as directory:
            form = BatchFormData(
                dataset="cmip6",
                models=("ACCESS-CM2", "MIROC6"),
                experiments=("historical", "ssp245"),
                members=("r1i1p1f1",),
                variables=("tas", "pr"),
                tables=("day",),
                version="v2.0",
                start_year="2000",
                end_year="2005",
                global_area=True,
                west="-180",
                east="180",
                south="-90",
                north="90",
                resolution="original",
                temporal_scale="original",
                aggregation="mean",
                output=directory,
                workers="3",
                keep_raw=True,
            )

            request = form.to_request()

            self.assertEqual(len(request.selection.expand_queries()), 8)
            self.assertEqual(request.selection.models, ("ACCESS-CM2", "MIROC6"))
            self.assertFalse(request.needs_processing)


if __name__ == "__main__":
    unittest.main()
