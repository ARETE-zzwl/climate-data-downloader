import tempfile
import unittest
from pathlib import Path

import numpy as np
import xarray as xr

from cmip_downloader.process import ProcessOptions, process_netcdf


class NetcdfProcessingTests(unittest.TestCase):
    def test_crops_resamples_and_aggregates_monthly(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.nc"
            output = Path(directory) / "processed.nc"
            data = np.arange(60 * 3 * 3, dtype=float).reshape(60, 3, 3)
            dataset = xr.Dataset(
                {"tas": (("time", "lat", "lon"), data)},
                coords={
                    "time": np.arange("2000-01-01", "2000-03-01", dtype="datetime64[D]").astype("datetime64[ns]"),
                    "lat": [20.0, 10.0, 0.0],
                    "lon": [100.0, 110.0, 120.0],
                },
            )
            dataset.to_netcdf(source, engine="scipy")
            options = ProcessOptions(
                bbox=(105.0, 120.0, 5.0, 20.0),
                spatial_resolution=5.0,
                temporal_scale="monthly",
                aggregation="mean",
            )

            process_netcdf(source, output, options)

            with xr.open_dataset(output) as result:
                self.assertEqual(result.sizes["time"], 2)
                self.assertEqual(result.sizes["lat"], 4)
                self.assertEqual(result.sizes["lon"], 4)
                self.assertEqual(result.lat.values.tolist(), [5.0, 10.0, 15.0, 20.0])

    def test_understands_negative_bbox_for_zero_to_360_longitudes(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.nc"
            output = Path(directory) / "processed.nc"
            dataset = xr.Dataset(
                {"pr": (("lat", "lon"), np.ones((2, 4)))},
                coords={"lat": [0.0, 10.0], "lon": [0.0, 90.0, 180.0, 270.0]},
            )
            dataset.to_netcdf(source, engine="scipy")

            process_netcdf(source, output, ProcessOptions(bbox=(-100.0, -80.0, -5.0, 15.0)))

            with xr.open_dataset(output) as result:
                self.assertEqual(result.lon.values.tolist(), [270.0])


if __name__ == "__main__":
    unittest.main()
