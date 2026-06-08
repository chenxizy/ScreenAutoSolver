from __future__ import annotations

import contextlib
import queue
import threading
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Any

from .config import (
    ApiConfig,
    OcrConfig,
    RegionConfig,
    RuntimeConfig,
    SolverConfig,
    default_config,
    load_config,
    save_config,
)
from .models import Decision, OptionOcr, Region
from .runner import ScreenOnlySolver, SolverStop


APP_TITLE = "纯屏幕识别自动答题 SOP"


@dataclass
class GuiRequest:
    kind: str
    title: str
    message: str
    options: list[OptionOcr] | None = None
    default_label: str | None = None
    event: threading.Event | None = None
    response: Any = None


class QueueWriter:
    def __init__(self, out_queue: queue.Queue[tuple[str, Any]]) -> None:
        self.out_queue = out_queue

    def write(self, text: str) -> int:
        if text:
            self.out_queue.put(("log", text))
        return len(text)

    def flush(self) -> None:
        return None


class GuiInteraction:
    def __init__(self, out_queue: queue.Queue[tuple[str, Any]]) -> None:
        self.out_queue = out_queue

    def ask_label(self, title: str, message: str, options: list[OptionOcr]) -> str | None:
        return self._request(
            GuiRequest(kind="label", title=title, message=message, options=options)
        )

    def confirm_decision(
        self,
        message: str,
        options: list[OptionOcr],
        default_label: str,
    ) -> str | None:
        return self._request(
            GuiRequest(
                kind="confirm",
                title="确认点击",
                message=message,
                options=options,
                default_label=default_label,
            )
        )

    def ask_continue(self, title: str, message: str) -> bool:
        return bool(self._request(GuiRequest(kind="continue", title=title, message=message)))

    def _request(self, request: GuiRequest) -> Any:
        request.event = threading.Event()
        self.out_queue.put(("request", request))
        request.event.wait()
        return request.response


class GuiScreenOnlySolver(ScreenOnlySolver):
    def __init__(
        self,
        config: SolverConfig,
        interaction: GuiInteraction,
        stop_event: threading.Event,
    ) -> None:
        super().__init__(config)
        self.interaction = interaction
        self.stop_event = stop_event

    def run(self, once: bool = False) -> None:
        max_questions = 1 if once else self.config.runtime.max_questions
        for attempt_index in range(1, max_questions + 1):
            if self.stop_event.is_set():
                print("[auto-solver] stop requested")
                return
            print(f"[auto-solver] attempt {attempt_index}: capture")
            result = self.solve_once(attempt_index)
            if result == "stop":
                print("[auto-solver] stop condition reached")
                return
            if once:
                return
        print(f"[auto-solver] max_questions reached: {max_questions}")

    def _manual_mismatch(
        self,
        attempt_index: int,
        options: list[OptionOcr],
        message: str,
    ) -> Decision | str:
        print(f"[auto-solver] answer mismatch: {message}")
        label = self.interaction.ask_label(
            "需要人工选择",
            f"自动决策失败：{message}\n"
            "请选择要点击的选项；取消则停止运行。",
            options,
        )
        if not label:
            return "stop"
        selected = _find_option(options, label)
        if not selected:
            print(f"[auto-solver] unknown label: {label}")
            return "stop"
        return Decision(
            option=selected,
            evidence={"manual_mismatch": selected.label},
            confidence=0.0,
            click_point=selected.center(),
            reason=f"Manual mismatch override: {message}",
        )

    def _manual_confirm(
        self,
        attempt_index: int,
        options: list[OptionOcr],
        decision: Decision,
    ) -> Decision:
        label = self.interaction.confirm_decision(
            f"已解析为 {decision.option.label}: {decision.option.text}\n"
            f"点击坐标: {decision.click_point}",
            options,
            decision.option.label,
        )
        if label is None:
            raise SolverStop("Stopped by user")
        selected = _find_option(options, label)
        if not selected:
            raise SolverStop(f"Unknown manual label: {label}")
        if selected.label == decision.option.label:
            return decision
        return Decision(
            option=selected,
            evidence={"manual_confirm": selected.label},
            confidence=decision.confidence,
            click_point=selected.center(),
            reason="Manual override",
        )

    def _pause_or_stop(self, attempt_index: int, reason: str) -> str:
        self.logger.save_text(attempt_index, "pause.txt", reason)
        print(f"[auto-solver] {reason}")
        keep_going = self.interaction.ask_continue("需要确认", reason)
        return "continue" if keep_going else "stop"

    def _pause_or_continue(self, prompt: str) -> str:
        keep_going = self.interaction.ask_continue("需要确认", prompt)
        return "continue" if keep_going else "stop"


class AutoSolverApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("980x720")
        self.minsize(900, 620)

        self.events: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.stop_event = threading.Event()
        self.worker: threading.Thread | None = None
        self.region_vars: dict[str, dict[str, tk.StringVar]] = {}

        self._create_vars(default_config())
        self._build_ui()
        self.after(120, self._poll_events)

    def _create_vars(self, config: SolverConfig) -> None:
        self.config_path = tk.StringVar(value="config.yaml")
        self.api_url = tk.StringVar(value=config.api.url)
        self.api_key = tk.StringVar(value=config.api.api_key)
        self.api_key_header = tk.StringVar(value=config.api.api_key_header)
        self.api_key_prefix = tk.StringVar(value=config.api.api_key_prefix)
        self.api_model = tk.StringVar(value=config.api.model)
        self.api_temperature = tk.StringVar(value=str(config.api.temperature))
        self.api_timeout = tk.StringVar(value=str(config.api.timeout_seconds))
        self.click_point_space = tk.StringVar(value=config.api.click_point_space)

        self.ocr_engine = tk.StringVar(value=config.ocr.engine)
        self.text_match_threshold = tk.StringVar(value=str(config.ocr.text_match_threshold))
        self.min_line_confidence = tk.StringVar(value=str(config.ocr.min_line_confidence))

        self.log_dir = tk.StringVar(value=config.runtime.log_dir)
        self.max_questions = tk.StringVar(value=str(config.runtime.max_questions))
        self.click_delay = tk.StringVar(value=str(config.runtime.click_delay_seconds))
        self.next_delay = tk.StringVar(value=str(config.runtime.next_delay_seconds))
        self.selection_diff_threshold = tk.StringVar(
            value=str(config.runtime.selection_diff_threshold)
        )
        self.unchanged_question_threshold = tk.StringVar(
            value=str(config.runtime.unchanged_question_threshold)
        )
        self.require_manual_confirm = tk.BooleanVar(
            value=config.runtime.require_manual_confirm
        )
        self.dry_run = tk.BooleanVar(value=config.runtime.dry_run)
        self.strict_triple_check = tk.BooleanVar(value=config.runtime.strict_triple_check)
        self.non_strict_use_confidence_margin = tk.BooleanVar(
            value=config.runtime.non_strict_use_confidence_margin
        )
        self.non_strict_confidence_margin = tk.StringVar(
            value=str(config.runtime.non_strict_confidence_margin)
        )
        self.cache_next_button_after_first_detection = tk.BooleanVar(
            value=config.runtime.cache_next_button_after_first_detection
        )
        self.stop_if_question_unchanged = tk.BooleanVar(
            value=config.runtime.stop_if_question_unchanged
        )
        self.auto_minimize_on_run = tk.BooleanVar(
            value=config.runtime.auto_minimize_on_run
        )
        self.once_run = tk.BooleanVar(value=False)
        self.next_keywords = tk.StringVar(value=", ".join(config.runtime.next_keywords))
        self.stop_keywords = tk.StringVar(value=", ".join(config.runtime.stop_keywords))

        self.region_vars = {}
        for key, region in {
            "question": config.regions.question,
            "options": config.regions.options,
            "next_button": config.regions.next_button,
        }.items():
            self.region_vars[key] = {
                "x": tk.StringVar(value=str(region.x)),
                "y": tk.StringVar(value=str(region.y)),
                "width": tk.StringVar(value=str(region.width)),
                "height": tk.StringVar(value=str(region.height)),
            }

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        root = ttk.Frame(self, padding=12)
        root.grid(row=0, column=0, sticky="nsew")
        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)

        self._build_toolbar(root)
        self._build_notebook(root)
        self._build_log(root)

    def _build_toolbar(self, parent: ttk.Frame) -> None:
        bar = ttk.Frame(parent)
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        bar.columnconfigure(1, weight=1)

        ttk.Label(bar, text="配置").grid(row=0, column=0, sticky="w")
        ttk.Entry(bar, textvariable=self.config_path).grid(
            row=0, column=1, sticky="ew", padx=6
        )
        ttk.Button(bar, text="浏览", command=self._browse_config).grid(row=0, column=2)
        ttk.Button(bar, text="加载", command=self.load_config_from_ui).grid(
            row=0, column=3, padx=(6, 0)
        )
        ttk.Button(bar, text="保存", command=self.save_config_from_ui).grid(
            row=0, column=4, padx=(6, 0)
        )
        ttk.Button(bar, text="校准全部区域", command=self.calibrate_all).grid(
            row=0, column=5, padx=(6, 0)
        )

    def _build_notebook(self, parent: ttk.Frame) -> None:
        notebook = ttk.Notebook(parent)
        notebook.grid(row=1, column=0, sticky="nsew")
        parent.rowconfigure(1, weight=1)

        basic = ttk.Frame(notebook, padding=10)
        regions = ttk.Frame(notebook, padding=10)
        runtime = ttk.Frame(notebook, padding=10)
        notebook.add(basic, text="API / OCR")
        notebook.add(regions, text="屏幕区域")
        notebook.add(runtime, text="运行")

        self._build_basic_tab(basic)
        self._build_regions_tab(regions)
        self._build_runtime_tab(runtime)

    def _build_basic_tab(self, tab: ttk.Frame) -> None:
        tab.columnconfigure(1, weight=1)
        _row_entry(tab, 0, "API URL", self.api_url)
        _row_entry(tab, 1, "API Key", self.api_key, show="*")
        _row_entry(tab, 2, "Key Header", self.api_key_header)
        _row_entry(tab, 3, "Key Prefix", self.api_key_prefix)
        _row_entry(tab, 4, "Model", self.api_model)
        _row_entry(tab, 5, "Temperature", self.api_temperature)
        _row_entry(tab, 6, "超时秒数", self.api_timeout)
        _row_entry(tab, 7, "点击坐标空间", self.click_point_space)
        _row_entry(tab, 8, "OCR 引擎", self.ocr_engine)
        _row_entry(tab, 9, "文本匹配阈值", self.text_match_threshold)
        _row_entry(tab, 10, "OCR 最低置信度", self.min_line_confidence)

    def _build_regions_tab(self, tab: ttk.Frame) -> None:
        for col in range(5):
            tab.columnconfigure(col, weight=1 if col else 0)
        headers = ["区域", "x", "y", "width", "height", ""]
        for col, header in enumerate(headers):
            ttk.Label(tab, text=header).grid(row=0, column=col, sticky="w", padx=4)

        labels = {
            "question": "题目截图区",
            "options": "选项区",
            "next_button": "下一题按钮",
        }
        for row, (key, label) in enumerate(labels.items(), start=1):
            ttk.Label(tab, text=label).grid(row=row, column=0, sticky="w", padx=4, pady=4)
            for col, field in enumerate(("x", "y", "width", "height"), start=1):
                ttk.Entry(tab, textvariable=self.region_vars[key][field], width=12).grid(
                    row=row, column=col, sticky="ew", padx=4, pady=4
                )
            ttk.Button(
                tab,
                text="校准",
                command=lambda region_key=key, region_label=label: self.calibrate_region(
                    region_key, region_label
                ),
            ).grid(row=row, column=5, padx=4, pady=4)

    def _build_runtime_tab(self, tab: ttk.Frame) -> None:
        tab.columnconfigure(1, weight=1)
        _row_entry(tab, 0, "日志目录", self.log_dir)
        _row_entry(tab, 1, "最大题数", self.max_questions)
        _row_entry(tab, 2, "点击延迟秒", self.click_delay)
        _row_entry(tab, 3, "下一题延迟秒", self.next_delay)
        _row_entry(tab, 4, "选中复核差异阈值", self.selection_diff_threshold)
        _row_entry(tab, 5, "题目未变化阈值", self.unchanged_question_threshold)
        _row_entry(tab, 6, "下一题关键词", self.next_keywords)
        _row_entry(tab, 7, "停止关键词", self.stop_keywords)
        _row_entry(tab, 8, "非严格差异阈值", self.non_strict_confidence_margin)

        checks = ttk.Frame(tab)
        checks.grid(row=9, column=0, columnspan=2, sticky="w", pady=(12, 0))
        ttk.Checkbutton(checks, text="干跑不点击", variable=self.dry_run).grid(
            row=0, column=0, sticky="w", padx=(0, 16)
        )
        ttk.Checkbutton(checks, text="只跑一题", variable=self.once_run).grid(
            row=0, column=1, sticky="w", padx=(0, 16)
        )
        ttk.Checkbutton(
            checks, text="每题人工确认", variable=self.require_manual_confirm
        ).grid(row=0, column=2, sticky="w", padx=(0, 16))
        ttk.Checkbutton(
            checks, text="严格三重校验", variable=self.strict_triple_check
        ).grid(row=1, column=0, sticky="w", pady=(6, 0), padx=(0, 16))
        ttk.Checkbutton(
            checks,
            text="非严格时启用差异阈值",
            variable=self.non_strict_use_confidence_margin,
        ).grid(row=1, column=1, sticky="w", pady=(6, 0), padx=(0, 16))
        ttk.Checkbutton(
            checks,
            text="下一题按钮固定：只识别一次",
            variable=self.cache_next_button_after_first_detection,
        ).grid(row=1, column=2, sticky="w", pady=(6, 0), padx=(0, 16))
        ttk.Checkbutton(
            checks,
            text="题目未变化时停止",
            variable=self.stop_if_question_unchanged,
        ).grid(row=2, column=0, sticky="w", pady=(6, 0), padx=(0, 16))
        ttk.Checkbutton(
            checks,
            text="运行时最小化窗口",
            variable=self.auto_minimize_on_run,
        ).grid(row=2, column=1, sticky="w", pady=(6, 0), padx=(0, 16))

        actions = ttk.Frame(tab)
        actions.grid(row=10, column=0, columnspan=2, sticky="w", pady=(18, 0))
        ttk.Button(actions, text="单题干跑", command=self.run_once_dry).grid(
            row=0, column=0, padx=(0, 8)
        )
        ttk.Button(actions, text="开始运行", command=self.start_run).grid(
            row=0, column=1, padx=(0, 8)
        )
        ttk.Button(actions, text="停止", command=self.stop_run).grid(row=0, column=2)

    def _build_log(self, parent: ttk.Frame) -> None:
        log_frame = ttk.LabelFrame(parent, text="运行日志", padding=8)
        log_frame.grid(row=2, column=0, sticky="nsew", pady=(8, 0))
        parent.rowconfigure(2, weight=1)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_text = tk.Text(log_frame, height=10, wrap="word")
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scroll.set)

    def _browse_config(self) -> None:
        path = filedialog.asksaveasfilename(
            title="选择配置文件",
            defaultextension=".yaml",
            filetypes=[("YAML", "*.yaml *.yml"), ("All files", "*.*")],
            initialfile=self.config_path.get() or "config.yaml",
        )
        if path:
            self.config_path.set(path)

    def load_config_from_ui(self) -> None:
        try:
            config = load_config(self.config_path.get())
            self._apply_config(config)
            self._log(f"Loaded config: {self.config_path.get()}\n")
        except Exception as exc:
            messagebox.showerror("加载失败", str(exc))

    def save_config_from_ui(self) -> SolverConfig | None:
        try:
            config = self._build_config()
            save_config(config, self.config_path.get())
            self._log(f"Saved config: {self.config_path.get()}\n")
            return config
        except Exception as exc:
            messagebox.showerror("保存失败", str(exc))
            return None

    def calibrate_all(self) -> None:
        for key, label in (
            ("question", "题目截图区"),
            ("options", "选项区"),
            ("next_button", "下一题按钮"),
        ):
            if not self.calibrate_region(key, label):
                return

    def calibrate_region(self, key: str, label: str) -> bool:
        messagebox.showinfo("校准", f"把鼠标移动到【{label}】左上角，然后点确定。")
        x1, y1 = self.winfo_pointerx(), self.winfo_pointery()
        messagebox.showinfo("校准", f"把鼠标移动到【{label}】右下角，然后点确定。")
        x2, y2 = self.winfo_pointerx(), self.winfo_pointery()
        width = abs(x2 - x1)
        height = abs(y2 - y1)
        if width <= 0 or height <= 0:
            messagebox.showerror("校准失败", "区域宽度和高度必须大于 0。")
            return False
        self.region_vars[key]["x"].set(str(min(x1, x2)))
        self.region_vars[key]["y"].set(str(min(y1, y2)))
        self.region_vars[key]["width"].set(str(width))
        self.region_vars[key]["height"].set(str(height))
        self._log(f"Calibrated {label}: x={min(x1, x2)} y={min(y1, y2)} w={width} h={height}\n")
        return True

    def run_once_dry(self) -> None:
        self.dry_run.set(True)
        self.once_run.set(True)
        self.start_run()

    def start_run(self) -> None:
        if self.worker and self.worker.is_alive():
            messagebox.showwarning("正在运行", "当前任务还在运行。")
            return
        config = self.save_config_from_ui()
        if not config:
            return
        self.stop_event.clear()
        interaction = GuiInteraction(self.events)
        self.worker = threading.Thread(
            target=self._run_worker,
            args=(config, interaction, bool(self.once_run.get())),
            daemon=True,
        )
        self.worker.start()
        if self.auto_minimize_on_run.get():
            self.after(300, self.iconify)

    def stop_run(self) -> None:
        self.stop_event.set()
        self._log("Stop requested. The solver will stop after the current operation.\n")

    def _run_worker(
        self,
        config: SolverConfig,
        interaction: GuiInteraction,
        once: bool,
    ) -> None:
        writer = QueueWriter(self.events)
        try:
            with contextlib.redirect_stdout(writer), contextlib.redirect_stderr(writer):
                solver = GuiScreenOnlySolver(config, interaction, self.stop_event)
                solver.run(once=once)
            self.events.put(("done", "运行结束"))
        except Exception as exc:
            self.events.put(("error", str(exc)))

    def _poll_events(self) -> None:
        while True:
            try:
                event, payload = self.events.get_nowait()
            except queue.Empty:
                break
            if event == "log":
                self._log(str(payload))
            elif event == "done":
                self._log(f"{payload}\n")
            elif event == "error":
                self._log(f"ERROR: {payload}\n")
                messagebox.showerror("运行失败", str(payload))
            elif event == "request":
                self._handle_request(payload)
        self.after(120, self._poll_events)

    def _handle_request(self, request: GuiRequest) -> None:
        try:
            if self.auto_minimize_on_run.get():
                self.deiconify()
                self.lift()
                self.focus_force()
            if request.kind == "label":
                request.response = self._ask_option_label(request)
            elif request.kind == "confirm":
                request.response = self._confirm_option(request)
            elif request.kind == "continue":
                request.response = messagebox.askyesno(request.title, request.message)
            else:
                request.response = None
        finally:
            if request.event:
                request.event.set()
            if (
                self.auto_minimize_on_run.get()
                and self.worker
                and self.worker.is_alive()
                and not self.stop_event.is_set()
            ):
                self.after(300, self.iconify)

    def _ask_option_label(self, request: GuiRequest) -> str | None:
        options_text = _format_options(request.options or [])
        value = simpledialog.askstring(
            request.title,
            f"{request.message}\n\n{options_text}\n\n输入选项字母，取消则停止：",
            parent=self,
        )
        if value is None:
            return None
        return value.strip().upper() or None

    def _confirm_option(self, request: GuiRequest) -> str | None:
        result = messagebox.askyesnocancel(
            request.title,
            f"{request.message}\n\n是：接受\n否：改选\n取消：停止",
            parent=self,
        )
        if result is None:
            return None
        if result is True:
            return request.default_label
        return self._ask_option_label(request)

    def _apply_config(self, config: SolverConfig) -> None:
        self.api_url.set(config.api.url)
        self.api_key.set(config.api.api_key)
        self.api_key_header.set(config.api.api_key_header)
        self.api_key_prefix.set(config.api.api_key_prefix)
        self.api_model.set(config.api.model)
        self.api_temperature.set(str(config.api.temperature))
        self.api_timeout.set(str(config.api.timeout_seconds))
        self.click_point_space.set(config.api.click_point_space)
        self.ocr_engine.set(config.ocr.engine)
        self.text_match_threshold.set(str(config.ocr.text_match_threshold))
        self.min_line_confidence.set(str(config.ocr.min_line_confidence))
        self.log_dir.set(config.runtime.log_dir)
        self.max_questions.set(str(config.runtime.max_questions))
        self.click_delay.set(str(config.runtime.click_delay_seconds))
        self.next_delay.set(str(config.runtime.next_delay_seconds))
        self.selection_diff_threshold.set(str(config.runtime.selection_diff_threshold))
        self.unchanged_question_threshold.set(str(config.runtime.unchanged_question_threshold))
        self.require_manual_confirm.set(config.runtime.require_manual_confirm)
        self.dry_run.set(config.runtime.dry_run)
        self.strict_triple_check.set(config.runtime.strict_triple_check)
        self.non_strict_use_confidence_margin.set(
            config.runtime.non_strict_use_confidence_margin
        )
        self.non_strict_confidence_margin.set(
            str(config.runtime.non_strict_confidence_margin)
        )
        self.cache_next_button_after_first_detection.set(
            config.runtime.cache_next_button_after_first_detection
        )
        self.stop_if_question_unchanged.set(config.runtime.stop_if_question_unchanged)
        self.auto_minimize_on_run.set(config.runtime.auto_minimize_on_run)
        self.next_keywords.set(", ".join(config.runtime.next_keywords))
        self.stop_keywords.set(", ".join(config.runtime.stop_keywords))
        for key, region in {
            "question": config.regions.question,
            "options": config.regions.options,
            "next_button": config.regions.next_button,
        }.items():
            self.region_vars[key]["x"].set(str(region.x))
            self.region_vars[key]["y"].set(str(region.y))
            self.region_vars[key]["width"].set(str(region.width))
            self.region_vars[key]["height"].set(str(region.height))

    def _build_config(self) -> SolverConfig:
        return SolverConfig(
            api=ApiConfig(
                url=self.api_url.get().strip(),
                api_key=self.api_key.get(),
                api_key_header=self.api_key_header.get().strip(),
                api_key_prefix=self.api_key_prefix.get(),
                model=self.api_model.get().strip() or "glm-5.1",
                temperature=float(self.api_temperature.get()),
                timeout_seconds=float(self.api_timeout.get()),
                click_point_space=self.click_point_space.get().strip() or "auto",
            ),
            regions=RegionConfig(
                question=self._region_from_vars("question"),
                options=self._region_from_vars("options"),
                next_button=self._region_from_vars("next_button"),
            ),
            ocr=OcrConfig(
                engine=self.ocr_engine.get().strip() or "rapidocr",
                text_match_threshold=float(self.text_match_threshold.get()),
                min_line_confidence=float(self.min_line_confidence.get()),
            ),
            runtime=RuntimeConfig(
                log_dir=self.log_dir.get().strip() or "runs",
                max_questions=int(self.max_questions.get()),
                click_delay_seconds=float(self.click_delay.get()),
                next_delay_seconds=float(self.next_delay.get()),
                require_manual_confirm=bool(self.require_manual_confirm.get()),
                dry_run=bool(self.dry_run.get()),
                strict_triple_check=bool(self.strict_triple_check.get()),
                non_strict_use_confidence_margin=bool(
                    self.non_strict_use_confidence_margin.get()
                ),
                non_strict_confidence_margin=float(
                    self.non_strict_confidence_margin.get()
                ),
                cache_next_button_after_first_detection=bool(
                    self.cache_next_button_after_first_detection.get()
                ),
                auto_minimize_on_run=bool(self.auto_minimize_on_run.get()),
                selection_diff_threshold=float(self.selection_diff_threshold.get()),
                unchanged_question_threshold=float(
                    self.unchanged_question_threshold.get()
                ),
                stop_if_question_unchanged=bool(self.stop_if_question_unchanged.get()),
                next_keywords=_split_keywords(self.next_keywords.get()),
                stop_keywords=_split_keywords(self.stop_keywords.get()),
            ),
        )

    def _region_from_vars(self, key: str) -> Region:
        vars_for_region = self.region_vars[key]
        return Region(
            x=int(vars_for_region["x"].get()),
            y=int(vars_for_region["y"].get()),
            width=int(vars_for_region["width"].get()),
            height=int(vars_for_region["height"].get()),
            name=key,
        )

    def _log(self, text: str) -> None:
        self.log_text.insert("end", text)
        self.log_text.see("end")


def _row_entry(
    parent: ttk.Frame,
    row: int,
    label: str,
    variable: tk.StringVar,
    show: str | None = None,
) -> None:
    ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=4)
    ttk.Entry(parent, textvariable=variable, show=show).grid(
        row=row, column=1, sticky="ew", padx=(8, 0), pady=4
    )


def _find_option(options: list[OptionOcr], label: str) -> OptionOcr | None:
    normalized = label.strip().upper()
    return next((option for option in options if option.label.upper() == normalized), None)


def _format_options(options: list[OptionOcr]) -> str:
    if not options:
        return "未识别到选项。"
    return "\n".join(f"{option.label}: {option.text}" for option in options)


def _split_keywords(text: str) -> list[str]:
    return [part.strip() for part in text.split(",") if part.strip()]


def main() -> None:
    app = AutoSolverApp()
    app.mainloop()


if __name__ == "__main__":
    main()
