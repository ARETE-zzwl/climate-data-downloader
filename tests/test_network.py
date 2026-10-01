import os
import unittest
from unittest.mock import patch
from cmip_downloader.network import open_url


class NetworkTests(unittest.TestCase):
    def test_direct_uses_empty_proxy_map_without_changing_system_settings(self):
        with patch.dict(os.environ, {'CLIMATE_DIRECT': '1'}):
            with patch('cmip_downloader.network.urllib.request.ProxyHandler') as proxy:
                with patch('cmip_downloader.network.urllib.request.build_opener') as opener:
                    open_url('https://example.org/data.nc', timeout=15)
                    proxy.assert_called_once_with({})
                    opener.return_value.open.assert_called_once_with('https://example.org/data.nc', timeout=15)

    def test_default_honors_system_proxy(self):
        with patch.dict(os.environ, {'CLIMATE_DIRECT': '0'}):
            with patch('cmip_downloader.network.urllib.request.urlopen') as request:
                open_url('https://example.org/data.nc')
                self.assertEqual(request.call_args.args[0], 'https://example.org/data.nc')
