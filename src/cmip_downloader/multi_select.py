from collections.abc import Callable, Iterable
from tkinter import Listbox, StringVar, Toplevel
from tkinter import ttk


def filter_values(values: Iterable[str], search: str) -> list[str]:
    needle = search.strip().casefold()
    return [value for value in values if not needle or needle in value.casefold()]


def selection_summary(selected: Iterable[str]) -> str:
    values = list(selected)
    if not values:
        return "请选择…"
    if len(values) == 1:
        return values[0]
    return f"已选 {len(values)} 项"


class MultiSelectField(ttk.Frame):
    def __init__(
        self,
        master,
        values: Iterable[str] = (),
        selected: Iterable[str] = (),
        on_change: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(master, style="Surface.TFrame")
        self._values = list(dict.fromkeys(values))
        self._selected = set(selected) & set(self._values)
        self._on_change = on_change
        self._text = StringVar(value=selection_summary(self.get()))
        self.button = ttk.Button(self, textvariable=self._text, command=self._open)
        self.button.pack(fill="x")

    def get(self) -> tuple[str, ...]:
        return tuple(value for value in self._values if value in self._selected)

    def set_values(
        self,
        values: Iterable[str],
        selected: Iterable[str] | None = None,
    ) -> None:
        self._values = list(dict.fromkeys(values))
        if selected is None:
            self._selected &= set(self._values)
        else:
            self._selected = set(selected) & set(self._values)
        self._refresh_text()

    def set_selected(self, selected: Iterable[str]) -> None:
        self._selected = set(selected) & set(self._values)
        self._refresh_text()
        if self._on_change:
            self._on_change()

    def configure(self, cnf=None, **kwargs):
        state = kwargs.pop("state", None)
        result = super().configure(cnf, **kwargs)
        if state is not None:
            self.button.configure(state=state)
        return result

    config = configure

    def _refresh_text(self) -> None:
        self._text.set(selection_summary(self.get()))

    def _open(self) -> None:
        MultiSelectDialog(self, self._values, self.get(), self.set_selected)


class MultiSelectDialog(Toplevel):
    def __init__(
        self,
        owner: MultiSelectField,
        values: Iterable[str],
        selected: Iterable[str],
        on_confirm: Callable[[Iterable[str]], None],
    ) -> None:
        super().__init__(owner)
        self.title("多选")
        self.geometry("430x480")
        self.transient(owner.winfo_toplevel())
        self.grab_set()
        self._values = list(values)
        self._selected = set(selected)
        self._visible: list[str] = []
        self._on_confirm = on_confirm
        self._search = StringVar()
        self._build()
        self._search.trace_add("write", lambda *_: self._render())
        self._render()
        self.bind("<Escape>", lambda _event: self.destroy())

    def _build(self) -> None:
        frame = ttk.Frame(self, padding=12)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="搜索").pack(anchor="w")
        entry = ttk.Entry(frame, textvariable=self._search)
        entry.pack(fill="x", pady=(3, 8))
        entry.focus_set()
        self._list = Listbox(
            frame,
            activestyle="none",
            font=("Microsoft YaHei UI", 10),
            selectmode="browse",
        )
        self._list.pack(fill="both", expand=True)
        self._list.bind("<ButtonRelease-1>", self._toggle)
        self._list.bind("<space>", self._toggle)

        actions = ttk.Frame(frame)
        actions.pack(fill="x", pady=(10, 0))
        ttk.Button(actions, text="全选当前", command=self._select_visible).pack(side="left")
        ttk.Button(actions, text="清空", command=self._clear).pack(side="left", padx=6)
        ttk.Button(actions, text="取消", command=self.destroy).pack(side="right")
        ttk.Button(actions, text="确定", command=self._confirm).pack(side="right", padx=6)

    def _render(self) -> None:
        self._visible = filter_values(self._values, self._search.get())
        self._list.delete(0, "end")
        for value in self._visible:
            mark = "☑" if value in self._selected else "☐"
            self._list.insert("end", f"{mark}  {value}")

    def _toggle(self, _event=None):
        selection = self._list.curselection()
        if not selection:
            return "break"
        value = self._visible[selection[0]]
        if value in self._selected:
            self._selected.remove(value)
        else:
            self._selected.add(value)
        self._render()
        self._list.selection_set(self._visible.index(value))
        return "break"

    def _select_visible(self) -> None:
        self._selected.update(self._visible)
        self._render()

    def _clear(self) -> None:
        self._selected.clear()
        self._render()

    def _confirm(self) -> None:
        self._on_confirm(self._selected)
        self.destroy()
