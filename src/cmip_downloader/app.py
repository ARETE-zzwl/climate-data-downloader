import queue
import threading
from datetime import datetime
from pathlib import Path
from tkinter import BooleanVar, StringVar, Tk, filedialog, messagebox
from tkinter import ttk

from . import esgf, nex
from .catalog import (
    NEX_EXPERIMENTS,
    NEX_MODELS,
    NEX_VARIABLES,
    fetch_esgf_facets,
)
from .download import download_many
from .form import DownloadRequest, FormData
from .models import DownloadItem
from .process import process_netcdf


DATASETS = {"NEX-GDDP-CMIP6（降尺度）": "nex", "CMIP6（原始模式数据）": "cmip6"}
TEMPORAL_SCALES = {"保持原尺度": "original", "日": "daily", "月": "monthly", "年": "annual"}
AGGREGATIONS = {"平均值": "mean", "求和": "sum", "最小值": "min", "最大值": "max"}


def format_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


class ClimateDownloaderApp:
    def __init__(self, root: Tk):
        self.root = root
        self.events: queue.Queue = queue.Queue()
        self.items: list[DownloadItem] = []
        self.current_request: DownloadRequest | None = None
        self.downloaded: dict[str, int] = {}
        self.total_bytes = 0
        self._variables()
        self._configure_window()
        self._build_ui()
        self._dataset_changed()
        self.root.after(100, self._poll_events)

    def _variables(self) -> None:
        home = Path.home() / "climate-data"
        self.dataset = StringVar(value=next(iter(DATASETS)))
        self.model = StringVar(value="ACCESS-CM2")
        self.experiment = StringVar(value="historical")
        self.member = StringVar(value="r1i1p1f1")
        self.variable = StringVar(value="pr")
        self.table = StringVar(value="day")
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
        self.keep_raw = BooleanVar(value=True)
        self.summary = StringVar(value="尚未查询文件清单")
        self.status = StringVar(value="就绪")

    def _configure_window(self) -> None:
        self.root.title("气候数据下载器 · NEX-GDDP-CMIP6 / CMIP6")
        self.root.geometry("1180x760")
        self.root.minsize(980, 640)
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
            text="统一检索 NEX-GDDP-CMIP6 与 CMIP6，下载后可按区域、网格和时间尺度处理",
            style="Subheader.TLabel",
        ).pack(anchor="w", pady=(3, 0))

        body = ttk.Frame(self.root, padding=14)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=0, minsize=385)
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
        self.model_box = self._combo(data_tab, 1, "模式", self.model, NEX_MODELS)
        self.experiment_box = self._combo(data_tab, 2, "情景 / 试验", self.experiment, NEX_EXPERIMENTS)
        self.member_box = self._combo(data_tab, 3, "成员", self.member, ["r1i1p1f1"])
        self.variable_box = self._combo(data_tab, 4, "变量", self.variable, NEX_VARIABLES)
        self.table_box = self._combo(data_tab, 5, "频率 / table", self.table, ["day"])
        self.version_box = self._combo(data_tab, 6, "NEX 版本", self.version, ["v2.0", "v1.1", "original"], readonly=True)
        self._entry(data_tab, 7, "起始年份", self.start_year)
        self._entry(data_tab, 8, "结束年份", self.end_year)
        self.source_hint = ttk.Label(data_tab, style="Hint.TLabel", wraplength=320, justify="left")
        self.source_hint.grid(row=9, column=0, columnspan=2, sticky="ew", pady=(10, 8))
        self.refresh_button = ttk.Button(data_tab, text="刷新可选项", command=self._refresh_catalog)
        self.refresh_button.grid(row=10, column=0, columnspan=2, sticky="ew", pady=(4, 0))

        global_check = ttk.Checkbutton(
            output_tab, text="全球范围（取消勾选后填写矩形经纬度）", variable=self.global_area,
            command=self._toggle_bbox,
        )
        global_check.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
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
            text="重采样改变网格间距，不会提高模式的真实物理精度。时间聚合默认取平均；降水率等变量请按研究目的选择。",
            style="Hint.TLabel", wraplength=320, justify="left",
        ).grid(row=5, column=0, columnspan=2, sticky="ew", pady=(10, 8))

        ttk.Label(output_tab, text="输出目录").grid(row=6, column=0, sticky="w", pady=5)
        output_row = ttk.Frame(output_tab, style="Surface.TFrame")
        output_row.grid(row=6, column=1, sticky="ew", pady=5)
        output_row.columnconfigure(0, weight=1)
        ttk.Entry(output_row, textvariable=self.output).grid(row=0, column=0, sticky="ew")
        ttk.Button(output_row, text="浏览", command=self._browse_output).grid(row=0, column=1, padx=(5, 0))
        self._combo(output_tab, 7, "并发下载数", self.workers, [str(number) for number in range(1, 9)], readonly=True)
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
        self.tree = ttk.Treeview(table_frame, columns=("name", "size", "source"), show="headings", selectmode="browse")
        self.tree.heading("name", text="文件名")
        self.tree.heading("size", text="大小")
        self.tree.heading("source", text="来源")
        self.tree.column("name", width=440, anchor="w")
        self.tree.column("size", width=90, anchor="e")
        self.tree.column("source", width=120, anchor="center")
        scroll_y = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        scroll_x = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll_y.grid(row=0, column=1, sticky="ns")
        scroll_x.grid(row=1, column=0, sticky="ew")

        ttk.Label(parent, text="任务日志", style="Section.TLabel").grid(row=3, column=0, sticky="w", pady=(12, 5))
        self.log = __import__("tkinter").Text(
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
        ttk.Label(footer, textvariable=self.status, width=18).grid(row=0, column=1, padx=(0, 12))
        self.preview_button = ttk.Button(footer, text="1. 查询清单", command=self._preview)
        self.preview_button.grid(row=0, column=2, padx=(0, 8))
        self.download_button = ttk.Button(footer, text="2. 开始下载", style="Accent.TButton", command=self._start_download)
        self.download_button.grid(row=0, column=3)

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

    def _dataset_changed(self) -> None:
        is_nex = DATASETS[self.dataset.get()] == "nex"
        if is_nex:
            self.model_box.configure(values=NEX_MODELS)
            self.experiment_box.configure(values=NEX_EXPERIMENTS)
            self.variable_box.configure(values=NEX_VARIABLES)
            self.table.set("day")
            self.table_box.configure(values=["day"], state="disabled")
            self.version_box.configure(state="readonly")
            self.source_hint.configure(text="NEX：0.25° 日尺度降尺度数据；默认使用 v2.0，避免同一年多版本重复下载。")
        else:
            self.table_box.configure(state="normal")
            self.version_box.configure(state="disabled")
            self.source_hint.configure(text="CMIP6：模式、试验、成员、变量和 table 可直接输入；点击“刷新可选项”从 ESGF 获取候选值。")
        self._invalidate_preview()

    def _toggle_bbox(self) -> None:
        state = "disabled" if self.global_area.get() else "normal"
        for entry in getattr(self, "bbox_entries", []):
            entry.configure(state=state)

    def _browse_output(self) -> None:
        selected = filedialog.askdirectory(initialdir=self.output.get() or str(Path.home()))
        if selected:
            self.output.set(selected)

    def _form(self) -> FormData:
        resolution = self.resolution.get().strip()
        return FormData(
            dataset=DATASETS[self.dataset.get()], model=self.model.get(), experiment=self.experiment.get(),
            member=self.member.get(), variable=self.variable.get(), table=self.table.get(), version=self.version.get(),
            start_year=self.start_year.get(), end_year=self.end_year.get(), global_area=self.global_area.get(),
            west=self.west.get(), east=self.east.get(), south=self.south.get(), north=self.north.get(),
            resolution="original" if resolution == "原始" else resolution,
            temporal_scale=TEMPORAL_SCALES[self.temporal_scale.get()],
            aggregation=AGGREGATIONS[self.aggregation.get()], output=self.output.get(), workers=self.workers.get(),
            keep_raw=self.keep_raw.get(),
        )

    def _validated_request(self) -> DownloadRequest | None:
        try:
            return self._form().to_request()
        except ValueError as error:
            messagebox.showerror("参数有误", str(error), parent=self.root)
            return None

    def _invalidate_preview(self) -> None:
        self.items = []
        self.current_request = None
        self.summary.set("筛选条件已变化，请重新查询")

    def _refresh_catalog(self) -> None:
        if DATASETS[self.dataset.get()] == "nex":
            self._dataset_changed()
            self._write_log("已加载 NEX 官方模式、情景和变量列表。")
            return
        self._start_worker("catalog", fetch_esgf_facets, "正在刷新 ESGF 可选项…")

    def _preview(self) -> None:
        request = self._validated_request()
        if not request:
            return
        fetcher = nex.fetch_files if request.dataset == "nex" else esgf.fetch_files
        self._start_worker("preview", lambda: (request, fetcher(request.query)), "正在查询文件清单…")

    def _start_download(self) -> None:
        request = self._validated_request()
        if not request:
            return
        if not self.items or request != self.current_request:
            messagebox.showinfo("请先查询", "筛选条件发生过变化，请先点击“查询清单”。", parent=self.root)
            return
        size = format_size(sum(item.size for item in self.items))
        processing = "，下载后将执行裁剪/重采样/聚合" if request.needs_processing else ""
        if not messagebox.askyesno(
            "确认下载", f"将下载 {len(self.items)} 个文件，共 {size}{processing}。是否继续？", parent=self.root
        ):
            return
        self.downloaded = {}
        self.total_bytes = sum(item.size for item in self.items)
        self.progress["value"] = 0
        self._start_worker(
            "download", lambda: self._download_job(request, list(self.items)), "正在下载…"
        )

    def _download_job(self, request: DownloadRequest, items: list[DownloadItem]):
        completed, failed = download_many(
            items, request.output, workers=request.workers, progress=self._download_progress
        )
        processed: list[Path] = []
        process_failed: dict[str, Exception] = {}
        if request.needs_processing:
            for index, source in enumerate(completed, 1):
                self.events.put(("log", f"处理 {index}/{len(completed)}：{source.name}"))
                target = request.output / "processed" / source.parent.name / f"{source.stem}_processed.nc"
                try:
                    processed.append(process_netcdf(source, target, request.process))
                    if not request.keep_raw:
                        source.unlink()
                except Exception as error:
                    process_failed[source.name] = error
        return completed, failed, processed, process_failed

    def _download_progress(self, filename: str, downloaded: int, total: int) -> None:
        self.events.put(("progress", filename, downloaded, total))

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
        try:
            while True:
                event = self.events.get_nowait()
                kind = event[0]
                if kind == "catalog":
                    self._catalog_ready(event[1])
                elif kind == "preview":
                    self._preview_ready(*event[1])
                elif kind == "download":
                    self._download_ready(*event[1])
                elif kind == "progress":
                    self._progress_ready(*event[1:])
                elif kind == "log":
                    self._write_log(event[1])
                elif kind == "error":
                    self._show_worker_error(event[1], event[2])
                elif kind == "busy":
                    self._set_busy(event[1], "就绪")
        except queue.Empty:
            pass
        self.root.after(100, self._poll_events)

    def _catalog_ready(self, facets: dict[str, list[str]]) -> None:
        mapping = [
            (self.model_box, "source_id"), (self.experiment_box, "experiment_id"),
            (self.member_box, "variant_label"), (self.variable_box, "variable_id"),
            (self.table_box, "table_id"),
        ]
        for widget, key in mapping:
            if facets.get(key):
                widget.configure(values=facets[key])
        self._write_log("ESGF 可选项刷新完成；所有下拉框仍允许手动输入。")

    def _preview_ready(self, request: DownloadRequest, items: list[DownloadItem]) -> None:
        self.items = items
        self.current_request = request
        for row in self.tree.get_children():
            self.tree.delete(row)
        for item in items:
            self.tree.insert("", "end", values=(item.filename, format_size(item.size), item.source))
        total = sum(item.size for item in items)
        self.summary.set(f"匹配 {len(items)} 个文件 · 预计 {format_size(total)} · 输出到 {request.output}")
        self._write_log(f"查询完成：{len(items)} 个文件，{format_size(total)}。")
        if not items:
            messagebox.showinfo("没有匹配项", "当前组合没有找到可下载文件，请调整模式、成员、变量或时间范围。", parent=self.root)

    def _progress_ready(self, filename: str, downloaded: int, total: int) -> None:
        self.downloaded[filename] = downloaded
        if self.total_bytes:
            self.progress["value"] = min(100, sum(self.downloaded.values()) * 100 / self.total_bytes)
        self.status.set(f"{filename[:18]} {format_size(downloaded)}/{format_size(total)}")

    def _download_ready(self, completed, failed, processed, process_failed) -> None:
        self.progress["value"] = 100 if not failed else self.progress["value"]
        self._write_log(f"下载完成：成功 {len(completed)}，失败 {len(failed)}；处理输出 {len(processed)}，处理失败 {len(process_failed)}。")
        for filename, error in {**failed, **process_failed}.items():
            self._write_log(f"失败 · {filename} · {error}")
        if failed or process_failed:
            messagebox.showwarning("任务部分完成", "部分文件失败，详情请查看任务日志；可直接重试以利用断点续传。", parent=self.root)
        else:
            messagebox.showinfo("任务完成", "所有文件均已完成。", parent=self.root)

    def _show_worker_error(self, action: str, error: Exception) -> None:
        labels = {"catalog": "刷新可选项", "preview": "查询清单", "download": "下载任务"}
        self._write_log(f"{labels.get(action, action)}失败：{error}")
        messagebox.showerror("操作失败", str(error), parent=self.root)

    def _set_busy(self, busy: bool, status: str) -> None:
        state = "disabled" if busy else "normal"
        for button in (self.refresh_button, self.preview_button, self.download_button):
            button.configure(state=state)
        self.status.set(status)

    def _write_log(self, message: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", f"[{datetime.now():%H:%M:%S}] {message}\n")
        self.log.see("end")
        self.log.configure(state="disabled")


def launch() -> None:
    root = Tk()
    ClimateDownloaderApp(root)
    root.mainloop()

