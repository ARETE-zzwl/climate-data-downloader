"""A process-local network preference; never change Windows proxy settings."""

import os
import ssl
import urllib.request

import certifi


def open_url(request, timeout=30, context=None):
    context = context or ssl.create_default_context(cafile=certifi.where())
    if os.environ.get('CLIMATE_DIRECT') == '1':
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=context))
        return opener.open(request, timeout=timeout)
    return urllib.request.urlopen(request, timeout=timeout, context=context)
