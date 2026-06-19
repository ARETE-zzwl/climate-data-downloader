import json
import ssl
import urllib.parse
import urllib.request
from dataclasses import dataclass
from itertools import product

import certifi

from .batch import MAX_COMBINATIONS, PlannedItem, fetch_queries
from .esgf import _first, _httpserver_url, _overlaps
from .models import DownloadItem


SEARCH_ENDPOINT = "https://esgf-data.dkrz.de/esg-search/search"
FACETS = (
    "domain",
    "driving_model",
    "experiment",
    "ensemble",
    "rcm_name",
    "variable",
    "time_frequency",
)


@dataclass(frozen=True)
class CordexQuery:
    domain: str
    driving_model: str
    experiment: str
    ensemble: str
    rcm_name: str
    variable: str
    frequency: str
    start_year: int
    end_year: int

    def __post_init__(self) -> None:
        for value in (
            self.domain,
            self.driving_model,
            self.experiment,
            self.ensemble,
            self.rcm_name,
            self.variable,
            self.frequency,
        ):
            if not value.strip():
                raise ValueError("CORDEX 筛选项不能为空")
        if self.start_year > self.end_year:
            raise ValueError("起始年份不能晚于结束年份")


@dataclass(frozen=True)
class CordexSelection:
    domains: tuple[str, ...]
    driving_models: tuple[str, ...]
    experiments: tuple[str, ...]
    ensembles: tuple[str, ...]
    rcm_names: tuple[str, ...]
    variables: tuple[str, ...]
    frequencies: tuple[str, ...]
    start_year: int
    end_year: int
    dataset: str = "cordex"

    def expand_queries(self) -> list[CordexQuery]:
        dimensions = (
            self.domains,
            self.driving_models,
            self.experiments,
            self.ensembles,
            self.rcm_names,
            self.variables,
            self.frequencies,
        )
        if any(not values for values in dimensions):
            raise ValueError("请完成 CORDEX 的全部筛选项")
        count = 1
        for values in dimensions:
            count *= len(values)
        if count > MAX_COMBINATIONS:
            raise ValueError(f"筛选组合达到 {count} 个，超过安全上限 {MAX_COMBINATIONS}")
        return [
            CordexQuery(*values, self.start_year, self.end_year)
            for values in product(*dimensions)
        ]


def build_search_url(query: CordexQuery, offset: int = 0, limit: int = 500) -> str:
    params = {
        "type": "File",
        "project": "CORDEX",
        "domain": query.domain,
        "driving_model": query.driving_model,
        "experiment": query.experiment,
        "ensemble": query.ensemble,
        "variable": query.variable,
        "time_frequency": query.frequency,
        "latest": "true",
        "replica": "false",
        "format": "application/solr+json",
        "offset": str(offset),
        "limit": str(limit),
    }
    if query.rcm_name != "不限":
        params["rcm_name"] = query.rcm_name
    return f"{SEARCH_ENDPOINT}?{urllib.parse.urlencode(params)}"


def parse_search_response(
    payload: dict, query: CordexQuery
) -> tuple[list[DownloadItem], int]:
    response = payload.get("response", {})
    items: list[DownloadItem] = []
    for doc in response.get("docs", []):
        filename = str(doc.get("title", ""))
        url = _httpserver_url(doc.get("url"))
        unsafe = filename in {"", ".", ".."} or "/" in filename or "\\" in filename
        if unsafe or not url or not _overlaps(filename, query.start_year, query.end_year):
            continue
        checksum_type = _first(doc.get("checksum_type"))
        items.append(
            DownloadItem(
                url=url,
                filename=filename,
                size=int(doc.get("size", 0)),
                checksum=_first(doc.get("checksum")),
                checksum_type=checksum_type.lower() if checksum_type else None,
                source="cordex",
            )
        )
    return items, int(response.get("numFound", 0))


def _ssl_context() -> ssl.SSLContext:
    return ssl.create_default_context(cafile=certifi.where())


def fetch_files(query: CordexQuery, timeout: int = 120) -> list[DownloadItem]:
    offset = 0
    limit = 500
    found: dict[str, DownloadItem] = {}
    while True:
        request = urllib.request.Request(build_search_url(query, offset, limit))
        with urllib.request.urlopen(
            request, timeout=timeout, context=_ssl_context()
        ) as response:
            items, total = parse_search_response(json.load(response), query)
        for item in items:
            found.setdefault(item.filename, item)
        offset += limit
        if offset >= total:
            return sorted(found.values(), key=lambda item: item.filename)


def fetch_facets(timeout: int = 120) -> dict[str, list[str]]:
    params = {
        "type": "File",
        "project": "CORDEX",
        "latest": "true",
        "replica": "false",
        "facets": ",".join(FACETS),
        "limit": "0",
        "format": "application/solr+json",
    }
    url = f"{SEARCH_ENDPOINT}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=timeout, context=_ssl_context()) as response:
        payload = json.load(response)
    fields = payload.get("facet_counts", {}).get("facet_fields", {})
    parsed: dict[str, list[str]] = {}
    for name, raw in fields.items():
        if isinstance(raw, dict):
            parsed[name] = list(raw)
        elif isinstance(raw, list):
            parsed[name] = [str(raw[index]) for index in range(0, len(raw), 2)]
    return parsed


def fetch_batch(
    selection: CordexSelection, workers: int = 4
) -> tuple[list[PlannedItem], dict[object, Exception]]:
    return fetch_queries(
        selection.dataset, selection.expand_queries(), fetch_files, workers
    )
