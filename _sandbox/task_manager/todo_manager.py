import tkinter as tk
from tkinter import ttk
import json
from datetime import datetime
import os

class TodoManager:
    def __init__(self, root):
        self.root = root
        self.root.title('📝 Task Manager')
        self.root.geometry('500x600')
        self.root.configure(bg='#f5f5f5')
        
        # Store tasks in JSON file
        self.tasks_file = 'tasks.json'
        self.tasks = []
        self.load_tasks()
        
        # Create main container
        main_frame = ttk.Frame(root, padding='20')
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Header
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill=tk.X, pady=10)
        
        self.title_label = tk.Label(
            header_frame,
            text='Task Manager',
            font=('Arial', 24, 'bold'),
            bg='#ffffff',
            fg='#2c3e50'
        )
        self.title_label.pack(side=tk.LEFT)
        
        self.date_label = tk.Label(
            header_frame,
            text=datetime.now().strftime('%B %d, %Y'),
            font=('Arial', 14),
            bg='#ffffff',
            fg='#7f8c8d'
        )
        self.date_label.pack(side=tk.RIGHT)
        
        # Task list container
        list_frame = ttk.Frame(main_frame)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # Task listbox
        self.task_listbox = tk.Listbox(
            list_frame,
            selectmode=tk.EXTENDED,
            font=('Arial', 12),
            bg='#ffffff',
            fg='#2c3e50',
            highlightthickness=1,
            bordercolor='#000000',
            highlightbackground='#3498db'
        )
        self.task_listbox.pack(fill=tk.BOTH, expand=True)
        
        # Progress bar
        self.progress_label = tk.Label(
            list_frame,
            text=f"{len(self.tasks)}/{len(self.tasks)} Tasks Completed",
            font=('Arial', 11),
            bg='#ffffff',
            fg='#27ae60'
        )
        self.progress_label.pack(fill=tk.X, pady=5)
        
        # Input frame
        input_frame = ttk.Frame(main_frame)
        input_frame.pack(fill=tk.X, pady=10)
        
        # Task entry
        self.task_entry = tk.Entry(
            input_frame,
            width=45,
            font=('Arial', 12),
            bg='#ffffff',
            fg='#2c3e50',
            relief=tk.SOLID,
            borderwidth=1,
            highlightthickness=2,
            highlightcolor='#3498db'
        )
        self.task_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        # Action buttons
        self.add_btn = ttk.Button(
            input_frame,
            text='Add',
            command=self.add_task,
            width=8
        )
        self.add_btn.pack(side=tk.LEFT, padx=5)
        
        self.delete_btn = ttk.Button(
            input_frame,
            text='Delete',
            command=self.delete_task,
            width=8
        )
        self.delete_btn.pack(side=tk.LEFT, padx=5)
        
        self.complete_btn = ttk.Button(
            input_frame,
            text='Complete',
            command=self.complete_task,
            width=8
        )
        self.complete_btn.pack(side=tk.LEFT, padx=5)
        
        # Update UI
        self.update_task_display()
        self.update_progress()
    
    def load_tasks(self):
        if os.path.exists(self.tasks_file):
            try:
                with open(self.tasks_file, 'r') as f:
                    self.tasks = json.load(f)
            except (json.JSONDecodeError, IOError):
                self.tasks = []
        else:
            self.tasks = []
    
    def save_tasks(self):
        try:
            with open(self.tasks_file, 'w') as f:
                json.dump(self.tasks, f, indent=2)
        except IOError as e:
            print(f"Error saving tasks: {e}")
    
    def add_task(self):
        text = self.task_entry.get().strip()
        if text:
            new_task = {
                'text': text,
                'completed': False,
                'created': datetime.now().isoformat()
            }
            self.tasks.append(new_task)
            self.save_tasks()
            self.task_entry.delete(0, tk.END)
            self.update_task_display()
            self.update_progress()
    
    def delete_task(self):
        selection = self.task_listbox.curselection()
        if selection:
            index = selection[-1]
            self.tasks.pop(index)
            self.save_tasks()
            self.update_task_display()
            self.update_progress()
    
    def complete_task(self):
        selection = self.task_listbox.curselection()
        if selection:
            index = selection[-1]
            self.tasks[index]['completed'] = True
            self.save_tasks()
            self.update_task_display()
            self.update_progress()
    
    def update_task_display(self):
        self.task_listbox.delete(0, tk.END)
        for i, task in enumerate(self.tasks):
            status = '✅ ' if task['completed'] else '❌ '
            text = f"{status} {task['text']}"
            self.task_listbox.insert(i, text)
    
    def update_progress(self):
        completed = sum(1 for t in self.tasks if t['completed'])
        self.progress_label.config(text=f"{completed}/{len(self.tasks)} Tasks Completed")
    
    def clear_all(self):
        confirmation = tk.messagebox.askyesno(
            'Clear All',
            'Are you sure you want to clear all tasks?'
        )
        if confirmation:
            self.tasks = []
            self.save_tasks()
            self.update_task_display()
            self.update_progress()
    
    def show_stats(self):
        total = len(self.tasks)
        completed = sum(1 for t in self.tasks if t['completed'])
        pending = total - completed
        
        stats = [
            f"Total Tasks: {total}",
            f"Completed: {completed}",
            f"Pending: {pending}",
            f"Completion Rate: {completed/total*100:.1f}%"
        ]
        
        message = tk.messagebox.showinfo(
            'Task Statistics',
            '\n'.join(stats)
        )

# Run the application
if __name__ == '__main__':
    root = tk.Tk()
    app = TodoManager(root)
    root.mainloop()
