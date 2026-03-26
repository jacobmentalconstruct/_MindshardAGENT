"""Dedicated Prompt Lab workbench shell.

Phase 2 keeps this workbench intentionally restrained:
- separate from the main app shell
- service-first and inspection/admin-safe
- no rich freeform editing or graph canvas yet
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any

from src.core.project.source_file_service import open_folder
from src.core.prompt_lab import (
    PromptLabServiceBundle,
    build_prompt_lab_services,
    describe_active_prompt_lab_runtime,
    get_promotion_status,
)
from src.core.prompt_lab.contracts import serialize_record


BG = "#0a0f1a"
SURFACE = "#111827"
SURFACE_ALT = "#1f2937"
BORDER = "#2a3b55"
CYAN = "#19f0ff"
GREEN = "#6ef68c"
YELLOW = "#f6d365"
TEXT = "#d8e7ff"
TEXT_DIM = "#8aa1c4"
RED = "#ff6b7a"
FONT = ("Consolas", 10)
FONT_BOLD = ("Consolas", 10, "bold")
FONT_HEAD = ("Consolas", 12, "bold")


def _pretty_json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True)


def _safe_serialize(record: Any) -> dict[str, Any]:
    return serialize_record(record)


def _readable_status(status: str) -> str:
    return status.replace("_", " ").strip().title() if status else "Unknown"


@dataclass(frozen=True)
class PromptLabWorkbenchState:
    project_root: Path
    metadata: dict[str, Any]
    paths: dict[str, str]
    runtime_summary: str
    promotion_state: str
    promotion_message: str
    active_package_id: str
    active_validation_status: str = "unknown"
    active_validation_snapshot_id: str = ""
    latest_validation_id: str = ""
    latest_validation_status: str = "unknown"
    counts: dict[str, int] = field(default_factory=dict)


def build_workbench_state(project_root: str | Path) -> PromptLabWorkbenchState:
    root = Path(project_root).resolve()
    services = build_prompt_lab_services(root)
    promotion_status = get_promotion_status(root)
    active_package = services.package_service.resolve_active_package()
    validations = services.storage.list_history_records("validation_snapshot")
    latest_validation = validations[0] if validations else None
    counts = {
        "profiles": len(services.profile_service.list_profiles()),
        "plans": len(services.execution_plan_service.list_plans()),
        "bindings": len(services.binding_service.list_bindings()),
        "artifacts": len(services.storage.list_design_objects("prompt_build_artifact")),
        "packages": len(services.package_service.list_published_packages()),
        "eval_runs": len(services.storage.list_history_records("eval_run")),
        "promotions": len(services.storage.list_history_records("promotion_record")),
        "validations": len(services.storage.list_history_records("validation_snapshot")),
    }
    return PromptLabWorkbenchState(
        project_root=root,
        metadata=dict(services.metadata),
        paths={
            field_name: str(getattr(services.storage.paths, field_name))
            for field_name in services.storage.paths.__dataclass_fields__
        },
        runtime_summary=describe_active_prompt_lab_runtime(root),
        promotion_state=promotion_status.state,
        promotion_message=promotion_status.message,
        active_package_id=promotion_status.active_package_id,
        active_validation_status=(
            active_package.validation_status if active_package is not None else "unknown"
        ),
        active_validation_snapshot_id=(
            active_package.validation_snapshot_id if active_package is not None else ""
        ),
        latest_validation_id=(latest_validation["id"] if latest_validation is not None else ""),
        latest_validation_status=(latest_validation["status"] if latest_validation is not None else "unknown"),
        counts=counts,
    )


def launch_prompt_lab_workbench_process(project_root: str | Path) -> str | None:
    root = Path(project_root).resolve()
    script_path = Path(__file__).resolve().with_name("main.py")
    command = [
        sys.executable,
        str(script_path),
        "--project-root",
        str(root),
    ]
    try:
        subprocess.Popen(command, cwd=str(root))
        return None
    except Exception as exc:
        return str(exc)


class _ListPane(tk.Frame):
    def __init__(self, parent, title: str):
        super().__init__(parent, bg=BG)
        tk.Label(self, text=title, font=FONT_BOLD, fg=CYAN, bg=BG, anchor="w").pack(fill="x", padx=8, pady=(6, 2))
        frame = tk.Frame(self, bg=SURFACE, highlightthickness=1, highlightbackground=BORDER)
        frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.listbox = tk.Listbox(
            frame,
            bg=SURFACE,
            fg=TEXT,
            selectbackground="#164e63",
            selectforeground=TEXT,
            relief="flat",
            bd=0,
            highlightthickness=0,
            font=FONT,
        )
        scroll = tk.Scrollbar(frame, orient="vertical", command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scroll.set)
        self.listbox.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=6)
        scroll.pack(side="right", fill="y", pady=6, padx=(0, 6))


class _TextPane(tk.Frame):
    def __init__(self, parent, title: str):
        super().__init__(parent, bg=BG)
        tk.Label(self, text=title, font=FONT_BOLD, fg=CYAN, bg=BG, anchor="w").pack(fill="x", padx=8, pady=(6, 2))
        frame = tk.Frame(self, bg=SURFACE, highlightthickness=1, highlightbackground=BORDER)
        frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.text = tk.Text(
            frame,
            wrap="word",
            bg=SURFACE,
            fg=TEXT,
            relief="flat",
            bd=0,
            highlightthickness=0,
            insertbackground=CYAN,
            font=FONT,
        )
        scroll = tk.Scrollbar(frame, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=scroll.set)
        self.text.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=6)
        scroll.pack(side="right", fill="y", pady=6, padx=(0, 6))
        self.set_text("")

    def set_text(self, text: str) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", text)
        self.text.configure(state="disabled")


class PromptLabWorkbench(tk.Tk):
    def __init__(self, project_root: str | Path):
        super().__init__()
        self.project_root = Path(project_root).resolve()
        self.services: PromptLabServiceBundle = build_prompt_lab_services(self.project_root)
        self.title(f"Prompt Lab — {self.project_root.name}")
        self.configure(bg=BG)
        self.geometry("1380x920")
        self.minsize(1100, 760)
        self.option_add("*TCombobox*Listbox*Background", SURFACE)
        self.option_add("*TCombobox*Listbox*Foreground", TEXT)
        self._profile_ids: list[str] = []
        self._artifact_ids: list[str] = []
        self._plan_ids: list[str] = []
        self._binding_ids: list[str] = []
        self._package_ids: list[str] = []
        self._validation_ids: list[str] = []
        self._promotion_ids: list[str] = []
        self._eval_ids: list[str] = []
        self._selected_package_id: str | None = None
        self._build_ui()
        self._record_ui("open_workbench", "ok", {"project_root": str(self.project_root)})
        self.reload_all()

    def _record_ui(self, action: str, status: str, details: dict[str, Any] | None = None) -> None:
        self.services.operation_log.record(channel="ui", action=action, status=status, details=details or {})

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        header = tk.Frame(self, bg=BG)
        header.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 8))
        header.columnconfigure(1, weight=1)

        tk.Label(header, text="PROMPT LAB", font=("Consolas", 16, "bold"), fg=CYAN, bg=BG).grid(row=0, column=0, sticky="w")
        self._status_label = tk.Label(header, text="", font=FONT, fg=TEXT_DIM, bg=BG, justify="left")
        self._status_label.grid(row=0, column=1, sticky="ew", padx=(12, 0))

        actions = tk.Frame(header, bg=BG)
        actions.grid(row=0, column=2, sticky="e")
        self._button(actions, "Reload", self.reload_all).pack(side="left")
        self._button(actions, "Validate", self._validate_state).pack(side="left", padx=(6, 0))
        self._button(actions, "Open State Folder", self._open_state_folder).pack(side="left", padx=(6, 0))

        notebook = ttk.Notebook(self)
        notebook.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))

        self._sources_tab = self._build_sources_tab(notebook)
        self._build_tab = self._build_build_tab(notebook)
        self._execution_tab = self._build_execution_tab(notebook)
        self._bindings_tab = self._build_bindings_tab(notebook)
        self._promotion_tab = self._build_promotion_tab(notebook)
        self._evaluation_tab = self._build_evaluation_tab(notebook)

        notebook.add(self._sources_tab, text="Sources")
        notebook.add(self._build_tab, text="Build")
        notebook.add(self._execution_tab, text="Execution")
        notebook.add(self._bindings_tab, text="Bindings")
        notebook.add(self._promotion_tab, text="Promotion")
        notebook.add(self._evaluation_tab, text="Evaluation")

        self._operator_status = tk.Label(
            self,
            text="Ready.",
            font=FONT,
            fg=TEXT_DIM,
            bg=BG,
            anchor="w",
            justify="left",
        )
        self._operator_status.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 10))

    def _button(self, parent, text: str, command):
        return tk.Button(
            parent,
            text=text,
            command=command,
            font=FONT,
            fg=CYAN,
            bg=SURFACE_ALT,
            activeforeground=GREEN,
            activebackground=SURFACE,
            relief="flat",
            bd=0,
            padx=10,
            pady=4,
            cursor="hand2",
        )

    def _build_sources_tab(self, notebook) -> tk.Frame:
        tab = tk.Frame(notebook, bg=BG)
        tab.columnconfigure(1, weight=1)
        tab.rowconfigure(0, weight=1)
        left = _ListPane(tab, "PROMPT PROFILES")
        left.grid(row=0, column=0, sticky="nsw")
        right = tk.Frame(tab, bg=BG)
        right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(1, weight=1)
        right.rowconfigure(2, weight=2)
        self._sources_detail = _TextPane(right, "PROFILE DETAILS")
        self._sources_detail.pack(fill="both", expand=True)
        self._sources_preview = _TextPane(right, "SOURCE PREVIEW")
        self._sources_preview.pack(fill="both", expand=True)
        left.listbox.bind("<<ListboxSelect>>", self._on_profile_selected)
        self._profiles_list = left.listbox
        return tab

    def _build_build_tab(self, notebook) -> tk.Frame:
        tab = tk.Frame(notebook, bg=BG)
        tab.columnconfigure(1, weight=1)
        tab.rowconfigure(0, weight=1)
        left = _ListPane(tab, "BUILD ARTIFACTS")
        left.grid(row=0, column=0, sticky="nsw")
        right = tk.Frame(tab, bg=BG)
        right.grid(row=0, column=1, sticky="nsew")
        self._build_detail = _TextPane(right, "ARTIFACT DETAILS")
        self._build_detail.pack(fill="both", expand=True)
        self._build_preview = _TextPane(right, "COMPILED PROMPT")
        self._build_preview.pack(fill="both", expand=True)
        left.listbox.bind("<<ListboxSelect>>", self._on_artifact_selected)
        self._artifacts_list = left.listbox
        return tab

    def _build_execution_tab(self, notebook) -> tk.Frame:
        tab = tk.Frame(notebook, bg=BG)
        tab.columnconfigure(1, weight=1)
        tab.rowconfigure(0, weight=1)
        left = _ListPane(tab, "EXECUTION PLANS")
        left.grid(row=0, column=0, sticky="nsw")
        right = tk.Frame(tab, bg=BG)
        right.grid(row=0, column=1, sticky="nsew")
        self._execution_detail = _TextPane(right, "PLAN DETAILS")
        self._execution_detail.pack(fill="both", expand=True)
        self._execution_nodes = _TextPane(right, "PLAN NODES")
        self._execution_nodes.pack(fill="both", expand=True)
        left.listbox.bind("<<ListboxSelect>>", self._on_plan_selected)
        self._plans_list = left.listbox
        return tab

    def _build_bindings_tab(self, notebook) -> tk.Frame:
        tab = tk.Frame(notebook, bg=BG)
        tab.columnconfigure(1, weight=1)
        tab.rowconfigure(0, weight=1)
        left = _ListPane(tab, "BINDINGS")
        left.grid(row=0, column=0, sticky="nsw")
        right = tk.Frame(tab, bg=BG)
        right.grid(row=0, column=1, sticky="nsew")
        self._bindings_detail = _TextPane(right, "BINDING DETAILS")
        self._bindings_detail.pack(fill="both", expand=True)
        self._bindings_matrix = _TextPane(right, "BINDING MATRIX")
        self._bindings_matrix.pack(fill="both", expand=True)
        left.listbox.bind("<<ListboxSelect>>", self._on_binding_selected)
        self._bindings_list = left.listbox
        return tab

    def _build_promotion_tab(self, notebook) -> tk.Frame:
        tab = tk.Frame(notebook, bg=BG)
        tab.columnconfigure(1, weight=1)
        tab.rowconfigure(1, weight=1)

        top = tk.Frame(tab, bg=BG)
        top.grid(row=0, column=0, columnspan=2, sticky="ew")
        self._promotion_summary = _TextPane(top, "ACTIVE STATE")
        self._promotion_summary.pack(fill="x", expand=False)

        left = _ListPane(tab, "PUBLISHED PACKAGES")
        left.grid(row=1, column=0, sticky="nsw")
        right = tk.Frame(tab, bg=BG)
        right.grid(row=1, column=1, sticky="nsew")
        right.rowconfigure(1, weight=1)
        buttons = tk.Frame(right, bg=BG)
        buttons.pack(fill="x", padx=8, pady=(6, 0))
        self._activate_btn = self._button(buttons, "Activate Selected", self._activate_selected_package)
        self._activate_btn.pack(side="left")
        self._button(buttons, "Refresh", self.reload_all).pack(side="left", padx=(6, 0))
        self._button(buttons, "Inspect Active State", self._inspect_active_state).pack(side="left", padx=(6, 0))
        self._promotion_detail = _TextPane(right, "PACKAGE DETAILS")
        self._promotion_detail.pack(fill="both", expand=True)
        self._promotion_history = _TextPane(right, "PROMOTION HISTORY")
        self._promotion_history.pack(fill="both", expand=True)
        left.listbox.bind("<<ListboxSelect>>", self._on_package_selected)
        self._packages_list = left.listbox
        return tab

    def _build_evaluation_tab(self, notebook) -> tk.Frame:
        tab = tk.Frame(notebook, bg=BG)
        tab.columnconfigure(0, weight=1)
        tab.columnconfigure(1, weight=1)
        tab.columnconfigure(2, weight=2)
        tab.rowconfigure(1, weight=1)
        tab.rowconfigure(2, weight=1)

        self._evaluation_summary = _TextPane(tab, "VALIDATION SUMMARY")
        self._evaluation_summary.grid(row=0, column=0, columnspan=3, sticky="ew")

        validation_list = _ListPane(tab, "VALIDATION SNAPSHOTS")
        validation_list.grid(row=1, column=0, sticky="nsew")
        promotion_list = _ListPane(tab, "PROMOTION RECORDS")
        promotion_list.grid(row=1, column=1, sticky="nsew")
        self._evaluation_detail = _TextPane(tab, "DETAILS")
        self._evaluation_detail.grid(row=1, column=2, sticky="nsew")

        eval_list = _ListPane(tab, "EVAL RUNS")
        eval_list.grid(row=2, column=0, sticky="nsew")
        self._ops_text = _TextPane(tab, "RECENT OPERATIONS")
        self._ops_text.grid(row=2, column=1, columnspan=2, sticky="nsew")

        validation_list.listbox.bind("<<ListboxSelect>>", self._on_validation_selected)
        promotion_list.listbox.bind("<<ListboxSelect>>", self._on_promotion_record_selected)
        eval_list.listbox.bind("<<ListboxSelect>>", self._on_eval_selected)
        self._validations_list = validation_list.listbox
        self._promotion_records_list = promotion_list.listbox
        self._eval_runs_list = eval_list.listbox
        return tab

    def reload_all(self) -> None:
        state = build_workbench_state(self.project_root)
        self._status_label.config(
            text=(
                f"{self.project_root}\n"
                f"{state.runtime_summary.splitlines()[0]}\n"
                f"Profiles {state.counts['profiles']} | Plans {state.counts['plans']} | "
                f"Bindings {state.counts['bindings']} | Packages {state.counts['packages']}\n"
                f"Latest validation: {_readable_status(state.latest_validation_status)}"
                f"{f' ({state.latest_validation_id})' if state.latest_validation_id else ''}"
            )
        )
        self._promotion_summary.set_text(
            f"{state.runtime_summary}\n\n"
            f"Promotion: {_readable_status(state.promotion_state)}\n"
            f"{state.promotion_message}\n"
            f"Active validation: {_readable_status(state.active_validation_status)}"
            f"{f' ({state.active_validation_snapshot_id})' if state.active_validation_snapshot_id else ''}"
        )
        self._populate_profiles()
        self._populate_artifacts()
        self._populate_plans()
        self._populate_bindings()
        self._populate_packages()
        self._populate_evaluation()
        self._set_operator_status(
            "Reloaded Prompt Lab workbench state."
            if state.counts["packages"] or state.counts["profiles"] or state.counts["plans"]
            else "Prompt Lab is ready but empty. Create profiles, plans, and bindings through the settled services first."
        )
        self._record_ui("reload_workbench", "ok", {"project_root": str(self.project_root)})

    def _populate_profiles(self) -> None:
        items = self.services.profile_service.list_profiles()
        self._profile_ids = [item["id"] for item in items]
        self._replace_listbox_items(self._profiles_list, [
            f"{item['id']}  ({item.get('name') or 'unnamed'})" for item in items
        ])
        if items:
            self._profiles_list.selection_set(0)
            self._on_profile_selected()
        else:
            self._sources_detail.set_text("No prompt profiles yet.")
            self._sources_preview.set_text("Prompt profiles will appear here once created.")

    def _populate_artifacts(self) -> None:
        items = self.services.storage.list_design_objects("prompt_build_artifact")
        self._artifact_ids = [item["id"] for item in items]
        self._replace_listbox_items(self._artifacts_list, [
            f"{item['id']}  ({item.get('fingerprint', '')[:12] or 'no-fp'})" for item in items
        ])
        if items:
            self._artifacts_list.selection_set(0)
            self._on_artifact_selected()
        else:
            self._build_detail.set_text(
                "No build artifacts are stored yet.\n\n"
                "This Phase 2 workbench is intentionally layered over the settled services, "
                "so the Build tab only inspects persisted artifacts rather than generating new ones."
            )
            self._build_preview.set_text("")

    def _populate_plans(self) -> None:
        items = self.services.execution_plan_service.list_plans()
        self._plan_ids = [item["id"] for item in items]
        self._replace_listbox_items(self._plans_list, [
            f"{item['id']}  ({item.get('name') or 'unnamed'})" for item in items
        ])
        if items:
            self._plans_list.selection_set(0)
            self._on_plan_selected()
        else:
            self._execution_detail.set_text("No execution plans yet.")
            self._execution_nodes.set_text("")

    def _populate_bindings(self) -> None:
        items = self.services.binding_service.list_bindings()
        self._binding_ids = [item["id"] for item in items]
        self._replace_listbox_items(self._bindings_list, [
            f"{item['id']}  ({item.get('name') or item['id']})" for item in items
        ])
        self._bindings_matrix.set_text(self._render_binding_matrix())
        if items:
            self._bindings_list.selection_set(0)
            self._on_binding_selected()
        else:
            self._bindings_detail.set_text("No bindings yet.")

    def _populate_packages(self) -> None:
        items = self.services.package_service.list_published_packages()
        self._package_ids = [item["id"] for item in items]
        self._replace_listbox_items(self._packages_list, [
            f"{item['id']}  ({item.get('name') or 'unnamed'})" for item in items
        ])
        active_id = self.services.package_service.get_active_state()
        active_package_id = active_id.published_package_id if active_id is not None else ""
        if items:
            target_index = 0
            if active_package_id and active_package_id in self._package_ids:
                target_index = self._package_ids.index(active_package_id)
            self._packages_list.selection_set(target_index)
            self._on_package_selected()
        else:
            self._selected_package_id = None
            self._activate_btn.config(state="disabled", text="Activate Selected")
            self._promotion_detail.set_text("No published packages yet.")
            self._promotion_history.set_text("No promotion history yet.")

    def _populate_evaluation(self) -> None:
        validations = self.services.storage.list_history_records("validation_snapshot")
        promotions = self.services.storage.list_history_records("promotion_record")
        eval_runs = self.services.storage.list_history_records("eval_run")
        ops = self.services.operation_log.tail(limit=25)
        self._validation_ids = [item["id"] for item in validations]
        self._promotion_ids = [item["id"] for item in promotions]
        self._eval_ids = [item["id"] for item in eval_runs]
        latest_validation = validations[0] if validations else None
        self._evaluation_summary.set_text(
            "Validation snapshots: {0}\nPromotion records: {1}\nEval runs: {2}\nLatest validation: {3}".format(
                len(validations),
                len(promotions),
                len(eval_runs),
                f"{latest_validation['status']} ({latest_validation['id']})" if latest_validation else "none",
            )
        )
        self._replace_listbox_items(
            self._validations_list,
            [f"{item['id']} | {item['status']} | {item['created_at']}" for item in validations],
        )
        self._replace_listbox_items(
            self._promotion_records_list,
            [f"{item['id']} | {item['status']} | {item['created_at']}" for item in promotions],
        )
        self._replace_listbox_items(
            self._eval_runs_list,
            [f"{item['id']} | {item['status']} | {item['created_at']}" for item in eval_runs],
        )
        if validations:
            self._validations_list.selection_set(0)
            self._on_validation_selected()
        elif promotions:
            self._promotion_records_list.selection_set(0)
            self._on_promotion_record_selected()
        elif eval_runs:
            self._eval_runs_list.selection_set(0)
            self._on_eval_selected()
        else:
            self._evaluation_detail.set_text("No validation, promotion, or evaluation history yet.")
        self._ops_text.set_text(_pretty_json(ops))

    def _replace_listbox_items(self, listbox: tk.Listbox, items: list[str]) -> None:
        listbox.delete(0, "end")
        for item in items:
            listbox.insert("end", item)

    def _selected_id(self, listbox: tk.Listbox, ids: list[str]) -> str | None:
        selection = listbox.curselection()
        if not selection:
            return None
        index = int(selection[0])
        if index < 0 or index >= len(ids):
            return None
        return ids[index]

    def _on_profile_selected(self, _event=None) -> None:
        profile_id = self._selected_id(self._profiles_list, self._profile_ids)
        if not profile_id:
            return
        profile = self.services.profile_service.get_profile(profile_id)
        resolved_sources = self.services.source_service.resolve_profile_sources(profile)
        detail = _pretty_json(_safe_serialize(profile))
        preview_chunks: list[str] = []
        for source in resolved_sources:
            preview_chunks.append(f"# {source.path}\n{_pretty_json(source.metadata)}")
            if source.metadata.get("exists") and source.metadata.get("is_file"):
                try:
                    preview_chunks.append(self.services.source_service.read_source_text(source.path))
                except Exception as exc:
                    preview_chunks.append(f"(could not read source text: {exc})")
            else:
                preview_chunks.append("(missing or non-file source)")
            preview_chunks.append("")
        self._sources_detail.set_text(detail)
        self._sources_preview.set_text("\n".join(preview_chunks).strip())

    def _on_artifact_selected(self, _event=None) -> None:
        artifact_id = self._selected_id(self._artifacts_list, self._artifact_ids)
        if not artifact_id:
            return
        artifact = self.services.storage.load_design_object("prompt_build_artifact", artifact_id)
        self._build_detail.set_text(_pretty_json(_safe_serialize(artifact)))
        self._build_preview.set_text(artifact.compiled_text or "(artifact has no compiled text)")

    def _on_plan_selected(self, _event=None) -> None:
        plan_id = self._selected_id(self._plans_list, self._plan_ids)
        if not plan_id:
            return
        plan = self.services.execution_plan_service.get_plan(plan_id)
        nodes = sorted(plan.nodes, key=lambda node: node.order_index)
        node_lines = []
        for node in nodes:
            node_lines.append(
                f"{node.order_index}. {node.label} [{node.loop_type}]"
                f"{' (disabled)' if not node.enabled else ''}"
            )
            if node.wrapper:
                node_lines.append(f"   wrapper: {node.wrapper}")
            if node.condition:
                node_lines.append(f"   condition: {node.condition}")
            if node.runtime_policy:
                node_lines.append(f"   runtime_policy: {node.runtime_policy}")
        self._execution_detail.set_text(_pretty_json(_safe_serialize(plan)))
        self._execution_nodes.set_text("\n".join(node_lines) if node_lines else "(plan has no nodes)")

    def _on_binding_selected(self, _event=None) -> None:
        binding_id = self._selected_id(self._bindings_list, self._binding_ids)
        if not binding_id:
            return
        binding = self.services.binding_service.get_binding(binding_id)
        self._bindings_detail.set_text(_pretty_json(_safe_serialize(binding)))

    def _render_binding_matrix(self) -> str:
        lines = []
        for item in self.services.binding_service.list_bindings():
            binding = self.services.binding_service.get_binding(item["id"])
            lines.append(
                f"{binding.execution_plan_id} :: {binding.node_id} -> {binding.prompt_profile_id}"
                + (f" (fallback {binding.fallback_profile_id})" if binding.fallback_profile_id else "")
            )
        return "\n".join(lines) if lines else "(no bindings yet)"

    def _on_package_selected(self, _event=None) -> None:
        package_id = self._selected_id(self._packages_list, self._package_ids)
        if not package_id:
            return
        self._selected_package_id = package_id
        package = self.services.package_service.get_published_package(package_id)
        active_state = self.services.package_service.get_active_state()
        is_active = active_state is not None and active_state.published_package_id == package_id
        self._activate_btn.config(
            state="normal",
            text="Already Active" if is_active else "Activate Selected",
        )
        self._promotion_detail.set_text(
            f"Active package: {'yes' if is_active else 'no'}\n\n{_pretty_json(_safe_serialize(package))}"
        )
        self._promotion_history.set_text(self._render_package_promotion_history(package_id))
        self._set_operator_status(
            f"Selected package {package_id}."
            + (" It is already active." if is_active else " Use Activate Selected to make it runtime-consumable.")
        )

    def _render_package_promotion_history(self, package_id: str) -> str:
        records = self.services.storage.list_history_records("promotion_record")
        matching = [
            item for item in records
            if item["primary_ref"] == package_id
        ]
        if not matching:
            return "No promotion history recorded for this package yet."
        lines = []
        for item in matching:
            lines.append(f"{item['id']} | {item['status']} | {item['created_at']}")
        return "\n".join(lines)

    def _validate_state(self) -> None:
        snapshot = self.services.validate_state(self.services.storage)
        self.services.storage.save_validation_snapshot(snapshot)
        self._record_ui("validate_state", snapshot.status, {"snapshot_id": snapshot.id})
        self._populate_evaluation()
        self._set_operator_status(
            f"Validation completed: {_readable_status(snapshot.status)} with {len(snapshot.findings)} finding(s)."
        )
        messagebox.showinfo(
            "Prompt Lab Validation",
            f"Status: {snapshot.status}\nSnapshot: {snapshot.id}\nFindings: {len(snapshot.findings)}",
            parent=self,
        )

    def _activate_selected_package(self) -> None:
        package_id = self._selected_id(self._packages_list, self._package_ids)
        if not package_id:
            self._set_operator_status("Select a published package before activating it.", color=YELLOW)
            messagebox.showinfo("Prompt Lab", "Select a published package first.", parent=self)
            return
        active_state = self.services.package_service.get_active_state()
        if active_state is not None and active_state.published_package_id == package_id:
            self._set_operator_status(f"Package {package_id} is already active.", color=TEXT_DIM)
            messagebox.showinfo("Prompt Lab", f"Package {package_id} is already active.", parent=self)
            return
        try:
            active_state = self.services.package_service.activate_package(package_id, activated_by="workbench")
        except Exception as exc:
            self._record_ui("activate_package", "error", {"package_id": package_id, "message": str(exc)})
            self._set_operator_status(f"Activation failed for {package_id}: {exc}", color=RED)
            messagebox.showerror("Activation Failed", str(exc), parent=self)
            return
        self._record_ui("activate_package", "ok", {"package_id": active_state.published_package_id})
        self.reload_all()
        self._set_operator_status(
            f"Activated package {active_state.published_package_id}. The main app may now consume it as active published state.",
            color=GREEN,
        )
        messagebox.showinfo(
            "Prompt Lab",
            f"Activated package {active_state.published_package_id}.",
            parent=self,
        )

    def _open_state_folder(self) -> None:
        err = open_folder(self.services.storage.paths.state_root)
        if err:
            self._record_ui("open_state_folder", "error", {"message": str(err)})
            self._set_operator_status(f"Could not open Prompt Lab state folder: {err}", color=RED)
            messagebox.showerror("Open Folder Failed", err, parent=self)
            return
        self._record_ui("open_state_folder", "ok", {"path": str(self.services.storage.paths.state_root)})
        self._set_operator_status("Opened the Prompt Lab state folder.", color=TEXT_DIM)

    def _inspect_active_state(self) -> None:
        active_state = self.services.package_service.get_active_state()
        if active_state is None:
            self._set_operator_status("No active Prompt Lab package is set yet.", color=YELLOW)
            messagebox.showinfo("Prompt Lab", "No active Prompt Lab package is set yet.", parent=self)
            return
        package = self.services.package_service.resolve_active_package()
        detail = _pretty_json(_safe_serialize(active_state))
        if package is not None:
            detail += "\n\nPublished Package\n" + _pretty_json(_safe_serialize(package))
        self._promotion_detail.set_text(detail)
        self._set_operator_status(
            f"Inspected active state for package {active_state.published_package_id}.",
            color=TEXT_DIM,
        )

    def _on_validation_selected(self, _event=None) -> None:
        validation_id = self._selected_id(self._validations_list, self._validation_ids)
        if not validation_id:
            return
        record = self.services.storage.load_history_record("validation_snapshot", validation_id)
        findings = getattr(record, "findings", [])
        text = _pretty_json(_safe_serialize(record))
        if findings:
            text += "\n\nFindings\n" + "\n".join(
                f"- {finding['code']}: {finding['message']}" for finding in findings
            )
        self._evaluation_detail.set_text(text)
        self._set_operator_status(
            f"Selected validation snapshot {validation_id} with {len(findings)} finding(s).",
            color=TEXT_DIM,
        )

    def _on_promotion_record_selected(self, _event=None) -> None:
        promotion_id = self._selected_id(self._promotion_records_list, self._promotion_ids)
        if not promotion_id:
            return
        record = self.services.storage.load_history_record("promotion_record", promotion_id)
        self._evaluation_detail.set_text(_pretty_json(_safe_serialize(record)))
        self._set_operator_status(f"Selected promotion record {promotion_id}.", color=TEXT_DIM)

    def _on_eval_selected(self, _event=None) -> None:
        eval_id = self._selected_id(self._eval_runs_list, self._eval_ids)
        if not eval_id:
            return
        record = self.services.storage.load_history_record("eval_run", eval_id)
        self._evaluation_detail.set_text(_pretty_json(_safe_serialize(record)))
        self._set_operator_status(f"Selected eval run {eval_id}.", color=TEXT_DIM)

    def _set_operator_status(self, text: str, *, color: str = TEXT_DIM) -> None:
        self._operator_status.config(text=text, fg=color)


def run_prompt_lab_workbench(project_root: str | Path) -> int:
    app = PromptLabWorkbench(project_root)
    app.mainloop()
    return 0
