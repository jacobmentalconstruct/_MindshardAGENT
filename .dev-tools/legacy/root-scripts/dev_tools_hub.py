import os
import ast
import sys
import subprocess
import threading
import tkinter as tk
from tkinter import ttk
from pathlib import Path

# --- Dark Theme Colors ---
BG_DARK = "#121212"
BG_CARD = "#1e1e1e"
TEXT_MAIN = "#e0e0e0"
TEXT_MUTED = "#9e9e9e"
ACCENT = "#3b82f6"

def scan_for_tools():
    """Scans the current directory for Python files containing TOOL_METADATA."""
    tools = []
    current_dir = Path(__file__).parent
    
    for file_path in current_dir.glob("*.py"):
        if file_path.name == Path(__file__).name:
            continue # Skip this hub script itself
            
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                # Parse the AST to safely extract the dict without executing the code
                tree = ast.parse(f.read(), filename=file_path.name)
                for node in tree.body:
                    if isinstance(node, ast.Assign):
                        for target in node.targets:
                            if isinstance(target, ast.Name) and target.id == "TOOL_METADATA":
                                metadata = ast.literal_eval(node.value)
                                metadata["filename"] = file_path.name
                                tools.append(metadata)
        except Exception as e:
            print(f"Skipping {file_path.name} due to parse error: {e}")
            
    return sorted(tools, key=lambda x: x.get("name", ""))

class DevToolsHub(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Dev Tools Hub")
        self.geometry("750x450")
        self.configure(bg=BG_DARK)
        
        self.tools_data = scan_for_tools()
        
        self.setup_ui()
        self.populate_list()

    def setup_ui(self):
        # Configure grid
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Left Sidebar (Listbox)
        sidebar_frame = tk.Frame(self, bg=BG_CARD, padx=10, pady=10)
        sidebar_frame.grid(row=0, column=0, sticky="nsew", padx=(10, 5), pady=10)
        
        tk.Label(sidebar_frame, text="Available Tools", bg=BG_CARD, fg=TEXT_MAIN, font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(0, 10))
        
        # exportselection=False prevents the listbox from losing its blue highlight!
        self.tool_listbox = tk.Listbox(sidebar_frame, bg=BG_DARK, fg=TEXT_MAIN, borderwidth=0, 
                                       selectbackground=ACCENT, selectforeground="#fff", font=("Segoe UI", 10), exportselection=False)
        self.tool_listbox.pack(fill="both", expand=True)
        self.tool_listbox.bind('<<ListboxSelect>>', self.on_select)

        # Right Main Area (Details)
        details_frame = tk.Frame(self, bg=BG_CARD, padx=20, pady=20)
        details_frame.grid(row=0, column=1, sticky="nsew", padx=(5, 10), pady=10)
        
        # --- HEADER ROW ---
        header_frame = tk.Frame(details_frame, bg=BG_CARD)
        header_frame.pack(fill="x", pady=(0, 5))
        
        self.lbl_name = tk.Label(header_frame, text="Select a tool", bg=BG_CARD, fg=ACCENT, font=("Segoe UI", 16, "bold"))
        self.lbl_name.pack(side="left")
        
        self.btn_copy = tk.Button(header_frame, text="📋 Copy for Agent", bg=BG_DARK, fg=TEXT_MAIN, 
                                  font=("Segoe UI", 9), borderwidth=1, relief="solid", padx=8, pady=2, 
                                  command=self.copy_to_clipboard, state="disabled", cursor="hand2")
        self.btn_copy.pack(side="right")
        
        self.lbl_filename = tk.Label(details_frame, text="", bg=BG_CARD, fg=TEXT_MUTED, font=("Consolas", 10))
        self.lbl_filename.pack(anchor="w", pady=(0, 15))
        
        # Text box for Description & Usage
        self.txt_details = tk.Text(details_frame, bg=BG_DARK, fg=TEXT_MAIN, wrap="word", font=("Segoe UI", 11), borderwidth=0, padx=10, pady=10)
        self.txt_details.pack(fill="both", expand=True, pady=(0, 15))

        # --- RUNNER UI ---
        run_frame = tk.Frame(details_frame, bg=BG_CARD)
        run_frame.pack(fill="x", pady=(15, 5))
        tk.Label(run_frame, text="Args:", bg=BG_CARD, fg=TEXT_MAIN).pack(side="left")
        self.entry_args = tk.Entry(run_frame, bg=BG_DARK, fg=TEXT_MAIN, insertbackground=TEXT_MAIN, borderwidth=1, relief="solid")
        self.entry_args.pack(side="left", fill="x", expand=True, padx=10)
        self.btn_run = tk.Button(run_frame, text="▶ Run Tool", bg="#10b981", fg="#121212", font=("Segoe UI", 10, "bold"), borderwidth=0, padx=15, pady=5, command=self.run_tool, state="disabled", cursor="hand2")
        self.btn_run.pack(side="right")

        # --- CONSOLE OUTPUT ---
        tk.Label(details_frame, text="Terminal Output:", bg=BG_CARD, fg=TEXT_MUTED).pack(anchor="w", pady=(10, 0))
        self.txt_console = tk.Text(details_frame, bg="#000000", fg="#00ff00", font=("Consolas", 10), height=10, borderwidth=1, relief="solid")
        self.txt_console.pack(fill="both", expand=True, pady=(5, 0))
        self.txt_console.insert(tk.END, "Ready...\n")
        self.txt_console.config(state="disabled")

    def populate_list(self):
        for tool in self.tools_data:
            self.tool_listbox.insert(tk.END, tool.get("name", "Unknown Tool"))

    def on_select(self, event):
        selection = self.tool_listbox.curselection()
        if not selection:
            return
            
        index = selection[0]
        tool = self.tools_data[index]
        
        self.lbl_name.config(text=tool.get("name", ""))
        self.lbl_filename.config(text=f"File: {tool.get('filename', '')}")
        
        details_text = f"--- DESCRIPTION ---\n{tool.get('description', 'No description provided.')}\n\n"
        details_text += f"--- HOW TO USE ---\n{tool.get('usage', 'No usage instructions provided.')}\n"
        
        self.txt_details.delete("1.0", tk.END)
        self.txt_details.insert(tk.END, details_text)
        
        self.btn_copy.config(state="normal", text="📋 Copy for Agent", bg=BG_DARK)
        self.btn_run.config(state="normal")
        self.selected_tool_text = f"I want to use the local tool '{tool.get('name')}'.\nFilename: {tool.get('filename')}\nDescription: {tool.get('description')}\nUsage context: {tool.get('usage')}\n\nPlease provide the exact terminal command or JSON patch I need to run this tool to achieve my next goal."

    def copy_to_clipboard(self):
        self.clipboard_clear()
        self.clipboard_append(self.selected_tool_text)
        self.btn_copy.config(text="✔ Copied!", bg="#10b981")

    def run_tool(self):
        selection = self.tool_listbox.curselection()
        if not selection: return
        tool = self.tools_data[selection[0]]
        script_path = Path(__file__).parent / tool['filename']
        args = self.entry_args.get().strip().split()

        self.txt_console.config(state="normal")
        self.txt_console.delete("1.0", tk.END)
        self.txt_console.insert(tk.END, f"> Running: {tool['filename']} {' '.join(args)}\n\n")
        self.txt_console.config(state="disabled")
        self.btn_run.config(state="disabled", text="Running...")

        def thread_target():
            cmd = [sys.executable, str(script_path)] + args
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
            for line in iter(process.stdout.readline, ''):
                self.after(0, self._append_console, line)
            process.stdout.close()
            process.wait()
            self.after(0, self._run_finished, process.returncode)

        threading.Thread(target=thread_target, daemon=True).start()

    def _append_console(self, text):
        self.txt_console.config(state="normal")
        self.txt_console.insert(tk.END, text)
        self.txt_console.see(tk.END)
        self.txt_console.config(state="disabled")

    def _run_finished(self, returncode):
        self._append_console(f"\n[Process exited with code {returncode}]\n")
        self.btn_run.config(state="normal", text="▶ Run Tool")

if __name__ == "__main__":
    app = DevToolsHub()
    app.mainloop()