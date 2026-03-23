"""
FILE: app_journal_ui.py
ROLE: Tkinter manager UI for _app-journal.
WHAT IT DOES: Opens a project-local SQLite journal, shows recent entries, supports search, and lets a user create, update, append, and export notes.
HOW TO USE:
  - python _app-journal/ui/app_journal_ui.py --project-root C:\\path\\to\\project
"""

from __future__ import annotations

import argparse
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from lib.journal_store import export_entries, initialize_store, parse_tags, query_entries, write_entry


class AppJournalUI(ttk.Frame):
    def __init__(self, master: tk.Tk, *, project_root: str | None = None, db_path: str | None = None) -> None:
        super().__init__(master, padding=10)
        self.master = master
        self.paths = initialize_store(project_root=project_root, db_path=db_path)
        self.selected_entry_uid = ""
        self._entries_by_uid: dict[str, dict] = {}

        self.search_var = tk.StringVar()
        self.kind_var = tk.StringVar(value="")
        self.source_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="")

        self.title_var = tk.StringVar()
        self.kind_edit_var = tk.StringVar(value="note")
        self.source_edit_var = tk.StringVar(value="user")
        self.status_edit_var = tk.StringVar(value="open")
        self.tags_var = tk.StringVar()
        self.author_var = tk.StringVar()
        self.related_path_var = tk.StringVar()
        self.related_ref_var = tk.StringVar()

        self._build()
        self._refresh_entries()

    def _build(self) -> None:
        self.master.title("App Journal")
        self.master.geometry("1200x760")
        self.grid(sticky="nsew")
        self.master.columnconfigure(0, weight=1)
        self.master.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=3)
        self.columnconfigure(1, weight=2)
        self.rowconfigure(1, weight=1)

        header = ttk.Label(self, text=f"Project Journal: {self.paths['project_root']}")
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))

        left = ttk.Frame(self)
        left.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(1, weight=1)

        filter_frame = ttk.Frame(left)
        filter_frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        filter_frame.columnconfigure(1, weight=1)

        ttk.Label(filter_frame, text="Search").grid(row=0, column=0, sticky="w")
        ttk.Entry(filter_frame, textvariable=self.search_var).grid(row=0, column=1, sticky="ew", padx=(4, 8))
        ttk.Button(filter_frame, text="Refresh", command=self._refresh_entries).grid(row=0, column=2, padx=(0, 6))
        ttk.Button(filter_frame, text="Export", command=self._export_markdown).grid(row=0, column=3)

        ttk.Label(filter_frame, text="Kind").grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Combobox(filter_frame, textvariable=self.kind_var, values=["", "note", "decision", "todo", "issue", "log", "feedback"], state="readonly").grid(row=1, column=1, sticky="ew", padx=(4, 8), pady=(6, 0))
        ttk.Label(filter_frame, text="Source").grid(row=1, column=2, sticky="e", pady=(6, 0))
        ttk.Combobox(filter_frame, textvariable=self.source_var, values=["", "user", "agent", "system"], state="readonly", width=12).grid(row=1, column=3, sticky="w", pady=(6, 0))

        ttk.Label(filter_frame, text="Status").grid(row=2, column=0, sticky="w", pady=(6, 0))
        ttk.Combobox(filter_frame, textvariable=self.status_var, values=["", "open", "closed", "archived"], state="readonly").grid(row=2, column=1, sticky="ew", padx=(4, 8), pady=(6, 0))

        self.tree = ttk.Treeview(left, columns=("updated_at", "kind", "source", "status", "title"), show="headings", height=18)
        for name, width in (("updated_at", 150), ("kind", 90), ("source", 80), ("status", 80), ("title", 340)):
            self.tree.heading(name, text=name)
            self.tree.column(name, width=width, anchor="w")
        self.tree.grid(row=1, column=0, sticky="nsew")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        detail_frame = ttk.Frame(self)
        detail_frame.grid(row=1, column=1, sticky="nsew")
        detail_frame.columnconfigure(0, weight=1)
        detail_frame.rowconfigure(1, weight=1)
        detail_frame.rowconfigure(3, weight=2)

        ttk.Label(detail_frame, text="Selected Entry").grid(row=0, column=0, sticky="w")
        self.detail_text = tk.Text(detail_frame, wrap="word", height=10)
        self.detail_text.grid(row=1, column=0, sticky="nsew", pady=(4, 8))
        self.detail_text.configure(state="disabled")

        ttk.Label(detail_frame, text="Editor").grid(row=2, column=0, sticky="w")

        editor = ttk.Frame(detail_frame)
        editor.grid(row=3, column=0, sticky="nsew")
        for column in range(4):
            editor.columnconfigure(column, weight=1)
        editor.rowconfigure(4, weight=1)

        ttk.Label(editor, text="Title").grid(row=0, column=0, sticky="w")
        ttk.Entry(editor, textvariable=self.title_var).grid(row=0, column=1, columnspan=3, sticky="ew", padx=(4, 0))

        ttk.Label(editor, text="Kind").grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Combobox(editor, textvariable=self.kind_edit_var, values=["note", "decision", "todo", "issue", "log", "feedback"], state="readonly").grid(row=1, column=1, sticky="ew", padx=(4, 8), pady=(6, 0))
        ttk.Label(editor, text="Source").grid(row=1, column=2, sticky="w", pady=(6, 0))
        ttk.Combobox(editor, textvariable=self.source_edit_var, values=["user", "agent", "system"], state="readonly").grid(row=1, column=3, sticky="ew", pady=(6, 0))

        ttk.Label(editor, text="Status").grid(row=2, column=0, sticky="w", pady=(6, 0))
        ttk.Combobox(editor, textvariable=self.status_edit_var, values=["open", "closed", "archived"], state="readonly").grid(row=2, column=1, sticky="ew", padx=(4, 8), pady=(6, 0))
        ttk.Label(editor, text="Tags").grid(row=2, column=2, sticky="w", pady=(6, 0))
        ttk.Entry(editor, textvariable=self.tags_var).grid(row=2, column=3, sticky="ew", pady=(6, 0))

        ttk.Label(editor, text="Author").grid(row=3, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(editor, textvariable=self.author_var).grid(row=3, column=1, sticky="ew", padx=(4, 8), pady=(6, 0))
        ttk.Label(editor, text="Related Path").grid(row=3, column=2, sticky="w", pady=(6, 0))
        ttk.Entry(editor, textvariable=self.related_path_var).grid(row=3, column=3, sticky="ew", pady=(6, 0))

        ttk.Label(editor, text="Related Ref").grid(row=4, column=0, sticky="nw", pady=(8, 0))
        ttk.Entry(editor, textvariable=self.related_ref_var).grid(row=4, column=1, sticky="ew", padx=(4, 8), pady=(8, 0))
        ttk.Label(editor, text="Body").grid(row=5, column=0, sticky="nw", pady=(8, 0))
        self.body_text = tk.Text(editor, wrap="word", height=12)
        self.body_text.grid(row=5, column=1, columnspan=3, sticky="nsew", pady=(8, 0))

        action_bar = ttk.Frame(editor)
        action_bar.grid(row=6, column=0, columnspan=4, sticky="ew", pady=(8, 0))
        ttk.Button(action_bar, text="New Draft", command=self._clear_editor).pack(side="left")
        ttk.Button(action_bar, text="Save New", command=self._save_new).pack(side="left", padx=(6, 0))
        ttk.Button(action_bar, text="Save Update", command=self._save_update).pack(side="left", padx=(6, 0))
        ttk.Button(action_bar, text="Append To Selected", command=self._append_selected).pack(side="left", padx=(6, 0))

    def _refresh_entries(self) -> None:
        result = query_entries(
            db_path=self.paths["db_path"],
            query=self.search_var.get(),
            kind=self.kind_var.get(),
            source=self.source_var.get(),
            status=self.status_var.get(),
            limit=200,
        )
        for item in self.tree.get_children():
            self.tree.delete(item)
        self._entries_by_uid = {}
        for entry in result["entries"]:
            self._entries_by_uid[entry["entry_uid"]] = entry
            self.tree.insert(
                "",
                "end",
                iid=entry["entry_uid"],
                values=(entry["updated_at"], entry["kind"], entry["source"], entry["status"], entry["title"]),
            )

    def _on_select(self, _event: object) -> None:
        selected = self.tree.selection()
        if not selected:
            return
        entry_uid = selected[0]
        entry = self._entries_by_uid.get(entry_uid)
        if not entry:
            return
        self.selected_entry_uid = entry_uid
        self.title_var.set(entry["title"])
        self.kind_edit_var.set(entry["kind"])
        self.source_edit_var.set(entry["source"])
        self.status_edit_var.set(entry["status"])
        self.tags_var.set(", ".join(entry["tags"]))
        self.author_var.set(entry["author"])
        self.related_path_var.set(entry["related_path"])
        self.related_ref_var.set(entry["related_ref"])
        self.body_text.delete("1.0", "end")
        self.body_text.insert("1.0", entry["body"])
        detail = [
            f"entry_uid: {entry['entry_uid']}",
            f"created_at: {entry['created_at']}",
            f"updated_at: {entry['updated_at']}",
            f"kind: {entry['kind']}",
            f"source: {entry['source']}",
            f"status: {entry['status']}",
            f"tags: {', '.join(entry['tags'])}",
            "",
            entry["body"],
        ]
        self.detail_text.configure(state="normal")
        self.detail_text.delete("1.0", "end")
        self.detail_text.insert("1.0", "\n".join(detail))
        self.detail_text.configure(state="disabled")

    def _editor_payload(self) -> dict[str, object]:
        return {
            "db_path": self.paths["db_path"],
            "title": self.title_var.get().strip(),
            "body": self.body_text.get("1.0", "end").strip(),
            "kind": self.kind_edit_var.get().strip() or "note",
            "source": self.source_edit_var.get().strip() or "user",
            "status": self.status_edit_var.get().strip() or "open",
            "tags": parse_tags(self.tags_var.get()),
            "author": self.author_var.get().strip(),
            "related_path": self.related_path_var.get().strip(),
            "related_ref": self.related_ref_var.get().strip(),
        }

    def _save_new(self) -> None:
        payload = self._editor_payload()
        entry = write_entry(action="create", **payload)
        self.selected_entry_uid = entry["entry_uid"]
        self._refresh_entries()
        self.tree.selection_set(entry["entry_uid"])
        self.tree.see(entry["entry_uid"])

    def _save_update(self) -> None:
        if not self.selected_entry_uid:
            messagebox.showinfo("App Journal", "Select an entry to update first.")
            return
        payload = self._editor_payload()
        entry = write_entry(action="update", entry_uid=self.selected_entry_uid, **payload)
        self._refresh_entries()
        self.tree.selection_set(entry["entry_uid"])
        self.tree.see(entry["entry_uid"])

    def _append_selected(self) -> None:
        if not self.selected_entry_uid:
            messagebox.showinfo("App Journal", "Select an entry to append to first.")
            return
        entry = write_entry(
            action="append",
            entry_uid=self.selected_entry_uid,
            db_path=self.paths["db_path"],
            append_text=self.body_text.get("1.0", "end").strip(),
            status=self.status_edit_var.get().strip() or None,
        )
        self.body_text.delete("1.0", "end")
        self._refresh_entries()
        self.tree.selection_set(entry["entry_uid"])
        self.tree.see(entry["entry_uid"])

    def _clear_editor(self) -> None:
        self.selected_entry_uid = ""
        self.title_var.set("")
        self.kind_edit_var.set("note")
        self.source_edit_var.set("user")
        self.status_edit_var.set("open")
        self.tags_var.set("")
        self.author_var.set("")
        self.related_path_var.set("")
        self.related_ref_var.set("")
        self.body_text.delete("1.0", "end")
        self.detail_text.configure(state="normal")
        self.detail_text.delete("1.0", "end")
        self.detail_text.configure(state="disabled")

    def _export_markdown(self) -> None:
        result = export_entries(
            db_path=self.paths["db_path"],
            query=self.search_var.get(),
            kind=self.kind_var.get(),
            source=self.source_var.get(),
            status=self.status_var.get(),
            format_name="markdown",
        )
        messagebox.showinfo("App Journal", f"Exported journal view to:\n{result['export_path']}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Launch the App Journal Tkinter manager.")
    parser.add_argument("--project-root", help="Project root whose _docs journal should be opened.")
    parser.add_argument("--db-path", help="Explicit path to the SQLite journal file.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = tk.Tk()
    AppJournalUI(root, project_root=args.project_root, db_path=args.db_path)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
