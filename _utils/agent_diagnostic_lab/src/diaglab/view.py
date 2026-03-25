from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

from src.core.agent.benchmark_runner import BenchmarkSuiteResult
from src.ui import theme

from diaglab.components.log_panel import LogPanel
from diaglab.components.metric_card import MetricCard
from diaglab.components.section_frame import SectionFrame
from diaglab.models import ProbeResult


class DiagnosticView:
    def __init__(self, root: tk.Tk, toolbox_root: Path):
        self.root = root
        self.toolbox_root = Path(toolbox_root)
        self._configure_root()
        self._build_styles()
        self._build_layout()
        self._set_defaults()

    def bind_actions(
        self,
        *,
        refresh_models,
        refresh_benchmarks,
        refresh_history,
        refresh_resources,
        run_prompt_probe,
        run_direct_probe,
        run_engine_probe,
        run_benchmark_suite,
        restore_prompt_version,
        compare_benchmark_runs,
        diff_prompt_versions,
        stop_active_probe,
        export_last_result,
    ) -> None:
        self.refresh_models_btn.configure(command=refresh_models)
        self.refresh_benchmarks_btn.configure(command=refresh_benchmarks)
        self.refresh_history_btn.configure(command=refresh_history)
        self.refresh_resources_btn.configure(command=refresh_resources)
        self.prompt_probe_btn.configure(command=run_prompt_probe)
        self.direct_probe_btn.configure(command=run_direct_probe)
        self.engine_probe_btn.configure(command=run_engine_probe)
        self.benchmark_btn.configure(command=run_benchmark_suite)
        self.restore_version_btn.configure(command=restore_prompt_version)
        self.compare_runs_btn.configure(command=compare_benchmark_runs)
        self.diff_versions_btn.configure(command=diff_prompt_versions)
        self.stop_btn.configure(command=stop_active_probe)
        self.export_btn.configure(command=export_last_result)

    def get_inputs(self) -> dict[str, object]:
        return {
            "sandbox_root": self.sandbox_var.get().strip(),
            "model_name": self.model_var.get().strip(),
            "base_url": self.base_url_var.get().strip(),
            "user_text": self.prompt_text.get("1.0", "end").strip(),
            "docker_enabled": bool(self.docker_var.get()),
            "temperature": float(self.temperature_var.get()),
            "num_ctx": int(self.ctx_var.get()),
            "benchmark_suite": self.benchmark_var.get().strip(),
        }

    def get_history_inputs(self) -> dict[str, int]:
        return {
            "version_id": int(self.version_id_var.get() or 0),
            "left_run_id": int(self.compare_left_var.get() or 0),
            "right_run_id": int(self.compare_right_var.get() or 0),
            "diff_left_version_id": int(self.diff_left_var.get() or 0),
            "diff_right_version_id": int(self.diff_right_var.get() or 0),
        }

    def set_models(self, models: list[str]) -> None:
        self.model_combo["values"] = models
        self.models_card.set_value(str(len(models)), theme.CYAN)
        if models and self.model_var.get().strip() not in models:
            self.model_var.set(models[0])

    def set_resources(self, snapshot) -> None:
        self.cpu_card.set_value(f"{snapshot.cpu_percent:.0f}%", theme.CYAN)
        self.ram_card.set_value(f"{snapshot.ram_used_gb:.1f}/{snapshot.ram_total_gb:.1f} GB", theme.GREEN)
        if snapshot.gpu_available:
            self.gpu_card.set_value(f"{snapshot.vram_used_gb:.1f}/{snapshot.vram_total_gb:.1f} GB", theme.PURPLE)
        else:
            self.gpu_card.set_value("n/a", theme.TEXT_DIM)

    def set_benchmark_suites(self, suites: list[dict[str, str]]) -> None:
        values = [suite["name"] for suite in suites]
        self.benchmark_combo["values"] = values
        if suites and self.benchmark_var.get().strip() not in values:
            self.benchmark_var.set(suites[0]["name"])

    def set_history_snapshot(self, versions: list[dict[str, object]], benchmark_runs: list[dict[str, object]]) -> None:
        lines = ["## Prompt Versions", ""]
        if versions:
            for version in versions:
                lines.append(
                    f"[v{version['id']}] {str(version.get('git_commit', ''))[:12]}  "
                    f"{version.get('reason', '')}  "
                    f"{version.get('created_at', '')}"
                )
        else:
            lines.append("(no prompt versions yet)")
        lines.extend(["", "## Benchmark Runs", ""])
        if benchmark_runs:
            for run in benchmark_runs:
                lines.append(
                    f"[b{run['id']}] {run.get('suite_name', '')}  "
                    f"score={run.get('average_overall_score', 0.0)}  "
                    f"tokens={run.get('total_tokens', 0)}  "
                    f"{run.get('created_at', '')}"
                )
        else:
            lines.append("(no benchmark runs yet)")
        self.history_panel.set_text("\n".join(lines))

    def set_status(self, text: str) -> None:
        self.status_var.set(text)

    def set_busy(self, is_busy: bool, status: str = "") -> None:
        state = "disabled" if is_busy else "normal"
        for button in (
            self.refresh_models_btn,
            self.refresh_benchmarks_btn,
            self.refresh_history_btn,
            self.refresh_resources_btn,
            self.prompt_probe_btn,
            self.direct_probe_btn,
            self.engine_probe_btn,
            self.benchmark_btn,
            self.restore_version_btn,
            self.compare_runs_btn,
            self.diff_versions_btn,
            self.export_btn,
        ):
            button.configure(state=state)
        self.stop_btn.configure(state="normal")
        if status:
            self.set_status(status)

    def show_probe_result(self, result: ProbeResult) -> None:
        self.events_card.set_value(str(len(result.events)), theme.AMBER)
        self.score_card.set_value(f"{result.metadata.get('overall_score', 0.0):.3f}", theme.GREEN)
        self.last_probe_card.set_value(result.name, theme.CYAN)
        self.summary_panel.set_text(self._format_summary(result))
        self.prompt_panel.set_text(result.prompt_text or "[No prompt text]")
        self.response_panel.set_text(result.response_text or "[No response text]")
        self.events_panel.set_text(self._format_events(result))
        self.set_status(f"{result.name}: {result.status}")
        self.notebook.select(self.summary_tab)

    def show_benchmark_result(self, result: BenchmarkSuiteResult) -> None:
        self.score_card.set_value(f"{result.metadata.get('average_overall_score', 0.0):.3f}", theme.GREEN)
        self.events_card.set_value(str(result.metadata.get("case_count", 0)), theme.AMBER)
        self.last_probe_card.set_value(result.suite_label, theme.CYAN)
        self.summary_panel.set_text(self._format_benchmark_summary(result))
        self.benchmark_panel.set_text(self._format_benchmark_cases(result))
        self.prompt_panel.set_text("[Benchmark suite uses named prompts from _docs/benchmark_suite.json]")
        self.response_panel.set_text(self._format_benchmark_responses(result))
        self.events_panel.set_text("[Benchmark cases reuse the per-probe event logs stored in SQLite and exports.]")
        self.set_status(f"{result.suite_label}: avg score {result.metadata.get('average_overall_score', 0.0):.3f}")
        self.notebook.select(self.benchmark_tab)

    def show_error(self, message: str) -> None:
        self.set_status(f"Error: {message}")
        self.events_panel.set_text(message)
        self.notebook.select(self.events_tab)

    def show_history_message(self, text: str) -> None:
        self.history_panel.set_text(text)
        self.notebook.select(self.history_tab)

    def confirm_restore_version(self, version_id: int) -> bool:
        return messagebox.askyesno(
            "Restore Prompt Version",
            f"Restore prompt version {version_id} into the live prompt docs and project overrides?\n\n"
            "This overwrites the current prompt assets on disk, but the version history remains available.",
            parent=self.root,
        )

    def _configure_root(self) -> None:
        self.root.title("Agent Diagnostic Lab")
        self.root.geometry("1500x980")
        self.root.configure(bg=theme.BG_DARK)
        self.root.rowconfigure(2, weight=1)
        self.root.columnconfigure(0, weight=1)

    def _build_styles(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("default")
        style.configure("Lab.TNotebook", background=theme.BG_DARK, borderwidth=0)
        style.configure(
            "Lab.TNotebook.Tab",
            background=theme.BG_MID,
            foreground=theme.TEXT_DIM,
            padding=(14, 8),
            font=theme.FONT_BODY,
        )
        style.map(
            "Lab.TNotebook.Tab",
            background=[("selected", theme.BG_LIGHT), ("active", theme.BG_LIGHT)],
            foreground=[("selected", theme.CYAN), ("active", theme.TEXT_BRIGHT)],
        )
        style.configure(
            "Lab.TCombobox",
            fieldbackground=theme.BG_LIGHT,
            background=theme.BG_LIGHT,
            foreground=theme.TEXT_PRIMARY,
            arrowcolor=theme.CYAN,
        )

    def _build_layout(self) -> None:
        header = tk.Frame(self.root, bg=theme.BG_DARK)
        header.grid(row=0, column=0, sticky="ew", padx=18, pady=(16, 10))
        header.columnconfigure(1, weight=1)
        title = tk.Label(header, text="AGENT DIAGNOSTIC LAB", bg=theme.BG_DARK, fg=theme.CYAN, font=theme.FONT_TITLE)
        title.grid(row=0, column=0, sticky="w")
        subtitle = tk.Label(
            header,
            text="Prompt / Model / Engine probes for tuning the local agent",
            bg=theme.BG_DARK,
            fg=theme.TEXT_DIM,
            font=theme.FONT_BODY,
        )
        subtitle.grid(row=0, column=1, sticky="w", padx=(16, 0))

        metrics = tk.Frame(self.root, bg=theme.BG_DARK)
        metrics.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 12))
        for idx in range(6):
            metrics.columnconfigure(idx, weight=1)
        self.cpu_card = MetricCard(metrics, "CPU")
        self.cpu_card.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.ram_card = MetricCard(metrics, "RAM")
        self.ram_card.grid(row=0, column=1, sticky="ew", padx=8)
        self.gpu_card = MetricCard(metrics, "VRAM")
        self.gpu_card.grid(row=0, column=2, sticky="ew", padx=8)
        self.models_card = MetricCard(metrics, "MODELS", accent=theme.CYAN)
        self.models_card.grid(row=0, column=3, sticky="ew", padx=8)
        self.score_card = MetricCard(metrics, "SCORE", accent=theme.GREEN)
        self.score_card.grid(row=0, column=4, sticky="ew", padx=8)
        self.events_card = MetricCard(metrics, "EVENTS", accent=theme.AMBER)
        self.events_card.grid(row=0, column=5, sticky="ew", padx=(8, 0))

        body = tk.PanedWindow(self.root, orient="horizontal", bg=theme.BG_DARK, sashwidth=8, sashrelief="flat")
        body.grid(row=2, column=0, sticky="nsew", padx=18, pady=(0, 10))

        control_col = tk.Frame(body, bg=theme.BG_DARK)
        control_col.rowconfigure(1, weight=1)
        control_col.columnconfigure(0, weight=1)
        body.add(control_col, minsize=400, width=430)

        results_col = tk.Frame(body, bg=theme.BG_DARK)
        results_col.rowconfigure(0, weight=1)
        results_col.columnconfigure(0, weight=1)
        body.add(results_col, minsize=700)

        control_frame = SectionFrame(control_col, "Probe Controls")
        control_frame.grid(row=0, column=0, sticky="nsew")
        self._build_controls(control_frame.body)

        last_probe_frame = SectionFrame(control_col, "Last Probe")
        last_probe_frame.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        last_probe_frame.body.columnconfigure(0, weight=1)
        self.last_probe_card = MetricCard(last_probe_frame.body, "LAST RESULT", value="(none)", accent=theme.CYAN)
        self.last_probe_card.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        self.version_id_var = tk.StringVar()
        self.compare_left_var = tk.StringVar()
        self.compare_right_var = tk.StringVar()
        tk.Label(last_probe_frame.body, text="Version ID", bg=theme.BG_MID, fg=theme.TEXT_DIM, font=theme.FONT_SMALL).grid(
            row=1, column=0, sticky="w", padx=10, pady=(6, 2)
        )
        restore_row = tk.Frame(last_probe_frame.body, bg=theme.BG_MID)
        restore_row.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 6))
        restore_row.columnconfigure(0, weight=1)
        tk.Entry(
            restore_row,
            textvariable=self.version_id_var,
            bg=theme.BG_LIGHT,
            fg=theme.TEXT_INPUT,
            insertbackground=theme.CYAN,
            relief="flat",
            font=theme.FONT_INPUT,
        ).grid(row=0, column=0, sticky="ew")
        self.restore_version_btn = self._action_button(restore_row, "Restore")
        self.restore_version_btn.grid(row=0, column=1, padx=(6, 0))
        tk.Label(last_probe_frame.body, text="Compare Benchmark Runs", bg=theme.BG_MID, fg=theme.TEXT_DIM, font=theme.FONT_SMALL).grid(
            row=3, column=0, sticky="w", padx=10, pady=(8, 2)
        )
        compare_row = tk.Frame(last_probe_frame.body, bg=theme.BG_MID)
        compare_row.grid(row=4, column=0, sticky="ew", padx=10, pady=(0, 6))
        compare_row.columnconfigure(0, weight=1)
        compare_row.columnconfigure(1, weight=1)
        tk.Entry(
            compare_row,
            textvariable=self.compare_left_var,
            bg=theme.BG_LIGHT,
            fg=theme.TEXT_INPUT,
            insertbackground=theme.CYAN,
            relief="flat",
            font=theme.FONT_INPUT,
        ).grid(row=0, column=0, sticky="ew")
        tk.Entry(
            compare_row,
            textvariable=self.compare_right_var,
            bg=theme.BG_LIGHT,
            fg=theme.TEXT_INPUT,
            insertbackground=theme.CYAN,
            relief="flat",
            font=theme.FONT_INPUT,
        ).grid(row=0, column=1, sticky="ew", padx=(6, 0))
        self.compare_runs_btn = self._action_button(compare_row, "Compare")
        self.compare_runs_btn.grid(row=0, column=2, padx=(6, 0))
        self.refresh_history_btn = self._action_button(last_probe_frame.body, "Refresh History")
        self.refresh_history_btn.grid(row=5, column=0, sticky="ew", padx=10, pady=(8, 6))
        tk.Label(last_probe_frame.body, text="Diff Prompt Versions", bg=theme.BG_MID, fg=theme.TEXT_DIM, font=theme.FONT_SMALL).grid(
            row=6, column=0, sticky="w", padx=10, pady=(8, 2)
        )
        self.diff_left_var = tk.StringVar()
        self.diff_right_var = tk.StringVar()
        diff_row = tk.Frame(last_probe_frame.body, bg=theme.BG_MID)
        diff_row.grid(row=7, column=0, sticky="ew", padx=10, pady=(0, 10))
        diff_row.columnconfigure(0, weight=1)
        diff_row.columnconfigure(1, weight=1)
        tk.Entry(
            diff_row,
            textvariable=self.diff_left_var,
            bg=theme.BG_LIGHT,
            fg=theme.TEXT_INPUT,
            insertbackground=theme.CYAN,
            relief="flat",
            font=theme.FONT_INPUT,
        ).grid(row=0, column=0, sticky="ew")
        tk.Entry(
            diff_row,
            textvariable=self.diff_right_var,
            bg=theme.BG_LIGHT,
            fg=theme.TEXT_INPUT,
            insertbackground=theme.CYAN,
            relief="flat",
            font=theme.FONT_INPUT,
        ).grid(row=0, column=1, sticky="ew", padx=(6, 0))
        self.diff_versions_btn = self._action_button(diff_row, "Diff")
        self.diff_versions_btn.grid(row=0, column=2, padx=(6, 0))

        self.notebook = ttk.Notebook(results_col, style="Lab.TNotebook")
        self.notebook.grid(row=0, column=0, sticky="nsew")
        self.summary_tab = self._make_tab("Summary")
        self.benchmark_tab = self._make_tab("Benchmarks")
        self.history_tab = self._make_tab("History")
        self.prompt_tab = self._make_tab("Prompt")
        self.response_tab = self._make_tab("Response")
        self.events_tab = self._make_tab("Events")

        self.summary_panel = LogPanel(self.summary_tab)
        self.summary_panel.pack(fill="both", expand=True, padx=10, pady=10)
        self.benchmark_panel = LogPanel(self.benchmark_tab)
        self.benchmark_panel.pack(fill="both", expand=True, padx=10, pady=10)
        self.history_panel = LogPanel(self.history_tab)
        self.history_panel.pack(fill="both", expand=True, padx=10, pady=10)
        self.prompt_panel = LogPanel(self.prompt_tab)
        self.prompt_panel.pack(fill="both", expand=True, padx=10, pady=10)
        self.response_panel = LogPanel(self.response_tab)
        self.response_panel.pack(fill="both", expand=True, padx=10, pady=10)
        self.events_panel = LogPanel(self.events_tab)
        self.events_panel.pack(fill="both", expand=True, padx=10, pady=10)

        footer = tk.Frame(self.root, bg=theme.BG_DARK)
        footer.grid(row=3, column=0, sticky="ew", padx=18, pady=(0, 16))
        footer.columnconfigure(0, weight=1)
        self.status_var = tk.StringVar(value="Ready")
        status_label = tk.Label(footer, textvariable=self.status_var, bg=theme.BG_DARK, fg=theme.TEXT_DIM, font=theme.FONT_BODY)
        status_label.grid(row=0, column=0, sticky="w")

    def _build_controls(self, parent: tk.Frame) -> None:
        parent.configure(bg=theme.BG_MID)
        parent.columnconfigure(1, weight=1)
        row = 0

        self.sandbox_var = tk.StringVar()
        self.base_url_var = tk.StringVar(value="http://localhost:11434")
        self.model_var = tk.StringVar()
        self.temperature_var = tk.StringVar(value="0.7")
        self.ctx_var = tk.StringVar(value="8192")
        self.docker_var = tk.IntVar(value=0)
        self.benchmark_var = tk.StringVar(value="default")

        for label_text, variable in (
            ("Sandbox Root", self.sandbox_var),
            ("Ollama URL", self.base_url_var),
        ):
            tk.Label(parent, text=label_text, bg=theme.BG_MID, fg=theme.TEXT_DIM, font=theme.FONT_SMALL).grid(
                row=row, column=0, sticky="w", padx=12, pady=(10, 4)
            )
            entry = tk.Entry(
                parent,
                textvariable=variable,
                bg=theme.BG_LIGHT,
                fg=theme.TEXT_INPUT,
                insertbackground=theme.CYAN,
                relief="flat",
                font=theme.FONT_INPUT,
            )
            entry.grid(row=row, column=1, sticky="ew", padx=12, pady=(10, 4))
            row += 1

        tk.Label(parent, text="Model", bg=theme.BG_MID, fg=theme.TEXT_DIM, font=theme.FONT_SMALL).grid(
            row=row, column=0, sticky="w", padx=12, pady=(10, 4)
        )
        self.model_combo = ttk.Combobox(parent, textvariable=self.model_var, style="Lab.TCombobox")
        self.model_combo.grid(row=row, column=1, sticky="ew", padx=12, pady=(10, 4))
        row += 1

        tk.Label(parent, text="Temperature", bg=theme.BG_MID, fg=theme.TEXT_DIM, font=theme.FONT_SMALL).grid(
            row=row, column=0, sticky="w", padx=12, pady=(10, 4)
        )
        tk.Spinbox(
            parent,
            from_=0.0,
            to=2.0,
            increment=0.1,
            textvariable=self.temperature_var,
            bg=theme.BG_LIGHT,
            fg=theme.TEXT_INPUT,
            insertbackground=theme.CYAN,
            relief="flat",
            font=theme.FONT_INPUT,
        ).grid(row=row, column=1, sticky="ew", padx=12, pady=(10, 4))
        row += 1

        tk.Label(parent, text="Context Tokens", bg=theme.BG_MID, fg=theme.TEXT_DIM, font=theme.FONT_SMALL).grid(
            row=row, column=0, sticky="w", padx=12, pady=(10, 4)
        )
        tk.Spinbox(
            parent,
            from_=1024,
            to=65536,
            increment=1024,
            textvariable=self.ctx_var,
            bg=theme.BG_LIGHT,
            fg=theme.TEXT_INPUT,
            insertbackground=theme.CYAN,
            relief="flat",
            font=theme.FONT_INPUT,
        ).grid(row=row, column=1, sticky="ew", padx=12, pady=(10, 4))
        row += 1

        tk.Checkbutton(
            parent,
            text="Probe in Docker mode",
            variable=self.docker_var,
            bg=theme.BG_MID,
            fg=theme.TEXT_PRIMARY,
            activebackground=theme.BG_MID,
            activeforeground=theme.CYAN,
            selectcolor=theme.BG_LIGHT,
            font=theme.FONT_BODY,
        ).grid(row=row, column=0, columnspan=2, sticky="w", padx=12, pady=(10, 6))
        row += 1

        tk.Label(parent, text="Benchmark Suite", bg=theme.BG_MID, fg=theme.TEXT_DIM, font=theme.FONT_SMALL).grid(
            row=row, column=0, sticky="w", padx=12, pady=(10, 4)
        )
        benchmark_row = tk.Frame(parent, bg=theme.BG_MID)
        benchmark_row.grid(row=row, column=1, sticky="ew", padx=12, pady=(10, 4))
        benchmark_row.columnconfigure(0, weight=1)
        self.benchmark_combo = ttk.Combobox(benchmark_row, textvariable=self.benchmark_var, style="Lab.TCombobox")
        self.benchmark_combo.grid(row=0, column=0, sticky="ew")
        self.refresh_benchmarks_btn = self._action_button(benchmark_row, "↻")
        self.refresh_benchmarks_btn.grid(row=0, column=1, padx=(6, 0))
        row += 1

        tk.Label(parent, text="Prompt / Test Input", bg=theme.BG_MID, fg=theme.TEXT_DIM, font=theme.FONT_SMALL).grid(
            row=row, column=0, columnspan=2, sticky="w", padx=12, pady=(10, 4)
        )
        row += 1
        self.prompt_text = tk.Text(
            parent,
            height=14,
            bg=theme.BG_LIGHT,
            fg=theme.TEXT_INPUT,
            insertbackground=theme.CYAN,
            relief="flat",
            font=theme.FONT_BODY,
            wrap="word",
        )
        self.prompt_text.grid(row=row, column=0, columnspan=2, sticky="nsew", padx=12, pady=(0, 10))
        parent.rowconfigure(row, weight=1)
        row += 1

        button_row = tk.Frame(parent, bg=theme.BG_MID)
        button_row.grid(row=row, column=0, columnspan=2, sticky="ew", padx=12, pady=(4, 12))
        for idx in range(2):
            button_row.columnconfigure(idx, weight=1)
        self.refresh_models_btn = self._action_button(button_row, "Refresh Models")
        self.refresh_models_btn.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.refresh_resources_btn = self._action_button(button_row, "Refresh Resources")
        self.refresh_resources_btn.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        self.prompt_probe_btn = self._action_button(button_row, "Prompt Probe")
        self.prompt_probe_btn.grid(row=1, column=0, sticky="ew", padx=(0, 6), pady=(10, 0))
        self.direct_probe_btn = self._action_button(button_row, "Direct Model")
        self.direct_probe_btn.grid(row=1, column=1, sticky="ew", padx=(6, 0), pady=(10, 0))
        self.engine_probe_btn = self._action_button(button_row, "Engine Turn")
        self.engine_probe_btn.grid(row=2, column=0, sticky="ew", padx=(0, 6), pady=(10, 0))
        self.stop_btn = self._action_button(button_row, "Stop Active", accent=theme.MAGENTA)
        self.stop_btn.grid(row=2, column=1, sticky="ew", padx=(6, 0), pady=(10, 0))
        self.benchmark_btn = self._action_button(button_row, "Run Suite", accent=theme.GREEN)
        self.benchmark_btn.grid(row=3, column=0, sticky="ew", padx=(0, 6), pady=(10, 0))
        self.export_btn = self._action_button(button_row, "Export Report", accent=theme.GREEN)
        self.export_btn.grid(row=3, column=1, sticky="ew", padx=(6, 0), pady=(10, 0))

    def _make_tab(self, title: str) -> tk.Frame:
        frame = tk.Frame(self.notebook, bg=theme.BG_MID)
        self.notebook.add(frame, text=title)
        return frame

    def _action_button(self, master, text: str, accent: str | None = None) -> tk.Button:
        return tk.Button(
            master,
            text=text,
            bg=accent or theme.BG_LIGHT,
            fg=theme.CYAN if accent is None else theme.BG_DARK,
            activebackground=theme.CYAN if accent is None else accent,
            activeforeground=theme.BG_DARK,
            relief="flat",
            bd=0,
            padx=10,
            pady=8,
            font=theme.FONT_BUTTON,
            cursor="hand2",
        )

    def _set_defaults(self) -> None:
        self.sandbox_var.set(str(self.toolbox_root))
        self.prompt_text.insert(
            "1.0",
            "Summarize how this app would handle a user request to inspect a Python codebase, "
            "then note which tools it would likely call first.",
        )
        self.summary_panel.set_text("Run a probe to inspect prompt assembly, direct model streaming, or the full engine loop.")
        self.benchmark_panel.set_text("Run a benchmark suite to compare intent, context, and reality handling with a reusable score.")
        self.prompt_panel.set_text("[No prompt built yet]")
        self.response_panel.set_text("[No response yet]")
        self.events_panel.set_text("[No events captured yet]")
        self.history_panel.set_text("Refresh history to inspect prompt versions, benchmark runs, and restore targets.")

    def _format_summary(self, result: ProbeResult) -> str:
        lines = [
            f"Name: {result.name}",
            f"Status: {result.status}",
            f"Summary: {result.summary}",
            f"Started: {result.started_at}",
            f"Ended: {result.ended_at}",
            f"Duration: {result.duration_ms:.1f} ms",
            f"Events: {len(result.events)}",
            "",
            "Metadata:",
        ]
        for key, value in sorted(result.metadata.items()):
            lines.append(f"- {key}: {value}")
        if result.warnings:
            lines.extend(["", "Warnings:"])
            lines.extend([f"- {warning}" for warning in result.warnings])
        return "\n".join(lines)

    def _format_benchmark_summary(self, result: BenchmarkSuiteResult) -> str:
        lines = [
            f"Suite: {result.suite_label}",
            f"Name: {result.suite_name}",
            f"Description: {result.suite_description}",
            f"Started: {result.started_at}",
            f"Ended: {result.ended_at}",
            f"Duration: {result.duration_ms:.1f} ms",
            "",
            "Aggregate Metrics:",
        ]
        for key, value in sorted(result.metadata.items()):
            lines.append(f"- {key}: {value}")
        return "\n".join(lines)

    def _format_benchmark_cases(self, result: BenchmarkSuiteResult) -> str:
        lines: list[str] = []
        for case in result.cases:
            probe = case.result
            m = probe.metadata
            # Model role line — only include roles that are populated
            role_parts = [f"chat={m.get('model', '—')}"]
            if m.get("planner_model"):
                role_parts.append(f"planner={m['planner_model']}")
            if m.get("fast_probe_model"):
                role_parts.append(f"probe={m['fast_probe_model']}")
            lines.extend(
                [
                    f"[{case.case_id}] {case.label}",
                    f"  - Probe type:      {case.probe_type}",
                    f"  - Status:          {probe.status}",
                    f"  - Loop mode:       {m.get('loop_mode', '—')}",
                    f"  - Models:          {', '.join(role_parts)}",
                    f"  - Planning used:   {m.get('planning_used', False)}",
                    f"  - Probes run:      {m.get('probes_run', 0)} ({m.get('probe_total_ms', 0):.0f}ms)",
                    f"  - STM window:      {m.get('stm_window_size', '—')} turns, falloff={m.get('stm_falloff_count', 0)}",
                    f"  - Budget:          {m.get('budget_total_after', '?')}/{m.get('budget_available', '?')} tokens"
                    + (" ⚠ TRIMMED" if m.get("budget_trimmed") else ""),
                    f"  - Overall score:   {m.get('overall_score', 0.0)}",
                    f"  - Accuracy score:  {m.get('accuracy_score', 0.0)}",
                    f"  - Efficiency score:{m.get('efficiency_score', 0.0)}",
                    f"  - Tokens:          {m.get('total_tokens', 0)}",
                    f"  - Rounds:          {m.get('rounds', 0)}",
                    f"  - Summary:         {probe.summary}",
                    "",
                ]
            )
        return "\n".join(lines).rstrip() or "[No benchmark results]"

    def _format_benchmark_responses(self, result: BenchmarkSuiteResult) -> str:
        lines: list[str] = []
        for case in result.cases:
            excerpt = case.result.response_text[:1200].strip() or "[No response text]"
            lines.extend(
                [
                    f"## {case.label}",
                    excerpt,
                    "",
                ]
            )
        return "\n".join(lines).rstrip() or "[No benchmark responses]"

    def _format_events(self, result: ProbeResult) -> str:
        if not result.events:
            return "[No events captured]"
        return "\n".join(
            f"[{event.timestamp}] {event.kind.upper():<6} {event.source}: {event.message}"
            for event in result.events
        )
