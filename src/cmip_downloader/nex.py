import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from .models import DataQuery, DownloadItem
from .network import open_url


S3_ENDPOINT = "https://nex-gddp-cmip6.s3.us-west-2.amazonaws.com"
_YEAR = re.compile(r"_(\d{4})(?:_v[\d.]+)?\.nc$")
_VERSION = re.compile(r"_v([\d.]+)\.nc$")


def _matches_version(filename: str, requested: str) -> bool:
    match = _VERSION.search(filename)
    if requested == "original":
        return match is None
    return match is not None and f"v{match.group(1)}" == requested


def parse_listing(xml_text: str, query: DataQuery) -> tuple[list[DownloadItem], str | None]:
    root = ET.fromstring(xml_text)
    items: list[DownloadItem] = []
    for node in root.findall("{*}Contents"):
        key = node.findtext("{*}Key", "")
        filename = key.rsplit("/", 1)[-1]
        year_match = _YEAR.search(filename)
        if not year_match or not _matches_version(filename, query.version):
            continue
        year = int(year_match.group(1))
        if query.start_year <= year <= query.end_year:
            url = f"{S3_ENDPOINT}/{urllib.parse.quote(key, safe='/')}"
            items.append(
                DownloadItem(
                    url=url,
                    filename=filename,
                    size=int(node.findtext("{*}Size", "0")),
                    source="nex-gddp-cmip6",
                )
            )
    return items, root.findtext("{*}NextContinuationToken")


def fetch_files(query: DataQuery, timeout: int = 60) -> list[DownloadItem]:
    prefix = "/".join(
        ["NEX-GDDP-CMIP6", query.model, query.experiment, query.member, query.variable, ""]
    )
    token: str | None = None
    found: list[DownloadItem] = []
    while True:
        params = {"list-type": "2", "prefix": prefix}
        if token:
            params["continuation-token"] = token
        url = f"{S3_ENDPOINT}/?{urllib.parse.urlencode(params)}"
        with open_url(url, timeout=timeout) as response:
            page, token = parse_listing(response.read().decode("utf-8"), query)
        found.extend(page)
        if not token:
            return found

