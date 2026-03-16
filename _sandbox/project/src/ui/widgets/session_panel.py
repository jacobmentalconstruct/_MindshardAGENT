"""Session management panel — list, select, rename, branch, delete sessions.

Displays active session list with controls. Fits in the control pane
or as a popup dialog.
"""

import tkinter as tk
from tkinter import simpledialog, messagebox
from src.ui import theme as T


class SessionPanel(tk.Frame):
    """Session list with management controls."""

    def __init__(self, parent, on_new=None, on_select=None, on_rename=None,
                 on_delete=None, on_branch=None, **kw):
        kw.setdefault("bg", T.BG_MID)
        super().__init__(parent, **kw)

        self._on_new = on_new
        self._on_select = on_select
        self._on_rename = on_rename
        self._on_delete = on_delete
        self._on_branch = on_branch
        self._sessions: list[dict] = []
        self._selected_sid: str | None = None

        # Header
        header = tk.Frame(self, bg=T.BG_MID)
        header.pack(fill="x", padx=8, pady=(6, 2))
        tk.Label(header, text="SESSIONS", font=T.FONT_SMALL,
                 fg=T.TEXT_DIM, bg=T.BG_MID).pack(side="left")

        # New session button
        new_btn = tk.Button(
            header, text="+ NEW", font=(T.FONT_FAMILY, T.FONT_SIZE_SM, "bold"),
            fg=T.GREEN, bg=T.BG_LIGHT, activebackground=T.BG_SURFACE,
            activeforeground=T.GREEN, relief="flat", bd=0, cursor="hand2",
            padx=6, pady=1, command=self._handle_new,
        )
        new_btn.pack(side="right")
        new_btn.bind("<Enter>", lambda e: new_btn.config(bg=T.BG_SURFACE))
        new_btn.bind("<Leave>", lambda e: new_btn.config(bg=T.BG_LIGHT))

        # Session listbox
        list_frame = tk.Frame(self, bg=T.BG_DARK)
        list_frame.pack(fill="both", expand=True, padx=8, pady=(2, 4))

        self._listbox = tk.Listbox(
            list_frame, font=T.FONT_SMALL,
            fg=T.TEXT_PRIMARY, bg=T.BG_LIGHT,
            selectbackground=T.BG_SURFACE, selectforeground=T.CYAN,
            highlightthickness=1, highlightcolor=T.BORDER_GLOW,
            highlightbackground=T.BORDER,
            relief="flat", bd=0, height=6,
            activestyle="none",
        )
        scrollbar = tk.Scrollbar(list_frame, orient="vertical",
                                  command=self._listbox.yview,
                                  bg=T.SCROLLBAR_BG, troughcolor=T.SCROLLBAR_BG)
        self._listbox.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self._listbox.pack(side="left", fill="both", expand=True)
        self._listbox.bind("<<ListboxSelect>>", self._handle_select)

        # Action buttons row
        btn_row = tk.Frame(self, bg=T.BG_MID)
        btn_row.pack(fill="x", padx=8, pady=(0, 6))

        for label, cmd, color in [
            ("Rename", self._handle_rename, T.CYAN),
            ("Branch", self._handle_branch, T.PURPLE),
            ("Delete", self._handle_delete, T.RED),
        ]:
            btn = tk.Button(
                btn_row, text=label, font=(T.FONT_FAMILY, T.FONT_SIZE_SM),
                fg=color, bg=T.BG_LIGHT, activebackground=T.BG_SURFACE,
                activeforeground=color, relief="flat", bd=0,
                padx=6, pady=1, cursor="hand2", command=cmd,
            )
            btn.pack(side="left", padx=2)
            btn.bind("<Enter>", lambda e, b=btn, c=color: b.config(bg=T.BG_SURFACE))
            btn.bind("<Leave>", lambda e, b=btn: b.config(bg=T.BG_LIGHT))

    def set_sessions(self, sessions: list[dict], active_sid: str | None = None) -> None:
        """Update the session list. Each dict needs session_id and title."""
        self._sessions = sessions
        self._selected_sid = active_sid
        self._listbox.delete(0, "end")
        for i, s in enumerate(sessions):
            prefix = "► " if s["session_id"] == active_sid else "  "
            self._listbox.insert("end", f"{prefix}{s['title']}")
            if s["session_id"] == active_sid:
                self._listbox.selection_set(i)

    def _get_selected_session(self) -> dict | None:
        sel = self._listbox.curselection()
        if not sel or sel[0] >= len(self._sessions):
            return None
        return self._sessions[sel[0]]

    def _handle_select(self, _event=None) -> None:
        session = self._get_selected_session()
        if session and self._on_select:
            self._on_select(session["session_id"])

    def _handle_new(self) -> None:
        if self._on_new:
            self._on_new()

    def _handle_rename(self) -> None:
        session = self._get_selected_session()
        if not session:
            return
        new_title = simpledialog.askstring(
            "Rename Session", "New title:",
            initialvalue=session["title"],
            parent=self,
        )
        if new_title and new_title.strip() and self._on_rename:
            self._on_rename(session["session_id"], new_title.strip())

    def _handle_branch(self) -> None:
        session = self._get_selected_session()
        if not session:
            return
        if self._on_branch:
            self._on_branch(session["session_id"])

    def _handle_delete(self) -> None:
        session = self._get_selected_session()
        if not session:
            return
        confirm = messagebox.askyesno(
            "Delete Session",
            f"Delete session '{session['title']}'?\nThis cannot be undone.",
            parent=self,
        )
        if confirm and self._on_delete:
            self._on_delete(session["session_id"])
