"""VCS panel — local git versioning UI for MindshardAGENT.

Two sub-tabs:
  Changes  — file status list, stage-all, commit form
  History  — commit log, revert-to button

Requires a MindshardVCS instance to be set after init via set_vcs().
"""

import threading
import tkinter as tk
from typing import Optional

from src.ui import theme as T


class VCSPanel(tk.Frame):
    """Version control panel for the .mindshard/ local git repo."""

    def __init__(self, parent, on_snapshot=None, **kw):
        kw.setdefault("bg", T.BG_DARK)
        super().__init__(parent, **kw)

        self._vcs = None
        self._on_snapshot = on_snapshot  # callable() — called after user commits

        # ── Mini tab bar ─────────────────────────────
        tab_bar = tk.Frame(self, bg=T.BG_DARK)
        tab_bar.pack(fill="x", padx=4, pady=(4, 0))

        self._tab_btns: dict[str, tk.Button] = {}
        self._active_sub = "Changes"
        for name in ("Changes", "History"):
            btn = tk.Button(
                tab_bar, text=name,
                font=(T.FONT_FAMILY, T.FONT_SIZE_SM, "bold"),
                fg=T.TEXT_DIM, bg=T.BG_DARK,
                activebackground=T.BG_MID, activeforeground=T.CYAN,
                relief="flat", bd=0, padx=8, pady=3, cursor="hand2",
                command=lambda n=name: self._switch(n),
            )
            btn.pack(side="left", padx=1)
            self._tab_btns[name] = btn

        tk.Frame(self, bg=T.BORDER, height=1).pack(fill="x", padx=6, pady=(2, 0))

        # ── Content container ────────────────────────
        self._container = tk.Frame(self, bg=T.BG_DARK)
        self._container.pack(fill="both", expand=True)

        # ── Changes tab ──────────────────────────────
        self._changes_frame = tk.Frame(self._container, bg=T.BG_DARK)

        tk.Label(self._changes_frame, text="CHANGED FILES", font=T.FONT_SMALL,
                 fg=T.TEXT_DIM, bg=T.BG_DARK).pack(anchor="w", padx=8, pady=(6, 2))

        listbox_frame = tk.Frame(self._changes_frame, bg=T.BG_LIGHT)
        listbox_frame.pack(fill="both", expand=True, padx=8)

        self._changes_list = tk.Listbox(
            listbox_frame, font=T.FONT_SMALL,
            fg=T.TEXT_PRIMARY, bg=T.BG_LIGHT,
            selectbackground=T.BG_SURFACE, selectforeground=T.CYAN,
            relief="flat", bd=0, highlightthickness=0,
            height=5, activestyle="none",
        )
        changes_scroll = tk.Scrollbar(listbox_frame, orient="vertical",
                                      command=self._changes_list.yview,
                                      bg=T.SCROLLBAR_BG, troughcolor=T.SCROLLBAR_BG)
        self._changes_list.configure(yscrollcommand=changes_scroll.set)
        changes_scroll.pack(side="right", fill="y")
        self._changes_list.pack(side="left", fill="both", expand=True)

        tk.Frame(self._changes_frame, bg=T.BORDER, height=1).pack(
            fill="x", padx=8, pady=4)

        tk.Label(self._changes_frame, text="COMMIT MESSAGE", font=T.FONT_SMALL,
                 fg=T.TEXT_DIM, bg=T.BG_DARK).pack(anchor="w", padx=8, pady=(0, 2))

        self._commit_msg = tk.Text(
            self._changes_frame, font=T.FONT_SMALL,
            fg=T.TEXT_INPUT, bg=T.BG_LIGHT,
            relief="flat", bd=0, highlightthickness=1,
            highlightbackground=T.BORDER, highlightcolor=T.CYAN,
            height=3, padx=6, pady=4, wrap="word",
        )
        self._commit_msg.pack(fill="x", padx=8, pady=(0, 4))
        self._commit_msg.insert("1.0", "")

        commit_btn = tk.Button(
            self._changes_frame, text="SNAPSHOT",
            font=T.FONT_BUTTON,
            fg=T.BG_DARK, bg=T.CYAN,
            activebackground=T.BLUE_SOFT, activeforeground=T.BG_DARK,
            relief="flat", bd=0, padx=10, pady=4, cursor="hand2",
            command=self._do_snapshot,
        )
        commit_btn.pack(fill="x", padx=8, pady=(0, 6))

        self._changes_status = tk.Label(
            self._changes_frame, text="", font=T.FONT_SMALL,
            fg=T.TEXT_DIM, bg=T.BG_DARK, anchor="w",
        )
        self._changes_status.pack(fill="x", padx=8, pady=(0, 4))

        # ── History tab ──────────────────────────────
        self._history_frame = tk.Frame(self._container, bg=T.BG_DARK)

        tk.Label(self._history_frame, text="SNAPSHOTS", font=T.FONT_SMALL,
                 fg=T.TEXT_DIM, bg=T.BG_DARK).pack(anchor="w", padx=8, pady=(6, 2))

        hist_frame = tk.Frame(self._history_frame, bg=T.BG_LIGHT)
        hist_frame.pack(fill="both", expand=True, padx=8)

        self._history_list = tk.Listbox(
            hist_frame, font=(T.FONT_FAMILY, T.FONT_SIZE_SM),
            fg=T.TEXT_PRIMARY, bg=T.BG_LIGHT,
            selectbackground=T.BG_SURFACE, selectforeground=T.CYAN,
            relief="flat", bd=0, highlightthickness=0,
            activestyle="none",
        )
        hist_scroll = tk.Scrollbar(hist_frame, orient="vertical",
                                   command=self._history_list.yview,
                                   bg=T.SCROLLBAR_BG, troughcolor=T.SCROLLBAR_BG)
        self._history_list.configure(yscrollcommand=hist_scroll.set)
        hist_scroll.pack(side="right", fill="y")
        self._history_list.pack(side="left", fill="both", expand=True)

        revert_btn = tk.Button(
            self._history_frame, text="REVERT TO SELECTED",
            font=T.FONT_BUTTON,
            fg=T.AMBER, bg=T.BG_LIGHT,
            activebackground=T.BG_SURFACE, activeforeground=T.AMBER,
            relief="flat", bd=0, padx=10, pady=4, cursor="hand2",
            command=self._do_revert,
        )
        revert_btn.pack(fill="x", padx=8, pady=6)

        self._history_status = tk.Label(
            self._history_frame, text="", font=T.FONT_SMALL,
            fg=T.TEXT_DIM, bg=T.BG_DARK, anchor="w",
        )
        self._history_status.pack(fill="x", padx=8, pady=(0, 4))

        # Store commit hashes for revert (parallel to listbox entries)
        self._commit_hashes: list[str] = []

        # ── Activate first tab ───────────────────────
        self._switch("Changes")

    # ── Tab switching ─────────────────────────────────

    def _switch(self, name: str) -> None:
        self._active_sub = name
        for tab_name, btn in self._tab_btns.items():
            if tab_name == name:
                btn.config(fg=T.CYAN, bg=T.BG_MID)
            else:
                btn.config(fg=T.TEXT_DIM, bg=T.BG_DARK)

        for frame in (self._changes_frame, self._history_frame):
            frame.place_forget()

        if name == "Changes":
            self._changes_frame.place(in_=self._container, x=0, y=0,
                                       relwidth=1.0, relheight=1.0)
            self._changes_frame.lift()
            self._refresh_changes()
        else:
            self._history_frame.place(in_=self._container, x=0, y=0,
                                      relwidth=1.0, relheight=1.0)
            self._history_frame.lift()
            self._refresh_history()

    # ── VCS binding ──────────────────────────────────

    def set_vcs(self, vcs) -> None:
        """Attach a MindshardVCS instance and refresh."""
        self._vcs = vcs
        self.refresh()

    def refresh(self) -> None:
        """Refresh whichever sub-tab is currently visible."""
        if self._active_sub == "Changes":
            self._refresh_changes()
        else:
            self._refresh_history()

    # ── Data refresh ─────────────────────────────────

    def _refresh_changes(self) -> None:
        if not self._vcs or not self._vcs.is_attached:
            self._changes_list.delete(0, "end")
            self._changes_list.insert("end", "  No VCS attached")
            return

        def _load():
            try:
                entries = self._vcs.status_entries()
            except Exception:
                entries = []
            self.after(0, lambda: self._populate_changes(entries))

        threading.Thread(target=_load, daemon=True).start()

    def _populate_changes(self, entries) -> None:
        self._changes_list.delete(0, "end")
        if not entries:
            self._changes_list.insert("end", "  ✓ No changes")
            return
        for entry in entries:
            marker = entry.index if entry.index != "-" else entry.workdir
            self._changes_list.insert("end", f"  {marker}  {entry.path}")

    def _refresh_history(self) -> None:
        if not self._vcs or not self._vcs.is_attached:
            self._history_list.delete(0, "end")
            self._history_list.insert("end", "  No VCS attached")
            return

        def _load():
            try:
                items = self._vcs.log(limit=20)
            except Exception:
                items = []
            self.after(0, lambda: self._populate_history(items))

        threading.Thread(target=_load, daemon=True).start()

    def _populate_history(self, items) -> None:
        from datetime import datetime
        self._history_list.delete(0, "end")
        self._commit_hashes.clear()
        if not items:
            self._history_list.insert("end", "  No snapshots yet")
            return
        for commit, summary, _author, ts in items:
            dt = datetime.fromtimestamp(ts).strftime("%m-%d %H:%M")
            label = f"  [{commit[:7]}] {dt}  {summary[:35]}"
            self._history_list.insert("end", label)
            self._commit_hashes.append(commit)

    # ── Actions ──────────────────────────────────────

    def _do_snapshot(self) -> None:
        if not self._vcs or not self._vcs.is_attached:
            self._changes_status.config(text="No VCS attached", fg=T.RED)
            return

        message = self._commit_msg.get("1.0", "end").strip()
        self._changes_status.config(text="Snapshotting...", fg=T.AMBER)

        def _run():
            try:
                commit_hash = self._vcs.snapshot(message or "")
                if commit_hash:
                    self.after(0, lambda: self._changes_status.config(
                        text=f"✓ Snapshot {commit_hash[:8]}", fg=T.GREEN))
                    self.after(0, lambda: self._commit_msg.delete("1.0", "end"))
                    self.after(0, self._refresh_changes)
                    if self._on_snapshot:
                        self.after(0, self._on_snapshot)
                else:
                    self.after(0, lambda: self._changes_status.config(
                        text="Nothing to commit", fg=T.TEXT_DIM))
                    self.after(0, self._refresh_changes)
            except Exception as e:
                err = str(e)[:60]
                self.after(0, lambda: self._changes_status.config(
                    text=f"Error: {err}", fg=T.RED))

        threading.Thread(target=_run, daemon=True).start()

    def _do_revert(self) -> None:
        if not self._vcs or not self._vcs.is_attached:
            return

        sel = self._history_list.curselection()
        if not sel:
            self._history_status.config(text="Select a snapshot first", fg=T.AMBER)
            return

        idx = sel[0]
        if idx >= len(self._commit_hashes):
            return

        commit_hash = self._commit_hashes[idx]
        from tkinter import messagebox
        if not messagebox.askyesno("Revert Workspace",
                                    f"Hard reset workspace to snapshot {commit_hash[:8]}?\n\n"
                                    "All uncommitted changes will be lost."):
            return

        self._history_status.config(text="Reverting...", fg=T.AMBER)

        def _run():
            try:
                self._vcs.revert_to(commit_hash)
                self.after(0, lambda: self._history_status.config(
                    text=f"✓ Reverted to {commit_hash[:8]}", fg=T.GREEN))
                self.after(0, self._refresh_history)
                self.after(0, self._refresh_changes)
            except Exception as e:
                err = str(e)[:60]
                self.after(0, lambda: self._history_status.config(
                    text=f"Error: {err}", fg=T.RED))

        threading.Thread(target=_run, daemon=True).start()
