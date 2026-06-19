import json
import re
import urllib.parse
import urllib.request

from .models import DataQuery, DownloadItem


SEARCH_ENDPOINT = "https://esgf-node.llnl.gov/esg-search/search"
_DATE_RANGE = re.compile(r"_(\d{4})\d{4}-(\d{4})\d{4}(?:-[^.]+)?\.nc$")


def _first(value: object) -> str | None:
    if isinstance(value, list):
        return str(value[0]) if value else None
    return str(value) if value is not None else None


def _httpserver_url(values: object) -> str | None:
    if not isinstance(values, list):
        return None
    for value in values:
        parts = str(value).split("|")
        if len(parts) >= 3 and parts[-1] == "HTTPServer":
            return parts[0]
    return None


def _overlaps(filename: str, start_year: int, end_year: int) -> bool:
    match = _DATE_RANGE.search(filename)
    if not match:
        return True
    file_start, file_end = map(int, match.groups())
    return file_start <= end_year and file_end >= start_year


def parse_search_response(payload: dict, query: DataQuery) -> tuple[list[DownloadItem], int]:
    response = payload.get("response", {})
    items: list[DownloadItem] = []
    for doc in response.get("docs", []):
        filename = str(doc.get("title", ""))
        url = _httpserver_url(doc.get("url"))
        if not filename or not url or not _overlaps(filename, query.start_year, query.end_year):
            continue
        checksum_type = _first(doc.get("checksum_type"))
        items.append(
            DownloadItem(
                url=url,
                filename=filename,
                size=int(doc.get("size", 0)),
                checksum=_first(doc.get("checksum")),
                checksum_type=checksum_type.lower() if checksum_type else None,
                source="cmip6",
            )
        )
    return items, int(response.get("numFound", 0))


def build_search_url(query: DataQuery, offset: int = 0, limit: int = 500) -> str:
    params = {
        "type": "File",
        "project": "CMIP6",
        "source_id": query.model,
        "experiment_id": query.experiment,
        "variant_label": query.member,
        "variable_id": query.variable,
        "table_id": query.table,
        "latest": "true",
        "replica": "false",
        "format": "application/solr+json",
        "offset": str(offset),
        "limit": str(limit),
    }
    return f"{SEARCH_ENDPOINT}?{urllib.parse.urlencode(params)}"


def fetch_files(query: DataQuery, timeout: int = 120) -> list[DownloadItem]:
    offset = 0
    limit = 500
    found: dict[str, DownloadItem] = {}
    while True:
        request = urllib.request.Request(build_search_url(query, offset, limit))
        with urllib.request.urlopen(request, timeout=timeout) as response:
            items, total = parse_search_response(json.load(response), query)
        for item in items:
            found.setdefault(item.filename, item)
        offset += limit
        if offset >= total:
            return sorted(found.values(), key=lambda item: item.filename)
