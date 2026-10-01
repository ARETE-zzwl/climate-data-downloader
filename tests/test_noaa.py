import unittest
from unittest.mock import patch, MagicMock

from cmip_downloader.noaa import NoaaSelection, file_url, fetch_files


class NoaaTests(unittest.TestCase):
    def test_cpc_expands_years_and_official_url(self):
        queries = NoaaSelection('noaa_cpc', ('precip',), 2019, 2020).expand_queries()
        self.assertEqual(len(queries), 2)
        self.assertEqual(file_url(queries[1]),
                         'https://downloads.psl.noaa.gov/Datasets/cpc_global_precip/precip.2020.nc')

    def test_ncep_variables_are_expanded_without_scenarios(self):
        queries = NoaaSelection('noaa_ncep', ('air', 'slp'), 2020, 2020).expand_queries()
        self.assertEqual(len(queries), 2)
        self.assertTrue(file_url(queries[0]).endswith('/surface/air.sig995.2020.nc'))
        self.assertTrue(file_url(queries[1]).endswith('/surface/slp.2020.nc'))

    def test_rejects_invalid_year_or_variable(self):
        for args in [('noaa_cpc', ('air',), 2020, 2020),
                     ('noaa_cpc', ('precip',), 1978, 2020),
                     ('noaa_ncep', (), 2000, 2001),
                     ('noaa_ncep', ('air',), 2021, 2020)]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                NoaaSelection(*args).expand_queries()

    def test_head_supplies_exact_size(self):
        query = NoaaSelection('noaa_cpc', ('precip',), 2020, 2020).expand_queries()[0]
        response = MagicMock()
        response.headers = {'Content-Length': '59112656'}
        response.__enter__.return_value = response
        with patch('cmip_downloader.noaa.urllib.request.urlopen', return_value=response):
            item, = fetch_files(query)
        self.assertEqual(item.size, 59112656)
        self.assertEqual(item.filename, 'precip.2020.nc')
