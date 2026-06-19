from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from itertools import product
from typing import Callable, Iterable

from .models import DataQuery, DownloadItem


MAX_COMBINATIONS = 500


@dataclass(frozen=True)
class BatchSelection:
    dataset: str
    models: tuple[str, ...]
    experiments: tuple[str, ...]
    members: tuple[str, ...]
    variables: tuple[str, ...]
    tables: tuple[str, ...]
    start_year: int
    end_year: int
    version: str = "v2.0"

    def expand_queries(self) -> list[DataQuery]:
        dimensions = {
            "模式": self.models,
            "情景/试验": self.experiments,
            "成员": self.members,
            "变量": self.variables,
            "频率/table": self.tables,
        }
        for label, values in dimensions.items():
            if not values:
                raise ValueError(f"请至少选择一个{label}")
        tables = ("day",) if self.dataset == "nex" else self.tables
        count = (
            len(self.models)
            * len(self.experiments)
            * len(self.members)
            * len(self.variables)
            * len(tables)
        )
        if count > MAX_COMBINATIONS:
            raise ValueError(f"筛选组合达到 {count} 个，超过安全上限 {MAX_COMBINATIONS}")
        return [
            DataQuery(
                model=model,
                experiment=experiment,
                member=member,
                variable=variable,
                start_year=self.start_year,
                end_year=self.end_year,
                table=table,
                version=self.version,
            )
            for model, experiment, member, variable, table in product(
                self.models, self.experiments, self.members, self.variables, tables
            )
        ]


@dataclass(frozen=True)
class PlannedItem:
    dataset: str
    query: object
    item: DownloadItem


def merge_query_results(
    dataset: str,
    results: Iterable[tuple[object, list[DownloadItem]]],
) -> list[PlannedItem]:
    merged: dict[tuple[str, int, str], PlannedItem] = {}
    for query, items in results:
        for item in items:
            identity = (item.filename, item.size, item.checksum or item.url)
            merged.setdefault(identity, PlannedItem(dataset, query, item))
    return sorted(merged.values(), key=lambda planned: planned.item.filename)


def fetch_batch(
    selection: BatchSelection,
    fetcher: Callable[[DataQuery], list[DownloadItem]],
    workers: int = 4,
) -> tuple[list[PlannedItem], dict[DataQuery, Exception]]:
    return fetch_queries(selection.dataset, selection.expand_queries(), fetcher, workers)


def fetch_queries(
    dataset: str,
    queries: Iterable[object],
    fetcher: Callable[[object], list[DownloadItem]],
    workers: int = 4,
) -> tuple[list[PlannedItem], dict[object, Exception]]:
    results: list[tuple[object, list[DownloadItem]]] = []
    failed: dict[object, Exception] = {}
    query_list = list(queries)
    if not query_list:
        return [], {}
    with ThreadPoolExecutor(max_workers=min(max(1, workers), len(query_list))) as executor:
        futures = {executor.submit(fetcher, query): query for query in query_list}
        for future in as_completed(futures):
            query = futures[future]
            try:
                results.append((query, future.result()))
            except Exception as error:
                failed[query] = error
    return merge_query_results(dataset, results), failed
