import queue
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from tkinter import BooleanVar, StringVar, Text, Tk, filedialog, messagebox
from tkinter import ttk

from . import cordex, esgf, nex, noaa
from .batch import PlannedItem, fetch_batch
from .catalog import NEX_EXPERIMENTS, NEX_MODELS, NEX_VARIABLES, fetch_esgf_facets
from .era5 import AVAILABILITY_MESSAGE
from .form import BatchDownloadRequest, BatchFormData
from .multi_select import MultiSelectField
from .tasks import create_task, load_task, run_task
from .progress import ProgressBuffer
from .power import POWER_VARIABLES, PowerSelection, plan_files
from .process import ProcessOptions


DATASETS = {
    "NEX-GDDP-CMIP6（降尺度）": "nex",
    "CMIP6（原始模式数据）": "cmip6",
    "CORDEX（区域气候模式）": "cordex",
    "NASA POWER（气象与太阳能）": "power",
    "NOAA CPC（全球逐日降水）": "noaa_cpc",
    "NOAA NCEP/NCAR（逐日再分析）": "noaa_ncep",
    "ERA5 / ERA5-Land（预留）": "era5",
}
TEMPORAL_SCALES = {"保持原尺度": "original", "日": "daily", "月": "monthly", "年": "annual"}
AGGREGATIONS = {"平均值": "mean", "求和": "sum", "最小值": "min", "最大值": "max"}

CMIP_TABLES = ["day", "Amon", "Omon", "3hr", "6hrLev", "fx"]
CMIP_MEMBERS = ["r1i1p1f1", "r2i1p1f1", "r3i1p1f1"]
CORDEX_DOMAINS = ["SEA-22", "EUR-11", "EUR-44", "EAS-22", "EAS-44", "AFR-22", "NAM-22", "AUS-22"]
CORDEX_MODELS = ["MOHC-HadGEM2-ES", "CNRM-CERFACS-CNRM-CM5", "ECMWF-ERAINT", "MPI-M-MPI-ESM-LR"]
CORDEX_RCMS = ["不限", "HadRM3P", "ALADIN63", "CCLM4-8-17", "RCA4", "REMO2009"]
CORDEX_EXPERIMENTS = ["evaluation", "historical", "rcp26", "rcp45", "rcp85"]
CORDEX_MEMBERS = ["r1i1p1", "r0i0p0"]
CORDEX_VARIABLES = ["tas", "tasmax", "tasmin", "pr", "areacella"]
CORDEX_FREQUENCIES = ["day", "mon", "fx", "3hr", "6hr"]


def format_size(size: int) -> str:
    if not size:
        return "服务器生成"
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TiB"


class ClimateDownloaderApp:
    def __init__(self, root: Tk):
        self.root = root
        self.events: queue.Queue = queue.Queue()
        self.items: list[PlannedItem] = []
        self.current_request: BatchDownloadRequest | None = None
        self.query_failures: dict[object, Exception] = {}
        self.downloaded: dict[str, int] = {}
        self.total_bytes = 0
        self.progress_buffer = ProgressBuffer()
        self.stop_event = threading.Event()
        self.busy = False
        self.downloading = False
        self.active_package = None
        self.last_activity = time.monotonic()
        self.speed_time = self.last_activity
        self.speed_bytes = 0
        self._variables()
        self._configure_window()
        self._build_ui()
        self._dataset_changed()
        self.root.after(100, self._poll_events)
        self.root.protocol('WM_DELETE_WINDOW', self._close)

    def _variables(self) -> None:
        home = Path.home() / "climate-data"
        self.dataset = StringVar(value=next(iter(DATASETS)))
        self.version = StringVar(value="v2.0")
        self.start_year = StringVar(value="2000")
        self.end_year = StringVar(value="2014")
        self.global_area = BooleanVar(value=True)
        self.west = StringVar(value="73")
        self.east = StringVar(value="136")
        self.south = StringVar(value="18")
        self.north = StringVar(value="54")
        self.resolution = StringVar(value="原始")
        self.temporal_scale = StringVar(value="保持原尺度")
        self.aggregation = StringVar(value="平均值")
        self.output = StringVar(value=str(home))
        self.workers = StringVar(value="3")
        self.connection = StringVar(value='直连' if os.environ.get('CLIMATE_DIRECT') == '1' else '系统代理')
        self.keep_raw = BooleanVar(value=True)
        self.summary = StringVar(value="尚未查询文件清单")
        self.status = StringVar(value="就绪")

    def _configure_window(self) -> None:
        self.root.title("气候数据下载器 · 多源批量版")
        self.root.geometry("1260x820")
        self.root.minsize(1040, 700)
        self.root.configure(bg="#edf2f1")
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("TFrame", background="#edf2f1")
        style.configure("Surface.TFrame", background="#ffffff")
        style.configure("Header.TFrame", background="#193f46")
        style.configure("Header.TLabel", background="#193f46", foreground="#ffffff", font=("Microsoft YaHei UI", 18, "bold"))
        style.configure("Subheader.TLabel", background="#193f46", foreground="#c9dedb", font=("Microsoft YaHei UI", 9))
        style.configure("Section.TLabel", background="#ffffff", foreground="#193f46", font=("Microsoft YaHei UI", 11, "bold"))
        style.configure("Hint.TLabel", background="#ffffff", foreground="#5d6f72", font=("Microsoft YaHei UI", 9))
        style.configure("Accent.TButton", background="#147d78", foreground="#ffffff", font=("Microsoft YaHei UI", 10, "bold"), padding=(14, 8))
        style.map("Accent.TButton", background=[("active", "#0f6864"), ("disabled", "#8da9a7")])
        style.configure("TButton", padding=(10, 6))
        style.configure("Treeview", rowheight=27, font=("Microsoft YaHei UI", 9))
        style.configure("Treeview.Heading", font=("Microsoft YaHei UI", 9, "bold"))

    def _build_ui(self) -> None:
        header = ttk.Frame(self.root, style="Header.TFrame", padding=(24, 16))
        header.pack(fill="x")
        ttk.Label(header, text="气候数据下载器", style="Header.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="NEX · CMIP6 · CORDEX · NASA POWER · NOAA｜批量下载与任务恢复",
            style="Subheader.TLabel",
        ).pack(anchor="w", pady=(3, 0))

        body = ttk.Frame(self.root, padding=14)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=0, minsize=430)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)
        left = ttk.Frame(body, style="Surface.TFrame", padding=12)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        right = ttk.Frame(body, style="Surface.TFrame", padding=12)
        right.grid(row=0, column=1, sticky="nsew")
        self._build_filters(left)
        self._build_results(right)
        self._build_footer()

    def _build_filters(self, parent) -> None:
        notebook = ttk.Notebook(parent)
        notebook.pack(fill="both", expand=True)
        data_tab = ttk.Frame(notebook, style="Surface.TFrame", padding=12)
        output_tab = ttk.Frame(notebook, style="Surface.TFrame", padding=12)
        notebook.add(data_tab, text=" 数据筛选 ")
        notebook.add(output_tab, text=" 范围与输出 ")
        for tab in (data_tab, output_tab):
            tab.columnconfigure(1, weight=1)

        self.dataset_box = self._combo(data_tab, 0, "数据源", self.dataset, list(DATASETS), readonly=True)
        self.dataset_box.bind("<<ComboboxSelected>>", lambda _event: self._dataset_changed())
        self.domain_label, self.domain_field = self._multi(data_tab, 1, "区域域", CORDEX_DOMAINS)
        self.model_label, self.model_field = self._multi(data_tab, 2, "模式", NEX_MODELS)
        self.rcm_label, self.rcm_field = self._multi(data_tab, 3, "区域模式 RCM", CORDEX_RCMS)
        self.experiment_label, self.experiment_field = self._multi(data_tab, 4, "情景 / 试验", NEX_EXPERIMENTS)
        self.member_label, self.member_field = self._multi(data_tab, 5, "成员", ["r1i1p1f1"])
        self.variable_label, self.variable_field = self._multi(data_tab, 6, "变量", NEX_VARIABLES)
        self.table_label, self.table_field = self._multi(data_tab, 7, "频率 / table", ["day"])
        self.version_box = self._combo(data_tab, 8, "NEX 版本", self.version, ["v2.0", "v1.1", "original"], readonly=True)
        self._entry(data_tab, 9, "起始年份", self.start_year)
        self._entry(data_tab, 10, "结束年份", self.end_year)
        self.source_hint = ttk.Label(data_tab, style="Hint.TLabel", wraplength=360, justify="left")
        self.source_hint.grid(row=11, column=0, columnspan=2, sticky="ew", pady=(10, 8))
        self.refresh_button = ttk.Button(data_tab, text="刷新官方可选项", command=self._refresh_catalog)
        self.refresh_button.grid(row=12, column=0, columnspan=2, sticky="ew", pady=(4, 0))

        global_check = ttk.Checkbutton(
            output_tab,
            text="全球范围（取消勾选后填写矩形经纬度）",
            variable=self.global_area,
            command=self._toggle_bbox,
        )
        global_check.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        self.global_check = global_check
        bbox = ttk.Frame(output_tab, style="Surface.TFrame")
        bbox.grid(row=1, column=0, columnspan=2, sticky="ew")
        for column in range(4):
            bbox.columnconfigure(column, weight=1)
        self.bbox_entries = []
        for column, (label, variable) in enumerate(
            [("西经度", self.west), ("东经度", self.east), ("南纬度", self.south), ("北纬度", self.north)]
        ):
            ttk.Label(bbox, text=label).grid(row=0, column=column, sticky="w", padx=(0, 5))
            entry = ttk.Entry(bbox, textvariable=variable, width=8)
            entry.grid(row=1, column=column, sticky="ew", padx=(0, 5))
            self.bbox_entries.append(entry)
        self.resolution_box = self._combo(
            output_tab, 2, "输出空间分辨率", self.resolution,
            ["原始", "0.1", "0.25", "0.5", "1.0", "2.0"],
        )
        self.temporal_box = self._combo(
            output_tab, 3, "输出时间尺度", self.temporal_scale, list(TEMPORAL_SCALES), readonly=True,
        )
        self.aggregation_box = self._combo(
            output_tab, 4, "聚合方式", self.aggregation, list(AGGREGATIONS), readonly=True,
        )
        ttk.Label(
            output_tab,
            text="重采样只改变网格间距，不会提高真实物理精度。NASA POWER 的区域接口要求经纬度各至少跨越 2°。",
            style="Hint.TLabel", wraplength=360, justify="left",
        ).grid(row=5, column=0, columnspan=2, sticky="ew", pady=(10, 8))
        ttk.Label(output_tab, text="输出目录").grid(row=6, column=0, sticky="w", pady=5)
        output_row = ttk.Frame(output_tab, style="Surface.TFrame")
        output_row.grid(row=6, column=1, sticky="ew", pady=5)
        output_row.columnconfigure(0, weight=1)
        ttk.Entry(output_row, textvariable=self.output).grid(row=0, column=0, sticky="ew")
        ttk.Button(output_row, text="浏览", command=self._browse_output).grid(row=0, column=1, padx=(5, 0))
        self._combo(output_tab, 7, "并发下载数", self.workers, [str(number) for number in range(1, 9)], readonly=True)
        self.connection_box = self._combo(output_tab, 9, '连接方式', self.connection, ['系统代理', '直连'], readonly=True)
        ttk.Checkbutton(output_tab, text="处理完成后保留原始文件", variable=self.keep_raw).grid(
            row=8, column=0, columnspan=2, sticky="w", pady=(8, 0)
        )
        self._toggle_bbox()

    def _build_results(self, parent) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(2, weight=1)
        ttk.Label(parent, text="文件清单", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(parent, textvariable=self.summary, style="Hint.TLabel").grid(row=1, column=0, sticky="w", pady=(2, 8))
        table_frame = ttk.Frame(parent, style="Surface.TFrame")
        table_frame.grid(row=2, column=0, sticky="nsew")
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(
            table_frame, columns=("name", "size", "source", "selection"), show="headings", selectmode="browse"
        )
        for name, label in (("name", "文件名"), ("size", "大小"), ("source", "来源"), ("selection", "所属组合")):
            self.tree.heading(name, text=label)
        self.tree.column("name", width=390, anchor="w")
        self.tree.column("size", width=95, anchor="e")
        self.tree.column("source", width=100, anchor="center")
        self.tree.column("selection", width=240, anchor="w")
        scroll_y = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        scroll_x = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll_y.grid(row=0, column=1, sticky="ns")
        scroll_x.grid(row=1, column=0, sticky="ew")
        ttk.Label(parent, text="任务日志", style="Section.TLabel").grid(row=3, column=0, sticky="w", pady=(12, 5))
        self.log = Text(
            parent, height=8, bg="#f6f8f8", fg="#29484d", relief="flat", padx=8, pady=6,
            font=("Consolas", 9), state="disabled", wrap="word",
        )
        self.log.grid(row=4, column=0, sticky="ew")

    def _build_footer(self) -> None:
        footer = ttk.Frame(self.root, padding=(14, 0, 14, 14))
        footer.pack(fill="x")
        footer.columnconfigure(0, weight=1)
        self.progress = ttk.Progressbar(footer, mode="determinate", maximum=100)
        self.progress.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        ttk.Label(footer, textvariable=self.status, wraplength=1100).grid(row=1, column=0, columnspan=6, sticky='w', pady=(8, 0))
        self.preview_button = ttk.Button(footer, text="1. 查询清单", command=self._preview)
        self.preview_button.grid(row=0, column=2, padx=(0, 8))
        self.download_button = ttk.Button(footer, text="2. 下载并整理", style="Accent.TButton", command=self._start_download)
        self.download_button.grid(row=0, column=3)
        self.resume_button = ttk.Button(footer, text='恢复任务…', command=self._resume_task)
        self.resume_button.grid(row=0, column=4, padx=8)
        self.pause_button = ttk.Button(footer, text='暂停', command=self._pause_task, state='disabled')
        self.pause_button.grid(row=0, column=5)

    def _combo(self, parent, row, label, variable, values, readonly=False):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=5, padx=(0, 8))
        box = ttk.Combobox(parent, textvariable=variable, values=values, state="readonly" if readonly else "normal")
        box.grid(row=row, column=1, sticky="ew", pady=5)
        return box

    def _entry(self, parent, row, label, variable):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=5, padx=(0, 8))
        entry = ttk.Entry(parent, textvariable=variable)
        entry.grid(row=row, column=1, sticky="ew", pady=5)
        return entry

    def _multi(self, parent, row, label, values):
        label_widget = ttk.Label(parent, text=label)
        label_widget.grid(row=row, column=0, sticky="w", pady=5, padx=(0, 8))
        field = MultiSelectField(parent, values, on_change=self._invalidate_preview)
        field.grid(row=row, column=1, sticky="ew", pady=5)
        return label_widget, field

    def _show_filter(self, label, field, visible: bool) -> None:
        if visible:
            label.grid()
            field.grid()
        else:
            label.grid_remove()
            field.grid_remove()

    def _dataset_changed(self) -> None:
        dataset = DATASETS[self.dataset.get()]
        for label, field in (
            (self.model_label, self.model_field),
            (self.experiment_label, self.experiment_field),
            (self.member_label, self.member_field),
            (self.variable_label, self.variable_field),
            (self.table_label, self.table_field),
        ):
            self._show_filter(label, field, True)
            field.configure(state="normal")
        self._show_filter(self.domain_label, self.domain_field, dataset == "cordex")
        self._show_filter(self.rcm_label, self.rcm_field, dataset == "cordex")
        self.version_box.configure(state="disabled")
        self.global_check.configure(state="normal")
        if dataset not in {"power", "era5"}:
            self.global_area.set(True)

        if dataset == "nex":
            self.model_field.set_values(NEX_MODELS, ["ACCESS-CM2"])
            self.experiment_field.set_values(NEX_EXPERIMENTS, ["historical"])
            self.member_field.set_values(["r1i1p1f1"], ["r1i1p1f1"])
            self.variable_field.set_values(NEX_VARIABLES, ["pr"])
            self.table_field.set_values(["day"], ["day"])
            self.table_field.configure(state="disabled")
            self.version_box.configure(state="readonly")
            self.source_hint.configure(text="NEX：NASA NCCS / AWS Open Data 官方镜像的 0.25° 日尺度降尺度数据。模式、情景和变量可多选。")
        elif dataset == "cmip6":
            self.model_field.set_values(NEX_MODELS, ["ACCESS-CM2"])
            self.experiment_field.set_values(NEX_EXPERIMENTS, ["historical"])
            self.member_field.set_values(CMIP_MEMBERS, ["r1i1p1f1"])
            self.variable_field.set_values(NEX_VARIABLES, ["tas"])
            self.table_field.set_values(CMIP_TABLES, ["day"])
            self.source_hint.configure(text="CMIP6：LLNL ESGF 官方联邦索引；五类筛选均可多选，刷新可获得完整候选列表。")
        elif dataset == "cordex":
            self.domain_field.set_values(CORDEX_DOMAINS, ["SEA-22"])
            self.model_field.set_values(CORDEX_MODELS, ["MOHC-HadGEM2-ES"])
            self.rcm_field.set_values(CORDEX_RCMS, ["不限"])
            self.experiment_field.set_values(CORDEX_EXPERIMENTS, ["rcp26"])
            self.member_field.set_values(CORDEX_MEMBERS, ["r0i0p0"])
            self.variable_field.set_values(CORDEX_VARIABLES, ["areacella"])
            self.table_field.set_values(CORDEX_FREQUENCIES, ["fx"])
            self.source_hint.configure(text="CORDEX：WCRP 区域气候数据，通过 DKRZ ESGF 官方索引检索；区域域、驱动模式和 RCM 可独立多选。")
        elif dataset in noaa.VARIABLES:
            for label, field in ((self.model_label, self.model_field),
                                 (self.experiment_label, self.experiment_field),
                                 (self.member_label, self.member_field)):
                self._show_filter(label, field, False)
            self.variable_field.set_values(noaa.VARIABLES[dataset], [noaa.VARIABLES[dataset][0]])
            self.table_field.set_values(['day'], ['day'])
            self.table_field.configure(state='disabled')
            hint = ('CPC：0.5° 全球陆地站点分析降水，1979 年起，precip 单位 mm/day。'
                    if dataset == 'noaa_cpc' else
                    'NCEP/NCAR：2.5° 逐日再分析，1948 年起。air 为 sigma=0.995 近地面气温（不是 2m 气温）；slp 为海平面气压。')
            self.source_hint.configure(text=hint + ' NOAA PSL 官方 NetCDF，按年下载；区域裁剪在本地执行。')
        elif dataset == "power":
            for label, field in (
                (self.model_label, self.model_field),
                (self.experiment_label, self.experiment_field),
                (self.member_label, self.member_field),
            ):
                self._show_filter(label, field, False)
            self.variable_field.set_values(POWER_VARIABLES, ["T2M"])
            self.table_field.set_values(["daily", "monthly"], ["daily"])
            self.global_area.set(False)
            self.west.set("116")
            self.east.set("118")
            self.south.set("38")
            self.north.set("40")
            self.source_hint.configure(text="NASA POWER：NASA LaRC 官方 API，无需密钥。区域请求会为每个变量分别生成 NetCDF，再统一整理。")
        else:
            for label, field in (
                (self.model_label, self.model_field), (self.experiment_label, self.experiment_field),
                (self.member_label, self.member_field), (self.variable_label, self.variable_field),
                (self.table_label, self.table_field),
            ):
                self._show_filter(label, field, False)
            self.source_hint.configure(text=AVAILABILITY_MESSAGE)
            self.refresh_button.configure(state="disabled")
        self._toggle_bbox()
        self._invalidate_preview()
        reserved = dataset == "era5"
        self.preview_button.configure(state="disabled" if reserved else "normal")
        self.download_button.configure(state="disabled" if reserved else "normal")
        if not reserved:
            self.refresh_button.configure(state="normal")

    def _toggle_bbox(self) -> None:
        state = "disabled" if self.global_area.get() else "normal"
        for entry in getattr(self, "bbox_entries", []):
            entry.configure(state=state)

    def _browse_output(self) -> None:
        selected = filedialog.askdirectory(initialdir=self.output.get() or str(Path.home()))
        if selected:
            self.output.set(selected)

    def _common_values(self):
        try:
            start, end, workers = int(self.start_year.get()), int(self.end_year.get()), int(self.workers.get())
        except ValueError as error:
            raise ValueError("年份和并发数必须是整数") from error
        if start > end:
            raise ValueError("起始年份不能晚于结束年份")
        if not 1 <= workers <= 16:
            raise ValueError("并发数必须位于 1 到 16 之间")
        output = Path(self.output.get()).expanduser()
        parent = output if output.exists() else output.parent
        if not parent.exists():
            raise ValueError("输出目录的上级目录不存在")
        bbox = None
        if not self.global_area.get():
            try:
                bbox = tuple(float(value.get()) for value in (self.west, self.east, self.south, self.north))
            except ValueError as error:
                raise ValueError("经纬度必须是数字") from error
        resolution_text = self.resolution.get().strip()
        try:
            resolution = None if resolution_text == "原始" else float(resolution_text)
        except ValueError as error:
            raise ValueError("空间分辨率必须是数字") from error
        process = ProcessOptions(
            bbox=bbox,
            spatial_resolution=resolution,
            temporal_scale=TEMPORAL_SCALES[self.temporal_scale.get()],
            aggregation=AGGREGATIONS[self.aggregation.get()],
        )
        return start, end, workers, output, bbox, process

    def _validated_request(self) -> BatchDownloadRequest | None:
        self._apply_connection()
        dataset = DATASETS[self.dataset.get()]
        if dataset == "era5":
            messagebox.showinfo("ERA5 预留入口", AVAILABILITY_MESSAGE, parent=self.root)
            return None
        try:
            start, end, workers, output, bbox, process = self._common_values()
            if dataset in {"nex", "cmip6"}:
                request = BatchFormData(
                    dataset=dataset,
                    models=self.model_field.get(), experiments=self.experiment_field.get(),
                    members=self.member_field.get(), variables=self.variable_field.get(), tables=self.table_field.get(),
                    version=self.version.get(), start_year=str(start), end_year=str(end),
                    global_area=self.global_area.get(), west=self.west.get(), east=self.east.get(),
                    south=self.south.get(), north=self.north.get(),
                    resolution="original" if self.resolution.get() == "原始" else self.resolution.get(),
                    temporal_scale=TEMPORAL_SCALES[self.temporal_scale.get()],
                    aggregation=AGGREGATIONS[self.aggregation.get()], output=str(output),
                    workers=str(workers), keep_raw=self.keep_raw.get(),
                ).to_request()
            elif dataset == "cordex":
                selection = cordex.CordexSelection(
                    self.domain_field.get(), self.model_field.get(), self.experiment_field.get(),
                    self.member_field.get(), self.rcm_field.get(), self.variable_field.get(),
                    self.table_field.get(), start, end,
                )
                selection.expand_queries()
                request = BatchDownloadRequest(selection, process, output, workers, self.keep_raw.get())
            elif dataset in noaa.VARIABLES:
                selection = noaa.NoaaSelection(dataset, self.variable_field.get(), start, end)
                selection.expand_queries()
                request = BatchDownloadRequest(selection, process, output, workers, self.keep_raw.get())
            else:
                if bbox is None:
                    raise ValueError("NASA POWER 必须取消全球范围并填写矩形区域")
                west, east, south, north = bbox
                selection = PowerSelection(
                    self.variable_field.get(), self.table_field.get(), start, end,
                    west, east, south, north,
                )
                selection.expand_queries()
                power_process = ProcessOptions(
                    bbox=None,
                    spatial_resolution=process.spatial_resolution,
                    temporal_scale=process.temporal_scale,
                    aggregation=process.aggregation,
                )
                request = BatchDownloadRequest(selection, power_process, output, workers, self.keep_raw.get())
            return request
        except ValueError as error:
            messagebox.showerror("参数有误", str(error), parent=self.root)
            return None

    def _invalidate_preview(self) -> None:
        self.items = []
        self.current_request = None
        if hasattr(self, "summary"):
            self.summary.set("筛选条件已变化，请重新查询")

    def _refresh_catalog(self) -> None:
        self._apply_connection()
        dataset = DATASETS[self.dataset.get()]
        if dataset in {"nex", "power", *noaa.VARIABLES}:
            self._dataset_changed()
            self._write_log("已加载数据源官方变量与筛选列表。")
        elif dataset == "cmip6":
            self._start_worker("catalog", lambda: (dataset, fetch_esgf_facets()), "正在刷新 CMIP6 可选项…")
        elif dataset == "cordex":
            self._start_worker("catalog", lambda: (dataset, cordex.fetch_facets()), "正在刷新 CORDEX 可选项…")

    def _preview(self) -> None:
        request = self._validated_request()
        if not request:
            return

        def query():
            if request.dataset in {"nex", "cmip6"}:
                fetcher = nex.fetch_files if request.dataset == "nex" else esgf.fetch_files
                items, failed = fetch_batch(request.selection, fetcher, request.workers)
            elif request.dataset == "cordex":
                items, failed = cordex.fetch_batch(request.selection, request.workers)
            elif request.dataset in noaa.VARIABLES:
                items, failed = fetch_batch(request.selection, noaa.fetch_files, request.workers)
            else:
                items, failed = plan_files(request.selection), {}
            return request, items, failed

        count = len(request.selection.expand_queries())
        self._start_worker("preview", query, f"正在查询 {count} 个筛选组合…")

    def _start_download(self) -> None:
        request = self._validated_request()
        if not request:
            return
        if not self.items or request != self.current_request:
            messagebox.showinfo("请先查询", "筛选条件发生过变化，请先点击“查询清单”。", parent=self.root)
            return
        known_total = sum(planned.item.size for planned in self.items)
        unknown = sum(not planned.item.size for planned in self.items)
        size = format_size(known_total) if known_total else "由服务器生成"
        extra = f"，其中 {unknown} 个文件大小由服务器生成" if unknown else ""
        processing = "，下载后将执行裁剪/重采样/聚合" if request.needs_processing else ""
        if not messagebox.askyesno(
            "确认下载",
            f"将下载 {len(self.items)} 个文件，已知大小 {size}{extra}{processing}。完成后自动生成清单和 SHA256。是否继续？",
            parent=self.root,
        ):
            return
        self.downloaded = {}
        self.total_bytes = 0 if unknown else known_total
        self.progress["value"] = 0
        self._begin_transfer()
        items, query_failures = list(self.items), dict(self.query_failures)
        self._start_worker(
            "download",
            lambda: self._download_job(request, items, query_failures),
            "正在下载并整理…",
        )

    def _download_job(
        self,
        request: BatchDownloadRequest,
        items: list[PlannedItem],
        query_failures: dict[object, Exception],
    ):
        package = create_task(request.output, items, request.selection, request.process,
                              request.keep_raw, query_failures)
        self.active_package = package
        self.events.put(('log', f'任务已保存，可从此目录恢复：{package}'))
        return self._run_saved(package, request.workers)

    def _run_saved(self, package, workers):
        return run_task(package, workers, self._download_progress, self.stop_event,
                        lambda message: self.events.put(('log', message)))

    def _begin_transfer(self):
        self.stop_event.clear()
        self.progress_buffer.take()
        self.downloading = True
        self.last_activity = self.speed_time = time.monotonic()
        self.speed_bytes = 0
        self.pause_button.configure(state='normal')

    def _resume_task(self):
        self._apply_connection()
        selected = filedialog.askdirectory(title='选择含 task.json 的数据包', initialdir=self.output.get())
        if not selected:
            return
        try:
            task = load_task(Path(selected))
            workers = int(self.workers.get())
        except (ValueError, OSError, KeyError, TypeError) as error:
            messagebox.showerror('无法恢复', str(error), parent=self.root)
            return
        if not messagebox.askyesno('恢复任务', f'恢复 {len(task["planned"])} 个文件，跳过已有文件，继续使用保存的处理参数。\n{selected}', parent=self.root):
            return
        self.active_package = Path(selected)
        self.total_bytes = sum(p.item.size for p in task['planned']) if all(p.item.size for p in task['planned']) else 0
        self.downloaded = {}
        self._begin_transfer()
        self._start_worker('download', lambda: self._run_saved(Path(selected), workers), '正在恢复原数据包…')

    def _pause_task(self):
        self.stop_event.set()
        self.pause_button.configure(state='disabled')
        self.status.set('正在暂停，等待当前网络读取/处理结束；已下载文件会保留')

    def _apply_connection(self):
        os.environ['CLIMATE_DIRECT'] = '1' if self.connection.get() == '直连' else '0'

    def _close(self):
        if self.busy and not messagebox.askyesno('关闭程序', '任务仍在运行。关闭将中断任务；下载任务可通过“恢复任务”继续。是否关闭？', parent=self.root):
            return
        self.stop_event.set()
        self.root.destroy()

    def _download_progress(self, filename: str, downloaded: int, total: int) -> None:
        self.progress_buffer.put(filename, downloaded, total)

    def _start_worker(self, event_name: str, function, status: str) -> None:
        self._set_busy(True, status)

        def run():
            try:
                self.events.put((event_name, function()))
            except Exception as error:
                self.events.put(("error", event_name, error))
            finally:
                self.events.put(("busy", False))

        threading.Thread(target=run, daemon=True).start()

    def _poll_events(self) -> None:
        for filename, (downloaded, total) in self.progress_buffer.take().items():
            self._progress_ready(filename, downloaded, total)
        try:
            while True:
                event = self.events.get_nowait()
                kind = event[0]
                if kind == "catalog":
                    self._catalog_ready(*event[1])
                elif kind == "preview":
                    self._preview_ready(*event[1])
                elif kind == "download":
                    self._download_ready(*event[1])
                elif kind == "progress":
                    self._progress_ready(*event[1:])
                elif kind == "log":
                    self._write_log(event[1])
                    self.status.set(event[1])
                elif kind == "error":
                    self._show_worker_error(event[1], event[2])
                elif kind == "busy":
                    self._set_busy(event[1], "就绪")
        except queue.Empty:
            pass
        if self.downloading and not self.stop_event.is_set() and time.monotonic() - self.last_activity > 30:
            self.status.set('暂未收到新数据；请查看日志中的连接/重试/处理状态，可暂停后恢复')
        self.root.after(100, self._poll_events)

    def _catalog_ready(self, dataset: str, facets: dict[str, list[str]]) -> None:
        if dataset != DATASETS[self.dataset.get()]:
            return
        if dataset == "cmip6":
            mapping = (
                (self.model_field, "source_id"), (self.experiment_field, "experiment_id"),
                (self.member_field, "variant_label"), (self.variable_field, "variable_id"),
                (self.table_field, "table_id"),
            )
        else:
            mapping = (
                (self.domain_field, "domain"), (self.model_field, "driving_model"),
                (self.experiment_field, "experiment"), (self.member_field, "ensemble"),
                (self.rcm_field, "rcm_name"), (self.variable_field, "variable"),
                (self.table_field, "time_frequency"),
            )
        for widget, key in mapping:
            if facets.get(key):
                current = widget.get()
                values = facets[key]
                if dataset == "cordex" and key == "rcm_name":
                    values = ["不限", *values]
                widget.set_values(values, current)
        self._write_log(f"{dataset.upper()} 官方可选项刷新完成。")

    def _query_summary(self, query: object) -> str:
        if hasattr(query, "model"):
            return f"{query.model} · {query.experiment} · {query.variable}"
        if hasattr(query, "driving_model"):
            return f"{query.domain} · {query.rcm_name} · {query.variable}"
        return f"{query.variable} · {query.temporal}"

    def _preview_ready(
        self,
        request: BatchDownloadRequest,
        items: list[PlannedItem],
        query_failures: dict[object, Exception],
    ) -> None:
        self.items = items
        self.current_request = request
        self.query_failures = query_failures
        for row in self.tree.get_children():
            self.tree.delete(row)
        for planned in items:
            item = planned.item
            self.tree.insert(
                "", "end",
                values=(item.filename, format_size(item.size), item.source, self._query_summary(planned.query)),
            )
        total = sum(planned.item.size for planned in items)
        unknown = sum(not planned.item.size for planned in items)
        size_text = format_size(total) if total else "大小由服务器生成"
        failed_text = f" · {len(query_failures)} 个组合查询失败" if query_failures else ""
        unknown_text = f" · {unknown} 个大小待生成" if unknown else ""
        self.summary.set(f"匹配 {len(items)} 个文件 · {size_text}{unknown_text}{failed_text} · 输出到 {request.output}")
        self._write_log(f"查询完成：{len(items)} 个文件，{len(query_failures)} 个组合失败。")
        if not items:
            messagebox.showinfo("没有匹配项", "当前组合没有找到可下载文件，请调整筛选条件或年份。", parent=self.root)

    def _progress_ready(self, filename: str, downloaded: int, total: int) -> None:
        now = time.monotonic()
        previous = self.downloaded.get(filename, downloaded)
        delta = max(0, downloaded - previous)
        self.speed_bytes += delta
        if delta:
            self.last_activity = now
        self.downloaded[filename] = downloaded
        if self.total_bytes:
            self.progress["value"] = min(100, sum(self.downloaded.values()) * 100 / self.total_bytes)
        elif total:
            self.progress["value"] = min(99, downloaded * 100 / total)
        elapsed = max(0.1, now - self.speed_time)
        speed = self.speed_bytes / elapsed
        self.status.set(f'累计 {format_size(sum(self.downloaded.values()))} / {format_size(self.total_bytes)} · {speed / 1048576:.2f} MiB/s · {filename}')
        if elapsed > 3:
            self.speed_time, self.speed_bytes = now, 0

    def _download_ready(self, package, completed, failed, processed, process_failed) -> None:
        self.downloading = False
        if self.stop_event.is_set():
            self._write_log(f'任务已暂停，已完成 {len(completed)} 个文件。恢复目录：{package}')
            return
        query_failed = load_task(package)['data'].get('query_failures', {})
        self.progress["value"] = 100 if not failed else self.progress["value"]
        self._write_log(
            f"数据包结束：成功 {len(completed)}，失败 {len(failed)}；处理输出 {len(processed)}，处理失败 {len(process_failed)}；查询失败 {len(query_failed)}。"
        )
        self._write_log(f"数据包：{package}")
        for filename, error in {**failed, **process_failed}.items():
            self._write_log(f"失败 · {filename} · {error}")
        if failed or process_failed or query_failed:
            messagebox.showwarning("任务部分完成", f"部分文件或查询失败；已保留成功文件和报告：\n{package}", parent=self.root)
        else:
            messagebox.showinfo("任务完成", f"数据包、清单和 SHA256 已生成：\n{package}", parent=self.root)

    def _show_worker_error(self, action: str, error: Exception) -> None:
        labels = {"catalog": "刷新可选项", "preview": "查询清单", "download": "下载任务"}
        self._write_log(f"{labels.get(action, action)}失败：{error}")
        messagebox.showerror("操作失败", str(error), parent=self.root)

    def _set_busy(self, busy: bool, status: str) -> None:
        self.busy = busy
        if not busy:
            self.downloading = False
            self.pause_button.configure(state='disabled')
        self.resume_button.configure(state='disabled' if busy else 'normal')
        state = "disabled" if busy else "normal"
        reserved = DATASETS[self.dataset.get()] == "era5"
        for button in (self.refresh_button, self.preview_button, self.download_button):
            button.configure(state="disabled" if reserved else state)
        self.dataset_box.configure(state="disabled" if busy else "readonly")
        self.connection_box.configure(state='disabled' if busy else 'readonly')
        self.status.set(status)

    def _write_log(self, message: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", f"[{datetime.now():%H:%M:%S}] {message}\n")
        if int(self.log.index('end-1c').split('.')[0]) > 1000:
            self.log.delete('1.0', '101.0')
        self.log.see("end")
        self.log.configure(state="disabled")


def launch() -> None:
    root = Tk()
    ClimateDownloaderApp(root)
    root.mainloop()
