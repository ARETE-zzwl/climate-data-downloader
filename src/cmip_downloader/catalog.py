import json
import urllib.parse
import urllib.request

from .esgf import SEARCH_ENDPOINT


NEX_MODELS = [
    "ACCESS-CM2", "ACCESS-ESM1-5", "BCC-CSM2-MR", "CESM2", "CESM2-WACCM",
    "CMCC-CM2-SR5", "CMCC-ESM2", "CNRM-CM6-1", "CNRM-ESM2-1", "CanESM5",
    "EC-Earth3", "EC-Earth3-Veg-LR", "FGOALS-g3", "GFDL-CM4", "GFDL-ESM4",
    "GISS-E2-1-G", "HadGEM3-GC31-LL", "HadGEM3-GC31-MM", "IITM-ESM",
    "INM-CM4-8", "INM-CM5-0", "IPSL-CM6A-LR", "KACE-1-0-G", "KIOST-ESM",
    "MIROC-ES2L", "MIROC6", "MPI-ESM1-2-HR", "MPI-ESM1-2-LR", "MRI-ESM2-0",
    "NESM3", "NorESM2-LM", "NorESM2-MM", "TaiESM1", "UKESM1-0-LL",
]
NEX_EXPERIMENTS = ["historical", "ssp126", "ssp245", "ssp370", "ssp585"]
NEX_VARIABLES = ["hurs", "huss", "pr", "rlds", "rsds", "sfcWind", "tas", "tasmax", "tasmin"]
ESGF_FACETS = ["source_id", "experiment_id", "variant_label", "variable_id", "table_id"]


def parse_facets(payload: dict) -> dict[str, list[str]]:
    fields = payload.get("facet_counts", {}).get("facet_fields", {})
    parsed: dict[str, list[str]] = {}
    for name, raw in fields.items():
        if isinstance(raw, dict):
            parsed[name] = list(raw)
        elif isinstance(raw, list):
            parsed[name] = [str(raw[index]) for index in range(0, len(raw), 2)]
    return parsed


def fetch_esgf_facets(timeout: int = 120) -> dict[str, list[str]]:
    params = {
        "type": "File",
        "project": "CMIP6",
        "latest": "true",
        "replica": "false",
        "facets": ",".join(ESGF_FACETS),
        "limit": "0",
        "format": "application/solr+json",
    }
    url = f"{SEARCH_ENDPOINT}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return parse_facets(json.load(response))
