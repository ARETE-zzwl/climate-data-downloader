from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DataQuery:
    model: str
    experiment: str
    member: str
    variable: str
    start_year: int
    end_year: int
    table: str = "day"
    version: str = "v2.0"

    def __post_init__(self) -> None:
        required = {
            "模式": self.model,
            "情景/试验": self.experiment,
            "成员": self.member,
            "变量": self.variable,
        }
        for label, value in required.items():
            if not value.strip():
                raise ValueError(f"{label}不能为空")
        if self.start_year > self.end_year:
            raise ValueError("起始年份不能晚于结束年份")


@dataclass(frozen=True)
class DownloadItem:
    url: str
    filename: str
    size: int
    checksum: str | None = None
    checksum_type: str | None = None
    source: str = ""
    relative_dir: str | None = None

    def target_path(self, output: Path) -> Path:
        relative = Path(self.relative_dir or self.source)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("下载目录必须是安全的相对路径")
        if self.filename in {"", ".", ".."} or Path(self.filename).name != self.filename:
            raise ValueError("下载文件名不安全")
        return output / relative / self.filename
