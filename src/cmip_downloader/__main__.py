import argparse
import sys
from pathlib import Path

from . import esgf, nex
from .app import format_size, launch
from .batch_cli import load_batch_job, run_batch_job
from .download import download_many
from .models import DataQuery


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="NEX-GDDP-CMIP6 / CMIP6 数据下载器")
    subparsers = parser.add_subparsers(dest="dataset")
    for name in ("nex", "cmip6"):
        command = subparsers.add_parser(name)
        command.add_argument("--model", required=True)
        command.add_argument("--experiment", required=True)
        command.add_argument("--member", required=True)
        command.add_argument("--variable", required=True)
        command.add_argument("--years", required=True, help="例如 2000:2014")
        command.add_argument("--table", default="day")
        command.add_argument("--version", default="v2.0")
        command.add_argument("--output", type=Path, default=Path("downloads"))
        command.add_argument("--workers", type=int, default=3)
        command.add_argument("--dry-run", action="store_true")
    batch = subparsers.add_parser("batch", help="从 JSON 配置批量查询、下载并整理数据包")
    batch.add_argument("--config", required=True, type=Path, help="批量任务 JSON 配置文件")
    batch.add_argument("--output", type=Path, help="覆盖配置文件中的输出目录")
    batch.add_argument("--workers", type=int, help="覆盖配置文件中的并发数")
    batch.add_argument("--dry-run", action="store_true", help="只查询/规划清单，不下载文件")
    return parser


def _run_cli(arguments) -> int:
    try:
        start, end = (int(value) for value in arguments.years.split(":", 1))
        query = DataQuery(
            arguments.model, arguments.experiment, arguments.member, arguments.variable,
            start, end, arguments.table, arguments.version,
        )
        items = nex.fetch_files(query) if arguments.dataset == "nex" else esgf.fetch_files(query)
    except (ValueError, OSError) as error:
        print(f"错误：{error}", file=sys.stderr)
        return 2
    print(f"匹配 {len(items)} 个文件，共 {format_size(sum(item.size for item in items))}")
    for item in items:
        print(f"{format_size(item.size):>10}  {item.filename}")
    if arguments.dry_run or not items:
        return 0
    completed, failed = download_many(items, arguments.output, arguments.workers)
    print(f"完成 {len(completed)}，失败 {len(failed)}")
    for filename, error in failed.items():
        print(f"失败：{filename}：{error}", file=sys.stderr)
    return 1 if failed else 0


def _run_batch_cli(arguments) -> int:
    try:
        job = load_batch_job(arguments.config, arguments.output, arguments.workers)
        result = run_batch_job(job, dry_run=arguments.dry_run)
    except (ValueError, OSError) as error:
        print(f"错误：{error}", file=sys.stderr)
        return 2
    action = "规划" if arguments.dry_run else "完成"
    print(
        f"批量任务{action}：清单 {result.planned_count} 个，"
        f"完成 {result.completed_count} 个，失败 {result.failed_count} 个。"
    )
    if result.package:
        print(f"数据包：{result.package}")
    return result.exit_code


def main() -> int:
    if len(sys.argv) == 1:
        launch()
        return 0
    arguments = _parser().parse_args()
    if arguments.dataset in {"nex", "cmip6"}:
        return _run_cli(arguments)
    if arguments.dataset == "batch":
        return _run_batch_cli(arguments)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
