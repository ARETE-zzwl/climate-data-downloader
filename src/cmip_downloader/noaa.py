"""Yearly NetCDF products hosted by NOAA Physical Sciences Laboratory."""

from dataclasses import dataclass
from datetime import datetime, timezone
import ssl
import urllib.request

import certifi

from .models import DownloadItem
from .network import open_url


ROOT = 'https://downloads.psl.noaa.gov/Datasets'
VARIABLES = {'noaa_cpc': ('precip',), 'noaa_ncep': ('air', 'slp')}
MIN_YEAR = {'noaa_cpc': 1979, 'noaa_ncep': 1948}


@dataclass(frozen=True)
class NoaaQuery:
    dataset: str
    variable: str
    year: int

    @property
    def model(self):
        return 'CPC' if self.dataset == 'noaa_cpc' else 'NCEP-NCAR'

    experiment = 'observations-reanalysis'
    member = 'default'
    table = 'day'


@dataclass(frozen=True)
class NoaaSelection:
    dataset: str
    variables: tuple[str, ...]
    start_year: int
    end_year: int

    def expand_queries(self):
        if self.dataset not in VARIABLES:
            raise ValueError('不支持的 NOAA 数据源')
        if not self.variables or any(v not in VARIABLES[self.dataset] for v in self.variables):
            raise ValueError('请选择该 NOAA 数据源支持的变量')
        if not MIN_YEAR[self.dataset] <= self.start_year <= self.end_year <= datetime.now(timezone.utc).year:
            raise ValueError(f'年份必须位于 {MIN_YEAR[self.dataset]} 到当前年之间')
        return [NoaaQuery(self.dataset, variable, year)
                for variable in dict.fromkeys(self.variables)
                for year in range(self.start_year, self.end_year + 1)]


def file_url(query: NoaaQuery) -> str:
    # Validate even when called without a selection (e.g. imported saved tasks).
    NoaaSelection(query.dataset, (query.variable,), query.year, query.year).expand_queries()
    if query.dataset == 'noaa_cpc':
        return f'{ROOT}/cpc_global_precip/precip.{query.year}.nc'
    prefix = 'air.sig995' if query.variable == 'air' else 'slp'
    return f'{ROOT}/ncep.reanalysis.dailyavgs/surface/{prefix}.{query.year}.nc'


def fetch_files(query: NoaaQuery, timeout: int = 30) -> list[DownloadItem]:
    url = file_url(query)
    request = urllib.request.Request(url, method='HEAD')
    context = ssl.create_default_context(cafile=certifi.where())
    with open_url(request, timeout=timeout, context=context) as response:
        size = int(response.headers.get('Content-Length', 0))
    return [DownloadItem(url, url.rsplit('/', 1)[-1], size, source=query.dataset)]
