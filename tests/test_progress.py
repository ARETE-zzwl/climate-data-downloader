import unittest
from cmip_downloader.progress import ProgressBuffer


class ProgressTests(unittest.TestCase):
    def test_large_burst_retains_only_latest_value_per_file(self):
        buffer = ProgressBuffer()
        for value in range(100000):
            buffer.put('a.nc', value, 100000)
            buffer.put('b.nc', value, 100000)
        self.assertEqual(buffer.take(), {'a.nc': (99999, 100000), 'b.nc': (99999, 100000)})
        self.assertEqual(buffer.take(), {})
